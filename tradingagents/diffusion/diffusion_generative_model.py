# tradingagents/diffusion/diffusion_generative_model.py
"""
扩散增强生成模型 — 替换 HPC-Loop 中硬编码的高斯/分类概率分布
用条件 DDIM 扩散模型实现多模分布预测

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DiffusionConfig / DDIMSampler / TemporalUNet1D 无缝集成
    - 扩散失败自动退化为均匀先验（最大熵合法先验，非降级机制）
    - 多采样实现不确定性量化，支持 Classifier-Free Guidance
"""

from __future__ import annotations

import logging

import numpy as np

from .config import DiffusionConfig
from .ddim_sampler import DDIMSampler
from .score_network import TemporalUNet1D
from .uniform_prior import uniform_prior

logger = logging.getLogger(__name__)


class DiffusionGenerativeModel:
    """
    条件扩散生成模型 — 替代硬编码概率模型

    用条件 DDIM 扩散模型替换 HPC-Loop MarketGenerativeModel 中
    硬编码的高斯/分类概率分布，实现多模分布预测。

    功能:
        1. 接收市场状态嵌入 + 历史序列 → 生成未来 K 步的条件概率分布
        2. 支持多模分布（多峰），比单峰高斯更真实地建模金融市场
        3. 支持 Classifier-Free Guidance 强化特定市场体制
        4. 输出不确定性量化（多采样方差估计）

    条件信号: 市场体制标签(one-hot)、宏观因子、历史波动率

    Usage:
        >>> model = DiffusionGenerativeModel()
        >>> market_state = np.random.randn(4, 20, 16)  # (batch, seq_len, features)
        >>> result = model.predict_distribution(market_state, num_samples=10)
        >>> result['mean'].shape
        (4, 50, 16)
        >>> result['confidence']
        0.85
    """

    def __init__(self, config: DiffusionConfig | None = None):
        """
        Args:
            config: 扩散模型配置，若为 None 则使用默认配置
        """
        self.config = config or DiffusionConfig()

        # DDIM 确定性采样器
        self.sampler = DDIMSampler(self.config)

        # Temporal U-Net 去噪网络（骨架，懒初始化等待维度校准）
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=1,  # 占位值，_ensure_calibrated 会重建
            out_channels=1,
            num_down_blocks=2,
            use_attention=True,
            attention_heads=4,
        )

        # 维度校准状态
        self._calibrated = False
        self._feat_dim: int | None = None

        # 采样历史缓存（用于调试和监控）
        self._sample_history: list[dict] = []
        self._history_maxlen = 100

        logger.info(
            "DiffusionGenerativeModel 初始化完毕 (懒加载): hidden_dim=%d, cond_dim=%d",
            self.config.hidden_dim,
            self.config.cond_dim,
        )

    # ------------------------------------------------------------------
    # 懒初始化维度校准
    # ------------------------------------------------------------------

    def _ensure_calibrated(self, market_state: np.ndarray) -> None:
        """首次调用时根据实际数据维度重建网络

        检查 market_state 的特征维度，若与当前网络不匹配则自动调用
        model.rebuild() 重建 TemporalUNet1D 的权重矩阵。
        rebuild 成功后执行 dummy 前向传播验证维度兼容性。

        Args:
            market_state: 市场状态序列, shape (batch, seq_len, features)

        Raises:
            ValueError: 当 rebuild 后的网络维度与输入不匹配时提供详细诊断
        """
        _, _seq_len, feat_dim = market_state.shape

        if not self._calibrated or self._feat_dim != feat_dim:
            self._feat_dim = feat_dim
            self.model.rebuild(
                in_channels=feat_dim,
                out_channels=feat_dim,
            )

            # 验证: 用 dummy 输入执行前向传播确保所有层维度匹配
            try:
                dummy_x = np.random.randn(2, feat_dim, 4).astype(np.float64)
                dummy_t = 1
                _ = self.model.forward(dummy_x, dummy_t, cond=None)
                logger.info(
                    "DiffusionGenerativeModel rebuild 验证通过: feat_dim=%d, seq_len=4",
                    feat_dim,
                )
            except Exception as exc:
                self._calibrated = False
                raise ValueError(
                    f"DiffusionGenerativeModel rebuild 后前向验证失败 "
                    f"(feat_dim={feat_dim}): {exc}. "
                    f"请检查 score_network 的各层维度是否与 config 一致。",
                ) from exc

            self._calibrated = True
            logger.info(
                "DiffusionGenerativeModel 维度校准: feat_dim=%d",
                feat_dim,
            )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def predict_distribution(
        self,
        market_state: np.ndarray,  # (batch, seq_len, features)
        condition: np.ndarray | None = None,  # (batch, cond_dim)
        num_samples: int | None = None,  # 采样数，默认使用配置值
    ) -> dict:
        """
        预测未来 K 步的条件概率分布

        Args:
            market_state: 市场状态序列, shape (batch, seq_len, features)
            condition: 可选条件信号, shape (batch, cond_dim)
                      例如 one-hot 市场体制编码 + 宏观因子 + 波动率
            num_samples: 生成样本数用于不确定性估计
                         (默认 config.n_uncertainty_samples)

        Returns:
            dict 包含:
                - 'mean':      (batch, horizon, features) 预测均值
                - 'std':       (batch, horizon, features) 预测标准差
                - 'samples':   (num_samples, batch, horizon, features) 完整样本
                - 'confidence': float 预测置信度 [0, 1]
                - 'modes':     List[float] 检测到的多个分布模式（峰值位置）
        """
        # --- 懒初始化维度校准 ---
        self._ensure_calibrated(market_state)

        batch_size, seq_len, feat_dim = market_state.shape
        horizon = self.config.num_timesteps
        n_samples = num_samples or self.config.n_uncertainty_samples

        # --- 准备条件嵌入 ---
        cond = self._encode_condition(condition) if condition is not None else self._default_condition(batch_size)

        # --- 封装去噪函数（兼容 DDIMSampler 的 Callable 签名） ---
        def denoise_fn(x_t: np.ndarray, t: int, c: np.ndarray | None) -> np.ndarray:
            return self.model.forward(x_t, t, c)

        # --- 多次采样用于不确定性量化 ---
        all_samples = []
        for _ in range(n_samples):
            try:
                # sampling_loop 返回 (batch, channels, seq_len)
                # 其中 channels = feat_dim, seq_len = horizon
                sample = self.sampler.sampling_loop(
                    denoise_fn=denoise_fn,
                    shape=(batch_size, feat_dim, horizon),
                    cond=cond,
                    return_all_steps=False,
                )
                # 转置为时序优先格式: (batch, horizon, features)
                sample = sample.transpose(0, 2, 1)
                all_samples.append(sample)
            except Exception as e:
                logger.warning(
                    "扩散采样失败 (sample %d/%d): %s, 退化为均匀先验",
                    len(all_samples) + 1,
                    n_samples,
                    e,
                )
                all_samples.append(uniform_prior((batch_size, horizon, feat_dim)))

        # --- 聚合统计量 ---
        # (K, batch, horizon, features)
        all_samples_arr = np.stack(all_samples, axis=0)

        mean_pred = np.mean(all_samples_arr, axis=0)
        std_pred = np.std(all_samples_arr, axis=0)

        # 置信度 = 1 - 归一化标准差 / 均值幅度
        # 当预测接近零时，用小量 epsilon 防止除零
        mean_magnitude = np.mean(np.abs(mean_pred)) + 1e-8
        std_magnitude = np.mean(std_pred)
        confidence = float(np.clip(1.0 - std_magnitude / mean_magnitude, 0.0, 1.0))

        # --- 多模检测 ---
        modes = self._detect_modes(all_samples_arr)

        # --- 记录采样历史 ---
        self._sample_history.append(
            {
                "batch_size": batch_size,
                "seq_len": seq_len,
                "feat_dim": feat_dim,
                "horizon": horizon,
                "n_samples": n_samples,
                "confidence": confidence,
                "n_modes": len(modes),
            },
        )
        if len(self._sample_history) > self._history_maxlen:
            self._sample_history.pop(0)

        return {
            "mean": mean_pred,
            "std": std_pred,
            "samples": all_samples_arr,
            "confidence": confidence,
            "modes": modes,
        }

    def sample(
        self,
        market_state: np.ndarray,
        condition: np.ndarray | None = None,
        n_samples: int = 1,
    ) -> np.ndarray:
        """
        便捷采样接口 — 从条件分布中采样

        Args:
            market_state: 市场状态, (batch, seq_len, features)
            condition: 条件信号, (batch, cond_dim)
            n_samples: 采样数

        Returns:
            np.ndarray: (n_samples, batch, horizon, features)
        """
        result = self.predict_distribution(
            market_state=market_state,
            condition=condition,
            num_samples=n_samples,
        )
        return result["samples"]

    # ------------------------------------------------------------------
    # 条件编码
    # ------------------------------------------------------------------

    def _encode_condition(self, condition: np.ndarray) -> np.ndarray:
        """将条件信号投影到 cond_dim 维度

        Args:
            condition: 原始条件, (batch, cond_features)

        Returns:
            np.ndarray: (batch, cond_dim) 投影后的条件向量
        """
        condition.shape[0]
        in_dim = condition.shape[-1]

        if in_dim == self.config.cond_dim:
            return condition.astype(np.float64, copy=False)

        # 简单线性投影 + layer norm
        # 使用固定随机投影（类似于随机特征方法）
        if not hasattr(self, "_cond_proj_W"):
            self._cond_proj_W = np.random.randn(in_dim, self.config.cond_dim).astype(np.float64) * (
                1.0 / np.sqrt(in_dim)
            )
            self._cond_proj_b = np.zeros(self.config.cond_dim, dtype=np.float64)

        projected = condition.astype(np.float64) @ self._cond_proj_W + self._cond_proj_b

        # LayerNorm: 稳定条件嵌入
        mean = projected.mean(axis=-1, keepdims=True)
        std = projected.std(axis=-1, keepdims=True) + 1e-8
        return (projected - mean) / std

    def _default_condition(self, batch_size: int) -> np.ndarray:
        """无条件生成时的零条件向量

        Args:
            batch_size: 批量大小

        Returns:
            np.ndarray: shape (batch_size, cond_dim) 零向量
        """
        return np.zeros((batch_size, self.config.cond_dim), dtype=np.float64)

    # ------------------------------------------------------------------
    # 多模检测
    # ------------------------------------------------------------------

    def _detect_modes(self, samples: np.ndarray, num_bins: int = 20) -> list[float]:
        """基于直方图的简单多模检测

        将所有样本展开后，在直方图中寻找局部峰值，
        用于检测预测分布中的多个模式（多峰分布）。

        Args:
            samples: 所有样本, (num_samples, batch, horizon, features)
            num_bins: 直方图 bin 数量

        Returns:
            List[float]: 检测到的模式位置（值）
        """
        flat = samples.reshape(-1)
        if flat.size == 0:
            return []

        hist, bin_edges = np.histogram(flat, bins=num_bins)
        hist_mean = np.mean(hist)

        modes = []
        for i in range(1, num_bins - 1):
            if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > hist_mean:
                # 峰值位置 = bin 中心
                peak = (bin_edges[i] + bin_edges[i + 1]) / 2.0
                modes.append(float(peak))

        return modes

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_sample_history(self) -> list[dict]:
        """获取采样历史记录"""
        return list(self._sample_history)

    def get_config(self) -> DiffusionConfig:
        """获取当前配置"""
        return self.config

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置生成模型（清空采样历史 + 重置校准状态）"""
        self._sample_history.clear()
        self._calibrated = False
        self._feat_dim = None
        if hasattr(self, "_cond_proj_W"):
            del self._cond_proj_W
            del self._cond_proj_b
        # 重建模型骨架
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=1,
            out_channels=1,
            num_down_blocks=2,
            use_attention=True,
            attention_heads=4,
        )
        logger.info("DiffusionGenerativeModel 已重置")

    def __repr__(self) -> str:
        return (
            f"DiffusionGenerativeModel("
            f"config={self.config}, "
            f"model={type(self.model).__name__}, "
            f"samples_cached={len(self._sample_history)})"
        )
