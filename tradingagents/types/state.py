from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class NodeTiming(TypedDict, total=False):
    elapsed: float


class PerformanceMetrics(TypedDict, total=False):
    total_elapsed: float
    node_timings: dict[str, float]
    model_info: str
    token_usage: dict[str, Any] | None


class HPCState(TypedDict, total=False):
    """HPC-Loop 运行时状态（匹配 hpc_state.py:HPCState.to_dict() 输出）"""
    enabled: bool
    config: dict[str, Any]
    data: dict[str, Any]
    # 以下字段来自 hpc_state.py:HPCState dataclass 的运行时序列化
    latent_state: dict[str, Any] | None
    last_prediction: dict[str, Any] | None
    last_prediction_error: dict[str, Any] | None
    workspace_contents: list[dict[str, Any]]
    workspace_broadcast: list[str]
    candidate_actions: list[dict[str, Any]]
    selected_action: dict[str, Any] | None
    causal_counterfactuals: list[dict[str, Any]]
    memory_trace: dict[str, Any] | None
    current_episode: dict[str, Any] | None
    step_counter: int
    enabled_features: dict[str, bool]
    meta_data: dict[str, Any]


class AnalysisResult(TypedDict, total=False):
    reports: dict[str, str]
    decision: str
    confidence: float
    risk_score: float
    reasoning: str
    performance: PerformanceMetrics
    hpc_state: dict[str, Any] | None
    aif_state: dict[str, Any] | None


class AgentRunConfig(TypedDict, total=False):
    company_name: str
    trade_date: str
    stock_code: str | None
    task_id: str | None
    fusion_mode: str | None
    max_retries: int
    timeout: int


class FusionMode(TypedDict, total=False):
    mode: str
    enabled: bool
    use_aif: bool
    use_hpc: bool
    use_diffusion: bool
    use_l_iwm: bool
    use_hsrc_mc: bool


class GraphResult(TypedDict, total=False):
    final_state: dict[str, Any]
    performance: PerformanceMetrics
    model_info: str


class StateSnapshot(TypedDict, total=False):
    company_of_interest: str
    trade_date: str
    market_report: str
    fundamentals_report: str
    news_report: str
    sentiment_report: str
    investment_plan: str
    trader_investment_plan: str
    final_trade_decision: str
    performance_metrics: PerformanceMetrics
    hpc_state: dict[str, Any] | None
    aif_state: dict[str, Any] | None
