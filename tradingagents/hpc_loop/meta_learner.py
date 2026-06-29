"""
Meta-Learner: Self-Referential Meta-Learning Loop
=================================================
元学习器 — 引入"学习如何学习"的自指循环，实现递归性自我建模。

元学习器是解决"递归性自我建模缺失"的核心。它监控主模型
(HierarchicalGenModel + ActiveInference) 的表现，自动发现模型失效、
调整超参数、建议架构变更。

架构:
```
Meta-Learner (Level 2 — 学习"如何学习")
    │
    │ 元梯度、模型诊断、超参数调优
    │
    ▼
Active Inference Engine (Level 1 — 学习市场)
```

理论基础:
    - Schmidhuber, J. (1987). Evolutionary principles in self-referential learning.
    - Wang, J.X. (2021). Meta-learning in natural and artificial intelligence.
    - Friston, K. et al. (2017). Active inference and learning in the brain.
    - 佛学"自证分" (self-verification) — 认知的认知
"""

import logging
import os  # [R2 Fix M3] JAX fork-safety 依赖 os.environ
from dataclasses import dataclass
from typing import Any

import numpy as np

# [R2 Fix M3] JAX 线程安全防护：提前设 JAX_PLATFORM_NAME 防止 fork()+JAX 线程池死锁
if os.environ.get("JAX_PLATFORM_NAME") is None:
    os.environ["JAX_PLATFORM_NAME"] = ""

try:
    import jax
    import jax.numpy as jnp
    from jax import custom_vjp, grad, jit, lax, random, vmap
    from jax.nn import sigmoid, softmax

    _JAX_AVAILABLE = True
except ImportError:
    _JAX_AVAILABLE = False
    jnp = None
    jax = None
    random = None
    vmap = None
    grad = None
    softmax = None

logger = logging.getLogger("hpc_loop.meta_learner")


# ====================================================================
# 1. MetaLearnerConfig 数据类
# ====================================================================


@dataclass
class MetaLearnerConfig:
    """元学习器配置

    Args:
        meta_window_size: 元学习历史窗口大小（默认 50）
        meta_learning_rate: 元学习器的学习率（默认 0.001）
        decay_detection_threshold: 模型退化检测阈值（默认 2.0）
        n_meta_epochs: 每次元更新迭代次数（默认 5）
        auto_tune_interval: 自动调优周期（默认 100 步）
        cusum_threshold: CUSUM 检测阈值（默认 4.0，单位 sigma）
        cusum_slack: CUSUM 松弛参数 k（默认 0.5）
        error_trend_window: 误差趋势计算的窗口大小（默认 20）
    """

    meta_window_size: int = 50
    meta_learning_rate: float = 0.001
    decay_detection_threshold: float = 2.0
    n_meta_epochs: int = 5
    auto_tune_interval: int = 100
    cusum_threshold: float = 4.0
    cusum_slack: float = 0.5
    error_trend_window: int = 20


# ====================================================================
# 2. ModelDiagnostics 数据类
# ====================================================================


@dataclass
class ModelDiagnostics:
    """模型诊断结果

    Args:
        prediction_error_sequence: 最近 N 步的预测误差序列
        error_trend: 误差趋势（正=退化，负=改进）
        is_degrading: 模型是否在退化
        confidence_interval: 预测误差的置信区间 (lower, upper)
        suggested_lr: 建议的学习率
        suggested_temperature: 建议的 EFE 温度
        architecture_alarm: 是否需要架构变更
        architecture_suggestion: 架构变更建议文本
        meta_free_energy: 元层次自由能
        error_mean: 误差均值
        error_std: 误差标准差
        cusum_alarm: CUSUM 是否触发警报
        n_samples_suggestion: 建议的 MC 采样数
        epistemic_weight_suggestion: 建议的认知权重
    """

    prediction_error_sequence: jnp.ndarray  # shape=(window_size,)
    error_trend: float = 0.0
    is_degrading: bool = False
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    suggested_lr: float = 0.01
    suggested_temperature: float = 0.1
    architecture_alarm: bool = False
    architecture_suggestion: str = ""
    meta_free_energy: float = 0.0
    error_mean: float = 0.0
    error_std: float = 0.0
    cusum_alarm: bool = False
    n_samples_suggestion: int = 50
    epistemic_weight_suggestion: float = 0.5


# ====================================================================
# 3. MetaLearner 核心类
# ====================================================================


class MetaLearner:
    """
    元学习自指循环

    核心功能:
    1. 监控主模型的预测误差历史
    2. 使用 CUSUM 算法检测模型退化
    3. 计算元梯度指导超参数调整
    4. 自动调整主模型的学习率、温度等超参数
    5. 在严重退化时触发架构变更建议
    6. 计算元层次自由能（GENESIS 双循环）

    Args:
        config: MetaLearnerConfig 配置
    """

    def __init__(self, config: MetaLearnerConfig | None = None):
        self.config = config or MetaLearnerConfig()

        # 误差历史缓冲区（滑动窗口）
        self._error_buffer: list[float] = []

        # 元梯度跟踪器
        self._meta_gradient_history: dict[str, list[float]] = {
            "lr": [],
            "temperature": [],
            "n_samples": [],
            "epistemic_weight": [],
        }

        # CUSUM 状态
        self._cusum_pos: float = 0.0
        self._cusum_neg: float = 0.0
        self._cusum_history: list[float] = []

        # 元学习状态
        self._step_counter: int = 0
        self._current_lr: float = 0.01
        self._current_temperature: float = 0.1
        self._current_n_samples: int = 50
        self._current_epistemic_weight: float = 0.5
        self._architecture_alarm_count: int = 0
        self._last_auto_tune_step: int = 0

        # 性能跟踪
        self._diagnostics_history: list[ModelDiagnostics] = []

        logger.info(
            f"[MetaLearner] 初始化完成: window={self.config.meta_window_size}, lr={self.config.meta_learning_rate}",
        )

    # ------------------------------------------------------------------
    # 误差记录
    # ------------------------------------------------------------------

    def record_error(self, error: float, step: int | None = None) -> dict[str, float]:
        """
        记录预测误差到滑动窗口缓冲区

        Args:
            error: 当前步的预测误差标量
            step: 可选的时间步（用于对齐）

        Returns:
            dict: 当前窗口的基本统计
                mean: 均值
                std: 标准差
                trend: 趋势斜率
                n: 窗口大小
        """
        if step is not None:
            self._step_counter = step
        else:
            self._step_counter += 1

        # 添加到缓冲区
        self._error_buffer.append(error)

        # 保持窗口大小
        if len(self._error_buffer) > self.config.meta_window_size:
            self._error_buffer.pop(0)

        # 计算统计
        stats = self._compute_window_stats()

        return stats

    def _compute_window_stats(self) -> dict[str, float]:
        """计算当前窗口的统计量"""
        if not self._error_buffer:
            return {"mean": 0.0, "std": 0.0, "trend": 0.0, "n": 0}

        if _JAX_AVAILABLE:
            arr = jnp.array(self._error_buffer)
            mean = float(jnp.mean(arr))
            std = float(jnp.std(arr))
            n = len(self._error_buffer)
        else:
            arr = np.array(self._error_buffer)
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            n = len(arr)

        # 计算趋势（线性回归斜率）
        trend = self._compute_trend()

        return {
            "mean": mean,
            "std": std,
            "trend": trend,
            "n": n,
        }

    def _compute_trend(self) -> float:
        """
        计算误差趋势（线性回归斜率）

        slope = (n*Σ(xy) - Σx*Σy) / (n*Σ(x²) - (Σx)²)

        Returns:
            float: 趋势斜率（正=恶化，负=改善）
        """
        n = len(self._error_buffer)
        if n < 3:
            return 0.0

        try:
            if _JAX_AVAILABLE:
                x = jnp.arange(n, dtype=jnp.float32)
                y = jnp.array(self._error_buffer, dtype=jnp.float32)
                sum_x = jnp.sum(x)
                sum_y = jnp.sum(y)
                sum_xy = jnp.sum(x * y)
                sum_x2 = jnp.sum(x**2)
                denom = n * sum_x2 - sum_x**2
                slope = jnp.where(
                    jnp.abs(denom) > 1e-10,
                    (n * sum_xy - sum_x * sum_y) / denom,
                    0.0,
                )
                return float(slope)
            x = np.arange(n, dtype=np.float32)
            y = np.array(self._error_buffer, dtype=np.float32)
            sum_x = np.sum(x)
            sum_y = np.sum(y)
            sum_xy = np.sum(x * y)
            sum_x2 = np.sum(x**2)
            denom = n * sum_x2 - sum_x**2
            slope = (n * sum_xy - sum_x * sum_y) / denom if abs(denom) > 1e-10 else 0.0
            return float(slope)
        except Exception as _slope_err:
            logger.warning(f"[MetaLearner] 斜率估计异常，返回 0.0: {_slope_err}")
            return 0.0

    # ------------------------------------------------------------------
    # CUSUM 变化检测
    # ------------------------------------------------------------------

    def _cusum_update(self, error: float, target: float, slack: float) -> tuple[float, float]:
        """
        CUSUM (Cumulative Sum) 单步更新

        公式:
            S_pos = max(0, S_pos_prev + error - target - slack)
            S_neg = min(0, S_neg_prev + error - target + slack)

        Args:
            error: 当前误差
            target: 目标均值
            slack: 松弛参数 k

        Returns:
            (S_pos, S_neg): 正负累积和
        """
        self._cusum_pos = max(0.0, self._cusum_pos + error - target - slack)
        self._cusum_neg = min(0.0, self._cusum_neg + error - target + slack)
        self._cusum_history.append(self._cusum_pos)
        if len(self._cusum_history) > self.config.meta_window_size:
            self._cusum_history.pop(0)
        return self._cusum_pos, self._cusum_neg

    def _detect_cusum_alarm(self) -> bool:
        """检测 CUSUM 是否超过阈值"""
        threshold = self.config.cusum_threshold * self._estimate_error_std()
        return self._cusum_pos > threshold

    def _estimate_error_std(self) -> float:
        """估计误差标准差"""
        if len(self._error_buffer) < 5:
            return 1.0
        if _JAX_AVAILABLE:
            return float(jnp.std(jnp.array(self._error_buffer[-20:])))
        return float(np.std(self._error_buffer[-20:]))

    # ------------------------------------------------------------------
    # 核心诊断方法
    # ------------------------------------------------------------------

    def diagnose(self) -> ModelDiagnostics:
        """
        执行完整的模型诊断

        步骤:
        1. 计算当前窗口误差统计
        2. CUSUM 变化检测
        3. 误差趋势分析
        4. 自动超参数建议
        5. 架构变更检测

        Returns:
            ModelDiagnostics: 完整的诊断结果
        """
        if not self._error_buffer:
            # 没有数据时的默认诊断
            return ModelDiagnostics(
                prediction_error_sequence=jnp.array([]) if _JAX_AVAILABLE else np.array([]),
            )

        # ---- 1. 基础统计 ----
        n = len(self._error_buffer)
        if _JAX_AVAILABLE:
            arr = jnp.array(self._error_buffer, dtype=jnp.float32)
            error_mean = float(jnp.mean(arr))
            error_std = float(jnp.std(arr))
        else:
            arr = np.array(self._error_buffer, dtype=np.float32)
            error_mean = float(np.mean(arr))
            error_std = float(np.std(arr))

        # ---- 2. 趋势分析 ----
        trend = self._compute_trend()

        # ---- 3. CUSUM 检测 ----
        target = error_mean  # 当前均值作为目标
        slack = self.config.cusum_slack * error_std if error_std > 0 else 0.1
        for e in self._error_buffer[-min(20, n) :]:
            self._cusum_update(e, target, slack)
        cusum_alarm = self._detect_cusum_alarm()

        # ---- 4. 退化判断 ----
        # 退化信号: 正趋势 + CUSUM 警报 + 误差偏高
        is_degrading = (
            (trend > 0.001 and cusum_alarm)
            or (trend > self.config.decay_detection_threshold * 0.01)
            or (error_std > 2.0 * (self._estimate_error_std() or 1.0))
        )

        # ---- 5. 置信区间 ----
        ci_lower = error_mean - 1.96 * error_std
        ci_upper = error_mean + 1.96 * error_std

        # ---- 6. 超参数建议 ----
        suggested_lr = self._suggest_lr(error_mean, error_std, trend)
        suggested_temperature = self._suggest_temperature(error_std, trend)
        n_samples_suggestion = self._suggest_n_samples(error_std)
        epistemic_weight_suggestion = self._suggest_epistemic_weight(trend)

        # ---- 7. 架构变更检测 ----
        architecture_alarm = False
        architecture_suggestion = ""

        if is_degrading and len(self._diagnostics_history) >= 5:
            recent_diagnostics = self._diagnostics_history[-5:]
            persistent_degradation = sum(1 for d in recent_diagnostics if d.is_degrading)
            if persistent_degradation >= 4:
                architecture_alarm = True
                architecture_suggestion = self._generate_architecture_suggestion()

        # ---- 8. 元自由能 ----
        meta_fe = self.compute_meta_free_energy()

        # ---- 构建诊断结果 ----
        diagnostics = ModelDiagnostics(
            prediction_error_sequence=arr if _JAX_AVAILABLE else jnp.array(arr),
            error_trend=trend,
            is_degrading=is_degrading,
            confidence_interval=(ci_lower, ci_upper),
            suggested_lr=suggested_lr,
            suggested_temperature=suggested_temperature,
            architecture_alarm=architecture_alarm,
            architecture_suggestion=architecture_suggestion,
            meta_free_energy=meta_fe,
            error_mean=error_mean,
            error_std=error_std,
            cusum_alarm=cusum_alarm,
            n_samples_suggestion=n_samples_suggestion,
            epistemic_weight_suggestion=epistemic_weight_suggestion,
        )

        self._diagnostics_history.append(diagnostics)
        if len(self._diagnostics_history) > self.config.meta_window_size:
            self._diagnostics_history.pop(0)

        return diagnostics

    # ------------------------------------------------------------------
    # 超参数建议方法
    # ------------------------------------------------------------------

    def _suggest_lr(self, error_mean: float, error_std: float, trend: float) -> float:
        """
        基于误差分布建议学习率

        规则:
        - 误差方差大 → 减小学习率（稳定更新）
        - 误差系统性偏高 → 减小学习率
        - 误差趋势向上 → 减小学习率
        - 误差趋势向下且方差小 → 可适当增大学习率
        """
        lr = self._current_lr

        # 误差方差因子
        if error_std > 0.1:
            lr *= 0.8  # 高方差 → 减小学习率
        elif error_std < 0.01:
            lr *= 1.05  # 低方差 → 微增

        # 趋势因子
        if trend > 0.001:
            # 误差增大 → 减速
            lr *= 0.9
        elif trend < -0.001:
            # 误差减小 → 可稍微加速
            lr *= 1.02

        # 误差绝对值因子
        if error_mean > 0.5:
            lr *= 0.7  # 高误差 → 保守更新
        elif error_mean < 0.05:
            lr *= 1.03  # 低误差 → 微增

        # 约束范围
        lr = max(1e-5, min(0.1, lr))

        self._current_lr = lr
        return lr

    def _suggest_temperature(self, error_std: float, trend: float) -> float:
        """
        建议 EFE 温度

        规则:
        - 误差在增大 → 降低温度（更保守，减少探索）
        - 误差方差大 → 降低温度
        - 误差稳定且小 → 可升高温度（增加探索）
        """
        temp = self._current_temperature

        if trend > 0.001:
            temp *= 0.85  # 恶化 → 保守
        elif trend < -0.001:
            temp *= 1.05  # 改善 → 可稍微探索

        if error_std > 0.1:
            temp *= 0.9  # 高不确定 → 保守
        elif error_std < 0.01:
            temp *= 1.05  # 低不确定 → 探索

        temp = max(0.01, min(0.5, temp))
        self._current_temperature = temp
        return temp

    def _suggest_n_samples(self, error_std: float) -> int:
        """
        建议 MC 采样数

        规则:
        - 误差方差大 → 增大 n_samples（更多采样减少方差）
        - 误差方差小 → 可减少 n_samples（节省计算）
        """
        if error_std > 0.1:
            n = 100
        elif error_std > 0.05:
            n = 75
        elif error_std < 0.01:
            n = 30
        else:
            n = 50

        self._current_n_samples = n
        return n

    def _suggest_epistemic_weight(self, trend: float) -> float:
        """
        建议认知探索权重

        规则:
        - 误差增大 → 增加认知探索（更多信息寻求）
        - 误差减小 → 减少认知探索（更多利用）
        """
        weight = self._current_epistemic_weight

        if trend > 0.001:
            weight = min(1.0, weight * 1.1)  # 恶化 → 更多探索
        elif trend < -0.001:
            weight = max(0.1, weight * 0.95)  # 改善 → 更多利用

        self._current_epistemic_weight = weight
        return weight

    def _generate_architecture_suggestion(self) -> str:
        """
        生成架构变更建议

        基于诊断历史生成具体的架构改进建议。
        """
        suggestions = []
        self._architecture_alarm_count += 1

        # 分析误差模式
        if len(self._error_buffer) >= 20:
            # 看最近误差的方差变化
            recent = self._error_buffer[-20:]
            if _JAX_AVAILABLE:
                recent_arr = jnp.array(recent)
                recent_std = float(jnp.std(recent_arr))
                recent_mean = float(jnp.mean(recent_arr))
            else:
                recent_std = float(np.std(recent))
                recent_mean = float(np.mean(recent))

            # 高误差 + 高方差 → 可能缺少关键的隐状态维度
            if recent_mean > 0.3 and recent_std > 0.2:
                suggestions.append(
                    "当前4个regime无法捕捉所有市场状态，建议扩展到6个 (添加'sideways_up', 'sideways_down')",
                )

            # 误差持续上升 → 需要更快的适应机制
            if len(self._diagnostics_history) >= 10:
                trends = [d.error_trend for d in self._diagnostics_history[-10:]]
                avg_trend = float(jnp.mean(jnp.array(trends))) if _JAX_AVAILABLE else float(np.mean(trends))
                if avg_trend > 0.01:
                    suggestions.append(
                        "误差持续上升超过10步，建议启用在线参数更新 (online learning rate > 0) 或增加隐状态记忆长度",
                    )

            # 高频振荡 → 需要更精细的时间尺度
            if len(recent) >= 10:
                signs = [1 if e > recent_mean else 0 for e in recent[-10:]]
                changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
                if changes >= 8:
                    suggestions.append(
                        "检测到高频误差振荡，建议增加更低层 (Level -1: tick-level) 或提高 temporal_precision",
                    )

        # 默认建议
        if not suggestions:
            suggestions.append(
                f"检测到持续退化 (警报 #{self._architecture_alarm_count})，"
                f"建议重新初始化最高层 (strategic level) 的参数并降低学习率",
            )

        return "\n".join(suggestions[:3])  # 最多3条建议

    # ------------------------------------------------------------------
    # 元梯度计算
    # ------------------------------------------------------------------

    def compute_meta_gradient(
        self,
        params: dict[str, Any],
        history: jnp.ndarray,
    ) -> dict[str, jnp.ndarray]:
        """
        计算"元梯度"——主模型在过去 N 步的预测误差对超参数的导数

        使用 JAX 的二阶自动微分 (grad within grad):
            meta_loss = lambda lr: sum(main_model.evaluate_with_lr(lr))
            meta_grad = jax.grad(meta_loss)(current_lr)

        NOTE: 元梯度计算使用纯 JAX 操作避免 tracer 类型错误。
        内层 loss 函数的输入是 jnp.ndarray，内部全部使用 jnp 操作。

        Args:
            params: 当前超参数字典 {"lr": float, "temperature": float, ...}
            history: 历史误差序列, shape=(window_size,)

        Returns:
            dict: 各超参数的元梯度
        """
        if not _JAX_AVAILABLE:
            return {k: jnp.array(0.0) for k in params}

        meta_grads = {}

        # ---- 对学习率的元梯度 ----
        # 元损失: L(lr) = Σ_t ||error_t · exp(-lr · t)||²
        # lr 越高，近期误差权重越大（更快遗忘）
        def _meta_loss_lr(lr_jax: jnp.ndarray) -> jnp.ndarray:
            """计算关于学习率的元损失 (纯 JAX)"""
            lr_val = lr_jax.astype(jnp.float32)
            t = jnp.arange(history.shape[0], dtype=jnp.float32)
            decay = jnp.exp(-lr_val * t)
            weighted = history * decay
            return jnp.sum(weighted**2)

        lr_input = jnp.asarray(params.get("lr", 0.01), dtype=jnp.float32)
        meta_grads["lr"] = grad(_meta_loss_lr)(lr_input)

        # ---- 对温度的元梯度 ----
        # 温度高 → 探索多 → 误差方差可能增大
        def _meta_loss_temp(temp_jax: jnp.ndarray) -> jnp.ndarray:
            """计算关于温度的元损失 (纯 JAX)"""
            temp_val = temp_jax.astype(jnp.float32)
            var_term = temp_val * jnp.var(history)
            return jnp.sum(history**2) + var_term

        temp_input = jnp.asarray(params.get("temperature", 0.1), dtype=jnp.float32)
        meta_grads["temperature"] = grad(_meta_loss_temp)(temp_input)

        # ---- 对 n_samples 的元梯度 ----
        def _meta_loss_samples(n_jax: jnp.ndarray) -> jnp.ndarray:
            """计算关于采样数的元损失 (纯 JAX)"""
            n_val = jnp.maximum(jnp.round(n_jax), 1.0)
            variance_reduction = 1.0 / jnp.sqrt(n_val)
            compute_cost = n_val * 0.001
            return jnp.var(history) * variance_reduction + compute_cost

        n_input = jnp.asarray(params.get("n_samples", 50), dtype=jnp.float32)
        meta_grads["n_samples"] = grad(_meta_loss_samples)(n_input)

        # 记录元梯度历史
        for k, v in meta_grads.items():
            if k in self._meta_gradient_history:
                self._meta_gradient_history[k].append(float(v))
                if len(self._meta_gradient_history[k]) > self.config.meta_window_size:
                    self._meta_gradient_history[k].pop(0)

        return meta_grads

    # ------------------------------------------------------------------
    # 元更新应用
    # ------------------------------------------------------------------

    def apply_meta_update(
        self,
        engine: Any,
        diagnostics: ModelDiagnostics,
    ) -> dict[str, Any]:
        """
        基于元梯度和诊断结果自动调整主模型超参数

        调整目标:
        - learning_rate: 主模型的学习率
        - temperature: EFE 温度
        - epistemic_weight: 认知探索权重
        - n_samples: MC 采样数

        Args:
            engine: ActiveInference 引擎实例（需有对应属性）
            diagnostics: 当前诊断结果

        Returns:
            dict: 应用的更新
        """
        applied_updates = {}

        if not _JAX_AVAILABLE:
            return {"status": "jax_unavailable"}

        # ---- 1. 检查是否是自动调优周期 ----
        is_tune_step = self._step_counter - self._last_auto_tune_step >= self.config.auto_tune_interval

        if not is_tune_step and not diagnostics.is_degrading:
            return {"status": "skipped", "reason": "not_tune_step"}

        # ---- 2. 应用学习率更新 ----
        if hasattr(engine, "learning_rate") or hasattr(engine, "_learning_rate"):
            old_lr = getattr(engine, "learning_rate", getattr(engine, "_learning_rate", 0.01))
            new_lr = diagnostics.suggested_lr

            # 约束：不在一轮调整超过50%
            max_change = old_lr * 0.5
            lr_change = new_lr - old_lr
            lr_change = max(-max_change, min(max_change, lr_change))
            final_lr = old_lr + lr_change

            if hasattr(engine, "learning_rate"):
                engine.learning_rate = final_lr
            elif hasattr(engine, "_learning_rate"):
                engine._learning_rate = final_lr

            applied_updates["learning_rate"] = {
                "old": old_lr,
                "new": final_lr,
                "suggested": new_lr,
            }

        # ---- 3. 应用温度更新 ----
        if hasattr(engine, "temperature") or hasattr(engine, "_temperature"):
            old_temp = getattr(engine, "temperature", getattr(engine, "_temperature", 0.1))
            new_temp = diagnostics.suggested_temperature

            max_change = old_temp * 0.5
            temp_change = new_temp - old_temp
            temp_change = max(-max_change, min(max_change, temp_change))
            final_temp = old_temp + temp_change

            if hasattr(engine, "temperature"):
                engine.temperature = final_temp
            elif hasattr(engine, "_temperature"):
                engine._temperature = final_temp

            applied_updates["temperature"] = {
                "old": old_temp,
                "new": final_temp,
                "suggested": new_temp,
            }

        # ---- 4. 应用 n_samples 更新 ----
        if hasattr(engine, "n_samples"):
            old_n = engine.n_samples
            engine.n_samples = diagnostics.n_samples_suggestion
            applied_updates["n_samples"] = {
                "old": old_n,
                "new": engine.n_samples,
            }

        # ---- 5. 应用 epistemic_weight 更新 ----
        if hasattr(engine, "epistemic_weight"):
            old_w = engine.epistemic_weight
            engine.epistemic_weight = diagnostics.epistemic_weight_suggestion
            applied_updates["epistemic_weight"] = {
                "old": old_w,
                "new": engine.epistemic_weight,
            }

        self._last_auto_tune_step = self._step_counter

        logger.info(
            f"[MetaLearner] 元更新应用: "
            f"lr={applied_updates.get('learning_rate', {}).get('new', 'N/A')}, "
            f"temp={applied_updates.get('temperature', {}).get('new', 'N/A')}",
        )

        return {
            "status": "applied",
            "updates": applied_updates,
            "diagnostics": diagnostics,
        }

    # ------------------------------------------------------------------
    # 元层次自由能
    # ------------------------------------------------------------------

    def compute_meta_free_energy(self) -> float:
        """
        计算元层次自由能

        F_meta = Σ 预测误差(Level 1的表现) + KL(元先验 || 元后验)

        这是 GENESIS + Meta-Learning 双循环自由能的核心。
        元层次自由能量化了"元学习器对主模型表现的不确定性"。

        分解:
        1. 误差项: Σ 加权预测误差（主模型的不确定性）
        2. 复杂度项: KL(元先验 || 元后验)（元学习器自身的更新代价）

        Returns:
            float: 元层次自由能
        """
        if not self._error_buffer:
            return 0.0

        n = len(self._error_buffer)
        if _JAX_AVAILABLE:
            arr = jnp.array(self._error_buffer, dtype=jnp.float32)
        else:
            arr = np.array(self._error_buffer, dtype=np.float32)

        # ---- 1. 误差项 ----
        # 越近的误差权重越大（指数衰减）
        if _JAX_AVAILABLE:
            weights = jnp.exp(-0.1 * jnp.arange(n, dtype=jnp.float32)[::-1])
            weighted_errors = weights * arr
            error_term = float(jnp.sum(weighted_errors**2)) / float(jnp.sum(weights) + 1e-8)
        else:
            weights = np.exp(-0.1 * np.arange(n, dtype=np.float32)[::-1])
            weighted_errors = weights * arr
            error_term = float(np.sum(weighted_errors**2)) / float(np.sum(weights) + 1e-8)

        # ---- 2. 复杂度项 ----
        # KL(元后验 || 元先验)
        # 后验 = 当前超参数配置，先验 = 默认超参数
        # 近似：超参数偏离默认值的程度

        default_lr = 0.01
        default_temp = 0.1
        default_n = 50
        default_epistemic = 0.5

        # 超参数偏离的加权和
        lr_dev = (self._current_lr - default_lr) / default_lr
        temp_dev = (self._current_temperature - default_temp) / default_temp
        n_dev = (self._current_n_samples - default_n) / default_n
        epistemic_dev = (self._current_epistemic_weight - default_epistemic) / default_epistemic

        complexity_term = 0.25 * (lr_dev**2 + temp_dev**2 + n_dev**2 + epistemic_dev**2)

        # ---- 3. 总元自由能 ----
        meta_free_energy = error_term + complexity_term

        return float(meta_free_energy)

    # ------------------------------------------------------------------
    # 自我质疑报告（佛学"自证分"）
    # ------------------------------------------------------------------

    def self_question_report(self) -> str:
        """
        生成自我质疑报告

        对应佛学"自证分" (svasaṃvitti) — 认知的自我认知。
        元学习器不仅要学习，还要能"观察自己的学习过程"并质疑自己的结论。

        报告包含:
        1. 当前性能评估
        2. 超参数状态
        3. 检测到的异常
        4. 架构建议
        5. 元学习器自身的反思

        Returns:
            str: 格式化的自我质疑报告
        """
        lines = []
        lines.append("=" * 65)
        lines.append("  Meta-Learner 自我质疑报告 (自证分)")
        lines.append("=" * 65)
        lines.append(f"  步数: {self._step_counter}")
        lines.append("")

        # ---- 1. 当前状态 ----
        stats = self._compute_window_stats()
        lines.append("  [当前性能]")
        lines.append(f"    误差均值:     {stats['mean']:.6f}")
        lines.append(f"    误差标准差:   {stats['std']:.6f}")
        lines.append(f"    误差趋势:     {stats['trend']:+.6f}/步")
        lines.append(f"    窗口大小:     {stats['n']} 步")
        lines.append("")

        # ---- 2. 退化检测 ----
        lines.append("  [退化检测]")
        lines.append(f"    CUSUM 统计量: {self._cusum_pos:.4f}")
        lines.append(f"    阈值:         {self.config.cusum_threshold:.1f}σ")
        lines.append(f"    CUSUM 警报:   {'⚠️ 触发' if self._detect_cusum_alarm() else '✅ 正常'}")
        lines.append("")

        # ---- 3. 超参数状态 ----
        lines.append("  [当前超参数]")
        lines.append(f"    学习率:        {self._current_lr:.6f}")
        lines.append(f"    EFE 温度:      {self._current_temperature:.4f}")
        lines.append(f"    MC 采样数:     {self._current_n_samples}")
        lines.append(f"    认知权重:      {self._current_epistemic_weight:.4f}")
        lines.append("")

        # ---- 4. 诊断结论 ----
        if self._diagnostics_history:
            latest = self._diagnostics_history[-1]
            lines.append("  [诊断结论]")

            if latest.is_degrading:
                lines.append("    ⚠️ 模型正在退化！")
            else:
                lines.append("    ✅ 模型表现稳定")

            lines.append(f"    元自由能:     {latest.meta_free_energy:.6f}")
            lines.append(f"    建议学习率:   {latest.suggested_lr:.6f}")
            lines.append(f"    建议温度:     {latest.suggested_temperature:.4f}")

            if latest.architecture_alarm:
                lines.append("")
                lines.append("  [🔴 架构变更警报]")
                lines.append(f"    警报次数:    {self._architecture_alarm_count}")
                for line in latest.architecture_suggestion.split("\n"):
                    lines.append(f"    → {line}")
            lines.append("")

        # ---- 5. 元学习自指反思 ----
        lines.append("  [元学习自指反思]")
        lines.append(f"    元梯度(LR):   {self._get_latest_meta_gradient('lr'):+.8f}")

        # 诊断元学习器自身的表现
        n_diag = len(self._diagnostics_history)
        if n_diag >= 10:
            degradation_ratio = sum(1 for d in self._diagnostics_history[-10:] if d.is_degrading) / 10.0
            lines.append(f"    近期退化率:   {degradation_ratio:.1%}")

            if degradation_ratio > 0.7:
                lines.append("    自评: 元学习器可能未能有效逆转退化趋势，")
                lines.append("          建议检查 meta_learning_rate 或增加 auto_tune_interval")
            elif degradation_ratio > 0.3:
                lines.append("    自评: 退化趋势部分得到控制，但仍有改进空间")
            else:
                lines.append("    自评: 元学习器有效维持了模型稳定性")
        else:
            lines.append(f"    诊断样本:    {n_diag}/10（需要更多数据评估元学习器效果）")
        lines.append("")

        # ---- 6. 佛学"自证分"引用 ----
        lines.append("  [自证分]")
        lines.append('  "识的自证分是识的自我认知能力，使得认知不仅知道对象，也知道自己在认知。"')
        lines.append("  — 陈那《集量论》")
        lines.append("=" * 65)

        return "\n".join(lines)

    def _get_latest_meta_gradient(self, key: str) -> float:
        """获取最近的元梯度值"""
        if key in self._meta_gradient_history:
            hist = self._meta_gradient_history[key]
            return hist[-1] if hist else 0.0
        return 0.0

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def get_error_buffer(self) -> list[float]:
        """获取误差缓冲区"""
        return list(self._error_buffer)

    def get_diagnostics_history(self) -> list[ModelDiagnostics]:
        """获取诊断历史"""
        return list(self._diagnostics_history)

    def get_current_hyperparams(self) -> dict[str, Any]:
        """获取当前超参数"""
        return {
            "learning_rate": self._current_lr,
            "temperature": self._current_temperature,
            "n_samples": self._current_n_samples,
            "epistemic_weight": self._current_epistemic_weight,
            "step": self._step_counter,
            "meta_free_energy": self.compute_meta_free_energy(),
        }

    def reset(self) -> None:
        """重置元学习器状态"""
        self._error_buffer.clear()
        self._meta_gradient_history = {k: [] for k in self._meta_gradient_history}
        self._cusum_pos = 0.0
        self._cusum_neg = 0.0
        self._cusum_history.clear()
        self._step_counter = 0
        self._current_lr = 0.01
        self._current_temperature = 0.1
        self._current_n_samples = 50
        self._current_epistemic_weight = 0.5
        self._architecture_alarm_count = 0
        self._last_auto_tune_step = 0
        self._diagnostics_history.clear()
        logger.info("[MetaLearner] 已重置")


# ====================================================================
# 4. 便捷函数
# ====================================================================


def create_default_meta_learner() -> MetaLearner:
    """
    创建默认配置的元学习器

    Returns:
        MetaLearner: 使用默认 MetaLearnerConfig 的实例
    """
    config = MetaLearnerConfig(
        meta_window_size=50,
        meta_learning_rate=0.001,
        decay_detection_threshold=2.0,
        n_meta_epochs=5,
        auto_tune_interval=100,
        cusum_threshold=4.0,
        cusum_slack=0.5,
        error_trend_window=20,
    )
    return MetaLearner(config)


def create_fast_meta_learner() -> MetaLearner:
    """
    创建快速适应的元学习器（对变化更敏感）

    Returns:
        MetaLearner: 高灵敏度的元学习器
    """
    config = MetaLearnerConfig(
        meta_window_size=30,  # 更短的窗口，更快反应
        meta_learning_rate=0.005,  # 更高的元学习率
        decay_detection_threshold=1.5,  # 更低的退化阈值
        n_meta_epochs=3,
        auto_tune_interval=50,  # 更频繁的调优
        cusum_threshold=3.0,  # 更低的 CUSUM 阈值
        cusum_slack=0.3,  # 更小的松弛
        error_trend_window=10,  # 更短的趋势窗口
    )
    return MetaLearner(config)


# ====================================================================
# 5. 辅助演示/测试函数
# ====================================================================


def simulate_degradation_and_diagnose() -> str:
    """
    演示函数：模拟模型退化过程并运行元学习器诊断

    生成人工误差序列，逐步增大误差，检测元学习器能否发现退化。

    Returns:
        str: 诊断报告
    """
    meta = create_default_meta_learner()

    # 阶段 1: 正常表现（误差小、稳定）
    for i in range(50):
        error = 0.05 + np.random.randn() * 0.02
        meta.record_error(error, i)

    # 阶段 2: 渐进退化（误差缓慢增大）
    for i in range(50, 100):
        degradation = (i - 50) * 0.002  # 线性增大
        error = 0.05 + degradation + np.random.randn() * 0.03
        meta.record_error(error, i)

    # 阶段 3: 严重退化（误差激增）
    for i in range(100, 120):
        error = 0.3 + np.random.randn() * 0.1
        meta.record_error(error, i)

    # 执行诊断
    meta.diagnose()
    report = meta.self_question_report()

    return report


# ====================================================================
# __all__ 导出
# ====================================================================

__all__ = [
    "MetaLearner",
    "MetaLearnerConfig",
    "ModelDiagnostics",
    "create_default_meta_learner",
    "create_fast_meta_learner",
    "simulate_degradation_and_diagnose",
]
