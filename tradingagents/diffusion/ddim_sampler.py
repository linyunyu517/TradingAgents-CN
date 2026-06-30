# tradingagents/diffusion/ddim_sampler.py
"""
DDIM (Denoising Diffusion Implicit Models) 确定性采样器

实现 DDIM 论文 (Song et al. 2022) 中的确定性采样过程，
支持 Classifier-Free Guidance (CFG) 条件控制。

核心公式:
    x_{t-1} = √(ᾱ_{t-1}) · x̂_0 + √(1 - ᾱ_{t-1} - σ²_t) · ε_θ + σ_t · z

    其中:
        x̂_0 = (x_t - √(1 - ᾱ_t) · ε_θ) / √ᾱ_t      (预测的干净数据)
        σ_t = η · √((1 - ᾱ_{t-1}) / (1 - ᾱ_t)) · √(1 - ᾱ_t / ᾱ_{t-1})
        η=0 → 完全确定性 (DDIM)

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 向量化批量处理，支持 batch 维度
    - CFG 通过 score 插值实现，无需额外分类器
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from .config import DiffusionConfig

# ------------------------------------------------------------------
# 核心 DDIM 采样函数
# ------------------------------------------------------------------


def ddim_step(
    model_denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
    x_t: np.ndarray,
    t: int,
    t_next: int,
    alphas_cumprod: np.ndarray,
    alphas_cumprod_prev: np.ndarray,
    cond: np.ndarray | None = None,
    cfg_scale: float = 0.0,
    eta: float = 0.0,
) -> np.ndarray:
    """执行单步 DDIM 去噪更新

    Args:
        model_denoise_fn: 去噪函数 fn(x_t, t, cond) -> ε_θ
            x_t: shape (..., *data_dim) 当前噪声数据
            t: int 当前时间步
            cond: Optional[np.ndarray] 条件向量
            returns: ε_θ shape 与 x_t 相同
        x_t: 当前时间步的噪声数据, shape (batch, *data_dim)
        t: 当前时间步 (1-indexed)
        t_next: 下一时间步 (1-indexed, t_next < t)
        alphas_cumprod: ᾱ_t 序列, shape (T,)
        alphas_cumprod_prev: ᾱ_{t-1} 序列, shape (T,)
        cond: 条件向量, shape (batch, cond_dim) 或 None
        cfg_scale: CFG 引导强度。0=无条件, >0 启用 CFG
        eta: 随机性参数。0=完全确定性 DDIM, >0 添加随机噪声

    Returns:
        np.ndarray: x_{t-1}, shape 与 x_t 相同
    """
    # 1. 获取当前步的噪声调度值
    ac = alphas_cumprod[t - 1]  # ᾱ_t
    ac_next = alphas_cumprod_prev[t - 1]  # ᾱ_{t-1} (注意 t 是 1-indexed)

    # 2. 模型预测噪声 ε_θ(x_t, t, cond)
    if cfg_scale > 0.0 and cond is not None:
        # Classifier-Free Guidance: 插值条件/无条件预测
        eps_cond = model_denoise_fn(x_t, t, cond)  # 条件预测
        eps_uncond = model_denoise_fn(x_t, t, None)  # 无条件预测
        eps = (1.0 + cfg_scale) * eps_cond - cfg_scale * eps_uncond
    else:
        eps = model_denoise_fn(x_t, t, cond)

    # 3. 预测 x̂_0 (原始数据)
    # x̂_0 = (x_t - √(1 - ᾱ_t) · ε_θ) / √ᾱ_t
    sqrt_ac = np.sqrt(ac)
    sqrt_one_minus_ac = np.sqrt(np.clip(1.0 - ac, 1e-10, 1.0))
    x0_pred = (x_t - sqrt_one_minus_ac * eps) / sqrt_ac

    # 4. 裁剪 x̂_0 到有效范围 [-1, 1] (数值稳定性)
    x0_pred = np.clip(x0_pred, -1.0, 1.0)

    # 5. 计算 DDIM 更新方向
    # 方向系数: √(1 - ᾱ_{t-1} - σ²_t)
    if ac_next > 0:
        sigma = eta * math.sqrt(max((1.0 - ac_next) / (1.0 - ac), 0.0) * max((1.0 - ac / ac_next), 0.0))
    else:
        sigma = 0.0

    dir_coeff = np.sqrt(np.clip(1.0 - ac_next - sigma**2, 1e-10, 1.0))

    # 6. 组合更新
    # x_{t-1} = √(ᾱ_{t-1}) · x̂_0 + direction_coeff · ε_θ + σ · z
    sqrt_ac_next = np.sqrt(ac_next)
    x_next = sqrt_ac_next * x0_pred + dir_coeff * eps

    # 添加随机噪声 (仅当 eta > 0 时)
    if sigma > 0.0:
        z = np.random.randn(*x_t.shape).astype(x_t.dtype)
        x_next += sigma * z

    return x_next


def ddim_sampling_loop(
    model_denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
    shape: tuple[int, ...],
    config: DiffusionConfig,
    cond: np.ndarray | None = None,
    return_all_steps: bool = False,
) -> np.ndarray:
    """完整 DDIM 确定性采样循环

    从纯噪声 x_T ~ N(0, I) 开始，沿去噪轨迹迭代 K 步，
    最终生成干净样本 x_0。

    Args:
        model_denoise_fn: 去噪函数 fn(x_t, t, cond) -> ε_θ
        shape: 采样形状 (batch, *data_dim)，不含时间步
        config: 扩散模型配置
        cond: 条件向量, shape (batch, cond_dim) 或 None
        return_all_steps: 是否返回所有中间步的轨迹

    Returns:
        np.ndarray: 生成的干净样本
            - return_all_steps=False: shape (batch, *data_dim)
            - return_all_steps=True: shape (K+1, batch, *data_dim)
    """
    # 1. 获取采样时间步
    timesteps = config.get_sampling_timesteps()  # 降序, shape (K,)
    K = len(timesteps)

    # 2. 从纯噪声初始化 x_T ~ N(0, I)
    x = np.random.randn(*shape).astype(np.float64)

    # 3. 可选: 记录轨迹
    if return_all_steps:
        trajectory = [x.copy()]

    # 4. 迭代去噪
    # [优化 2026-06-22] 自适应 CFG: 前半段使用完整 CFG 引导，后半段禁用
    # 因为在去噪后期样本已接近数据流形，CFG 的引导效果边际递减
    # 这可将每一步的 model_denoise_fn 调用从 2 次减为 1 次
    cfg_scale_active = config.cfg_scale if config.use_classifier_free_guidance else 0.0
    for i in range(K - 1):
        t = timesteps[i]  # 当前时间步
        t_next = timesteps[i + 1]  # 下一时间步

        # 确保 t > t_next (降序)
        if t_next >= t:
            continue

        # 自适应 CFG: 后半程禁用（样本已接近数据流形，无需额外引导）
        current_cfg = 0.0 if config.use_classifier_free_guidance and i >= K // 2 else cfg_scale_active

        # 单步 DDIM 更新
        x = ddim_step(
            model_denoise_fn=model_denoise_fn,
            x_t=x,
            t=int(t),
            t_next=int(t_next),
            alphas_cumprod=config.alphas_cumprod,
            alphas_cumprod_prev=config.alphas_cumprod_prev,
            cond=cond,
            cfg_scale=current_cfg,
            eta=0.0,  # 完全确定性采样
        )

        if return_all_steps:
            trajectory.append(x.copy())

    # 5. 返回结果
    if return_all_steps:
        return np.stack(trajectory, axis=0)  # (K+1, batch, *data_dim)
    return x


# ------------------------------------------------------------------
# DDIMSampler 类包装
# ------------------------------------------------------------------


class DDIMSampler:
    """DDIM 确定性采样器类

    封装 `ddim_sampling_loop` 和 `ddim_step` 函数为对象接口，
    持有 DiffusionConfig 配置，提供更便捷的采样 API。

    Args:
        config: 扩散模型配置
    """

    def __init__(self, config: DiffusionConfig):
        self.config = config

    def step(
        self,
        denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
        x_t: np.ndarray,
        t: int,
        t_next: int,
        cond: np.ndarray | None = None,
        cfg_scale: float | None = None,
    ) -> np.ndarray:
        """单步 DDIM 去噪

        Args:
            denoise_fn: 去噪函数
            x_t: 当前噪声数据
            t: 当前时间步
            t_next: 下一时间步
            cond: 条件向量
            cfg_scale: CFG 引导强度 (默认使用 config.cfg_scale)

        Returns:
            np.ndarray: x_{t-1}
        """
        return ddim_step(
            model_denoise_fn=denoise_fn,
            x_t=x_t,
            t=t,
            t_next=t_next,
            alphas_cumprod=self.config.alphas_cumprod,
            alphas_cumprod_prev=self.config.alphas_cumprod_prev,
            cond=cond,
            cfg_scale=cfg_scale if cfg_scale is not None else self.config.cfg_scale,
        )

    def sampling_loop(
        self,
        denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
        shape: tuple[int, ...],
        cond: np.ndarray | None = None,
        return_all_steps: bool = False,
    ) -> np.ndarray:
        """完整 DDIM 采样循环

        Args:
            denoise_fn: 去噪函数
            shape: 采样形状 (batch, *data_dim)
            cond: 条件向量
            return_all_steps: 是否返回所有中间步

        Returns:
            np.ndarray: 生成样本
        """
        return ddim_sampling_loop(
            model_denoise_fn=denoise_fn,
            shape=shape,
            config=self.config,
            cond=cond,
            return_all_steps=return_all_steps,
        )

    def sample_with_uncertainty(
        self,
        denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
        shape: tuple[int, ...],
        cond: np.ndarray | None = None,
        n_samples: int = 16,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """带不确定性量化的多次采样"""
        return sample_with_uncertainty(
            model_denoise_fn=denoise_fn,
            shape=shape,
            config=self.config,
            cond=cond,
            n_samples=n_samples,
        )


# ------------------------------------------------------------------
# 便捷函数: 批量采样 + 不确定性量化
# ------------------------------------------------------------------


def sample_with_uncertainty(
    model_denoise_fn: Callable[[np.ndarray, int, np.ndarray | None], np.ndarray],
    shape: tuple[int, ...],
    config: DiffusionConfig,
    cond: np.ndarray | None = None,
    n_samples: int = 16,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """多次 DDIM 采样，估计均值和不确定性

    通过多次独立采样 (不同随机种子) 估算预测的均值和标准差，
    用于下游的贝叶斯融合和置信度评估。

    Args:
        model_denoise_fn: 去噪函数
        shape: 采样形状 (batch, *data_dim)
        config: 扩散模型配置
        cond: 条件向量
        n_samples: 采样次数 (默认 16)

    Returns:
        Tuple[np.ndarray, np.ndarray, np.ndarray]:
            - mean: 样本均值, shape (batch, *data_dim)
            - std: 样本标准差, shape (batch, *data_dim)
            - all_samples: 所有样本, shape (n_samples, batch, *data_dim)
    """
    samples = []
    for _ in range(n_samples):
        sample = ddim_sampling_loop(
            model_denoise_fn=model_denoise_fn,
            shape=shape,
            config=config,
            cond=cond,
            return_all_steps=False,
        )
        samples.append(sample)

    all_samples = np.stack(samples, axis=0)  # (n_samples, batch, *data_dim)
    mean = all_samples.mean(axis=0)
    std = all_samples.std(axis=0)
    return mean, std, all_samples
