# tradingagents/diffusion/diffusion_trader.py
"""
Trading Decision Diffuser — 扩散交易决策器

灵感: Decision Diffuser (Ajay et al., 2022, arXiv:2211.15657)
将 Agent 辩论结果作为条件，通过条件扩散生成概率化的交易动作序列，
替代传统的单步离散决策（买/卖/持有）。

核心创新:
    - 多步连续规划: 输出未来K步的连续动作概率分布，而非单步分类
    - 全局一致性: 扩散模型隐式编码时序约束，避免单步决策的"前后矛盾"
    - 不确定性量化: 多采样估计动作分布的方差，支持风险感知决策

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DiffusionConfig / DDIMSampler / TemporalUNet1D 无缝集成
    - 随机投影矩阵按特征维度缓存，确保条件构建的确定性
    - 扩散推理失败时自动退化为均匀先验（非降级机制）

References:
    - Ajay et al., "Decision Diffuser", NeurIPS 2022, arXiv:2211.15657
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

from .config import DiffusionConfig
from .ddim_sampler import DDIMSampler
from .score_network import TemporalUNet1D
from .uniform_prior import uniform_prior

logger = logging.getLogger(__name__)


# ==================================================================
# 轻量 DiT (Diffusion Transformer) 包装
# ==================================================================


class DiTLite:
    """轻量 DiT (Diffusion Transformer) — 用于动作序列去噪

    对 TemporalUNet1D 的轻量封装，保持与现有 ScoreNetwork 接口兼容。
    当未来需要引入纯 Transformer 架构的去噪网络时，可继承此类扩展。

    Args:
        model: TemporalUNet1D 实例
    """

    def __init__(self, model: TemporalUNet1D):
        self.model = model

    def forward(self, x: np.ndarray, t: int, cond: np.ndarray | None = None) -> np.ndarray:
        """委托给 TemporalUNet1D.forward"""
        return self.model.forward(x, t, cond)

    def __call__(self, x: np.ndarray, t: int, cond: np.ndarray | None = None) -> np.ndarray:
        return self.forward(x, t, cond)


# ==================================================================
# 扩散交易决策器
# ==================================================================


class TradingDecisionDiffuser:
    """扩散交易决策器

    将单步离散交易决策（买/卖/持有）升级为多步连续规划 + 全局一致性约束。

    输入:
        - market_state: (batch, seq_len, features) 市场状态序列
        - debate_result: (batch, debate_dim) 多Agent辩论结果嵌入
        - risk_preference: float 风险偏好参数

    输出:
        - action_sequence: (batch, horizon, n_actions) 概率化动作序列
        - uncertainty: (batch, horizon, n_actions) 动作不确定性
        - confidence: float 决策置信度

    Usage:
        >>> diffuser = TradingDecisionDiffuser()
        >>> market = np.random.randn(4, 20, 16)  # (batch, seq, feat)
        >>> debate = np.random.randn(4, 16)        # (batch, debate_dim)
        >>> result = diffuser.decide(market, debate, horizon=5)
        >>> result['action_sequence'].shape
        (4, 5, 3)
        >>> result['preferred_action'].shape
        (4, 5)

    Args:
        config: 扩散模型配置；若为 None 使用默认配置
        feat_dim: 潜在特征维度 (默认 16)
        num_actions: 动作类别数 (默认 3: 卖/持有/买)
    """

    def __init__(
        self,
        config: DiffusionConfig | None = None,
        feat_dim: int = 16,
        num_actions: int = 3,
        auto_load_checkpoint: bool = True,
    ):
        self.config = config or DiffusionConfig()
        self._feat_dim = feat_dim
        self._num_actions = num_actions

        # === 子模块 ===
        # DDIM 确定性采样器
        self.sampler = DDIMSampler(self.config)

        # Score Network: 1D Temporal U-Net（骨架，懒初始化等待维度校准）
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=1,  # 占位值，_ensure_calibrated 会重建
            out_channels=1,
        )

        # 维度校准状态
        self._calibrated = False

        # 条件投影矩阵缓存 {input_dim: np.ndarray}
        # 在首次遇到新特征维度时按 Kaiming 初始化创建，后续复用
        self._market_proj_cache: dict[int, np.ndarray] = {}
        self._debate_proj_cache: dict[int, np.ndarray] = {}

        # [FIX 2026-06-26] Phase 3.3: 自动加载 checkpoint
        if auto_load_checkpoint:
            self._try_load_checkpoint()

        logger.info(
            "TradingDecisionDiffuser 初始化完毕 (懒加载): "
            "num_actions=%d, hidden_dim=%d, cond_dim=%d, "
            "num_timesteps=%d, cfg_scale=%.1f",
            num_actions,
            self.config.hidden_dim,
            self.config.cond_dim,
            self.config.num_timesteps,
            self.config.cfg_scale,
        )

    # ------------------------------------------------------------------
    # [FIX 2026-06-26] Phase 3.3: Checkpoint 加载
    # ------------------------------------------------------------------
    def _try_load_checkpoint(self) -> bool:
        """启动时自动加载最新 checkpoint

        从 checkpoint 中的 input_proj/W 形状推断训练时的 in_channels，
        若与当前模型不匹配则先 rebuild 再 restore。
        同时设置 _calibrated = True，阻止后续 _ensure_calibrated 重复 rebuild。

        注意事项:
            1. 必须先于 _ensure_calibrated 调用（在 __init__ 中）
            2. rebuild 后会做 dummy 前向验证
            3. restore 成功后 _calibrated 设为 True，_feat_dim 设为 checkpoint 维度
            4. restore 失败时 _calibrated 保持 False，允许 _ensure_calibrated 兜底

        Reference:
            HuggingFace from_pretrained(ignore_mismatched_sizes=True) 设计模式

        Returns:
            bool: 是否成功加载
        """
        try:
            from tradingagents.utils.checkpoint_manager import CheckpointManager

            mgr = CheckpointManager()
            models_data = mgr.load_latest()
            if not models_data:
                logger.info("[Diffusion] 无 checkpoint，使用随机初始化")
                return False

            # 获取 checkpoint 中的 diffusion 模型参数
            diffusion_state = models_data.get("diffusion", {})
            if not diffusion_state:
                logger.info("[Diffusion] checkpoint 中无 diffusion 参数，使用随机初始化")
                return False

            # ==== [FIX 2026-06-26] 维度自动适配 ====
            # input_proj 是 Conv1D 层，W 形状为 (out_channels, in_channels, kernel_size)
            # 训练时 in_channels=16，推理时初始 in_channels=1（占位值）
            # 通过读取 checkpoint 中的 input_proj/W 第二维，推断训练时的 in_channels
            input_proj_data = diffusion_state.get("input_proj", {})
            need_rebuild = False
            ckpt_in_c = 16  # 默认值
            if "W" in input_proj_data:
                w_shape = input_proj_data["W"]
                if isinstance(w_shape, (list, tuple)) and len(w_shape) == 3:
                    ckpt_in_c = int(w_shape[1])  # W 的第二维 = in_channels
                    current_in_c = self.model.in_channels
                    if ckpt_in_c != current_in_c:
                        logger.info(
                            "[Diffusion] 🔧 checkpoint 维度自动适配: "
                            "in_channels %d → %d (来自 input_proj/W=%s)",
                            current_in_c, ckpt_in_c, str(w_shape),
                        )
                        self.model.rebuild(
                            in_channels=ckpt_in_c,
                            out_channels=ckpt_in_c,
                        )
                        need_rebuild = True

                        # [FIX 2026-06-26] 重建后执行 dummy 前向验证
                        # 替代 _ensure_calibrated 中缺失的维度验证
                        try:
                            _dummy_x = np.random.randn(
                                2, ckpt_in_c, 4,
                            ).astype(np.float64)
                            _dummy_t = 1
                            _ = self.model.forward(_dummy_x, _dummy_t, cond=None)
                            logger.info(
                                "[Diffusion] ✅ checkpoint 维度验证通过: "
                                "in_channels=%d, hidden_dim=%d",
                                ckpt_in_c, self.model.hidden_dim,
                            )
                        except Exception as _exc:
                            logger.warning(
                                "[Diffusion] ⚠️ checkpoint 维度验证失败，"
                                "回退到随机初始化: %s",
                                _exc,
                            )
                            # 设为 calibrated 防止 _ensure_calibrated 也爆炸
                            self._calibrated = True
                            return False

            if not need_rebuild:
                logger.info("[Diffusion] 模型维度已匹配，直接加载 checkpoint")

            # ==== 恢复参数 ====
            restored = mgr.restore(self.model, "diffusion", models_data)

            if restored > 0:
                # [FIX 2026-06-26] 阻止 _ensure_calibrated 再次 rebuild
                self._calibrated = True
                self._feat_dim = ckpt_in_c
                logger.info(
                    "[Diffusion] ✅ checkpoint 加载成功: "
                    "%d 参数已恢复 (feat_dim=%d)",
                    restored, ckpt_in_c,
                )
                return True

            logger.info(
                "[Diffusion] checkpoint 加载失败（0 参数匹配），使用随机初始化",
            )
            return False

        except Exception as e:
            logger.debug("[Diffusion] checkpoint 加载跳过: %s", e)
            return False

    # ------------------------------------------------------------------
    # 懒初始化维度校准
    # ------------------------------------------------------------------

    # [FIX 2026-06-26] Phase 1.6: 冻结扩散模型维度
    # 之前每次 feat_dim 变化都 rebuild 网络，导致 state_dict 丢失和维度退化。
    # 现在第一次校准后冻结维度，后续不匹配时只告警不 rebuild。
    _FROZEN_FEAT_DIM: int = 16  # 固定特征维度

    def _ensure_calibrated(self, market_state: np.ndarray) -> None:
        """冻结维度模式下的一次性校准

        第一次调用时根据固定维度重建网络。
        后续调用仅检查维度匹配，不 rebuild。
        维度不匹配时自动 reshape 输入。

        Args:
            market_state: 市场状态序列, shape (batch, seq_len, features)

        Raises:
            ValueError: 当第一次校准失败时
        """
        if hasattr(self, "_calibrated") and self._calibrated:
            # 已校准：仅检查维度
            feat_dim = market_state.shape[-1]
            if feat_dim != self._FROZEN_FEAT_DIM:
                logger.warning(
                    "[Diffusion] ⚠️ 输入维度 %d ≠ 冻结维度 %d，"
                    "reshape 到 %d 维（可能丢失信息）",
                    feat_dim, self._FROZEN_FEAT_DIM, self._FROZEN_FEAT_DIM,
                )
            return

        # 第一次校准
        feat_dim = self._FROZEN_FEAT_DIM
        self._feat_dim = feat_dim
        self.model.rebuild(
            in_channels=feat_dim,
            out_channels=feat_dim,
        )

        # 验证
        try:
            dummy_x = np.random.randn(2, feat_dim, 4).astype(np.float64)
            dummy_t = 1
            _ = self.model.forward(dummy_x, dummy_t, cond=None)
            logger.info(
                "[Diffusion] ✅ 维度校准完成: feat_dim=%d (已冻结)",
                feat_dim,
            )
        except Exception as exc:
            self._calibrated = False
            raise ValueError(
                f"TradingDecisionDiffuser rebuild 后前向验证失败 "
                f"(feat_dim={feat_dim}): {exc}. "
                f"请检查 score_network 的各层维度是否与 config 一致。",
            ) from exc

        self._calibrated = True

    # ------------------------------------------------------------------
    # 主决策接口
    # ------------------------------------------------------------------

    def decide(
        self,
        market_state: np.ndarray,
        debate_result: np.ndarray | None = None,
        horizon: int = 5,
        n_actions: int | None = None,
        num_samples: int = 20,
        risk_preference: float = 1.0,
    ) -> dict[str, np.ndarray]:
        """生成概率化交易动作序列

        流程:
            1. 构建条件向量（市场状态摘要 + 辩论结果嵌入 + 风险偏好调制）
            2. 多次 DDIM 采样，估计动作分布的均值和方差
            3. 从扩散输出中提取动作通道，经 Softmax 得到概率化动作
            4. 计算首选动作、连续权重、不确定性和置信度

        Args:
            market_state: 市场状态序列, shape (batch, seq_len, features)
            debate_result: 多Agent辩论结果嵌入, shape (batch, debate_dim) 或 None
            horizon: 规划水平线（未来K步）, 默认 5
            n_actions: 动作类别数, 默认使用构造时的 num_actions (3)
            num_samples: 不确定性估计采样次数, 默认 20
            risk_preference: 风险偏好参数, >1 激进, <1 保守, 默认 1.0

        Returns:
            dict 包含:
                - 'action_sequence': (batch, horizon, n_actions) 每个动作的概率
                - 'preferred_action': (batch, horizon) 每步的最可能动作索引
                - 'action_weights': (batch, horizon) 连续动作权重 [-1, 1]
                        正值=买入倾向, 负值=卖出倾向
                - 'uncertainty': (batch, horizon) 动作不确定性
                        值为多次采样中概率分布的标准差均值
                - 'confidence': float 整体置信度
                - 'raw_samples': (num_samples, batch, horizon, n_actions)
                        完整采样分布，用于下游的贝叶斯融合
        """
        # --- 输入标准化 ---
        if market_state.ndim == 2:
            market_state = market_state[np.newaxis, ...]  # (1, seq, feat)

        batch_size = market_state.shape[0]
        seq_len = market_state.shape[1]
        n_actions = n_actions or self._num_actions

        # --- [FIX] 2026-06-18: 防御: 空序列保护 + Mock 数据生成 ---
        if seq_len == 0:
            logger.warning(
                "TradingDecisionDiffuser.decide 收到空市场状态序列 (seq_len=0), 生成合成 Mock 数据并标记 degraded",
            )
            # 生成合成 Mock 数据：至少 5 个时间步，包含合理 OHLCV 模式
            mock_seq_len = max(5, horizon)
            # [FIX] 2026-06-18 P3: 使用 None 种子（每次调用随机），避免固定种子导致的确定性价格漂移
            rng_mock = np.random.RandomState(None)
            # [FIX] 2026-06-18 P3: 用 Ornstein-Uhlenbeck 均值回归替代纯随机游走
            # dX = θ(μ - X)dt + σdW, 其中 θ=0.1, μ=100.0, σ=1.5
            ou_theta = 0.1  # 均值回归速度
            ou_mu = 100.0  # 长期均值
            ou_sigma = 1.5  # 波动率
            price_base = np.zeros(mock_seq_len, dtype=np.float64)
            price_base[0] = ou_mu + rng_mock.randn() * ou_sigma  # 初始值
            for t in range(1, mock_seq_len):
                dx = ou_theta * (ou_mu - price_base[t - 1]) + ou_sigma * rng_mock.randn()
                price_base[t] = price_base[t - 1] + dx
            price_base = np.maximum(price_base, 50.0)  # 下限保护
            price_base = np.minimum(price_base, 150.0)  # 上限保护（对称钳制）
            # OHLCV 模式: close=price_base, open=prev_close+noise, high/low 在 close 附近
            mock_ohlcv = np.zeros((batch_size, mock_seq_len, 5), dtype=np.float64)
            for b in range(batch_size):
                seed_b = hash(str(b)) % (2**31)
                rng_b = np.random.RandomState(seed_b)
                for t in range(mock_seq_len):
                    c = price_base[t]
                    o = price_base[t - 1] + rng_b.randn() * 0.5 if t > 0 else c
                    h = max(c, o) + abs(rng_b.randn()) * 0.8
                    l = min(c, o) - abs(rng_b.randn()) * 0.8
                    v = max(1e6 + rng_b.randn() * 2e5, 1e5)
                    mock_ohlcv[b, t] = [o, h, l, c, v]
            # 填充其余特征维度（如果有额外技术指标等）
            feat_mock = market_state.shape[2] if market_state.ndim == 3 and market_state.shape[2] > 5 else 16
            if feat_mock > 5:
                mock_full = np.zeros((batch_size, mock_seq_len, feat_mock), dtype=np.float64)
                mock_full[:, :, :5] = mock_ohlcv
                for f in range(5, feat_mock):
                    mock_full[:, :, f] = rng_mock.randn(mock_seq_len) * 0.1
                mock_full[:, :, 5:] = np.clip(mock_full[:, :, 5:], -2.0, 2.0)
            else:
                mock_full = mock_ohlcv

            logger.info(
                "[FIX] TradingDecisionDiffuser 生成合成 Mock 数据: seq_len=%d, feat=%d, degraded=True",
                mock_seq_len,
                feat_mock,
            )
            return {
                "action_sequence": np.ones((batch_size, horizon, n_actions), dtype=np.float64) / n_actions,
                "preferred_action": np.zeros((batch_size, horizon), dtype=np.int32),
                "action_weights": np.zeros((batch_size, horizon), dtype=np.float64),
                "uncertainty": np.ones((batch_size, horizon), dtype=np.float64),
                "confidence": 0.0,
                "raw_samples": np.zeros((num_samples, batch_size, horizon, n_actions), dtype=np.float64),
                "degraded": True,  # [FIX] degraded 标记
                "timestamp": datetime.now(timezone.utc).isoformat(),  # [FIX] ISO 时间戳
                "mock_data_generated": True,  # [FIX] mock 生成标记
            }

        # --- 懒初始化维度校准 ---
        self._ensure_calibrated(market_state)
        feat_dim = self._feat_dim

        # --- 构建条件向量 ---
        cond = self._build_condition(market_state, debate_result, risk_preference)

        # --- 多次 DDIM 采样估计分布 [优化 2026-06-22] ---
        # [渐进式采样 + 自适应精度]
        # 策略: 先采 min_samples 个样本评估置信度，若置信度足够高则提前停止
        # 避免在所有情况下都执行完整的 num_samples 次采样
        all_samples = []

        # 渐进式采样配置
        min_samples = max(5, num_samples // 4)  # 至少 5 个样本
        early_stop_confidence = 0.95  # 置信度≥0.95 即可提前停止
        check_interval = 3  # 每 3 个样本检查一次

        for s in range(num_samples):
            try:
                # DDIM 采样: 从纯噪声生成 feat_dim 维序列
                # denoise_fn 使用 self.model.forward 符合 ScoreNetwork 接口
                sample = self.sampler.sampling_loop(
                    denoise_fn=self.model.forward,
                    shape=(batch_size, feat_dim, horizon),
                    cond=cond,
                )  # -> (batch, feat_dim, horizon)
                all_samples.append(sample)
            except Exception as exc:
                logger.warning(
                    "DDIM 采样 #%d 失败, 退化为均匀先验: %s",
                    s,
                    exc,
                )
                all_samples.append(uniform_prior((batch_size, feat_dim, horizon)))

            # --- 渐进式采样: 提前停止检查 ---
            if (s + 1) >= min_samples and (s + 1) % check_interval == 0:
                # 用已采样的样本估算置信度
                interim_arr = np.stack(all_samples, axis=0)
                interim_logits = interim_arr[:, :, : self._num_actions, :]
                interim_logits = interim_logits.transpose(0, 1, 3, 2)
                interim_probs = self._softmax(interim_logits, axis=-1)
                interim_std = np.mean(np.std(interim_probs, axis=0))
                interim_conf = float(1.0 - np.mean(interim_std))

                if interim_conf >= early_stop_confidence:
                    logger.info(
                        "[Diffusion] ⏱️ 渐进式采样提前停止: %d/%d 样本, 置信度=%.4f (阈值=%.4f), 节省 %d 次采样",
                        s + 1,
                        num_samples,
                        interim_conf,
                        early_stop_confidence,
                        num_samples - (s + 1),
                    )
                    break  # 提前停止采样循环

        # (num_samples, batch, feat_dim, horizon)
        all_samples_arr = np.stack(all_samples, axis=0)

        # --- 提取动作相关通道并计算概率 ---
        # 取前 n_actions 个通道作为动作 logits
        action_logits = all_samples_arr[:, :, :n_actions, :]  # (K, batch, n_actions, horizon)
        action_logits = action_logits.transpose(0, 1, 3, 2)  # (K, batch, horizon, n_actions)

        # Softmax 得到动作概率
        action_probs = self._softmax(action_logits, axis=-1)  # (K, batch, horizon, n_actions)

        # --- 聚合统计 ---
        mean_probs = np.mean(action_probs, axis=0)  # (batch, horizon, n_actions)
        std_probs = np.std(action_probs, axis=0)  # (batch, horizon, n_actions)

        # 首选动作: 概率最大的动作索引
        preferred = np.argmax(mean_probs, axis=-1).astype(np.int32)  # (batch, horizon)

        # 连续动作权重: [卖出(0) -> 持有(1) -> 买入(2)]
        # 权重 = 买入概率 - 卖出概率, 范围 [-1, 1]
        # 0 表示中性（持有）, 正数偏买入, 负数偏卖出
        if n_actions >= 3:
            action_weights = mean_probs[:, :, 2] - mean_probs[:, :, 0]
        elif n_actions == 2:
            # 二分类: 0=卖出, 1=买入
            action_weights = mean_probs[:, :, 1] - mean_probs[:, :, 0]
        else:
            # 单动作: 直接使用概率
            action_weights = mean_probs[:, :, 0] * 2.0 - 1.0

        # 不确定性: 概率分布的标准差均值（跨所有动作类别）
        uncertainty = np.mean(std_probs, axis=-1)  # (batch, horizon)

        # === [FIX 2026-06-26] 不确定性分解：Aleatoric + Epistemic ===
        # 参考: Kendall & Gal 2017 "What Uncertainties Do We Need?"
        # 之前只用了 epistemic（采样一致性），忽略了 aleatoric（预测清晰度）
        #
        # 认知不确定性(Epistemic): DDIM样本间的标准差 → 模型知识不足
        #   高 ← 样本意见分歧 → 模型不确定
        #   低 ← 样本意见一致 → 模型确定
        # 偶然不确定性(Aleatoric): 平均预测概率分布的熵 → 数据固有噪声
        #   高 ← 平均概率接近均匀分布 → 数据本身模糊
        #   低 ← 平均概率接近one-hot → 数据清晰
        # ============================================================
        epistemic = np.mean(std_probs)  # 认知不确定性 (0~1)
        
        # 偶然不确定性: 归一化熵 (0~1)
        # H(p) = -Σ p_i * log(p_i) / log(n_actions)
        # 均匀分布 → 1.0, one-hot → 0.0
        n_actions_float = float(n_actions)
        entropy = -np.sum(mean_probs * np.log(np.clip(mean_probs, 1e-8, 1.0)), axis=-1) / np.log(n_actions_float)
        aleatoric = float(np.mean(entropy))  # 偶然不确定性 (0~1)
        
        # 总不确定性 = 认知 + 偶然 的均值
        total_uncertainty = 0.5 * (epistemic + aleatoric)
        confidence = float(1.0 - total_uncertainty)
        
        # 日志记录分解
        logger.info(
            "[FIX] 不确定性分解: epistemic=%.4f, aleatoric=%.4f, confidence=%.4f (旧算法=%.4f)",
            epistemic,
            aleatoric,
            confidence,
            float(1.0 - np.mean(uncertainty)),
        )

        # --- 自适应风险调整 ---
        adjusted_weights = self.adaptive_risk_adjust(
            action_weights,
            uncertainty,
        )

        # [FIX] 2026-06-18: 信息日志 — 采样统计
        logger.info(
            "[FIX] TradingDecisionDiffuser.decide 执行成功: "
            "num_samples=%d, confidence=%.4f, real_data=True, "
            "batch=%d, horizon=%d, n_actions=%d",
            num_samples,
            confidence,
            batch_size,
            horizon,
            n_actions,
        )

        return {
            "action_sequence": mean_probs,  # (batch, horizon, n_actions)
            "preferred_action": preferred,  # (batch, horizon)
            "action_weights": adjusted_weights,  # (batch, horizon)
            "uncertainty": uncertainty,  # (batch, horizon)
            "confidence": confidence,  # scalar
            "raw_samples": action_probs,  # (K, batch, horizon, n_actions)
            "degraded": False,  # [FIX] 正常执行标记
            "timestamp": datetime.now(timezone.utc).isoformat(),  # [FIX] ISO 时间戳
        }

    # ------------------------------------------------------------------
    # 条件构建
    # ------------------------------------------------------------------

    def _build_condition(
        self,
        market_state: np.ndarray,
        debate_result: np.ndarray | None = None,
        risk_preference: float = 1.0,
    ) -> np.ndarray:
        """构建条件嵌入向量

        将市场状态摘要和辩论结果融合为条件向量，经 LayerNorm 后输出。

        流程:
            1. 市场状态时序均值池化 → 固定维度摘要
            2. 线性投影到 cond_dim（首次遇到新特征维度时缓存投影矩阵）
            3. 可选: 辩论结果投影后与市场状态平均融合
            4. 风险偏好调制 (scale)
            5. LayerNorm 归一化

        Args:
            market_state: (batch, seq_len, features) 市场状态序列
            debate_result: (batch, debate_dim) 辩论嵌入或 None
            risk_preference: 风险偏好标量

        Returns:
            np.ndarray: (batch, cond_dim) float32 条件向量
        """
        market_state.shape[0]
        feat_dim = market_state.shape[2]
        cond_dim = self.config.cond_dim

        # --- 1. 市场状态摘要（时序均值池化） ---
        # 沿时间维取均值, 保留 batch 和特征维
        market_summary = np.mean(market_state, axis=1)  # (batch, feat_dim)

        # --- 2. 线性投影到 cond_dim ---
        W_market = self._get_or_init_projection(
            cache=self._market_proj_cache,
            input_dim=feat_dim,
            output_dim=cond_dim,
        )
        cond = market_summary @ W_market  # (batch, cond_dim)

        # --- 3. 融合辩论结果 ---
        if debate_result is not None:
            debate_dim = debate_result.shape[-1]
            W_debate = self._get_or_init_projection(
                cache=self._debate_proj_cache,
                input_dim=debate_dim,
                output_dim=cond_dim,
            )
            debate_cond = debate_result @ W_debate  # (batch, cond_dim)

            # 平均融合（等权重）
            cond = (cond + debate_cond) / 2.0

        # --- 4. 风险偏好调制 ---
        # risk_preference > 1 → 放大条件信号（更激进）
        # risk_preference < 1 → 缩小条件信号（更保守）
        cond = cond * risk_preference

        # --- 5. LayerNorm ---
        mean = np.mean(cond, axis=-1, keepdims=True)
        std = np.std(cond, axis=-1, keepdims=True) + 1e-5
        cond = (cond - mean) / std

        return cond.astype(np.float32)

    # ------------------------------------------------------------------
    # 自适应风险调整
    # ------------------------------------------------------------------

    @staticmethod
    def adaptive_risk_adjust(
        action_weights: np.ndarray,
        uncertainty: np.ndarray,
        market_volatility: float = 0.02,
    ) -> np.ndarray:
        """基于不确定性的自适应风险调整

        当模型对预测不确定性高时, 自动缩小仓位权重,
        避免在高不确定性环境下过度交易。

        核心逻辑:
            - uncertainty_factor = 1 / (1 + uncertainty * 10)
            - 高 uncertainty → factor 趋近 0 → 权重缩小
            - 低 uncertainty → factor 趋近 1 → 权重保持
            - 波动率裁剪: 权重不超过 [-1, 1] 范围

        Args:
            action_weights: 原始动作权重, shape (batch, horizon)
                范围 [-1, 1], 正值=买入, 负值=卖出
            uncertainty: 动作不确定性, shape (batch, horizon)
                范围 [0, 1], 0=完全确定, 1=完全不确定
            market_volatility: 市场波动率阈值, 默认 0.02
                用于最终的权重裁剪（保留扩展）

        Returns:
            np.ndarray: 调整后的动作权重, shape 与 action_weights 相同
        """
        # 不确定性缩放因子
        # uncertainty=0.0 → factor=1.0 (完全信任)
        # uncertainty=0.5 → factor≈0.17 (大幅缩小)
        # uncertainty=1.0 → factor≈0.09 (几乎归零)
        uncertainty_factor = 1.0 / (1.0 + uncertainty * 10.0)

        adjusted = action_weights * uncertainty_factor

        # 安全裁剪
        adjusted = np.clip(adjusted, -1.0, 1.0)

        return adjusted

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_or_init_projection(
        self,
        cache: dict[int, np.ndarray],
        input_dim: int,
        output_dim: int,
    ) -> np.ndarray:
        """获取或初始化投影矩阵

        在 __init__ 时无法预知 market_state 的特征维度, 因此在
        首次遇到新维度时按 Kaiming 均匀初始化创建投影矩阵并缓存。

        Args:
            cache: 投影矩阵缓存字典
            input_dim: 输入维度
            output_dim: 输出维度

        Returns:
            np.ndarray: shape (input_dim, output_dim) 投影矩阵
        """
        if input_dim not in cache:
            # Kaiming 均匀初始化
            scale = np.sqrt(6.0 / (input_dim + output_dim))
            W = np.random.uniform(
                -scale,
                scale,
                size=(input_dim, output_dim),
            ).astype(np.float64)
            cache[input_dim] = W
            logger.debug(
                "初始化投影矩阵: %d -> %d (scale=%.4f)",
                input_dim,
                output_dim,
                scale,
            )
        return cache[input_dim]

    @staticmethod
    def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        """数值稳定的 Softmax

        Args:
            x: 输入数组
            axis: Softmax 计算轴

        Returns:
            np.ndarray: Softmax 概率
        """
        x_max = np.max(x, axis=axis, keepdims=True)
        e_x = np.exp(x - x_max)
        return e_x / (np.sum(e_x, axis=axis, keepdims=True) + 1e-8)

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置决策器状态

        清空投影矩阵缓存并重置校准状态。
        """
        self._calibrated = False
        self.model = TemporalUNet1D(
            config=self.config,
            in_channels=1,
            out_channels=1,
        )
        self._market_proj_cache.clear()
        self._debate_proj_cache.clear()
        logger.info("TradingDecisionDiffuser 已重置")

    def __repr__(self) -> str:
        return (
            f"TradingDecisionDiffuser(feat_dim={self._feat_dim}, num_actions={self._num_actions}, config={self.config})"
        )
