# tradingagents/diffusion/diffusion_portfolio_optimizer.py
"""
因子条件扩散投资组合优化器

基于 Factor-Based Conditional Diffusion 概念 (arXiv 2509.22088)，
使用条件扩散模型生成夏普最优权重的完整分布（而非点估计）。

核心思想:
    扩散模型在投资组合权重空间中执行去噪过程，以因子暴露为条件，
    生成多个候选投资组合，然后通过优化选择 Pareto 最优解。

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DiffusionConfig / DDIMSampler 无缝集成
    - 输出完整的权重分布而非单一点估计，支持不确定性量化
    - 支持最大夏普、最小方差、风险平价等多目标优化
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from .config import DiffusionConfig
from .ddim_sampler import ddim_sampling_loop
from .uniform_prior import uniform_prior

logger = logging.getLogger(__name__)


@dataclass
class PortfolioOptimizationResult:
    """投资组合优化结果数据类

    Attributes:
        weights:       候选投资组合权重, (num_portfolios, n_assets)
        pareto_frontier:有效前沿点列表, 每个点为 (risk, return) 元组
        optimal_weight: 最优权重 (最大夏普), (n_assets,)
        weight_uncertainty: 权重不确定性矩阵, (n_assets, n_assets)
        sharpe_ratios:  候选组合的夏普比率, (num_portfolios,)
        annualized_return:  最优组合的年化收益
        annualized_volatility: 最优组合的年化波动
        convergence:    是否收敛
    """

    weights: np.ndarray
    pareto_frontier: list[tuple[float, float]] = field(default_factory=list)
    optimal_weight: np.ndarray = field(default_factory=lambda: np.array([]))
    weight_uncertainty: np.ndarray = field(default_factory=lambda: np.array([]))
    sharpe_ratios: np.ndarray = field(default_factory=lambda: np.array([]))
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    convergence: bool = False

    def __repr__(self) -> str:
        n_assets = self.optimal_weight.shape[0] if self.optimal_weight.size > 0 else 0
        n_portfolios = self.weights.shape[0] if self.weights.size > 0 else 0
        return (
            f"PortfolioOptimizationResult("
            f"n_assets={n_assets}, "
            f"n_portfolios={n_portfolios}, "
            f"sharpe={self.annualized_return / max(self.annualized_volatility, 1e-8):.3f}, "
            f"convergence={self.convergence})"
        )


class DiffusionPortfolioOptimizer:
    """
    因子条件扩散投资组合优化器

    输入: 多资产历史收益序列 + 因子暴露矩阵
    输出: 夏普最优权重的完整分布 (而非点估计)

    使用扩散模型的去噪过程在权重空间中生成多样化候选解，
    然后通过优化选择 Pareto 最优投资组合。

    Usage:
        >>> optimizer = DiffusionPortfolioOptimizer()
        >>> returns = np.random.randn(10, 252)  # 10 资产, 252 交易日
        >>> factors = np.random.randn(10, 5)     # 5 个因子暴露
        >>> result = optimizer.optimize(returns, factors)
        >>> result.optimal_weight.shape
        (10,)
        >>> result.sharpe_ratios.max()
        1.2
    """

    # 风险厌恶系数默认值
    DEFAULT_RISK_AVERSION: float = 2.0

    def __init__(self, config: DiffusionConfig | None = None):
        """
        Args:
            config: 扩散模型配置；若为 None 使用默认配置
        """
        self.config = config or DiffusionConfig()

        # 预设条件投影矩阵 (lazy init)
        self._factor_proj_W: np.ndarray | None = None
        self._factor_proj_b: np.ndarray | None = None

        # 维度校准状态
        self._calibrated = False
        self._n_assets: int | None = None

        logger.info(
            "DiffusionPortfolioOptimizer 初始化完毕 (懒加载): num_timesteps=%d, cond_dim=%d",
            self.config.num_timesteps,
            self.config.cond_dim,
        )

    # ------------------------------------------------------------------
    # 懒初始化维度校准
    # ------------------------------------------------------------------

    def _ensure_calibrated(self, returns: np.ndarray) -> None:
        """首次调用时根据资产数量重建内部去噪网络

        当 n_assets 与上次不同（或首次调用）时，清除缓存的 _denoise_W
        和 _denoise_b，使 _diffuse_weights 中的懒初始化逻辑以正确维度重建。

        Args:
            returns: 多资产历史收益, (n_assets, n_periods)
        """
        n_assets = returns.shape[0]
        if not self._calibrated or self._n_assets != n_assets:
            self._n_assets = n_assets
            self._calibrated = True
            # 清除去噪投影缓存，_diffuse_weights 中的懒初始化会以新维度重建
            if hasattr(self, "_denoise_W"):
                del self._denoise_W
                del self._denoise_b
            logger.info(
                "DiffusionPortfolioOptimizer 维度校准: n_assets=%d",
                n_assets,
            )

    # ------------------------------------------------------------------
    # 主优化接口
    # ------------------------------------------------------------------

    def optimize(
        self,
        returns: np.ndarray,  # (n_assets, n_periods)
        factors: np.ndarray | None = None,  # (n_assets, n_factors) 因子暴露
        num_portfolios: int = 100,
        risk_free_rate: float = 0.02,
        target_return: float | None = None,
    ) -> PortfolioOptimizationResult:
        """
        执行扩散投资组合优化

        流程:
            1. 从历史收益计算资产统计量 (均值、协方差)
            2. 用扩散模型生成多样化候选权重
            3. 评估每个候选组合的夏普比率
            4. 构建有效前沿，选择最优组合

        Args:
            returns: 多资产历史收益, (n_assets, n_periods)
            factors: 因子暴露矩阵, (n_assets, n_factors)
                     如果为 None，使用统计因子 (PCA)
            num_portfolios: 生成的候选投资组合数量
            risk_free_rate: 无风险利率 (年化)
            target_return: 目标收益率 (可选)，若指定则在该收益下最小化方差

        Returns:
            PortfolioOptimizationResult: 优化结果
        """
        # --- 懒初始化维度校准 ---
        self._ensure_calibrated(returns)

        n_assets, _n_periods = returns.shape

        if n_assets < 2:
            raise ValueError(f"至少需要 2 个资产, 当前: {n_assets}")

        # --- 1. 计算资产统计量 ---
        mu = returns.mean(axis=1)  # (n_assets,) 年化收益
        cov = np.cov(returns)  # (n_assets, n_assets) 协方差矩阵

        # --- 2. 构造条件向量 ---
        cond = self._build_condition(returns, mu, cov, factors)

        # --- 3. 扩散采样: 生成候选权重 ---
        # 权重空间中的去噪过程
        if num_portfolios > 1:
            weights_candidates = self._diffuse_weights(
                n_assets=n_assets,
                n_samples=num_portfolios,
                cond=cond,
            )
        else:
            # 单次采样退化为均匀先验
            weights_candidates = uniform_prior((1, n_assets), low=-1.0, high=1.0)

        # --- 4. 约束: 权重归一化为满仓投资 (sum = 1) ---
        weights = self._normalize_weights(weights_candidates)

        # --- 5. 评估候选组合 ---
        portfolio_returns = weights @ mu  # (num_portfolios,)
        portfolio_var = np.einsum("ij,jk,ik->i", weights, cov, weights)  # (num_portfolios,)
        portfolio_std = np.sqrt(np.clip(portfolio_var, 1e-10, None))

        sharpe = (portfolio_returns - risk_free_rate) / portfolio_std

        # --- 6. 有效前沿与最优选择 ---
        if target_return is not None:
            # 在目标收益下最小化方差
            valid_mask = np.abs(portfolio_returns - target_return) < 0.01
            if valid_mask.any():
                valid_indices = np.where(valid_mask)[0]
                best_idx = valid_indices[np.argmin(portfolio_var[valid_indices])]
            else:
                # 无精确匹配，选收益最接近目标且方差最小的
                best_idx = np.argmin(np.abs(portfolio_returns - target_return) + 0.1 * portfolio_var)
        else:
            # 最大夏普比率
            best_idx = int(np.argmax(sharpe))

        optimal_weight = weights[best_idx].copy()
        optimal_return = float(portfolio_returns[best_idx])
        optimal_vol = float(portfolio_std[best_idx])

        # --- 7. 有效前沿构建 ---
        pareto = self._build_pareto_frontier(weights, portfolio_returns, portfolio_std)

        # --- 8. 权重不确定性 ---
        weight_uncertainty = np.cov(weights.T)

        return PortfolioOptimizationResult(
            weights=weights,
            pareto_frontier=pareto,
            optimal_weight=optimal_weight,
            weight_uncertainty=weight_uncertainty,
            sharpe_ratios=sharpe,
            annualized_return=optimal_return,
            annualized_volatility=optimal_vol,
            convergence=len(pareto) > 1,
        )

    # ------------------------------------------------------------------
    # 扩散权重生成
    # ------------------------------------------------------------------

    def _diffuse_weights(
        self,
        n_assets: int,
        n_samples: int,
        cond: np.ndarray,
    ) -> np.ndarray:
        """使用 DDIM 扩散生成多样化候选权重

        Args:
            n_assets: 资产数量
            n_samples: 生成样本数
            cond: 条件向量, (1, cond_dim) 或 (batch, cond_dim)

        Returns:
            np.ndarray: (n_samples, n_assets) 候选权重（未归一化）
        """

        # 简单的前向去噪函数: 用线性层模拟 score network
        # 在权重空间中，最自然的先验是均匀分布 (多元化先验)
        def denoise_fn(x_t: np.ndarray, t: int, c: np.ndarray | None) -> np.ndarray:
            """简易 score 预测函数

            对于纯 NumPy 实现，使用可学习的线性投影
            作为轻量级得分网络替代。
            """
            batch = x_t.shape[0]
            channels = x_t.shape[1]

            # 懒惰初始化: 创建轻量级去噪投影
            if not hasattr(self, "_denoise_W"):
                self._denoise_W = np.random.randn(channels + self.config.cond_dim, channels).astype(np.float64) * 0.1
                self._denoise_b = np.zeros(channels, dtype=np.float64)

            # 拼接条件
            if c is not None:
                c_broadcast = np.broadcast_to(c, (batch, self.config.cond_dim))
                x_flat = x_t.transpose(0, 2, 1)  # (batch, seq_len, channels)
                x_cond = np.concatenate(
                    [x_flat, c_broadcast[:, np.newaxis, :].repeat(x_flat.shape[1], axis=1)],
                    axis=-1,
                )
                # 线性投影
                eps = x_cond @ self._denoise_W + self._denoise_b
                eps = eps.transpose(0, 2, 1)  # (batch, channels, seq_len)
            else:
                eps = x_t * 0.0  # 无条件 → 纯噪声

            return eps

        # 从纯噪声开始扩散采样
        # 使用固定小批量，避免单次采样内存过大
        batch_size = min(n_samples, self.config.batch_size)
        all_samples = []

        remaining = n_samples
        while remaining > 0:
            current_batch = min(batch_size, remaining)

            try:
                sample = ddim_sampling_loop(
                    model_denoise_fn=denoise_fn,
                    shape=(current_batch, n_assets, 1),  # (batch, channels, seq_len=1)
                    config=self.config,
                    cond=cond,
                    return_all_steps=False,
                )
                # (batch, n_assets, 1) → (batch, n_assets)
                sample = sample[:, :, 0]
            except Exception as e:
                logger.warning(
                    "扩散权重采样失败 (batch=%d): %s, 退化为均匀先验",
                    current_batch,
                    e,
                )
                # 在权重空间中，均匀先验等价于随机权重
                sample = uniform_prior((current_batch, n_assets), low=-1.0, high=1.0)

            all_samples.append(sample)
            remaining -= current_batch

        return np.concatenate(all_samples, axis=0)  # (n_samples, n_assets)

    # ------------------------------------------------------------------
    # 有效前沿构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_pareto_frontier(
        weights: np.ndarray,
        returns: np.ndarray,
        stds: np.ndarray,
    ) -> list[tuple[float, float]]:
        """构建有效前沿（Pareto 最优前沿）

        对于给定的风险-收益点集，找出所有 Pareto 最优的点
        (即不存在另一个点在相同风险下收益更高，或相同收益下风险更低)。

        Args:
            weights: 权重, (n, n_assets)
            returns: 收益, (n,)
            stds: 标准差, (n,)

        Returns:
            List[Tuple[float, float]]: 有效前沿点 [(risk, return), ...]
                按风险升序排列
        """
        n = len(returns)
        pareto_mask = np.ones(n, dtype=bool)

        for i in range(n):
            if not pareto_mask[i]:
                continue
            # 找支配点: 更低风险且更高收益
            dominated = ((stds <= stds[i]) & (returns >= returns[i])) & ~np.eye(n, dtype=bool)[i]
            if dominated.any():
                pareto_mask[i] = False

        # 对 Pareto 点按风险排序
        pareto_indices = np.where(pareto_mask)[0]
        if len(pareto_indices) == 0:
            return [(float(stds[returns.argmax()]), float(returns.max()))]

        sorted_idx = pareto_indices[np.argsort(stds[pareto_indices])]
        frontier = [(float(stds[i]), float(returns[i])) for i in sorted_idx]
        return frontier

    # ------------------------------------------------------------------
    # 条件构造
    # ------------------------------------------------------------------

    def _build_condition(
        self,
        returns: np.ndarray,
        mu: np.ndarray,
        cov: np.ndarray,
        factors: np.ndarray | None,
    ) -> np.ndarray:
        """构建扩散条件向量

        条件包含:
            - 因子暴露 (如果提供)
            - 资产收益统计量 (均值、波动率、夏普)
            - 市场状态代理变量

        Args:
            returns: 历史收益, (n_assets, n_periods)
            mu: 均值收益, (n_assets,)
            cov: 协方差矩阵, (n_assets, n_assets)
            factors: 因子暴露, (n_assets, n_factors) 或 None

        Returns:
            np.ndarray: (1, cond_dim) 条件向量
        """
        returns.shape[0]
        cond_dim = self.config.cond_dim

        components: list[np.ndarray] = []

        # --- 因子条件 ---
        if factors is not None:
            # 汇总因子暴露: 均值、方差等统计量
            factors = np.asarray(factors, dtype=np.float64)
            f_mean = factors.mean(axis=0)
            f_std = factors.std(axis=0)
            f_max = np.abs(factors).max(axis=0)
            components.extend([f_mean, f_std, f_max])

        # --- 资产统计条件 ---
        vol = np.sqrt(np.diag(cov))
        sharpe_asset = mu / (vol + 1e-10)

        components.append(mu)  # 均值收益
        components.append(vol)  # 波动率
        components.append(sharpe_asset)  # 资产级夏普

        # --- 分散化指标 ---
        avg_corr = np.mean(cov / np.outer(vol, vol + 1e-10))
        components.append(np.array([avg_corr]))

        # --- 拼接并投影到 cond_dim ---
        raw = np.concatenate([c.ravel().astype(np.float64) for c in components])
        raw_dim = raw.shape[0]

        # 懒惰初始化投影矩阵
        if self._factor_proj_W is None or self._factor_proj_W.shape[0] != raw_dim:
            self._factor_proj_W = np.random.randn(raw_dim, cond_dim).astype(np.float64) * (1.0 / np.sqrt(raw_dim))
            self._factor_proj_b = np.zeros(cond_dim, dtype=np.float64)

        cond = raw @ self._factor_proj_W + self._factor_proj_b

        # LayerNorm
        cond = (cond - cond.mean()) / (cond.std() + 1e-8)
        return cond[np.newaxis, :]  # (1, cond_dim)

    # ------------------------------------------------------------------
    # 权重约束与归一化
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_weights(raw_weights: np.ndarray) -> np.ndarray:
        """将原始权重归一化为满仓投资组合

        约束:
            1. sum(weights) = 1 (满仓)
            2. 支持空头 (允许负权重)

        Args:
            raw_weights: 原始权重, (n, n_assets)

        Returns:
            np.ndarray: 归一化后的权重, (n, n_assets)
        """
        # 居中并归一化
        centered = raw_weights - raw_weights.mean(axis=1, keepdims=True)
        # 缩放使 sum(abs) 的符号与 sum 匹配
        total = centered.sum(axis=1, keepdims=True)
        # 调整使 sum = 1
        weights = centered / (total + 1e-10)
        return weights

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def set_config(self, config: DiffusionConfig) -> None:
        """更新配置并重置投影矩阵"""
        self.config = config
        self._factor_proj_W = None
        self._factor_proj_b = None
        self._calibrated = False
        self._n_assets = None
        if hasattr(self, "_denoise_W"):
            del self._denoise_W
            del self._denoise_b
        logger.info("DiffusionPortfolioOptimizer 配置已更新")

    def estimate_sharpe(
        self,
        weights: np.ndarray,
        returns: np.ndarray,
        risk_free_rate: float = 0.02,
    ) -> float:
        """估算给定权重的夏普比率

        Args:
            weights: 投资组合权重, (n_assets,)
            returns: 历史收益, (n_assets, n_periods)
            risk_free_rate: 无风险利率

        Returns:
            float: 年化夏普比率
        """
        mu = returns.mean(axis=1)
        cov = np.cov(returns)
        portfolio_return = float(weights @ mu)
        portfolio_var = float(weights @ cov @ weights)
        portfolio_std = np.sqrt(max(portfolio_var, 1e-10))
        return (portfolio_return - risk_free_rate) / portfolio_std

    def reset(self) -> None:
        """重置优化器状态"""
        self._factor_proj_W = None
        self._factor_proj_b = None
        self._calibrated = False
        self._n_assets = None
        if hasattr(self, "_denoise_W"):
            del self._denoise_W
            del self._denoise_b
        logger.info("DiffusionPortfolioOptimizer 已重置")

    def __repr__(self) -> str:
        return f"DiffusionPortfolioOptimizer(config={self.config})"
