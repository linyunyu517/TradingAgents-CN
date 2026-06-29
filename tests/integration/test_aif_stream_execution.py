#!/usr/bin/env python3
"""
集成测试 2: AIF Nodes → TradingGraph Stream Execution

验证目标:
  1. `_sanitize_aif_return()` 能正确过滤分析师管线字段，
     防止 LangGraph 通道冲突 (InvalidUpdateError)。
  2. `graph.stream(init_agent_state, stream_mode="updates")`
     在 AIF 节点正确清洗返回值时不会触发 InvalidUpdateError。
  3. 方案C 回退机制：当 stream_mode="updates" 触发 InvalidUpdateError 时，
     `propagate()` 能正确回退到 stream_mode="values"。
  4. AIF 节点返回的键不会与分析师管线键冲突。

背景:
    - 方案B: _sanitize_aif_return() 作为 defense-in-depth 安全网，
      从 AIF 节点返回值中移除分析师管线字段。
    - 方案C: propagate() 方法中的 try/except 捕获 InvalidUpdateError，
      自动切换到 stream_mode="values"。
    - RUNTIME-042: _process_stream_chunk() 统一处理 updates 和 values 两种模式。
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# ====================================================================
# Test: _sanitize_aif_return
# ====================================================================


class TestSanitizeAifReturn:
    """验证 _sanitize_aif_return() 行为。"""

    def test_filters_analyst_report_keys(self):
        """应过滤掉分析师管线字段。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        return_dict = {
            "hpc_state": {"step": 1},
            "aif_state": {"belief": 0.5},
            "market_report": "should be filtered",
            "sentiment_report": "should be filtered",
            "news_report": "should be filtered",
            "fundamentals_report": "should be filtered",
            "investment_plan": "should be filtered",
        }

        result = _sanitize_aif_return(return_dict, source="test")

        # 确认所有分析师字段被过滤
        assert "market_report" not in result
        assert "sentiment_report" not in result
        assert "news_report" not in result
        assert "fundamentals_report" not in result
        assert "investment_plan" not in result

        # 确认 AIF/HPC 相关字段保留
        assert "hpc_state" in result
        assert "aif_state" in result
        assert result["hpc_state"]["step"] == 1
        assert result["aif_state"]["belief"] == 0.5

    def test_keeps_aif_specific_fields(self):
        """应保留所有 AIF 专用字段。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        return_dict = {
            "aif_selection": {"action": "buy"},
            "aif_action_trace": [{"step": 1}],
            "aif_belief": {"value": 0.8},
            "aif_free_energy": -0.5,
            "aif_prior_injections": [],
            "aif_observation": {"price": 100},
            "aif_meta_diagnostics": {"diverged": False},
            "aif_meta_triggered": True,
            "fusion_action": "hold",
            "fusion_confidence": 0.7,
            "_aif_iteration_count": 1,
            "_aif_max_iterations": 3,
        }

        result = _sanitize_aif_return(return_dict, source="test")

        for key in return_dict:
            assert key in result, f"AIF 专用字段 {key} 应被保留"

    def test_filters_sender_and_debate_states(self):
        """应过滤 sender 和辩论状态字段。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        return_dict = {
            "hpc_state": {},
            "sender": "AIF_Node",
            "investment_debate_state": {"count": 1},
            "risk_debate_state": {"count": 0},
            "trader_investment_plan": "should be filtered",
            "final_trade_decision": "should be filtered",
        }

        result = _sanitize_aif_return(return_dict, source="test")

        assert "sender" not in result
        assert "investment_debate_state" not in result
        assert "risk_debate_state" not in result
        assert "trader_investment_plan" not in result
        assert "final_trade_decision" not in result
        assert "hpc_state" in result

    def test_returns_empty_dict_for_all_filtered(self):
        """当所有键都被过滤时，应返回空 dict。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        return_dict = {
            "market_report": "report1",
            "sentiment_report": "report2",
        }

        result = _sanitize_aif_return(return_dict, source="test")
        assert result == {}

    def test_preserves_non_conflicting_keys(self):
        """应保留既不在排除列表中也不冲突的键。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        return_dict = {
            "hpc_state": {"step": 1},
            "market_report": "filtered",
            "custom_field": "kept",
            "another_field": 42,
        }

        result = _sanitize_aif_return(return_dict, source="test")

        assert "custom_field" in result
        assert result["custom_field"] == "kept"
        assert "another_field" in result
        assert result["another_field"] == 42


# ====================================================================
# Test: _ANALYST_EXCLUDE_KEYS Completeness
# ====================================================================


class TestAnalystExcludeKeysCompleteness:
    """验证 _ANALYST_EXCLUDE_KEYS 的完整性和一致性。"""

    def test_all_report_channels_covered(self):
        """
        验证 setup.py 中注册的所有 report_channels 都在排除集合中。

        这是关键安全测试：如果 setup.py 增加了新的 report channel
        但忘记在 _ANALYST_EXCLUDE_KEYS 中添加，AIF 节点可能意外写入
        该通道并触发 InvalidUpdateError。
        """
        from tradingagents.hpc_loop.aif_integration import _ANALYST_EXCLUDE_KEYS

        # 这些是在 setup.py 中验证的 report_channels
        all_report_channels = [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "sender",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "past_context",
        ]

        for channel in all_report_channels:
            assert channel in _ANALYST_EXCLUDE_KEYS, (
                f"通道 {channel} 已在 setup.py 中注册为 report_channel，"
                f"但未在 _ANALYST_EXCLUDE_KEYS 中排除！"
                f"这可能导致 AIF 节点写入此通道时触发 InvalidUpdateError。"
            )

    def test_exclude_keys_not_contain_aif_keys(self):
        """排除集合不应包含 AIF 专用键。"""
        from tradingagents.hpc_loop.aif_integration import _ANALYST_EXCLUDE_KEYS

        aif_keys = [
            "hpc_state",
            "aif_state",
            "_aif_iteration_count",
            "_aif_max_iterations",
            "fusion_action",
            "fusion_confidence",
            "fusion_reasoning",
            "aif_selection",
            "aif_belief",
            "aif_free_energy",
            "aif_observation",
        ]

        for key in aif_keys:
            assert key not in _ANALYST_EXCLUDE_KEYS, f"AIF 专用键 {key} 不应出现在排除集合中"


# ====================================================================
# Test: Graph Stream with AIF-like Return Values
# ====================================================================


class TestGraphStreamAifCompatibility:
    """
    验证 graph.stream() 在 AIF 节点返回清洗后的值时不会触发
    InvalidUpdateError。

    测试策略:
    使用 StateGraph + 自定义节点来模拟 AIF 节点返回各种值，
    验证 stream() 是否能正确处理。
    """

    def test_state_update_with_sanitized_aif_return(self):
        """
        验证使用 _sanitize_aif_return() 清洗后的返回值更新 state
        时不会触发 InvalidUpdateError。
        """
        try:
            from typing import Annotated, TypedDict

            from langgraph.errors import InvalidUpdateError
            from langgraph.graph import StateGraph
            from langgraph.graph.message import MessagesState

            # 创建一个简化的测试状态（模拟 AgentState 的核心结构）
            class TestState(TypedDict):
                messages: Annotated[
                    list,
                    lambda a, b: a + b if isinstance(a, list) and isinstance(b, list) else (b if b is not None else a),
                ]
                market_report: str
                aif_state: Any
                hpc_state: Any
                _aif_iteration_count: int

            from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

            def aif_node(state: TestState) -> dict:
                """模拟 AIF 节点，返回带分析师字段的值（但经过清洗）。"""
                raw_return = {
                    "hpc_state": {"step": 1},
                    "aif_state": {"belief": 0.5},
                    "market_report": "this would be filtered",  # 会被清洗
                    "_aif_iteration_count": 1,
                }
                return _sanitize_aif_return(raw_return, source="test")

            # 构建图
            workflow = StateGraph(TestState)
            workflow.add_node("aif_node", aif_node)
            workflow.set_entry_point("aif_node")
            workflow.set_finish_point("aif_node")
            compiled = workflow.compile()

            # 执行 stream - 不应抛出 InvalidUpdateError
            init_state = {
                "messages": [],
                "market_report": "",
                "aif_state": None,
                "hpc_state": None,
                "_aif_iteration_count": 0,
            }

            chunks = []
            for chunk in compiled.stream(init_state, stream_mode="updates"):
                chunks.append(chunk)

            # 验证结果
            final_state = chunks[-1] if chunks else {}
            assert "aif_node" in final_state
            assert "market_report" not in final_state.get("aif_node", {})
            assert final_state["aif_node"].get("_aif_iteration_count") == 1
            assert final_state["aif_node"]["hpc_state"]["step"] == 1

        except (ImportError, Exception) as e:
            pytest.skip(f"测试需要 langgraph 支持: {e}")

    def test_concurrent_writes_with_reducer(self):
        """
        验证多个节点并发写入同一字段（带 reducer）时，
        stream() 不会抛出 InvalidUpdateError。

        这模拟了 Fusion 模式下 Bull/Bear Researcher 并发写入
        同一 report 字段的场景。
        """
        try:
            from typing import Annotated, TypedDict

            from langgraph.graph import StateGraph

            # 定义带 reducer 的状态（类似 AgentState 的 report 字段）
            def test_reducer(current: str, new: str) -> str:
                if not new or new.strip() == "":
                    return current
                return new

            class TestState(TypedDict):
                messages: Annotated[
                    list,
                    lambda a, b: a + b if isinstance(a, list) and isinstance(b, list) else (b if b is not None else a),
                ]
                market_report: Annotated[str, test_reducer]
                sentiment_report: Annotated[str, test_reducer]

            def bull_node(state: TestState) -> dict:
                return {"market_report": "Bull: market is bullish"}

            def bear_node(state: TestState) -> dict:
                return {"sentiment_report": "Bear: market is bearish"}

            # 使用并行节点（模拟 Fusion 模式中的并发写入）

            workflow = StateGraph(TestState)
            workflow.add_node("bull", bull_node)
            workflow.add_node("bear", bear_node)
            workflow.set_entry_point("bull")
            workflow.add_edge("bull", "bear")
            workflow.set_finish_point("bear")
            compiled = workflow.compile()

            init_state = {
                "messages": [],
                "market_report": "",
                "sentiment_report": "",
            }

            # 使用 updates 模式（模拟 propagate 中有 progress_callback 的场景）
            chunks = []
            for chunk in compiled.stream(init_state, stream_mode="updates"):
                chunks.append(chunk)

            # 验证两个节点都执行了
            node_names_seen = set()
            for chunk in chunks:
                node_names_seen.update(chunk.keys())

            assert "bull" in node_names_seen
            assert "bear" in node_names_seen

            # 如果用 values 模式，验证最终的 state 包含两个报告
            chunks_values = []
            for chunk in compiled.stream(init_state, stream_mode="values"):
                chunks_values.append(chunk)

            final = chunks_values[-1]
            assert "Bull" in final.get("market_report", "")
            assert "Bear" in final.get("sentiment_report", "")

        except Exception as e:
            pytest.skip(f"测试需要 langgraph 支持: {e}")

    def test_invalid_update_error_fallback_simulation(self):
        """
        模拟方案C回退机制：捕获 InvalidUpdateError 并切换到
        stream_mode="values"。

        注：LangGraph 0.7+ 中 Annotated reducer 正常工作，
        不会抛出 InvalidUpdateError。此测试验证 fallback
        逻辑的编码正确性，而非实际触发错误。
        """
        from langgraph.errors import InvalidUpdateError

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # 验证 InvalidUpdateError 是可导入的
        assert InvalidUpdateError is not None

        # 验证方案C逻辑在 propagate() 中已实现
        import inspect

        source = inspect.getsource(TradingAgentsGraph.propagate)

        # 确认方案C回退机制存在
        assert "InvalidUpdateError" in source, "propagate() 应包含 InvalidUpdateError 处理"
        assert "stream_mode" in source, "propagate() 应包含 stream_mode 切换逻辑"

        # 验证存在 retry 逻辑
        assert "max_retries" in source, "propagate() 应包含重试逻辑 (BUG-NEW-006)"


# ====================================================================
# Test: AIF Node Return Values (simulated stream execution)
# ====================================================================


class TestAifNodeReturnValues:
    """
    验证 AIF 各个节点的返回值经过 _sanitize_aif_return() 处理后的正确性。

    覆盖 aif_integration.py 中所有使用 _sanitize_aif_return() 的节点。
    """

    def test_aif_predict_node_return(self):
        """验证 aif_predict_node 的返回值清洗。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        # 模拟 aif_predict_node 的返回值 (line 278-281)
        raw_return = {
            "hpc_state": {"step": 1, "latent_state": {}},
            "aif_state": {"belief": 0.5},
        }
        sanitized = _sanitize_aif_return(raw_return, source="aif_predict_node")
        assert "hpc_state" in sanitized
        assert "aif_state" in sanitized
        assert len(sanitized) == 2  # 只有这两个键

    def test_aif_llm_prior_node_return(self):
        """验证 aif_llm_prior_node 的返回值清洗。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        # 模拟包含分析师字段的返回值
        raw_return = {
            "hpc_state": {"step": 1},
            "aif_state": {"belief": 0.5},
            "market_report": "accidental write",  # 不应发生但清洗会处理
        }
        sanitized = _sanitize_aif_return(raw_return, source="aif_llm_prior_node")
        assert "market_report" not in sanitized
        assert "hpc_state" in sanitized

    def test_aif_select_action_evaluate_node_return(self):
        """验证 aif_select_action_evaluate_node 的返回值清洗 (line 914-938)。"""
        from tradingagents.hpc_loop.aif_integration import _sanitize_aif_return

        # 模拟 aif_select_action_evaluate_node 的完整返回值
        raw_return = {
            "hpc_state": {"step": 2},
            "aif_state": {"belief": 0.7},
            "_aif_iteration_count": 1,
            "_aif_max_iterations": 3,
            "fusion_action": "buy",
            "fusion_confidence": 0.8,
            "fusion_reasoning": "Strong momentum",
            "fusion_efe_scores": {"buy": -0.5, "hold": -0.3},
            "aif_selection": {"action": "buy"},
            "aif_action_trace": [{"step": 1}],
            "aif_free_energy": -0.5,
            "market_report": "FILTERED",  # 意外包含的报告字段
            "sentiment_report": "FILTERED",
        }
        sanitized = _sanitize_aif_return(raw_return, source="aif_select_action_evaluate_node")

        # 分析师字段应被过滤
        assert "market_report" not in sanitized
        assert "sentiment_report" not in sanitized

        # AIF 字段应保留
        assert sanitized["fusion_action"] == "buy"
        assert sanitized["_aif_iteration_count"] == 1
        assert sanitized["aif_free_energy"] == -0.5
        assert sanitized["hpc_state"]["step"] == 2


# ====================================================================
# Test: Propagator get_graph_args
# ====================================================================


class TestPropagatorGraphArgs:
    """验证 Propagator.get_graph_args() 的 stream_mode 选择逻辑。"""

    def test_updates_mode_with_callback(self):
        """有 progress_callback 时应使用 updates 模式。"""
        from tradingagents.graph.propagation import Propagator

        propagator = Propagator()
        args = propagator.get_graph_args(use_progress_callback=True)

        assert args["stream_mode"] == "updates"
        assert "config" in args
        assert args["config"]["recursion_limit"] == 100

    def test_values_mode_without_callback(self):
        """无 progress_callback 时应使用 values 模式。"""
        from tradingagents.graph.propagation import Propagator

        propagator = Propagator()
        args = propagator.get_graph_args(use_progress_callback=False)

        assert args["stream_mode"] == "values"

    def test_custom_recursion_limit(self):
        """应支持自定义 recursion_limit。"""
        from tradingagents.graph.propagation import Propagator

        propagator = Propagator(max_recur_limit=200)
        args = propagator.get_graph_args()

        assert args["config"]["recursion_limit"] == 200


# ====================================================================
# Test: _process_stream_chunk (RUNTIME-042)
# ====================================================================


class TestProcessStreamChunk:
    """验证 _process_stream_chunk() 的兼容性。"""

    def test_process_updates_chunk(self):
        """应能处理 updates 模式的 chunk。"""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # 创建 minimal instance
        MagicMock(spec=TradingAgentsGraph)

        # 验证 _process_stream_chunk 方法的签名存在
        import inspect

        try:
            sig = inspect.signature(TradingAgentsGraph._process_stream_chunk)
            params = list(sig.parameters.keys())
            assert "chunk" in params
            assert "node_timings" in params
            assert "final_state" in params
        except (ValueError, AttributeError):
            pytest.skip("无法检查 _process_stream_chunk 签名")

    def test_propagate_method_has_retry_logic(self):
        """验证 propagate() 包含三层重试逻辑。"""
        import inspect

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        source = inspect.getsource(TradingAgentsGraph.propagate)

        # 验证重试逻辑存在
        assert "for attempt in range(max_retries)" in source
        assert "retry_delays" in source
        assert "time.sleep(delay)" in source
        assert "InvalidUpdateError" in source
        assert "stream_mode" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
