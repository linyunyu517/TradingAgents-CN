# TradingAgents/hpc_loop/prediction_error.py
"""
预测误差计算与传播模块

实现多尺度预测误差计算、变分自由能估计、
惊奇检测和精度动态更新机制。

理论基础:
    - Rao & Ballard (1999) 层级预测编码
    - Friston 变分自由能原理
"""

import math
from typing import Any

import numpy as np

from .hpc_config import HPCLoopConfig
from .hpc_state import MarketPrediction, PredictionError


class PredictionErrorCalculator:
    """
    预测误差计算器

    核心功能:
    1. 多尺度预测误差计算
    2. 变分自由能估计
    3. 惊奇检测 (显著性超出预期的误差)
    4. 精度 (逆方差) 动态更新
    """

    def __init__(self, config: HPCLoopConfig | None = None):
        self.config = config or HPCLoopConfig()

        # 精度 (逆方差) 权重 - 各维度独立维护
        self._precision_weights: dict[str, float] = {
            "price": 1.0,
            "volatility": 1.0,
            "sentiment": 1.0,
            "macro": 1.0,
            "tick": 1.0,
            "minute": 1.0,
            "daily": 1.0,
            "weekly": 1.0,
            "monthly": 1.0,
        }

        # 误差历史 (用于精度动态更新)
        self._error_history: dict[str, list[float]] = {k: [] for k in self._precision_weights}

        # 误差归一化统计
        self._error_mean: dict[str, float] = dict.fromkeys(self._precision_weights, 0.0)
        self._error_std: dict[str, float] = dict.fromkeys(self._precision_weights, 1.0)

    def compute_multiscale_error(
        self,
        prediction: MarketPrediction,
        actual: dict[str, Any],
    ) -> PredictionError:
        """
        计算多尺度预测误差

        Args:
            prediction: 生成模型的预测输出
            actual: 实际观测值

        Returns:
            PredictionError: 多尺度预测误差
        """
        error = PredictionError()

        # === 价格预测误差 ===
        if getattr(prediction, "price_prediction", None) and actual.get("price") is not None:
            pred_mean = (prediction.price_prediction or {}).get("mean", 0)
            actual_price = actual["price"]
            error.price_error = actual_price - pred_mean

        # === 波动率预测误差 ===
        if getattr(prediction, "volatility_prediction", None) and "volatility" in actual:
            pred_vol = (prediction.volatility_prediction or {}).get("mean", 0)
            actual_vol = actual["volatility"]
            error.volatility_error = actual_vol - pred_vol

        # === 情绪预测误差 ===
        if getattr(prediction, "sentiment_prediction", None) and "sentiment" in actual:
            pred_sent = (prediction.sentiment_prediction or {}).get("mean", 0)
            actual_sent = actual["sentiment"]
            error.sentiment_error = actual_sent - pred_sent

        # === 宏观因子预测误差 ===
        if getattr(prediction, "macro_prediction", None) and actual.get("macro") is not None:
            pred_macro = (prediction.macro_prediction or {}).get("mean", 0)
            actual_macro = actual["macro"] if isinstance(actual.get("macro"), (int, float)) else 0
            error.macro_error = actual_macro - pred_macro

        # === 多尺度误差 ===
        if getattr(prediction, "tick_prediction", None) and "tick" in actual:
            error.tick_error = actual.get("tick", 0) - (prediction.tick_prediction or {}).get("mean", 0)
        if getattr(prediction, "minute_prediction", None) and "minute" in actual:
            error.minute_error = actual.get("minute", 0) - (prediction.minute_prediction or {}).get("mean", 0)
        if getattr(prediction, "daily_prediction", None) and "daily" in actual:
            error.daily_error = actual.get("daily", 0) - (prediction.daily_prediction or {}).get("mean", 0)
        if getattr(prediction, "weekly_prediction", None) and "weekly" in actual:
            error.weekly_error = actual.get("weekly", 0) - (prediction.weekly_prediction or {}).get("mean", 0)
        if getattr(prediction, "monthly_prediction", None) and "monthly" in actual:
            error.monthly_error = actual.get("monthly", 0) - (prediction.monthly_prediction or {}).get("mean", 0)

        # === 汇总误差计算 ===
        error.total_error = self._compute_weighted_total(error)
        error.error_norm = abs(error.total_error)

        # === 精度权重赋值 ===
        error.precision_weights = dict(self._precision_weights)

        # === 惊奇检测 ===
        error.is_surprising, error.surprise_magnitude = self._detect_surprise(error)

        # === 更新误差历史 (用于精度动态更新) ===
        self._update_error_history(error)

        return error

    def _compute_weighted_total(self, error: PredictionError) -> float:
        """计算加权总误差（包含4个维度和6个时间尺度的误差）"""
        total = 0.0
        total_weight = 0.0

        # 4个主要维度误差
        weighted_errors = [
            ("price", error.price_error),
            ("volatility", error.volatility_error),
            ("sentiment", error.sentiment_error),
            ("macro", error.macro_error),
        ]

        for dim_name, err_val in weighted_errors:
            if err_val is not None:
                weight = self._precision_weights.get(dim_name, 1.0)
                total += weight * err_val
                total_weight += weight

        # 6个时间尺度细粒度误差（保留多尺度信息）
        time_scale_errors = [
            ("tick", error.tick_error),
            ("minute", error.minute_error),
            ("daily", error.daily_error),
            ("weekly", error.weekly_error),
            ("monthly", error.monthly_error),
        ]

        for scale_name, err_val in time_scale_errors:
            if err_val is not None:
                weight = self._precision_weights.get(scale_name, 1.0)
                total += weight * err_val
                total_weight += weight

        return total / total_weight if total_weight > 0 else 0.0

    def compute_free_energy(
        self,
        prediction_error: PredictionError,
        belief_uncertainty: float = 1.0,
        model_complexity: float = 0.0,
    ) -> float:
        """
        计算变分自由能

        F = 预测误差项 (accuracy) + 模型复杂度 (complexity)

        Args:
            prediction_error: 预测误差
            belief_uncertainty: 信念不确定性 (方差)
            model_complexity: 模型复杂度 (KL(Q||P))

        Returns:
            float: 变分自由能值
        """
        # 精确度项 (negative log-likelihood 近似)
        accuracy_term = 0.5 * (prediction_error.error_norm**2) / (belief_uncertainty + 1e-8)
        accuracy_term += 0.5 * math.log(belief_uncertainty + 1e-8)

        # 复杂度项 (KL散度近似)
        complexity_term = model_complexity

        free_energy = accuracy_term + complexity_term
        return free_energy

    def surprise_detection(
        self,
        prediction_error: PredictionError,
        threshold: float | None = None,
    ) -> float:
        """
        惊奇检测

        当预测误差显著超出历史分布时返回惊奇信号。
        使用 z-score 方法。

        Args:
            prediction_error: 预测误差
            threshold: 阈值 (标准差倍数), 默认使用配置值

        Returns:
            float: 惊奇信号强度 (0 = 无惊奇, >1 = 惊奇)
        """
        if threshold is None:
            threshold = self.config.prediction_error_surprise_threshold

        # 使用价格误差的 z-score 作为主要惊奇度量
        error_val = prediction_error.price_error or 0.0
        mean = self._error_mean.get("price", 0.0)
        std = self._error_std.get("price", 1.0)

        if std < 1e-8:
            return 0.0

        z_score = abs(error_val - mean) / std

        if z_score >= threshold:
            return min(z_score / threshold, 10.0)  # 截断到 [0, 10]
        return 0.0

    def _detect_surprise(
        self,
        prediction_error: PredictionError,
    ) -> tuple[bool, float]:
        """
        检测是否为惊奇事件

        综合多个维度的 z-score 判断。

        Returns:
            (is_surprising, magnitude)
        """
        threshold = self.config.prediction_error_surprise_threshold
        max_z_score = 0.0
        n_dims = 0

        for dim_name, err_val in [
            ("price", prediction_error.price_error),
            ("volatility", prediction_error.volatility_error),
            ("sentiment", prediction_error.sentiment_error),
            ("macro", prediction_error.macro_error),
        ]:
            if err_val is not None:
                mean = self._error_mean.get(dim_name, 0.0)
                std = self._error_std.get(dim_name, 1.0)
                if std > 1e-8:
                    z_score = abs(err_val - mean) / std
                    max_z_score = max(max_z_score, z_score)
                    n_dims += 1

        is_surprising = max_z_score >= threshold
        magnitude = max_z_score / threshold if threshold > 0 else max_z_score

        return is_surprising, magnitude

    def update_precision(
        self,
        prediction_error: PredictionError | None = None,
    ) -> dict[str, float]:
        """
        动态更新精度权重 (逆方差)

        基于预测误差的历史分布更新精度。
        误差越大、越不稳定 → 精度越低 → 该维度在信念更新中的权重越低。

        Args:
            prediction_error: 最近一次预测误差 (可选)

        Returns:
            Dict[str, float]: 更新后的精度权重
        """
        if not self.config.prediction_error_precision_dynamics:
            return dict(self._precision_weights)

        # CRITICAL-2: 使用配置的 prediction_error_rate 作为平滑因子
        alpha = getattr(self.config, "prediction_error_rate", 0.15)

        for dim_name in self._precision_weights:
            history = self._error_history.get(dim_name, [])
            if len(history) < 2:
                continue

            # 使用滚动窗口的方差估计
            variance = np.var(history[-50:]) + 1e-8
            # 精度 = 1 / 方差
            precision = 1.0 / variance

            # 平滑更新 (避免单步剧烈变化)
            self._precision_weights[dim_name] = alpha * precision + (1 - alpha) * self._precision_weights[dim_name]

            # 截断到合理范围 [0.01, 10.0]
            self._precision_weights[dim_name] = max(0.01, min(10.0, self._precision_weights[dim_name]))

        return dict(self._precision_weights)

    def _update_error_history(self, error: PredictionError) -> None:
        """更新误差历史"""
        for dim_name, err_val in [
            ("price", error.price_error),
            ("volatility", error.volatility_error),
            ("sentiment", error.sentiment_error),
            ("macro", error.macro_error),
            ("tick", error.tick_error),
            ("minute", error.minute_error),
            ("daily", error.daily_error),
            ("weekly", error.weekly_error),
            ("monthly", error.monthly_error),
        ]:
            if err_val is not None:
                self._error_history[dim_name].append(err_val)

                # 更新滚动均值和标准差
                recent = self._error_history[dim_name][-100:]  # 窗口大小 100
                self._error_mean[dim_name] = float(np.mean(recent))
                self._error_std[dim_name] = float(np.std(recent)) + 1e-8

    def get_precision_weights(self) -> dict[str, float]:
        """获取当前精度权重"""
        return dict(self._precision_weights)

    def reset(self) -> None:
        """重置内部状态"""
        for key in self._precision_weights:
            self._precision_weights[key] = 1.0
            self._error_history[key] = []
            self._error_mean[key] = 0.0
            self._error_std[key] = 1.0
