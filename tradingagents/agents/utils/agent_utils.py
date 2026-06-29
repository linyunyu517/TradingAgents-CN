from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage
from langchain_core.tools import tool

import numpy as np

from tradingagents.dataflows import interface
from tradingagents.default_config import DEFAULT_CONFIG

# 导入统一日志系统和工具日志装饰器
from tradingagents.utils.logging_init import get_logger

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
from tradingagents.utils.tool_logging import log_tool_call

logger = get_logger("agents")

# ===== [PR #2] 数据源故障检测 ContextVar =====
import contextvars

_data_fetch_failed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_data_fetch_failed", default=False
)


def is_data_fetch_failed() -> bool:
    """检查当前上下文中是否有数据源获取失败。

    Returns:
        bool: 任一数据源获取失败返回 True
    """
    return _data_fetch_failed.get()


def reset_data_fetch_failed():
    """重置数据源故障标记（graph 运行结束后调用）。"""
    _data_fetch_failed.set(False)
# ===== END [PR #2] =====


def create_msg_delete(analyst_type: str = "") -> Callable[[dict], dict]:
    """创建消息清空节点（LangGraph 节点工厂）

    Args:
        analyst_type: 分析师类型标识 ("market"/"social"/"news"/"fundamentals")
                      用于节点日志和调试信息；默认为空字符串兼容旧调用方式

    Returns:
        返回一个 LangGraph 节点函数，该函数清空 state["messages"] 并注入占位消息

    Raises:
        KeyError: 如果 state 缺少 "messages" 键
    """
    def delete_messages(state: dict) -> dict:
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # 携带 analyst_type 信息增强调试能力
        prefix = f"[{analyst_type}] " if analyst_type else ""
        placeholder = HumanMessage(content=f"{prefix}Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


# 🐛 [Bug Fix] safe_add_messages — 防御性 add_messages reducer 包装器
#
# LangGraph 的 add_messages reducer 在 RemoveMessage 目标 ID 不存在时
# 抛出 ValueError。此函数提供防御性容错:
#
# 1. REMOVE_ALL_MESSAGES 哨兵: 原子化清除所有消息，跳过逐 ID 检查
# 2. RemoveMessage ID 不存在时静默跳过，而非抛出异常
#
# 完全兼容 LangGraph add_messages 的接口签名:
#   safe_add_messages(current: list[BaseMessage], new: BaseMessage | list[BaseMessage]) -> list[BaseMessage]
def safe_add_messages(
    current: list[BaseMessage],
    new: BaseMessage | list[BaseMessage],
) -> list[BaseMessage]:
    """防御性消息追加 reducer，防止 RemoveMessage 不存在的 ID 导致 ValueError。

    Args:
        current: 当前消息列表。
        new: 新消息或消息列表。

    Returns:
        合并后的消息列表。
    """
    from langgraph.graph.message import add_messages

    # 将单条消息包装为列表统一处理
    if not isinstance(new, list):
        new = [new]

    # 🔧 预处理: 检查是否包含 REMOVE_ALL_MESSAGES 哨兵
    # 如果是，直接返回清除后的消息列表（跳过逐 ID 的 RemoveMessage）
    REMOVE_ALL_MESSAGES = "REMOVE_ALL_MESSAGES"
    if any(isinstance(m, RemoveMessage) and m.id == REMOVE_ALL_MESSAGES for m in new):
        # 只保留非 RemoveMessage 的消息
        remaining = [m for m in new if not isinstance(m, RemoveMessage)]
        return remaining

    # 收集当前消息的 ID 集合（用于快速查找）
    current_ids = {m.id for m in current if hasattr(m, "id") and m.id is not None}

    # 🔧 过滤: 移除那些目标 ID 在当前消息列表中不存在的 RemoveMessage
    # 防止 LangGraph 原生 add_messages 抛出 ValueError
    filtered_new: list[BaseMessage] = []
    for m in new:
        if isinstance(m, RemoveMessage) and m.id is not None and m.id not in current_ids:
            # 静默跳过: RemoveMessage 目标 ID 不存在
            continue
        filtered_new.append(m)

    # 委托给原生的 add_messages 处理
    return add_messages(current, filtered_new)  # type: ignore[return-value,arg-type]


# =============================================================================
# [H14 集中化防御] 模块公开接口列表
# =============================================================================
# 所有从本模块导出的函数/类在此统一声明，确保 import * 行为可预测
__all__ = [
    "Toolkit",
    "are_all_reports_empty",
    "clean_orphaned_tool_calls",
    "create_msg_delete",
    "get_tool_names",
    "invoke_with_timeout",
    "is_deepseek_via_openai",
    "safe_add_messages",
    "safe_chain_invoke",
    "safe_extract_content",
    "safe_llm_invoke",
]


# =============================================================================
# [H14] safe_llm_invoke — 安全 LLM 调用包装器
# =============================================================================
def safe_llm_invoke(
    llm,
    messages,
    **kwargs,
):
    """安全调用 LLM，自动清理孤儿 tool_calls 并防御性处理异常。

    当 LLM 响应中包含 orphan tool_calls（无对应 ToolMessage）时，
    自动移除以避免 LangGraph 状态机崩溃。

    Args:
        llm: LLM 实例（如 ChatOpenAI、ChatDeepSeek 等）。
        messages: 消息列表或字符串 prompt。
        **kwargs: 传递给 llm.invoke() 的额外参数。

    Returns:
        AIMessage | str: LLM 响应内容。发生异常时返回空字符串。
    """
    from langchain_core.messages import AIMessage

    try:
        response = llm.invoke(messages, **kwargs)
        # 自动清理孤儿 tool_calls，防止 LangGraph 状态机报错
        if isinstance(response, AIMessage):
            clean_orphaned_tool_calls(response)
        return response
    except Exception as e:
        logger.error(f"❌ [H14] safe_llm_invoke 调用失败: {e}")
        return ""


# =============================================================================
# [H14] safe_extract_content — 安全提取 AIMessage 文本内容
# =============================================================================
def safe_extract_content(response) -> str:
    """安全地从 LLM 响应中提取文本内容。

    统一处理 AIMessage、字符串和任意类型的 LLM 响应。

    Args:
        response: LLM 响应，可以是 AIMessage、str 或任意类型

    Returns:
        str: 提取的文本内容。输入无效或异常时返回空字符串。
    """
    from langchain_core.messages import AIMessage

    try:
        if isinstance(response, AIMessage):
            content = response.content
            if isinstance(content, str):
                # [MoA-Fix] 纯工具调用场景：content="" 但 tool_calls 非空
                # 这时返回空字符串会导致下游丢失分析信号，返回占位符以保证数据流完整性
                if not content and hasattr(response, 'tool_calls') and response.tool_calls:
                    return "(LLM返回纯工具调用，未生成独立分析文本)"
                return content
            if isinstance(content, list):
                return " ".join(str(part) for part in content if part)
            return str(content) if content else ""
        if isinstance(response, str):
            return response
        if hasattr(response, "content"):
            return str(response.content)
        return str(response) if response else ""
    except Exception as e:
        logger.error(f"❌ [H14] safe_extract_content 提取失败: {e}")
        return ""


# =============================================================================
# [Plan B] _safe_get_field: 安全字段提取 — 自动处理类型不匹配
# 解决: float(.get()) 被 dict/None/list 击穿的系统性风险
# 参考:
#   - Rust's Result/Option pattern (类型安全设计哲学)
#   - Python EAFP vs LBYL 的综合折中
#   - 物演通论: 系统复杂度越高 → 容错代偿必须越强
# =============================================================================

def _safe_get_field(
    data: Any,
    key: str,
    default: Any = None,
    target_type: type | None = None,
) -> Any:
    """安全地从 dict-like 对象提取字段，自动处理类型不匹配。

    核心逻辑:
    1. 只接受 dict 或支持 .get() 的对象（不尝试在 None 上调用 .get()）
    2. 如果值不存在或 data 不可用，返回 default
    3. 如果值存在但类型不匹配：
       a. 尝试 target_type(val) 转换（如 float("3.14")）
       b. 转换失败 → 返回 default
    4. 容器→标量聚合：
       a. dict: 尝试 "overall" → "score" → 数值均值
       b. list: 数值均值

    Args:
        data: 目标对象（dict 或支持 .get() 的对象）
        key: 字段名
        default: 字段不存在或类型不匹配时的默认值
        target_type: 期望的类型（如 float, int, str）

    Returns:
        字段值（经过类型安全处理）
    """
    # 阶段1: 检查 data 可用性
    if data is None:
        return default
    if not hasattr(data, "get"):
        return default

    # 阶段2: 提取值
    val = data.get(key, default)

    # 阶段3: 如果值就是 default，直接返回
    if val is default:
        return val

    # 阶段4: 类型检查与转换
    if target_type is None:
        return val
    if isinstance(val, target_type):
        return val
    # bool 是 int 的子类, 但不应作为数值
    if isinstance(val, bool):
        return default

    try:
        # 容器→标量的特殊情况
        if target_type in (float, int) and not isinstance(val, (str, bool)):
            if isinstance(val, dict):
                for agg_key in ("overall", "score", "value", "total", "mean", "health", "overall_health"):
                    if agg_key in val:
                        agg_val = val[agg_key]
                        if isinstance(agg_val, (int, float)):
                            return target_type(agg_val)
                        if isinstance(agg_val, str):
                            # 字符串健康状态 → 数值
                            health_map = {"healthy": 1.0, "degraded": 0.5, "warning": 0.3, "unhealthy": 0.0, "critical": 0.0}
                            if agg_val.lower() in health_map:
                                return target_type(health_map[agg_val.lower()])
                            # 尝试直接转换数值字符串
                            try:
                                return target_type(agg_val)
                            except (ValueError, TypeError):
                                pass
                numeric_vals = [v for v in val.values() if isinstance(v, (int, float))]
                if numeric_vals:
                    return target_type(sum(numeric_vals) / len(numeric_vals))
                return default
            if isinstance(val, (list, tuple)):
                numeric_vals = [v for v in val if isinstance(v, (int, float))]
                if numeric_vals:
                    return target_type(sum(numeric_vals) / len(numeric_vals))
                return default

        return target_type(val)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return default


# =============================================================================
# [Plan C] Phase 1.2: 全局工作空间 + 注意力分配 + 收敛检测辅助函数
# 参考: Baars 1988 "Global Workspace Theory"; Dehaene 2001 "Cortical mechanisms"
#       Friston 2009 "Predictive coding under the free-energy principle"
#       Haken 1983 "Synergetics" — 序参量; 道家"无为"; 佛学"空性"
# =============================================================================

def build_global_workspace(state: dict) -> dict:
    """从 state 收集所有模块的当前输出，填充到全局工作空间。

    每个模块的输出被标准化为统一格式，供 AttentionAllocator 和
    IterativeRefinement 使用。

    Args:
        state: LangGraph AgentState 字典

    Returns:
        dict: 全局工作空间, 结构:
            { "trader": {"probs": [...], "plan_summary": "...", "confidence": 0.x},
              "diffusion": {"action_probs": [...], "confidence": 0.x, ...},
              "aif": {"efe_probs": [...], "efe_raw": {...}, "belief": "..."},
              "hsrc_mc": {"regime": {...}, "anomalies": [...], "health": 0.x},
              "l_iwm": {"ewc_loss": 0.x, "prediction_errors": [...], "module_perf": {...}},
              "hpc": {"prediction_error": 0.x, "selected_action": "..."},
              "analysts": {"market": int, "fundamentals": int, "news": int, "sentiment": int},
              "_meta": {"iteration": 0, "max_iterations": 3, "converged": False} }
    """
    workspace: dict[str, Any] = {"_meta": {"iteration": 0, "max_iterations": 3, "converged": False}}

    # 1. 交易员
    plan: str = state.get("trader_investment_plan", "") or ""
    if plan:
        plan_lower = plan.lower()
        buy_kw = ("买入", "买", "看多", "上涨", "利好", "反弹", "增持", "bull", "buy", "long")
        sell_kw = ("卖出", "卖", "看空", "下跌", "利空", "清仓", "减持", "bear", "sell", "short")
        buy_c = sum(plan_lower.count(kw) for kw in buy_kw)
        sell_c = sum(plan_lower.count(kw) for kw in sell_kw)
        tot = buy_c + sell_c + max(0, len(plan) // 50 - buy_c - sell_c) + 1
        probs = [buy_c / tot, sell_c / tot, (tot - buy_c - sell_c) / tot]
        workspace["trader"] = {
            "probs": [min(p, 1) for p in probs],
            "plan_summary": plan[:300],
            "confidence": max(probs),
        }
    else:
        workspace["trader"] = {"probs": [1 / 3, 1 / 3, 1 / 3], "plan_summary": "空", "confidence": 0.0}

    # 2. 扩散模型
    diff_dec = state.get("diffusion_decision", {}) or {}
    workspace["diffusion"] = {
        "action_probs": diff_dec.get("action_probs", [1 / 3, 1 / 3, 1 / 3]),
        "confidence": diff_dec.get("confidence", 0.0),
        "epistemic": _safe_get_field(diff_dec, "epistemic", 0.0, float),
        "aleatoric": _safe_get_field(diff_dec, "aleatoric", 0.0, float),
    }

    # 3. AIF-EFE
    efe = state.get("fusion_efe_scores", {}) or {}
    if efe and isinstance(efe, dict) and any(efe.values()):
        efe_vals = np.array([efe.get(a, 0.0) for a in ("buy", "sell", "hold")], dtype=np.float64)
        efe_probs = np.exp(-efe_vals) / (np.exp(-efe_vals).sum() + 1e-30)
        workspace["aif"] = {
            "efe_raw": dict(efe),
            "efe_probs": efe_probs.tolist(),
            "belief": str(state.get("aif_belief", ""))[:200],
        }
    else:
        workspace["aif"] = {"efe_raw": {}, "efe_probs": [1 / 3, 1 / 3, 1 / 3], "belief": "N/A"}

    # 4. 分析师报告（用字符数作为"信息量"指标）
    analysts_report: dict[str, int] = {}
    for key in ("market_report", "fundamentals_report", "news_report", "sentiment_report"):
        text = state.get(key, "")
        name = key.replace("_report", "")
        analysts_report[name] = len(text) if text else 0
    workspace["analysts"] = analysts_report

    # 5. HSR-MC
    hsrc = state.get("hsrc_mc", {}) or {}
    hsrc_meta = state.get("hsrc_mc_meta", {}) or {}
    workspace["hsrc_mc"] = {
        "regime": hsrc.get("regime", {}),
        "health": _safe_get_field(hsrc, "health", 1.0, float),
        "health_score": _safe_get_field(hsrc, "health_score", _safe_get_field(hsrc, "health", 1.0, float), float),
        "anomalies_count": len(hsrc.get("anomalies", []) or []),
        "self_model_stats": hsrc_meta.get("self_model_stats", {}),
    }

    # 6. L-IWM
    liwm = state.get("l_iwm", {}) or {}
    prediction_errors = state.get("prediction_errors", []) or []
    workspace["l_iwm"] = {
        "ewc_loss": liwm.get("ewc_loss", 0) if isinstance(liwm.get("ewc_loss"), (int, float)) else 0,
        "prediction_errors": (prediction_errors[-5:] if isinstance(prediction_errors, list) else []),
        "module_perf": state.get("module_performance", {}),
    }

    # 7. HPC
    hpc_state_val = state.get("hpc_state", {}) or {}
    # [Fix 方案C] reducer 保证 hpc_state 是 dict，但保留防御性退化
    if not isinstance(hpc_state_val, dict):
        hpc_state_val = {}
    pe = 0.0
    last_pe = hpc_state_val.get("last_prediction_error")
    if isinstance(last_pe, dict):
        pe = _safe_get_field(last_pe, "total", 0.0, float)
    elif isinstance(last_pe, (int, float)):
        pe = float(last_pe)
    workspace["hpc"] = {
        "prediction_error": pe,
        "selected_action": hpc_state_val.get("selected_action", ""),
    }

    return workspace


def compute_attention(workspace: dict, config: dict | None = None) -> dict:
    """计算各模块的注意力权重。

    核心公式:
        attention(m) = softmax(saliency(m) / temperature)

        saliency(m) 基于:
        - 置信度 (trader/diffusion — 高置信 = 高显著)
        - EFE区分度 (AIF — 买/卖/持的EFE差异大 = 高显著)
        - 异常数量 (HSR-MC — 异常多 = 高显著)
        - 预测误差 (L-IWM/HPC — 误差大 = 环境变化 = 高显著)
        - 信息量 (analysts — 报告长 = 高显著)

    Reference:
    - Friston 2009 "The free-energy principle: a rough guide to the brain?"
    - Haken 1983 "Synergetics" — 注意力作为序参量
    - AgentVerse arXiv:2308.10848 — 动态代理优先级

    Args:
        workspace: 全局工作空间字典
        config: 可选配置 dict, 支持 attention_temperature (default 1.0)

    Returns:
        dict: {"attention": {"trader": 0.x, ...}, "_temperature": 0.x, "_entropy": 0.x, "_conflict": 0.x}
    """
    if config is None:
        config = {}
    temperature = _safe_get_field(config, "attention_temperature", 1.0, float)

    raw_scores: dict[str, float] = {}

    # --- 1. trader: 置信度 ---
    trader = workspace.get("trader", {}) or {}
    raw_scores["trader"] = _safe_get_field(trader, "confidence", 0.5, float)

    # --- 2. diffusion: 置信度 - 不确定性 ---
    diff = workspace.get("diffusion", {}) or {}
    diff_conf = _safe_get_field(diff, "confidence", 0.5, float)
    diff_epi = _safe_get_field(diff, "epistemic", 0.0, float)
    diff_alea = _safe_get_field(diff, "aleatoric", 0.0, float)
    raw_scores["diffusion"] = max(0.01, diff_conf - (diff_epi + diff_alea) * 0.5)

    # --- 3. aif: EFE 区分度 ---
    aif = workspace.get("aif", {}) or {}
    efe_raw = aif.get("efe_raw", {}) or {}
    if efe_raw:
        efe_vals_list = [_safe_get_field(efe_raw, a, 0.0, float) for a in ("buy", "sell", "hold")]
        efe_range = max(efe_vals_list) - min(efe_vals_list)
        efe_mean = abs(np.mean(efe_vals_list)) + 1e-8
        raw_scores["aif"] = min(efe_range / efe_mean, 2.0)
    else:
        raw_scores["aif"] = 0.1  # 无数据 → 低显著

    # --- 4. hsrc_mc: 异常数量 / 健康度 ---
    hsrc = workspace.get("hsrc_mc", {}) or {}
    n_anomalies = int(hsrc.get("anomalies_count", 0))
    # 优先使用预提取的 health_score，降低 _safe_get_field 的字典解析开销
    health = _safe_get_field(hsrc, "health_score",
               _safe_get_field(hsrc, "health", 1.0, float), float)
    raw_scores["hsrc_mc"] = min(n_anomalies * (1.0 / max(health, 0.1)), 3.0)

    # --- 5. l_iwm: 平均预测误差 ---
    liwm = workspace.get("l_iwm", {}) or {}
    pes = liwm.get("prediction_errors", []) or []
    if isinstance(pes, list) and len(pes) > 0:
        numeric_pes = [abs(float(p)) for p in pes if isinstance(p, (int, float))]
        avg_pe = float(np.mean(numeric_pes)) if numeric_pes else 0.0
    else:
        avg_pe = 0.0
    raw_scores["l_iwm"] = min(avg_pe * 2, 2.0)

    # --- 6. hpc: 预测误差 ---
    hpc = workspace.get("hpc", {}) or {}
    hpc_pe = _safe_get_field(hpc, "prediction_error", 0.0, float)
    raw_scores["hpc"] = min(abs(hpc_pe) * 3, 2.0)

    # --- 7. analysts: 报告总字符数 ---
    analysts = workspace.get("analysts", {}) or {}
    total_chars = sum(analysts.values()) if isinstance(analysts, dict) else 0
    raw_scores["analysts"] = min(total_chars / 2000.0, 1.0) if total_chars > 0 else 0.1

    # === 冲突检测: 用 Jensen-Shannon 散度衡量 trader/diff/aif 之间的分歧 ===
    probs_list: list[list[float]] = []
    for key in ("trader", "diffusion", "aif"):
        entry = workspace.get(key, {}) or {}
        p = entry.get("probs") or entry.get("action_probs") or entry.get("efe_probs")
        if p and isinstance(p, (list, tuple)) and len(p) == 3:
            probs_list.append([float(v) for v in p])

    conflict = 0.0
    if len(probs_list) >= 2:
        jsds: list[float] = []
        eps_js = 1e-10
        for i in range(len(probs_list)):
            for j in range(i + 1, len(probs_list)):
                p_i = [max(float(v), eps_js) for v in probs_list[i]]
                p_j = [max(float(v), eps_js) for v in probs_list[j]]
                # 归一化确保总和为1
                s_i, s_j = sum(p_i), sum(p_j)
                p_i = [v / s_i for v in p_i] if s_i > 0 else [1/3]*3
                p_j = [v / s_j for v in p_j] if s_j > 0 else [1/3]*3
                m = [(a + b) / 2.0 for a, b in zip(p_i, p_j)]
                kl_i = sum(pa * np.log(pa / max(mq, eps_js)) for pa, mq in zip(p_i, m))
                kl_j = sum(pb * np.log(pb / max(mq, eps_js)) for pb, mq in zip(p_j, m))
                jsd = (kl_i + kl_j) / 2.0
                if not np.isnan(jsd) and not np.isinf(jsd):
                    jsds.append(float(jsd))
        conflict = float(np.mean(jsds)) if jsds else 0.0

    # 温度调节: 高冲突 → 高温度 (注意力更分散, 更探索)
    effective_temp = temperature * (1.0 + conflict * 2.0)

    # === Softmax 分配最终注意力权重 ===
    if raw_scores:
        scores = np.array(list(raw_scores.values()), dtype=np.float64)
        scores = np.clip(scores, 0.01, None)  # 保证正值
        scores = scores / effective_temp
        scores = scores - float(np.max(scores))  # 数值稳定
        attention: dict[str, float] = {}
        exp_scores = np.exp(scores)
        exp_sum = float(np.sum(exp_scores)) + 1e-30
        for key, exp_val in zip(raw_scores.keys(), exp_scores):
            attention[key] = float(exp_val) / exp_sum

        # 归一化确保精确 1.0
        total_att = sum(attention.values())
        if total_att > 0:
            for k in attention:
                attention[k] /= total_att
    else:
        attention = {}
        effective_temp = temperature
        conflict = 0.0

    # 注意力熵 (不确定性指标)
    att_vals = np.array(list(attention.values()), dtype=np.float64) if attention else np.array([1.0])
    entropy = -float(np.sum(att_vals * np.log(att_vals + 1e-30)))

    return {
        "attention": attention,
        "_temperature": effective_temp,
        "_entropy": entropy,
        "_conflict": conflict,
    }


def apply_attention_to_prompt(workspace: dict, attention: dict) -> str:
    """根据注意力权重生成 MoA 综合器的加权提示词。

    高注意力模块 → 提示词中靠前 + 详细展示 (最多 500 字符)
    低注意力模块 → 提示词中靠后 + 摘要展示 (最多 100 字符)
    累计注意力 < 5% 的模块 → 不展示 (节省 token + 降低噪音)

    参考:
    - 计算神经科学: 选择性注意是大脑处理信息的核心机制 (Treisman 1969)
    - 道家: "少则得, 多则惑" — 减少不必要的信息输入

    Args:
        workspace: 全局工作空间
        attention: compute_attention 的输出

    Returns:
        str: 加权提示词
    """
    att_map = attention.get("attention", {}) or {}
    if not att_map:
        # 兜底: 无注意力 → 默认提示
        return "综合以下所有模块输出, 给出最终交易决策。"

    # 按注意力降序排列, 计算累计
    sorted_modules = sorted(att_map.items(), key=lambda x: -x[1])
    cum = 0.0
    threshold = 0.95
    full_modules: list[str] = []
    summary_modules: list[str] = []
    for name, weight in sorted_modules:
        if weight < 0.01:
            break  # 低于 1% → 忽略
        if cum < threshold:
            full_modules.append(name)
        else:
            summary_modules.append(name)
        cum += weight

    conflict = _safe_get_field(attention, "_conflict", 0.0, float)
    entropy = _safe_get_field(attention, "_entropy", 0.0, float)

    parts = [
        "你是一位顶级股票投资决策综合师。以下证据按注意力权重排列（权重越高越重要）。",
        "",
        "请严格输出 JSON 格式：",
        f'  {{"action": "buy"|"sell"|"hold", "confidence": 0.0~1.0, "reasoning": "...", "key_factors": [...]}}',
        "",
    ]

    # --- 高注意力模块: 详细展示 ---
    for name in full_modules:
        weight = att_map.get(name, 0)
        parts.append(f"[{name}] (注意力={weight:.2f})")
        detail = _get_module_detail(workspace, name)
        if len(detail) > 500:
            detail = detail[:500] + "...(截断)"
        parts.append(detail if detail else "(无数据)")
        parts.append("")

    # --- 低注意力模块: 摘要展示 ---
    if summary_modules:
        parts.append("[其他模块 — 摘要]")
        for name in summary_modules:
            weight = att_map.get(name, 0)
            if weight < 0.01:
                continue
            summary = _get_module_summary(workspace, name)
            parts.append(f"  {name}(att={weight:.2f}): {summary[:120]}")
        parts.append("")

    # --- 冲突/不确定度提示 ---
    if conflict > 0.3:
        parts.append(f"⚠️ 模块间存在显著冲突 (conflict={conflict:.2f})，需要你判断哪方证据更可信。")
    if entropy > 1.5:
        parts.append(f"💡 注意力分布熵={entropy:.2f}，说明各模块输出分散，需仔细权衡。")

    return "\n".join(parts)


def _get_module_detail(workspace: dict, name: str) -> str:
    """获取指定模块的详细描述（供 apply_attention_to_prompt 使用）。"""
    entry = workspace.get(name, {}) or {}
    if name == "trader":
        probs = entry.get("probs", [])
        return (f"计划摘要: {entry.get('plan_summary', 'N/A')}\n"
                f"概率→ buy={probs[0]:.3f} sell={probs[1]:.3f} hold={probs[2]:.3f} "
                f"置信度={entry.get('confidence', 0):.2f}")
    elif name == "diffusion":
        ap = entry.get("action_probs", [])
        return (f"动作概率→ buy={ap[0]:.3f} sell={ap[1]:.3f} hold={ap[2]:.3f}\n"
                f"置信度={entry.get('confidence', 0):.2f} "
                f"认知不确定性={entry.get('epistemic', 'N/A')} "
                f"偶然不确定性={entry.get('aleatoric', 'N/A')}")
    elif name == "aif":
        ep = entry.get("efe_probs", [])
        return (f"EFE→ buy={ep[0]:.3f} sell={ep[1]:.3f} hold={ep[2]:.3f}\n"
                f"信念: {entry.get('belief', 'N/A')}")
    elif name == "hsrc_mc":
        return (f"制度: {entry.get('regime', {})}\n"
                f"健康度: {entry.get('health', 1.0):.2f} "
                f"异常数: {entry.get('anomalies_count', 0)}")
    elif name == "l_iwm":
        pes = entry.get("prediction_errors", []) or []
        pe_str = f"{np.mean([abs(p) for p in pes if isinstance(p, (int, float))]):.4f}" if pes else "N/A"
        return (f"EWC loss: {entry.get('ewc_loss', 0):.4f}\n"
                f"预测误差: {pe_str}")
    elif name == "hpc":
        return (f"预测误差: {entry.get('prediction_error', 0):.4f}\n"
                f"选定动作: {entry.get('selected_action', 'N/A')}")
    elif name == "analysts":
        if isinstance(entry, dict):
            return f"报告字符数: {entry}"
        return f"分析师: {entry}"
    return str(entry)[:300]


def _get_module_summary(workspace: dict, name: str) -> str:
    """获取指定模块的摘要描述（供 apply_attention_to_prompt 使用）。"""
    entry = workspace.get(name, {}) or {}
    if name == "trader":
        probs = entry.get("probs", [])
        conf = entry.get("confidence", 0)
        return f"方向={['买','卖','持'][int(np.argmax(probs))]} conf={conf:.2f}"
    elif name == "diffusion":
        ap = entry.get("action_probs", [])
        return (f"方向={['买','卖','持'][int(np.argmax(ap))]} "
                f"conf={entry.get('confidence', 0):.2f}")
    elif name == "aif":
        ep = entry.get("efe_probs", [])
        return f"方向={['买','卖','持'][int(np.argmax(ep))]}"
    elif name == "hsrc_mc":
        return f"异常={entry.get('anomalies_count', 0)} 健康={entry.get('health', 1.0):.2f}"
    elif name == "l_iwm":
        return f"EWC={entry.get('ewc_loss', 0):.2f}"
    elif name == "hpc":
        return f"PE={entry.get('prediction_error', 0):.3f}"
    return str(entry)[:80]


def check_convergence(decision_trace: list) -> tuple[bool, dict]:
    """检查迭代决策是否收敛。

    收敛条件（任一满足）:
    1. 连续 3 轮 action 一致 (强烈收敛)
    2. 连续 2 轮 action 一致 + 置信度变化 < 0.1
    3. 主导模块连续 2 轮相同 + 置信度 > 0.7

    参考:
    - 自由能原理: 收敛 = 自由能达到局部最小值
    - 佛学"止观": 心安住于一处 = 信念稳定

    Args:
        decision_trace: [{"action": "buy|sell|hold", "confidence": 0.x, "dominant_module": "..."}, ...]

    Returns:
        (bool, dict): (是否收敛, {"reason": "...", "confidence": 0.x})
    """
    if not isinstance(decision_trace, list) or len(decision_trace) < 2:
        return False, {"reason": "迭代次数不足", "confidence": 0.0}

    trace = decision_trace  # 已排序的迭代记录

    # 条件 1: 连续 3 轮一致
    if len(trace) >= 3:
        if trace[-1]["action"] == trace[-2]["action"] == trace[-3]["action"]:
            return True, {
                "reason": f"连续3轮决策一致({trace[-1]['action']})",
                "confidence": max(d["confidence"] for d in trace[-3:]),
            }

    # 条件 2: 连续 2 轮一致 + 置信度稳定
    if len(trace) >= 2 and trace[-1]["action"] == trace[-2]["action"]:
        conf_change = abs(trace[-1]["confidence"] - trace[-2]["confidence"])
        if conf_change < 0.1:
            return True, {
                "reason": f"连续2轮一致({trace[-1]['action']}), 置信度稳定(Δ={conf_change:.3f})",
                "confidence": max(trace[-1]["confidence"], trace[-2]["confidence"]),
            }

    # 条件 3: 主导模块连续 2 轮相同
    if len(trace) >= 2:
        dom1 = trace[-1].get("dominant_module", "")
        dom2 = trace[-2].get("dominant_module", "")
        if dom1 and dom1 == dom2 and trace[-1]["confidence"] > 0.7:
            return True, {
                "reason": f"主导模块一致({dom1}), 高置信度({trace[-1]['confidence']:.2f})",
                "confidence": trace[-1]["confidence"],
            }

    # 未收敛
    action_change = trace[-1]["action"] if len(trace) >= 2 else "N/A"
    return False, {
        "reason": f"未收敛({len(trace)}轮, 最后={action_change})",
        "confidence": trace[-1]["confidence"] if trace else 0.0,
    }


# =============================================================================
# [H14] safe_chain_invoke — 安全 Chain 调用包装器
# =============================================================================
def safe_chain_invoke(chain, input_data: dict) -> AIMessage:
    """安全调用 Chain，自动清理孤儿 tool_calls 并防御性处理异常。

    Args:
        chain: LangChain Chain 实例。
        input_data: 输入数据字典。

    Returns:
        AIMessage: Chain 响应。发生异常时返回包含错误信息的 AIMessage。
    """
    from langchain_core.messages import AIMessage

    try:
        result = chain.invoke(input_data)
        if isinstance(result, AIMessage):
            clean_orphaned_tool_calls(result)
        return result
    except Exception as e:
        logger.error(f"❌ [H14] safe_chain_invoke 调用失败: {e}")
        return AIMessage(content=f"（Chain 调用失败: {e}）")


# =============================================================================
# [H14] clean_orphaned_tool_calls — 清理孤儿 tool_calls
# =============================================================================
def clean_orphaned_tool_calls(response: AIMessage) -> AIMessage:
    """移除 AIMessage 中的孤儿 tool_calls（无对应 ToolMessage 的工具调用）。

    LangGraph 状态机在遇到 orphan tool_calls 时会抛出异常，
    此函数在 LLM 调用后和状态更新前清理这些残留数据。

    Args:
        response: 待清理的 AIMessage。

    Returns:
        AIMessage: 清理后的 AIMessage。
    """
    try:
        if not hasattr(response, "additional_kwargs"):
            return response
        additional_kwargs = response.additional_kwargs or {}
        if "tool_calls" in additional_kwargs:
            # 移除 orphan tool_calls，保留其他 additional_kwargs
            cleaned_kwargs = {k: v for k, v in additional_kwargs.items() if k != "tool_calls"}
            response.additional_kwargs = cleaned_kwargs
            logger.debug("🧹 [H14] clean_orphaned_tool_calls: 已清理 orphan tool_calls")
        return response
    except Exception as e:
        logger.error(f"❌ [H14] clean_orphaned_tool_calls 失败: {e}")
        return response


# =============================================================================
# [H14] get_tool_names — 获取工具名称列表
# =============================================================================
def get_tool_names(tools: list) -> list[str]:
    """从工具列表中提取所有工具的名称。

    兼容 @tool 装饰器函数、BaseTool 实例和任意 callable。

    Args:
        tools: 工具列表（每个元素可以是 @tool 函数、BaseTool 或 callable）。

    Returns:
        list[str]: 工具名称列表。
    """
    try:
        names: list[str] = []
        for tool in tools:
            if hasattr(tool, "name"):
                names.append(tool.name)
            elif hasattr(tool, "__name__"):
                names.append(tool.__name__)
            else:
                names.append(str(tool))
        return names
    except Exception as e:
        logger.error(f"❌ [H14] get_tool_names 失败: {e}")
        return []


# =============================================================================
# [H14] invoke_with_timeout — 带超时的函数调用
# =============================================================================
def invoke_with_timeout(
    func,
    args: dict | tuple | None = None,
    timeout: int = 30,
    timeout_msg: str = "操作",
) -> Any:
    """带超时保护的安全函数调用包装器。

    使用 concurrent.futures 实现超时控制，防止 LLM 或工具调用阻塞过长。

    Args:
        func: 要调用的可执行对象。
        args: 调用参数。dict 类型会解包为 **kwargs，tuple 会解包为 *args。
        timeout: 超时秒数（默认 30s）。
        timeout_msg: 超时日志中的操作描述。

    Returns:
        函数执行结果，超时或异常时返回空字符串。
    """
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            if isinstance(args, dict):
                future = executor.submit(func, **args)
            elif isinstance(args, tuple):
                future = executor.submit(func, *args)
            elif args is not None:
                future = executor.submit(func, args)
            else:
                future = executor.submit(func)

            try:
                result = future.result(timeout=timeout)
                return result
            except concurrent.futures.TimeoutError:
                logger.warning(f"⏰ [H14] {timeout_msg} 超时 ({timeout}s)")
                return ""
    except Exception as e:
        logger.error(f"❌ [H14] {timeout_msg} 调用失败: {e}")
        return ""


# =============================================================================
# [H14] is_deepseek_via_openai — 检测 ChatOpenAI 包装的 DeepSeek 模型
# =============================================================================
def is_deepseek_via_openai(llm) -> bool:
    """检测 LLM 实例是否为通过 ChatOpenAI 接口调用的 DeepSeek 模型。

    DeepSeek 模型在通过 ChatOpenAI 包装时，__class__.__name__ 为 ChatOpenAI，
    但 model name 包含 "deepseek" 关键词。此函数检测此特殊情况以便
    调用方采取兼容性处理（如强制预取新闻数据）。

    Args:
        llm: LLM 实例。

    Returns:
        bool: 如果检测到 DeepSeek 模型返回 True，否则 False。
    """
    try:
        model_name = getattr(llm, "model_name", "") or getattr(llm, "model", "") or ""
        return "deepseek" in model_name.lower()
    except Exception:
        return False


# =============================================================================
# [H14] are_all_reports_empty — 检查所有分析师报告是否为空
# =============================================================================
def are_all_reports_empty(state: dict) -> bool:
    """检查 state 中所有分析师报告是否都为空。

    用于 [H10 数据源全故障降级] 策略，当所有数据源均无法获取数据时，
    跳过 LLM 调用和辩论阶段，直接进入降级处理。

    Args:
        state: AgentState 字典，应包含以下键：
            - market_report: 市场分析报告
            - sentiment_report: 情绪分析报告
            - news_report: 新闻分析报告
            - fundamentals_report: 基本面分析报告

    Returns:
        bool: 所有报告均为空时返回 True，否则 False。
    """
    try:
        reports = [
            state.get("market_report", ""),
            state.get("sentiment_report", ""),
            state.get("news_report", ""),
            state.get("fundamentals_report", ""),
        ]
        return all(not r or not r.strip() for r in reports)
    except Exception as e:
        logger.error(f"❌ [H14] are_all_reports_empty 检查失败: {e}")
        return False




# ═══════════════════════════════════════════════════════════
# 工具注册表 — 方案 C
# 用途：将 @tool 方法按分类注册，graph 层通过注册表获取工具，
# 替代 self.toolkit.XXX 的硬编码属性引用。缺失工具自动跳过。
#
# 注：register 是模块级函数而非类方法，因为 Python 类体执行时
# 类名还不可用，无法在类体内使用 @Toolkit.register("cat")。
# 作为模块级函数可以正确工作，且 _REGISTRY 被类通过引用共享。
# ═══════════════════════════════════════════════════════════
_TOOLKIT_REGISTRY: dict[str, list[str]] = {}
"""category → [tool_method_name, ...]. 注册顺序即工具在 ToolNode 中的排列顺序。"""

def toolkit_register(category: str):
    """注册一个 Toolkit 方法到指定分类（模块级装饰器）。

    用法 (装饰器顺序):
        @staticmethod        # 4th (outermost)
        @tool                # 3rd
        @log_tool_call(...)  # 2nd (optional)
        @toolkit_register("fundamentals")  # 1st (closest to def)
        def my_tool(...):

    原理: 使用模块级 dict _TOOLKIT_REGISTRY 存储注册信息，
    Toolkit._registry 引用同一个 dict，所有 classmethod 方法
    通过 cls._registry 访问相同数据。
    """
    def decorator(func):
        name = func.__name__
        if name not in _TOOLKIT_REGISTRY.setdefault(category, []):
            _TOOLKIT_REGISTRY[category].append(name)
            logger.debug(f"📝 [注册表] {name} → {category}")
        return func
    return decorator


class Toolkit:
    _config = DEFAULT_CONFIG.copy()
    _registry = _TOOLKIT_REGISTRY  # 引用模块级注册表 dict

    # 注册表方法（classmethod，通过 cls._registry 访问共享数据）
    @classmethod
    def get_tools(cls, category: str):
        """获取指定分类的所有已注册工具列表。"""
        names = cls._registry.get(category, [])
        tools = []
        for name in names:
            fn = getattr(cls, name, None)
            if fn is not None:
                tools.append(fn)
            else:
                logger.warning(f"⚠️ [注册表] 方法 '{name}' 注册到 '{category}' 但不存在，跳过")
        return tools

    @classmethod
    def validate_registry(cls) -> list[str]:
        """校验所有注册方法是否存在。返回缺失列表，空 = 通过。"""
        missing = []
        for cat, names in cls._registry.items():
            for name in names:
                if not hasattr(cls, name):
                    missing.append(f"{cat}/{name}")
                    logger.error(f"❌ [注册表] 注册方法缺失: {cat}/{name}")
        return missing

    @classmethod
    def dump_registry(cls) -> dict[str, list[str]]:
        """返回注册表快照（用于调试/日志）。"""
        return {cat: list(names) for cat, names in cls._registry.items()}

    @classmethod
    def update_config(cls, config):
        """Update the class-level configuration."""
        cls._config.update(config)

    @property
    def config(self):
        """Access the configuration."""
        return self._config

    def __init__(self, config=None):
        if config:
            self.update_config(config)

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_chinese_social_sentiment 已删除，使用 get_stock_sentiment_unified
    def get_chinese_social_sentiment(
        ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ) -> str:
        """
        获取中国社交媒体和财经平台上关于特定股票的情绪分析和讨论热度。
        整合雪球、东方财富股吧、新浪财经等中国本土平台的数据。
        Args:
            ticker (str): 股票代码，如 AAPL, TSM
            curr_date (str): 当前日期，格式为 yyyy-mm-dd
        Returns:
            str: 包含中国投资者情绪分析、讨论热度、关键观点的格式化报告
        """
        try:
            # 这里可以集成多个中国平台的数据
            chinese_sentiment_results = interface.get_chinese_social_sentiment(ticker, curr_date)
            return chinese_sentiment_results
        except Exception:
            return ""

    @staticmethod
    # @tool  # 已移除：请使用 get_stock_fundamentals_unified 或 get_stock_market_data_unified
    def get_china_stock_data(
        stock_code: Annotated[str, "中国股票代码，如 000001(平安银行), 600519(贵州茅台)"],
        start_date: Annotated[str, "开始日期，格式 yyyy-mm-dd"],
        end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
    ) -> str:
        """
        获取中国A股实时和历史数据，通过Tushare等高质量数据源提供专业的股票数据。
        支持实时行情、历史K线、技术指标等全面数据，自动使用最佳数据源。
        Args:
            stock_code (str): 中国股票代码，如 000001(平安银行), 600519(贵州茅台)
            start_date (str): 开始日期，格式 yyyy-mm-dd
            end_date (str): 结束日期，格式 yyyy-mm-dd
        Returns:
            str: 包含实时行情、历史数据、技术指标的完整股票分析报告
        """
        try:
            logger.debug("📊 [DEBUG] ===== agent_utils.get_china_stock_data 开始调用 =====")
            logger.debug(f"📊 [DEBUG] 参数: stock_code={stock_code}, start_date={start_date}, end_date={end_date}")

            from tradingagents.dataflows.interface import get_china_stock_data_unified

            logger.debug("📊 [DEBUG] 成功导入统一数据源接口")

            logger.debug("📊 [DEBUG] 正在调用统一数据源接口...")
            result = get_china_stock_data_unified(stock_code, start_date, end_date)

            logger.debug("📊 [DEBUG] 统一数据源接口调用完成")
            logger.debug(f"📊 [DEBUG] 返回结果类型: {type(result)}")
            logger.debug(f"📊 [DEBUG] 返回结果长度: {len(result) if result else 0}")
            logger.debug(f"📊 [DEBUG] 返回结果前200字符: {str(result)[:200]}...")
            logger.debug("📊 [DEBUG] ===== agent_utils.get_china_stock_data 调用结束 =====")

            return result
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            logger.error("❌ [DEBUG] ===== agent_utils.get_china_stock_data 异常 =====")
            logger.error(f"❌ [DEBUG] 错误类型: {type(e).__name__}")
            logger.error(f"❌ [DEBUG] 错误信息: {e!s}")
            logger.error("❌ [DEBUG] 详细堆栈:")
            print(error_details)
            logger.error("❌ [DEBUG] ===== 异常处理结束 =====")
            return f"中国股票数据获取失败: {e!s}。请检查网络连接或稍后重试。"

    @staticmethod
    @tool
    @toolkit_register("market")
    def get_china_market_overview(
        curr_date: Annotated[str, "当前日期，格式 yyyy-mm-dd"],
    ) -> str:
        """
        获取中国股市整体概览，包括主要指数的实时行情。
        涵盖上证指数、深证成指、创业板指、科创50等主要指数。
        Args:
            curr_date (str): 当前日期，格式 yyyy-mm-dd
        Returns:
            str: 包含主要指数实时行情的市场概览报告
        """
        try:
            # 使用Tushare获取主要指数数据
            from tradingagents.dataflows.providers.china.tushare import get_tushare_adapter

            adapter = get_tushare_adapter()

            # 使用Tushare获取主要指数信息
            # 这里可以扩展为获取具体的指数数据
            return f"""# 中国股市概览 - {curr_date}

## 📊 主要指数
- 上证指数: 数据获取中...
- 深证成指: 数据获取中...
- 创业板指: 数据获取中...
- 科创50: 数据获取中...

## 💡 说明
市场概览功能正在从TDX迁移到Tushare，完整功能即将推出。
当前可以使用股票数据获取功能分析个股。

数据来源: Tushare专业数据源
更新时间: {curr_date}
"""

        except Exception as e:
            return f"中国市场概览获取失败: {e!s}。正在从TDX迁移到Tushare数据源。"

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_YFin_data 已删除，使用 get_stock_market_data_unified
    def get_YFin_data(
        symbol: Annotated[str, "ticker symbol of the company"],
        start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
        end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    ) -> str:
        """
        Retrieve the stock price data for a given ticker symbol from Yahoo Finance.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            start_date (str): Start date in yyyy-mm-dd format
            end_date (str): End date in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
        """

        result_data = interface.get_YFin_data(symbol, start_date, end_date)

        return result_data

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_YFin_data_online 已删除，使用 get_stock_market_data_unified
    def get_YFin_data_online(
        symbol: Annotated[str, "ticker symbol of the company"],
        start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
        end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    ) -> str:
        """
        Retrieve the stock price data for a given ticker symbol from Yahoo Finance.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            start_date (str): Start date in yyyy-mm-dd format
            end_date (str): End date in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
        """

        result_data = interface.get_YFin_data_online(symbol, start_date, end_date)

        return result_data

    @staticmethod
    @tool
    @toolkit_register("market")
    def get_stockstats_indicators_report(
        symbol: Annotated[str, "ticker symbol of the company"],
        indicator: Annotated[str, "technical indicator to get the analysis and report of"],
        curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
        look_back_days: Annotated[int, "how many days to look back"] = 30,
    ) -> str:
        """
        Retrieve stock stats indicators for a given ticker symbol and indicator.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            indicator (str): Technical indicator to get the analysis and report of
            curr_date (str): The current trading date you are trading on, YYYY-mm-dd
            look_back_days (int): How many days to look back, default is 30
        Returns:
            str: A formatted dataframe containing the stock stats indicators for the specified ticker symbol and indicator.
        """

        result_stockstats = interface.get_stock_stats_indicators_window(
            symbol, indicator, curr_date, look_back_days, False,
        )

        return result_stockstats

    @staticmethod
    @tool
    @toolkit_register("market")
    def get_stockstats_indicators_report_online(
        symbol: Annotated[str, "ticker symbol of the company"],
        indicator: Annotated[str, "technical indicator to get the analysis and report of"],
        curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
        look_back_days: Annotated[int, "how many days to look back"] = 30,
    ) -> str:
        """
        Retrieve stock stats indicators for a given ticker symbol and indicator.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            indicator (str): Technical indicator to get the analysis and report of
            curr_date (str): The current trading date you are trading on, YYYY-mm-dd
            look_back_days (int): How many days to look back, default is 30
        Returns:
            str: A formatted dataframe containing the stock stats indicators for the specified ticker symbol and indicator.
        """

        result_stockstats = interface.get_stock_stats_indicators_window(
            symbol, indicator, curr_date, look_back_days, True,
        )

        return result_stockstats

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_simfin_balance_sheet 已删除，使用 get_stock_fundamentals_unified
    def get_simfin_balance_sheet(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent balance sheet of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
            str: a report of the company's most recent balance sheet
        """

        data_balance_sheet = interface.get_simfin_balance_sheet(ticker, freq, curr_date)

        return data_balance_sheet

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_simfin_cashflow 已删除，使用 get_stock_fundamentals_unified
    def get_simfin_cashflow(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent cash flow statement of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
                str: a report of the company's most recent cash flow statement
        """

        data_cashflow = interface.get_simfin_cashflow(ticker, freq, curr_date)

        return data_cashflow

    @staticmethod
    # @tool  # 已禁用：底层 interface.get_simfin_income_statements 已删除，使用 get_stock_fundamentals_unified
    def get_simfin_income_stmt(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent income statement of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
                str: a report of the company's most recent income statement
        """

        data_income_stmt = interface.get_simfin_income_statements(ticker, freq, curr_date)

        return data_income_stmt

    @staticmethod
    @tool
    @toolkit_register("news")
    def get_realtime_stock_news(
        ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ) -> str:
        """
        获取股票的实时新闻分析，解决传统新闻源的滞后性问题。
        整合多个专业财经API，提供15-30分钟内的最新新闻。
        支持多种新闻源轮询机制，优先使用实时新闻聚合器，失败时自动尝试备用新闻源。
        对于A股和港股，会优先使用中文财经新闻源（如东方财富）。

        Args:
            ticker (str): 股票代码，如 AAPL, TSM, 600036.SH
            curr_date (str): 当前日期，格式为 yyyy-mm-dd
        Returns:
            str: 包含实时新闻分析、紧急程度评估、时效性说明的格式化报告
        """
        from tradingagents.dataflows.news.news_source_manager import get_news_report
        # 使用用户的东方财富/新浪/雪球中文新闻爬虫
        news_data = get_news_report(ticker, company_name=ticker, max_news=20)
        return news_data

    @staticmethod
    # @tool  # 已移除：请使用 get_stock_fundamentals_unified
    def get_fundamentals_openai(
        ticker: Annotated[str, "the company's ticker"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest fundamental information about a given stock on a given date by using OpenAI's news API.
        Args:
            ticker (str): Ticker of a company. e.g. AAPL, TSM
            curr_date (str): Current date in yyyy-mm-dd format
        Returns:
            str: A formatted string containing the latest fundamental information about the company on the given date.
        """
        logger.debug(f"📊 [DEBUG] get_fundamentals_openai 被调用: ticker={ticker}, date={curr_date}")

        # 检查是否为中国股票
        import re

        if re.match(r"^\d{6}$", str(ticker)):
            logger.debug(f"📊 [DEBUG] 检测到中国A股代码: {ticker}")
            # 使用统一接口获取中国股票名称
            try:
                from tradingagents.dataflows.interface import get_china_stock_info_unified

                stock_info = get_china_stock_info_unified(ticker)

                # 解析股票名称
                if "股票名称:" in stock_info:
                    company_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                else:
                    company_name = f"股票代码{ticker}"

                logger.debug(f"📊 [DEBUG] 中国股票名称映射: {ticker} -> {company_name}")
            except Exception as e:
                logger.error(f"⚠️ [DEBUG] 从统一接口获取股票名称失败: {e}")
                company_name = f"股票代码{ticker}"

            # 修改查询以包含正确的公司名称
            modified_query = f"{company_name}({ticker})"
            logger.debug(f"📊 [DEBUG] 修改后的查询: {modified_query}")
        else:
            logger.debug(f"📊 [DEBUG] 检测到非中国股票: {ticker}")
            modified_query = ticker

        try:
            openai_fundamentals_results = interface.get_fundamentals_openai(modified_query, curr_date)
            logger.debug(
                f"📊 [DEBUG] OpenAI基本面分析结果长度: {len(openai_fundamentals_results) if openai_fundamentals_results else 0}",
            )
            return openai_fundamentals_results
        except Exception as e:
            logger.error(f"❌ [DEBUG] OpenAI基本面分析失败: {e!s}")
            return f"基本面分析失败: {e!s}"

    @staticmethod
    # @tool  # 已移除：请使用 get_stock_fundamentals_unified
    def get_china_fundamentals(
        ticker: Annotated[str, "中国A股股票代码，如600036"],
        curr_date: Annotated[str, "当前日期，格式为yyyy-mm-dd"],
    ):
        """
        获取中国A股股票的基本面信息，使用中国股票数据源。
        Args:
            ticker (str): 中国A股股票代码，如600036, 000001
            curr_date (str): 当前日期，格式为yyyy-mm-dd
        Returns:
            str: 包含股票基本面信息的格式化字符串
        """
        logger.debug(f"📊 [DEBUG] get_china_fundamentals 被调用: ticker={ticker}, date={curr_date}")

        # 检查是否为中国股票
        import re

        if not re.match(r"^\d{6}$", str(ticker)):
            return f"错误：{ticker} 不是有效的中国A股代码格式"

        try:
            # 使用统一数据源接口获取股票数据（默认Tushare，支持备用数据源）
            from tradingagents.dataflows.interface import get_china_stock_data_unified

            logger.debug(f"📊 [DEBUG] 正在获取 {ticker} 的股票数据...")

            # 获取最近30天的数据用于基本面分析
            from datetime import datetime, timedelta

            end_date = datetime.strptime(curr_date, "%Y-%m-%d")
            start_date = end_date - timedelta(days=30)

            stock_data = get_china_stock_data_unified(
                ticker, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
            )

            logger.debug(f"📊 [DEBUG] 股票数据获取完成，长度: {len(stock_data) if stock_data else 0}")

            if not stock_data or "获取失败" in stock_data or "❌" in stock_data:
                return f"无法获取股票 {ticker} 的基本面数据：{stock_data}"

            # 调用真正的基本面分析
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

            # 创建分析器实例
            analyzer = OptimizedChinaDataProvider()

            # 生成真正的基本面分析报告
            fundamentals_report = analyzer._generate_fundamentals_report(ticker, stock_data)

            logger.debug("📊 [DEBUG] 中国基本面分析报告生成完成")
            logger.debug(f"📊 [DEBUG] get_china_fundamentals 结果长度: {len(fundamentals_report)}")

            return fundamentals_report

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            logger.error("❌ [DEBUG] get_china_fundamentals 失败:")
            logger.error(f"❌ [DEBUG] 错误: {e!s}")
            logger.error(f"❌ [DEBUG] 堆栈: {error_details}")
            return f"中国股票基本面分析失败: {e!s}"

    @staticmethod
    # @tool  # 已移除：请使用 get_stock_fundamentals_unified 或 get_stock_market_data_unified
    def get_hk_stock_data_unified(
        symbol: Annotated[str, "港股代码，如：0700.HK、9988.HK等"],
        start_date: Annotated[str, "开始日期，格式：YYYY-MM-DD"],
        end_date: Annotated[str, "结束日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        获取港股数据的统一接口，优先使用AKShare数据源，备用Yahoo Finance

        Args:
            symbol: 港股代码 (如: 0700.HK)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            str: 格式化的港股数据
        """
        logger.debug(
            f"🇭🇰 [DEBUG] get_hk_stock_data_unified 被调用: symbol={symbol}, start_date={start_date}, end_date={end_date}",
        )

        try:
            from tradingagents.dataflows.interface import get_hk_stock_data_unified

            result = get_hk_stock_data_unified(symbol, start_date, end_date)

            logger.debug(f"🇭🇰 [DEBUG] 港股数据获取完成，长度: {len(result) if result else 0}")

            return result

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            logger.error("❌ [DEBUG] get_hk_stock_data_unified 失败:")
            logger.error(f"❌ [DEBUG] 错误: {e!s}")
            logger.error(f"❌ [DEBUG] 堆栈: {error_details}")
            return f"港股数据获取失败: {e!s}"

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_fundamentals_unified", log_args=True)
    @toolkit_register("fundamentals")
    def get_stock_fundamentals_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        start_date: Annotated[str, "开始日期，格式：YYYY-MM-DD"] = None,
        end_date: Annotated[str, "结束日期，格式：YYYY-MM-DD"] = None,
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"] = None,
    ) -> str:
        """
        统一的股票基本面分析工具
        自动识别股票类型（A股、港股、美股）并调用相应的数据源
        支持基于分析级别的数据获取策略

        Args:
            ticker: 股票代码（如：000001、0700.HK、AAPL）
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）
            curr_date: 当前日期（可选，格式：YYYY-MM-DD）

        Returns:
            str: 基本面分析数据和报告
        """
        logger.info(f"📊 [统一基本面工具] 分析股票: {ticker}")

        # 🔧 获取分析级别配置，支持基于级别的数据获取策略
        research_depth = Toolkit._config.get("research_depth", "标准")
        logger.info(f"🔧 [分析级别] 当前分析级别: {research_depth}")

        # 数字等级到中文等级的映射
        numeric_to_chinese = {1: "快速", 2: "基础", 3: "标准", 4: "深度", 5: "全面"}

        # 标准化研究深度：支持数字输入
        if isinstance(research_depth, (int, float)):
            research_depth = int(research_depth)
            if research_depth in numeric_to_chinese:
                chinese_depth = numeric_to_chinese[research_depth]
                logger.info(f"🔢 [等级转换] 数字等级 {research_depth} → 中文等级 '{chinese_depth}'")
                research_depth = chinese_depth
            else:
                logger.warning(f"⚠️ 无效的数字等级: {research_depth}，使用默认标准分析")
                research_depth = "标准"
        elif isinstance(research_depth, str):
            # 如果是字符串形式的数字，转换为整数
            if research_depth.isdigit():
                numeric_level = int(research_depth)
                if numeric_level in numeric_to_chinese:
                    chinese_depth = numeric_to_chinese[numeric_level]
                    logger.info(f"🔢 [等级转换] 字符串数字 '{research_depth}' → 中文等级 '{chinese_depth}'")
                    research_depth = chinese_depth
                else:
                    logger.warning(f"⚠️ 无效的字符串数字等级: {research_depth}，使用默认标准分析")
                    research_depth = "标准"
            # 如果已经是中文等级，直接使用
            elif research_depth in ["快速", "基础", "标准", "深度", "全面"]:
                logger.info(f"📝 [等级确认] 使用中文等级: '{research_depth}'")
            else:
                logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用默认标准分析")
                research_depth = "标准"
        else:
            logger.warning(f"⚠️ 无效的研究深度类型: {type(research_depth)}，使用默认标准分析")
            research_depth = "标准"

        # 根据分析级别调整数据获取策略
        # 🔧 修正映射关系：data_depth 应该与 research_depth 保持一致
        if research_depth == "快速":
            # 快速分析：获取基础数据，减少数据源调用
            data_depth = "basic"
            logger.info("🔧 [分析级别] 快速分析模式：获取基础数据")
        elif research_depth == "基础":
            # 基础分析：获取标准数据
            data_depth = "standard"
            logger.info("🔧 [分析级别] 基础分析模式：获取标准数据")
        elif research_depth == "标准":
            # 标准分析：获取标准数据（不是full！）
            data_depth = "standard"
            logger.info("🔧 [分析级别] 标准分析模式：获取标准数据")
        elif research_depth == "深度":
            # 深度分析：获取完整数据
            data_depth = "full"
            logger.info("🔧 [分析级别] 深度分析模式：获取完整数据")
        elif research_depth == "全面":
            # 全面分析：获取最全面的数据，包含所有可用数据源
            data_depth = "comprehensive"
            logger.info("🔧 [分析级别] 全面分析模式：获取最全面数据")
        else:
            # 默认使用标准分析
            data_depth = "standard"
            logger.info("🔧 [分析级别] 未知级别，使用标准分析模式")

        # 添加详细的股票代码追踪日志
        logger.info(f"🔍 [股票代码追踪] 统一基本面工具接收到的原始股票代码: '{ticker}' (类型: {type(ticker)})")
        logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(ticker))}")
        logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(ticker))}")

        # 保存原始ticker用于对比
        original_ticker = ticker

        try:
            from datetime import datetime, timedelta

            from tradingagents.utils.stock_utils import StockUtils

            # 自动识别股票类型
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info["is_china"]
            is_hk = market_info["is_hk"]
            is_us = market_info["is_us"]

            logger.info(f"🔍 [股票代码追踪] StockUtils.get_market_info 返回的市场信息: {market_info}")
            logger.info(f"📊 [统一基本面工具] 股票类型: {market_info['market_name']}")
            logger.info(f"📊 [统一基本面工具] 货币: {market_info['currency_name']} ({market_info['currency_symbol']})")

            # 检查ticker是否在处理过程中发生了变化
            if str(ticker) != str(original_ticker):
                logger.warning(
                    f"🔍 [股票代码追踪] 警告：股票代码发生了变化！原始: '{original_ticker}' -> 当前: '{ticker}'",
                )

            # 设置默认日期
            if not curr_date:
                curr_date = datetime.now().strftime("%Y-%m-%d")

            # 基本面分析优化：不需要大量历史数据，只需要当前价格和财务数据
            # 根据数据深度级别设置不同的分析模块数量，而非历史数据范围
            # 🔧 修正映射关系：analysis_modules 应该与 data_depth 保持一致
            if data_depth == "basic":  # 快速分析：基础模块
                analysis_modules = "basic"
                logger.info("📊 [基本面策略] 快速分析模式：获取基础财务指标")
            elif data_depth == "standard":  # 基础/标准分析：标准模块
                analysis_modules = "standard"
                logger.info("📊 [基本面策略] 标准分析模式：获取标准财务分析")
            elif data_depth == "full":  # 深度分析：完整模块
                analysis_modules = "full"
                logger.info("📊 [基本面策略] 深度分析模式：获取完整基本面分析")
            elif data_depth == "comprehensive":  # 全面分析：综合模块
                analysis_modules = "comprehensive"
                logger.info("📊 [基本面策略] 全面分析模式：获取综合基本面分析")
            else:
                analysis_modules = "standard"  # 默认标准分析
                logger.info("📊 [基本面策略] 默认模式：获取标准基本面分析")

            # 基本面分析策略：
            # 1. 获取10天数据（保证能拿到数据，处理周末/节假日）
            # 2. 只使用最近2天数据参与分析（仅需当前价格）
            days_to_fetch = 10  # 固定获取10天数据
            days_to_analyze = 2  # 只分析最近2天

            logger.info(f"📅 [基本面策略] 获取{days_to_fetch}天数据，分析最近{days_to_analyze}天")

            if not start_date:
                start_date = (datetime.now() - timedelta(days=days_to_fetch)).strftime("%Y-%m-%d")

            if not end_date:
                end_date = curr_date

            result_data = []

            if is_china:
                # 中国A股：基本面分析优化策略 - 只获取必要的当前价格和基本面数据
                logger.info(f"🇨🇳 [统一基本面工具] 处理A股数据，数据深度: {data_depth}...")
                logger.info(f"🔍 [股票代码追踪] 进入A股处理分支，ticker: '{ticker}'")
                logger.info("💡 [优化策略] 基本面分析只获取当前价格和财务数据，不获取历史日线数据")

                # 优化策略：基本面分析不需要大量历史日线数据
                # 只获取当前股价信息（最近1-2天即可）和基本面财务数据
                try:
                    # 获取最新股价信息（只需要最近1-2天的数据）
                    from datetime import datetime, timedelta

                    recent_end_date = curr_date
                    recent_start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=2)).strftime(
                        "%Y-%m-%d",
                    )

                    from tradingagents.dataflows.interface import get_china_stock_data_unified

                    logger.info(
                        f"🔍 [股票代码追踪] 调用 get_china_stock_data_unified（仅获取最新价格），传入参数: ticker='{ticker}', start_date='{recent_start_date}', end_date='{recent_end_date}'",
                    )
                    current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)

                    # 🔍 调试：打印返回数据的前500字符
                    logger.info(f"🔍 [基本面工具调试] A股价格数据返回长度: {len(current_price_data)}")
                    logger.info(f"🔍 [基本面工具调试] A股价格数据前500字符:\n{current_price_data[:500]}")

                    result_data.append(f"## A股当前价格信息\n{current_price_data}")
                except Exception as e:
                    logger.error(f"❌ [基本面工具调试] A股价格数据获取失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## A股当前价格信息\n获取失败: {e}")
                    current_price_data = ""

                try:
                    # 获取基本面财务数据（这是基本面分析的核心）
                    from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

                    analyzer = OptimizedChinaDataProvider()
                    logger.info(
                        f"🔍 [股票代码追踪] 调用 OptimizedChinaDataProvider._generate_fundamentals_report，传入参数: ticker='{ticker}', analysis_modules='{analysis_modules}'",
                    )

                    # 传递分析模块参数到基本面分析方法
                    fundamentals_data = analyzer._generate_fundamentals_report(
                        ticker, current_price_data, analysis_modules,
                    )

                    # 🔍 调试：打印返回数据的前500字符
                    logger.info(f"🔍 [基本面工具调试] A股基本面数据返回长度: {len(fundamentals_data)}")
                    logger.info(f"🔍 [基本面工具调试] A股基本面数据前500字符:\n{fundamentals_data[:500]}")

                    result_data.append(f"## A股基本面财务数据\n{fundamentals_data}")
                except Exception as e:
                    logger.error(f"❌ [基本面工具调试] A股基本面数据获取失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## A股基本面财务数据\n获取失败: {e}")

            elif is_hk:
                # 港股：使用AKShare数据源，支持多重备用方案
                logger.info(f"🇭🇰 [统一基本面工具] 处理港股数据，数据深度: {data_depth}...")

                hk_data_success = False

                # 🔥 统一策略：所有级别都获取完整数据
                # 原因：提示词是统一的，如果数据不完整会导致LLM基于不存在的数据进行分析（幻觉）
                logger.info("🔍 [港股基本面] 统一策略：获取完整数据（忽略 data_depth 参数）")

                # 主要数据源：AKShare
                try:
                    from tradingagents.dataflows.interface import get_hk_stock_data_unified

                    hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 调试：打印返回数据的前500字符
                    logger.info(f"🔍 [基本面工具调试] 港股数据返回长度: {len(hk_data)}")
                    logger.info(f"🔍 [基本面工具调试] 港股数据前500字符:\n{hk_data[:500]}")

                    # 检查数据质量
                    if hk_data and len(hk_data) > 100 and "❌" not in hk_data:
                        result_data.append(f"## 港股数据\n{hk_data}")
                        hk_data_success = True
                        logger.info("✅ [统一基本面工具] 港股主要数据源成功")
                    else:
                        logger.warning("⚠️ [统一基本面工具] 港股主要数据源质量不佳")

                except Exception as e:
                    logger.error(f"❌ [基本面工具调试] 港股数据获取失败: {e}")

                # 备用方案：基础港股信息
                if not hk_data_success:
                    try:
                        from tradingagents.dataflows.interface import get_hk_stock_info_unified

                        hk_info = get_hk_stock_info_unified(ticker)

                        basic_info = f"""## 港股基础信息

**股票代码**: {ticker}
**股票名称**: {hk_info.get("name", f"港股{ticker}")}
**交易货币**: 港币 (HK$)
**交易所**: 香港交易所 (HKG)
**数据源**: {hk_info.get("source", "基础信息")}

⚠️ 注意：详细的价格和财务数据暂时无法获取，建议稍后重试或使用其他数据源。

**基本面分析建议**：
- 建议查看公司最新财报
- 关注港股市场整体走势
- 考虑汇率因素对投资的影响
"""
                        result_data.append(basic_info)
                        logger.info("✅ [统一基本面工具] 港股备用信息成功")

                    except Exception as e2:
                        # 最终备用方案
                        fallback_info = f"""## 港股信息（备用）

**股票代码**: {ticker}
**股票类型**: 港股
**交易货币**: 港币 (HK$)
**交易所**: 香港交易所 (HKG)

❌ 数据获取遇到问题: {e2!s}

**建议**：
- 请稍后重试
- 或使用其他数据源
- 检查股票代码格式是否正确
"""
                        result_data.append(fallback_info)
                        logger.error(f"❌ [统一基本面工具] 港股所有数据源都失败: {e2}")

            else:
                # 美股：使用OpenAI/Finnhub数据源
                logger.info("🇺🇸 [统一基本面工具] 处理美股数据...")

                # 🔥 统一策略：所有级别都获取完整数据
                # 原因：提示词是统一的，如果数据不完整会导致LLM基于不存在的数据进行分析（幻觉）
                logger.info("🔍 [美股基本面] 统一策略：获取完整数据（忽略 data_depth 参数）")

                try:
                    from tradingagents.dataflows.interface import get_fundamentals_openai

                    us_data = get_fundamentals_openai(ticker, curr_date)
                    result_data.append(f"## 美股基本面数据\n{us_data}")
                    logger.info("✅ [统一基本面工具] 美股数据获取成功")
                except Exception as e:
                    result_data.append(f"## 美股基本面数据\n获取失败: {e}")
                    logger.error(f"❌ [统一基本面工具] 美股数据获取失败: {e}")

            # 组合所有数据
            combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info["market_name"]}
**货币**: {market_info["currency_name"]} ({market_info["currency_symbol"]})
**分析日期**: {curr_date}
**数据深度级别**: {data_depth}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

            # 添加详细的数据获取日志
            logger.info("📊 [统一基本面工具] ===== 数据获取完成摘要 =====")
            logger.info(f"📊 [统一基本面工具] 股票代码: {ticker}")
            logger.info(f"📊 [统一基本面工具] 股票类型: {market_info['market_name']}")
            logger.info(f"📊 [统一基本面工具] 数据深度级别: {data_depth}")
            logger.info(f"📊 [统一基本面工具] 获取的数据模块数量: {len(result_data)}")
            logger.info(f"📊 [统一基本面工具] 总数据长度: {len(combined_result)} 字符")

            # 记录每个数据模块的详细信息
            for i, data_section in enumerate(result_data, 1):
                section_lines = data_section.split("\n")
                section_title = section_lines[0] if section_lines else "未知模块"
                section_length = len(data_section)
                logger.info(f"📊 [统一基本面工具] 数据模块 {i}: {section_title} ({section_length} 字符)")

                # 如果数据包含错误信息，特别标记
                if "获取失败" in data_section or "❌" in data_section:
                    logger.warning(f"⚠️ [统一基本面工具] 数据模块 {i} 包含错误信息")
                else:
                    logger.info(f"✅ [统一基本面工具] 数据模块 {i} 获取成功")

            # 根据数据深度级别记录具体的获取策略
            if data_depth in ["basic", "standard"]:
                logger.info("📊 [统一基本面工具] 基础/标准级别策略: 仅获取核心价格数据和基础信息")
            elif data_depth in ["full", "detailed", "comprehensive"]:
                logger.info("📊 [统一基本面工具] 完整/详细/全面级别策略: 获取价格数据 + 基本面数据")
            else:
                logger.info("📊 [统一基本面工具] 默认策略: 获取完整数据")

            logger.info("📊 [统一基本面工具] ===== 数据获取摘要结束 =====")

            return combined_result

        except Exception as e:
            error_msg = f"统一基本面分析工具执行失败: {e!s}"
            logger.error(f"❌ [统一基本面工具] {error_msg}")
            _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_market_data_unified", log_args=True)
    @toolkit_register("market")
    def get_stock_market_data_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        start_date: Annotated[
            str,
            "开始日期，格式：YYYY-MM-DD。可省略，系统会自动填充当天日期并扩展回溯天数（通常为365天）",
        ] = "",
        end_date: Annotated[
            str,
            "结束日期，格式：YYYY-MM-DD。可省略，系统会自动填充当天日期",
        ] = "",
    ) -> str:
        """
        统一的股票市场数据工具
        自动识别股票类型（A股、港股、美股）并调用相应的数据源获取价格和技术指标数据

        ⚠️ 重要：系统会自动扩展日期范围到配置的回溯天数（通常为365天），以确保技术指标计算有足够的历史数据。
        你只需要传递当前分析日期作为 start_date 和 end_date 即可，无需手动计算历史日期范围。

        Args:
            ticker: 股票代码（如：000001、0700.HK、AAPL）
            start_date: 开始日期（格式：YYYY-MM-DD）。传递当前分析日期即可，系统会自动扩展
            end_date: 结束日期（格式：YYYY-MM-DD）。传递当前分析日期即可

        Returns:
            str: 市场数据和技术分析报告

        示例：
            如果分析日期是 2025-11-09，传递：
            - ticker: "00700.HK"
            - start_date: "2025-11-09"
            - end_date: "2025-11-09"
            系统会自动获取 2024-11-09 到 2025-11-09 的365天历史数据
        """
        logger.info(f"📈 [统一市场工具] 分析股票: {ticker}")

        try:
            from datetime import datetime

            from tradingagents.utils.stock_utils import StockUtils

            # 自动填充日期（兼容 LLM 不传日期参数的情况）
            today_str = datetime.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = today_str
            if not end_date:
                end_date = today_str

            # 自动识别股票类型
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info["is_china"]
            is_hk = market_info["is_hk"]
            is_us = market_info["is_us"]

            logger.info(f"📈 [统一市场工具] 股票类型: {market_info['market_name']}")
            logger.info(f"📈 [统一市场工具] 货币: {market_info['currency_name']} ({market_info['currency_symbol']}")

            result_data = []

            if is_china:
                # 中国A股：使用中国股票数据源
                logger.info("🇨🇳 [统一市场工具] 处理A股市场数据...")

                try:
                    from tradingagents.dataflows.interface import get_china_stock_data_unified

                    stock_data = get_china_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 调试：打印返回数据的前500字符
                    logger.info(f"🔍 [市场工具调试] A股数据返回长度: {len(stock_data)}")
                    logger.info(f"🔍 [市场工具调试] A股数据前500字符:\n{stock_data[:500]}")

                    result_data.append(f"## A股市场数据\n{stock_data}")
                except Exception as e:
                    logger.error(f"❌ [市场工具调试] A股数据获取失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## A股市场数据\n获取失败: {e}")

            elif is_hk:
                # 港股：使用AKShare数据源
                logger.info("🇭🇰 [统一市场工具] 处理港股市场数据...")

                try:
                    from tradingagents.dataflows.interface import get_hk_stock_data_unified

                    hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 调试：打印返回数据的前500字符
                    logger.info(f"🔍 [市场工具调试] 港股数据返回长度: {len(hk_data)}")
                    logger.info(f"🔍 [市场工具调试] 港股数据前500字符:\n{hk_data[:500]}")

                    result_data.append(f"## 港股市场数据\n{hk_data}")
                except Exception as e:
                    logger.error(f"❌ [市场工具调试] 港股数据获取失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## 港股市场数据\n获取失败: {e}")

            else:
                # 美股：优先使用FINNHUB API数据源
                logger.info("🇺🇸 [统一市场工具] 处理美股市场数据...")

                result_data.append(f"## 美股市场数据\n美股数据源已移除，仅支持 A 股 Tushare 数据")

            # 组合所有数据
            combined_result = f"""# {ticker} 市场数据分析

**股票类型**: {market_info["market_name"]}
**货币**: {market_info["currency_name"]} ({market_info["currency_symbol"]})
**分析期间**: {start_date} 至 {end_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

            logger.info(f"📈 [统一市场工具] 数据获取完成，总长度: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"统一市场数据工具执行失败: {e!s}"
            logger.error(f"❌ [统一市场工具] {error_msg}")
            _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_news_unified", log_args=True)
    @toolkit_register("news")
    def get_stock_news_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        统一的股票新闻工具
        自动识别股票类型（A股、港股、美股）并调用相应的新闻数据源

        Args:
            ticker: 股票代码（如：000001、0700.HK、AAPL）
            curr_date: 当前日期（格式：YYYY-MM-DD）

        Returns:
            str: 新闻分析报告
        """
        logger.info(f"📰 [统一新闻工具] 分析股票: {ticker}")

        try:
            from datetime import datetime, timedelta

            from tradingagents.utils.stock_utils import StockUtils

            # 自动识别股票类型
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info["is_china"]
            is_hk = market_info["is_hk"]
            is_us = market_info["is_us"]

            logger.info(f"📰 [统一新闻工具] 股票类型: {market_info['market_name']}")

            # 计算新闻查询的日期范围
            end_date = datetime.strptime(curr_date, "%Y-%m-%d")
            start_date = end_date - timedelta(days=7)
            start_date_str = start_date.strftime("%Y-%m-%d")

            result_data = []

            if is_china or is_hk:
                # 中国A股和港股：使用AKShare东方财富新闻和Google新闻（中文搜索）
                logger.info("🇨🇳🇭🇰 [统一新闻工具] 处理中文新闻...")

                # 1. 尝试获取AKShare东方财富新闻
                try:
                    # 处理股票代码
                    clean_ticker = (
                        ticker.replace(".SH", "")
                        .replace(".SZ", "")
                        .replace(".SS", "")
                        .replace(".HK", "")
                        .replace(".XSHE", "")
                        .replace(".XSHG", "")
                    )

                    logger.info(f"🇨🇳🇭🇰 [统一新闻工具] 尝试获取东方财富新闻: {clean_ticker}")

                    # 通过 AKShare Provider 获取新闻
                    # AKShare 数据源已移除，跳过东方财富新闻获取
                    news_df = None

                    if news_df is not None and not news_df.empty:
                        # 格式化东方财富新闻
                        em_news_items = []
                        for _, row in news_df.iterrows():
                            # AKShare 返回的字段名
                            news_title = row.get("新闻标题", "") or row.get("标题", "")
                            news_time = row.get("发布时间", "") or row.get("时间", "")
                            news_url = row.get("新闻链接", "") or row.get("链接", "")

                            news_item = f"- **{news_title}** [{news_time}]({news_url})"
                            em_news_items.append(news_item)

                        # 添加到结果中
                        if em_news_items:
                            em_news_text = "\n".join(em_news_items)
                            result_data.append(f"## 东方财富新闻\n{em_news_text}")
                            logger.info(f"🇨🇳🇭🇰 [统一新闻工具] 成功获取{len(em_news_items)}条东方财富新闻")
                except Exception as em_e:
                    logger.error(f"❌ [统一新闻工具] 东方财富新闻获取失败: {em_e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## 东方财富新闻\n获取失败: {em_e}")

                # 2. 通过news_source_manager获取补充新闻
                try:
                    from tradingagents.dataflows.news.news_source_manager import get_news_report
                    extra_report = get_news_report(ticker, max_news=5)
                    if extra_report:
                        result_data.append(f"## 实时财经新闻\n{extra_report}")
                except Exception as e:
                    logger.error(f"❌ [统一新闻工具] 实时新闻获取失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障

            else:
                # 美股：通过news_source_manager获取新闻
                logger.info("🇺🇸 [统一新闻工具] 处理美股新闻...")

                try:
                    from tradingagents.dataflows.news.news_source_manager import get_news_report
                    news_data = get_news_report(ticker, max_news=10)
                    if news_data:
                        result_data.append(f"## 美股新闻\n{news_data}")
                except Exception as e:
                    result_data.append(f"## 美股新闻\n获取失败: {e}")

            # 组合所有数据
            combined_result = f"""# {ticker} 新闻分析

**股票类型**: {market_info["market_name"]}
**分析日期**: {curr_date}
**新闻时间范围**: {start_date_str} 至 {curr_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的新闻源*
"""

            logger.info(f"📰 [统一新闻工具] 数据获取完成，总长度: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"统一新闻工具执行失败: {e!s}"
            logger.error(f"❌ [统一新闻工具] {error_msg}")
            _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_sentiment_unified", log_args=True)
    @toolkit_register("social")
    def get_stock_sentiment_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        统一的股票情绪分析工具
        自动识别股票类型（A股、港股、美股）并调用相应的情绪数据源

        数据源策略：
        - A股：东方财富股吧（主源） + 雪球情绪分析（备源）
        - 港股：东方财富股吧（主源，港股代码） + 雪球
        - 美股：暂不可用，推荐新闻分析

        Args:
            ticker: 股票代码（如：000001、0700.HK、AAPL）
            curr_date: 当前日期（格式：YYYY-MM-DD）

        Returns:
            str: 情绪分析报告
        """
        logger.info(f"😊 [统一情绪工具] 分析股票: {ticker}")

        try:
            from tradingagents.utils.stock_utils import StockUtils

            # 自动识别股票类型
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info["is_china"]
            is_hk = market_info["is_hk"]
            is_us = market_info["is_us"]

            logger.info(f"😊 [统一情绪工具] 股票类型: {market_info['market_name']}")

            result_data = []

            if is_china or is_hk:
                # 中国A股和港股：使用东方财富股吧 + 雪球情绪分析
                logger.info("🇨🇳🇭🇰 [统一情绪工具] 处理中文市场情绪...")

                # ── 源1: 东方财富股吧 ──
                try:
                    from tradingagents.dataflows.news.providers.eastmoney_guba_provider import (
                        fetch_guba_sentiment,
                        format_sentiment_report,
                    )

                    guba_sentiment = fetch_guba_sentiment(ticker, pages=2, max_posts=40)
                    if guba_sentiment and guba_sentiment.get("total_posts", 0) > 0:
                        guba_report = format_sentiment_report(guba_sentiment)
                        result_data.append(guba_report)
                        logger.info(
                            f"😊 [统一情绪工具] ✅ 东方财富股吧数据: "
                            f"{guba_sentiment['total_posts']} 条帖子, "
                            f"情绪分 {guba_sentiment['sentiment_score']}"
                        )
                    else:
                        logger.info("[统一情绪工具] ⚠️ 东方财富股吧无数据")
                        result_data.append(
                            "## 东方财富股吧情绪\n"
                            "当前未获取到股吧讨论数据。可能原因：\n"
                            "1. 该股票在股吧讨论较少\n"
                            "2. 反爬虫限制导致数据获取失败\n"
                            "3. 股票代码格式不正确\n"
                        )
                except ImportError as e:
                    logger.warning(f"[统一情绪工具] ⚠️ 东方财富股吧模块导入失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append("## 东方财富股吧情绪\n模块未安装，跳过股吧数据源。\n")
                except Exception as e:
                    logger.warning(f"[统一情绪工具] ⚠️ 东方财富股吧请求失败: {e}")
                    _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
                    result_data.append(f"## 东方财富股吧情绪\n数据获取异常: {e}\n")

                # ── 源2: 雪球情绪（备源） ──
                try:
                    from tradingagents.dataflows.news.providers.xueqiu_provider import fetch_news as fetch_xueqiu_news

                    xueqiu_news = fetch_xueqiu_news(ticker, page_size=5)
                    if xueqiu_news:
                        xueqiu_summary = "## 雪球社区讨论\n\n"
                        for item in xueqiu_news[:5]:
                            title = item.get("title", "无标题")
                            content = item.get("content", "")[:100]
                            pub_time = item.get("publish_time", "")
                            xueqiu_summary += f"- **{title}**\n"
                            if content:
                                xueqiu_summary += f"  {content}...\n"
                            if pub_time:
                                xueqiu_summary += f"  🕐 {pub_time}\n"
                            xueqiu_summary += "\n"
                        result_data.append(xueqiu_summary)
                        logger.info(f"😊 [统一情绪工具] ✅ 雪球数据: {len(xueqiu_news)} 条")
                except ImportError:
                    logger.debug("[统一情绪工具] 雪球模块未导入，跳过")
                except Exception as e:
                    logger.debug(f"[统一情绪工具] 雪球请求失败: {e}")

            else:
                # 美股：暂不可用
                logger.info("🇺🇸 [统一情绪工具] 处理美股情绪...")
                result_data.append(
                    "## 美股情绪分析\n"
                    "美股社交媒体情绪数据源暂不可用。\n\n"
                    "推荐替代方案：\n"
                    "1. 使用新闻分析工具分析相关财经新闻\n"
                    "2. 关注公司财报和市场研报\n"
                    "3. 使用技术分析工具评估市场情绪\n"
                )

            # 组合所有数据
            combined_result = f"""# {ticker} 情绪分析

**股票类型**: {market_info["market_name"]}
**分析日期**: {curr_date}

{chr(10).join(result_data)}

---
*数据来源: 东方财富股吧（A股/港股主源）+ 雪球社区（备源）*
"""

            logger.info(f"😊 [统一情绪工具] 数据获取完成，总长度: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"统一情绪分析工具执行失败: {e!s}"
            logger.error(f"❌ [统一情绪工具] {error_msg}")
            _data_fetch_failed.set(True)  # [PR #2] 标记数据源故障
            return error_msg
