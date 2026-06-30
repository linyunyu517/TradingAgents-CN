# TradingAgents/hpc_loop/generative_model.py
"""
宏观生成模型 (Macro Generative Model)

实现 Karl Friston 自由能原理驱动的层级生成模型。
在每个时间步，先生成对市场观测的预测，再接收实际观测计算预测误差，
最后使用预测误差更新内部模型参数 (变分贝叶斯更新)。

理论基础:
    - Friston Free Energy Principle (2010, 2013)
    - Rao & Ballard Predictive Coding (1999)
    - 贝叶斯脑假说 (Bayesian Brain Hypothesis)
"""

import logging
import math
from datetime import datetime
from typing import Any

import numpy as np

from .hpc_config import HPCLoopConfig

logger = logging.getLogger(__name__)
from .hpc_state import (
    MarketLatentState,
    MarketPrediction,
    PredictionError,
)
from .prediction_error import PredictionErrorCalculator

# === Phase 3: 扩散增强生成模型 (可选) ===
try:
    from tradingagents.diffusion import DiffusionGenerativeModel as _DiffusionGenModel

    _DIFFUSION_GEN_AVAILABLE = True
except ImportError:
    _DiffusionGenModel = None  # type: ignore
    _DIFFUSION_GEN_AVAILABLE = False


class MarketGenerativeModel:
    """
    L3 层级生成模型 — 维护市场状态的层级化概率表征。

    核心状态变量:
    - market_regime: 市场体制 (牛市/熊市/震荡/危机) — 离散潜变量
    - volatility_state: 波动率状态 (低/中/高/极端)
    - correlation_structure: 板块相关性矩阵
    - macro_prior: 宏观经济因子先验

    每个变量维护为概率分布 P(latent_variable)。

    关键流程:
    1. generate_prediction(): 基于当前信念生成对未来观测的预测分布
    2. compute_prediction_error(): 计算预测与实际的偏差
    3. update_beliefs(): 基于预测误差更新信念 (变分更新)
    4. detect_phase_transition(): 检测市场相变
    """

    def __init__(
        self,
        config: HPCLoopConfig | None = None,
    ):
        self.config = config or HPCLoopConfig()

        # 初始化隐状态
        self.latent_state = MarketLatentState()

        # 预测误差计算器
        self.pe_calculator = PredictionErrorCalculator(config)

        # 历史记录
        self._prediction_history: list[MarketPrediction] = []
        self._observation_history: list[dict[str, Any]] = []
        self._free_energy_history: list[float] = []

        # 变分更新参数
        self._learning_rate = self.config.generative_model_learning_rate
        self._latent_dim = self.config.generative_model_latent_dim  # 32D (旧 HPC dict 路径)
        # 注意: generative_model_latent_dim=32 仅用于 MarketGenerativeModel (旧 HPC 路径).
        # AIF 引擎使用 aif_latent_dim=8 (aif_engine.py JAX 紧凑向量).
        # 两个子系统通过 _adapt_s_t_dim() 自动适配维度差异.

        # 模型复杂度正则化项
        self._model_complexity = 0.0

        # === Phase 3: 扩散生成模型 (可选) ===
        self._diffusion_model: _DiffusionGenModel | None = None
        if _DIFFUSION_GEN_AVAILABLE:
            try:
                # 从 HPCLoopConfig 同步 diffusion_num_timesteps → DiffusionConfig
                from tradingagents.diffusion.config import DiffusionConfig as _DiffusionConfig

                _diff_cfg = _DiffusionConfig(
                    num_timesteps=getattr(
                        self.config, "diffusion_num_timesteps", 20,
                    ),  # [优化 2026-06-22] 默认从 100 降至 20，配合 diffusion 模块渐进式采样
                )
                self._diffusion_model = _DiffusionGenModel(config=_diff_cfg)
            except Exception as exc:
                logger.warning("[DiffusionGen] 扩散模型初始化失败: %s", exc)

    def generate_prediction(
        self,
        current_latent_state: MarketLatentState | None = None,
    ) -> MarketPrediction:
        """
        生成对下一时刻市场状态的预测

        基于当前隐状态，生成对观测数据各个维度的预测分布。

        Args:
            current_latent_state: 当前隐状态 (若为None则使用内部状态)

        Returns:
            MarketPrediction: 包含各维度预测值和置信区间
        """
        state = current_latent_state or self.latent_state
        prediction = MarketPrediction()

        regime = state.get_regime()
        volatility = state.get_volatility()
        entropy = state.get_entropy()

        # === 价格预测 ===
        price_mean = self._predicted_price_change(regime, volatility)
        price_std = self._predicted_volatility(volatility, entropy)
        prediction.price_prediction = {
            "mean": price_mean,
            "lower": price_mean - 1.96 * price_std,
            "upper": price_mean + 1.96 * price_std,
        }

        # === 波动率预测 ===
        vol_mean, vol_std = self._predicted_volatility_distribution(volatility, state.volatility_state_probs)
        prediction.volatility_prediction = {
            "mean": vol_mean,
            "lower": vol_mean - 1.96 * vol_std,
            "upper": vol_mean + 1.96 * vol_std,
        }

        # === 情绪预测 ===
        sentiment_mean = self._predicted_sentiment(regime, state.macro_prior)
        sentiment_std = 0.1 + 0.3 * entropy  # 不确定性越大，预测置信区间越宽
        prediction.sentiment_prediction = {
            "mean": sentiment_mean,
            "lower": sentiment_mean - 1.96 * sentiment_std,
            "upper": sentiment_mean + 1.96 * sentiment_std,
        }

        # === 宏观因子预测 ===
        prediction.macro_prediction = self._predicted_macro(state.macro_prior)

        # === 多尺度预测 ===
        # Tick级别: 快速波动
        prediction.tick_prediction = {
            "mean": price_mean * 0.1,
            "lower": price_mean * 0.1 - 2 * price_std * 0.1,
            "upper": price_mean * 0.1 + 2 * price_std * 0.1,
        }
        # 分钟级别: 中速波动
        prediction.minute_prediction = {
            "mean": price_mean * 0.3,
            "lower": price_mean * 0.3 - 1.5 * price_std * 0.3,
            "upper": price_mean * 0.3 + 1.5 * price_std * 0.3,
        }
        # 日级别: 主时间尺度
        prediction.daily_prediction = {
            "mean": price_mean,
            "lower": price_mean - 1.96 * price_std,
            "upper": price_mean + 1.96 * price_std,
        }
        # 周级别: 趋势预测
        weekly_mean = price_mean * 5
        weekly_std = price_std * math.sqrt(5)
        prediction.weekly_prediction = {
            "mean": weekly_mean,
            "lower": weekly_mean - 1.96 * weekly_std,
            "upper": weekly_mean + 1.96 * weekly_std,
        }
        # 月级别: 长期预测 (高不确定性)
        monthly_std = price_std * math.sqrt(21) * 1.5  # 额外不确定性乘子
        prediction.monthly_prediction = {
            "mean": weekly_mean * 4,
            "lower": weekly_mean * 4 - 1.96 * monthly_std,
            "upper": weekly_mean * 4 + 1.96 * monthly_std,
        }

        # === 置信度计算 ===
        prediction.confidence_scores = {
            "price": 1.0 / (1.0 + price_std),
            "volatility": 1.0 / (1.0 + vol_std),
            "sentiment": 1.0 / (1.0 + sentiment_std),
            "overall": 1.0 / (1.0 + entropy),
        }

        # === Phase 3: 扩散增强预测 (可选) ===
        try:
            diffusion_gen_enabled = getattr(self.config, "diffusion_generative_enabled", False)
        except Exception:
            diffusion_gen_enabled = False
        if diffusion_gen_enabled and _DIFFUSION_GEN_AVAILABLE and self._diffusion_model is not None:
            prediction = self._run_diffusion_enhancement(prediction, state)

        prediction.timestamp = datetime.now().isoformat()

        # 记录历史
        self._prediction_history.append(prediction)
        if len(self._prediction_history) > self.config.generative_model_history_window:
            self._prediction_history.pop(0)

        return prediction

    def compute_prediction_error(
        self,
        prediction: MarketPrediction,
        actual_observation: dict[str, Any],
    ) -> PredictionError:
        """
        计算预测误差

        委托给 PredictionErrorCalculator 进行多尺度误差计算。

        Args:
            prediction: 生成的预测
            actual_observation: 实际观测值

        Returns:
            PredictionError: 多尺度预测误差
        """
        error = self.pe_calculator.compute_multiscale_error(prediction, actual_observation)
        return error

    def update_beliefs(
        self,
        prediction_error: PredictionError,
    ) -> MarketLatentState:
        """
        基于预测误差更新内部信念 (变分贝叶斯更新)

        使用预测误差来更新 MarketLatentState 中的概率分布。
        这是一个简化的变分推理步骤。

        Args:
            prediction_error: 多尺度预测误差

        Returns:
            MarketLatentState: 更新后的隐状态
        """
        state = self.latent_state
        error_val = prediction_error.total_error
        error_norm = prediction_error.error_norm

        # 计算信念更新量
        # 使用负梯度: 预测误差的方向告诉我们应该如何调整信念
        self._learning_rate * error_val
        surprise_factor = 1.0 + prediction_error.surprise_magnitude * 0.5

        # === 更新市场体制信念 ===
        state = self._update_regime_belief(state, error_val, error_norm, surprise_factor)

        # === 更新波动率状态信念 ===
        state = self._update_volatility_belief(state, prediction_error.volatility_error, surprise_factor)

        # === 更新不确定性度量 ===
        state = self._update_uncertainty(state, prediction_error)

        # === 更新模型复杂度 (KL(Q||P)) ===
        # 当预测误差大时，模型复杂度增加（需要更大的模型调整）
        self._model_complexity = 0.9 * self._model_complexity + 0.1 * error_norm

        # === 计算变分自由能 ===
        free_energy = self.pe_calculator.compute_free_energy(
            prediction_error,
            belief_uncertainty=state.total_uncertainty,
            model_complexity=self._model_complexity,
        )
        self._free_energy_history.append(free_energy)

        # === 记录信念历史 (用于相变检测) ===
        state.belief_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "regime_probs": dict(state.market_regime_probs),
                "volatility_probs": dict(state.volatility_state_probs),
                "total_uncertainty": state.total_uncertainty,
                "free_energy": free_energy,
                "prediction_error": error_norm,
            },
        )
        if len(state.belief_history) > self.config.generative_model_history_window:
            state.belief_history.pop(0)

        self.latent_state = state
        return state

    def _update_regime_belief(
        self,
        state: MarketLatentState,
        error_val: float,
        error_norm: float,
        surprise_factor: float,
    ) -> MarketLatentState:
        """更新市场体制信念"""
        regimes = list(state.market_regime_probs.keys())
        state.get_regime()

        # 预测误差的方向决定体制偏移方向
        if error_val > 0:
            # 实际价格高于预测 → 可能向牛市偏移
            shift_toward = "bull"
            shift_away = "bear"
        else:
            # 实际价格低于预测 → 可能向熊市偏移
            shift_toward = "bear"
            shift_away = "bull"

        # 计算每个体制的更新量
        updates = {}
        for regime in regimes:
            if regime == shift_toward:
                # 向该体制偏移
                updates[regime] = error_norm * surprise_factor * 1.5
            elif regime == shift_away:
                # 远离该体制
                updates[regime] = -error_norm * surprise_factor * 0.5
            elif regime == "crisis" and error_norm > 0.5:
                # 大误差 → 危机概率上升
                updates[regime] = error_norm * 0.3 * surprise_factor
            else:
                # 震荡市是默认回归
                updates[regime] = -error_norm * 0.1

        # 应用更新 (在 logit 空间)
        logits = []
        for regime in regimes:
            prob = state.market_regime_probs[regime]
            # 转换为 logit: log(p / (1-p))
            logit = math.log(max(prob, 1e-8) / max(1 - prob, 1e-8))
            logit += updates[regime] * self._learning_rate
            logits.append(logit)

        # Softmax 转换回概率
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        sum_exp = sum(exp_logits)

        for i, regime in enumerate(regimes):
            state.market_regime_probs[regime] = exp_logits[i] / sum_exp

        return state

    def _update_volatility_belief(
        self,
        state: MarketLatentState,
        volatility_error: float | None,
        surprise_factor: float,
    ) -> MarketLatentState:
        """更新波动率状态信念"""
        if volatility_error is None:
            return state

        vol_states = list(state.volatility_state_probs.keys())
        vol_update = abs(volatility_error) * surprise_factor

        # 增大波动率 → 向 high/extreme 偏移
        if vol_update > 0.1:
            logits = []
            for vs in vol_states:
                prob = state.volatility_state_probs[vs]
                logit = math.log(max(prob, 1e-8) / max(1 - prob, 1e-8))

                if vs == "extreme":
                    logit += vol_update * 0.8 * self._learning_rate
                elif vs == "high":
                    logit += vol_update * 0.4 * self._learning_rate
                elif vs == "medium":
                    logit -= vol_update * 0.1 * self._learning_rate
                elif vs == "low":
                    logit -= vol_update * 0.3 * self._learning_rate
                logits.append(logit)

            max_logit = max(logits)
            exp_logits = [math.exp(l - max_logit) for l in logits]
            sum_exp = sum(exp_logits)

            for i, vs in enumerate(vol_states):
                state.volatility_state_probs[vs] = exp_logits[i] / sum_exp

        return state

    def _update_uncertainty(
        self,
        state: MarketLatentState,
        prediction_error: PredictionError,
    ) -> MarketLatentState:
        """更新不确定性度量"""
        error_norm = prediction_error.error_norm
        surprise = prediction_error.surprise_magnitude

        # 总不确定性 = 偶然不确定性 + 认知不确定性
        # 偶然不确定性 (aleatoric): 数据固有的噪声
        # 认知不确定性 (epistemic): 模型不知道的部分

        aleatoric_update = 0.05 * (error_norm - state.aleatoric_uncertainty)
        state.aleatoric_uncertainty = max(0.01, min(1.0, state.aleatoric_uncertainty + aleatoric_update))

        # 认知不确定性: 受惊奇事件影响
        epistemic_update = 0.1 * (surprise * 0.2 - state.epistemic_uncertainty)
        state.epistemic_uncertainty = max(0.01, min(1.0, state.epistemic_uncertainty + epistemic_update))

        state.total_uncertainty = state.aleatoric_uncertainty + state.epistemic_uncertainty
        state.total_uncertainty = min(max(state.total_uncertainty, 0.01), 2.0)

        return state

    def detect_phase_transition(self) -> dict[str, Any]:
        """
        检测市场相变

        基于信念历史分析，检测市场体制是否可能正在发生相变。

        相变信号:
        1. 信念分布的 KL 散度变化率激增
        2. 不确定性突然增大
        3. 连续的高预测误差

        Returns:
            Dict 包含:
            - is_transitioning: bool
            - transition_probability: float (0-1)
            - signal_strength: float
            - from_regime: str
            - to_regime: str (预测)
        """
        history = self.latent_state.belief_history
        if len(history) < 5:
            return {
                "is_transitioning": False,
                "transition_probability": 0.0,
                "signal_strength": 0.0,
                "from_regime": self.latent_state.get_regime(),
                "to_regime": self.latent_state.get_regime(),
            }

        # 1. 信念分布变异性
        recent_beliefs = history[-5:]
        regime_changes = []
        for i in range(1, len(recent_beliefs)):
            prev_probs = recent_beliefs[i - 1]["regime_probs"]
            curr_probs = recent_beliefs[i]["regime_probs"]
            kl_div = self._kl_divergence(prev_probs, curr_probs)
            regime_changes.append(kl_div)

        avg_kl_change = np.mean(regime_changes) if regime_changes else 0.0

        # 2. 不确定性趋势
        uncertainty_trend = recent_beliefs[-1]["total_uncertainty"] - recent_beliefs[0]["total_uncertainty"]

        # 3. 自由能趋势
        if len(self._free_energy_history) >= 5:
            recent_fe = self._free_energy_history[-5:]
            fe_trend = (recent_fe[-1] - recent_fe[0]) / max(abs(recent_fe[0]), 1e-8)
        else:
            fe_trend = 0.0

        # 综合相变信号
        signal_strength = (
            0.4 * min(avg_kl_change * 10, 1.0)
            + 0.3 * min(max(uncertainty_trend * 5, 0), 1.0)
            + 0.3 * min(max(fe_trend, 0), 1.0)
        )

        is_transitioning = signal_strength > 0.5

        # 预测目标体制: 基于最近变化趋势
        current_regime = self.latent_state.get_regime()
        if is_transitioning and uncertainty_trend > 0:
            # 不确定性上升 + 信号强 → 可能向危机/震荡过渡
            target_regime = "range_bound" if current_regime in ("bull", "bear") else "crisis"
        else:
            target_regime = current_regime

        return {
            "is_transitioning": is_transitioning,
            "transition_probability": min(signal_strength, 1.0),
            "signal_strength": signal_strength,
            "from_regime": current_regime,
            "to_regime": target_regime,
            "kl_divergence_rate": avg_kl_change,
            "uncertainty_trend": uncertainty_trend,
            "free_energy_trend": fe_trend,
        }

    def get_latent_state(self) -> MarketLatentState:
        """获取当前隐状态"""
        return self.latent_state

    def get_free_energy(self) -> float:
        """获取最近计算的变分自由能"""
        return self._free_energy_history[-1] if self._free_energy_history else 0.0

    def get_free_energy_history(self) -> list[float]:
        """获取自由能历史"""
        return list(self._free_energy_history)

    # ==================== 内部预测方法 ====================

    def _predicted_price_change(self, regime: str, volatility: str) -> float:
        """基于体制和波动率预测价格变化"""
        regime_map = {
            "bull": 0.005,
            "bear": -0.005,
            "range_bound": 0.0,
            "crisis": -0.02,
        }
        vol_map = {
            "low": 0.001,
            "medium": 0.005,
            "high": 0.01,
            "extreme": 0.02,
        }
        # 体制方向 * 波动率幅度
        direction = regime_map.get(regime, 0.0)
        magnitude = vol_map.get(volatility, 0.005)
        return direction * (magnitude / 0.005) * 0.01

    def _predicted_volatility(self, volatility: str, entropy: float) -> float:
        """预测波动率 (标准差)"""
        vol_map = {
            "low": 0.005,
            "medium": 0.015,
            "high": 0.03,
            "extreme": 0.06,
        }
        base_vol = vol_map.get(volatility, 0.015)
        # 不确定性越高，预测波动率越大
        return base_vol * (1.0 + entropy)

    def _predicted_volatility_distribution(
        self,
        volatility: str,
        vol_probs: dict[str, float],
    ) -> tuple[float, float]:
        """预测波动率分布的均值和标准差"""
        vol_values = {"low": 0.2, "medium": 0.5, "high": 0.8, "extreme": 1.0}
        mean = sum(vol_values[k] * vol_probs.get(k, 0) for k in vol_values)
        var = sum(vol_values[k] ** 2 * vol_probs.get(k, 0) for k in vol_values) - mean**2
        return mean, math.sqrt(max(var, 1e-8))

    def _predicted_sentiment(self, regime: str, macro_prior: dict[str, float]) -> float:
        """预测市场情绪"""
        regime_sentiment = {
            "bull": 0.3,
            "bear": -0.3,
            "range_bound": 0.0,
            "crisis": -0.6,
        }
        base_sentiment = regime_sentiment.get(regime, 0.0)
        # 宏观因子调整
        macro_adjustment = sum(macro_prior.values()) / max(len(macro_prior), 1) * 0.1
        return base_sentiment + macro_adjustment

    def _predicted_macro(self, macro_prior: dict[str, float]) -> dict[str, float]:
        """预测宏观因子"""
        if not macro_prior:
            return {"gdp_growth": 0.02, "inflation": 0.025, "interest_rate": 0.05}
        # 保持现有宏观因子值，微小随机波动
        result = {}
        for key, val in macro_prior.items():
            result[key] = val * (1 + np.random.randn() * 0.01)
        return result

    def reset(self) -> None:
        """重置生成模型"""
        self.latent_state = MarketLatentState()
        self._prediction_history.clear()
        self._observation_history.clear()
        self._free_energy_history.clear()
        self._model_complexity = 0.0
        self.pe_calculator.reset()
        # 重置扩散模型（如有）
        if self._diffusion_model is not None:
            try:
                self._diffusion_model = _DiffusionGenModel()
            except Exception:
                logger.warning("生成模型执行失败", exc_info=True)

    # ==================== Phase 3: 扩散增强 ====================

    def _run_diffusion_enhancement(
        self,
        prediction: MarketPrediction,
        state: MarketLatentState,
    ) -> MarketPrediction:
        """
        使用扩散生成模型增强预测分布

        将原有的硬编码高斯预测与扩散模型的多模预测融合，
        提供更准确的不确定性量化和多峰分布建模。

        Args:
            prediction: 原有预测
            state: 当前隐状态

        Returns:
            MarketPrediction: 增强后的预测
        """
        try:
            market_state = self._build_market_state_from_latent(state)
            result = self._diffusion_model.predict_distribution(
                market_state=market_state,
                num_samples=10,
            )
            diff_mean = result["mean"][0]  # (seq_len, feat)
            diff_std = result["std"][0]  # (seq_len, feat)
            diff_confidence = result["confidence"]

            # 加权混合: 70% 原始 + 30% 扩散
            blend_ratio = 0.3
            for key in ("price_prediction", "volatility_prediction", "sentiment_prediction"):
                pred = getattr(prediction, key, None)
                if pred is not None and isinstance(pred, dict) and "mean" in pred:
                    orig_mean = pred["mean"]
                    # 从 diff_mean 取第一个时间步的第一个特征
                    if isinstance(diff_mean, np.ndarray):
                        delta = float(diff_mean[0, 0]) if diff_mean.ndim >= 2 else float(diff_mean[0])
                    else:
                        delta = float(diff_mean)
                    pred["mean"] = (1 - blend_ratio) * orig_mean + blend_ratio * delta
                    # 使用扩散标准差更新置信区间
                    if isinstance(diff_std, np.ndarray):
                        std_val = float(diff_std[0, 0]) if diff_std.ndim >= 2 else float(diff_std[0])
                    else:
                        std_val = float(diff_std)
                    pred["lower"] = pred["mean"] - 1.96 * std_val
                    pred["upper"] = pred["mean"] + 1.96 * std_val

            # 更新置信度分数
            if prediction.confidence_scores:
                overall = prediction.confidence_scores.get("overall", 0.5)
                prediction.confidence_scores["overall"] = 0.7 * overall + 0.3 * diff_confidence
                prediction.confidence_scores["diffusion_confidence"] = diff_confidence

        except Exception as exc:
            logger.warning("[DiffusionGen] 扩散增强失败，使用原始预测: %s", exc)

        return prediction

    def _build_market_state_from_latent(self, state: MarketLatentState) -> np.ndarray:
        """
        从 MarketLatentState 构建扩散模型所需的 market_state 数组

        将隐状态中的概率分布和信念值转换为固定维度的数值向量，
        遵循扩散 DecisionDiffuser 的 (batch, seq_len, features) 约定。

        Args:
            state: 当前隐状态

        Returns:
            np.ndarray: shape (1, 1, features) 的 market_state
        """
        # 构建特征向量
        features = []

        # 市场体制概率 (4维)
        for regime in ("bull", "bear", "range_bound", "crisis"):
            features.append(state.market_regime_probs.get(regime, 0.25))

        # 波动率概率 (4维)
        for vol in ("low", "medium", "high", "extreme"):
            features.append(state.volatility_state_probs.get(vol, 0.25))

        # 不确定性度量 (3维)
        features.append(state.total_uncertainty)
        features.append(state.aleatoric_uncertainty)
        features.append(state.epistemic_uncertainty)

        # 宏观因子均值 (最多5个)
        macro_values = list(state.macro_prior.values()) if state.macro_prior else [0.02, 0.025, 0.05]
        for _ in range(5):
            features.append(macro_values[_] if _ < len(macro_values) else 0.0)

        # 构造 (1, 1, F) 数组
        market_state = np.array(features, dtype=np.float32).reshape(1, 1, -1)
        return market_state

    # ==================== 工具方法 ====================

    @staticmethod
    def _kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
        """计算两个概率分布的 KL 散度"""
        kl = 0.0
        for key in set(list(p.keys()) + list(q.keys())):
            p_val = max(p.get(key, 1e-8), 1e-8)
            q_val = max(q.get(key, 1e-8), 1e-8)
            kl += p_val * math.log(p_val / q_val)
        return kl
