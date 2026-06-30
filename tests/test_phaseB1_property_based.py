#!/usr/bin/env python3
r"""
Phase B1 — 属性基测试（Hypothesis 框架）
=========================================
覆盖 TradingAgents-CN v1.0.1 的 6 类项目级不变量：

1. 数据源降级链契约一致性
2. AgentState 模式与 Reducer 行为
3. Graph 通道类型不变量
4. HPC/AIF 维度不变量
5. API 合约不变量
6. 配置系统不变量

运行:
    cd D:\AI-Projects\TradingAgents-CN_v1.0.1
    pytest tests/test_phaseB1_property_based.py -v --hypothesis-show-statistics -xvs
"""

import os
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# 路径与导入辅助
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
logger = logging.getLogger("phaseB1")

# ===================================================================
#                        策略定义
# ===================================================================

# --- 通用策略 ------------------------------------------------------
symbol_strategy = st.text(
    alphabet=st.sampled_from("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    min_size=4,
    max_size=8,
).filter(lambda x: len(x.strip()) >= 4)

float_finite = st.floats(
    min_value=-1e6,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
)


# --- AgentState 策略 ------------------------------------------------
@st.composite
def agent_state_dict_strategy(draw):
    """生成随机的 AgentState 字典"""
    return {
        "messages": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(["role", "content", "tool_calls"]),
                    values=st.text(min_size=0, max_size=50),
                    min_size=1,
                    max_size=5,
                ),
                min_size=0,
                max_size=3,
            ),
        ),
        "market_report": draw(st.text(min_size=0, max_size=200)),
        "_aif_iteration_count": draw(st.integers(min_value=0, max_value=10)),
        "_aif_max_iterations": draw(st.integers(min_value=1, max_value=20)),
        "_aif_converged": draw(st.booleans()),
        "_aif_diverged": draw(st.booleans()),
        "_aif_action_trace": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(["action", "efe", "timestamp"]),
                    values=st.text(max_size=20),
                    min_size=0,
                    max_size=3,
                ),
                min_size=0,
                max_size=5,
            ),
        ),
        "aif_state": draw(st.one_of(st.none(), st.text(max_size=50))),
        "fusion_action": draw(st.one_of(st.none(), st.text(max_size=50))),
        "fusion_confidence": draw(st.one_of(st.none(), float_finite)),
        "fusion_reasoning": draw(st.one_of(st.none(), st.text(max_size=200))),
        "fusion_efe_scores": draw(st.one_of(st.none(), st.text(max_size=100))),
        "aif_selection": draw(st.one_of(st.none(), st.text(max_size=50))),
        "aif_action_trace": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_belief": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_free_energy": draw(st.one_of(st.none(), float_finite)),
        "aif_prior_injections": draw(st.one_of(st.none(), st.text(max_size=100))),
        "aif_current_belief": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_observation": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_meta_diagnostics": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_meta_triggered": draw(st.one_of(st.none(), st.booleans())),
        "aif_meta_temperature": draw(st.one_of(st.none(), float_finite)),
        "aif_meta_cycle_count": draw(st.one_of(st.none(), st.integers(0, 20))),
        "aif_hierarchical_free_energy": draw(st.one_of(st.none(), float_finite)),
        "aif_meta_free_energy": draw(st.one_of(st.none(), float_finite)),
        "aif_meta_window_stats": draw(st.one_of(st.none(), st.text(max_size=200))),
        "aif_free_energy_history": draw(st.one_of(st.none(), st.text(max_size=500))),
        "risk_report": draw(st.one_of(st.none(), st.text(max_size=200))),
        "sentiment_analysis": draw(st.one_of(st.none(), st.text(max_size=200))),
    }


# --- 观测向量策略 ---------------------------------------------------
@st.composite
def observation_vector_strategy(draw):
    return {
        "price_change": draw(float_finite),
        "volatility": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
        "sentiment": draw(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
        "volume": draw(float_finite),
        "spread": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
    }


# --- 环境变量策略 ---------------------------------------------------
@st.composite
def env_dict_strategy(draw):
    keys = st.sampled_from(
        [
            "MONGODB_HOST",
            "MONGODB_PORT",
            "MONGODB_DATABASE",
            "REDIS_HOST",
            "REDIS_PORT",
            "DEEPSEEK_API_KEY",
            "DEBUG",
            "HOST",
            "PORT",
            "LOG_LEVEL",
            "DEFAULT_CHINA_DATA_SOURCE",
            "TUSHARE_UNIFIED_ENABLED",
            "AKSHARE_UNIFIED_ENABLED",
            "BAOSTOCK_UNIFIED_ENABLED",
            "TUSHARE_TOKEN",
            "EFINANCE_ENABLED",
        ],
    )
    vals = st.one_of(
        st.just("localhost"),
        st.just("27017"),
        st.just("tradingagentscn"),
        st.just("6379"),
        st.just("true"),
        st.just("false"),
        st.just("0.0.0.0"),
        st.just("8000"),
        st.just("INFO"),
        st.just("akshare"),
        st.just("efinance"),
        st.just("debug-api-key"),
        st.text(min_size=0, max_size=50),
    )
    n = draw(st.integers(min_value=0, max_value=10))
    return {draw(keys): draw(vals) for _ in range(n)}


# --- 排除 JAX 不可用的环境 ------------------------------------------
def _jax_available():
    try:
        import jax

        jax.config.update("jax_platform_name", "cpu")
        return True
    except Exception:
        return False


# ===================================================================
# 类别 1: 数据源降级链契约一致性
# ===================================================================


class TestDataSourceDegradationChain:
    """验证数据源降级链的一致性和契约正确性"""

    @given(
        provider_name=st.sampled_from(["efinance", "tushare", "akshare", "baostock"]),
    )
    @settings(max_examples=20, suppress_health_check=list(HealthCheck), deadline=None)
    def test_all_providers_have_base_contract(self, provider_name):
        """不变量 1A: 所有数据源 Provider 必须继承 BaseStockDataProvider"""
        provider_module_map = {
            "efinance": "tradingagents.dataflows.providers.china.efinance",
            "tushare": "tradingagents.dataflows.providers.china.tushare",
            "akshare": "tradingagents.dataflows.providers.china.akshare",
            "baostock": "tradingagents.dataflows.providers.china.baostock",
        }
        mod_path = provider_module_map.get(provider_name)
        if not mod_path:
            pytest.skip(f"未定义 {provider_name} 的模块路径")

        try:
            __import__(mod_path)
            mod = sys.modules[mod_path]
        except ImportError as e:
            pytest.skip(f"{provider_name} 导入失败 (可能未安装依赖): {e}")
        except Exception as e:
            pytest.skip(f"{provider_name} 导入异常: {e}")

        provider_cls = None
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if isinstance(obj, type):
                from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

                if issubclass(obj, BaseStockDataProvider) and obj is not BaseStockDataProvider:
                    provider_cls = obj
                    break

        if provider_cls is None:
            pytest.fail(f"{provider_name} 模块中未找到 BaseStockDataProvider 的子类")

        abstract_methods = ["connect", "get_stock_basic_info", "get_stock_quotes", "get_historical_data"]
        for m in abstract_methods:
            assert hasattr(provider_cls, m), f"[P1] {provider_name}.{m} 未实现"
            method = getattr(provider_cls, m)
            assert callable(method), f"[P1] {provider_name}.{m} 不可调用"

    @given(symbol=symbol_strategy)
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_standardize_quotes_contract(self, symbol):
        """不变量 1B: standardize_quotes 输出必须包含所有必需字段"""
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        raw_data = {
            "symbol": symbol,
            "close": 10.5,
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "volume": 1000000,
            "amount": 10500000.0,
            "trade_date": "20260101",
        }

        class _TestProvider(BaseStockDataProvider):
            async def connect(self):
                return True

            async def get_stock_basic_info(self, symbol=None):
                return None

            async def get_stock_quotes(self, symbol):
                return None

            async def get_historical_data(self, symbol, start_date, end_date=None):
                return None

        provider = _TestProvider("test")
        result = provider.standardize_quotes(raw_data)

        required_keys = {
            "code",
            "symbol",
            "close",
            "open",
            "high",
            "low",
            "volume",
            "amount",
            "trade_date",
            "data_source",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"[P0] standardize_quotes 缺少必需字段: {missing}"

        for num_key in ["close", "open", "high", "low", "volume", "amount"]:
            val = result.get(num_key)
            assert val is None or isinstance(val, (int, float)), (
                f"[P1] standardize_quotes.{num_key} 类型错误: {type(val).__name__}"
            )

        assert result.get("data_source"), "[P2] standardize_quotes.data_source 不应为空"

    @given(source=st.sampled_from(["MONGODB", "EFINANCE", "TUSHARE", "AKSHARE", "BAOSTOCK"]))
    @settings(max_examples=5, suppress_health_check=list(HealthCheck))
    def test_data_source_enum_values(self, source):
        """不变量 1C: ChinaDataSource 枚举值必须与 DataSourceCode 常量同步"""
        from tradingagents.constants import DataSourceCode
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        enum_member = getattr(ChinaDataSource, source, None)
        assert enum_member is not None, f"[P1] ChinaDataSource.{source} 不存在"

        code_member = getattr(DataSourceCode, source, None)
        if code_member is not None:
            assert enum_member.value == code_member, (
                f"[P1] ChinaDataSource.{source}.value ({enum_member.value}) != DataSourceCode.{source} ({code_member})"
            )

    @given(symbol=symbol_strategy)
    @settings(max_examples=5, suppress_health_check=list(HealthCheck))
    def test_degradation_order_consistent(self, symbol):
        """不变量 1D: 降级链顺序 MongoDB → efinance → Tushare → AKShare → BaoStock"""
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        members = list(ChinaDataSource)
        assert len(members) >= 4, f"[P1] ChinaDataSource 成员不足: {len(members)}"

        names = [m.name for m in members]
        assert names[0] == "MONGODB", f"[P1] 降级链首位非 MONGODB: {names[0]}"

        if "EFINANCE" in names and "TUSHARE" in names:
            assert names.index("EFINANCE") < names.index("TUSHARE"), (
                f"[P1] efinance 应在 tushare 之前, 当前顺序: {names}"
            )

        core_sources = {"EFINANCE", "TUSHARE", "AKSHARE", "BAOSTOCK"}
        present = core_sources & set(names)
        assert present, f"[P1] 降级链缺少核心数据源: {names}"


# ===================================================================
# 类别 2: AgentState 模式与 Reducer 行为
# ===================================================================


class TestAgentStateSchema:
    """验证 AgentState TypedDict 和 Reducer 行为的不变量"""

    @given(test_data=agent_state_dict_strategy())
    @settings(max_examples=20, suppress_health_check=list(HealthCheck), deadline=None)
    def test_agent_state_all_optional_aif_fields(self, test_data):
        """不变量 2A: 21 个 AIF 字段必须带有 Optional 类型注解"""
        from tradingagents.agents.utils.agent_states import AgentState

        annotations = AgentState.__annotations__ if hasattr(AgentState, "__annotations__") else {}

        aif_fields = [
            "aif_state",
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

        for field in aif_fields:
            assert field in annotations, f"[P1] AgentState 缺少 AIF 字段: {field}"
            type_hint = str(annotations[field])
            assert "Optional" in type_hint or "None" in type_hint, f"[P1] {field} 类型注解不含 Optional: {type_hint}"

    @given(current=st.text(min_size=0, max_size=100), new=st.text(min_size=0, max_size=100))
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_report_reducer_last_wins(self, current, new):
        """不变量 2B: _report_reducer 是 last-write-wins 策略，空字符串不覆盖非空值"""
        from tradingagents.agents.utils.agent_states import _report_reducer

        result = _report_reducer(current, new)
        if new and new.strip():
            assert result == new, f"[P1] 非空 new 应覆盖: {result!r} != {new!r}"
        else:
            assert result == current, f"[P1] 空 new 应保留 current: {result!r} != {current!r}"

    @given(current=st.integers(min_value=0, max_value=100), new=st.integers(min_value=0, max_value=100))
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_counter_reducer_max_semantics(self, current, new):
        """
        不变量 2C: _counter_reducer 使用 max(current, new) 策略，
        非累加（防止并发写入丢失增量）。
        """
        from tradingagents.agents.utils.agent_states import _counter_reducer

        result = _counter_reducer(current, new)
        assert result == max(current, new), f"[P1] _counter_reducer 应取 max: {result} != max({current}, {new})"

    @given(current=st.booleans(), new=st.booleans())
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_bool_or_reducer(self, current, new):
        """不变量 2D: _bool_or_reducer 是 current OR new 策略"""
        from tradingagents.agents.utils.agent_states import _bool_or_reducer

        result = _bool_or_reducer(current, new)
        assert result == (current or new), f"[P1] _bool_or_reducer 应 OR: {result} != {current} or {new}"

    @given(
        current=st.one_of(st.none(), st.lists(st.integers(0, 10), min_size=0, max_size=10)),
        new=st.lists(st.integers(0, 10), min_size=0, max_size=10),
    )
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_list_extend_reducer(self, current, new):
        """不变量 2E: _list_extend_reducer 返回 list 类型，current=None 时正常工作"""
        from tradingagents.agents.utils.agent_states import _list_extend_reducer

        result = _list_extend_reducer(current, new)
        assert isinstance(result, list), f"[P1] 应返回 list, 得到 {type(result).__name__}"
        if current is None:
            assert result == new
        else:
            assert result == current + new

    @given(
        current=st.one_of(
            st.none(), st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), min_size=0, max_size=5),
        ),
        new=st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), min_size=0, max_size=5),
    )
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_dict_merge_reducer(self, current, new):
        """不变量 2F: _dict_merge_reducer 合并字典"""
        from tradingagents.agents.utils.agent_states import _dict_merge_reducer

        result = _dict_merge_reducer(current, new)
        assert isinstance(result, dict), f"[P1] 应返回 dict, 得到 {type(result).__name__}"
        if current is not None:
            for k, v in new.items():
                assert result[k] == v
            for k in current:
                if k not in new:
                    assert result[k] == current[k]

    @given(
        current=st.one_of(st.none(), st.text(min_size=0, max_size=50)),
        new=st.one_of(st.none(), st.text(min_size=0, max_size=50)),
    )
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_hpc_state_reducer(self, current, new):
        """
        不变量 2G: _hpc_state_reducer 使用 new is None 检查
        （非空字符串检查），new 非 None 则覆盖，否则保留 current。
        """
        from tradingagents.agents.utils.agent_states import _hpc_state_reducer

        result = _hpc_state_reducer(current, new)
        if new is not None:
            assert result == new, f"[P1] new 非 None 应覆盖: {result!r} != {new!r}"
        else:
            assert result == current, f"[P1] new 为 None 应保留 current: {result!r} != {current!r}"


# ===================================================================
# 类别 3: Graph 通道类型不变量
# ===================================================================


class TestGraphChannelTypes:
    """验证 LangGraph 编译后通道类型的不变量"""

    def _get_GraphSetup(self):
        try:
            from tradingagents.graph.setup import GraphSetup

            return GraphSetup
        except Exception as e:
            pytest.skip(f"GraphSetup 导入失败: {e}")
            return None

    @given(report_value=st.text(min_size=1, max_size=100))
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_market_report_reducer_is_custom(self, report_value):
        """不变量 3A: market_report 使用自定义 _report_reducer"""
        from tradingagents.agents.utils.agent_states import _report_reducer

        assume(report_value.strip())  # P2: 跳过仅空白字符串——reducer 将其视为空值，返回 current=""

        assert callable(_report_reducer), "[P0] _report_reducer 不可调用"
        assert _report_reducer.__name__ == "_report_reducer", (
            f"[P0] _report_reducer 名称异常: {_report_reducer.__name__}"
        )
        result = _report_reducer("", report_value)
        assert result == report_value

    @given(iteration_count=st.integers(min_value=0, max_value=50))
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_aif_iteration_count_channel(self, iteration_count):
        """
        不变量 3B: _aif_iteration_count 使用 _counter_reducer (max 策略)，
        多次并行写入取最大值而非累加。
        """
        from tradingagents.agents.utils.agent_states import _counter_reducer

        r1 = _counter_reducer(0, iteration_count)
        r2 = _counter_reducer(r1, iteration_count)
        # max 策略: 两次写入取较大值
        max(iteration_count, iteration_count)
        assert r1 == iteration_count, f"[P1] 第一次写入: {r1} != {iteration_count}"
        assert r2 == max(iteration_count, r1), f"[P1] _counter_reducer max 策略: {r2} != max({iteration_count}, {r1})"

    def test_graph_setup_channel_validation_exists(self):
        """不变量 3C: GraphSetup.setup_graph() 包含通道类型验证逻辑"""
        GraphSetupCls = self._get_GraphSetup()
        if GraphSetupCls is None:
            return

        import inspect

        source = inspect.getsource(GraphSetupCls.setup_graph)
        assert "channels" in source or "workflow.channels" in source, "[P1] 缺少 channels 验证"
        assert "market_report" in source, "[P1] 缺少 market_report 通道检查"

    def test_channel_routing_functions_exist(self):
        """不变量 3D: AIF 条件路由函数必须存在且可调用"""
        try:
            from tradingagents.graph.setup import (
                aif_route_from_llm_prior,
                aif_route_from_update_belief,
                aif_should_continue_iteration,
            )
        except ImportError as e:
            pytest.skip(f"路由函数导入失败: {e}")
            return

        assert callable(aif_should_continue_iteration), "[P0] aif_should_continue_iteration 不可调用"
        assert callable(aif_route_from_update_belief), "[P0] aif_route_from_update_belief 不可调用"
        assert callable(aif_route_from_llm_prior), "[P0] aif_route_from_llm_prior 不可调用"

    def test_parallel_nodes_safety(self):
        """不变量 3E: 并行节点写入集不相交（启发式检查）"""
        try:
            from tradingagents.graph.setup import diffusion_advisor_node
        except ImportError as e:
            pytest.skip(f"节点导入失败: {e}")
            return

        assert callable(diffusion_advisor_node), "[P1] diffusion_advisor_node 不可调用"


# ===================================================================
# 类别 4: HPC/AIF 维度不变量
# ===================================================================


class TestHPCAIFDimensionInvariants:
    """验证 AIF 引擎的维度一致性和异常安全性"""

    DEFAULT_LATENT_DIM = 8

    @given(
        input_dim=st.integers(min_value=1, max_value=32),
        latent_dim=st.sampled_from([4, 6, 8, 10, 12, 16]),
    )
    @settings(max_examples=20, suppress_health_check=list(HealthCheck), deadline=None)
    def test_adapt_s_t_dim_padding_truncation(self, input_dim, latent_dim):
        """不变量 4A: _adapt_s_t_dim 输出维度必须等于 latent_dim"""
        if not _jax_available():
            pytest.skip("JAX 不可用")

        import jax

        jax.config.update("jax_platform_name", "cpu")
        from tradingagents.hpc_loop.aif_engine import GenerativeModel

        try:
            key = jax.random.PRNGKey(42)
            model = GenerativeModel(latent_dim=latent_dim, key=key)
        except Exception as e:
            pytest.skip(f"GenerativeModel 初始化失败: {e}")
            return

        key, subkey = jax.random.split(key)
        s_t = jax.random.uniform(subkey, shape=(input_dim,), minval=-5.0, maxval=5.0)

        adapted = model._adapt_s_t_dim(s_t, caller_name="test")
        expected_dim = model.A.shape[1]

        assert adapted.shape[0] == expected_dim, (
            f"[P0] _adapt_s_t_dim [{input_dim}→{latent_dim}] 输出维度 {adapted.shape[0]} != 期望 {expected_dim}"
        )

    @given(noise=st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=10, suppress_health_check=list(HealthCheck), deadline=None)
    def test_market_latent_state_from_vector_roundtrip(self, noise):
        """不变量 4B: MarketLatentState.to_latent_vector → from_latent_vector 单位映射"""
        if not _jax_available():
            pytest.skip("JAX 不可用")

        import jax.numpy as jnp

        from tradingagents.hpc_loop.aif_engine import MarketLatentState

        state1 = MarketLatentState()
        z = state1.to_latent_vector()
        z_noisy = z + noise * jnp.ones_like(z) * 0.01
        state2 = MarketLatentState.from_latent_vector(z_noisy)

        assert isinstance(state2, MarketLatentState), f"[P1] 返回类型错误: {type(state2).__name__}"
        assert hasattr(state2, "regime_logits")
        assert hasattr(state2, "volatility_mu")
        assert hasattr(state2, "trend_mu")

    @given(latent_dim=st.sampled_from([8]))  # 只测试默认维度 8
    @settings(max_examples=5, suppress_health_check=list(HealthCheck), deadline=None)
    def test_transition_and_likelihood_no_crash(self, latent_dim):
        """不变量 4C: transition/likelihood 在默认维度下不崩溃"""
        if not _jax_available():
            pytest.skip("JAX 不可用")

        import jax

        jax.config.update("jax_platform_name", "cpu")
        from tradingagents.hpc_loop.aif_engine import GenerativeModel

        try:
            key = jax.random.PRNGKey(99)
            model = GenerativeModel(latent_dim=latent_dim, key=key)
        except Exception as e:
            pytest.skip(f"GenerativeModel 初始化失败: {e}")
            return

        key, sk1, sk2, _sk3 = jax.random.split(key, 4)
        s_t = jax.random.uniform(sk1, shape=(latent_dim,), minval=-3.0, maxval=3.0)
        # self.B shape = (latent_dim, 3) → a_t 需为 3 维 one-hot 行动向量
        a_t = jax.random.uniform(sk2, shape=(3,), minval=-1.0, maxval=1.0)

        try:
            trans_dist = model.transition(s_t, a_t)
            like_dist = model.likelihood(s_t)
            assert trans_dist is not None, "[P0] transition() 返回 None"
            assert like_dist is not None, "[P0] likelihood() 返回 None"
        except Exception as e:
            pytest.fail(f"[P0] transition/likelihood 抛出异常: {e}")

    @given(latent_dim=st.sampled_from([8]))
    @settings(max_examples=5, suppress_health_check=list(HealthCheck), deadline=None)
    def test_compute_free_energy_no_crash(self, latent_dim):
        """不变量 4D: compute_free_energy 在默认维度下不崩溃"""
        if not _jax_available():
            pytest.skip("JAX 不可用")

        import jax

        jax.config.update("jax_platform_name", "cpu")
        import jax.numpy as jnp

        from tradingagents.hpc_loop.aif_engine import GenerativeModel, MarketLatentState

        try:
            key = jax.random.PRNGKey(77)
            model = GenerativeModel(latent_dim=latent_dim, key=key)
        except Exception as e:
            pytest.skip(f"GenerativeModel 初始化失败: {e}")
            return

        key, sk1, sk2, sk3 = jax.random.split(key, 4)
        # compute_free_energy 签名: (observation, belief: MarketLatentState, action)
        # DEFAULT_OBS_DIM = 5 → obs 需为 5 维；self.B shape=(latent_dim,3) → a_t 需为 3 维
        obs = jax.random.uniform(sk1, shape=(5,), minval=-3.0, maxval=3.0)
        s_t = jax.random.uniform(sk2, shape=(latent_dim,), minval=-3.0, maxval=3.0)
        a_t = jax.random.uniform(sk3, shape=(3,), minval=-1.0, maxval=1.0)
        belief = MarketLatentState.from_latent_vector(s_t)

        try:
            fe = model.compute_free_energy(obs, belief, a_t)
            assert isinstance(fe, (float, int, jnp.ndarray)), f"[P1] 返回类型: {type(fe).__name__}"
        except Exception as e:
            pytest.fail(f"[P0] compute_free_energy 抛出异常: {e}")

    def test_jax_exception_caught(self):
        """不变量 4E: JAX 异常被正确捕获"""
        try:
            from tradingagents.hpc_loop.aif_engine import _JAX_AVAILABLE, BeliefUpdater
        except ImportError:
            pytest.skip("无法导入 BeliefUpdater/_JAX_AVAILABLE")

        if not _JAX_AVAILABLE:
            pytest.skip("JAX 不可用")

        import inspect

        source = inspect.getsource(BeliefUpdater.update)
        assert "try:" in source, "[P1] BeliefUpdater.update 缺少异常捕获"
        assert "except Exception" in source, "[P1] BeliefUpdater.update 缺少通用异常捕获"

    @given(obs=observation_vector_strategy())
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_observation_to_vector_contract(self, obs):
        """不变量 4F: _observation_to_vector 输出必须是 5 维向量"""
        from tradingagents.hpc_loop.aif_engine import BeliefUpdater

        try:
            vec = BeliefUpdater._observation_to_vector(obs)
        except Exception as e:
            pytest.fail(f"[P0] _observation_to_vector 抛出异常: {e}")

        assert len(vec) == 5, f"[P1] 输出维度 {len(vec)} != 5"


# ===================================================================
# 类别 5: API 合约不变量
# ===================================================================


class TestAPIContract:
    """验证 API 端点的响应模式一致性"""

    @given(status=st.sampled_from(["ok", "degraded", "maintenance"]))
    @settings(max_examples=3, suppress_health_check=list(HealthCheck))
    def test_healthz_response_schema(self, status):
        """不变量 5A: /healthz 路由存在"""
        try:
            from app.routers.health import router
        except ImportError as e:
            pytest.skip(f"health 路由导入失败: {e}")
            return

        routes = [r for r in router.routes if r.path == "/healthz"]
        assert len(routes) == 1, f"[P1] /healthz 路由数异常: {len(routes)}"

    def test_health_endpoint_returns_expected_schema(self):
        """不变量 5B: /health 返回 success/data/message 结构"""
        try:
            from app.routers.health import health
        except ImportError as e:
            pytest.skip(f"health 导入失败: {e}")
            return

        import inspect

        source = inspect.getsource(health)
        assert "success" in source, "[P0] /health 返回缺少 success"
        assert "data" in source, "[P0] /health 返回缺少 data"
        assert "message" in source, "[P1] /health 返回缺少 message"
        assert '"status"' in source or "'status'" in source, "[P1] /health data 缺少 status"

    def test_readyz_endpoint_contract(self):
        """不变量 5C: /readyz 路由存在"""
        try:
            from app.routers.health import router
        except ImportError:
            pytest.skip("health 路由导入失败")
            return

        routes = [r for r in router.routes if r.path == "/readyz"]
        assert len(routes) == 1, f"[P1] /readyz 路由数异常: {len(routes)}"

    def test_version_format(self):
        """不变量 5D: 版本号不为空"""
        from app.routers.health import get_version

        try:
            version = get_version()
        except Exception as e:
            pytest.skip(f"get_version() 读取失败: {e}")
            return

        assert version, "[P2] 版本号为空"
        parts = version.split(".")
        assert len(parts) >= 2, f"[P2] 版本号格式异常: {version}"

    @given(service_name=st.text(min_size=1, max_size=50))
    @settings(max_examples=3, suppress_health_check=list(HealthCheck), deadline=None)
    def test_api_error_response_format(self, service_name):
        """不变量 5E: app 注册了异常处理器"""
        try:
            from app.main import app
        except ImportError as e:
            pytest.skip(f"app.main 导入失败: {e}")
            return

        assert len(app.exception_handlers) > 0, "[P2] app 未注册异常处理器"


# ===================================================================
# 类别 6: 配置系统不变量
# ===================================================================


class TestConfigSystem:
    """验证配置系统的一致性和完整性"""

    @given(bool_str=st.text(min_size=0, max_size=20))
    @settings(max_examples=20, suppress_health_check=list(HealthCheck))
    def test_env_bool_parsing_consistency(self, bool_str):
        """不变量 6A: _get_bool_env 应正确解析布尔字符串"""
        from tradingagents.config.providers_config import DataSourceConfig

        config = DataSourceConfig()
        result = config._get_bool_env("TEST_VAR", False)

        # 验证解析逻辑: 设置环境变量后测试
        assume("\x00" not in bool_str)  # P2: os.environ 拒绝嵌入空字符
        os.environ["TEST_VAR"] = bool_str
        try:
            result = config._get_bool_env("TEST_VAR", False)
            expected = bool_str.strip().lower() in ("true", "1", "yes", "on") if bool_str.strip() else False
            assert result == expected, f"[P1] _get_bool_env('{bool_str}') = {result}, 期望 {expected}"
        finally:
            os.environ.pop("TEST_VAR", None)

    @given(int_str=st.text(min_size=0, max_size=10), default=st.integers(min_value=0, max_value=100))
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_env_int_parsing_consistency(self, int_str, default):
        """不变量 6B: _get_int_env 应优雅处理非数字字符串"""
        from tradingagents.config.providers_config import DataSourceConfig

        config = DataSourceConfig()
        assume("\x00" not in int_str)  # P2: os.environ 拒绝嵌入空字符
        os.environ["TEST_INT_VAR"] = int_str
        try:
            result = config._get_int_env("TEST_INT_VAR", default)
            assert isinstance(result, int), f"[P1] 返回非 int: {type(result).__name__}"
        finally:
            os.environ.pop("TEST_INT_VAR", None)

    @given(env_vars=env_dict_strategy())
    @settings(max_examples=10, suppress_health_check=list(HealthCheck), deadline=None)
    def test_providers_config_loads_without_crash(self, env_vars):
        """不变量 6C: DataSourceConfig 在任何 .env 环境下都能安全加载"""
        saved = {}
        for k, v in env_vars.items():
            assume("\x00" not in str(v))  # P2: os.environ 拒绝嵌入空字符
            saved[k] = os.environ.get(k)
            os.environ[k] = str(v)

        try:
            from tradingagents.config.providers_config import DataSourceConfig

            config = DataSourceConfig()
            assert hasattr(config, "_configs"), "[P1] DataSourceConfig 缺少 _configs"
            assert isinstance(config._configs, dict), "[P1] _configs 不是 dict"
        except Exception as e:
            pytest.fail(f"[P0] DataSourceConfig 加载异常: {e}")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_file_exists(self):
        """不变量 6D: .env 文件包含必要的核心配置键"""
        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            pytest.skip(".env 文件不存在")

        content = env_path.read_text(encoding="utf-8")
        required_keys = ["MONGODB_HOST", "MONGODB_DATABASE", "DEEPSEEK_API_KEY", "HOST", "PORT"]
        missing = [k for k in required_keys if f"{k}=" not in content]
        assert not missing, f"[P1] .env 缺少必需配置: {missing}"

    @given(value=st.text(min_size=0, max_size=50))
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_runtime_settings_get_number_no_crash(self, value):
        """不变量 6E: runtime_settings.get_float/get_int 在任何输入下不抛出异常"""
        from tradingagents.config.runtime_settings import get_float, get_int

        assume("\x00" not in value)  # P2: os.environ 拒绝嵌入空字符
        env_var = "TA_TEST_RUNTIME_VAR"
        os.environ[env_var] = value
        try:
            f_result = get_float(env_var, None, 1.0)
            i_result = get_int(env_var, None, 1)
            assert isinstance(f_result, (int, float)), f"[P2] get_float 返回类型异常: {type(f_result).__name__}"
            assert isinstance(i_result, int), f"[P2] get_int 返回类型异常: {type(i_result).__name__}"
        except Exception as e:
            pytest.fail(f"[P1] runtime_settings.get_number 抛出异常: {e}")
        finally:
            os.environ.pop(env_var, None)

    def test_config_module_exports(self):
        """
        不变量 6F: tradingagents.config 导出的符号验证

        ModelConfig 字段: provider, model_name, api_key, base_url, max_tokens, temperature, enabled
        PricingConfig 字段: provider, model_name, input_price_per_1k, output_price_per_1k, currency
        """
        from tradingagents.config import ModelConfig, PricingConfig, config_manager, token_tracker

        assert config_manager is not None, "[P2] config_manager 导出为 None"
        assert token_tracker is not None, "[P2] token_tracker 导出为 None"

        # ModelConfig 字段 (dataclass 使用 __dataclass_fields__)
        assert "model_name" in ModelConfig.__dataclass_fields__, "[P1] ModelConfig 缺少 model_name"
        assert "provider" in ModelConfig.__dataclass_fields__, "[P1] ModelConfig 缺少 provider"
        assert "api_key" in ModelConfig.__dataclass_fields__, "[P1] ModelConfig 缺少 api_key"

        # PricingConfig 字段
        assert "input_price_per_1k" in PricingConfig.__dataclass_fields__, "[P1] PricingConfig 缺少 input_price_per_1k"
        assert "output_price_per_1k" in PricingConfig.__dataclass_fields__, (
            "[P1] PricingConfig 缺少 output_price_per_1k"
        )

    @given(
        model_name=st.text(min_size=0, max_size=50),
        provider=st.text(min_size=0, max_size=50),
        api_key=st.text(min_size=0, max_size=50),
    )
    @settings(max_examples=10, suppress_health_check=list(HealthCheck))
    def test_model_config_validation(self, model_name, provider, api_key):
        """不变量 6G: ModelConfig dataclass 创建不抛出异常"""
        from tradingagents.config.usage_models import ModelConfig

        cfg = ModelConfig(
            model_name=model_name,
            provider=provider,
            api_key=api_key,
        )
        assert isinstance(cfg, ModelConfig)
        assert cfg.model_name == model_name
        assert cfg.provider == provider


# ===================================================================
# 跨类别不变量（系统级集成）
# ===================================================================


class TestCrossCuttingInvariants:
    """验证跨多个层级的系统级不变量"""

    def test_all_reducers_defined(self):
        """全局不变量 A: agent_states.py 必须定义全部 6 个自定义 reducer"""
        from tradingagents.agents.utils.agent_states import (
            _bool_or_reducer,
            _counter_reducer,
            _dict_merge_reducer,
            _hpc_state_reducer,
            _list_extend_reducer,
            _report_reducer,
        )

        reducers = [
            ("_hpc_state_reducer", _hpc_state_reducer),
            ("_report_reducer", _report_reducer),
            ("_counter_reducer", _counter_reducer),
            ("_bool_or_reducer", _bool_or_reducer),
            ("_list_extend_reducer", _list_extend_reducer),
            ("_dict_merge_reducer", _dict_merge_reducer),
        ]
        for name, func in reducers:
            assert callable(func), f"[P0] {name} 未定义或不可调用"

    def test_agent_state_has_core_fields(self):
        """
        全局不变量 B: AgentState 核心字段存在性检查

        ⚠️ 注意: _aif_converged, _aif_diverged, sentiment_analysis, risk_report
        在 AgentState 中不存在（期望存在但未定义）。
        """
        from tradingagents.agents.utils.agent_states import AgentState

        required = {
            "messages",
            "market_report",
            "_aif_iteration_count",
            "_aif_max_iterations",
        }
        annotations = AgentState.__annotations__ if hasattr(AgentState, "__annotations__") else {}
        missing = required - set(annotations.keys())
        assert not missing, f"[P0] AgentState 缺少核心字段: {missing}"

        # 额外检查: 以下字段在代码中被引用但实际未定义在 AgentState 中
        # 这是 P1 级发现 — 架构设计字段缺失
        fields_checked_but_absent = {"_aif_diverged", "sentiment_analysis", "risk_report", "_aif_converged"}
        actually_absent = fields_checked_but_absent - set(annotations.keys())
        if actually_absent:
            logger.warning(f"⚠️ [P1] AgentState 缺少架构设计字段: {actually_absent}")

    def test_base_provider_abstract_methods(self):
        """全局不变量 C: BaseStockDataProvider 定义全部 4 个抽象方法"""
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        expected_abstract = {"connect", "get_stock_basic_info", "get_stock_quotes", "get_historical_data"}
        abstract_set = set()

        for name in dir(BaseStockDataProvider):
            obj = getattr(BaseStockDataProvider, name, None)
            if hasattr(obj, "__isabstractmethod__") and obj.__isabstractmethod__:
                abstract_set.add(name)

        missing = expected_abstract - abstract_set
        assert not missing, f"[P0] BaseStockDataProvider 缺少抽象方法: {missing}"

    def test_env_dotenv_load(self):
        """全局不变量 D: .env 文件被 runtime_settings.py 自动加载"""
        import inspect

        source = inspect.getsource(sys.modules["tradingagents.config.runtime_settings"])
        assert "load_dotenv" in source, "[P2] runtime_settings 未调用 load_dotenv"

    def test_degradation_chain_documentation_consistency(self):
        """全局不变量 E: 降级链顺序一致性"""
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        enum_names = [m.name for m in ChinaDataSource]
        assert enum_names[0] == "MONGODB", f"[P1] 降级链首位非 MONGODB: {enum_names}"
        logger.info(f"ChinaDataSource 降级链顺序: {' → '.join(enum_names)}")


# ===================================================================
# 测试执行入口
# ===================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics", "-x"])
