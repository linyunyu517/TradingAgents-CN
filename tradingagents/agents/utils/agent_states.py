from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState
from typing_extensions import TypedDict

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[str, "Bullish Conversation history"]  # Bullish Conversation history
    bear_history: Annotated[str, "Bearish Conversation history"]  # Bullish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    current_response: Annotated[str, "Latest response"]  # Last response
    judge_decision: Annotated[str, "Final judge decision"]  # Last response
    count: Annotated[int, "Length of the current conversation"]  # Conversation length
    debate_summary: Annotated[str, "Accumulated debate key points"]  # Incremental summary of debate


# Risk management team state
class RiskDebateState(TypedDict):
    risky_history: Annotated[str, "Risky Agent's Conversation history"]  # Conversation history
    safe_history: Annotated[str, "Safe Agent's Conversation history"]  # Conversation history
    neutral_history: Annotated[str, "Neutral Agent's Conversation history"]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_risky_response: Annotated[str, "Latest response by the risky analyst"]  # Last response
    current_safe_response: Annotated[str, "Latest response by the safe analyst"]  # Last response
    current_neutral_response: Annotated[str, "Latest response by the neutral analyst"]  # Last response
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


# === LangGraph InvalidUpdateError 修复: Reducer 函数集合 ===
def _hpc_state_reducer(current, new):
    """HPC-Loop 状态合并 reducer。

    LangGraph 在同一个 step 中可能有多个节点（HPC_Predict + AIF_Predict 等）
    同时写入 hpc_state。此 reducer 确保 LangGraph 可以正确处理多次写入，
    而不是抛出 InvalidUpdateError。

    策略：使用最新的非 None 值直接替换旧值（last-write-wins）。
    因为每个 AIF 迭代产生的都是完整的 HPCState dict，独立于之前的步骤。
    """
    if new is None:
        return current
    # [Fix 方案C] HPCState 是 @dataclass，无 .get() 方法。
    # reducer 在存储前自动序列化为 dict，保证所有读取 .get() 的代码不出错。
    if hasattr(new, "to_dict"):
        return new.to_dict()
    return new


def _report_reducer(current: str, new: str) -> str:
    """报告字段合并 reducer（修复 LangGraph InvalidUpdateError）。

    LangGraph 在同一个 step 中可能有多个节点并发写入 report 字段
    （如分析师内部循环：analyst → tools → analyst），导致抛出
    InvalidUpdateError。

    策略：使用最新的非空字符串直接替换旧值（last-write-wins）。
    因为每次写入的都是完整的分析师报告，独立于之前的步骤。
    """
    if not new or new.strip() == "":
        return current
    return new


def _counter_reducer(current: int, new: int) -> int:
    """计数器字段合并 reducer（修复 LangGraph InvalidUpdateError）。

    分析师节点的工具调用计数器（market_tool_call_count 等）在 Fusion 模式中
    可能被多个并发路径同时写入。使用 max() 策略确保计数不会因并发写入而
    丢失增量。

    策略：取 current 和 new 中的较大值（max）。
    因为：每次写入都是递增操作（count + 1），max 可以正确处理
    所有并发路径中最高的计数值。

    注意：if new is None 防御 — LangGraph 条件边路由可能传递 None，
    参考 _hpc_state_reducer 的相同模式。
    """
    if new is None:
        return current
    return max(current, new)


def _bool_or_reducer(current: bool, new: bool) -> bool:
    """布尔 OR 合并 reducer（修复 LangGraph InvalidUpdateError）。

    `data_source_failure` 在 Fusion 模式中可能被 Bull/Bear Researcher
    并发写入（bull 设 True，bear 读取 True 后也写入）。使用 OR 语义确保
    任一节点标记为 True 则保持 True。

    策略：current or new（一旦 True 永远 True）。
    """
    return current or new


def _list_extend_reducer(current: list | None, new: list) -> list:
    """列表字段合并 reducer（修复 LangGraph InvalidUpdateError）。

    用于 list 类型字段的并发写入合并。每个节点写入完整的 list，
    此 reducer 将新旧列表拼接在一起（extend）。
    """
    if current is None:
        return new
    if new is None:
        return current
    return current + new


def _dict_merge_reducer(current: dict | None, new: dict) -> dict:
    """字典逐字段合并 reducer（通用版本）。

    用于 TypedDict 字段的并发写入合并。每个节点写入完整的 dict 但只更新
    部分字段。此 reducer 逐字段合并：
    - count 字段：取最大值（单调递增计数器）
    - 字符串字段：取最新的非空值（last-write-wins）
    - 其他字段：新值覆盖旧值

    适用：investment_debate_state（Bull/Bear Researcher + Judge 并发写入）
         risk_debate_state（Risky/Safe/Neutral/Judge 并发写入）
    注意：if new is None 防御 — LangGraph 条件边路由可能传递 None，
    参考 _hpc_state_reducer 的相同模式（L48-49）。
    """
    if current is None:
        return new
    if new is None:
        return current
    result = dict(current)
    for k, v in new.items():
        if k == "count":
            # 计数器取最大值（单调递增）
            result[k] = max(result.get(k, 0), v)
        elif isinstance(v, str) and not v.strip():
            # 空字符串不覆盖
            if k not in result or not result.get(k):
                result[k] = v
        else:
            # 非空值直接覆盖
            result[k] = v
    return result


# 🐛 [Bug Fix] 导入 safe_add_messages 作为 messages 字段的安全 reducer
#
# AgentState 继承 MessagesState, 后者定义:
#   messages: Annotated[list[AnyMessage], add_messages]
#
# LangGraph 的 add_messages reducer 在 RemoveMessage 目标 ID 不存在时
# 抛出 ValueError。safe_add_messages 包装器提供了防御性容错:
# 1. REMOVE_ALL_MESSAGES 哨兵: 原子化清除所有消息, 跳过逐 ID 检查
# 2. RemoveMessage ID 不存在时静默跳过, 而非抛出异常
from tradingagents.agents.utils.agent_utils import safe_add_messages


class AgentState(MessagesState):
    # 🐛 [Bug Fix] 覆盖 MessagesState.messages 使用 safe_add_messages
    # 原 MessagesState 使用 raw add_messages, 会导致 RemoveMessage ID 不存在时抛出 ValueError。
    # safe_add_messages 提供防御性容错, 同时保持与 add_messages 完全兼容的行为。
    messages: Annotated[list[AnyMessage], safe_add_messages]

    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]

    # 🐛 [Bug Fix] 使用 _report_reducer 防止 LangGraph InvalidUpdateError
    # 多个节点可能并发写入 sender（如并行分析师节点），需要 last-write-wins reducer。
    sender: Annotated[str, "Agent that sent this message", _report_reducer]

    # research step
    market_report: Annotated[str, _report_reducer] = ""
    sentiment_report: Annotated[str, _report_reducer] = ""
    news_report: Annotated[str, _report_reducer] = ""
    fundamentals_report: Annotated[str, _report_reducer] = ""

    # 🔧 死循环修复: 工具调用计数器（使用 _counter_reducer 防止并发写入 InvalidUpdateError）
    market_tool_call_count: Annotated[int, _counter_reducer]
    news_tool_call_count: Annotated[int, _counter_reducer]
    sentiment_tool_call_count: Annotated[int, _counter_reducer]
    fundamentals_tool_call_count: Annotated[int, _counter_reducer]

    # 🔧 [H10 数据源全故障降级] 连续空研究轮次计数（>=1 时跳过辩论阶段）
    empty_research_count: Annotated[int, _counter_reducer]
    # 🔧 [H10 数据源全故障降级] 数据源全故障标记，供下游节点参考
    # 🐛 [Bug Fix] 添加 _bool_or_reducer 防止 LangGraph InvalidUpdateError
    # Bull/Bear Researcher 在 Fusion 模式下可能并发写入 data_source_failure，
    # 使用 OR 语义确保任一节点标记为 True 则保持 True。
    data_source_failure: Annotated[bool, "All data sources failed, graceful degradation", _bool_or_reducer]

    # researcher team discussion step
    # 🔧 辩论状态合并：使用 _dict_merge_reducer 防止 Bull/Bear Researcher 并发写入 InvalidUpdateError
    investment_debate_state: Annotated[InvestDebateState, _dict_merge_reducer]
    # 🐛 [Bug Fix] 使用 _report_reducer 防止 LangGraph InvalidUpdateError
    # 多个节点（如 AIF 迭代循环或 Fusion 模式下的并发路径）在同一个 step 中
    # 可能同时写入 investment_plan，未定义 reducer 时 LangGraph 抛出错误。
    # _report_reducer 采用 last-write-wins 策略，忽略空值写入。
    # ⚠️ LangGraph 0.6.x 要求 reducer 必须是 Annotated 元组的最后一个元素
    # (meta[-1] 必须是 callable)，描述字符串放在前面。
    investment_plan: Annotated[str, "Plan generated by the Analyst", _report_reducer]

    # 🐛 [Bug Fix] 添加 _report_reducer 防止 LangGraph InvalidUpdateError
    # Trader 节点写入 trader_investment_plan 可能与其它并发路径冲突。
    # 使用与 investment_plan 相同的 last-write-wins 策略。
    trader_investment_plan: Annotated[str, "Plan generated by the Trader", _report_reducer]

    # risk management team discussion step
    # 🔧 风险评估状态合并：使用 _dict_merge_reducer 防止 Risky/Safe/Neutral 并发写入 InvalidUpdateError
    risk_debate_state: Annotated[RiskDebateState, _dict_merge_reducer]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts", _report_reducer]

    # === 三轮改造 (HPC-Loop / L-IWM / HSR-MC) 扩展状态字段 ===
    past_context: Annotated[str, _report_reducer]  # Memory log context — last-write-wins 策略

    # === AIF (Active Inference Framework) 循环迭代计数器 ===
    # 🐛 [Bug Fix] 必须在 AgentState 中显式声明，否则 LangGraph TypedDict schema
    # 会静默丢弃 AIF_SelectAction_Evaluate 节点返回的 _aif_iteration_count，
    # 导致 aif_route_from_update_belief 始终读到 0，陷入无限循环。
    _aif_iteration_count: Annotated[int, _counter_reducer]
    _aif_max_iterations: Annotated[int, _counter_reducer]
    # === AIF (Active Inference Framework) 运行时状态 ===
    # 🐛 [Bug Fix] P1-1: 在 AgentState 中声明缺失的 AIF 键，否则 LangGraph TypedDict schema
    # 会静默丢弃 AIF_SelectAction_Evaluate 节点返回的额外键。
    # 这些字段由 create_aif_select_action_evaluate_node 写入。
    # 🐛 [Bug-New-006 修复] 添加 _hpc_state_reducer 防止 LangGraph InvalidUpdateError
    # AIF_Observe 在 Fusion 模式下被 Section B（首次通过）和 Section C（迭代循环）
    # 两条路径同时写入 aif_state，未定义 reducer 时 LangGraph 抛出
    # "Can receive only one value per step. Use an Annotated key to handle multiple values."
    # _hpc_state_reducer 使用 last-write-wins 策略，与 hpc_state 一致。
    aif_state: Annotated[dict[str, Any] | None, _hpc_state_reducer] = None
    fusion_action: str | None = None
    fusion_confidence: float | None = None
    fusion_reasoning: str | None = None
    fusion_efe_scores: dict[str, float] | None = None
    aif_selection: dict[str, Any] | None = None
    aif_action_trace: list[dict[str, Any]] | None = None
    aif_belief: Any | None = None
    aif_free_energy: float | None = None
    aif_prior_injections: list[dict[str, Any]] | None = None
    aif_current_belief: Any | None = None
    aif_observation: dict[str, Any] | None = None
    aif_meta_diagnostics: dict[str, Any] | None = None
    aif_meta_triggered: bool | None = None
    aif_meta_temperature: float | None = None
    aif_meta_cycle_count: int | None = None
    aif_hierarchical_free_energy: float | None = None
    aif_meta_free_energy: float | None = None
    aif_meta_window_stats: dict[str, Any] | None = None
    aif_free_energy_history: list[float] | None = None

    # === 🐛 [P1-1 2026-06-18] AIF 收敛/发散监控字段 ===
    _aif_diverged: bool | None = None
    """AIF 发散标记 — 当自由能异常增加时由 AIF 节点设置"""
    _aif_converged: bool | None = None
    """AIF 收敛标记 — 当自由能趋于稳定时由 AIF 节点设置"""

    # === 🐛 [P1-1 2026-06-18] 情绪分析 / 风控报告字段 ===
    sentiment_analysis: dict[str, Any] | None = None
    """情绪分析结果，由情绪分析节点写入"""
    risk_report: dict[str, Any] | None = None
    """风控报告，由风险管理节点写入"""

    # HPC-Loop extended state
    hpc_state: Annotated[dict[str, Any] | None, _hpc_state_reducer] = None
    """HPC-Loop 扩展状态，由 hpc_loop 模块管理"""

    gws_broadcast_summary: Annotated[str | None, "Global Workspace broadcast summary", _report_reducer] = None
    """全局工作空间广播摘要"""

    hpc_phase_transition: Annotated[dict[str, Any] | None, "Phase transition detection result", _dict_merge_reducer] = (
        None
    )
    """市场相变检测结果"""

    # === Phase 3: 扩散模块 (Diffusion) 扩展状态字段 ===
    diffusion_decision: Annotated[dict[str, Any] | None, "Diffusion advisor trading decision", _dict_merge_reducer] = (
        None
    )
    """扩散顾问模块 B 输出的交易决策（含置信度），由 diffusion_advisor_node 写入"""

    fused_decision: Annotated[dict[str, Any] | None, "Fused decision after weighted merge", _dict_merge_reducer] = None
    """加权融合后的最终决策，由 fusion_node 写入"""

    # === 🐛 Bug #5 修复: L-IWM / HSR-MC 数据管道字段 ===
    # 这些字段由 l_iwm_bridge_node 写入，须在 AgentState 中显式定义，
    # 否则 LangGraph TypedDict schema 会静默丢弃额外键。
    module_losses: Annotated[
        dict[str, Any] | None, "Module loss values for HSR-MC meta-learning", _dict_merge_reducer,
    ] = None
    """各模块损失值（EFE、EWC、Causal、RSSM、GWS、RealDataPipeline），供 HSR-MC 消费"""

    module_performance: Annotated[
        dict[str, Any] | None, "Module performance metrics for HSR-MC", _dict_merge_reducer,
    ] = None
    """各模块性能指标（基于损失的逆映射），供 HSR-MC 消费"""

    prediction_errors: Annotated[
        list | None, "Prediction error list for HSR-MC meta-learning", _list_extend_reducer,
    ] = None
    """预测误差列表，供 HSR-MC online_meta_step() 消费"""

    l_iwm: Annotated[dict[str, Any] | None, "L-IWM aggregated state (EWC loss, etc.)", _dict_merge_reducer] = None
    """L-IWM 聚合状态（含 EWC 正则化损失等）"""

    # === HSR-MC 节点输出字段（供 _extract_hpc_reports 提取） ===
    hsrc_mc: Annotated[dict[str, Any] | None, "HSR-MC aggregated state", _dict_merge_reducer] = None
    """HSR-MC 聚合状态"""

    hsrc_mc_meta: Annotated[dict[str, Any] | None, "HSR-MC meta-observer output", _dict_merge_reducer] = None
    """HSR-MC 元观察器输出（健康报告、梯度统计等）"""

    hsrc_mc_adjust: Annotated[dict[str, Any] | None, "HSR-MC adjustment output", _dict_merge_reducer] = None
    """HSR-MC 调整节点输出（调整后的权重/参数）"""

    hsrc_mc_reflect: Annotated[dict[str, Any] | None, "HSR-MC reflection output", _dict_merge_reducer] = None
    """HSR-MC 反思节点输出（机制反思结果）"""

    # ========== [Plan C] 认知架构 — 全局工作空间 + 注意力分配 + 迭代轨迹 ==========
    # 参考: Baars 1988 "Global Workspace Theory"; Dehaene 2001
    #       道家"无为"; 计算神经科学"丘脑-皮层40Hz绑定"
    global_workspace: Annotated[
        dict[str, Any] | None, "Global Workspace — 所有模块的当前输出集合", _dict_merge_reducer,
    ] = None
    """全局工作空间——收集所有模块(交易员/扩散/AIF/HSR-MC/L-IWM/分析师)的当前输出。
    供 AttentionAllocator 计算注意力权重, 供 IterativeRefinement 迭代精炼使用。"""

    attention_allocation: Annotated[
        dict[str, Any] | None, "Attention allocation — 各模块的注意力权重", _dict_merge_reducer,
    ] = None
    """注意力分配——AttentionAllocator 计算的各模块注意力权重。
    结构: {"attention": {"trader": 0.x, "diffusion": 0.x, ...},
           "_temperature": 0.x, "_entropy": 0.x, "_conflict": 0.x}"""

    decision_trace: Annotated[
        list | None, "Decision iteration trace — 迭代决策轨迹", _list_extend_reducer,
    ] = None
    """迭代决策轨迹——记录 IterativeRefinement 每轮的 {action, confidence, dominant_module}。
    用于收敛检测: 连续 2 轮 action 相同 → 收敛。"""
