# tradingagents/diffusion/diffusion_imputer.py
"""
CSDI 时序数据补全 — 条件 Score-based Diffusion 插补
处理停牌日、财报空窗期、非交易日的数据缺失

核心思想:
    - 观测掩码 M: 0=缺失, 1=已观测
    - 条件去噪: ε_θ([x_t; M], t) 通过 mask 通道条件化
    - 观测值重注入: 每步 DDIM 更新后，观测位置替换为当前步含噪观测值
      (与 CSDI 论文一致，确保观测值始终处于正确的噪声水平)
    - 插补输出: 从纯噪声开始，沿 DDIM 轨迹逐步去噪

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DiffusionConfig / DDIMSampler / TemporalUNet1D 无缝集成
    - 自动掩码构建: 从 NaN 自动推断观测/缺失位置
    - 不确定性量化: 通过多次采样估计缺失位置的插补方差

References:
    - CSDI: Conditional Score-based Diffusion Models for Probabilistic Time Series
      Imputation (Tashiro et al., NeurIPS 2021)
"""

from __future__ import annotations

import logging

import numpy as np

from .config import DiffusionConfig
from .score_network import TemporalUNet1D
from .uniform_prior import uniform_prior

logger = logging.getLogger(__name__)


# ==================================================================
# CSDI 时序插补器
# ==================================================================


class CSDIImputer:
    """条件 Score-based Diffusion 时序插补器

    对金融时序中的缺失数据（停牌日、财报空窗期、非交易日）进行概率插补。
    使用 Mask 通道将观测信息注入扩散过程，通过观测值重注入确保
    观测位置保持不变，缺失位置由扩散模型生成合理值。

    Usage:
        >>> imputer = CSDIImputer()
        >>> data = np.random.randn(4, 128, 16)   # (batch, seq, feat)
        >>> data[0, 50:70] = np.nan               # 引入缺失
        >>> result = imputer.impute(data)
        >>> result['imputed'].shape
        (4, 128, 16)
        >>> np.isnan(result['imputed']).any()
        False

    Args:
        config: 扩散模型配置；若为 None 使用默认配置
        feat_dim: 特征维度 (默认 16)，在首次 impute 调用时可动态适配
    """

    def __init__(
        self,
        config: DiffusionConfig | None = None,
        feat_dim: int = 16,
    ):
        self.config = config or DiffusionConfig()
        self._feat_dim = feat_dim

        # 模型: in_channels = feat_dim + 1 (原始特征 + mask 通道)
        # out_channels = feat_dim (仅输出特征部分的噪声预测)
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=feat_dim + 1,
            out_channels=feat_dim,
        )

        logger.info(
            "CSDIImputer 初始化完毕: feat_dim=%d, in_channels=%d, num_timesteps=%d",
            feat_dim,
            feat_dim + 1,
            self.config.num_timesteps,
        )

    # ------------------------------------------------------------------
    # 主插补接口
    # ------------------------------------------------------------------

    def impute(
        self,
        observed: np.ndarray,
        mask: np.ndarray | None = None,
        return_uncertainty: bool = True,
    ) -> dict[str, np.ndarray]:
        """填补时序中的缺失值

        流程:
            1. 自动构建观测掩码 (从 NaN 推断)
            2. 观测值 NaN → 0 填充 (扩散过程会修复)
            3. CSDI 条件采样循环 (含观测值重注入)
            4. 观测位置保留原值，仅填补缺失位置
            5. 可选: 多次采样估计逐点不确定性

        Args:
            observed: 含 NaN 的观测数据, shape (batch, seq_len, features)
            mask: 观测掩码, shape (batch, seq_len, 1)
                  0=缺失, 1=已观测；若为 None 自动从 NaN 构建
            return_uncertainty: 是否返回不确定性估计 (默认 True)

        Returns:
            dict 包含:
                - 'imputed': (batch, seq_len, features) 填补后的完整序列
                - 'uncertainty': (batch, seq_len, features) 逐点不确定性
                      观测位置为 0，缺失位置为多次采样的标准差
                - 'mask': 使用的观测掩码
        """
        batch_size, seq_len, feat_dim = observed.shape

        # --- 动态适配特征维度 (首次调用或维度变化时) ---
        if feat_dim != self._feat_dim:
            self._feat_dim = feat_dim
            self.model = TemporalUNet1D(
                config=self.config,
                in_channels=feat_dim + 1,
                out_channels=feat_dim,
            )
            logger.info("CSDIImputer 适配 feat_dim=%d", feat_dim)

        # --- 自动构建掩码 ---
        if mask is None:
            # 特征维度的任意一个通道为 NaN 即视为缺失
            mask = (~np.isnan(observed)).astype(np.float64).mean(axis=-1, keepdims=True)
        mask = np.clip(mask, 0.0, 1.0)

        # === 观测值 NaN → 0 ===
        # 扩散过程会修复 NaN 位置；观测位置在重注入时恢复
        observed_filled = np.nan_to_num(observed, nan=0.0)

        # 转换为 channels-first: (batch, channels, seq_len)
        observed_t = observed_filled.transpose(0, 2, 1)  # (batch, feat, seq)
        mask_t = mask.transpose(0, 2, 1)  # (batch, 1, seq)

        # --- CSDI 条件采样 ---
        try:
            imputed_t = self._csdi_sampling_loop(
                observed_t=observed_t,
                mask_t=mask_t,
                batch_size=batch_size,
                feat_dim=feat_dim,
                seq_len=seq_len,
            )
        except Exception as exc:
            logger.warning(
                "CSDI 采样失败 (shape=%s): %s, 退化为均匀先验",
                (batch_size, seq_len, feat_dim),
                exc,
            )
            imputed_t = uniform_prior((batch_size, feat_dim, seq_len))

        # 转换回 (batch, seq_len, features)
        imputed = imputed_t.transpose(0, 2, 1)

        # --- 观测位置保留原值 ---
        result = mask * observed_filled + (1.0 - mask) * imputed

        # --- 不确定性估计 ---
        uncertainty = np.zeros_like(result)
        if return_uncertainty:
            uncertainty = self._estimate_uncertainty(
                observed_t=observed_t,
                mask_t=mask_t,
                mask=mask,
                batch_size=batch_size,
                feat_dim=feat_dim,
                seq_len=seq_len,
            )

        return {
            "imputed": result,
            "uncertainty": uncertainty,
            "mask": mask,
        }

    # ------------------------------------------------------------------
    # CSDI 条件采样循环
    # ------------------------------------------------------------------

    def _csdi_sampling_loop(
        self,
        observed_t: np.ndarray,
        mask_t: np.ndarray,
        batch_size: int,
        feat_dim: int,
        seq_len: int,
    ) -> np.ndarray:
        """CSDI 条件采样循环 (含观测值重注入)

        与标准 DDIM 的区别:
            - 模型输入为 [x_t; mask] 拼接 (mask 通道告知观测位置)
            - 每步 DDIM 更新后，观测位置被替换为当前步的含噪观测值
            - 确保观测值始终处于正确的噪声水平，供下一步条件化

        Args:
            observed_t: 观测值 (channels-first), (batch, feat, seq)
            mask_t: 观测掩码 (channels-first), (batch, 1, seq)
            batch_size: 批量大小
            feat_dim: 特征维度
            seq_len: 序列长度

        Returns:
            np.ndarray: 插补结果, (batch, feat, seq)
        """
        # 采样时间步 (降序)
        timesteps = self.config.get_sampling_timesteps()
        K = len(timesteps)

        # 噪声调度序列 (使用内部缓存避免属性拷贝开销)
        ac = self.config._alphas_cumprod  # (T,)
        # ac_prev = self.config._alphas_cumprod_prev  # (T,)

        # 从纯噪声开始
        x = np.random.randn(batch_size, feat_dim, seq_len).astype(np.float64)

        # 缓存随机噪声用于观测值重注入 (避免每次重新生成)
        eps_obs = np.random.randn(K, batch_size, feat_dim, seq_len).astype(np.float64)

        for i in range(K - 1):
            t = int(timesteps[i])
            t_next = int(timesteps[i + 1])

            # 确保严格降序
            if t_next >= t:
                continue

            # ============================================================
            # 1. 模型前向: 预测噪声 ε_θ([x_t; mask], t)
            # ============================================================
            model_in = np.concatenate([x, mask_t], axis=1)  # (batch, feat+1, seq)
            # cond=None 表示不使用 FiLM 条件调制 (纯无条件 CSDI)
            eps_pred = self.model.forward(model_in, t, cond=None)

            # ============================================================
            # 2. DDIM 更新: x_t → x_{t_next}
            # ============================================================
            ac_t = ac[t - 1]
            ac_next_val = ac[t_next - 1] if t_next > 0 else 1.0

            sqrt_ac_t = np.sqrt(ac_t)
            sqrt_one_minus_ac_t = np.sqrt(np.clip(1.0 - ac_t, 1e-10, 1.0))

            # 预测 x̂_0 (干净数据)
            x0_pred = (x - sqrt_one_minus_ac_t * eps_pred) / sqrt_ac_t
            x0_pred = np.clip(x0_pred, -1.0, 1.0)

            # DDIM 确定性更新 (η=0)
            sqrt_ac_next = np.sqrt(ac_next_val)
            dir_coeff = np.sqrt(np.clip(1.0 - ac_next_val, 1e-10, 1.0))

            x_next = sqrt_ac_next * x0_pred + dir_coeff * eps_pred

            # ============================================================
            # 3. 观测值重注入: 观测位置替换为含噪观测值
            # ============================================================
            # z_{t_next} = √(ᾱ_{t_next}) · x_obs + √(1 - ᾱ_{t_next}) · ε
            z_next = sqrt_ac_next * observed_t + np.sqrt(np.clip(1.0 - ac_next_val, 1e-10, 1.0)) * eps_obs[i]

            # 重注入: 观测位置 ← 含噪观测值, 缺失位置 ← DDIM 输出
            x_next = mask_t * z_next + (1.0 - mask_t) * x_next

            x = x_next

        return x

    # ------------------------------------------------------------------
    # 不确定性量化
    # ------------------------------------------------------------------

    def _estimate_uncertainty(
        self,
        observed_t: np.ndarray,
        mask_t: np.ndarray,
        mask: np.ndarray,
        batch_size: int,
        feat_dim: int,
        seq_len: int,
    ) -> np.ndarray:
        """通过多次 CSDI 采样估计缺失位置的不确定性

        仅在 mask 中存在缺失位置时执行多次采样；若全观测，
        直接返回全零不确定性矩阵。

        Returns:
            np.ndarray: (batch, seq, feat) 逐点不确定性
                观测位置为 0，缺失位置为样本标准差
        """
        # 检查是否存在缺失位置
        missing_mask = (1.0 - mask).squeeze(-1) > 0.5
        if not missing_mask.any():
            return np.zeros((batch_size, seq_len, feat_dim), dtype=np.float64)

        n_samples = self.config.n_uncertainty_samples
        samples = []

        for _ in range(n_samples):
            s = self._csdi_sampling_loop(
                observed_t=observed_t,
                mask_t=mask_t,
                batch_size=batch_size,
                feat_dim=feat_dim,
                seq_len=seq_len,
            )
            # (batch, feat, seq) → (batch, seq, feat)
            samples.append(s.transpose(0, 2, 1))

        samples_arr = np.stack(samples, axis=0)  # (n, batch, seq, feat)
        uncertainty = samples_arr.std(axis=0)  # (batch, seq, feat)

        # 仅缺失位置有不确定性
        uncertainty = uncertainty * (1.0 - mask.squeeze(-1)[..., np.newaxis])

        return uncertainty

    # ------------------------------------------------------------------
    # 批量插补
    # ------------------------------------------------------------------

    def batch_impute(
        self,
        stocks_data: list[np.ndarray],
        masks: list[np.ndarray] | None = None,
    ) -> list[np.ndarray]:
        """批量填补多只股票的缺失值

        处理不同长度的股票序列:
            - 按最长序列 pad 对齐
            - 每只股票保持独立掩码
            - 向量化推理 (单次 impute 调用)

        Args:
            stocks_data: 股票数据列表，每项 shape (seq_len_i, features)
            masks: 掩码列表，每项 shape (seq_len_i, 1) 或 None
                   若为 None 自动从 NaN 构建

        Returns:
            List[np.ndarray]: 填补后的股票序列列表，每项 shape (seq_len_i, features)
        """
        if masks is None:
            masks = [(~np.isnan(d)).astype(np.float64).mean(axis=-1, keepdims=True) for d in stocks_data]

        batch_size = len(stocks_data)
        max_len = max(d.shape[0] for d in stocks_data)
        feat_dim = stocks_data[0].shape[1]

        # 对齐到相同长度 (pad 尾部)
        aligned = np.zeros((batch_size, max_len, feat_dim), dtype=np.float64)
        aligned_mask = np.zeros((batch_size, max_len, 1), dtype=np.float64)

        for i, (data, m) in enumerate(zip(stocks_data, masks, strict=False)):
            n = data.shape[0]
            aligned[i, :n] = np.nan_to_num(data, nan=0.0)
            aligned_mask[i, :n] = m[:n]

        # 单次向量化插补
        result = self.impute(aligned, aligned_mask, return_uncertainty=False)

        # 按原始长度切分
        output: list[np.ndarray] = []
        for i, d in enumerate(stocks_data):
            n = d.shape[0]
            output.append(result["imputed"][i, :n].copy())

        return output

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置模型权重 (重新初始化)"""
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=self._feat_dim + 1,
            out_channels=self._feat_dim,
        )
        logger.info("CSDIImputer 模型权重已重置")

    def __repr__(self) -> str:
        return f"CSDIImputer(feat_dim={self._feat_dim}, config={self.config})"
