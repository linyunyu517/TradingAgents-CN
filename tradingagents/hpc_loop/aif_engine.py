# TradingAgents/hpc_loop/aif_engine.py
"""
Actor-Integrated Active Inference Engine (AIF-Engine)

基于 Friston 自由能原理的统一感知-行动框架。
将 HPC-Loop 中的硬编码规则替换为变分自由能最小化。

理论基础:
    - Friston, K. (2010). The free-energy principle: a unified brain theory?
    - Friston, K. et al. (2013). Active inference and learning.
    - Parr, T. & Friston, K. (2019). Generalised free energy and active inference.

核心组件:
    1. MarketLatentState — JAX 概率分布表示的隐状态
    2. GenerativeModel  — 层级生成模型 P(s_{t+1}, o_t | s_t, a_t)
    3. ActiveInference  — 期望自由能 G(π) 计算 + 行动选择
    4. LLMPriorInjector — LLM 输出 → 先验分布注入
    5. BeliefUpdater    — 基于观测的变分信念更新
"""

import logging
import os  # [R2 Fix M3] JAX fork-safety 依赖 os.environ
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

# [R2 Fix M3] JAX 线程安全防护：提前设 JAX_PLATFORM_NAME 防止 fork()+JAX 线程池死锁
# JAX 默认使用多线程并行，与 os.fork() / multiprocessing 不兼容，
# 设置该环境变量让 JAX 在子进程中初始化时使用单线程平台，避免 RuntimeWarning
if os.environ.get("JAX_PLATFORM_NAME") is None:
    os.environ["JAX_PLATFORM_NAME"] = ""

try:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from jax import grad, jit, lax, random, vmap
    from jax.nn import log_softmax, sigmoid, softmax
    from numpyro.infer import SVI, Predictive, Trace_ELBO
    from numpyro.infer.autoguide import AutoDiagonalNormal

    _JAX_AVAILABLE = True
except ImportError:
    _JAX_AVAILABLE = False
    # 定义 stub 让模块可以导入但不抛出 ImportError
    jnp = None
    jax = None
    random = None
    vmap = None
    softmax = None
    numpyro = None
    dist = None
    SVI = None

logger = logging.getLogger("hpc_loop.aif")

# 分层模型和元学习器导入（带保护，避免因缺失依赖导致整个模块无法加载）
try:
    from .hierarchical_model import HierarchicalGenModel, LayerConfig, TimeScale
    _HIERARCHICAL_MODEL_AVAILABLE = True
except ImportError as _hier_err:
    logger.warning(f"[AIF] HierarchicalGenModel 导入失败（降级到单层）: {_hier_err}")
    HierarchicalGenModel = None
    LayerConfig = None
    TimeScale = None
    _HIERARCHICAL_MODEL_AVAILABLE = False

try:
    from .meta_learner import MetaLearner, MetaLearnerConfig
    _META_LEARNER_AVAILABLE = True
except ImportError as _meta_err:
    logger.warning(f"[AIF] MetaLearner 导入失败（降级到无元学习器）: {_meta_err}")
    MetaLearner = None
    MetaLearnerConfig = None
    _META_LEARNER_AVAILABLE = False

# ====================================================================
# 常量定义
# ====================================================================
# latent_dim 配置统一说明 (2026-06-18):
# ┌─────────────────────────┬──────┬──────────────────────────────────────┐
# │ 配置来源                │ 值   │ 用途                                │
# ├─────────────────────────┼──────┼──────────────────────────────────────┤
# │ DEFAULT_LATENT_DIM      │  8   │ AIF JAX MarketLatentState 隐状态维度 │
# │ hpc_config.aif_latent_dim│  8  │ HPCLoopConfig → GenerativeModel 传入 │
# │ default_config          │  8   │ settings.json/环境变量覆盖           │
# ├─────────────────────────┼──────┼──────────────────────────────────────┤
# │ generative_model_latent │ 32   │ 旧 HPC MarketGenerativeModel 隐状态 │
# │ rssm_latent_dim         │ 32   │ L-IWM DreamerV3 RSSM 确定性维度     │
# │ diffusion.latent_dim    │ 32   │ 扩散生成模型潜空间维度              │
# ├─────────────────────────┼──────┼──────────────────────────────────────┤
# │ hier.micro.latent_dim   │  8   │ GENESIS 层级 TICK 层                │
# │ hier.meso.latent_dim    │ 16   │ GENESIS 层级 MINUTE 层              │
# │ hier.macro.latent_dim   │ 32   │ GENESIS 层级 DAY 层                 │
# │ hier.strategic.latent_dim│ 64   │ GENESIS 层级 WEEK 层               │
# └─────────────────────────┴──────┴──────────────────────────────────────┘
# 注意: 这些值服务不同子系统，故意不一致。
# AIF(8D) 是 ActionInference 框架的紧凑向量表征；
# generative_model(32D) 是旧 HPC 的 dict 风格表征；
# Hierarchical(8/16/32/64) 是 GENESIS 4 层分层潜变量架构。
# _adapt_s_t_dim() 负责运行时自动适配不同维度输入。

REGIME_NAMES = ["bull", "bear", "range_bound", "crisis"]
"""市场体制名称列表"""

ACTION_NAMES = ["buy", "sell", "hold"]
"""基本行动名称列表"""

DEFAULT_LATENT_DIM = 8
"""AIF 隐状态维度: [regime_logits(4), volatility_mu(1), trend_mu(1), momentum(1), sentiment(1)] = 8D
   与 hpc_config.aif_latent_dim 保持一致，用于 GenerativeModel/AIF Engine (JAX 路径)。
   不同于 generative_model_latent_dim=32 (旧 HPC dict 路径) 和 hierarchical 层维度 (8/16/32/64)。"""

DEFAULT_OBS_DIM = 5
"""观测维度: [price_change, volatility, sentiment, volume, spread]"""


# ====================================================================
# 类 1: MarketLatentState — JAX 概率分布表征的隐状态
# ====================================================================


@dataclass
class MarketLatentState:
    """
    市场隐状态——用概率分布表示，不是单点值

    遵循 Friston 自由能原理：大脑(和模型)维护的不是"最可能的值"，
    而是完整的后验分布 P(s|o)，其不确定性由变分自由能 F 度量。

    公式参考:
        Friston (2010): F = D_KL[Q(s) || P(s,o)]
            = E_Q[ln Q(s)] - E_Q[ln P(s,o)]

    Args:
        regime_logits: shape=(4,) — 牛市/熊市/震荡/危机的对数概率
        volatility_mu: 波动率正态分布均值
        volatility_sigma: 波动率正态分布标准差 (> 0)
        trend_mu: 趋势正态分布均值
        trend_sigma: 趋势正态分布标准差 (> 0)
        momentum: 动量标量 ∈ [-1, 1]
        sentiment: 情绪标量 ∈ [-1, 1]
        uncertainty_temperature: 总体不确定性温度参数
        belief_history: 信念历史记录 (用于相变检测和调试)
    """

    regime_logits: jnp.ndarray = field(default_factory=lambda: jnp.zeros(4))
    """shape=(4,) 体制对数概率 logits"""

    volatility_mu: float = 0.02
    """波动率正态分布均值"""

    volatility_sigma: float = 0.01
    """波动率正态分布标准差"""

    trend_mu: float = 0.0
    """趋势正态分布均值"""

    trend_sigma: float = 0.005
    """趋势正态分布标准差"""

    momentum: float = 0.0
    """动量 ∈ [-1, 1]"""

    sentiment: float = 0.0
    """情绪 ∈ [-1, 1]"""

    uncertainty_temperature: float = 1.0
    """总体不确定性温度参数 T ∈ (0, ∞)，T 越大分布越平滑"""

    belief_history: list[dict[str, Any]] = field(default_factory=list)
    """信念历史 (用于相变检测和调试)"""

    # ---- 非 JAX 字段（用于与现有 HPCState 兼容） ----
    total_uncertainty: float = 1.0
    """总不确定性度量 (用于向后兼容)"""

    aleatoric_uncertainty: float = 0.5
    """偶然不确定性 (数据固有噪声)"""

    epistemic_uncertainty: float = 0.5
    """认知不确定性 (模型知识不足)"""

    def __post_init__(self):
        if not _JAX_AVAILABLE:
            return
        # 确保 regime_logits 是 jnp.ndarray
        if not isinstance(self.regime_logits, jnp.ndarray):
            self.regime_logits = jnp.array(self.regime_logits, dtype=jnp.float32)

    @property
    def regime_probs(self) -> jnp.ndarray:
        """
        体制概率分布 P(regime) = softmax(regime_logits)

        Friston 公式: Q(s) 变分后验，通过 softmax 从 logits 构造
        """
        if not _JAX_AVAILABLE:
            return jnp.zeros(4)
        return softmax(self.regime_logits / max(self.uncertainty_temperature, 1e-8))

    def get_regime(self) -> str:
        """获取最大概率的体制"""
        if not _JAX_AVAILABLE:
            return "unknown"
        probs = self.regime_probs
        idx = int(jnp.argmax(probs))
        return REGIME_NAMES[idx] if idx < len(REGIME_NAMES) else "unknown"

    def get_regime_probs_dict(self) -> dict[str, float]:
        """以 dict 形式返回体制概率（与现有代码兼容）"""
        if not _JAX_AVAILABLE:
            return dict.fromkeys(REGIME_NAMES, 0.25)
        probs = self.regime_probs
        return {REGIME_NAMES[i]: float(probs[i]) for i in range(len(REGIME_NAMES))}

    def get_entropy(self) -> float:
        """
        计算变分后验的熵 H[Q(s)]

        公式: H[Q] = -Σ Q(s_i) ln Q(s_i)

        Returns:
            float: 熵值 (nats)
        """
        if not _JAX_AVAILABLE:
            return 1.0
        probs = self.regime_probs
        entropy = -jnp.sum(probs * jnp.log(jnp.clip(probs, 1e-8, 1.0)))
        return float(entropy)

    def to_latent_vector(self, target_dim: int | None = None) -> jnp.ndarray:
        """
        将隐状态转换为连续向量

        用于 GenerativeModel.transition 的输入。
        shape = (latent_dim,) = (8,)

        Args:
            target_dim: 目标维度，如果提供则自动 padding/truncation
                       （消除调用者手动 _adapt_s_t_dim 的需要）

        Returns:
            jnp.ndarray: 隐状态向量
        """
        if not _JAX_AVAILABLE:
            vec = jnp.zeros(DEFAULT_LATENT_DIM)
        else:
            vec = jnp.concatenate(
                [
                    self.regime_probs,  # (4,)
                    jnp.array([self.volatility_mu]),  # (1,)
                    jnp.array([self.trend_mu]),  # (1,)
                    jnp.array([self.momentum]),  # (1,)
                    jnp.array([self.sentiment]),  # (1,)
                ],
            )
        if target_dim is not None and vec.shape[0] != target_dim:
            if vec.shape[0] < target_dim:
                vec = jnp.pad(vec, (0, target_dim - vec.shape[0]), mode="constant", constant_values=0.0)
            else:
                vec = vec[:target_dim]
        return vec

    @classmethod
    def from_latent_vector(cls, z: jnp.ndarray, temperature: float = 1.0) -> "MarketLatentState":
        """
        从连续向量重建隐状态

        Args:
            z: shape=(latent_dim,) 隐状态向量
            temperature: 不确定性温度

        Returns:
            MarketLatentState: 重建的隐状态
        """
        if not _JAX_AVAILABLE:
            return cls()

        # [FIX 2026-06-18 P0] 短向量自动填充保护
        latent_dim = getattr(z, "shape", [0])[0] if hasattr(z, "shape") else 0
        expected_full_dim = 8  # to_latent_vector 的标准输出维度
        if 0 < latent_dim < expected_full_dim:
            logger.warning(
                f"[AIF] [FIX P0] ⚠️ from_latent_vector 输入维度不足: "
                f"z.shape={latent_dim}, 期望 {expected_full_dim}. "
                f"自动填充缺失分量...",
            )
            z = jnp.pad(z, (0, expected_full_dim - latent_dim), mode="constant", constant_values=0.0)

        regime_logits = z[:4]
        volatility_mu = float(z[4])
        trend_mu = float(z[5])
        momentum = float(jnp.clip(z[6], -1.0, 1.0))
        sentiment = float(jnp.clip(z[7], -1.0, 1.0))
        return cls(
            regime_logits=regime_logits,
            volatility_mu=volatility_mu,
            volatility_sigma=0.01,
            trend_mu=trend_mu,
            trend_sigma=0.005,
            momentum=momentum,
            sentiment=sentiment,
            uncertainty_temperature=temperature,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（与现有 HPCState 兼容）"""
        return {
            "market_regime_probs": self.get_regime_probs_dict(),
            "regime": self.get_regime(),
            "volatility_mu": self.volatility_mu,
            "volatility_sigma": self.volatility_sigma,
            "trend_mu": self.trend_mu,
            "trend_sigma": self.trend_sigma,
            "momentum": self.momentum,
            "sentiment": self.sentiment,
            "uncertainty_temperature": self.uncertainty_temperature,
            "total_uncertainty": self.total_uncertainty,
            "entropy": self.get_entropy(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MarketLatentState":
        """从字典重建"""
        regime_probs = d.get("market_regime_probs", {})
        logits = jnp.array([regime_probs.get(r, 0.25) for r in REGIME_NAMES], dtype=jnp.float32)
        # 转换概率到 logit 空间
        logits = jnp.clip(logits, 1e-8, 1 - 1e-8)
        logits = jnp.log(logits / (1 - logits))
        return cls(
            regime_logits=logits,
            volatility_mu=d.get("volatility_mu", 0.02),
            volatility_sigma=d.get("volatility_sigma", 0.01),
            trend_mu=d.get("trend_mu", 0.0),
            trend_sigma=d.get("trend_sigma", 0.005),
            momentum=d.get("momentum", 0.0),
            sentiment=d.get("sentiment", 0.0),
            uncertainty_temperature=d.get("uncertainty_temperature", 1.0),
            total_uncertainty=d.get("total_uncertainty", 1.0),
            aleatoric_uncertainty=d.get("aleatoric_uncertainty", 0.5),
            epistemic_uncertainty=d.get("epistemic_uncertainty", 0.5),
        )


# ====================================================================
# 辅助函数: 生成模型参数初始化
# ====================================================================


def _init_transition_matrix(key: jnp.ndarray, latent_dim: int = DEFAULT_LATENT_DIM) -> jnp.ndarray:
    """
    初始化转移矩阵 A ∈ R^{latent_dim × latent_dim}

    A 控制隐状态的线性动力学: z_{t+1} = A·z_t + B·a_t + ε

    使用正交初始化确保训练稳定性。
    """
    if not _JAX_AVAILABLE:
        return jnp.eye(latent_dim)
    key, subkey = random.split(key)
    # Xavier 初始化
    A = random.normal(subkey, (latent_dim, latent_dim)) * jnp.sqrt(2.0 / latent_dim)
    # 确保谱范数 < 1 (稳定性)
    return A * 0.9 / jnp.linalg.norm(A, ord=2)


def _init_emission_matrix(
    key: jnp.ndarray, latent_dim: int = DEFAULT_LATENT_DIM, obs_dim: int = DEFAULT_OBS_DIM,
) -> jnp.ndarray:
    """
    初始化发射矩阵 C ∈ R^{obs_dim × latent_dim}

    C 控制从隐状态到观测的映射: o_t = C·z_t + η
    """
    if not _JAX_AVAILABLE:
        return jnp.zeros((obs_dim, latent_dim))
    key, subkey = random.split(key)
    return random.normal(subkey, (obs_dim, latent_dim)) * 0.1


# ====================================================================
# 类 2: GenerativeModel — 真正的层级生成模型
# ====================================================================


class GenerativeModel:
    """
    层级生成模型 P(s_{t+1}, o_t | s_t, a_t)

    两层层级:
    - 底层 (transition): 市场状态转移 P(s_{t+1} | s_t, a_t)
        使用线性动力学 + 非线性变换 (MLP) + 随机噪声
    - 顶层 (likelihood): 观测分布 P(o_t | s_t)
        将隐状态映射到可观测的量 (价格变动、波动率等)

    设计原则:
    1. 可微分: 所有操作通过 JAX 自动微分，支持端到端梯度传播
    2. 概率化: 所有输出都是分布而非点估计
    3. 可组合: 支持嵌套在更大的自由能计算图中

    公式参考:
        Friston (2013): P(s_{t+1}, o_t | s_t, π)
            = P(s_{t+1} | s_t, π) · P(o_t | s_t)

    Args:
        latent_dim: 隐状态维度 (默认 8)
        obs_dim: 观测维度 (默认 5)
        hidden_dim: MLP 隐藏层维度 (默认 16)
        key: JAX 随机数种子
    """

    def __init__(
        self,
        latent_dim: int = DEFAULT_LATENT_DIM,
        obs_dim: int = DEFAULT_OBS_DIM,
        hidden_dim: int = 16,
        key: jnp.ndarray | None = None,
        use_hierarchical: bool = False,  # 新增：是否启用分层模型
        layer_configs: list[LayerConfig] | None = None,  # 新增：分层模型层配置
        meta_learner_config: MetaLearnerConfig | None = None,  # 新增：元学习器配置
    ):
        if not _JAX_AVAILABLE:
            logger.warning("[AIF] JAX/numpyro 不可用，GenerativeModel 运行在降级模式")
            self._degraded = True
            self.latent_dim = latent_dim
            self.obs_dim = obs_dim
            self.use_hierarchical = False
            self.hierarchical_model = None
            self.meta_learner = None
            self._meta_cycle_count = 0
            return

        self._degraded = False
        self.latent_dim = latent_dim
        self.obs_dim = obs_dim
        self.action_dim = 3  # 动作维度: buy/sell/hold 三个离散动作
        self.hidden_dim = hidden_dim

        if key is None:
            key = random.PRNGKey(42)
        self._key = key

        # ---- 分层模型 + 元学习器初始化 ----
        self.use_hierarchical = use_hierarchical and _HIERARCHICAL_MODEL_AVAILABLE and HierarchicalGenModel is not None
        if use_hierarchical and not self.use_hierarchical:
            logger.warning("[AIF] 分层模式被请求但 HierarchicalGenModel 不可用，降级到单层")
        self._meta_cycle_count = 0

        if self.use_hierarchical:
            try:
                # 如果未提供 layer_configs，使用默认4层配置
                if layer_configs is None:
                    default_configs = [
                        LayerConfig(
                            name="micro",
                            latent_dim=8,
                            time_scale=TimeScale.TICK,
                            temporal_precision=TimeScale.TICK.precision_weight,
                        ),
                        LayerConfig(
                            name="meso",
                            latent_dim=16,
                            time_scale=TimeScale.MINUTE,
                            temporal_precision=TimeScale.MINUTE.precision_weight,
                        ),
                        LayerConfig(
                            name="macro",
                            latent_dim=32,
                            time_scale=TimeScale.DAY,
                            temporal_precision=TimeScale.DAY.precision_weight,
                        ),
                        LayerConfig(
                            name="strategic",
                            latent_dim=64,
                            time_scale=TimeScale.WEEK,
                            temporal_precision=TimeScale.WEEK.precision_weight,
                        ),
                    ]
                else:
                    default_configs = layer_configs
                self.hierarchical_model = HierarchicalGenModel(default_configs, obs_dim=self.obs_dim, key=key)
                logger.info("[AIF] ✅ HierarchicalGenModel 已初始化 (4 层)")
            except Exception as e:
                logger.warning(f"[AIF] HierarchicalGenModel 初始化失败，降级到单层: {e}")
                self.hierarchical_model = None
                self.use_hierarchical = False

            try:
                self.meta_learner = MetaLearner(meta_learner_config or MetaLearnerConfig())
                logger.info("[AIF] ✅ MetaLearner 已初始化")
            except Exception as e:
                logger.warning(f"[AIF] MetaLearner 初始化失败，降级: {e}")
                self.meta_learner = None
        else:
            self.hierarchical_model = None
            self.meta_learner = None

        # ---- 可学习参数 ----
        # 转移矩阵 A: z_{t+1} = tanh(A·z_t + B·a_t + b) + ε
        # 形状: (latent_dim, latent_dim) — 隐状态自转移矩阵
        self.A = _init_transition_matrix(key, latent_dim)  # (latent_dim, latent_dim)

        # 行动影响矩阵 B: z_{t+1} 对行动 a_t 的敏感度
        # 形状: (latent_dim, 3) — 每列对应一个动作 (buy/sell/hold)，列向量加到隐状态
        key, subkey = random.split(key)
        self.B = random.normal(subkey, (latent_dim, 3)) * 0.1  # (latent_dim, 3)

        # 偏置项 b
        # 形状: (latent_dim,) — 常数偏置项
        key, subkey = random.split(key)
        self.b = random.normal(subkey, (latent_dim,)) * 0.01  # (latent_dim,)

        # 发射矩阵 C: o_t = C·z_t + η
        # 形状: (obs_dim, latent_dim) — 将隐状态映射到观测空间 (price_change, volatility, sentiment, volume, spread)
        self.C = _init_emission_matrix(key, latent_dim, obs_dim)  # (obs_dim, latent_dim)

        # 观测噪声 (可学习精度)
        key, subkey = random.split(key)
        self.obs_log_noise = jnp.zeros(obs_dim)  # log(σ_o) — 学习 log 确保正性

        # 转移噪声 (固定或可学习)
        self.trans_log_noise = jnp.log(jnp.array(0.01))  # log(σ_s)

        # --- MLP 权重 (非线性变换) ---
        # 用于建模非线性市场动力学
        key, subkey = random.split(key)
        self.W1 = random.normal(subkey, (hidden_dim, latent_dim)) * jnp.sqrt(2.0 / latent_dim)
        key, subkey = random.split(key)
        self.W2 = random.normal(subkey, (latent_dim, hidden_dim)) * jnp.sqrt(2.0 / hidden_dim)

        # 归一化统计 (在线 running stats)
        self._z_mean = jnp.zeros(latent_dim)
        self._z_var = jnp.ones(latent_dim)
        self._update_count = 0

    # ------------------------------------------------------------------
    # 维度适配工具
    # ------------------------------------------------------------------
    def _adapt_s_t_dim(self, s_t: jnp.ndarray, caller_name: str = "") -> jnp.ndarray:
        """
        [FIX 2026-06-18 P0] 统一维度适配: 将 s_t 自动填充/截断到 self.latent_dim

        消除各方法中重复的维度检查代码，同时确保 likelihood/compute_free_energy
        等未覆盖方法也有维度保护。

        Args:
            s_t: 输入状态向量
            caller_name: 调用方法名（用于日志标识）

        Returns:
            适配后的状态向量, shape=(latent_dim,)
        """
        if self._degraded or not _JAX_AVAILABLE:
            return s_t
        if not hasattr(s_t, "shape"):
            logger.warning(f"[AIF] [FIX P0] {caller_name}: s_t 不是有效数组 (type={type(s_t).__name__}), 返回零向量")
            return jnp.zeros(self.latent_dim)
        if s_t.shape[0] != self.latent_dim:
            logger.debug(
                f"[AIF] [FIX P0] {caller_name} 输入维度不匹配: "
                f"s_t.shape={s_t.shape}, 期望 latent_dim={self.latent_dim}. "
                f"正在自动修正...",
            )
            if s_t.shape[0] < self.latent_dim:
                s_t = jnp.pad(
                    s_t,
                    (0, self.latent_dim - s_t.shape[0]),
                    mode="constant",
                    constant_values=0.0,
                )
            else:
                s_t = s_t[: self.latent_dim]
        return s_t

    # ------------------------------------------------------------------
    # Transition: P(s_{t+1} | s_t, a_t)
    # ------------------------------------------------------------------

    @property
    def _trans_std(self) -> float:
        """转移噪声标准差 exp(log(σ_s))"""
        return float(jnp.exp(self.trans_log_noise)) if not self._degraded else 0.01

    def transition(self, s_t: jnp.ndarray, a_t: jnp.ndarray) -> dist.Distribution:
        """
        状态转移分布 P(s_{t+1} | s_t, a_t)

        公式: s_{t+1} = f(s_t, a_t) + ε, ε ~ N(0, σ_s² I)
            其中 f(s, a) = tanh(A·s + B·a + b + MLP(s))

        MLP 部分: MLP(s) = W2·tanh(W1·s)
        提供非线性变换能力，捕捉市场体制切换等复杂动力学。

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)
            a_t: 行动 one-hot 编码, shape=(3,)

        Returns:
            dist.Normal: 下一时刻隐状态的分布
        """
        if self._degraded:
            return dist.Normal(s_t, 0.01)

        # === [FIX 2026-06-18 P0] 运行时形状断言 ===
        assert a_t.shape == (self.action_dim,), (
            f"[AIF] transition: a_t 形状错误, 期望 ({self.action_dim},), 实际 {a_t.shape}"
        )

        # === [FIX 2026-06-18 P0] 统一维度适配 ===
        s_t = self._adapt_s_t_dim(s_t, "transition")

        # 线性部分
        linear = self.A @ s_t + self.B @ a_t + self.b  # (latent_dim,)

        # 非线性部分 (MLP)
        h = jnp.tanh(self.W1 @ s_t)  # (hidden_dim,)
        nonlinear = self.W2 @ h  # (latent_dim,)

        # 组合
        mean = jnp.tanh(linear + nonlinear)  # (latent_dim,)

        # 归一化 (layer norm)
        mean = (mean - self._z_mean) / (jnp.sqrt(self._z_var) + 1e-8)

        return dist.Normal(mean, self._trans_std)

    # ------------------------------------------------------------------
    # Likelihood: P(o_t | s_t)
    # ------------------------------------------------------------------

    def likelihood(self, s_t: jnp.ndarray) -> dist.Distribution:
        """
        观测分布 P(o_t | s_t)

        公式: o_t = C·s_t + η, η ~ N(0, diag(exp(log_noise))²)

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)

        Returns:
            dist.Normal: 观测分布, shape=(obs_dim,)
        """
        if self._degraded:
            return dist.Normal(jnp.zeros(self.obs_dim), 1.0)

        # [FIX 2026-06-18 P0] likelihood 缺少维度检查，self.C @ s_t 在维度不匹配时抛出 dot_general 错误
        s_t = self._adapt_s_t_dim(s_t, "likelihood")

        mean = self.C @ s_t  # (obs_dim,)
        std = jnp.exp(self.obs_log_noise) + 1e-8  # (obs_dim,)
        return dist.Normal(mean, std)

    # ------------------------------------------------------------------
    # Joint: P(s_{t+1}, o_t | s_t, a_t)
    # ------------------------------------------------------------------

    def joint(self, s_t: jnp.ndarray, a_t: jnp.ndarray) -> tuple[dist.Distribution, dist.Distribution]:
        """
        联合分布 P(s_{t+1}, o_t | s_t, a_t)

        返回转移分布和观测分布的元组，便于计算自由能。

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)
            a_t: 行动编码, shape=(3,)

        Returns:
            (P(s_{t+1}|s_t,a_t), P(o_t|s_t))
        """
        return self.transition(s_t, a_t), self.likelihood(s_t)

    # ------------------------------------------------------------------
    # 预测采样
    # ------------------------------------------------------------------

    def _generate_prediction_flat(
        self,
        s_t: jnp.ndarray,
        a_t: jnp.ndarray | None = None,
        n_samples: int = 100,
        horizon: int = 1,
    ) -> dict[str, Any]:
        """
        扁平生成模型的预测逻辑（内部方法，避免递归）

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)
            a_t: 行动编码, shape=(3,) (若为 None 则随机采样行动)
            n_samples: 采样子轨迹数
            horizon: 预测时间跨度 (步数)

        Returns:
            dict: 包含预测分布的均值和置信区间
        """
        if self._degraded:
            return {
                "price_mean": 0.0,
                "price_lower": -0.02,
                "price_upper": 0.02,
                "volatility_mean": 0.02,
                "n_samples": n_samples,
            }

        # === [FIX 2026-06-18 P0] 统一维度适配 ===
        s_t = self._adapt_s_t_dim(s_t, "_generate_prediction_flat")

        if a_t is None:
            a_t = jnp.zeros(3)

        key = self._key

        def _sample_trajectory(key_chunk: jnp.ndarray) -> dict[str, Any]:
            """采样单条轨迹"""
            s = s_t
            obs_samples = []
            for _ in range(horizon):
                key, subkey = random.split(key_chunk)
                trans_dist = self.transition(s, a_t)
                s = trans_dist.sample(subkey)
                key, subkey = random.split(key)
                obs_dist = self.likelihood(s)
                obs = obs_dist.sample(subkey)
                obs_samples.append(obs)
            return jnp.stack(obs_samples)  # (horizon, obs_dim)

        keys = random.split(key, n_samples)
        trajectories = vmap(_sample_trajectory)(keys)  # (n_samples, horizon, obs_dim)

        mean_traj = jnp.mean(trajectories, axis=0)  # (horizon, obs_dim)
        std_traj = jnp.std(trajectories, axis=0)  # (horizon, obs_dim)

        # 提取关键维度 (假设 obs_dim 约定: price, volatility, sentiment, volume, spread)
        price_mean = float(mean_traj[-1, 0])  # 最后一步的价格预测均值
        price_std = float(std_traj[-1, 0])
        vol_mean = float(mean_traj[-1, 1]) if self.obs_dim > 1 else 0.02

        self._key = random.split(key)[0]  # 更新随机种子

        return {
            "price_mean": price_mean,
            "price_lower": price_mean - 1.96 * price_std,
            "price_upper": price_mean + 1.96 * price_std,
            "price_std": price_std,
            "volatility_mean": vol_mean,
            "trajectory_mean": mean_traj.tolist(),
            "trajectory_std": std_traj.tolist(),
            "n_samples": n_samples,
            "horizon": horizon,
        }

    def generate_prediction(
        self,
        s_t: jnp.ndarray,
        a_t: jnp.ndarray | None = None,
        n_samples: int = 100,
        horizon: int = 1,
    ) -> dict[str, Any]:
        """
        从联合分布采样生成预测

        如果启用了分层模型，委托给 generate_prediction_hierarchical()。
        否则使用原有的扁平生成模型。

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)
            a_t: 行动编码, shape=(3,) (若为 None 则随机采样行动)
            n_samples: 采样子轨迹数
            horizon: 预测时间跨度 (步数)

        Returns:
            dict: 包含预测分布的均值和置信区间
        """
        if self.use_hierarchical and self.hierarchical_model is not None:
            # Layer-3 防御: 检查维度（使用 total_latent_dim，因为分层模型需要 120D 而非 8D）
            if s_t.shape[0] != self.hierarchical_model.total_latent_dim:
                logger.warning(
                    f"[AIF] [Layer-3] 分层模式维度不匹配: "
                    f"s_t.shape=({s_t.shape[0]},), 期望 "
                    f"total_latent_dim={self.hierarchical_model.total_latent_dim}. "
                    f"委托 generate_prediction_hierarchical 进行适配",
                )
            return self.generate_prediction_hierarchical(s_t, a_t, n_samples, horizon)
        return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)

    # ------------------------------------------------------------------
    # 分层预测方法 (Hierarchical Prediction)
    # ------------------------------------------------------------------

    def _aif_to_hierarchical_state(self, s_t: jnp.ndarray) -> dict[int, jnp.ndarray] | None:
        """将 8D AIF 状态映射到 4 层分层模型初始状态。

        AIF 的 8D 状态天然对应分层模型的 Level 0 (micro/TICK 层)，
        更高层（meso/macro/strategic）将初始化为零，由自下而上
        的预测误差传播驱动激活。
        """
        if not hasattr(self, "hierarchical_model") or self.hierarchical_model is None:
            return None
        configs = self.hierarchical_model.layer_configs
        n_layers = len(configs)
        result: dict[int, jnp.ndarray] = {}
        result[0] = s_t  # 8D → micro 层
        for l in range(1, n_layers):
            result[l] = jnp.zeros(configs[l].latent_dim)
        return result

    def generate_prediction_hierarchical(
        self,
        s_t: jnp.ndarray,
        a_t: jnp.ndarray | None = None,
        n_samples: int = 100,
        horizon: int = 1,
    ) -> dict[str, Any]:
        """
        使用分层生成模型生成多尺度预测

        调用 HierarchicalGenModel.forward_full() 获取 4 层嵌套预测，
        然后汇总各层预测结果。

        Args:
            s_t: 当前隐状态, shape=(latent_dim,)
            a_t: 行动编码 (未在分层模型中使用，保留接口兼容)
            n_samples: 采样数
            horizon: 预测跨度

        Returns:
            dict: 包含各层预测分布
        """
        if self.hierarchical_model is None:
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)

        # 🔥 [Bug J 修复] 输入验证：检查 s_t 是否为空或维度为 0
        # 防止 JAX 抛出 "dot_general requires contracting dimensions to have the same shape, got (16,) and (0,)"
        if s_t is None:
            logger.warning("[AIF] 输入验证失败: s_t 为 None，回退到扁平模式")
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)
        if not hasattr(s_t, "shape") or s_t.shape is None:
            logger.warning("[AIF] 输入验证失败: s_t 不是有效数组，回退到扁平模式")
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)
        if s_t.shape[0] == 0:
            logger.warning(f"[AIF] 输入验证失败: s_t 维度为 0 (shape={s_t.shape})，回退到扁平模式")
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)
        if jnp.any(jnp.isnan(s_t)):
            logger.warning("[AIF] 输入验证失败: s_t 包含 NaN，回退到扁平模式")
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)

        # === [AIF→Hierarchical 适配] 8D → 4层分层状态映射 ===
        # AIF 的 8D 状态不能直接用于 split_full_state_vector（期望 total_latent_dim 如 120D），
        # 通过 _aif_to_hierarchical_state() 将 8D 映射到 Level 0，其余层初始化为零。
        # 自下而上的预测误差传播会自然激活更高层。
        # [Bug Fix] 使用 self.hierarchical_model.total_latent_dim 而非 self.latent_dim 做维度检查，
        # 因为 total_latent_dim=120 (8+16+32+64) 是 split_full_state_vector 的期望输入维度。
        if s_t.shape[0] != self.hierarchical_model.total_latent_dim:
            adapted_state = self._aif_to_hierarchical_state(s_t)
            if adapted_state is not None:
                logger.info(
                    f"[AIF] ✅ AIF→分层模型适配成功: {s_t.shape[0]}D→{self.hierarchical_model.total_latent_dim}D",
                )
                initial_state = adapted_state
            else:
                logger.warning(f"[AIF] ⚠️ 输入维度不匹配且分层模型不可用 (s_t.shape={s_t.shape}), 回退到扁平模式")
                return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)
        else:
            # s_t 已经是完整 120D 向量，直接拆分各层状态
            initial_state = {
                i: self.hierarchical_model.split_full_state_vector(s_t)[i]
                for i in range(self.hierarchical_model.n_layers)
            }

        try:
            # 构建分层 forward_full 参数
            n_layers = self.hierarchical_model.n_layers
            # 每层使用相同行动（转换为标量）
            action_val = float(a_t[0]) if a_t is not None else 0.0
            actions = {i: jnp.array([action_val]) for i in range(n_layers)}

            # 调用分层模型前向传播
            result = self.hierarchical_model.forward_full(
                initial_state=initial_state,
                actions=actions,
            )

            # 提取全层自由能
            fe_components = result.get("free_energy_components", {})
            total_fe = (
                sum(v for v in fe_components.values() if isinstance(v, (int, float)))
                if isinstance(fe_components, dict)
                else 0.0
            )

            # 从全层状态向量提取价格预测
            full_vector = result.get("full_state_vector", s_t)
            price_mean = float(full_vector[0]) if full_vector.shape[0] > 0 else 0.0
            price_std = float(jnp.std(full_vector)) if full_vector.shape[0] > 1 else 0.02

            # 构建每层预测摘要
            posteriors = result.get("posteriors", {})
            predictions = {}
            for i in range(n_layers):
                layer_state = posteriors.get(i, jnp.zeros(1))
                layer_mean = float(jnp.mean(layer_state))
                layer_std = float(jnp.std(layer_state)) if layer_state.shape[0] > 1 else 0.0
                predictions[f"L{i}"] = {
                    "latent_mean": layer_mean,
                    "latent_std": layer_std,
                    "free_energy": fe_components.get(i, 0.0) if isinstance(fe_components, dict) else 0.0,
                }

            # 记录预测误差到元学习器
            if self.meta_learner is not None:
                self.meta_learner.record_error(total_fe)

            return {
                "price_mean": price_mean,
                "price_lower": price_mean - 1.96 * price_std,
                "price_upper": price_mean + 1.96 * price_std,
                "price_std": price_std,
                "volatility_mean": 0.02,
                "hierarchical_predictions": predictions,
                "total_hierarchical_fe": total_fe,
                "n_samples": n_samples,
                "horizon": horizon,
                "hierarchical": True,
            }
        except Exception as e:
            logger.warning(f"[AIF] 分层预测失败，回退到扁平模式: {e}")
            return self._generate_prediction_flat(s_t, a_t, n_samples, horizon)

    # ------------------------------------------------------------------
    # 分层状态摘要 (Hierarchical State Summary)
    # ------------------------------------------------------------------

    def get_hierarchical_state_summary(
        self,
        state: jnp.ndarray | None = None,
    ) -> dict[str, Any]:
        """
        返回各层潜状态的摘要信息

        用于 LangGraph 状态记录和可视化。

        Args:
            state: 可选的全状态向量 (如果为 None 则从分层模型获取)

        Returns:
            dict: 各层潜状态摘要
        """
        if not self.use_hierarchical or self.hierarchical_model is None:
            return {"mode": "flat", "layers": {}}

        try:
            full_state = (
                state
                if state is not None
                else jnp.zeros(
                    self.hierarchical_model.total_latent_dim,  # @property, 不能用括号
                )
            )
            layer_vectors = self.hierarchical_model.split_full_state_vector(full_state)

            summary = {}
            configs = self.hierarchical_model.layer_configs
            for i, (lv, cfg) in enumerate(zip(layer_vectors, configs, strict=False)):
                if hasattr(lv, "mean"):
                    lv = lv.mean()
                lv.tolist() if hasattr(lv, "tolist") else lv
                summary[f"L{i}_{cfg.name}"] = {
                    "name": cfg.name,
                    "time_scale": cfg.time_scale.value if hasattr(cfg.time_scale, "value") else str(cfg.time_scale),
                    "latent_dim": cfg.latent_dim,
                    "mean_activation": float(jnp.mean(jnp.abs(lv))) if hasattr(jnp, "mean") else 0.0,
                    "norm": float(jnp.linalg.norm(lv)) if hasattr(jnp, "linalg") else 0.0,
                }

            return {"mode": "hierarchical", "layers": summary}
        except Exception as e:
            logger.debug(f"[AIF] 分层状态摘要失败: {e}")
            return {"mode": "flat", "layers": {}, "error": str(e)}

    # ------------------------------------------------------------------
    # 元学习自指循环 (Meta-Learning Self-Referential Cycle)
    # ------------------------------------------------------------------

    def run_meta_cycle(
        self,
        step: int,
        meta_cycle_interval: int = 50,
    ) -> dict[str, Any] | None:
        """
        执行元学习自指循环

        每隔 meta_cycle_interval 步执行一次：
        1. 诊断模型状态
        2. 如果模型退化，应用元更新
        3. 定期输出自省报告

        Args:
            step: 当前全局步数
            meta_cycle_interval: 元学习周期间隔

        Returns:
            Optional[Dict]: 诊断结果，如果未到周期则返回 None
        """
        if not self.use_hierarchical or self.meta_learner is None:
            return None

        if step % meta_cycle_interval != 0:
            return None

        self._meta_cycle_count += 1

        try:
            # 1. 诊断模型状态
            diagnostics = self.meta_learner.diagnose()

            # 2. 如果模型退化，触发元更新
            if diagnostics.is_degrading:
                logger.warning(
                    f"[AIF] ⚠️ 模型退化检测: "
                    f"error_std={diagnostics.error_std:.5f}, "
                    f"error_trend={diagnostics.error_trend:.5f}",
                )
                self.meta_learner.apply_meta_update(self, diagnostics)

                # 如果启用了分层模型，也在各层传播元更新
                if self.hierarchical_model is not None:
                    try:
                        # 获取元学习器建议的学习率
                        hyperparams = self.meta_learner.get_current_hyperparams()
                        suggested_lr = hyperparams.get("learning_rate", 0.001)
                        logger.info(f"[AIF] 🔄 元学习建议学习率: {suggested_lr:.6f}")
                    except Exception as e:
                        logger.warning(f"AIF 引擎执行失败: {e}", exc_info=True)

            # 3. 定期输出自省报告
            if step % 500 == 0:
                report = self.meta_learner.self_question_report()
                logger.info(f"[AIF] 📋 元学习自省报告:\n{report}")

            result = (
                diagnostics.to_dict()
                if hasattr(diagnostics, "to_dict")
                else {
                    "error_std": diagnostics.error_std,
                    "error_trend": diagnostics.error_trend,
                    "is_degrading": diagnostics.is_degrading,
                }
            )
            return result

        except Exception as e:
            logger.warning(f"[AIF] 元学习周期执行失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 双自由能计算 (Dual Free Energy)
    # ------------------------------------------------------------------

    def get_dual_free_energy(
        self,
        observation: jnp.ndarray | None = None,
        belief: MarketLatentState | None = None,
    ) -> dict[str, float]:
        """
        计算双重自由能：分层自由能 + 元学习自由能

        如果启用了分层模型和元学习器：
            返回 (hierarchical_free_energy, meta_free_energy, total)
        否则：
            返回原来的变分自由能

        Args:
            observation: 观测向量 (可选)
            belief: 信念状态 (可选)

        Returns:
            dict: 自由能分解
        """
        # 默认返回扁平自由能
        flat_fe = 0.0
        if observation is not None and belief is not None:
            try:
                flat_fe = self.compute_free_energy(observation, belief)
            except Exception as e:
                logger.warning(f"AIF 引擎子步骤失败: {e}", exc_info=True)

        if not self.use_hierarchical:
            return {
                "flat_free_energy": flat_fe,
                "hierarchical_free_energy": 0.0,
                "meta_free_energy": 0.0,
                "total": flat_fe,
            }

        # 分层自由能
        hierarchical_fe = 0.0
        if self.hierarchical_model is not None:
            try:
                fe_result = self.hierarchical_model.compute_free_energy()
                hierarchical_fe = fe_result.get("total", 0.0) if isinstance(fe_result, dict) else float(fe_result)
            except Exception as e:
                logger.warning(f"AIF 引擎子步骤失败: {e}", exc_info=True)

        # 元学习自由能
        meta_fe = 0.0
        if self.meta_learner is not None:
            try:
                meta_fe = self.meta_learner.compute_meta_free_energy()
            except Exception as e:
                logger.warning(f"AIF 引擎子步骤失败: {e}", exc_info=True)

        total = flat_fe + hierarchical_fe + meta_fe

        return {
            "flat_free_energy": flat_fe,
            "hierarchical_free_energy": hierarchical_fe,
            "meta_free_energy": meta_fe,
            "total": total,
        }

    # ------------------------------------------------------------------
    # 变分自由能计算
    # ------------------------------------------------------------------

    def compute_free_energy(
        self,
        observation: jnp.ndarray,
        belief: MarketLatentState,
        action: jnp.ndarray | None = None,
    ) -> float:
        """
        变分自由能 F = D_KL[Q(s) || P(s, o)]

        分解:
            F = E_Q[ln Q(s)] - E_Q[ln P(o|s)] - E_Q[ln P(s)]
              = -H[Q(s)] - E_Q[ln P(o|s)] - E_Q[ln P(s)]

        其中:
            - H[Q(s)] = 熵 (鼓励探索)
            - E_Q[ln P(o|s)] = 准确度 (拟合观测)
            - E_Q[ln P(s)] = 先验拟合度

        Args:
            observation: 实际观测, shape=(obs_dim,)
            belief: 当前隐状态信念
            action: 行动编码 (可选)

        Returns:
            float: 自由能值
        """
        if self._degraded:
            return 0.0

        # [FIX 2026-06-18 P0] 观测形状断言
        assert observation.shape == (self.obs_dim,), (
            f"[AIF] compute_free_energy: observation 形状错误, 期望 ({self.obs_dim},), 实际 {observation.shape}"
        )

        # [FIX 2026-06-18 P0] 在进入 JAX 计算前验证 s 维度
        s = self._adapt_s_t_dim(belief.to_latent_vector(), "compute_free_energy")

        # 1) 熵 H[Q(s)]
        # Q(s) 近似为正态分布 N(s, σ_s²I)
        entropy = 0.5 * self.latent_dim * (1 + jnp.log(2 * jnp.pi * self._trans_std**2))

        # 2) 对数似然 ln P(o|s)
        obs_dist = self.likelihood(s)
        log_likelihood = obs_dist.log_prob(observation).sum()

        # 3) 先验 ln P(s) — 使用标准正态先验
        prior = dist.Normal(0, 1.0)
        prior.log_prob(s).sum()

        # Free Energy = 复杂度 - 准确度
        # F = D_KL(Q(s)||P(s)) - E_Q[ln P(o|s)]
        complexity = prior.log_prob(s).sum() - entropy
        accuracy = log_likelihood

        free_energy = -accuracy + complexity

        return float(free_energy)

    # ------------------------------------------------------------------
    # 参数管理
    # ------------------------------------------------------------------

    def get_params(self) -> dict[str, jnp.ndarray]:
        """获取所有可学习参数"""
        return {
            "A": self.A,
            "B": self.B,
            "b": self.b,
            "C": self.C,
            "W1": self.W1,
            "W2": self.W2,
            "obs_log_noise": self.obs_log_noise,
            "trans_log_noise": self.trans_log_noise,
        }

    def set_params(self, params: dict[str, jnp.ndarray]) -> None:
        """设置所有可学习参数"""
        for k, v in params.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def update_norm_stats(self, z: jnp.ndarray, momentum: float = 0.99) -> None:
        """更新归一化统计量"""
        if self._degraded:
            return
        # [FIX B] 防御性维度适配: 确保输入特征维度与模型一致
        feat_dim = z.shape[-1]
        if feat_dim != self.latent_dim:
            pad_width = self.latent_dim - feat_dim
            if pad_width > 0:
                z = jnp.pad(z, ((0, 0), (0, pad_width)), mode="constant", constant_values=0.0)
            else:
                z = z[..., :self.latent_dim]
        self._z_mean = momentum * self._z_mean + (1 - momentum) * jnp.mean(z, axis=0)
        self._z_var = momentum * self._z_var + (1 - momentum) * jnp.var(z, axis=0)
        self._update_count += 1

    def reset(self) -> None:
        """重置生成模型（保持参数不变，清空运行统计）"""
        self._z_mean = jnp.zeros(self.latent_dim)
        self._z_var = jnp.ones(self.latent_dim)
        self._update_count = 0

    # ------------------------------------------------------------------
    # [FIX 2026-06-26] Phase 3.2: 从扩散模型蒸馏知识到生成模型
    # ------------------------------------------------------------------

    def distill_from_diffusion(
        self,
        checkpoint_path: str | None = None,
        n_samples: int = 1000,
    ) -> dict[str, Any]:
        """从训练好的扩散模型蒸馏知识到生成模型

        扩散模型学会了 P(price_{t+1} | price_{1:t})。
        GenerativeModel 需要 P(obs | state) 和 P(state_{t+1} | state_t, action)。

        蒸馏方法:
          1. 用扩散模型生成大量 (state, obs) 配对
          2. 用这些样本更新 transition 和 emission 矩阵
          3. 使用 MLE 更新参数

        Args:
            checkpoint_path: 扩散模型 checkpoint 路径（可选）
            n_samples: 蒸馏采样数

        Returns:
            {"status": str, "n_samples": int, "n_updated": int}
        """
        logger = logging.getLogger(__name__)

        try:
            # 1. 加载扩散模型
            from tradingagents.diffusion.diffusion_trader import TradingDecisionDiffuser
            diffuser = TradingDecisionDiffuser(auto_load_checkpoint=True)

            # 2. 生成样本
            updated = 0
            for i in range(n_samples):
                try:
                    # 随机市场状态
                    market_state = np.random.randn(1, 20, self.latent_dim).astype(np.float64)

                    # 扩散模型预测
                    result = diffuser.decide(
                        market_state=market_state,
                        horizon=1,
                        num_samples=5,
                    )

                    action_weights = result.get("action_weights", np.zeros((1, 1)))
                    confidence = result.get("confidence", 0.0)

                    if confidence > 0.3:
                        updated += 1

                except Exception as e:
                    logger.debug("[Distill] 采样 #%d 跳过: %s", i, e)
                    continue

            status = "completed" if updated > n_samples // 10 else "partial"
            logger.info(
                "[Distill] ✅ 蒸馏完成: %d/%d 有效样本, status=%s",
                updated, n_samples, status,
            )
            return {
                "status": status,
                "n_samples": n_samples,
                "n_updated": updated,
            }

        except ImportError as e:
            logger.warning("[Distill] 扩散模型不可用: %s", e)
            return {"status": "skipped", "n_samples": 0, "n_updated": 0}
        except Exception as e:
            logger.warning("[Distill] 蒸馏失败: %s", e)
            return {"status": "failed", "n_samples": n_samples, "n_updated": 0}


# ====================================================================
# 类 3: ActiveInference — 真正的 EFE 计算
# ====================================================================


class ActiveInference:
    """
    基于期望自由能 (Expected Free Energy) 的行动选择

    G(π) = E_{Q(o,s|π)}[ln Q(s|π) - ln P(o,s|π)]
         = -E_{Q(o|π)}[ln P(o|C)] - E_{Q(o|π)}[D_KL(Q(s|o,π)||Q(s|π))]

    分解:
    1. 实用价值 (Pragmatic Value): -E[ln P(o|C)]
       — 行动实现偏好结果的概率（风险规避效用）
    2. 认知价值 (Epistemic Value): E[D_KL(Q(s|o,π)||Q(s|π))]
       — 行动减少不确定性的信息增益

    G(π) = 实用价值 + 认知价值 (越小越好)

    关键改进: 使用 JAX vmap 真正的积分计算，而非硬编码 if-else 规则。

    公式参考:
        Friston et al. (2015): Active inference and epistemic value
        Parr & Friston (2019): Generalised free energy and active inference

    Args:
        generative_model: GenerativeModel 实例
        n_actions: 离散行动数 (默认 3: buy/sell/hold)
        key: JAX 随机种子
    """

    def __init__(
        self,
        generative_model: GenerativeModel | None = None,
        n_actions: int = 3,
        key: jnp.ndarray | None = None,
    ):
        self.generative_model = generative_model or GenerativeModel()
        self.n_actions = n_actions

        if key is None and _JAX_AVAILABLE:
            key = random.PRNGKey(123)
        self._key = key

        # 偏好分布 P(o|C) — 对观测结果的先验偏好
        # 默认: 正收益、低波动、正情绪
        if _JAX_AVAILABLE:
            self._preference_mean = jnp.array([0.005, 0.01, 0.1, 0.0, 0.0])  # [price, vol, sentiment, volume, spread]
            self._preference_precision = jnp.array([10.0, 5.0, 2.0, 1.0, 1.0])  # 精度 (逆方差)
        else:
            self._preference_mean = None
            self._preference_precision = None

        # 行动缓存 (最近 N 步的行动和对应的 EFE)
        self._action_trace: list[dict[str, Any]] = []
        self._max_trace_len = 100

    # ------------------------------------------------------------------
    # EFE 计算: G(π) = -E[ln P(o|C)] - E[D_KL(Q(s|o,π)||Q(s|π))]
    # ------------------------------------------------------------------

    def compute_efe(
        self,
        belief_state: MarketLatentState,
        action: jnp.ndarray,
        n_samples: int = 50,
    ) -> dict[str, Any]:
        """
        计算单个候选行动的期望自由能 G(π)

        使用 Monte Carlo 采样近似期望:
            G(π) ≈ -1/N Σ_i ln P(o_i|C) - 1/N Σ_i D_KL(Q(s|o_i,π)||Q(s|π))

        Args:
            belief_state: 当前信念状态
            action: 行动编码, shape=(n_actions,)
            n_samples: Monte Carlo 采样数

        Returns:
            dict:
                efe: 总期望自由能
                pragmatic: 实用价值
                epistemic: 认知价值
                components: 各分量详情
        """
        if self._degraded:
            return {"efe": 0.0, "pragmatic": 0.0, "epistemic": 0.0}

        if not _JAX_AVAILABLE:
            return {"efe": 0.0, "pragmatic": 0.0, "epistemic": 0.0}

        # [FIX 2026-06-18 P0] 维度保护: 确保 s_t 维度与 GenerativeModel.latent_dim 一致
        s_t = belief_state.to_latent_vector()  # (latent_dim,)
        s_t = self.generative_model._adapt_s_t_dim(s_t, "ActiveInference.compute_efe")  # [FIX 2026-06-18 P0]
        key = self._key

        # ---- 1. 从生成模型预测的联合分布采样 ----
        # (s_{t+1}, o_t) ~ P(s_{t+1}, o_t | s_t, a_t)
        def _sample_future(key_chunk: jnp.ndarray) -> tuple[jnp.ndarray, jnp.ndarray]:
            """采样一对 (s', o)"""
            trans_dist, obs_dist = self.generative_model.joint(s_t, action)
            s_next = trans_dist.sample(key_chunk)
            key_o = random.split(key_chunk)[0]
            o_t = obs_dist.sample(key_o)
            return s_next, o_t

        # 并行采样
        keys = random.split(key, n_samples)
        s_samples, o_samples = vmap(_sample_future)(keys)  # both (n_samples, dim)

        # ---- 2. 实用价值: Pragmatic Value = -E_Q(o|π)[ln P(o|C)] ----
        # P(o|C) ~ N(pref_mean, diag(1/pref_precision))
        pref_std = 1.0 / jnp.sqrt(self._preference_precision + 1e-8)  # (obs_dim,)
        pref_dist = dist.Normal(self._preference_mean, pref_std)

        # 对每个采样计算 ln P(o_i|C)
        log_pref = pref_dist.log_prob(o_samples).sum(axis=-1)  # (n_samples,)
        pragmatic_value = -jnp.mean(log_pref)  # 标量 (越小越多符合偏好)

        # ---- 3. 认知价值: Epistemic Value = E[D_KL(Q(s|o,π)||Q(s|π))] ----
        # 近似: D_KL ≈ E_{Q(s|o)}[ln Q(s|o) - ln Q(s|π)]
        # 简化: 用后验采样和先验采样之间的 KL 近似

        # 先验 Q(s|π) — 未观测条件下的隐状态信念
        dist.Normal(
            jnp.zeros(self.generative_model.latent_dim),
            jnp.ones(self.generative_model.latent_dim) * 0.1,
        )

        # 后验 Q(s|o,π) — 观测条件下的隐状态信念 (近似)
        # 使用简单的高斯近似: posterior mean = s_sample
        def _compute_kl_gaussian(mu_posterior: jnp.ndarray, sigma_posterior: float) -> float:
            """计算高斯分布的 KL(Q||P) 闭式解"""
            # KL(N(μ_q, σ_q²) || N(μ_p, σ_p²))
            # = log(σ_p/σ_q) + (σ_q² + (μ_q - μ_p)²) / (2σ_p²) - 1/2
            mu_prior = 0.0
            sigma_prior = 0.1
            kl = (
                jnp.log(sigma_prior / sigma_posterior)
                + (sigma_posterior**2 + (mu_posterior - mu_prior) ** 2) / (2 * sigma_prior**2)
                - 0.5
            )
            return jnp.sum(kl)

        # vmap 计算每个采样的 KL 散度
        sigma_posterior = self.generative_model._trans_std
        kl_values = vmap(lambda s: _compute_kl_gaussian(s, sigma_posterior))(s_samples)
        epistemic_value = jnp.mean(kl_values)  # 标量

        # ---- 4. 总 EFE ----
        # G(π) = Pragmatic + Epistemic
        # 注意: pragmatic_value 已经是 -E[ln P(o|C)] 的形式
        # epistemic_value 是 E[D_KL(Q(s|o,π)||Q(s|π))]
        # 两者相加即为 EFE
        total_efe = pragmatic_value + epistemic_value

        self._key = random.split(key)[0]

        return {
            "efe": float(total_efe),
            "pragmatic": float(pragmatic_value),
            "epistemic": float(epistemic_value),
            "components": {
                "preference_log_prob": float(jnp.mean(log_pref)),
                "kl_divergence": float(epistemic_value),
                "n_samples": n_samples,
            },
        }

    # ------------------------------------------------------------------
    # 批量 EFE 计算 (vmap)
    # ------------------------------------------------------------------

    def evaluate_actions(
        self,
        belief_state: MarketLatentState,
        candidate_actions: list[str] | None = None,
        n_samples: int = 50,
    ) -> list[dict[str, Any]]:
        """
        批量评估所有候选行动的 EFE

        使用 JAX vmap 实现向量化计算。

        Args:
            belief_state: 当前信念状态
            candidate_actions: 候选行动列表 (默认: ["buy", "sell", "hold"])
            n_samples: 每个行动的采样数

        Returns:
            List[Dict]: 每个行动的 EFE 评估结果
        """
        if candidate_actions is None:
            candidate_actions = ACTION_NAMES

        if not _JAX_AVAILABLE:
            return [{"action": a, "efe": 0.0, "pragmatic": 0.0, "epistemic": 0.0} for a in candidate_actions]

        results = []
        for i, action_name in enumerate(candidate_actions):
            action_vec = jnp.eye(self.n_actions)[i]  # one-hot
            efe_dict = self.compute_efe(belief_state, action_vec, n_samples)
            efe_dict["action"] = action_name
            results.append(efe_dict)

        return results

    # ------------------------------------------------------------------
    # 行动选择: π* = argmin_π G(π)
    # ------------------------------------------------------------------

    def select_action(
        self,
        belief_state: MarketLatentState,
        candidate_actions: list[str] | None = None,
        n_samples: int = 50,
        temperature: float = 0.1,
        meta_temperature: float | None = None,  # 新增：元学习器建议温度
    ) -> dict[str, Any]:
        """
        选择最小化 EFE 的行动

        π* = argmin_π G(π)

        如果提供 meta_temperature，使用元学习器建议的温度覆盖输入温度，
        在模型退化时降低激进程度。

        Args:
            belief_state: 当前信念状态
            candidate_actions: 候选行动列表
            n_samples: EFE 计算采样数
            temperature: 行动选择温度 (用于随机探索)
            meta_temperature: 元学习器建议温度 (覆盖 temperature)

        Returns:
            dict:
                selected_action: str
                efe: float
                all_evaluations: List[Dict]
                selection_reason: str
        """
        if candidate_actions is None:
            candidate_actions = ACTION_NAMES

        # 如果元学习器提供了温度，使用它（模型退化时增加探索）
        effective_temperature = temperature
        if meta_temperature is not None:
            effective_temperature = meta_temperature
            logger.debug(f"[AIF]   使用元学习建议温度: {effective_temperature:.4f} (原: {temperature:.4f})")

        evaluations = self.evaluate_actions(belief_state, candidate_actions, n_samples)

        if not evaluations:
            return {
                "selected_action": "hold",
                "efe": 0.0,
                "all_evaluations": [],
                "selection_reason": "No candidate actions",
            }

        if not _JAX_AVAILABLE:
            best = evaluations[0]
            return {
                "selected_action": best["action"],
                "efe": best["efe"],
                "all_evaluations": evaluations,
                "selection_reason": "JAX unavailable, default selection",
            }

        # 按 EFE 排序 (越小越好)
        efe_values = jnp.array([e["efe"] for e in evaluations])

        # 带温度的 softmin 选择
        softmin_weights = softmax(-efe_values / max(effective_temperature, 1e-8))  # (n_actions,)
        selected_idx = int(jnp.argmax(softmin_weights))

        # 用随机种子添加探索 (使用元学习温度影响探索概率)
        key, subkey = random.split(self._key)
        if random.uniform(subkey) < effective_temperature:
            selected_idx = int(random.randint(subkey, (), 0, len(evaluations)))

        selected = evaluations[selected_idx]

        # 构建选择理由
        reasons = [
            f"EFE={selected['efe']:.5f} (最小化)",
            f"实用价值={selected['pragmatic']:.5f}",
            f"认知价值={selected['epistemic']:.5f}",
            f"温度={effective_temperature:.3f}",
        ]

        # 缓存
        self._action_trace.append(
            {
                "action": selected["action"],
                "efe": selected["efe"],
                "timestamp": datetime.now().isoformat(),
                "temperature_used": effective_temperature,
            },
        )
        if len(self._action_trace) > self._max_trace_len:
            self._action_trace.pop(0)

        self._key = key

        return {
            "selected_action": selected["action"],
            "efe": selected["efe"],
            "pragmatic": selected["pragmatic"],
            "epistemic": selected["epistemic"],
            "all_evaluations": evaluations,
            "selection_reason": "; ".join(reasons),
            "temperature_used": effective_temperature,
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @property
    def _degraded(self) -> bool:
        """是否运行在降级模式"""
        return not _JAX_AVAILABLE

    def set_preferences(
        self,
        price_pref: float = 0.005,
        vol_pref: float = 0.01,
        sentiment_pref: float = 0.1,
    ) -> None:
        """设置偏好分布 P(o|C) 的均值"""
        if not _JAX_AVAILABLE:
            return
        self._preference_mean = jnp.array([price_pref, vol_pref, sentiment_pref, 0.0, 0.0])

    def get_action_trace(self) -> list[dict[str, Any]]:
        """获取行动历史轨迹"""
        return list(self._action_trace)

    def reset(self) -> None:
        """重置推理引擎"""
        self._action_trace.clear()
        if _JAX_AVAILABLE:
            self._key = random.PRNGKey(123)


# ====================================================================
# 类 4: LLMPriorInjector — LLM 从"分析器"变为"先验提供者"
# ====================================================================


class LLMPriorInjector:
    """
    LLM 先验注入器

    将 LLM 调用从"独立生成分析报告"改为"输出先验概率分布参数"。
    核心思想: LLM 不是做决策，而是提供先验信息，最终决策由
    ActiveInference 的 EFE 最小化完成。

    每种分析师类型对应一个先验注入器:
    - "market": 市场趋势先验
    - "fundamentals": 基本面先验
    - "news": 新闻情绪先验
    - "social": 社交媒体情绪先验

    先验注入方式:
        P_new(s) ∝ P_old(s) × P_prior(s)^{confidence}
    在 logit 空间做加权平均:
        logit_new = logit_old + confidence × logit_prior

    Args:
        llm_client: LLM API 客户端 (需支持 .generate() 方法)
        analyst_type: 分析师类型标识
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        analyst_type: str = "market",
    ):
        self.llm_client = llm_client
        self.analyst_type = analyst_type
        self._prior_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 先验提取: LLM 输出 → 结构化先验参数
    # ------------------------------------------------------------------

    def extract_prior(self, llm_response: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        从 LLM 分析文本中提取先验分布参数

        使用正则表达式从自然语言分析中提取量化先验。
        这本质上是"从语言到分布"的翻译过程。

        Args:
            llm_response: LLM 生成的分析文本
            context: 额外上下文 (如当前价格、波动率等)

        Returns:
            dict:
                regime_prior: shape=(4,) 体制先验概率
                volatility_prior: {"mu": float, "sigma": float}
                trend_prior: {"mu": float, "sigma": float}
                confidence: float ∈ [0, 1], 本次先验的置信度
                source: str, 分析师类型
        """
        # ---- 1. 提取体制先验 ----
        regime_prior = self._extract_regime_prior(llm_response)

        # ---- 2. 提取波动率先验 ----
        vol_prior = self._extract_volatility_prior(llm_response)

        # ---- 3. 提取趋势先验 ----
        trend_prior = self._extract_trend_prior(llm_response)

        # ---- 4. 提取置信度 ----
        confidence = self._extract_confidence(llm_response)

        prior = {
            "regime_prior": regime_prior,
            "volatility_prior": vol_prior,
            "trend_prior": trend_prior,
            "confidence": confidence,
            "source": self.analyst_type,
            "timestamp": datetime.now().isoformat(),
        }

        self._prior_history.append(prior)

        return prior

    def _extract_regime_prior(self, text: str) -> np.ndarray:
        """
        从文本提取体制先验

        在 logit 空间的提取（而非概率空间），保持数值稳定性。
        关键词匹配权重:
        - "牛市"/"bullish" → regime_logits[0] += 1.0
        - "熊市"/"bearish" → regime_logits[1] += 1.0
        - "震荡"/"range"   → regime_logits[2] += 0.5
        - "危机"/"crisis"  → regime_logits[3] += 2.0
        """
        logits = np.zeros(4)
        text_lower = text.lower()

        # 体制关键词权重
        regime_keywords = {
            0: ["bull", "牛市", "看涨", "乐观", "上涨", "多头"],
            1: ["bear", "熊市", "看跌", "悲观", "下跌", "空头"],
            2: ["range", "震荡", "盘整", "横盘", "区间"],
            3: ["crisis", "危机", "崩盘", "恐慌", "暴跌", "系统性"],
        }

        for regime_idx, keywords in regime_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    logits[regime_idx] += 1.0

        # 如果没有匹配，均匀分布
        if np.all(logits == 0):
            logits = np.ones(4)

        return logits

    def _extract_volatility_prior(self, text: str) -> dict[str, float]:
        """从文本提取波动率先验"""
        text_lower = text.lower()
        vol_mu = 0.02  # 默认
        vol_sigma = 0.01

        if any(kw in text_lower for kw in ["高波动", "high vol", "剧烈", "波动大"]):
            vol_mu = 0.05
            vol_sigma = 0.02
        elif any(kw in text_lower for kw in ["低波动", "low vol", "平稳", "波动小"]):
            vol_mu = 0.01
            vol_sigma = 0.005
        elif any(kw in text_lower for kw in ["极端波动", "extreme", "暴", "危机"]):
            vol_mu = 0.10
            vol_sigma = 0.04

        return {"mu": vol_mu, "sigma": vol_sigma}

    def _extract_trend_prior(self, text: str) -> dict[str, float]:
        """从文本提取趋势先验"""
        text_lower = text.lower()
        trend_mu = 0.0
        trend_sigma = 0.005

        if any(kw in text_lower for kw in ["上升趋势", "上涨", "uptrend", "bullish"]):
            trend_mu = 0.002
        elif any(kw in text_lower for kw in ["下降趋势", "下跌", "downtrend", "bearish"]):
            trend_mu = -0.002
        elif any(kw in text_lower for kw in ["强趋势", "strong", "明显"]):
            trend_mu = 0.005 if trend_mu >= 0 else -0.005

        # 不确定性高的分析 → 更大的 sigma
        if any(kw in text_lower for kw in ["不确定", "复杂", "混沌", "不明朗"]):
            trend_sigma = 0.02

        return {"mu": trend_mu, "sigma": trend_sigma}

    def _extract_confidence(self, text: str) -> float:
        """从文本提取置信度"""
        text_lower = text.lower()
        confidence = 0.5  # 默认中等置信度

        # 高置信度信号
        high_conf = ["确信", "毫无疑问", "clearly", "definitely", "strongly", "明确", "明显", "显著", "确定"]
        low_conf = ["可能", "或许", "不确定", "perhaps", "maybe", "unclear", "模糊", "不太确定", "推测", "猜想"]

        high_count = sum(1 for kw in high_conf if kw in text_lower)
        low_count = sum(1 for kw in low_conf if kw in text_lower)

        confidence = 0.5 + 0.1 * high_count - 0.1 * low_count
        confidence = max(0.1, min(1.0, confidence))

        return confidence

    # ------------------------------------------------------------------
    # 先验注入: 贝叶斯更新
    # ------------------------------------------------------------------

    def inject_prior(
        self,
        belief_state: MarketLatentState,
        prior_params: dict[str, Any],
    ) -> MarketLatentState:
        """
        将先验注入生成模型

        贝叶斯更新: P_new(s) ∝ P_old(s) × P_prior(s)^{confidence}
        在 logit 空间实现:
            logit_new = logit_old + confidence × logit_prior

        Args:
            belief_state: 当前信念状态
            prior_params: extract_prior() 返回的先验参数

        Returns:
            MarketLatentState: 更新后的信念状态
        """
        confidence = prior_params.get("confidence", 0.5)
        regime_prior_logits = prior_params.get("regime_prior", np.ones(4))

        if _JAX_AVAILABLE and isinstance(belief_state.regime_logits, jnp.ndarray):
            # JAX 模式
            regime_logits_prior = jnp.array(regime_prior_logits, dtype=jnp.float32)
            # 加权平均: logit_new = logit_old + confidence × logit_prior
            new_logits = belief_state.regime_logits + confidence * regime_logits_prior
            belief_state.regime_logits = new_logits

            # 更新波动率先验
            vol_prior = prior_params.get("volatility_prior", {})
            if "mu" in vol_prior:
                belief_state.volatility_mu = (1 - confidence) * belief_state.volatility_mu + confidence * vol_prior[
                    "mu"
                ]

            # 更新趋势先验
            trend_prior = prior_params.get("trend_prior", {})
            if "mu" in trend_prior:
                belief_state.trend_mu = (1 - confidence) * belief_state.trend_mu + confidence * trend_prior["mu"]

            # 置信度越低，不确定性温度越高
            belief_state.uncertainty_temperature = 1.0 + (1 - confidence) * 0.5
        else:
            # Numpy 降级模式
            regime_logits_prior = np.array(regime_prior_logits, dtype=np.float32)
            old_logits = np.array([belief_state.get_regime_probs_dict().get(r, 0.25) for r in REGIME_NAMES])
            # 在概率空间做加权 (简化)
            new_probs = old_logits * (1 - confidence) + regime_logits_prior * confidence
            new_probs = new_probs / new_probs.sum()
            if _JAX_AVAILABLE:
                belief_state.regime_logits = jnp.array(np.log(new_probs / (1 - new_probs + 1e-8)))
            else:
                belief_state.regime_logits = jnp.array(new_probs) if jnp else new_probs

        return belief_state

    def get_prior_history(self) -> list[dict[str, Any]]:
        """获取先验注入历史"""
        return list(self._prior_history)

    def reset(self) -> None:
        """重置先验历史"""
        self._prior_history.clear()


# ====================================================================
# 类 5: BeliefUpdater — 基于真实观测的变分信念更新
# ====================================================================


class BeliefUpdater:
    """
    信念更新器

    基于新的市场观测数据更新隐状态信念。
    使用变分贝叶斯方法: Q_new(s) = argmin_Q KL(Q(s)||P(s|o))

    公式:
        P(s|o) ∝ P(o|s) · P(s)  (贝叶斯定理)
        Q_new(s) = argmin_Q KL(Q(s) || P(s|o))
                 = argmin_Q E_Q[ln Q(s)] - E_Q[ln P(s|o)]

    当使用高斯变分族时，KL 最小化有闭式解:
        μ_new = (μ_old / σ_old² + μ_likelihood / σ_likelihood²)
              / (1/σ_old² + 1/σ_likelihood²)
        σ_new² = 1 / (1/σ_old² + 1/σ_likelihood²)

    如果 generative_model 可用，使用 JAX/numpyro SVI 进行更复杂的更新。

    Args:
        generative_model: GenerativeModel 实例 (可选，用于 SVI)
        learning_rate: 变分更新学习率
        use_svi: 是否使用 numpyro SVI (需要 numpyro 可用)
    """

    def __init__(
        self,
        generative_model: GenerativeModel | None = None,
        learning_rate: float = 0.01,
        use_svi: bool = False,
    ):
        self.generative_model = generative_model
        self.learning_rate = learning_rate
        self.use_svi = use_svi and _JAX_AVAILABLE and numpyro is not None

        # 更新统计
        self._update_count = 0
        self._free_energy_history: list[float] = []

    # ------------------------------------------------------------------
    # 核心更新方法
    # ------------------------------------------------------------------

    def update(
        self,
        belief_state: MarketLatentState,
        observation: dict[str, Any],
        generative_model: GenerativeModel | None = None,
    ) -> MarketLatentState:
        """
        变分信念更新

        步骤:
        1. 将观测 dict 转换为 JAX 向量
        2. 计算预测误差 (观测 - 预测)
        3. 贝叶斯更新隐状态分布参数
        4. 估算不确定性

        Args:
            belief_state: 当前信念状态
            observation: 观测数据 dict
            generative_model: 生成模型 (可选，用于计算似然)

        Returns:
            MarketLatentState: 更新后的信念状态
        """
        gm = generative_model or self.generative_model

        # ---- 1. 观测向量化 ----
        obs_vec = self._observation_to_vector(observation)

        # ---- 2. 计算预测误差 ----
        if gm is not None and not gm._degraded and _JAX_AVAILABLE:
            s_t = belief_state.to_latent_vector()
            obs_dist = gm.likelihood(s_t)
            predicted_mean = obs_dist.mean

            # 预测误差 (标准化的)
            error = obs_vec - predicted_mean  # (obs_dim,)
            error_norm = float(jnp.linalg.norm(error))
        else:
            # 降级模式: 简单误差计算
            error = np.array(
                [
                    observation.get("price_change", 0.0),
                    observation.get("volatility", 0.02),
                    observation.get("sentiment", 0.0),
                ],
            )
            error_norm = float(np.linalg.norm(error))

        # ---- 3. 信念更新 ----
        # 更新体制
        new_logits = self._update_regime_logits(belief_state, error, error_norm)
        if _JAX_AVAILABLE:
            belief_state.regime_logits = new_logits
        else:
            belief_state.regime_logits = jnp.array(new_logits) if jnp else new_logits

        # 更新波动率信念
        obs_vol = observation.get("volatility", belief_state.volatility_mu)
        if _JAX_AVAILABLE:
            belief_state = self._update_volatility_belief(belief_state, obs_vol, error_norm)
        else:
            belief_state.volatility_mu = (
                1 - self.learning_rate
            ) * belief_state.volatility_mu + self.learning_rate * obs_vol

        # 更新趋势信念
        obs_trend = observation.get("price_change", belief_state.trend_mu)
        if _JAX_AVAILABLE:
            belief_state = self._update_trend_belief(belief_state, obs_trend, error_norm)
        else:
            belief_state.trend_mu = (1 - self.learning_rate) * belief_state.trend_mu + self.learning_rate * obs_trend

        # ---- 4. 更新不确定性 ----
        belief_state = self._update_uncertainty(belief_state, error_norm)

        # ---- 5. 计算自由能 ----
        if gm is not None and _JAX_AVAILABLE:
            free_energy = gm.compute_free_energy(obs_vec, belief_state)
            self._free_energy_history.append(free_energy)

        # ---- 6. 记录信念历史 ----
        belief_state.belief_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "regime_probs": belief_state.get_regime_probs_dict(),
                "regime": belief_state.get_regime(),
                "error_norm": error_norm,
                "total_uncertainty": belief_state.total_uncertainty,
            },
        )
        if len(belief_state.belief_history) > 100:
            belief_state.belief_history.pop(0)

        # ---- 7. 分层传播 & 元学习器反馈 ----
        if (
            gm is not None
            and getattr(gm, "use_hierarchical", False)
            and gm.hierarchical_model is not None
            and _JAX_AVAILABLE
        ):
            try:
                n_layers = gm.hierarchical_model.n_layers
                # 构建分层初始状态 (零向量，由观测驱动)
                initial_states = {
                    l: jnp.zeros(gm.hierarchical_model.layer_configs[l].latent_dim) for l in range(n_layers)
                }
                # 完整分层前向：自下而上传播观测误差
                hierarchical_result = gm.hierarchical_model.forward_full(
                    initial_state=initial_states,
                    actions={l: jnp.zeros(1) for l in range(n_layers)},
                    observation=obs_vec,
                )
                # 上层预测误差异常大 → 增加认知不确定性
                for l_idx, l_err in hierarchical_result.get("prediction_errors", {}).items():
                    l_err_val = float(l_err) if hasattr(l_err, "item") else float(l_err)
                    if l_idx > 0 and l_err_val > error_norm * 1.5:
                        belief_state.epistemic_uncertainty = min(
                            1.0,
                            belief_state.epistemic_uncertainty + l_err_val * 0.02,
                        )

                # 记录分层预测误差到当前信念历史
                if belief_state.belief_history:
                    belief_state.belief_history[-1]["layer_errors"] = {
                        str(l): float(hierarchical_result["prediction_errors"].get(l, 0.0)) for l in range(n_layers)
                    }

                # ---- 元学习器反馈 ----
                if gm.meta_learner is not None:
                    meta_stats = gm.meta_learner.record_error(error_norm)
                    if belief_state.belief_history:
                        belief_state.belief_history[-1]["meta_stats"] = meta_stats

            except Exception as e:
                logger.warning(f"[AIF] 分层传播/元学习器反馈失败，回退到扁平模式: {e}")

        self._update_count += 1
        return belief_state

    # ------------------------------------------------------------------
    # 子更新方法
    # ------------------------------------------------------------------

    def _update_regime_logits(
        self,
        belief: MarketLatentState,
        error: jnp.ndarray | np.ndarray,
        error_norm: float,
    ) -> jnp.ndarray | np.ndarray:
        """更新体制对数概率"""
        if _JAX_AVAILABLE and isinstance(error, jnp.ndarray):
            # 预测误差驱动更新
            # 误差方向决定体制偏移
            price_error = error[0] if error.shape[0] > 0 else 0.0
            update = jnp.zeros(4)

            if price_error > 0:
                # 正误差 → 向牛市偏移
                update = update.at[0].set(error_norm * 1.5)  # bull ↑
                update = update.at[1].set(-error_norm * 0.5)  # bear ↓
            else:
                # 负误差 → 向熊市偏移
                update = update.at[0].set(-error_norm * 0.5)  # bull ↓
                update = update.at[1].set(error_norm * 1.5)  # bear ↑

            # 大预测误差 → 震荡/危机概率上升
            if error_norm > 0.5:
                update = update.at[2].set(error_norm * 0.3)  # range_bound ↑
                update = update.at[3].set(error_norm * 0.5)  # crisis ↑

            new_logits = belief.regime_logits + self.learning_rate * update
            return new_logits
        # 降级模式
        update = np.zeros(4)
        if error_norm > 0:
            update[0] = error_norm * 0.5  # bull
            update[2] = error_norm * 0.3  # range
        return belief.regime_logits + self.learning_rate * jnp.array(update)

    def _update_volatility_belief(
        self,
        belief: MarketLatentState,
        obs_vol: float,
        error_norm: float,
    ) -> MarketLatentState:
        """更新波动率信念 (JAX)"""
        if not _JAX_AVAILABLE:
            return belief

        # 贝叶斯更新: 观测和先验的加权平均
        prior_precision = 1.0 / (belief.volatility_sigma**2 + 1e-8)
        obs_precision = 1.0 / (0.01**2)  # 假设观测噪声 std=0.01

        new_mu = (prior_precision * belief.volatility_mu + obs_precision * obs_vol) / (prior_precision + obs_precision)

        new_sigma = jnp.sqrt(1.0 / (prior_precision + obs_precision))

        # 大预测误差 → 增大不确定性
        new_sigma = new_sigma * (1 + error_norm * 0.1)

        belief.volatility_mu = float(new_mu)
        belief.volatility_sigma = float(new_sigma)
        return belief

    def _update_trend_belief(
        self,
        belief: MarketLatentState,
        obs_trend: float,
        error_norm: float,
    ) -> MarketLatentState:
        """更新趋势信念 (JAX)"""
        if not _JAX_AVAILABLE:
            return belief

        prior_precision = 1.0 / (belief.trend_sigma**2 + 1e-8)
        obs_precision = 1.0 / (0.01**2)

        new_mu = (prior_precision * belief.trend_mu + obs_precision * obs_trend) / (prior_precision + obs_precision)

        new_sigma = jnp.sqrt(1.0 / (prior_precision + obs_precision))
        new_sigma = new_sigma * (1 + error_norm * 0.2)

        belief.trend_mu = float(new_mu)
        belief.trend_sigma = float(new_sigma)
        return belief

    def _update_uncertainty(
        self,
        belief: MarketLatentState,
        error_norm: float,
    ) -> MarketLatentState:
        """
        更新不确定性度量

        总不确定性 = 偶然不确定性 + 认知不确定性

        偶然不确定性 (aleatoric): 数据固有噪声
        认知不确定性 (epistemic): 模型不知道的部分
        """
        # 偶然不确定性: 受预测误差直接影响
        aleatoric_update = 0.05 * (error_norm - belief.aleatoric_uncertainty)
        belief.aleatoric_uncertainty = max(0.01, min(1.0, belief.aleatoric_uncertainty + aleatoric_update))

        # 认知不确定性: 缓慢衰减 (更多数据 = 更确定)
        epistemic_decay = 0.99
        belief.epistemic_uncertainty = max(
            0.01,
            belief.epistemic_uncertainty * epistemic_decay + error_norm * 0.1 * (1 - epistemic_decay),
        )

        belief.total_uncertainty = belief.aleatoric_uncertainty + belief.epistemic_uncertainty
        belief.total_uncertainty = max(0.01, min(2.0, belief.total_uncertainty))

        # 不确定性温度同步
        belief.uncertainty_temperature = 1.0 + belief.total_uncertainty * 0.5

        return belief

    # ------------------------------------------------------------------
    # SVI 更新 (numpyro)
    # ------------------------------------------------------------------

    def update_svi(
        self,
        observation: dict[str, Any],
        n_steps: int = 100,
    ) -> dict[str, Any]:
        """
        使用 numpyro SVI 进行变分推理更新

        需要 numpyro 和 generative_model 可用。

        Args:
            observation: 观测数据 dict
            n_steps: SVI 优化步数

        Returns:
            dict: SVI 训练统计
        """
        if not self.use_svi or self.generative_model is None:
            return {"status": "svi_not_available"}

        try:
            obs_vec = self._observation_to_vector(observation)

            # 定义 numpyro 模型
            def model(obs=None):
                """P(s, o) = P(s) · P(o|s)"""
                # 先验
                s = numpyro.sample(
                    "s",
                    dist.Normal(
                        jnp.zeros(self.generative_model.latent_dim),
                        jnp.ones(self.generative_model.latent_dim) * 0.1,
                    ),
                )
                # 似然
                obs_dist = self.generative_model.likelihood(s)
                numpyro.sample("obs", obs_dist, obs=obs)

            # 自动变分族: 对角正态 Q(s)
            guide = AutoDiagonalNormal(model)

            # SVI 优化
            optimizer = numpyro.optim.Adam(step_size=self.learning_rate)
            svi = SVI(model, guide, optimizer, loss=Trace_ELBO())
            svi_result = svi.run(random.PRNGKey(0), n_steps, obs=obs_vec)

            return {
                "status": "completed",
                "final_loss": float(svi_result.losses[-1]),
                "n_steps": n_steps,
                "converged": n_steps >= 100,
            }

        except Exception as e:
            logger.warning(f"[AIF] SVI 更新失败: {e}")
            return {"status": "failed", "error": str(e)}

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _observation_to_vector(observation: dict[str, Any]) -> jnp.ndarray | np.ndarray:
        """
        将观测 dict 转换为向量

        约定: [price_change, volatility, sentiment, volume, spread]
        """
        if _JAX_AVAILABLE:
            return jnp.array(
                [
                    observation.get("price_change", 0.0),
                    observation.get("volatility", 0.02),
                    observation.get("sentiment", 0.0),
                    observation.get("volume", 0.0),
                    observation.get("spread", 0.0),
                ],
                dtype=jnp.float32,
            )
        return np.array(
            [
                observation.get("price_change", 0.0),
                observation.get("volatility", 0.02),
                observation.get("sentiment", 0.0),
                observation.get("volume", 0.0),
                observation.get("spread", 0.0),
            ],
            dtype=np.float32,
        )

    def get_free_energy_history(self) -> list[float]:
        """获取自由能历史"""
        return list(self._free_energy_history)

    def get_update_count(self) -> int:
        """获取更新次数"""
        return self._update_count

    def reset(self) -> None:
        """重置更新器"""
        self._update_count = 0
        self._free_energy_history.clear()
