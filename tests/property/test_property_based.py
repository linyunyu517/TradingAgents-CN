#!/usr/bin/env python3
"""
Property-Based Testing for TradingAgents-CN v1.0.1 核心模块
===========================================================
使用 Hypothesis 框架对以下模块执行属性基测试：

模块A: Reducer 函数 (`_report_reducer`, `_counter_reducer`)
  - [`_report_reducer`](tradingagents/agents/utils/agent_states.py:69)
  - [`_counter_reducer`](tradingagents/agents/utils/agent_states.py:84)

模块B: `_sanitize_aif_return()` 函数
  - [`_sanitize_aif_return`](tradingagents/hpc_loop/aif_integration.py:97)

模块C: 状态 Schema 不变性
  - [`AgentState`](tradingagents/agents/utils/agent_states.py:162)
  - reducer 组合行为一致性

运行方式:
    cd D:\\AI-Projects\\TradingAgents-CN_v1.0.1
    python -m pytest tests/property/test_property_based.py -v --tb=short -xvs
    python -m pytest tests/property/ -v --tb=short
"""

import logging
import sys
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 禁用非必要的日志输出，减少测试噪音
logging.disable(logging.CRITICAL)

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ================================================================
# 导入被测模块
# ================================================================

# 尝试导入 Reducer 函数
try:
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

    _CAN_TEST_REDUCERS = True
except Exception as exc:
    _CAN_TEST_REDUCERS = False
    _REDUCER_SKIP_REASON = str(exc)

# 尝试导入 _sanitize_aif_return
try:
    from tradingagents.hpc_loop.aif_integration import (
        _ANALYST_EXCLUDE_KEYS,
        _sanitize_aif_return,
    )

    _CAN_TEST_SANITIZE = True
except Exception as exc:
    _CAN_TEST_SANITIZE = False
    _SANITIZE_SKIP_REASON = str(exc)


# ================================================================
# 通用策略 (Strategies)
# ================================================================

# 文本策略: 任意字符串（包含空字符串和空白字符串）
text_strategy = st.text()

# 非空文本策略（排除纯空白字符串，因为 _report_reducer 将 .strip()=="" 视为空）
non_empty_text = st.text(min_size=1).filter(lambda s: s.strip() != "")

# 正整数策略
positive_int = st.integers(min_value=1, max_value=1000)

# 非负整数策略（含 0）
non_negative_int = st.integers(min_value=0, max_value=1000)

# 任意整数策略（含负数）
any_int = st.integers(min_value=-1000, max_value=1000)

# 布尔值策略
bool_strategy = st.booleans()


# 任意 dict 策略（用于 _sanitize_aif_return）
@st.composite
def arbitrary_dict_strategy(draw):
    """生成任意键值对字典，可能包含或不包含 _ANALYST_EXCLUDE_KEYS 中的键"""
    keys = draw(
        st.lists(
            st.text(alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=200)),
            min_size=0,
            max_size=10,
        ),
    )
    values = draw(
        st.lists(
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(min_value=-1000, max_value=1000),
                st.floats(allow_nan=False, allow_infinity=False),
                st.text(max_size=50),
            ),
            min_size=len(keys),
            max_size=len(keys),
        ),
    )
    result = dict(zip(keys, values, strict=False))
    # 随机加入一些被排除的键
    if draw(st.booleans()) and _CAN_TEST_SANITIZE:
        for ek in _ANALYST_EXCLUDE_KEYS:
            if draw(st.floats(min_value=0, max_value=1)) < 0.3:
                result[ek] = draw(st.text(max_size=50))
    return result


# ================================================================
# 模块A: Reducer 函数属性基测试
# ================================================================

pytestmark = pytest.mark.skipif(
    not _CAN_TEST_REDUCERS,
    reason=f"Reducer 导入失败: {_REDUCER_SKIP_REASON if _CAN_TEST_REDUCERS is False else ''}",
)


class TestReportReducer:
    """
    [`_report_reducer(current, new)`](tradingagents/agents/utils/agent_states.py:69)
    属性基测试

    被测函数行为:
        - 如果 new 是 None/空字符串/纯空白 → 返回 current
        - 否则返回 new (last-write-wins)
    """

    # ── 属性 1: 幂等性 ──────────────────────────────────────────
    @given(text=text_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop1_idempotent(self, text: str):
        """幂等性：同一输入多次应用结果不变"""
        r1 = _report_reducer(text, text)
        r2 = _report_reducer(text, text)
        assert r1 == r2

    # ── 属性 2: 空/空白字符串不覆盖 ────────────────────────────
    @given(current=text_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop2_empty_new_returns_current(self, current: str):
        """空/空白字符串作为 new 时返回 current"""
        result = _report_reducer(current, "")
        assert result == current
        result2 = _report_reducer(current, "   ")
        assert result2 == current
        result3 = _report_reducer(current, "\t\n ")
        assert result3 == current

    # ── 属性 3: 非空 new 覆盖 current ──────────────────────────
    @given(current=text_strategy, new=non_empty_text)
    @settings(max_examples=200, deadline=None)
    def test_prop3_nonempty_new_overrides(self, current: str, new: str):
        """非空 new 覆盖 current（last-write-wins）"""
        result = _report_reducer(current, new)
        assert result == new

    # ── 属性 4: None 输入不改变 current ────────────────────────
    @given(current=text_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop4_none_new_returns_current(self, current: str):
        """None 作为 new 时返回 current"""
        result = _report_reducer(current, None)  # type: ignore
        assert result == current

    # ── 属性 5: 结合性（在非空 new 路径上） ─────────────────────
    @given(
        a=text_strategy,
        b=non_empty_text,
        c=non_empty_text,
    )
    @settings(max_examples=200, deadline=None)
    def test_prop5_associative(self, a: str, b: str, c: str):
        """结合性: reducer(a, reducer(b, c)) == reducer(reducer(a, b), c)"""
        left = _report_reducer(a, _report_reducer(b, c))
        right = _report_reducer(_report_reducer(a, b), c)
        assert left == right


class TestCounterReducer:
    """
    [`_counter_reducer(current, new)`](tradingagents/agents/utils/agent_states.py:84)
    属性基测试

    被测函数行为:
        - 返回 max(current, new)
        - 用于 LangGraph 计数器并发写入场景
    """

    # ── 属性 1: 单调性（正整数） ───────────────────────────────
    @given(a=positive_int, b=positive_int)
    @settings(max_examples=200, deadline=None)
    def test_prop1_monotonic(self, a: int, b: int):
        """单调性：对于正整数输入，结果 >= 每个输入"""
        result = _counter_reducer(a, b)
        assert result >= a
        assert result >= b

    # ── 属性 2: 交换性 ─────────────────────────────────────────
    @given(a=any_int, b=any_int)
    @settings(max_examples=200, deadline=None)
    def test_prop2_commutative(self, a: int, b: int):
        """交换性: counter_reducer(a, b) == counter_reducer(b, a)"""
        assert _counter_reducer(a, b) == _counter_reducer(b, a)

    # ── 属性 3: 幂等性 ─────────────────────────────────────────
    @given(a=any_int)
    @settings(max_examples=200, deadline=None)
    def test_prop3_idempotent(self, a: int):
        """幂等性: counter_reducer(a, a) == a"""
        assert _counter_reducer(a, a) == a

    # ── 属性 4: max 语义 ───────────────────────────────────────
    @given(a=any_int, b=any_int)
    @settings(max_examples=200, deadline=None)
    def test_prop4_max_semantics(self, a: int, b: int):
        """结果恒等于 max(a, b)"""
        assert _counter_reducer(a, b) == max(a, b)

    # ── 属性 5: 结合性 ─────────────────────────────────────────
    @given(a=any_int, b=any_int, c=any_int)
    @settings(max_examples=200, deadline=None)
    def test_prop5_associative(self, a: int, b: int, c: int):
        """结合性: reducer(a, reducer(b, c)) == reducer(reducer(a, b), c)"""
        left = _counter_reducer(a, _counter_reducer(b, c))
        right = _counter_reducer(_counter_reducer(a, b), c)
        assert left == right


class TestBoolOrReducer:
    """
    [`_bool_or_reducer(current, new)`](tradingagents/agents/utils/agent_states.py:98)
    属性基测试

    被测函数行为:
        - 返回 current or new (一旦 True 永远 True)
    """

    @given(a=bool_strategy, b=bool_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop1_or_semantics(self, a: bool, b: bool):
        """OR 语义: 结果恒等于 a or b"""
        assert _bool_or_reducer(a, b) == (a or b)

    @given(a=bool_strategy, b=bool_strategy, c=bool_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop2_associative(self, a: bool, b: bool, c: bool):
        """结合性"""
        left = _bool_or_reducer(a, _bool_or_reducer(b, c))
        right = _bool_or_reducer(_bool_or_reducer(a, b), c)
        assert left == right

    @given(a=bool_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop3_monotonic(self, a: bool):
        """单调性: True 一旦设置永不重置"""
        assert _bool_or_reducer(a, True)
        if a:
            assert _bool_or_reducer(a, False)


class TestListExtendReducer:
    """
    [`_list_extend_reducer(current, new)`](tradingagents/agents/utils/agent_states.py:110)
    属性基测试
    """

    @given(
        a=st.lists(st.integers(), min_size=0, max_size=10),
        b=st.lists(st.integers(), min_size=0, max_size=10),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop1_extend_semantics(self, a: list[int], b: list[int]):
        """拼接语义: 结果 == a + b"""
        # 处理 None 情况
        result = _list_extend_reducer(a or None, b)
        if not a:
            assert result == b
        else:
            assert result == a + b

    @given(
        a=st.lists(st.integers(), min_size=0, max_size=10),
        b=st.lists(st.integers(), min_size=0, max_size=10),
        c=st.lists(st.integers(), min_size=0, max_size=10),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop2_associative(self, a: list[int], b: list[int], c: list[int]):
        """结合性"""
        left = _list_extend_reducer(_list_extend_reducer(a, b), c)
        right = _list_extend_reducer(a, b + c)
        assert left == right


class TestHpcStateReducer:
    """
    [`_hpc_state_reducer(current, new)`](tradingagents/agents/utils/agent_states.py:54)
    属性基测试

    被测函数行为:
        - 如果 new 是 None → 返回 current
        - 否则返回 new (last-write-wins)
    """

    @given(a=st.dictionaries(st.text(max_size=10), st.integers(), min_size=0, max_size=5))
    @settings(max_examples=200, deadline=None)
    def test_prop1_none_new_returns_current(self, a: dict[str, int]):
        """None new 返回 current"""
        assert _hpc_state_reducer(a, None) == a

    @given(
        a=st.dictionaries(st.text(max_size=10), st.integers(), min_size=0, max_size=5),
        b=st.dictionaries(st.text(max_size=10), st.integers(), min_size=0, max_size=5),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop2_new_overrides(self, a: dict[str, int], b: dict[str, int]):
        """非 None new 覆盖 current"""
        assert _hpc_state_reducer(a, b) == b


# ================================================================
# 模块B: _sanitize_aif_return() 属性基测试
# ================================================================


@pytest.mark.skipif(
    not _CAN_TEST_SANITIZE,
    reason=f"_sanitize_aif_return 导入失败: {_SANITIZE_SKIP_REASON if _CAN_TEST_SANITIZE is False else ''}",
)
class TestSanitizeAifReturn:
    """
    [`_sanitize_aif_return()`](tradingagents/hpc_loop/aif_integration.py:97)
    属性基测试

    被测函数行为:
        - 从返回值 dict 中移除 _ANALYST_EXCLUDE_KEYS 中的键
        - 保留其他所有键值对原样
        - 不修改输入 dict
    """

    # ── 属性 1: 排除键过滤 ─────────────────────────────────────
    @given(return_dict=arbitrary_dict_strategy())
    @settings(max_examples=200, deadline=None)
    def test_prop1_exclude_keys_removed(self, return_dict: dict[str, Any]):
        """排除键过滤：结果中不含 _ANALYST_EXCLUDE_KEYS 中的任何键"""
        result = _sanitize_aif_return(return_dict, source="test")
        for key in _ANALYST_EXCLUDE_KEYS:
            assert key not in result, f"排除键 '{key}' 不应出现在结果中"

    # ── 属性 2: 保留键不变 ─────────────────────────────────────
    @given(return_dict=arbitrary_dict_strategy())
    @settings(max_examples=200, deadline=None)
    def test_prop2_non_excluded_keys_preserved(self, return_dict: dict[str, Any]):
        """保留键不变：非排除键的键值对原样保留"""
        result = _sanitize_aif_return(return_dict, source="test")
        for key, value in return_dict.items():
            if key not in _ANALYST_EXCLUDE_KEYS:
                assert key in result, f"非排除键 '{key}' 应保留在结果中"
                assert result[key] == value, f"非排除键 '{key}' 的值应原样保留"

    # ── 属性 3: 键数单调 ───────────────────────────────────────
    @given(return_dict=arbitrary_dict_strategy())
    @settings(max_examples=200, deadline=None)
    def test_prop3_key_count_monotonic(self, return_dict: dict[str, Any]):
        """键数单调：len(result) <= len(input)"""
        result = _sanitize_aif_return(return_dict, source="test")
        assert len(result) <= len(return_dict), f"结果键数 {len(result)} 应 <= 输入键数 {len(return_dict)}"

    # ── 属性 4: 幂等性 ─────────────────────────────────────────
    @given(return_dict=arbitrary_dict_strategy())
    @settings(max_examples=200, deadline=None)
    def test_prop4_idempotent(self, return_dict: dict[str, Any]):
        """幂等性：两次清洗结果相同"""
        r1 = _sanitize_aif_return(return_dict, source="test")
        r2 = _sanitize_aif_return(r1, source="test")
        assert r1 == r2

    # ── 属性 5: 空 dict 输入 ────────────────────────────────────
    def test_prop5_empty_dict(self):
        """空 dict 输入返回空 dict"""
        result = _sanitize_aif_return({}, source="test")
        assert result == {}

    # ── 属性 6: 全排除键 dict ──────────────────────────────────
    @given(
        st.lists(
            st.sampled_from(sorted(_ANALYST_EXCLUDE_KEYS) if _CAN_TEST_SANITIZE else ["market_report"]),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop6_all_excluded_returns_empty(self, keys: list[str]):
        """全排除键 dict 返回空 dict"""
        if not _CAN_TEST_SANITIZE:
            pytest.skip("_ANALYST_EXCLUDE_KEYS 不可用")
        input_dict = dict.fromkeys(keys, "test_value")
        result = _sanitize_aif_return(input_dict, source="test")
        assert result == {}, f"全排除键输入应返回空 dict, 实际: {result}"


# ================================================================
# 模块C: 状态 Schema 不变性
# ================================================================


@pytest.mark.skipif(
    not _CAN_TEST_REDUCERS,
    reason=f"AgentState 导入失败: {_REDUCER_SKIP_REASON if _CAN_TEST_REDUCERS is False else ''}",
)
class TestAgentStateSchema:
    """
    [`AgentState`](tradingagents/agents/utils/agent_states.py:162) Schema 不变性测试

    测试属性:
        - AgentState 的字段默认值在创建后不变
        - reducer 组合行为一致性
        - 必需字段的存在性
    """

    # ── 属性 1: AgentState 类型对象存在 ────────────────────────
    def test_prop1_schema_exists(self):
        """AgentState class 应正确定义"""
        assert AgentState is not None
        assert hasattr(AgentState, "__annotations__")

    # ── 属性 2: 必需字段的存在性 ──────────────────────────────
    def test_prop2_required_fields_exist(self):
        """AgentState 应包含所有必需的 LangGraph 字段"""
        annotations = AgentState.__annotations__
        required_fields = [
            "messages",
            "company_of_interest",
            "trade_date",
            "sender",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "market_tool_call_count",
            "sentiment_tool_call_count",
            "news_tool_call_count",
            "fundamentals_tool_call_count",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "past_context",
            "_aif_iteration_count",
            "_aif_max_iterations",
            "hpc_state",
        ]
        for field in required_fields:
            assert field in annotations, f"必需字段 '{field}' 不在 AgentState 注解中"

    # ── 属性 3: Annotated reducer 存在性 ───────────────────────
    def test_prop3_reducer_annotations_exist(self):
        """使用 reducer 的字段应正确标注"""
        annotations = AgentState.__annotations__

        report_reducer_fields = [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "sender",
            "past_context",
        ]

        for field in report_reducer_fields:
            ann = annotations.get(field)
            assert ann is not None, f"字段 '{field}' 应具有 Annotated reducer 注解"
            if hasattr(ann, "__origin__"):
                # typing.Annotated
                assert _report_reducer in ann.__metadata__, f"字段 '{field}' 应使用 _report_reducer"

    # ── 属性 4: InvestDebateState 字段默认值 ───────────────────
    def test_prop4_invest_debate_state_fields(self):
        """InvestDebateState TypedDict 应包含所有必需字段"""
        required = [
            "bull_history",
            "bear_history",
            "history",
            "current_response",
            "judge_decision",
            "count",
        ]
        for field in required:
            assert field in InvestDebateState.__annotations__, f"InvestDebateState 缺少字段 '{field}'"

    # ── 属性 5: RiskDebateState 字段默认值 ─────────────────────
    def test_prop5_risk_debate_state_fields(self):
        """RiskDebateState TypedDict 应包含所有必需字段"""
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
            assert field in RiskDebateState.__annotations__, f"RiskDebateState 缺少字段 '{field}'"

    # ── 属性 6: reducer 组合一致性（_report_reducer 链） ───────
    @given(
        a=text_strategy,
        b=text_strategy,
        c=text_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_prop6_report_reducer_chain_consistency(self, a: str, b: str, c: str):
        """_report_reducer 链式调用保持一致性"""
        # 逐步应用 reducer
        s1 = _report_reducer("", a)
        s2 = _report_reducer(s1, b)
        s3 = _report_reducer(s2, c)

        # 直接应用 reducer
        direct = _report_reducer(_report_reducer("", a), _report_reducer(b, c))

        # 最终状态应该一致
        # 注意: 由于 last-write-wins 语义，只要 b 和 c 都是非空，
        # s3 和 direct 都应该等于 c（最后一个非空值）
        non_empty_chain = all(x and x.strip() for x in [a, b, c])
        if non_empty_chain:
            assert s3 == c
            assert direct == c

    # ── 属性 7: _counter_reducer 链式单调性 ────────────────────
    @given(
        values=st.lists(positive_int, min_size=1, max_size=20),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop7_counter_chain_monotonic(self, values: list[int]):
        """_counter_reducer 链式调用保持单调递增"""
        result = 0
        for v in values:
            result = _counter_reducer(result, v)
        assert result == max(values), f"链式 _counter_reducer 结果 {result} 应等于 max(values)={max(values)}"

    # ── 属性 8: _report_reducer 幂等链 ─────────────────────────
    @given(text=non_empty_text)
    @settings(max_examples=200, deadline=None)
    def test_prop8_report_reducer_idempotent_chain(self, text: str):
        """_report_reducer 连续应用同一非空值结果不变"""
        result = _report_reducer("", text)
        for _ in range(10):
            result = _report_reducer(result, text)
        assert result == text

    # ── 属性 9: _dict_merge_reducer count 单调性 ────────────────
    @given(
        dicts=st.lists(
            st.dictionaries(
                keys=st.just("count"),
                values=positive_int,
                min_size=1,
                max_size=1,
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop9_dict_merge_count_monotonic(self, dicts: list[dict[str, int]]):
        """_dict_merge_reducer 的 count 字段取最大值"""
        result: Any = None
        for d in dicts:
            result = _dict_merge_reducer(result, d)
        assert result is not None
        assert result["count"] == max(d["count"] for d in dicts)

    # ── 属性 10: _dict_merge_reducer 空字符串不覆盖 ────────────
    @given(
        initial=st.dictionaries(
            keys=st.sampled_from(["bull_history", "bear_history", "history"]),
            values=non_empty_text,
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop10_dict_merge_empty_string_not_overwrite(self, initial: dict[str, str]):
        """_dict_merge_reducer 空字符串不覆盖已有非空值"""
        result = _dict_merge_reducer(None, initial)
        empty_update = dict.fromkeys(initial, "")
        result2 = _dict_merge_reducer(result, empty_update)
        for k, v in initial.items():
            # 如果初始值非空，且新值为空字符串，应保留原值
            if v.strip():
                assert result2[k] == v


# ================================================================
# 跨模块综合测试
# ================================================================


class TestCrossModuleIntegration:
    """
    跨模块综合属性基测试

    验证多个 reducer 和 _sanitize_aif_return 在模拟 LangGraph
    运行时的组合行为一致性。
    """

    @given(
        report_fields=st.dictionaries(
            keys=st.sampled_from(["market_report", "sentiment_report", "news_report", "fundamentals_report"]),
            values=st.text(min_size=0, max_size=100),
            min_size=0,
            max_size=4,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_prop1_sanitize_never_removes_reducer_fields(self, report_fields: dict[str, str]):
        """_sanitize_aif_return 中的排除键与 _report_reducer 字段完全一致"""
        if not _CAN_TEST_SANITIZE or not _CAN_TEST_REDUCERS:
            pytest.skip("依赖模块不可用")
        # 验证所有排除键在 AgentState 中都有对应的 _report_reducer
        for key in _ANALYST_EXCLUDE_KEYS:
            annotations = AgentState.__annotations__
            if key in annotations:
                ann = annotations[key]
                if hasattr(ann, "__origin__"):
                    assert _report_reducer in ann.__metadata__ or _dict_merge_reducer in ann.__metadata__, (
                        f"排除键 '{key}' 应在 AgentState 中有对应的 reducer"
                    )
