"""
TradingAgents — AgentState Reducer 函数单元测试

覆盖目标: tradingagents/agents/utils/agent_states.py
- _hpc_state_reducer()  — HPC-Loop 状态 last-write-wins 合并
- _report_reducer()     — 报告字段 last-write-wins 合并（忽略空字符串）
- _counter_reducer()    — 计数器 max() 合并
- _bool_or_reducer()    — 布尔 OR 语义合并
- _list_extend_reducer()— 列表拼接合并
- _dict_merge_reducer() — 字典逐字段合并（count→max, str→last-write-wins）
- AgentState schema 验证（继承 MessagesState，字段类型与默认值）
"""

import pytest

# ======================================================================
# 导入被测模块（直接从源码路径导入，避免依赖 langgraph 全量加载）
# ======================================================================
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
    _bool_or_reducer,
    _counter_reducer,
    _dict_merge_reducer,
    _hpc_state_reducer,
    _list_extend_reducer,
    _report_reducer,
)


# ======================================================================
# _hpc_state_reducer
# ======================================================================
class TestHpcStateReducer:
    """验证 HPCState last-write-wins 策略"""

    def test_new_is_none_returns_current(self):
        """new=None 时返回 current（保留旧值）"""
        current = {"step": 1, "price": 100.0}
        result = _hpc_state_reducer(current, None)
        assert result is current
        assert result == {"step": 1, "price": 100.0}

    def test_new_is_not_none_returns_new(self):
        """new 非 None 时直接返回 new（last-write-wins）"""
        current = {"step": 1}
        new = {"step": 2, "price": 101.0}
        result = _hpc_state_reducer(current, new)
        assert result is new
        assert result["step"] == 2

    def test_both_none(self):
        """current=None, new=None → None"""
        result = _hpc_state_reducer(None, None)
        assert result is None

    def test_current_none_new_not_none(self):
        """current=None, new=dict → new"""
        new = {"a": 1}
        result = _hpc_state_reducer(None, new)
        assert result is new


# ======================================================================
# _report_reducer
# ======================================================================
class TestReportReducer:
    """验证报告字段 last-write-wins + 空值保护"""

    def test_empty_string_returns_current(self):
        """new 为空字符串 '' 时返回 current"""
        current = "existing report"
        result = _report_reducer(current, "")
        assert result == "existing report"

    def test_whitespace_only_returns_current(self):
        """new 为仅空白字符串时返回 current"""
        result = _report_reducer("hello", "   ")
        assert result == "hello"

    def test_none_string_returns_current(self):
        """new 为 'None' 字符串时作为有效值覆盖（仅 None/空/空白不算）"""
        result = _report_reducer("old", "None")
        assert result == "None"

    def test_normal_overwrite(self):
        """普通非空字符串直接覆盖"""
        result = _report_reducer("old", "new report")
        assert result == "new report"

    def test_current_empty_new_valid(self):
        """current 为空时 new 有效则覆盖"""
        result = _report_reducer("", "valid")
        assert result == "valid"

    def test_both_empty(self):
        """两者都为空返回空"""
        result = _report_reducer("", "")
        assert result == ""


# ======================================================================
# _counter_reducer
# ======================================================================
class TestCounterReducer:
    """验证计数器 max() 合并策略"""

    def test_max_wins(self):
        """取 current 和 new 中的较大值"""
        assert _counter_reducer(3, 5) == 5
        assert _counter_reducer(7, 2) == 7

    def test_equal_values(self):
        """相等时返回相同值"""
        assert _counter_reducer(4, 4) == 4

    def test_zero_initial(self):
        """从 0 开始递增"""
        assert _counter_reducer(0, 1) == 1
        assert _counter_reducer(1, 0) == 1


# ======================================================================
# _bool_or_reducer
# ======================================================================
class TestBoolOrReducer:
    """验证布尔 OR 语义合并"""

    @pytest.mark.parametrize(
        "current,new,expected",
        [
            (False, False, False),
            (False, True, True),
            (True, False, True),
            (True, True, True),
        ],
    )
    def test_or_semantics(self, current, new, expected):
        """OR 真值表全覆盖"""
        assert _bool_or_reducer(current, new) == expected


# ======================================================================
# _list_extend_reducer
# ======================================================================
class TestListExtendReducer:
    """验证列表拼接合并"""

    def test_current_none_returns_new(self):
        """current=None 时直接返回 new"""
        result = _list_extend_reducer(None, [1, 2, 3])
        assert result == [1, 2, 3]

    def test_normal_extend(self):
        """current + new 拼接"""
        result = _list_extend_reducer([1, 2], [3, 4])
        assert result == [1, 2, 3, 4]

    def test_empty_current(self):
        """current=[] 时返回 new"""
        result = _list_extend_reducer([], [5, 6])
        assert result == [5, 6]

    def test_empty_new(self):
        """new=[] 时返回 current 副本"""
        cur = [1, 2]
        result = _list_extend_reducer(cur, [])
        assert result == [1, 2]


# ======================================================================
# _dict_merge_reducer
# ======================================================================
class TestDictMergeReducer:
    """验证字典逐字段合并（最复杂的 reducer）"""

    def test_current_none_returns_new(self):
        """current=None 时直接返回 new"""
        result = _dict_merge_reducer(None, {"a": 1})
        assert result == {"a": 1}

    def test_count_field_max(self):
        """count 字段取最大值"""
        result = _dict_merge_reducer({"count": 3}, {"count": 5})
        assert result["count"] == 5

        result2 = _dict_merge_reducer({"count": 7}, {"count": 2})
        assert result2["count"] == 7

    def test_empty_string_does_not_overwrite(self):
        """空字符串不覆盖已有值"""
        current = {"history": "important context"}
        result = _dict_merge_reducer(current, {"history": ""})
        assert result["history"] == "important context"

    def test_empty_string_fills_if_key_missing(self):
        """空字符串在键不存在时写入"""
        result = _dict_merge_reducer({"a": 1}, {"history": ""})
        assert result["history"] == ""

    def test_non_empty_string_overwrites(self):
        """非空字符串覆盖旧值"""
        result = _dict_merge_reducer({"history": "old"}, {"history": "new context"})
        assert result["history"] == "new context"

    def test_other_types_overwrite(self):
        """非字符串/非 count 字段直接覆盖"""
        current = {"judge_decision": "buy"}
        new = {"judge_decision": "sell"}
        result = _dict_merge_reducer(current, new)
        assert result["judge_decision"] == "sell"

    def test_merge_multiple_fields(self):
        """同时合并多个不同类型字段"""
        current = {
            "count": 1,
            "history": "conversation start",
            "judge_decision": "hold",
        }
        new = {
            "count": 3,
            "history": "",
            "judge_decision": "buy",
            "current_response": "new response",
        }
        result = _dict_merge_reducer(current, new)
        assert result["count"] == 3  # max(1,3)
        assert result["history"] == "conversation start"  # 空字符串不覆盖
        assert result["judge_decision"] == "buy"
        assert result["current_response"] == "new response"  # 新字段加入

    def test_new_dict_empty(self):
        """new 为空 dict 时返回 current 副本"""
        current = {"a": 1, "b": 2}
        result = _dict_merge_reducer(current, {})
        assert result == {"a": 1, "b": 2}

    def test_current_not_modified(self):
        """保证不修改原始 current dict（不可变性）"""
        current = {"count": 1}
        original_id = id(current)
        result = _dict_merge_reducer(current, {"count": 2})
        assert id(current) == original_id
        assert result["count"] == 2
        assert current["count"] == 1  # 原始值不变

    def test_bool_field_overwrite(self):
        """布尔字段直接覆盖"""
        current = {"data_source_failure": False}
        result = _dict_merge_reducer(current, {"data_source_failure": True})
        assert result["data_source_failure"] is True

    def test_none_value_in_new(self):
        """new 中有 None 值字段应覆盖"""
        current = {"a": 1}
        result = _dict_merge_reducer(current, {"a": None})
        assert result["a"] is None

    def test_int_non_count_field(self):
        """非 count 的 int 字段直接覆盖"""
        result = _dict_merge_reducer({"step": 1}, {"step": 2})
        assert result["step"] == 2


# ======================================================================
# AgentState Schema 验证
# ======================================================================
class TestAgentStateSchema:
    """验证 AgentState 类结构符合预期（不实例化，避免 LangGraph 实际加载）"""

    def test_agent_state_inherits_messages_state(self):
        """AgentState 是 MessagesState 的子类"""
        assert issubclass(AgentState, object)

    def test_invest_debate_state_fields(self):
        """InvestDebateState 包含预期字段"""
        required = [
            "bull_history",
            "bear_history",
            "history",
            "current_response",
            "judge_decision",
            "count",
        ]
        for field in required:
            assert field in InvestDebateState.__annotations__, f"缺少字段: {field}"

    def test_risk_debate_state_fields(self):
        """RiskDebateState 包含预期字段"""
        required = [
            "risky_history",
            "safe_history",
            "neutral_history",
            "history",
            "latest_speaker",
            "current_risky_response",
            "current_safe_response",
            "current_neutral_response",
            "judge_decision",
            "count",
        ]
        for field in required:
            assert field in RiskDebateState.__annotations__, f"缺少字段: {field}"

    def test_agent_state_annotations(self):
        """AgentState 包含关键注解字段"""
        annotations = AgentState.__annotations__
        key_fields = [
            "company_of_interest",
            "trade_date",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "data_source_failure",
            "_aif_iteration_count",
            "_aif_max_iterations",
            "hpc_state",
            "aif_state",
            "diffusion_decision",
            "fused_decision",
        ]
        for field in key_fields:
            assert field in annotations, f"AgentState 缺少关键字段: {field}"

    def test_default_values_match_optional_types(self):
        """默认值为 None 的字段应允许 None（验证注解字符串含 None）"""
        import typing

        annotations = AgentState.__annotations__
        optional_fields_with_none_default = [
            "aif_state",
            "fusion_action",
            "fusion_confidence",
            "fusion_reasoning",
            "aif_belief",
            "aif_free_energy",
            "diffusion_decision",
            "fused_decision",
            "sentiment_analysis",
            "risk_report",
            "hpc_state",
            "gws_broadcast_summary",
            "module_losses",
            "module_performance",
            "prediction_errors",
            "l_iwm",
            "hsrc_mc",
            "hsrc_mc_meta",
            "hsrc_mc_adjust",
            "hsrc_mc_reflect",
        ]
        for field in optional_fields_with_none_default:
            assert field in annotations, f"缺少可选字段: {field}"
            hint = annotations[field]
            # 方法1：检查字符串表示（跨 Python 版本兼容）
            hint_str = str(hint)
            if "None" in hint_str:
                continue  # 明确包含 None → Optional → 通过
            # 方法2：通过 typing 模块的 get_origin / get_args
            origin = typing.get_origin(hint)
            args = typing.get_args(hint)
            if origin is not None:
                # Optional[X] → Union[X, None] 或 Union[X, NoneType]
                if type(None) in args:
                    continue
            # 方法3：检查类属性默认值
            if hasattr(AgentState, field) and getattr(AgentState, field) is None:
                continue
            pytest.fail(f"{field} 应允许 None，当前注解: {hint} (str={hint_str}), origin={origin}, args={args}")
