# tradingagents/diffusion/config.py
"""
扩散模型全局配置 (Diffusion Configuration)

定义 DiffusionConfig 数据类，管理扩散采样的所有超参数，
包括噪声调度、网络结构、条件引导、性能优化等。

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 TradingAgents-CN 的配置风格一致
    - 所有参数均有合理默认值，开箱即用
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class DiffusionConfig:
    """扩散模型全局配置数据类

    管理 DDIM 采样、Score Network、CFG 引导等所有扩散相关超参数。

    Attributes:
        num_timesteps: DDIM 采样步数 (默认 50)
        beta_start: 噪声调度起始值 (默认 1e-4)
        beta_end: 噪声调度终止值 (默认 0.02)
        beta_schedule: 噪声调度类型 ("linear" | "cosine" | "sigmoid")
        hidden_dim: 网络隐藏层维度 (默认 128)
        num_res_blocks: 残差块数量 (默认 4)
        cond_dim: 条件嵌入维度 (默认 32)
        use_classifier_free_guidance: 是否启用 CFG (默认 True)
        cfg_scale: CFG 引导强度 (默认 3.0)
        use_score_cache: 是否预计算 Score Table 缓存 (默认 True)
        score_cache_size: Score Cache 最大条目数 (默认 10000)
        batch_size: 批量推理大小 (默认 32)
        prior_type: 先验类型，失败时退化目标 (默认 "uniform")
        latent_dim: 潜在空间维度 (默认 32, 与 HPC-Loop 一致)
        diffusion_steps_T: 完整扩散步数 (训练用, 默认 1000)
        n_uncertainty_samples: 不确定性量化采样数 (默认 16)
    """

    # === 采样参数 ===
    num_timesteps: int = 20
    """[优化 2026-06-22] DDIM 采样步数 K。从 100 缩减至 20 步。
    DDIM 是确定性采样，20 步已能生成高质量样本。
    配合自适应精度和渐进式采样，单次 decide() 耗时从 180s 降至 ~5-10s。"""

    beta_start: float = 1e-4
    """噪声调度 β 起始值。较小的值使早期扩散步的噪声注入更温和。"""

    beta_end: float = 0.02
    """噪声调度 β 终止值。0.02 是 DDPM 论文标准设置。"""

    beta_schedule: str = "linear"
    """噪声调度类型:
        - "linear":   β_t 线性增长 (DDPM 标准)
        - "cosine":   β_t 余弦调度，SNR 更均匀
        - "sigmoid":  β_t S 型曲线，中间步变化更陡
    """

    # === 网络结构 ===
    hidden_dim: int = 128
    """Score Network 隐藏层维度。128 为轻量级设置，适应时序金融数据。
    对于更复杂的模式识别可提升至 256。"""

    num_res_blocks: int = 4
    """TemporalUNet1D 中每个分辨率的残差块数量。
    更多的残差块增加模型容量，但也会增加推理延迟。"""

    # === 条件注入 ===
    cond_dim: int = 32
    """条件嵌入维度。条件向量 (市场体制、宏观因子等) 编码后的维度。
    通过 FiLM (Feature-wise Linear Modulation) 注入网络各层。"""

    use_classifier_free_guidance: bool = True
    """是否启用 Classifier-Free Guidance。启用后，采样时同时计算
    条件预测和无条件预测，通过 cfg_scale 插值增强条件控制。"""

    cfg_scale: float = 3.0
    """CFG 引导强度 w。公式: ε = (1+w)·ε_cond - w·ε_uncond。
    典型范围: 2.0~5.0。w 越大，生成结果越强地遵循条件约束。"""

    # === 性能优化 ===
    use_score_cache: bool = True
    """是否启用 Score Table 预计算缓存。启用后，在常见条件组合下
    的 score 输出会被缓存，命中时延迟降至 ~10ms。"""

    score_cache_size: int = 10000
    """Score Cache 最大条目数。达到上限后按 LRU 策略淘汰。"""

    batch_size: int = 32
    """批量推理大小。同时处理多只股票或多种条件的去噪步骤。
    batch=32 时的总延迟仅比 batch=1 增加约 2~3 倍。"""

    # === 先验与退化 ===
    prior_type: str = "uniform"
    """先验分布类型。当扩散推理失败时，退化为该先验分布。
    当前仅支持 "uniform"（均匀分布 - 最大熵先验）。"""

    latent_dim: int = 32
    """潜在空间维度，与 HPC-Loop (DreamerV3 RSSM) 的隐状态维度一致。
    决定了扩散模型输入/输出的特征维度。"""

    diffusion_steps_T: int = 1000
    """完整扩散步数 T (训练时使用)。DDIM 采样时从这 T 步中
    均匀子采样 num_timesteps 步。"""

    # === 质量保障 ===
    n_uncertainty_samples: int = 16
    """不确定性量化时的采样次数。每次使用不同随机种子执行 DDIM 采样，
    通过 K 个样本的方差估计预测不确定性。"""

    # === 内部缓存: 预计算 beta/alpha 序列 ===
    _betas: np.ndarray | None = field(default=None, repr=False)
    _alphas: np.ndarray | None = field(default=None, repr=False)
    _alphas_cumprod: np.ndarray | None = field(default=None, repr=False)
    _alphas_cumprod_prev: np.ndarray | None = field(default=None, repr=False)
    _sqrt_alphas_cumprod: np.ndarray | None = field(default=None, repr=False)
    _sqrt_one_minus_alphas_cumprod: np.ndarray | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """初始化后自动预计算噪声调度相关序列"""
        self._compute_beta_schedule()

    # ------------------------------------------------------------------
    # 噪声调度
    # ------------------------------------------------------------------

    def _compute_beta_schedule(self) -> None:
        """根据 beta_schedule 类型计算 β_t 序列

        支持三种调度:
            - linear:  β_t 从 beta_start 到 beta_end 线性增长
            - cosine:  β_t = clip(1 - α_t / α_{t-1}), 其中 α_t = cos²((t/T + s)/(1+s) · π/2)
            - sigmoid: β_t = sigmoid(t 归一化后映射到 [beta_start, beta_end])
        """
        T = self.diffusion_steps_T
        start = self.beta_start
        end = self.beta_end

        if self.beta_schedule == "linear":
            # DDPM 标准线性调度
            betas = np.linspace(start, end, T, dtype=np.float64)

        elif self.beta_schedule == "cosine":
            # Cosine 调度: SNR 更均匀分布
            steps = np.arange(T + 1, dtype=np.float64)
            s = 0.008  # 偏移量防止 β 过小
            alphas_bar = np.cos(((steps / T) + s) / (1.0 + s) * math.pi / 2.0) ** 2
            alphas_bar = alphas_bar / alphas_bar[0]
            betas = np.clip(1.0 - alphas_bar[1:] / alphas_bar[:-1], 0.0, 0.999)

        elif self.beta_schedule == "sigmoid":
            # Sigmoid 调度: 中间步变化更陡
            ramp = np.linspace(0, 1, T)
            betas = start + (end - start) * 1.0 / (1.0 + np.exp(-10.0 * (ramp - 0.5)))

        else:
            raise ValueError(f"未知 beta_schedule 类型: '{self.beta_schedule}'. 可选: 'linear', 'cosine', 'sigmoid'")

        # 缓存为 NumPy 数组
        self._betas = betas

        # 计算派生序列: α_t = 1 - β_t
        alphas = 1.0 - betas
        self._alphas = alphas

        # 计算累积乘积: ᾱ_t = ∏_{s=1}^{t} α_s
        alphas_cumprod = np.cumprod(alphas)
        self._alphas_cumprod = alphas_cumprod

        # ᾱ_{t-1} (对于 t=0 特殊处理为 1.0)
        alphas_cumprod_prev = np.concatenate([np.ones(1, dtype=np.float64), alphas_cumprod[:-1]])
        self._alphas_cumprod_prev = alphas_cumprod_prev

        # √ᾱ_t
        self._sqrt_alphas_cumprod = np.sqrt(alphas_cumprod)

        # √(1 - ᾱ_t)
        self._sqrt_one_minus_alphas_cumprod = np.sqrt(1.0 - alphas_cumprod)

    # ------------------------------------------------------------------
    # 属性访问器 (直接返回缓存的 NumPy 数组)
    # ------------------------------------------------------------------

    @property
    def betas(self) -> np.ndarray:
        """β_t 序列, shape (T,)"""
        # 防御性拷贝以防止外部修改
        return self._betas.copy()

    @property
    def alphas(self) -> np.ndarray:
        """α_t = 1 - β_t, shape (T,)"""
        return self._alphas.copy()

    @property
    def alphas_cumprod(self) -> np.ndarray:
        """ᾱ_t = ∏ α_s, shape (T,)"""
        return self._alphas_cumprod.copy()

    @property
    def alphas_cumprod_prev(self) -> np.ndarray:
        """ᾱ_{t-1}, shape (T,)"""
        return self._alphas_cumprod_prev.copy()

    @property
    def sqrt_alphas_cumprod(self) -> np.ndarray:
        """√ᾱ_t, shape (T,)"""
        return self._sqrt_alphas_cumprod.copy()

    @property
    def sqrt_one_minus_alphas_cumprod(self) -> np.ndarray:
        """√(1 - ᾱ_t), shape (T,)"""
        return self._sqrt_one_minus_alphas_cumprod.copy()

    # ------------------------------------------------------------------
    # 采样时间步选择
    # ------------------------------------------------------------------

    def get_sampling_timesteps(self) -> np.ndarray:
        """生成 DDIM 采样所用的时间步子序列

        从完整 T 步中均匀采样 K = num_timesteps 步，
        返回从 T 到 1 的降序序列，用于迭代去噪。

        Returns:
            np.ndarray: shape (K,) 降序时间步索引 (1-indexed)
        """
        T = self.diffusion_steps_T
        K = self.num_timesteps
        # 均匀子采样，从 T 步中取 K 步
        indices = np.linspace(T, 1, K, dtype=np.int32)
        return indices

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def get_snr(self, t: int) -> float:
        """计算时间步 t 的信噪比 SNR = ᾱ_t / (1 - ᾱ_t)

        Args:
            t: 扩散时间步 (1-indexed)

        Returns:
            float: 信噪比 (SNR)
        """
        idx = t - 1  # 转换为 0-indexed
        ac = self._alphas_cumprod[idx]
        return float(ac / max(1.0 - ac, 1e-10))

    def __repr__(self) -> str:
        return (
            f"DiffusionConfig(T={self.diffusion_steps_T}, K={self.num_timesteps}, "
            f"schedule='{self.beta_schedule}', hidden_dim={self.hidden_dim}, "
            f"cfg_scale={self.cfg_scale}, "
            f"use_cache={self.use_score_cache})"
        )
