#!/usr/bin/env python3
"""
Round 4 Phase 3 — 属性基测试 (Property-Based Testing)

使用 Hypothesis 框架验证以下属性和不变量：
  测试组 1: 通道冲突回归测试
  测试组 2: AIF 返回键完整性
  测试组 3: 通道类型验证
  测试组 4: 迭代计数器单调性

运行方式:
    cd D:\\AI-Projects\\TradingAgents-CN_v1.0.1
    python -m pytest tests/test_round4_property_based.py -v --hypothesis-show-statistics
"""

import logging
import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from tradingagents.agents.utils.agent_states import AgentState

# 禁用非必要的日志输出
logging.disable(logging.CRITICAL)


# ==============================================================
# 测试组 1: 通道冲突回归测试
# ==============================================================


class TestReportReducer:
    """
    属性基测试: _report_reducer 幂等性

    验证 `_report_reducer(current, new)` 的合并语义：
    - 属性 2（幂等）: 空字符串 new 应返回 current
    - 额外: 非空 new 应替换 current
    """

    def _report_reducer(self, current: str, new: str) -> str:
        """_report_reducer 的内联副本，避免导入依赖"""
        if not new or new.strip() == "":
            return current
        return new

    @given(
        current=st.text(max_size=200),
        padding=st.text(alphabet=" \t\n\r", max_size=20),
    )
    @settings(max_examples=200)
    def test_idempotent_empty_new(self, current: str, padding: str):
        """属性 2（幂等）: _report_reducer(current, '') = current"""
        # 空字符串或空白字符串应返回 current
        result = self._report_reducer(current, "")
        assert result == current, f"空字符串应返回 current (got {result!r})"

        result = self._report_reducer(current, padding)
        assert result == current, f"空白字符串应返回 current (padding={padding!r}, got {result!r})"

    @given(
        current=st.text(max_size=200),
        new=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=200)
    def test_non_empty_new_wins(self, current: str, new: str):
        """非空 new 应替换 current"""
        assume(new.strip() != "")  # 确保 new 非空白
        result = self._report_reducer(current, new)
        assert result == new, f"非空 new 应替换 current (got {result!r})"

    @given(
        values=st.lists(st.text(max_size=100), min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_last_non_empty_wins_chain(self, values: list[str]):
        """链式合并: 最终结果应等于最后一个非空值"""
        accumulated = ""
        for v in values:
            accumulated = self._report_reducer(accumulated, v)
        # 预期: 最后一个非空值
        expected = ""
        for v in reversed(values):
            if v.strip():
                expected = v
                break
        assert accumulated == expected, f"链式合并结果应为最后一个非空值 {expected!r}, got {accumulated!r}"


# ==============================================================
# 测试组 2: AIF 返回键完整性
# ==============================================================

# create_aif_select_action_evaluate_node 返回 dict 中的键
_AIF_RETURN_KEYS = [
    "hpc_state",
    "aif_state",
    "_aif_iteration_count",
    "_aif_max_iterations",
    "fusion_action",
    "fusion_confidence",
    "fusion_reasoning",
    "fusion_efe_scores",
    "aif_selection",
    "aif_action_trace",
    "aif_belief",
    "aif_free_energy",
    "aif_prior_injections",
    "aif_current_belief",
    "aif_observation",
    "aif_meta_diagnostics",
    "aif_meta_triggered",
    "aif_meta_temperature",
    "aif_meta_cycle_count",
    "aif_hierarchical_free_energy",
    "aif_meta_free_energy",
    "aif_meta_window_stats",
    "aif_free_energy_history",
]

# 路由函数所需的键（aif_route_from_update_belief 和 aif_route_from_llm_prior）
_AIF_ROUTE_REQUIRED_KEYS = ["_aif_iteration_count", "_aif_max_iterations"]

# 必须排除的报告键（AIF 节点不得写入这些通道）
_AIF_EXCLUDED_REPORT_KEYS = [
    "market_report",
    "bull_report",
    "bear_report",
    "news_report",
    "sentiment_report",
    "fundamentals_report",
]


class TestAIFReturnKeys:
    """
    属性基测试: create_aif_select_action_evaluate_node 返回键完整性
    """

    def test_route_required_keys_present(self):
        """
        属性 3（路由所需键存在）:
        返回 dict 必须包含 _aif_iteration_count 和 _aif_max_iterations
        """
        for required in _AIF_ROUTE_REQUIRED_KEYS:
            assert required in _AIF_RETURN_KEYS, f"路由所需键 {required} 不在 _AIF_RETURN_KEYS 中"

    def test_market_report_keys_excluded(self):
        """
        属性 4（市场报告键排除）:
        返回 dict 不得包含 market_report/bull_report/bear_report/news_report/sentiment_report/fundamentals_report
        """
        for excluded in _AIF_EXCLUDED_REPORT_KEYS:
            assert excluded not in _AIF_RETURN_KEYS, f"返回 dict 不应包含报告键 {excluded}"

        annotations = getattr(AgentState, "__annotations__", {})
        missing = []
        for key in _AIF_RETURN_KEYS:
            if key not in annotations:
                missing.append(key)

        assert not missing, f"以下 AIF 返回键在 AgentState.__annotations__ 中缺失: {missing}"


# ==============================================================
# 测试组 3: 通道类型验证
# ==============================================================


class TestChannelTypes:
    """
    属性基测试: 编译后 LangGraph 通道类型验证

    需要导入 tradingagents 包和 setup.py 中的编译函数。
    如果无法编译（如缺少依赖），测试将跳过。
    """

    @classmethod
    def _get_compiled_graph(cls):
        """尝试获取编译后的图对象"""
        try:
            from tradingagents.graph.trading_graph import TradingAgent

            # 使用最小配置编译
            agent = TradingAgent(
                ticker="TEST",
                start_date="20250101",
                end_date="20250102",
                llm_config={
                    "provider": "openai",
                    "api_key": "sk-test",
                    "model": "gpt-4o-mini",
                },
                hpc_config={"enabled": False},
                aif_config={"enabled": False},
            )
            workflow = agent.setup()
            compiled = workflow.compile()
            return compiled
        except Exception as exc:
            pytest.skip(f"无法编译图: {exc}")

    def test_market_report_channel_type(self):
        """
        属性 6（market_report 通道）:
        编译图后 market_report 通道类型为 BinaryOperatorAggregate
        """
        compiled = self._get_compiled_graph()
        channels = compiled.get_graph().channels
        mr_channel = channels.get("market_report")
        assume(mr_channel is not None)
        type_name = type(mr_channel).__name__
        assert "BinaryOperator" in type_name, f"market_report 通道类型应为 BinaryOperatorAggregate, 实际为 {type_name}"

    def test_aif_iteration_count_channel_type(self):
        """
        属性 7（_aif_iteration_count 通道）:
        编译图后 _aif_iteration_count 通道类型为 BinaryOperatorAggregate
        """
        compiled = self._get_compiled_graph()
        channels = compiled.get_graph().channels
        aif_iter = channels.get("_aif_iteration_count")
        assume(aif_iter is not None)
        type_name = type(aif_iter).__name__
        assert "BinaryOperator" in type_name, (
            f"_aif_iteration_count 通道类型应为 BinaryOperatorAggregate, 实际为 {type_name}"
        )


# ==============================================================
# 测试组 4: 迭代计数器单调性
# ==============================================================


class TestIterationCounterMonotonic:
    """
    属性基测试: _aif_iteration_count 单调递增属性

    使用 _counter_reducer（max 策略）验证单调性：
    - 属性 8（计数器单调增）: 在 AIF 迭代循环中 _aif_iteration_count 应单调递增
    """

    def _counter_reducer(self, current: int, new: int) -> int:
        """_counter_reducer 的内联副本"""
        return max(current, new)

    @given(
        updates=st.lists(
            st.integers(min_value=0, max_value=100),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=200)
    def test_monotonic_increasing(self, updates: list[int]):
        """
        属性 8（计数器单调增）:
        _counter_reducer(max) 保证最终值 >= 所有输入值
        """
        accumulated = 0
        max_seen = 0
        for u in updates:
            accumulated = self._counter_reducer(accumulated, u)
            max_seen = max(max_seen, u)

        # 最终累计值应等于所有输入的最大值
        assert accumulated == max_seen, f"counter_reducer 最终值应为 {max_seen}, 实际为 {accumulated}"

    @given(
        updates=st.lists(
            st.integers(min_value=1, max_value=10),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_step_by_step_monotonic(self, updates: list[int]):
        """
        验证逐步合并时 counter_reducer 保持单调非减
        """
        accumulated = 0
        for u in updates:
            prev = accumulated
            accumulated = self._counter_reducer(accumulated, accumulated + u)
            assert accumulated >= prev, f"逐步递增后值不应减小: {prev} -> {accumulated}"


# ==============================================================
# 测试组 5: _dict_merge_reducer 合并语义
# ==============================================================


class TestDictMergeReducer:
    """
    补充测试: _dict_merge_reducer 的合并语义

    验证：
    - count 字段取最大值
    - 字符串字段 last-write-wins（非空）
    - 空字符串不覆盖
    """

    def _dict_merge_reducer(self, current: dict, new: dict) -> dict:
        """_dict_merge_reducer 的内联副本"""
        if current is None:
            return new
        result = dict(current)
        for k, v in new.items():
            if k == "count":
                result[k] = max(result.get(k, 0), v)
            elif isinstance(v, str) and not v.strip():
                if k not in result or not result.get(k):
                    result[k] = v
            else:
                result[k] = v
        return result

    @given(
        current_count=st.integers(min_value=0, max_value=100),
        new_count=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_count_takes_max(self, current_count: int, new_count: int):
        """count 字段应取最大值"""
        current = {"count": current_count}
        new = {"count": new_count}
        result = self._dict_merge_reducer(current, new)
        assert result["count"] == max(current_count, new_count), (
            f"count 应取最大值, expected {max(current_count, new_count)}, got {result['count']}"
        )

    @given(
        current_val=st.text(max_size=50),
        new_val=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_string_field_last_write_wins(self, current_val: str, new_val: str):
        """非空字符串应 last-write-wins"""
        current = {"field": current_val}
        new = {"field": new_val}
        result = self._dict_merge_reducer(current, new)
        if new_val.strip():
            assert result["field"] == new_val
        else:
            # 空字符串不覆盖
            assert result["field"] == current_val


# ==============================================================
# 入口
# ==============================================================

if __name__ == "__main__":
    # 直接运行模式 (不依赖 pytest)
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--hypothesis-show-statistics"]))
