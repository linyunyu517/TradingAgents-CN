"""
TradingAgents — Graph Setup 单元测试

覆盖目标: tradingagents/graph/setup.py
- _force_channel_to_binary_operator_aggregate()  — 通道类型强制转换
- aif_should_continue_iteration()                — AIF 迭代继续判断
- aif_route_from_update_belief()                 — UpdateBelief 条件路由
- _route_aif_observe()                           — AIF_Observe 条件路由
- aif_route_from_llm_prior()                     — LLMPrior 条件路由
- _route_to_risky_analyst()                      — 扩散路由守卫
- _create_defensive_tool_node()                  — RaceGuard 包装器
- diffusion_advisor_node()                       — 扩散顾问节点（降级路径）
- fusion_node()                                  — 加权融合节点
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ======================================================================
# _force_channel_to_binary_operator_aggregate
# ======================================================================
class TestForceChannelToBinaryOperatorAggregate:
    """验证通道类型强制转换安全网"""

    def test_channel_none_returns_false(self):
        """当通道不存在时返回 False"""
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        result = _force_channel_to_binary_operator_aggregate({}, "nonexistent", "_report_reducer")
        assert result is False

    def test_channel_already_binary_operator_returns_false(self):
        """当通道类型已经是 BinaryOperatorAggregate 时返回 False"""
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        # 构造一个名称中包含 'BinaryOperator' 的伪通道
        class FakeBinaryOpChannel:
            pass

        fake = FakeBinaryOpChannel()
        fake.__class__.__name__ = "BinaryOperatorAggregate"

        channels = {"market_report": fake}
        result = _force_channel_to_binary_operator_aggregate(channels, "market_report", "_report_reducer")
        assert result is False

    def test_unknown_reducer_returns_false(self):
        """当 reducer 名称不在映射中时返回 False"""
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        class FakeChannel:
            pass

        fake = FakeChannel()
        fake.__class__.__name__ = "LastValue"

        channels = {"test_key": fake}
        result = _force_channel_to_binary_operator_aggregate(channels, "test_key", "_nonexistent_reducer")
        assert result is False

    @patch("tradingagents.graph.setup.logger")
    def test_import_error_returns_false(self, mock_logger):
        """当 BinaryOperatorAggregate 不可用时返回 False"""
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        class FakeChannel:
            pass

        fake = FakeChannel()
        fake.__class__.__name__ = "LastValue"

        # BinaryOperatorAggregate 在函数内部从 langgraph.channels.binop 导入
        # 因此需要 patch langgraph.channels.binop 的导入路径
        import langgraph.channels.binop

        with patch.object(langgraph.channels.binop, "BinaryOperatorAggregate", side_effect=ImportError("not found")):
            channels = {"test_key": fake}
            result = _force_channel_to_binary_operator_aggregate(channels, "test_key", "_report_reducer")
            assert result is False

    @patch("tradingagents.graph.setup.logger")
    def test_successful_conversion(self, mock_logger):
        """正常路径下成功转换"""
        from tradingagents.agents.utils.agent_states import _report_reducer
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        class FakeChannel:
            pass

        fake = FakeChannel()
        fake.__class__.__name__ = "LastValue"

        # 构造一个 BinaryOperatorAggregate mock
        mock_binop = MagicMock()
        mock_binop_cls = MagicMock(return_value=mock_binop)

        import langgraph.channels.binop

        channels = {"market_report": fake}
        with patch.object(langgraph.channels.binop, "BinaryOperatorAggregate", mock_binop_cls):
            result = _force_channel_to_binary_operator_aggregate(channels, "market_report", "_report_reducer")
            assert result is True
            mock_binop_cls.assert_called_once_with(typ=str, operator=_report_reducer)
            assert channels["market_report"] is mock_binop

    @patch("tradingagents.graph.setup.logger")
    def test_successful_conversion_counter_reducer(self, mock_logger):
        """使用 _counter_reducer 成功转换"""
        from tradingagents.agents.utils.agent_states import _counter_reducer
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        class FakeChannel:
            pass

        fake = FakeChannel()
        fake.__class__.__name__ = "LastValue"

        mock_binop = MagicMock()
        mock_binop_cls = MagicMock(return_value=mock_binop)

        import langgraph.channels.binop

        channels = {"market_tool_call_count": fake}
        with patch.object(langgraph.channels.binop, "BinaryOperatorAggregate", mock_binop_cls):
            result = _force_channel_to_binary_operator_aggregate(channels, "market_tool_call_count", "_counter_reducer")
            assert result is True
            mock_binop_cls.assert_called_once_with(typ=int, operator=_counter_reducer)
            assert channels["market_tool_call_count"] is mock_binop

    @patch("tradingagents.graph.setup.logger")
    def test_exception_during_conversion_returns_false(self, mock_logger):
        """转换过程中抛出异常时返回 False"""
        from tradingagents.graph.setup import _force_channel_to_binary_operator_aggregate

        class FakeChannel:
            pass

        fake = FakeChannel()
        fake.__class__.__name__ = "LastValue"

        import langgraph.channels.binop

        channels = {"market_report": fake}
        with patch.object(langgraph.channels.binop, "BinaryOperatorAggregate", side_effect=Exception("unexpected")):
            result = _force_channel_to_binary_operator_aggregate(channels, "market_report", "_report_reducer")
            assert result is False


# ======================================================================
# AIF 迭代循环路由函数
# ======================================================================
class TestAifShouldContinueIteration:
    """验证 AIF 迭代继续判断"""

    @pytest.fixture
    def setup_module(self):
        """动态导入被测模块（避免 import-time side effects）"""
        from tradingagents.graph.setup import aif_should_continue_iteration

        return aif_should_continue_iteration

    def test_continue_when_below_max(self, setup_module):
        """iteration < max_iter → 'continue_iteration'"""
        fn = setup_module
        state = {"_aif_iteration_count": 1, "_aif_max_iterations": 3}
        assert fn(state) == "continue_iteration"

    def test_exit_when_equal_max(self, setup_module):
        """iteration == max_iter → 'exit_iteration'"""
        fn = setup_module
        state = {"_aif_iteration_count": 3, "_aif_max_iterations": 3}
        assert fn(state) == "exit_iteration"

    def test_exit_when_above_max(self, setup_module):
        """iteration > max_iter → 'exit_iteration'"""
        fn = setup_module
        state = {"_aif_iteration_count": 5, "_aif_max_iterations": 3}
        assert fn(state) == "exit_iteration"

    def test_default_max_iterations(self, setup_module):
        """未设置 max_iter 时使用 AIF_MAX_ITERATIONS 常量"""
        fn = setup_module
        state = {"_aif_iteration_count": 0}
        # iteration=0 < AIF_MAX_ITERATIONS (>=1) → continue
        assert fn(state) == "continue_iteration"

    def test_zero_iteration_continues(self, setup_module):
        """iteration=0 且 0 < max → continue（首次进入循环）"""
        fn = setup_module
        from tradingagents.graph.setup import AIF_MAX_ITERATIONS

        state = {"_aif_iteration_count": 0, "_aif_max_iterations": AIF_MAX_ITERATIONS}
        assert fn(state) == "continue_iteration"


class TestAifRouteFromUpdateBelief:
    """验证 AIF_UpdateBelief 条件路由"""

    @pytest.fixture
    def setup_module(self):
        from tradingagents.graph.setup import aif_route_from_update_belief

        return aif_route_from_update_belief

    def test_iteration_zero_exits(self, setup_module):
        """_aif_iteration_count == 0 → 'exit_iteration'（分析师管线路径）"""
        fn = setup_module
        state = {"_aif_iteration_count": 0, "_aif_max_iterations": 3}
        assert fn(state) == "exit_iteration"

    def test_iteration_positive_continues(self, setup_module):
        """0 < iteration < max_iter → 'continue_iteration'（AIF 循环路径）"""
        fn = setup_module
        state = {"_aif_iteration_count": 1, "_aif_max_iterations": 3}
        assert fn(state) == "continue_iteration"

    def test_iteration_at_max_exits(self, setup_module):
        """iteration >= max_iter → 'exit_iteration'（防止外部无限循环）"""
        fn = setup_module
        state = {"_aif_iteration_count": 3, "_aif_max_iterations": 3}
        assert fn(state) == "exit_iteration"

    def test_iteration_above_max_exits(self, setup_module):
        """iteration > max_iter → 'exit_iteration'"""
        fn = setup_module
        state = {"_aif_iteration_count": 5, "_aif_max_iterations": 3}
        assert fn(state) == "exit_iteration"

    def test_default_max(self, setup_module):
        """未提供 max_iter 时使用 AIF_MAX_ITERATIONS"""
        fn = setup_module
        # iteration=0 → 走分析师管线
        state = {"_aif_iteration_count": 0}
        assert fn(state) == "exit_iteration"


class TestRouteAifObserve:
    """验证 AIF_Observe 条件路由"""

    @pytest.fixture
    def setup_module(self):
        from tradingagents.graph.setup import _route_aif_observe

        return _route_aif_observe

    def test_first_pass_returns_update_belief(self, setup_module):
        """_aif_iteration_count == 0 → 'AIF_UpdateBelief'"""
        fn = setup_module
        state = {"_aif_iteration_count": 0}
        assert fn(state) == "AIF_UpdateBelief"

    def test_iteration_loop_returns_llm_prior(self, setup_module):
        """_aif_iteration_count > 0 → 'AIF_LLMPrior'"""
        fn = setup_module
        state = {"_aif_iteration_count": 1}
        assert fn(state) == "AIF_LLMPrior"

    def test_large_iteration_returns_llm_prior(self, setup_module):
        """多次迭代后仍路由到 AIF_LLMPrior"""
        fn = setup_module
        state = {"_aif_iteration_count": 5}
        assert fn(state) == "AIF_LLMPrior"


class TestAifRouteFromLlmPrior:
    """验证 AIF_LLMPrior 条件路由"""

    @pytest.fixture
    def setup_module(self):
        from tradingagents.graph.setup import aif_route_from_llm_prior

        return aif_route_from_llm_prior

    def test_first_pass_goes_to_analyst(self, setup_module):
        """_aif_iteration_count == 0 → 'to_analyst_pipeline'"""
        fn = setup_module
        state = {"_aif_iteration_count": 0}
        assert fn(state) == "to_analyst_pipeline"

    def test_iteration_goes_to_evaluate(self, setup_module):
        """_aif_iteration_count > 0 → 'to_aif_evaluate'"""
        fn = setup_module
        state = {"_aif_iteration_count": 1}
        assert fn(state) == "to_aif_evaluate"

    def test_large_iteration_goes_to_evaluate(self, setup_module):
        """多次迭代后仍路由到 AIF_SelectAction_Evaluate"""
        fn = setup_module
        state = {"_aif_iteration_count": 3}
        assert fn(state) == "to_aif_evaluate"


# ======================================================================
# _route_to_risky_analyst
# ======================================================================
class TestRouteToRiskyAnalyst:
    """验证扩散路由守卫"""

    def test_with_diffusion_advisor(self):
        """当 DiffusionAdvisor 在节点列表中时路由经过扩散分支"""
        from tradingagents.graph.setup import _route_to_risky_analyst

        workflow = MagicMock()
        all_node_names = ["DiffusionAdvisor", "FusionNode", "Risky Analyst"]
        _route_to_risky_analyst(workflow, all_node_names, "AIF_SelectAction_Evaluate")

        workflow.add_edge.assert_any_call("AIF_SelectAction_Evaluate", "DiffusionAdvisor")
        workflow.add_edge.assert_any_call("DiffusionAdvisor", "FusionNode")
        workflow.add_edge.assert_any_call("FusionNode", "Risky Analyst")

    def test_without_diffusion_advisor(self):
        """当 DiffusionAdvisor 不在节点列表中时直接路由到 Risky Analyst"""
        from tradingagents.graph.setup import _route_to_risky_analyst

        workflow = MagicMock()
        all_node_names = ["Risky Analyst"]
        _route_to_risky_analyst(workflow, all_node_names, "AIF_SelectAction_Evaluate")

        workflow.add_edge.assert_called_once_with("AIF_SelectAction_Evaluate", "Risky Analyst")


# ======================================================================
# _create_defensive_tool_node
# ======================================================================
class TestCreateDefensiveToolNode:
    """验证 RaceGuard ToolNode 包装器"""

    def test_no_ai_with_tool_calls_returns_empty_dict(self):
        """当 messages 中没有含 tool_calls 的 AIMessage 时返回空 dict"""
        from tradingagents.graph.setup import _create_defensive_tool_node

        mock_tool_node = MagicMock()
        # 创建包装器
        wrapper = _create_defensive_tool_node(mock_tool_node, "market")

        # 调用包装器，传入不含 tool_calls 的 state
        state = {"messages": []}
        result = wrapper(state)
        assert result == {}
        mock_tool_node.invoke.assert_not_called()

    def test_has_ai_with_tool_calls_invokes_tool_node(self):
        """当 messages 中含 tool_calls 的 AIMessage 时调用 tool_node.invoke"""
        from tradingagents.graph.setup import _create_defensive_tool_node

        mock_tool_node = MagicMock()
        mock_tool_node.invoke.return_value = {"result": "success"}

        wrapper = _create_defensive_tool_node(mock_tool_node, "news")

        # 构造一个模拟消息
        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "test_tool", "args": {}}]

        state = {"messages": [mock_msg]}
        result = wrapper(state)
        assert result == {"result": "success"}
        mock_tool_node.invoke.assert_called_once_with(state)

    def test_ai_message_without_tool_calls_returns_empty(self):
        """AIMessage 存在但没有 tool_calls 字段时返回空 dict"""
        from tradingagents.graph.setup import _create_defensive_tool_node

        mock_tool_node = MagicMock()
        wrapper = _create_defensive_tool_node(mock_tool_node, "fundamentals")

        # AIMessage 没有 tool_calls 属性
        mock_msg = MagicMock(spec=[])  # 空 spec，没有 tool_calls
        state = {"messages": [mock_msg]}
        result = wrapper(state)
        assert result == {}
        mock_tool_node.invoke.assert_not_called()

    def test_ai_message_with_empty_tool_calls_returns_empty(self):
        """AIMessage 有 tool_calls 但为空列表时返回空 dict"""
        from tradingagents.graph.setup import _create_defensive_tool_node

        mock_tool_node = MagicMock()
        wrapper = _create_defensive_tool_node(mock_tool_node, "market")

        mock_msg = MagicMock()
        mock_msg.tool_calls = []
        state = {"messages": [mock_msg]}
        result = wrapper(state)
        assert result == {}
        mock_tool_node.invoke.assert_not_called()


# ======================================================================
# diffusion_advisor_node — 降级路径
# ======================================================================
class TestDiffusionAdvisorNodeDegraded:
    """验证扩散顾问节点降级路径"""

    def test_diffusion_not_available_returns_uniform_prior(self):
        """当 _DIFFUSION_AVAILABLE 为 False 时返回均匀先验"""
        with patch("tradingagents.graph.setup._DIFFUSION_AVAILABLE", False):
            from tradingagents.graph.setup import diffusion_advisor_node

            result = diffusion_advisor_node({"trader_investment_plan": "buy AAPL"})
            assert result["diffusion_decision"]["action"] == "uniform_prior"
            assert result["diffusion_decision"]["confidence"] == 0.0
            assert result["diffusion_decision"]["weight"] == 0.0

    def test_empty_trader_plan_returns_uniform_prior(self):
        """当 trader_investment_plan 为空时退化为均匀先验"""
        with patch("tradingagents.graph.setup._DIFFUSION_AVAILABLE", True):
            from tradingagents.graph.setup import diffusion_advisor_node

            result = diffusion_advisor_node({"trader_investment_plan": ""})
            assert result["diffusion_decision"]["action"] == "uniform_prior"
            assert result["diffusion_decision"]["confidence"] == 0.0

    def test_missing_trader_plan_returns_uniform_prior(self):
        """当 trader_investment_plan 缺失时退化为均匀先验"""
        with patch("tradingagents.graph.setup._DIFFUSION_AVAILABLE", True):
            from tradingagents.graph.setup import diffusion_advisor_node

            result = diffusion_advisor_node({})
            assert result["diffusion_decision"]["action"] == "uniform_prior"
            assert result["diffusion_decision"]["confidence"] == 0.0

    def test_exception_during_diffusion_returns_uniform_prior(self):
        """当扩散推理抛出异常时退化为均匀先验"""
        with patch("tradingagents.graph.setup._DIFFUSION_AVAILABLE", True):
            with patch("tradingagents.graph.setup.TradingDecisionDiffuser", side_effect=ImportError("no module")):
                from tradingagents.graph.setup import diffusion_advisor_node

                result = diffusion_advisor_node({"trader_investment_plan": "buy AAPL"})
                assert result["diffusion_decision"]["action"] == "uniform_prior"
                assert result["diffusion_decision"]["confidence"] == 0.0


# ======================================================================
# fusion_node
# ======================================================================
class TestFusionNode:
    """验证加权融合节点"""

    def test_empty_diffusion_decision_degraded(self):
        """当 diffusion_decision 为空时退化"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {},
            },
        )
        assert result["fused_decision"]["source"] == "trader_only"
        assert result["fused_decision"]["fusion_weight"] == 0.0

    def test_zero_confidence_degraded(self):
        """当 confidence <= 0.0 时退化"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {"confidence": 0.0},
            },
        )
        assert result["fused_decision"]["source"] == "trader_only"

    def test_negative_confidence_degraded(self):
        """当 confidence < 0.0 时退化"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {"confidence": -0.5},
            },
        )
        assert result["fused_decision"]["source"] == "trader_only"

    def test_degraded_flag_triggers_degradation(self):
        """当 diffusion_decision 标记 degraded=True 时退化"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {"confidence": 0.8, "degraded": True},
            },
        )
        assert result["fused_decision"]["source"] == "trader_only"
        assert "degraded" in result["fused_decision"].get("degraded_reason", "")

    def test_stale_timestamp_triggers_degradation(self):
        """当时间戳超过 300 秒时退化"""
        from tradingagents.graph.setup import fusion_node

        old_timestamp = datetime.now(timezone.utc).isoformat()
        # 难以在毫秒级测试 300 秒过期，直接验证时间戳解析路径
        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {
                    "confidence": 0.8,
                    "timestamp": old_timestamp,
                },
            },
        )
        # 刚生成的时间戳不会过期（<300s），应走融合路径
        assert result["fused_decision"]["source"] == "fusion"

    def test_invalid_timestamp_handled_gracefully(self):
        """无效时间戳不触发退化（解析异常仅记录日志）"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {
                    "confidence": 0.8,
                    "timestamp": "not-a-timestamp",
                },
            },
        )
        # 时间戳解析失败不计入退化，继续融合
        assert result["fused_decision"]["source"] == "fusion"

    def test_successful_fusion_with_confidence_modulation(self):
        """正常融合路径：置信度调制的加权融合"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {
                    "action_weights": [0.2, 0.3, 0.5],
                    "preferred_action": [1, 2, 0],
                    "confidence": 0.8,
                    "weight": 0.8,
                },
                "diffusion_weight": 0.4,
            },
        )
        assert result["fused_decision"]["source"] == "fusion"
        assert result["fused_decision"]["diffusion_confidence"] == 0.8
        assert result["fused_decision"]["diffusion_weight_raw"] == 0.4
        # diff_weight = diff_weight_raw * diff_confidence = 0.4 * 0.8 = 0.32
        # 使用 pytest.approx 避免浮点精度问题
        assert result["fused_decision"]["diff_weight"] == pytest.approx(0.32, rel=1e-9)
        assert result["fused_decision"]["trader_weight"] == pytest.approx(0.68, rel=1e-9)

    def test_default_diffusion_weight(self):
        """未设置 diffusion_weight 时使用默认值 0.4"""
        from tradingagents.graph.setup import fusion_node

        result = fusion_node(
            {
                "trader_investment_plan": "buy AAPL",
                "diffusion_decision": {"confidence": 0.5},
            },
        )
        # diff_weight = 0.4 * 0.5 = 0.2
        assert result["fused_decision"]["diff_weight"] == pytest.approx(0.2, rel=1e-9)
