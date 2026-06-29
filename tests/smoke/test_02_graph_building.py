# TradingAgents-CN Smoke Test — LangGraph 图构建测试
# ============================================================
# 使用 mocked LLM 构建完整的 LangGraph StateGraph，验证：
#   - GraphSetup 能成功创建图对象
#   - 图能被正常编译
#   - 节点注册正确
#   所有 LLM 调用均使用 mock 对象，不产生真实 API 请求。
# ============================================================

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestGraphBuilding:
    """LangGraph 图构建冒烟测试"""

    @pytest.fixture
    def mock_components(self, mock_llm, mock_toolkit, mock_memory, mock_tool_nodes):
        """准备构建图所需的全部 mock 组件"""
        return {
            "quick_thinking_llm": mock_llm,
            "deep_thinking_llm": mock_llm,
            "toolkit": mock_toolkit,
            "tool_nodes": mock_tool_nodes,
            "bull_memory": mock_memory,
            "bear_memory": mock_memory,
            "trader_memory": mock_memory,
            "invest_judge_memory": mock_memory,
            "risk_manager_memory": mock_memory,
        }

    def test_graph_setup_instantiation(self, mock_components):
        """GraphSetup 可以被实例化（不传入 HPC/AIF 管理器）"""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.graph.setup import GraphSetup

        conditional_logic = MagicMock(spec=ConditionalLogic)
        setup = GraphSetup(
            **mock_components,
            conditional_logic=conditional_logic,
            config={},
            hpc_loop_manager=None,
            aif_engine_manager=None,
            use_fusion_mode=False,
        )
        assert setup is not None
        assert setup.quick_thinking_llm is mock_components["quick_thinking_llm"]
        assert setup.deep_thinking_llm is mock_components["deep_thinking_llm"]

    def test_graph_setup_with_config(self, mock_components):
        """GraphSetup 可以接受自定义配置"""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.graph.setup import GraphSetup

        conditional_logic = MagicMock(spec=ConditionalLogic)
        config = {
            "llm_provider": "mock",
            "hpc_loop_enabled": False,
            "use_aif_engine": False,
            "diffusion_enabled": False,
        }
        setup = GraphSetup(
            **mock_components,
            conditional_logic=conditional_logic,
            config=config,
            hpc_loop_manager=None,
            aif_engine_manager=None,
            use_fusion_mode=False,
        )
        assert setup.config["llm_provider"] == "mock"

    @patch("tradingagents.graph.setup.StateGraph")
    @patch("tradingagents.graph.setup.create_market_analyst")
    @patch("tradingagents.graph.setup.create_msg_delete")
    @patch("tradingagents.graph.setup.create_bull_researcher")
    @patch("tradingagents.graph.setup.create_bear_researcher")
    @patch("tradingagents.graph.setup.create_research_manager")
    @patch("tradingagents.graph.setup.create_trader")
    @patch("tradingagents.graph.setup.create_risky_debator")
    @patch("tradingagents.graph.setup.create_neutral_debator")
    @patch("tradingagents.graph.setup.create_safe_debator")
    @patch("tradingagents.graph.setup.create_risk_manager")
    def test_setup_graph_creates_workflow(
        self,
        mock_risk_manager,
        mock_safe_debator,
        mock_neutral_debator,
        mock_risky_debator,
        mock_trader,
        mock_research_manager,
        mock_bear_researcher,
        mock_bull_researcher,
        mock_msg_delete,
        mock_market_analyst,
        mock_stategraph,
        mock_components,
    ):
        """setup_graph() 创建 StateGraph 并添加节点"""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.graph.setup import GraphSetup

        # Mock all analyst creation functions to return callables
        for m in [
            mock_market_analyst,
            mock_bull_researcher,
            mock_bear_researcher,
            mock_research_manager,
            mock_trader,
            mock_risky_debator,
            mock_neutral_debator,
            mock_safe_debator,
            mock_risk_manager,
        ]:
            m.return_value = MagicMock(return_value={})
        mock_msg_delete.return_value = MagicMock(return_value={})

        conditional_logic = MagicMock(spec=ConditionalLogic)
        mock_graph_instance = MagicMock()
        mock_stategraph.return_value = mock_graph_instance

        setup = GraphSetup(
            **mock_components,
            conditional_logic=conditional_logic,
            config={"hpc_loop_enabled": False, "use_aif_engine": False, "diffusion_enabled": False},
            hpc_loop_manager=None,
            aif_engine_manager=None,
            use_fusion_mode=False,
        )

        # setup_graph 返回编译后的图
        setup.setup_graph(selected_analysts=["market"])
        # 验证 StateGraph 被创建（使用 AgentState）
        mock_stategraph.assert_called_once()
        # 验证 add_node 被调用（至少 market analyst 节点）
        assert mock_graph_instance.add_node.call_count >= 1
        # 验证 compile 被调用
        mock_graph_instance.compile.assert_called_once()

    def test_setup_graph_raises_on_empty_analysts(self, mock_components):
        """空的 selected_analysts 应抛出 ValueError"""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.graph.setup import GraphSetup

        conditional_logic = MagicMock(spec=ConditionalLogic)
        setup = GraphSetup(
            **mock_components,
            conditional_logic=conditional_logic,
            config={},
            hpc_loop_manager=None,
            aif_engine_manager=None,
            use_fusion_mode=False,
        )
        with pytest.raises(ValueError, match="no analysts selected"):
            setup.setup_graph(selected_analysts=[])

    def test_create_llm_by_provider(self):
        """create_llm_by_provider 对不同 provider 返回不同 LLM 实例"""
        from tradingagents.graph.trading_graph import create_llm_by_provider

        llm = create_llm_by_provider(
            provider="openai",
            model="gpt-4",
            backend_url="https://api.openai.com/v1",
            temperature=0.7,
            max_tokens=2000,
            timeout=30,
            api_key="sk-test",
        )
        assert llm is not None

    @patch("tradingagents.graph.trading_graph.ToolNode")
    def test_create_tool_nodes(self, mock_toolnode):
        """_create_tool_nodes 返回工具节点字典"""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            # _create_tool_nodes 使用 self.toolkit（单数）来获取工具
            graph.toolkit = MagicMock()
            graph.toolkits = {
                "market": MagicMock(),
                "social": MagicMock(),
                "news": MagicMock(),
                "fundamentals": MagicMock(),
            }
            graph.finnhub_key = "test_key"
            graph.akshare_enabled = False

            tool_nodes = graph._create_tool_nodes()
            assert isinstance(tool_nodes, dict)
            assert "market" in tool_nodes
            # 验证 ToolNode 被构造了 4 次（4 个数据源）
            assert mock_toolnode.call_count == 4
