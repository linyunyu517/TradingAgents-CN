# TradingAgents/hsrc_mc/meta_observer.py
"""
MetaObserver — 二阶元观察器
=============================

理论基础: 二阶控制论 (von Foerster)
    "Observing the observing system" — 系统观察自身的观察过程。

    MetaObserver 不直接观察市场，而是观察 L-IWM 各模块的：
    - 训练动态（梯度范数、损失曲线）
    - 性能指标（预测误差、收益趋势）
    - 模块间关系（学习不平衡、竞争/协作模式）

    这实现了 Heinz von Foerster 的"二阶控制论"：
    认知系统不仅是信息处理系统，更是能够观察自身认知过程的系统。

输出:
    - health_report: Dict[str, Any] — 模块健康状态
    - anomalies: List[Dict] — 检测到的异常
    - intervention_suggestions: List[Dict] — 干预建议
    - gradient_info: Dict[str, float] — 梯度统计
    - regime_info: Dict[str, Any] — 制度状态
"""

import logging
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ModuleGradientStats:
    """单个模块的梯度统计"""

    name: str
    grad_norm: float = 0.0
    grad_mean: float = 0.0
    grad_std: float = 0.0
    param_norm: float = 0.0
    grad_to_param_ratio: float = 0.0  # grad_norm / param_norm

    def to_dict(self) -> dict[str, float]:
        return {
            "grad_norm": self.grad_norm,
            "grad_mean": self.grad_mean,
            "grad_std": self.grad_std,
            "param_norm": self.param_norm,
            "grad_to_param_ratio": self.grad_to_param_ratio,
        }


class MetaObserver:
    """
    二阶元观察器 — 监控 L-IWM 各模块的健康状态。

    核心功能:
        1. 梯度健康监控: 检测梯度爆炸/消失
        2. 损失停滞检测: 检测训练陷入局部最优或停滞
        3. 性能衰减检测: 检测模块性能是否有系统性下降趋势
        4. 制度变化检测: 基于预测误差分布的市场制度变化
        5. 学习不平衡检测: 检测模块间学习速度的不平衡

    使用流程:
        observer = MetaObserver(config)
        observer.observe(l_iwm_manager, gradient_info)
        health = observer.get_health_report()
        anomalies = observer.get_anomalies()
    """

    # 模块名称列表（与 L-IWM 一致）
    MODULE_NAMES = ["RSSM", "RealDataPipeline", "EFE", "Causal", "EWC", "GWS"]

    def __init__(self, config):
        """
        Args:
            config: HSRMCConfig 实例
        """
        self.config = config

        # 损失历史 {module_name: deque}
        self._loss_history: dict[str, deque] = {
            name: deque(maxlen=config.observer_max_history) for name in self.MODULE_NAMES
        }

        # 梯度范数历史 {module_name: deque}
        self._grad_norm_history: dict[str, deque] = {
            name: deque(maxlen=config.observer_max_history) for name in self.MODULE_NAMES
        }

        # 性能指标历史 {module_name: deque}
        self._performance_history: dict[str, deque] = {
            name: deque(maxlen=config.observer_max_history) for name in self.MODULE_NAMES
        }

        # 预测误差历史（用于制度变化检测）
        self._prediction_error_history: deque = deque(maxlen=config.observer_max_history)

        # 检测到的异常列表
        self._anomalies: list[dict[str, Any]] = []

        # 干预建议列表
        self._intervention_suggestions: list[dict[str, Any]] = []

        # 市场制度状态
        self._regime: str = "unknown"
        self._regime_confidence: float = 0.0
        self._regime_history: deque = deque(maxlen=100)

        # 观察步数计数
        self._step: int = 0

        # 健康报告缓存
        self._last_health_report: dict[str, Any] = {}
        self._last_anomalies: list[dict[str, Any]] = []

        # 🔥 [Bug #5 修复] 首次运行检测标志和默认基线
        self._first_run_detected: bool = True
        """首次运行标志，首次 observe() 后设为 False"""
        self._warmup_steps: int = getattr(config, "warmup_runs", 3)
        """预热步数，在此步数内不生成健康报告/异常"""

    # ==================== 主观察入口 ====================

    def observe(
        self,
        module_losses: dict[str, float],
        grads_dict: dict[str, np.ndarray] | None = None,
        module_performance: dict[str, float] | None = None,
        prediction_errors: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        执行一次完整的观察循环。

        Args:
            module_losses: {模块名: 当前损失值}
            grads_dict: {参数名: 梯度数组} (可选)
            module_performance: {模块名: 性能指标} (可选)
            prediction_errors: 预测误差列表 (可选)

        Returns:
            Dict 包含:
                - "health": 健康报告
                - "anomalies": 当前异常列表
                - "regime": 制度状态
                - "gradient_status": 梯度状态摘要
        """
        self._step += 1

        # 🔥 [Bug #5 修复] 首次运行基线检测 — 仅在首次调用时记录日志
        if self._first_run_detected:
            self._first_run_detected = False
            logger.info(f"[MetaObserver] 首次运行，设置基线... (预热 {self._warmup_steps} 步)")

        # 1. 记录损失历史
        for name in self.MODULE_NAMES:
            if name in module_losses:
                self._loss_history[name].append(module_losses[name])

        # 2. 梯度分析
        gradient_stats = {}
        if grads_dict is not None:
            gradient_stats = self._analyze_gradients(grads_dict)
            for name, stats in gradient_stats.items():
                if name in self._grad_norm_history:
                    self._grad_norm_history[name].append(stats.grad_norm)

        # 3. 记录性能
        if module_performance is not None:
            for name in self.MODULE_NAMES:
                if name in module_performance:
                    self._performance_history[name].append(module_performance[name])

        # 4. 记录预测误差
        if prediction_errors is not None:
            self._prediction_error_history.extend(prediction_errors)

        # 5. 异常检测（按配置间隔）— 预热阶段跳过，避免冷启动假阳性
        if self._step > self._warmup_steps and self._step % self.config.observer_health_check_interval == 0:
            self._detect_anomalies(gradient_stats)

        # 6. 制度变化检测 — 预热阶段跳过，防止数据不足导致的误判
        if self._step > self._warmup_steps and len(self._prediction_error_history) >= 10:
            self._detect_regime_change()

        # 7. 生成健康报告
        self._last_health_report = self._generate_health_report(gradient_stats)
        self._last_anomalies = list(self._anomalies)

        # 8. 生成干预建议
        self._intervention_suggestions = self._generate_intervention_suggestions()

        return {
            "health": self._last_health_report,
            "anomalies": self._last_anomalies,
            "regime": self._regime,
            "regime_confidence": self._regime_confidence,
            "gradient_status": {
                name: stats.to_dict() if hasattr(stats, "to_dict") else stats for name, stats in gradient_stats.items()
            },
            "intervention_suggestions": self._intervention_suggestions,
            "step": self._step,
        }

    # ==================== 梯度分析 ====================

    def _analyze_gradients(self, grads_dict: dict[str, np.ndarray]) -> dict[str, ModuleGradientStats]:
        """
        分析梯度状态，按模块分组。

        对于每个参数计算:
            - grad_norm: L2 范数
            - grad_mean: 均值
            - grad_std: 标准差
            - param_norm: 参数 L2 范数
            - grad_to_param_ratio: 梯度/参数比率（指示更新幅度）

        Args:
            grads_dict: {参数名: 梯度数组}

        Returns:
            {模块名: ModuleGradientStats}
        """
        # 类型守卫：如果没有真实梯度张量（如桥接节点传入的简化数据），返回空
        if not grads_dict:
            return {}
        first_val = next(iter(grads_dict.values()))
        if not isinstance(first_val, (np.ndarray, list)):
            # 非张量数据（如桥接节点传入的简化 dict），跳过梯度分析
            logger.debug(f"[MetaObserver] 跳过梯度分析: 数据类型={type(first_val).__name__}")
            return {}

        # 按模块前缀分组
        module_grads: dict[str, list[np.ndarray]] = {name: [] for name in self.MODULE_NAMES}
        {name: [] for name in self.MODULE_NAMES}

        # 参数名到模块的映射规则
        def _param_to_module(param_name: str) -> str:
            pname = param_name.lower()
            if (
                "epi" in pname
                or "prag" in pname
                or "action_emb" in pname
                or "state_proj" in pname
                or "exploration" in pname
            ):
                return "EFE"
            if (
                "gru" in pname
                or "enc" in pname
                or "prior" in pname
                or "post" in pname
                or "dec" in pname
                or "reward" in pname
                or "continue" in pname
            ):
                return "RSSM"
            if "novelty" in pname or "impact" in pname or "urgency" in pname:
                return "GWS"
            if "causal" in pname or "dag" in pname:
                return "Causal"
            if "ewc" in pname or "fisher" in pname:
                return "EWC"
            if "real" in pname or "data" in pname or "pipeline" in pname:
                return "RealDataPipeline"
            return "RSSM"  # default

        for param_name, grad in grads_dict.items():
            module = _param_to_module(param_name)
            if module in module_grads:
                module_grads[module].append(grad.flatten())

        stats = {}
        for module in self.MODULE_NAMES:
            if module_grads[module]:
                all_grads = np.concatenate(module_grads[module])
                grad_norm = float(np.linalg.norm(all_grads))
                stats[module] = ModuleGradientStats(
                    name=module,
                    grad_norm=grad_norm,
                    grad_mean=float(np.mean(all_grads)),
                    grad_std=float(np.std(all_grads)),
                    param_norm=0.0,  # 需要参数值，仅从梯度无法获取
                    grad_to_param_ratio=0.0,
                )
            else:
                stats[module] = ModuleGradientStats(name=module)

        return stats

    # ==================== 异常检测 ====================

    def _detect_anomalies(self, gradient_stats: dict[str, ModuleGradientStats]) -> None:
        """
        多维度异常检测。

        检测类型:
            1. 梯度爆炸: grad_norm > threshold
            2. 损失停滞: 滑动窗口内损失无显著变化
            3. 性能衰减: 滑动窗口内性能斜率 < threshold
            4. 学习不平衡: 模块间梯度范数差异过大
        """
        current_anomalies = []

        # --- 1. 梯度爆炸/消失检测 ---
        for name, stats in gradient_stats.items():
            if stats.grad_norm > self.config.observer_gradient_norm_threshold:
                current_anomalies.append(
                    {
                        "type": "gradient_explosion",
                        "module": name,
                        "severity": "high",
                        "value": float(stats.grad_norm),
                        "threshold": self.config.observer_gradient_norm_threshold,
                        "step": self._step,
                        "message": f"{name} 梯度爆炸: 范数={stats.grad_norm:.4f}",
                    },
                )
            elif stats.grad_norm < 1e-10 and stats.grad_norm > 0:
                current_anomalies.append(
                    {
                        "type": "gradient_vanishing",
                        "module": name,
                        "severity": "medium",
                        "value": float(stats.grad_norm),
                        "step": self._step,
                        "message": f"{name} 梯度消失: 范数={stats.grad_norm:.4e}",
                    },
                )

        # --- 2. 损失停滞检测 ---
        window = self.config.observer_loss_stagnation_window
        tol = self.config.observer_loss_stagnation_tol
        for name in self.MODULE_NAMES:
            hist = list(self._loss_history[name])
            if len(hist) >= window:
                recent = hist[-window:]
                loss_range = max(recent) - min(recent)
                if loss_range < tol:
                    current_anomalies.append(
                        {
                            "type": "loss_stagnation",
                            "module": name,
                            "severity": "medium",
                            "value": float(loss_range),
                            "threshold": tol,
                            "step": self._step,
                            "message": f"{name} 损失停滞: 窗口[{window}]范围={loss_range:.4e}",
                        },
                    )

        # --- 3. 性能衰减检测 ---
        decay_window = self.config.observer_performance_decay_window
        decay_threshold = self.config.observer_performance_decay_threshold
        for name in self.MODULE_NAMES:
            hist = list(self._performance_history[name])
            if len(hist) >= decay_window:
                recent = hist[-decay_window:]
                # 线性回归斜率
                x = np.arange(len(recent))
                y = np.array(recent)
                if np.std(y) > 1e-12:
                    slope = np.polyfit(x, y, 1)[0]
                    if slope < decay_threshold:
                        current_anomalies.append(
                            {
                                "type": "performance_decay",
                                "module": name,
                                "severity": "high",
                                "value": float(slope),
                                "threshold": decay_threshold,
                                "step": self._step,
                                "message": f"{name} 性能衰减: 斜率={slope:.6f}",
                            },
                        )

        # --- 4. 学习不平衡检测 ---
        grad_norms = [stats.grad_norm for stats in gradient_stats.values() if stats.grad_norm > 0]
        if len(grad_norms) >= 2:
            grad_norms_arr = np.array(grad_norms)
            max_norm = np.max(grad_norms_arr)
            min_norm = np.maximum(np.min(grad_norms_arr), 1e-12)
            imbalance_ratio = max_norm / min_norm
            if imbalance_ratio > (1.0 + self.config.observer_learning_imbalance_threshold) / max(
                1e-12, 1.0 - self.config.observer_learning_imbalance_threshold,
            ):
                # 找出不平衡的模块对
                norms_dict = {name: stats.grad_norm for name, stats in gradient_stats.items()}
                sorted_norms = sorted(norms_dict.items(), key=lambda x: x[1])
                if len(sorted_norms) >= 2:
                    current_anomalies.append(
                        {
                            "type": "learning_imbalance",
                            "module": f"{sorted_norms[0][0]} vs {sorted_norms[-1][0]}",
                            "severity": "medium",
                            "value": float(imbalance_ratio),
                            "step": self._step,
                            "message": (
                                f"学习不平衡: "
                                f"min={sorted_norms[0][0]}({sorted_norms[0][1]:.4f}) vs "
                                f"max={sorted_norms[-1][0]}({sorted_norms[-1][1]:.4f}), "
                                f"ratio={imbalance_ratio:.2f}"
                            ),
                        },
                    )

        self._anomalies = current_anomalies

    # ==================== 制度变化检测 ====================

    def _detect_regime_change(self) -> None:
        """
        基于预测误差分布偏移检测市场制度变化。

        方法: 滑动窗口 Kolmogorov-Smirnov 风格检验。
        比较最近窗口与历史窗口的预测误差分布。
        如果分布差异超过灵敏度阈值，触发制度变化信号。
        """
        errors = list(self._prediction_error_history)
        if len(errors) < 20:
            return

        # 分割为近期窗口和历史窗口
        window_size = min(10, len(errors) // 3)
        recent = errors[-window_size:]
        historical = errors[:-window_size]

        if len(historical) < window_size or len(recent) < 3:
            return

        # 比较均值和标准差
        recent_mean = np.mean(recent)
        recent_std = np.std(recent)
        hist_mean = np.mean(historical)
        hist_std = np.std(historical)

        # 归一化偏移检测
        mean_shift = abs(recent_mean - hist_mean) / max(hist_std, 1e-12)
        std_shift = abs(recent_std - hist_std) / max(hist_std, 1e-12)

        # 综合偏移得分
        shift_score = mean_shift + std_shift

        sensitivity = self.config.observer_regime_change_sensitivity * 10.0  # 缩放为可解释范围

        if shift_score > sensitivity:
            # 制度变化
            new_regime = self._classify_regime(recent_mean, recent_std)
            self._regime_history.append(
                {
                    "step": self._step,
                    "regime": new_regime,
                    "shift_score": float(shift_score),
                },
            )

            if new_regime != self._regime:
                self._regime = new_regime
                self._regime_confidence = min(1.0, shift_score / (sensitivity * 2))
                self._anomalies.append(
                    {
                        "type": "regime_change",
                        "module": "system",
                        "severity": "high",
                        "value": float(shift_score),
                        "threshold": sensitivity,
                        "step": self._step,
                        "message": f"市场制度变化: {new_regime} (shift_score={shift_score:.2f})",
                    },
                )
        else:
            # 制度稳定，逐渐降低置信度
            self._regime_confidence *= 0.95

    def _classify_regime(self, error_mean: float, error_std: float) -> str:
        """
        根据预测误差统计特征分类市场制度。

        规则:
            - high_volatility: 误差大 + 标准差大
            - low_volatility: 误差小 + 标准差小
            - trending: 误差有偏（正或负）
            - normal: 其他
        """
        if abs(error_mean) > 0.1 and error_std > 0.05:
            return "high_volatility"
        if error_std < 0.01:
            return "low_volatility"
        if abs(error_mean) > 0.05:
            return "trending"
        return "normal"

    # ==================== 健康报告 ====================

    def _generate_health_report(self, gradient_stats: dict[str, ModuleGradientStats]) -> dict[str, Any]:
        """
        生成模块健康报告。

        Returns:
            Dict:
                - module_health: {模块名: "healthy"|"warning"|"critical"}
                - gradient_summary: {模块名: 梯度统计}
                - loss_summary: {模块名: 当前/平均损失}
                - overall_health: "healthy"|"degraded"|"unhealthy"
        """
        module_health: dict[str, str] = {}
        for name in self.MODULE_NAMES:
            # 基于最近异常判定健康状态
            module_anomalies = [a for a in self._anomalies if a["module"] == name or name in a.get("module", "")]
            severities = [a.get("severity", "low") for a in module_anomalies]
            if "high" in severities:
                module_health[name] = "critical"
            elif "medium" in severities:
                module_health[name] = "warning"
            elif "low" in severities:
                module_health[name] = "degraded"
            else:
                module_health[name] = "healthy"

        # 损失摘要
        loss_summary = {}
        for name in self.MODULE_NAMES:
            hist = list(self._loss_history[name])
            if hist:
                loss_summary[name] = {
                    "current": float(hist[-1]),
                    "mean": float(np.mean(hist)),
                    "min": float(np.min(hist)),
                    "trend": self._compute_trend(hist[-20:]) if len(hist) >= 20 else 0.0,
                }
            else:
                loss_summary[name] = {"current": None, "mean": None, "trend": None}

        # 综合健康状态
        health_values = list(module_health.values())
        if "critical" in health_values:
            overall_health = "unhealthy"
        elif "warning" in health_values or "degraded" in health_values:
            overall_health = "degraded"
        else:
            overall_health = "healthy"

        return {
            "module_health": module_health,
            "gradient_summary": {name: stats.to_dict() for name, stats in gradient_stats.items()},
            "loss_summary": loss_summary,
            "overall_health": overall_health,
            "anomaly_count": len(self._anomalies),
            "regime": self._regime,
            "regime_confidence": self._regime_confidence,
        }

    # ==================== 干预建议 ====================

    def _generate_intervention_suggestions(self) -> list[dict[str, Any]]:
        """
        基于当前状态生成干预建议。

        每条建议包含:
            - type: 干预类型
            - target_module: 目标模块
            - action: 建议动作
            - priority: 优先级 (0-1)
            - rationale: 理由

        干预类型:
            - reduce_lr: 降低学习率（梯度爆炸时）
            - increase_lr: 提高学习率（学习停滞时）
            - reset_module: 重置模块（严重异常时）
            - balance_modules: 平衡模块间学习速度
            - adjust_regularization: 调整正则化强度
        """
        suggestions = []

        for anomaly in self._anomalies:
            if anomaly["type"] == "gradient_explosion":
                suggestions.append(
                    {
                        "type": "reduce_lr",
                        "target_module": anomaly["module"],
                        "action": f"降低 {anomaly['module']} 的学习率 50%",
                        "priority": 0.9,
                        "rationale": f"梯度爆炸 (norm={anomaly['value']:.2f})，需要立即降低学习率",
                    },
                )

            elif anomaly["type"] == "gradient_vanishing":
                suggestions.append(
                    {
                        "type": "increase_lr",
                        "target_module": anomaly["module"],
                        "action": f"提高 {anomaly['module']} 的学习率 20%",
                        "priority": 0.6,
                        "rationale": f"梯度消失 (norm={anomaly['value']:.4e})，需要提高学习率或检查网络结构",
                    },
                )

            elif anomaly["type"] == "loss_stagnation":
                suggestions.append(
                    {
                        "type": "adjust_learning",
                        "target_module": anomaly["module"],
                        "action": f"为 {anomaly['module']} 添加随机扰动",
                        "priority": 0.7,
                        "rationale": f"损失停滞 (范围={anomaly['value']:.4e})，需要打破局部最优",
                    },
                )

            elif anomaly["type"] == "performance_decay":
                suggestions.append(
                    {
                        "type": "adjust_regularization",
                        "target_module": anomaly["module"],
                        "action": f"降低 {anomaly['module']} 的正则化强度",
                        "priority": 0.8,
                        "rationale": f"性能衰减 (斜率={anomaly['value']:.6f})，可能需要减少正则化",
                    },
                )

            elif anomaly["type"] == "learning_imbalance":
                suggestions.append(
                    {
                        "type": "balance_modules",
                        "target_module": anomaly["module"],
                        "action": "调整模块学习率以平衡学习速度",
                        "priority": 0.5,
                        "rationale": f"学习不平衡 (ratio={anomaly['value']:.2f})，需要协调模块间学习速度",
                    },
                )

            elif anomaly["type"] == "regime_change":
                suggestions.append(
                    {
                        "type": "adjust_exploration",
                        "target_module": "system",
                        "action": "增加探索率以适应新市场制度",
                        "priority": 0.85,
                        "rationale": f"市场制度变化到 {anomaly.get('message', 'unknown')}",
                    },
                )

        return suggestions

    # ==================== 工具方法 ====================

    def _compute_trend(self, values: list[float]) -> float:
        """计算简单线性趋势斜率"""
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values))
        y = np.array(values)
        if np.std(y) < 1e-12:
            return 0.0
        return float(np.polyfit(x, y, 1)[0])

    # ==================== 公共 API ====================

    def get_health_report(self) -> dict[str, Any]:
        """获取最新健康报告"""
        return self._last_health_report

    def get_anomalies(self) -> list[dict[str, Any]]:
        """获取当前异常列表"""
        return self._last_anomalies

    def get_intervention_suggestions(self) -> list[dict[str, Any]]:
        """获取当前干预建议"""
        return self._intervention_suggestions

    def get_regime_info(self) -> dict[str, Any]:
        """获取市场制度信息"""
        return {
            "regime": self._regime,
            "confidence": self._regime_confidence,
            "history": list(self._regime_history),
        }

    def get_gradient_stats(self) -> dict[str, Any]:
        """获取梯度统计摘要"""
        summary = {}
        for name in self.MODULE_NAMES:
            hist = list(self._grad_norm_history[name])
            if hist:
                summary[name] = {
                    "current": float(hist[-1]),
                    "mean": float(np.mean(hist)),
                    "max": float(np.max(hist)),
                    "min": float(np.min(hist)),
                }
        return summary

    def get_observation_vector(self) -> np.ndarray:
        """
        将当前观察状态编码为固定维度的向量（供 HyperNetwork 使用）。

        向量结构:
            [模块1_grad_norm, 模块1_loss, 模块1_perf,
             模块2_grad_norm, 模块2_loss, 模块2_perf,
             ...
             全局_regime_onehot, 全局_health_onehot]

        Returns:
            np.ndarray: 观察向量 (shape: [n_features])
        """
        features = []

        for name in self.MODULE_NAMES:
            # 梯度范数 (log 缩放)
            grad_hist = list(self._grad_norm_history[name])
            if grad_hist:
                features.append(math.log10(max(grad_hist[-1], 1e-12)))
            else:
                features.append(0.0)

            # 损失值
            loss_hist = list(self._loss_history[name])
            if loss_hist:
                features.append(float(loss_hist[-1]))
            else:
                features.append(0.0)

            # 性能
            perf_hist = list(self._performance_history[name])
            if perf_hist:
                features.append(float(perf_hist[-1]))
            else:
                features.append(0.0)

        # 制度 one-hot
        regime_map = {"unknown": 0, "normal": 1, "high_volatility": 2, "low_volatility": 3, "trending": 4}
        regime_onehot = [0.0] * 5
        regime_onehot[regime_map.get(self._regime, 0)] = 1.0
        features.extend(regime_onehot)

        # 综合健康 one-hot
        health_map = {"healthy": 0, "degraded": 1, "unhealthy": 2}
        health_val = self._last_health_report.get("overall_health", "healthy")
        health_onehot = [0.0] * 3
        health_onehot[health_map.get(health_val, 0)] = 1.0
        features.extend(health_onehot)

        return np.array(features, dtype=np.float32)

    def reset(self) -> None:
        """重置观察器状态"""
        for name in self.MODULE_NAMES:
            self._loss_history[name].clear()
            self._grad_norm_history[name].clear()
            self._performance_history[name].clear()
        self._prediction_error_history.clear()
        self._anomalies.clear()
        self._intervention_suggestions.clear()
        self._regime = "unknown"
        self._regime_confidence = 0.0
        self._regime_history.clear()
        self._step = 0
        self._last_health_report = {}
        self._last_anomalies = []
