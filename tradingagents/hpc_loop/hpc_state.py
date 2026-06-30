# TradingAgents/hpc_loop/hpc_state.py
"""
HPC-Loop 扩展状态定义

定义 HPC-Loop 在 LangGraph State 中新增的所有状态字段，
以及内部使用的数据结构。
"""

from dataclasses import dataclass, field
from typing import Any

# ==================== 市场隐状态 ====================


@dataclass
class MarketLatentState:
    """
    市场隐状态 (多尺度解耦表征)

    对应生成模型内部维护的层级潜变量表征。
    每个变量维护为概率分布参数。
    """

    # 离散潜变量：市场体制
    market_regime_probs: dict[str, float] = field(
        default_factory=lambda: {
            "bull": 0.25,
            "bear": 0.25,
            "range_bound": 0.25,
            "crisis": 0.25,
        },
    )
    """市场体制概率分布 P(market_regime)"""

    # 波动率状态
    volatility_state_probs: dict[str, float] = field(
        default_factory=lambda: {"low": 0.25, "medium": 0.25, "high": 0.25, "extreme": 0.25},
    )
    """波动率状态概率分布 P(volatility_state)"""

    # 板块相关性结构 (均值向量)
    correlation_structure: dict[str, float] = field(default_factory=dict)
    """板块相关性矩阵 (压缩表示)"""

    # 宏观因子先验
    macro_prior: dict[str, float] = field(default_factory=dict)
    """宏观经济因子先验 (利率/通胀/增长等)"""

    # 多尺度时间信念
    tick_belief: dict[str, Any] = field(default_factory=dict)
    """Tick 级别信念"""

    minute_belief: dict[str, Any] = field(default_factory=dict)
    """分钟级别信念"""

    daily_belief: dict[str, Any] = field(default_factory=dict)
    """日级别信念"""

    weekly_belief: dict[str, Any] = field(default_factory=dict)
    """周级别信念"""

    monthly_belief: dict[str, Any] = field(default_factory=dict)
    """月级别信念"""

    # 不确定性度量
    total_uncertainty: float = 1.0
    """总不确定性度量 (熵)"""

    aleatoric_uncertainty: float = 0.5
    """偶然不确定性 (数据噪声)"""

    epistemic_uncertainty: float = 0.5
    """认知不确定性 (模型知识不足)"""

    # 信念历史
    belief_history: list[dict[str, Any]] = field(default_factory=list)
    """信念历史 (用于相变检测)"""

    def get_regime(self) -> str:
        """获取当前最大概率的市场体制"""
        return max(self.market_regime_probs, key=self.market_regime_probs.get)

    def get_volatility(self) -> str:
        """获取当前最大概率的波动率状态"""
        return max(self.volatility_state_probs, key=self.volatility_state_probs.get)

    def get_entropy(self) -> float:
        """计算市场体制分布的熵"""
        import math

        entropy = 0.0
        for prob in self.market_regime_probs.values():
            if prob > 0:
                entropy -= prob * math.log(prob)
        return entropy

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "market_regime_probs": self.market_regime_probs,
            "volatility_state_probs": self.volatility_state_probs,
            "correlation_structure": self.correlation_structure,
            "macro_prior": self.macro_prior,
            "total_uncertainty": self.total_uncertainty,
            "aleatoric_uncertainty": self.aleatoric_uncertainty,
            "epistemic_uncertainty": self.epistemic_uncertainty,
            "regime": self.get_regime(),
            "entropy": self.get_entropy(),
            "belief_history": self.belief_history,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MarketLatentState":
        """从字典重建"""
        return cls(
            market_regime_probs=d.get("market_regime_probs", cls().market_regime_probs),
            volatility_state_probs=d.get("volatility_state_probs", cls().volatility_state_probs),
            correlation_structure=d.get("correlation_structure", {}),
            macro_prior=d.get("macro_prior", {}),
            total_uncertainty=d.get("total_uncertainty", 1.0),
            aleatoric_uncertainty=d.get("aleatoric_uncertainty", 0.5),
            epistemic_uncertainty=d.get("epistemic_uncertainty", 0.5),
            belief_history=d.get("belief_history", []),
        )


# ==================== 市场预测 ====================


@dataclass
class MarketPrediction:
    """
    生成模型对市场观测的预测输出。

    每个预测字段都带有置信区间 (mean, lower_bound, upper_bound)。
    """

    # 价格预测
    price_prediction: dict[str, float] | None = None
    """价格预测: {"mean": ..., "lower": ..., "upper": ...}"""

    # 波动率预测
    volatility_prediction: dict[str, float] | None = None
    """波动率预测: {"mean": ..., "lower": ..., "upper": ...}"""

    # 情绪预测
    sentiment_prediction: dict[str, float] | None = None
    """情绪预测: {"mean": ..., "lower": ..., "upper": ...}"""

    # 宏观因子预测
    macro_prediction: dict[str, Any] | None = None
    """宏观因子预测"""

    # 多尺度预测
    tick_prediction: dict[str, float] | None = None
    """Tick 级别预测"""
    minute_prediction: dict[str, float] | None = None
    """分钟级别预测"""
    daily_prediction: dict[str, float] | None = None
    """日级别预测"""
    weekly_prediction: dict[str, float] | None = None
    """周级别预测"""
    monthly_prediction: dict[str, float] | None = None
    """月级别预测"""

    # 预测元数据
    timestamp: str = ""
    """预测时间戳"""
    prediction_horizon: str = "daily"
    """预测时间跨度"""
    confidence_scores: dict[str, float] = field(default_factory=dict)
    """每个预测维度的置信度分数 (0-1)"""

    def to_dict(self) -> dict[str, Any]:
        multi_scale = {}
        if self.tick_prediction:
            multi_scale["tick"] = self.tick_prediction
        if self.minute_prediction:
            multi_scale["minute"] = self.minute_prediction
        if self.daily_prediction:
            multi_scale["daily"] = self.daily_prediction
        if self.weekly_prediction:
            multi_scale["weekly"] = self.weekly_prediction
        if self.monthly_prediction:
            multi_scale["monthly"] = self.monthly_prediction
        return {
            "price_prediction": self.price_prediction,
            "volatility_prediction": self.volatility_prediction,
            "sentiment_prediction": self.sentiment_prediction,
            "macro_prediction": self.macro_prediction,
            "multi_scale_predictions": multi_scale,
            "timestamp": self.timestamp,
            "prediction_horizon": self.prediction_horizon,
            "confidence_scores": self.confidence_scores,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MarketPrediction":
        """从字典重建"""
        multi = d.get("multi_scale_predictions", {})
        return cls(
            price_prediction=d.get("price_prediction"),
            volatility_prediction=d.get("volatility_prediction"),
            sentiment_prediction=d.get("sentiment_prediction"),
            macro_prediction=d.get("macro_prediction"),
            tick_prediction=multi.get("tick"),
            minute_prediction=multi.get("minute"),
            daily_prediction=multi.get("daily"),
            weekly_prediction=multi.get("weekly"),
            monthly_prediction=multi.get("monthly"),
            timestamp=d.get("timestamp", ""),
            prediction_horizon=d.get("prediction_horizon", "daily"),
            confidence_scores=d.get("confidence_scores", {}),
        )


# ==================== 预测误差 ====================


@dataclass
class PredictionError:
    """
    多尺度预测误差

    包含各维度的预测误差和汇总统计。
    """

    price_error: float | None = None
    """价格预测误差"""

    volatility_error: float | None = None
    """波动率预测误差"""

    sentiment_error: float | None = None
    """情绪预测误差"""

    macro_error: float | None = None
    """宏观因子预测误差"""

    # 多尺度误差
    tick_error: float | None = None
    minute_error: float | None = None
    daily_error: float | None = None
    weekly_error: float | None = None
    monthly_error: float | None = None

    # 汇总
    total_error: float = 0.0
    """总预测误差 (加权和)"""

    error_norm: float = 0.0
    """误差范数"""

    is_surprising: bool = False
    """是否为惊奇事件 (显著超出预期)"""

    surprise_magnitude: float = 0.0
    """惊奇幅度"""

    # 精度 (逆方差) 权重
    precision_weights: dict[str, float] = field(default_factory=dict)
    """各维度精度权重"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "price_error": self.price_error,
            "volatility_error": self.volatility_error,
            "sentiment_error": self.sentiment_error,
            "macro_error": self.macro_error,
            # 6个时间尺度细粒度误差
            "tick_error": self.tick_error,
            "minute_error": self.minute_error,
            "daily_error": self.daily_error,
            "weekly_error": self.weekly_error,
            "monthly_error": self.monthly_error,
            "total_error": self.total_error,
            "error_norm": self.error_norm,
            "is_surprising": self.is_surprising,
            "surprise_magnitude": self.surprise_magnitude,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PredictionError":
        """从字典重建"""
        return cls(
            price_error=d.get("price_error"),
            volatility_error=d.get("volatility_error"),
            sentiment_error=d.get("sentiment_error"),
            macro_error=d.get("macro_error"),
            tick_error=d.get("tick_error"),
            minute_error=d.get("minute_error"),
            daily_error=d.get("daily_error"),
            weekly_error=d.get("weekly_error"),
            monthly_error=d.get("monthly_error"),
            total_error=d.get("total_error", 0.0),
            error_norm=d.get("error_norm", 0.0),
            is_surprising=d.get("is_surprising", False),
            surprise_magnitude=d.get("surprise_magnitude", 0.0),
        )


# ==================== HPC-Loop State (嵌入 LangGraph) ====================


@dataclass
class HPCState:
    """
    HPC-Loop 在 LangGraph 中的扩展状态。

    此 dataclass 将作为 AgentState 的一个新字段 `hpc_state` 嵌入。
    """

    # 生成模型状态
    latent_state: MarketLatentState | None = None
    """当前市场隐状态"""

    last_prediction: MarketPrediction | None = None
    """最近一次生成的预测"""

    last_prediction_error: PredictionError | None = None
    """最近一次计算的预测误差"""

    # 全局工作空间状态
    workspace_contents: list[dict[str, Any]] = field(default_factory=list)
    """当前工作空间中的内容"""

    workspace_broadcast: list[str] = field(default_factory=list)
    """广播到全局工作空间的信息"""

    # 主动推理状态
    candidate_actions: list[dict[str, Any]] = field(default_factory=list)
    """候选行动列表 (含 EFE 分解)"""

    selected_action: dict[str, Any] | None = None
    """选择的行动"""

    # 因果推理状态
    causal_counterfactuals: list[dict[str, Any]] = field(default_factory=list)
    """因果反事实推理结果"""

    # 记忆系统状态
    memory_trace: dict[str, Any] | None = None
    """记忆检索结果"""

    # 交易事件 (待存储到记忆系统)
    current_episode: dict[str, Any] | None = None
    """当前交易事件"""

    # 元数据
    step_counter: int = 0
    """HPC-Loop 步骤计数器"""

    enabled_features: dict[str, bool] = field(default_factory=dict)
    """当前启用的特性"""

    # 双循环元状态（分层模型 + 元学习器）
    meta_data: dict[str, Any] = field(default_factory=dict)
    """
    元数据字典，存放 AIF 双循环拓扑的运行时状态。

    包含字段:
        aif_meta_diagnostics: dict — 元循环诊断报告
        aif_meta_triggered: bool — 元学习器是否触发
        aif_meta_temperature: Optional[float] — 元学习器建议温度
        aif_meta_cycle_count: int — 元循环执行次数
        aif_hierarchical_free_energy: Optional[float] — 分层自由能
        aif_meta_free_energy: Optional[float] — 元学习自由能
        aif_meta_window_stats: dict — 元学习器窗口统计
    """

    def to_dict(self) -> dict[str, Any]:
        result = {
            "latent_state": self.latent_state.to_dict() if self.latent_state else None,
            "last_prediction": self.last_prediction.to_dict() if self.last_prediction else None,
            "last_prediction_error": self.last_prediction_error.to_dict() if self.last_prediction_error else None,
            "workspace_contents": self.workspace_contents,
            "workspace_broadcast": self.workspace_broadcast,
            "candidate_actions": self.candidate_actions,
            "selected_action": self.selected_action,
            "causal_counterfactuals": self.causal_counterfactuals,
            "memory_trace": self.memory_trace,
            "current_episode": self.current_episode,
            "step_counter": self.step_counter,
            "enabled_features": self.enabled_features,
            "meta_data": self.meta_data,
        }
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HPCState":
        """从字典重建 HPCState"""
        state = cls()
        if d.get("latent_state"):
            state.latent_state = MarketLatentState.from_dict(d["latent_state"])
        if d.get("last_prediction"):
            state.last_prediction = MarketPrediction.from_dict(d["last_prediction"])
        if d.get("last_prediction_error"):
            state.last_prediction_error = PredictionError.from_dict(d["last_prediction_error"])
        state.workspace_contents = d.get("workspace_contents", [])
        state.workspace_broadcast = d.get("workspace_broadcast", [])
        state.candidate_actions = d.get("candidate_actions", [])
        state.selected_action = d.get("selected_action")
        state.causal_counterfactuals = d.get("causal_counterfactuals", [])
        state.memory_trace = d.get("memory_trace")
        state.current_episode = d.get("current_episode")
        state.step_counter = d.get("step_counter", 0)
        state.enabled_features = d.get("enabled_features", {})
        state.meta_data = d.get("meta_data", {})
        return state
