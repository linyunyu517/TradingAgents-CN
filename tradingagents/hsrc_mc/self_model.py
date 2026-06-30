# TradingAgents/hsrc_mc/self_model.py
"""
SelfModel — 自我指涉预测模型
==============================

理论基础:
    1. 反身性 (Soros, 1987):
       认知函数: y = f(x) — 系统认知市场
       操纵函数: x = g(y) — 系统行为影响市场
       反身性: f 和 g 互为递归，形成自我指涉循环

    2. 本征形式 (von Foerster, 1984):
       "Eigenforms" — 自我指涉系统的定点解
       当系统递归地观察自身，最终收敛到稳定形式（本征值）

    3. 二阶预测 (Bateson, 1972):
       学习如何学习 (deutero-learning)
       系统预测自身的学习效果

实现:
    SelfModel 预测 L-IWM 各模块的未来性能。
    当自预测与实际表现出现系统性偏差时，检测到"自我欺骗"。
    这是反身性循环的闭合——系统拥有"自我模型"。

    网络结构:
        Input (历史性能序列特征) → Linear + ReLU → Hidden (32) → Linear → Output (预测)

    输出:
        - 每个模块的未来性能预测
        - 预测不确定性估计
        - 自我欺骗检测信号
"""

import math
from collections import deque
from typing import Any

import numpy as np


def _he_init(shape: tuple[int, ...]) -> np.ndarray:
    """He 初始化"""
    if len(shape) == 1:
        return np.random.randn(shape[0]) * 0.01
    fan_in = shape[0]
    std = math.sqrt(2.0 / fan_in)
    return np.random.randn(*shape) * std


class _AdamOptimizer:
    """内部 Adam 优化器"""

    def __init__(self, lr: float = 1e-3, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m: dict[str, np.ndarray] = {}
        self.v: dict[str, np.ndarray] = {}
        self.t: int = 0

    def step(self, param_name: str, grad: np.ndarray) -> np.ndarray:
        if param_name not in self.m:
            self.m[param_name] = np.zeros_like(grad)
            self.v[param_name] = np.zeros_like(grad)
        self.t += 1
        self.m[param_name] = self.beta1 * self.m[param_name] + (1 - self.beta1) * grad
        self.v[param_name] = self.beta2 * self.v[param_name] + (1 - self.beta2) * (grad**2)
        m_hat = self.m[param_name] / (1 - self.beta1**self.t)
        v_hat = self.v[param_name] / (1 - self.beta2**self.t)
        return -self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset(self) -> None:
        self.m.clear()
        self.v.clear()
        self.t = 0


class SelfModel:
    """
    自我指涉预测模型。

    预测 L-IWM 各模块的未来性能，检测自我欺骗，
    并实现反身性闭环。

    使用流程:
        self_model = SelfModel(config, input_dim, n_modules)
        predictions = self_model.predict(performance_history)
        self_model.update(performance_history, actual_performance)
        deception = self_model.detect_self_deception()
    """

    MODULE_NAMES = ["RSSM", "RealDataPipeline", "EFE", "Causal", "EWC", "GWS"]

    def __init__(self, config, input_dim: int, n_modules: int = 6):
        """
        Args:
            config: HSRMCConfig 实例
            input_dim: 输入特征维度 (历史序列窗口)
            n_modules: 模块数 (默认 6)
        """
        self.config = config
        self.input_dim = input_dim
        self.n_modules = n_modules
        hidden_dim = config.self_model_hidden_dim

        # 每个模块一个独立的预测头，共享特征提取层
        # 共享层: (input_dim, hidden_dim)
        self.W_shared = _he_init((input_dim, hidden_dim))
        self.b_shared = np.zeros(hidden_dim, dtype=np.float32)

        # 每个模块的输出头: (hidden_dim, 2) → [prediction, uncertainty_log]
        self.W_heads = np.zeros((n_modules, hidden_dim, 2), dtype=np.float32)
        self.b_heads = np.zeros((n_modules, 2), dtype=np.float32)
        for m in range(n_modules):
            self.W_heads[m] = _he_init((hidden_dim, 2))
            self.b_heads[m] = np.zeros(2, dtype=np.float32)

        # 优化器 (共享层 + 所有头)
        self.optimizer = _AdamOptimizer(
            lr=config.self_model_learning_rate,
            beta1=config.self_model_beta1,
            beta2=config.self_model_beta2,
        )

        # ==================== 运行时状态 ====================
        self.train_step: int = 0

        # 预测历史 {模块名: deque of (predicted, actual)}
        self._prediction_history: dict[str, deque] = {
            name: deque(maxlen=config.self_model_history_len) for name in self.MODULE_NAMES
        }

        # 自预测与实际表现的误差历史
        self._prediction_errors: dict[str, deque] = {
            name: deque(maxlen=config.self_model_history_len) for name in self.MODULE_NAMES
        }

        # 自我欺骗信号历史
        self._deception_signals: deque = deque(maxlen=100)

        # 最近的预测缓存
        self._last_predictions: dict[str, float] | None = None

    # ==================== 前向传播 ====================

    def predict(
        self,
        performance_window: dict[str, list[float]],
    ) -> dict[str, dict[str, float]]:
        """
        预测各模块的未来性能。

        对每个模块，使用其最近 performance_window 作为输入，
        通过共享层 + 特定头预测未来性能。

        Args:
            performance_window: {模块名: [最近 N 个性能值]}
                每个列表长度应为 input_dim（不足则 padding）

        Returns:
            {模块名: {"prediction": float, "uncertainty": float}}
        """
        predictions = {}

        for i, name in enumerate(self.MODULE_NAMES):
            seq = performance_window.get(name, [])
            # 构造输入向量
            if len(seq) >= self.input_dim:
                x = np.array(seq[-self.input_dim :], dtype=np.float32)
            else:
                # padding 到 input_dim
                pad = [0.0] * (self.input_dim - len(seq))
                x = np.array(pad + list(seq), dtype=np.float32)

            # 共享层
            h = x @ self.W_shared + self.b_shared
            h = np.maximum(h, 0.0)  # ReLU

            # 模块特定头
            out = h @ self.W_heads[i] + self.b_heads[i]
            pred = float(out[0])
            uncertainty = float(np.exp(out[1]))  # log 不确定性 → 线性

            predictions[name] = {
                "prediction": pred,
                "uncertainty": uncertainty,
            }

        self._last_predictions = {name: pred["prediction"] for name, pred in predictions.items()}

        return predictions

    # ==================== 更新 ====================

    def update(
        self,
        performance_window: dict[str, list[float]],
        actual_performance: dict[str, float],
    ) -> dict[str, float]:
        """
        用实际性能数据更新自模型。

        Args:
            performance_window: {模块名: [最近性能值]} (输入)
            actual_performance: {模块名: 实际性能值} (目标)

        Returns:
            Dict: 训练统计 (loss, 各模块误差等)
        """
        self.train_step += 1
        total_loss = 0.0
        module_errors = {}

        # 计算每个模块的 MSE 损失 + 不确定性正则化
        for i, name in enumerate(self.MODULE_NAMES):
            seq = performance_window.get(name, [])
            if len(seq) < 2:
                continue

            # 构造输入
            if len(seq) >= self.input_dim:
                x = np.array(seq[-self.input_dim :], dtype=np.float32)
            else:
                pad = [0.0] * (self.input_dim - len(seq))
                x = np.array(pad + list(seq), dtype=np.float32)

            actual = actual_performance.get(name, 0.0)

            # 前向传播 (用于梯度计算)
            h = x @ self.W_shared + self.b_shared
            h_act = np.maximum(h, 0.0)
            out = h_act @ self.W_heads[i] + self.b_heads[i]
            predicted = out[0]
            log_uncertainty = out[1]

            # 损失: MSE + 不确定性正则化 (NLL)
            # L = (pred - actual)² / (2σ²) + 0.5*log(σ²)
            uncertainty = np.exp(log_uncertainty)
            mse = (predicted - actual) ** 2
            nll = 0.5 * (mse / (uncertainty + 1e-12) + log_uncertainty)

            # 手工梯度 (因为 NumPy 无 autograd)
            # ∂L/∂pred = (pred - actual) / σ²
            grad_pred = (predicted - actual) / (uncertainty + 1e-12)
            # ∂L/∂log_unc = 0.5 * (1 - (pred - actual)² / σ²)
            grad_log_unc = 0.5 * (1.0 - mse / (uncertainty + 1e-12))

            # 反向传播到头
            grad_W_head = np.outer(h_act, np.array([grad_pred, grad_log_unc]))
            grad_b_head = np.array([grad_pred, grad_log_unc])

            # 反向传播到共享层
            grad_h = self.W_heads[i] @ np.array([grad_pred, grad_log_unc])
            grad_h = grad_h * (h_act > 0).astype(np.float32)  # ReLU 梯度
            grad_W_shared = np.outer(x, grad_h)
            grad_b_shared = grad_h

            # 应用梯度 (使用等效参数更新)
            # 注意: 我们使用简化的 SGD 风格更新，不通过 Adam 优化器
            lr = self.config.self_model_learning_rate * 0.1  # 缩小学习率以稳定

            self.W_heads[i] -= lr * grad_W_head
            self.b_heads[i] -= lr * grad_b_head
            self.W_shared -= lr * grad_W_shared
            self.b_shared -= lr * grad_b_shared

            # 记录
            loss = float(nll)
            total_loss += loss
            module_errors[name] = float(mse)

            # 保存预测历史
            self._prediction_history[name].append((float(predicted), float(actual)))
            self._prediction_errors[name].append(float(mse))

        avg_loss = total_loss / max(len(module_errors), 1)

        # 自我欺骗检测
        deception_signal = self._compute_deception_signal()
        self._deception_signals.append(deception_signal)

        return {
            "loss": avg_loss,
            "module_errors": module_errors,
            "deception_signal": deception_signal,
            "train_step": self.train_step,
        }

    # ==================== 自我欺骗检测 ====================

    def _compute_deception_signal(self) -> float:
        """
        计算自我欺骗信号。

        自我欺骗定义为: 自预测与实际表现的系统性偏差。
        当系统预测自己会表现良好但实际上表现不佳（或反之），
        即出现自我欺骗。

        计算方法:
            1. 收集每个模块最近的 (predicted, actual) 对
            2. 计算加权平均绝对误差 (MAE)
            3. 如果 MAE > 阈值，触发自我欺骗信号

        Returns:
            float: 0~1 之间的欺骗信号值 (0=无欺骗, 1=严重欺骗)
        """
        all_errors = []
        for name in self.MODULE_NAMES:
            recent = list(self._prediction_errors[name])[-20:]
            if recent:
                all_errors.extend(recent)

        if not all_errors:
            return 0.0

        mae = float(np.mean(all_errors))
        threshold = self.config.self_model_deception_threshold

        # 使用 sigmoid 映射到 (0, 1)
        signal = 1.0 / (1.0 + math.exp(-5.0 * (mae - threshold)))
        return signal

    def detect_self_deception(self) -> dict[str, Any]:
        """
        检测并分析自我欺骗状态。

        Returns:
            Dict:
                - "deception_level": 0~1 欺骗等级
                - "is_deceived": bool 是否处于欺骗状态
                - "module_deception": {模块名: 欺骗程度}
                - "prediction_accuracy": {模块名: 平均预测误差}
                - "recommendation": 建议
        """
        deception_level = float(np.mean(self._deception_signals)) if self._deception_signals else 0.0
        is_deceived = deception_level > self.config.self_model_deception_threshold

        module_deception = {}
        prediction_accuracy = {}
        for name in self.MODULE_NAMES:
            errors = list(self._prediction_errors[name])
            if errors:
                mae = float(np.mean(errors))
                module_deception[name] = min(1.0, mae / max(self.config.self_model_deception_threshold, 1e-12))
                prediction_accuracy[name] = mae
            else:
                module_deception[name] = 0.0
                prediction_accuracy[name] = 0.0

        # 生成建议
        if is_deceived:
            # 找出哪些模块被欺骗最严重
            worst_module = max(module_deception.items(), key=lambda x: x[1])
            recommendation = (
                f"检测到自我欺骗 (level={deception_level:.3f})。"
                f"最严重的模块: {worst_module[0]} (deception={worst_module[1]:.3f})。"
                f"建议增加探索率，打破当前认知框架。"
            )
        else:
            recommendation = "自我模型处于健康状态。"

        return {
            "deception_level": deception_level,
            "is_deceived": is_deceived,
            "module_deception": module_deception,
            "prediction_accuracy": prediction_accuracy,
            "recommendation": recommendation,
        }

    # ==================== 反身性效应 ====================

    def compute_reflexivity_effect(
        self,
        meta_params: dict[str, Any],
    ) -> dict[str, float]:
        """
        计算反身性效应对元参数的修正。

        反身性: 系统的自我预测会影响系统的实际表现。
        这里实现为: 如果自模型预测某模块将表现不佳，则增加对其的调整幅度。

        Args:
            meta_params: HyperNetwork 生成的元参数

        Returns:
            {模块名: 修正因子}
        """
        if not self._last_predictions:
            return dict.fromkeys(self.MODULE_NAMES, 1.0)

        corrections = {}
        for name in self.MODULE_NAMES:
            pred = self._last_predictions.get(name, 0.5)
            # 如果预测值低（表现差），增加调整幅度
            correction = 1.0 + self.config.self_model_reflexivity_strength * (0.5 - pred)
            # 限制在 [0.5, 1.5] 范围
            correction = max(0.5, min(1.5, correction))
            corrections[name] = correction

        return corrections

    # ==================== 工具方法 ====================

    def get_reflexivity_vector(self) -> np.ndarray:
        """
        获取当前反身性状态向量 (供 HyperNetwork 上下文使用)。

        Returns:
            np.ndarray (n_modules + 1,): [模块1_欺骗, ..., 模块6_欺骗, 全局欺骗]
        """
        vec = []
        for name in self.MODULE_NAMES:
            errors = list(self._prediction_errors[name])
            if errors:
                vec.append(float(np.mean(errors[-10:])))
            else:
                vec.append(0.0)

        deception = float(np.mean(self._deception_signals)) if self._deception_signals else 0.0
        vec.append(deception)
        return np.array(vec, dtype=np.float32)

    def get_statistics(self) -> dict[str, Any]:
        """获取自模型统计信息"""
        deception_info = self.detect_self_deception()
        return {
            "train_step": self.train_step,
            "deception_level": deception_info["deception_level"],
            "is_deceived": deception_info["is_deceived"],
            "module_accuracy": deception_info["prediction_accuracy"],
            "W_shared_norm": float(np.linalg.norm(self.W_shared)),
        }

    def reset(self) -> None:
        """重置自模型状态"""
        self.train_step = 0
        for name in self.MODULE_NAMES:
            self._prediction_history[name].clear()
            self._prediction_errors[name].clear()
        self._deception_signals.clear()
        self._last_predictions = None
