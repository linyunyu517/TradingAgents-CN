# tradingagents/diffusion/diffusion_scenario.py
"""
扩散市场情景生成器 — Score-SDE + Euler-Maruyama 采样

基于 Score-SDE 框架 (Song et al., ICLR 2021) 的压力测试引擎：
    dx = f(x,t)dt + g(t)dw   (前向 SDE)
    dx = [f(x,t) - g(t)^2 * s_θ(x,t)]dt + g(t)dw̄  (反向 SDE)

功能:
    1. 接收当前市场状态 + 条件变量（利率变动/波动率冲击等）
    2. 生成 1000+ 条件市场轨迹
    3. 计算风险指标（VaR、CVaR、最大回撤分布）
    4. 输出压力测试报告

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DiffusionConfig / UniformPrior 基础设施兼容
    - 失败时自动退化为均匀先验（非降级机制）
    - 批量处理支持 1000+ 情景的高效生成

用法:
    >>> from tradingagents.diffusion.diffusion_scenario import DiffusionScenarioGenerator
    >>> generator = DiffusionScenarioGenerator()
    >>> result = generator.generate_scenarios(
    ...     current_state=np.random.randn(1, 16),
    ...     n_scenarios=1000,
    ...     horizon=200,
    ... )
    >>> print(f"VaR_95: {result['VaR_95']:.4f}")
"""

from __future__ import annotations

import logging

import numpy as np

from .config import DiffusionConfig
from .uniform_prior import uniform_prior

logger = logging.getLogger(__name__)


class EulerMaruyamaSDE:
    """Euler-Maruyama SDE 离散化采样器

    实现正/反向 SDE 的 Euler-Maruyama 离散化：

        正向:  x_{t+1} = x_t + f(x,t)dt + g(t)√|dt|·ε
        反向:  x_{t+1} = x_t + [f(x,t) - g(t)²·s_θ(x,t)]dt + g(t)√|dt|·ε

    Attributes:
        drift_fn:      漂移函数 f(x, t) -> drift
        diffusion_fn:  扩散系数函数 g(t) -> scalar
        score_fn:      Score 函数 s_θ(x, t) -> score
        dt:            离散化时间步长
    """

    def __init__(
        self,
        drift_fn,
        diffusion_fn,
        score_fn,
        dt: float = 0.01,
    ):
        self.drift_fn = drift_fn
        self.diffusion_fn = diffusion_fn
        self.score_fn = score_fn
        self.dt = dt

    def sample(
        self,
        x0: np.ndarray,
        n_steps: int,
        reverse: bool = True,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        SDE 采样（正向加噪 / 反向生成）

        Args:
            x0:         初始状态, shape (batch, dim)
            n_steps:    离散化步数
            reverse:     True=反向SDE(生成), False=正向SDE(加噪)

        Returns:
            trajectory:  (n_steps+1, batch, dim) 完整轨迹
            x_final:     (batch, dim) 最终状态
        """
        batch_size, dim = x0.shape
        trajectory = np.zeros((n_steps + 1, batch_size, dim), dtype=np.float32)
        trajectory[0] = x0
        x = x0.copy()

        for i in range(n_steps):
            t = i / n_steps
            dt = self.dt if reverse else -self.dt

            # 漂移项: f(x, t)
            drift = self.drift_fn(x, t)

            # 扩散系数: g(t)
            g = float(self.diffusion_fn(t))

            if reverse:
                # 反向 SDE: dx = [f - g² · s_θ]dt + g dw̄
                score = self.score_fn(x, t)
                drift_eff = drift - g**2 * score
            else:
                # 正向 SDE: dx = f(x,t)dt + g(t)dw
                drift_eff = drift

            # Wiener 增量: ε ~ N(0, 1)
            noise = np.random.randn(batch_size, dim).astype(np.float32)

            # Euler-Maruyama 更新
            x = x + drift_eff * dt + g * np.sqrt(abs(dt)) * noise

            trajectory[i + 1] = x

        return trajectory, x


class DiffusionScenarioGenerator:
    """
    扩散市场情景生成器（压力测试引擎）

    基于 Score-SDE + Euler-Maruyama 采样，一次生成 1000+
    条件市场轨迹，用于压力测试和风险指标计算。

    输入: 当前市场状态 + 条件变量（利率冲击、波动率冲击等）
    输出: 条件市场轨迹 + 风险指标（VaR, CVaR, 最大回撤分布）

    架构:
        - 使用轻量 MLP 作为 Score 函数近似
        - Ornstein-Uhlenbeck 漂移（均值回归，适合金融数据）
        - 可配置的扩散系数（复用 DiffusionConfig 噪声调度）
        - 自动退化到均匀先验（当采样失败时）
    """

    def __init__(self, config: DiffusionConfig | None = None):
        self.config = config or DiffusionConfig()
        # 使用占位维度初始化（_ensure_calibrated 会在首次 generate_scenarios 时重建）
        self._calibrated = False
        self._feat_dim: int | None = None
        self._build_score_fn(feat_dim=1)

    # ------------------------------------------------------------------
    # Score 网络构建
    # ------------------------------------------------------------------

    def _build_score_fn(self, feat_dim: int = 16) -> None:
        """构建轻量参数化 Score 网络（线性 + ReLU 近似）

        使用两层 MLP 近似 score 函数 s_θ(x, t)：
            h = ReLU(concat(x, t) @ W1 + b1)
            s = h @ W2 + b2

        网络权重使用小随机初始化（std=0.02），
        确保初始 score 接近零（对应纯噪声预测）。

        Args:
            feat_dim: 特征维度，首次构造时使用占位值，_ensure_calibrated 会重建
        """
        hidden_dim = self.config.hidden_dim

        # W1: (feat_dim + 1, hidden_dim) — +1 用于时间编码
        self.W1 = np.random.randn(feat_dim + 1, hidden_dim).astype(np.float32) * 0.02
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)

        # W2: (hidden_dim, feat_dim)
        self.W2 = np.random.randn(hidden_dim, feat_dim).astype(np.float32) * 0.02
        self.b2 = np.zeros(feat_dim, dtype=np.float32)

        self._feat_dim = feat_dim

    def _score_fn(self, x: np.ndarray, t: float) -> np.ndarray:
        """Score 函数 s_θ(x, t)

        将时间 t 拼接到输入上，通过两层 MLP 计算 score。

        Args:
            x: 当前状态, shape (batch, dim)
            t: 当前时间 [0, 1]

        Returns:
            np.ndarray: score 估计, shape (batch, dim)
        """
        t_vec = np.full((x.shape[0], 1), t, dtype=np.float32)
        xt = np.concatenate([x, t_vec], axis=-1)

        h = xt @ self.W1 + self.b1
        h = np.maximum(h, 0)  # ReLU
        score = h @ self.W2 + self.b2
        return score

    # ------------------------------------------------------------------
    # SDE 系数函数
    # ------------------------------------------------------------------

    def _drift_fn(self, x: np.ndarray, t: float) -> np.ndarray:
        """前向漂移: f(x,t) = -0.5 · x

        使用 Ornstein-Uhlenbeck 过程，适合金融数据的均值回归特性。
        θ = 0.5 对应中等回归速度，半衰期约为 1.39 个时间单位。

        Args:
            x: 当前状态, shape (batch, dim)
            t: 当前时间（未使用，保留接口兼容性）

        Returns:
            np.ndarray: 漂移项, shape (batch, dim)
        """
        return -0.5 * x

    def _diffusion_fn(self, t: float) -> float:
        """扩散系数: g(t) = √β(t)

        从 DiffusionConfig 预计算的 β 调度中插值获取当前时间步的 β，
        取平方根得到扩散系数。

        Args:
            t: 归一化时间 [0, 1]

        Returns:
            float: 扩散系数 g(t)
        """
        betas = self.config.betas  # shape (T,)
        idx = min(int(t * len(betas)), len(betas) - 1)
        return float(np.sqrt(betas[idx]))

    # ------------------------------------------------------------------
    # 懒初始化维度校准
    # ------------------------------------------------------------------

    def _ensure_calibrated(self, current_state: np.ndarray) -> None:
        """首次调用时根据实际特征维度重建 Score 网络

        当 current_state 的特征维度与当前 _feat_dim 不匹配时，
        以正确维度重新构建 _build_score_fn。

        Args:
            current_state: 当前市场状态, shape (batch, features)
        """
        feat_dim = current_state.shape[-1]
        if not self._calibrated or self._feat_dim != feat_dim:
            self._feat_dim = feat_dim
            self._build_score_fn(feat_dim=feat_dim)
            self._calibrated = True
            logger.info(
                "DiffusionScenarioGenerator 维度校准: feat_dim=%d",
                feat_dim,
            )

    # ------------------------------------------------------------------
    # 主采样接口
    # ------------------------------------------------------------------

    def generate_scenarios(
        self,
        current_state: np.ndarray,
        condition: np.ndarray | None = None,
        n_scenarios: int = 1000,
        horizon: int = 200,
        dt: float = 0.01,
    ) -> dict:
        """
        生成条件市场轨迹

        执行完整的扩散生成流程：
            1. 条件注入 → 调整初始状态
            2. 正向加噪 → 将状态扩散到 T/2
            3. 反向去噪 → 从噪声生成新轨迹
            4. 风险指标计算 → VaR, CVaR, 最大回撤

        Args:
            current_state:  当前市场状态, shape (batch, features)
            condition:      条件变量, shape (batch, cond_dim) 或 None
                            条件按比例叠加到初始状态的前 cond_dim 维
            n_scenarios:    生成情景数量（默认 1000）
            horizon:        前向步数，如 200 个交易日（默认 200）
            dt:             SDE 离散化时间步长（默认 0.01）

        Returns:
            dict: 包含以下键值:
                - 'trajectories':      (n_scenarios, horizon+1, features) 全部轨迹
                - 'final_states':      (n_scenarios, features) 终态分布
                - 'returns':           (n_scenarios, horizon, features) 逐日收益率
                - 'cumulative_returns':  (n_scenarios, horizon) 累计收益
                - 'VaR_95':            95% 在险价值
                - 'CVaR_95':           95% 条件在险价值
                - 'max_drawdown':       (n_scenarios,) 最大回撤分布
                - 'max_drawdown_mean':  平均最大回撤
                - 'max_drawdown_worst': 最差最大回撤
                - 'profitable_probability': 盈利概率

        Raises:
            ValueError: 当输入形状无效时
        """
        if current_state.ndim != 2:
            raise ValueError(f"current_state 应为 2D (batch, features), 但得到 {current_state.ndim}D")

        # --- 懒初始化维度校准 ---
        self._ensure_calibrated(current_state)

        batch_size, feat_dim = current_state.shape

        # ---- 1. 条件注入 ----
        if condition is not None:
            if condition.ndim != 2:
                raise ValueError(f"condition 应为 2D (batch, cond_dim), 但得到 {condition.ndim}D")
            cond_dim = min(condition.shape[1], feat_dim)
            current_state = current_state.copy()
            current_state[:, :cond_dim] += 0.1 * condition[:, :cond_dim]

        # ---- 2. 创建 SDE 采样器 ----
        sampler = EulerMaruyamaSDE(
            drift_fn=self._drift_fn,
            diffusion_fn=self._diffusion_fn,
            score_fn=self._score_fn,
            dt=dt,
        )

        # ---- 3. 批量生成轨迹 ----
        all_trajectories: list[np.ndarray] = []
        scenarios_per_batch = min(n_scenarios, 100)  # 每批最多 100 个情景

        for start in range(0, n_scenarios, scenarios_per_batch):
            end = min(start + scenarios_per_batch, n_scenarios)
            current_batch = end - start

            # 平铺当前状态到批次数
            repeats = current_batch // batch_size + 1
            x0 = np.tile(current_state, (repeats, 1))[:current_batch]

            try:
                # 4a. 正向加噪到 T/2
                _, x_noisy = sampler.sample(x0, n_steps=horizon // 2, reverse=False)

                # 4b. 反向去噪生成完整轨迹
                trajectory, _ = sampler.sample(x_noisy, n_steps=horizon, reverse=True)
                all_trajectories.append(trajectory)

            except Exception as e:
                logger.warning(
                    "扩散情景采样失败 (batch=%d-%d): %s, 退化为均匀先验",
                    start,
                    end,
                    e,
                )
                traj = uniform_prior(
                    (horizon + 1, current_batch, feat_dim),
                    low=-1.0,
                    high=1.0,
                ).astype(np.float32)
                all_trajectories.append(traj)

        # ---- 4. 合并批次 ----
        # 各批次 shape: (horizon+1, batch_i, feat_dim)
        # 拼接后: (horizon+1, total, feat_dim)
        trajectories = np.concatenate(all_trajectories, axis=1)

        # 转置为: (n_scenarios, horizon+1, features)
        trajectories = trajectories.transpose(1, 0, 2)

        # 截取精确的 n_scenarios
        trajectories = trajectories[:n_scenarios]

        final_states = trajectories[:, -1, :]  # (n_scenarios, features)

        # ---- 5. 风险指标计算 ----

        # 逐日收益率: (n_scenarios, horizon, features)
        returns = np.diff(trajectories, axis=1) / (np.abs(trajectories[:, :-1, :]) + 1e-8)

        # 按资产维度平均的收益率: (n_scenarios, horizon)
        portfolio_returns = np.mean(returns, axis=-1)

        # 累计收益: (n_scenarios, horizon)
        cumulative_returns = np.cumprod(1 + portfolio_returns, axis=-1) - 1

        # 终期累计收益: (n_scenarios,)
        final_cumret = cumulative_returns[:, -1]

        # VaR_95: 5% 分位数（最差的 5% 尾部损失）
        var_95 = float(np.percentile(final_cumret, 5))

        # CVaR_95: 低于 VaR 的尾部均值
        cvar_mask = final_cumret <= var_95
        cvar_95 = float(np.mean(final_cumret[cvar_mask])) if np.any(cvar_mask) else var_95

        # 最大回撤: (n_scenarios,)
        peak = np.maximum.accumulate(cumulative_returns + 1, axis=-1)
        drawdown = (cumulative_returns + 1) / peak - 1
        max_drawdown = np.min(drawdown, axis=-1)

        return {
            # 原始数据
            "trajectories": trajectories,
            "final_states": final_states,
            "returns": returns,
            "cumulative_returns": cumulative_returns,
            # 风险指标
            "VaR_95": var_95,
            "CVaR_95": cvar_95,
            "max_drawdown": max_drawdown,
            "max_drawdown_mean": float(np.mean(max_drawdown)),
            "max_drawdown_worst": float(np.min(max_drawdown)),
            "max_drawdown_std": float(np.std(max_drawdown)),
            "profitable_probability": float(np.mean(final_cumret > 0)),
            "expected_return": float(np.mean(final_cumret)),
            "return_volatility": float(np.std(final_cumret)),
        }

    # ------------------------------------------------------------------
    # 压力测试
    # ------------------------------------------------------------------

    def stress_test(
        self,
        current_state: np.ndarray,
        shock_scenarios: list[tuple[str, np.ndarray]] | None = None,
        n_scenarios_per_shock: int = 200,
        horizon: int = 100,
    ) -> dict:
        """
        压力测试：对预定义的冲击情景生成响应

        对每种冲击情景运行 generate_scenarios，汇总风险指标。
        适用于"利率突变 +100bp 会怎样？"等压力测试场景。

        Args:
            current_state:         当前市场状态, shape (1, features)
            shock_scenarios:       冲击情景列表 [(名称, 冲击向量), ...]
                                    默认包含 5 种常见冲击:
                                    - 利率+100bp
                                    - 利率-100bp
                                    - 波动率翻倍
                                    - 流动性危机
                                    - 市场崩盘
            n_scenarios_per_shock: 每种冲击生成的情景数（默认 200）
            horizon:               前向步数（默认 100）

        Returns:
            dict: {情景名称: {VaR_95, CVaR_95, max_drawdown_mean, ...}, ...}
                  以及 'baseline': 无冲击的基准结果
        """
        if shock_scenarios is None:
            # 默认 5 种标准金融冲击情景
            n_feats = current_state.shape[1]
            shock_scenarios = [
                ("利率+100bp", self._make_shock(n_feats, {0: 0.01})),
                ("利率-100bp", self._make_shock(n_feats, {0: -0.01})),
                ("波动率翻倍", self._make_shock(n_feats, {1: 0.02})),
                ("流动性危机", self._make_shock(n_feats, {2: -0.03})),
                ("市场崩盘", self._make_shock(n_feats, {0: -0.05, 1: 0.03, 2: -0.02})),
            ]

        # ---- 基准（无冲击） ----
        try:
            baseline = self.generate_scenarios(
                current_state,
                condition=None,
                n_scenarios=n_scenarios_per_shock,
                horizon=horizon,
            )
        except Exception as e:
            logger.warning("基准情景生成失败: %s", e)
            baseline = self._empty_result()

        results: dict = {
            "baseline": self._extract_risk_metrics(baseline),
        }

        # ---- 各冲击情景 ----
        for name, shock in shock_scenarios:
            try:
                result = self.generate_scenarios(
                    current_state,
                    condition=shock,
                    n_scenarios=n_scenarios_per_shock,
                    horizon=horizon,
                )
                results[name] = self._extract_risk_metrics(result)
            except Exception as e:
                logger.warning("冲击情景 '%s' 生成失败: %s", name, e)
                results[name] = self._empty_risk_metrics()

        return results

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _make_shock(feat_dim: int, assignments: dict) -> np.ndarray:
        """构造冲击向量

        Args:
            feat_dim:     特征维度
            assignments:  特征索引 -> 冲击幅值映射

        Returns:
            np.ndarray: shape (1, feat_dim) 的冲击向量
        """
        shock = np.zeros((1, feat_dim), dtype=np.float32)
        for idx, val in assignments.items():
            if idx < feat_dim:
                shock[0, idx] = val
        return shock

    @staticmethod
    def _extract_risk_metrics(result: dict) -> dict:
        """从 generate_scenarios 结果中提取风险指标摘要"""
        return {
            "VaR_95": result.get("VaR_95", 0.0),
            "CVaR_95": result.get("CVaR_95", 0.0),
            "max_drawdown_mean": result.get("max_drawdown_mean", 0.0),
            "max_drawdown_worst": result.get("max_drawdown_worst", 0.0),
            "max_drawdown_std": result.get("max_drawdown_std", 0.0),
            "profitable_probability": result.get("profitable_probability", 0.0),
            "expected_return": result.get("expected_return", 0.0),
            "return_volatility": result.get("return_volatility", 0.0),
        }

    @staticmethod
    def _empty_risk_metrics() -> dict:
        """返回空风险指标（用于异常退路）"""
        return {
            "VaR_95": 0.0,
            "CVaR_95": 0.0,
            "max_drawdown_mean": 0.0,
            "max_drawdown_worst": 0.0,
            "max_drawdown_std": 0.0,
            "profitable_probability": 0.0,
            "expected_return": 0.0,
            "return_volatility": 0.0,
            "_fallback": True,
        }

    @staticmethod
    def _empty_result() -> dict:
        """返回空结果（用于异常退路）"""
        return {
            "VaR_95": 0.0,
            "CVaR_95": 0.0,
            "max_drawdown_mean": 0.0,
            "max_drawdown_worst": 0.0,
            "profitable_probability": 0.0,
        }

    def get_report_summary(self, result: dict) -> str:
        """生成压力测试报告文本摘要

        Args:
            result: generate_scenarios() 或 stress_test() 的输出

        Returns:
            str: 格式化的报告摘要
        """
        lines = [
            "=" * 60,
            "扩散市场情景生成 — 压力测试报告",
            "=" * 60,
        ]

        if "VaR_95" in result:
            # 单次情景结果
            lines.extend(
                [
                    f"  VaR_95 (95%在险价值):   {result['VaR_95']:>8.4f}",
                    f"  CVaR_95 (95%条件VaR):   {result['CVaR_95']:>8.4f}",
                    f"  平均最大回撤:            {result.get('max_drawdown_mean', 0):>8.4f}",
                    f"  最差最大回撤:            {result.get('max_drawdown_worst', 0):>8.4f}",
                    f"  最大回撤标准差:          {result.get('max_drawdown_std', 0):>8.4f}",
                    f"  盈利概率:                {result.get('profitable_probability', 0):>7.2%}",
                    f"  预期收益:                {result.get('expected_return', 0):>8.4f}",
                    f"  收益波动率:              {result.get('return_volatility', 0):>8.4f}",
                ],
            )
        else:
            # 压力测试对比结果 (含 baseline)
            for scenario_name, metrics in result.items():
                lines.append(f"\n  --- {scenario_name} ---")
                if metrics.get("_fallback"):
                    lines.append("    [采样失败，使用均匀先验回退]")
                lines.extend(
                    [
                        f"    VaR_95:              {metrics['VaR_95']:>8.4f}",
                        f"    CVaR_95:             {metrics['CVaR_95']:>8.4f}",
                        f"    最大回撤(平均):      {metrics['max_drawdown_mean']:>8.4f}",
                        f"    最大回撤(最差):      {metrics['max_drawdown_worst']:>8.4f}",
                        f"    盈利概率:            {metrics['profitable_probability']:>7.2%}",
                    ],
                )

        lines.append("=" * 60)
        return "\n".join(lines)


# ------------------------------------------------------------------
# 便捷工厂函数
# ------------------------------------------------------------------


def create_scenario_generator(
    config: DiffusionConfig | None = None,
) -> DiffusionScenarioGenerator:
    """创建 DiffusionScenarioGenerator 实例的便捷函数

    Args:
        config: 扩散模型配置（可选）

    Returns:
        DiffusionScenarioGenerator: 情景生成器实例
    """
    return DiffusionScenarioGenerator(config=config)


__all__ = [
    "DiffusionScenarioGenerator",
    "EulerMaruyamaSDE",
    "create_scenario_generator",
]
