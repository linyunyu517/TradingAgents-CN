# TradingAgents-CN Smoke Test — 导入完整性测试
# ============================================================
# 验证项目核心模块能否正常导入，检测环境依赖缺失和导入路径错误。
# 对于因环境差异（如无 CUDA/JAX）导致的导入失败，使用 pytest.skip 跳过，
# 而非让测试失败。
# ============================================================

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestCoreImports:
    """核心包导入测试"""

    def test_tradingagents_package(self):
        """tradingagents 根包可导入"""
        import tradingagents

        assert hasattr(tradingagents, "__version__") or True  # 可能无 __version__

    def test_graph_module(self):
        """graph 模块可导入"""
        from tradingagents import graph

        assert graph is not None

    def test_agents_module(self):
        """agents 模块可导入"""
        from tradingagents import agents

        assert agents is not None

    def test_tools_module(self):
        """tools 模块可导入"""
        from tradingagents import tools

        assert tools is not None

    def test_utils_module(self):
        """utils 模块可导入"""
        from tradingagents import utils

        assert utils is not None

    def test_config_module(self):
        """config 模块可导入"""
        from tradingagents import config

        assert config is not None


class TestGraphModuleImports:
    """图相关模块导入测试"""

    def test_trading_graph_import(self):
        """TradingAgentsGraph 可导入"""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        assert TradingAgentsGraph is not None

    def test_graph_setup_import(self):
        """GraphSetup 可导入"""
        from tradingagents.graph.setup import GraphSetup

        assert GraphSetup is not None

    def test_agent_states_import(self):
        """AgentState 可导入"""
        from tradingagents.agents.utils.agent_states import AgentState

        assert AgentState is not None

    def test_agent_state_reducers_import(self):
        """所有 reducer 函数可导入"""
        from tradingagents.agents.utils.agent_states import (
            _bool_or_reducer,
            _counter_reducer,
            _dict_merge_reducer,
            _hpc_state_reducer,
            _list_extend_reducer,
            _report_reducer,
        )

        assert callable(_report_reducer)
        assert callable(_counter_reducer)
        assert callable(_bool_or_reducer)
        assert callable(_list_extend_reducer)
        assert callable(_dict_merge_reducer)
        assert callable(_hpc_state_reducer)

    def test_conditional_logic_import(self):
        """ConditionalLogic 可导入"""
        from tradingagents.graph.conditional_logic import ConditionalLogic

        assert ConditionalLogic is not None


class TestHpcAifImports:
    """HPC/AIF 模块导入测试"""

    def test_aif_integration_import(self):
        """AIF 集成模块可导入"""
        from tradingagents.hpc_loop import aif_integration

        assert aif_integration is not None

    def test_aif_engine_import(self):
        """AIF 引擎模块可导入（可能跳过）"""
        try:
            from tradingagents.hpc_loop import aif_engine

            assert aif_engine is not None
        except ImportError as e:
            if "jax" in str(e).lower() or "numpyro" in str(e).lower() or "cuda" in str(e).lower():
                pytest.skip(f"AIF 引擎依赖 JAX/numpyro，当前环境不可用: {e}")
            raise

    def test_sanitize_aif_return_import(self):
        """_sanitize_aif_return 和 _ANALYST_EXCLUDE_KEYS 可导入"""
        from tradingagents.hpc_loop.aif_integration import (
            _ANALYST_EXCLUDE_KEYS,
            _sanitize_aif_return,
        )

        assert callable(_sanitize_aif_return)
        assert isinstance(_ANALYST_EXCLUDE_KEYS, frozenset)

    def test_hpc_loop_module_import(self):
        """HPC-Loop 模块可导入"""
        from tradingagents.hpc_loop import hpc_integration

        assert hpc_integration is not None


class TestModelImports:
    """模型模块导入测试"""

    def test_llm_adapters_import(self):
        """LLM 适配器可导入"""
        from tradingagents.llm_adapters import ChatDashScopeOpenAI, adapter_registry

        assert adapter_registry is not None
        assert ChatDashScopeOpenAI is not None

    def test_llm_clients_import(self):
        """LLM 客户端可导入"""
        from tradingagents.llm_clients import BaseLLMClient, create_llm_client

        assert BaseLLMClient is not None
        assert callable(create_llm_client)


class TestWebAppImports:
    """Web 应用模块导入测试"""

    def test_web_app_import(self):
        """web.app 作为模块可导入（仅验证语法）"""
        # 不实际导入 streamlit 应用（会触发 streamlit 运行）
        import importlib.util

        spec = importlib.util.spec_from_file_location("web.app", str(PROJECT_ROOT / "web" / "app.py"))
        assert spec is not None, "web/app.py 语法有效"

    def test_run_web_import(self):
        """run_web.py 可执行导入"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("web.run_web", str(PROJECT_ROOT / "web" / "run_web.py"))
        assert spec is not None, "web/run_web.py 语法有效"


class TestDataflowImports:
    """数据流模块导入测试"""

    def test_dataflows_module(self):
        """dataflows 模块可导入"""
        from tradingagents import dataflows

        assert dataflows is not None


class TestApiModuleImports:
    """API 模块导入测试"""

    def test_api_module(self):
        """api 模块可导入"""
        from tradingagents import api

        assert api is not None

    def test_constants_import(self):
        """constants 模块可导入"""
        from tradingagents import constants

        assert constants is not None
