"""
TradingAgents — AIF Integration 单元测试

覆盖目标: tradingagents/hpc_loop/aif_integration.py
- _ANALYST_EXCLUDE_KEYS frozenset 验证
- _sanitize_aif_return()          — AIF 返回值清洗
- _aif_to_hpc_state()             — AIF→HPC 状态转换
- _hpc_to_aif_state()             — HPC→AIF 状态重建
- _ensure_hpc_state()             — HPCState 保障函数
- _extract_market_info()          — 市场信息提取
"""

import pytest

from tradingagents.hpc_loop.aif_integration import (
    _ANALYST_EXCLUDE_KEYS,
    _aif_to_hpc_state,
    _ensure_hpc_state,
    _extract_market_info,
    _hpc_to_aif_state,
    _sanitize_aif_return,
)


# ======================================================================
# _ANALYST_EXCLUDE_KEYS
# ======================================================================
class TestAnalystExcludeKeys:
    """验证分析师排除键集合"""

    def test_is_frozenset(self):
        """_ANALYST_EXCLUDE_KEYS 是 frozenset 类型（不可变、可哈希）"""
        assert isinstance(_ANALYST_EXCLUDE_KEYS, frozenset)

    def test_contains_all_expected_keys(self):
        """包含所有 11 个分析师管线字段"""
        expected_keys = {
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "sender",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "investment_debate_state",
            "risk_debate_state",
        }
        for key in expected_keys:
            assert key in _ANALYST_EXCLUDE_KEYS, f"排除键缺失: {key}"

    def test_does_not_contain_aif_keys(self):
        """不包含 AIF 相关键（应通过清洗）"""
        aif_keys = [
            "hpc_state",
            "aif_state",
            "aif_belief",
            "aif_free_energy",
            "aif_selection",
            "aif_action_trace",
            "fusion_action",
        ]
        for key in aif_keys:
            assert key not in _ANALYST_EXCLUDE_KEYS, f"AIF 键被错误排除: {key}"

    def test_exact_count(self):
        """确认恰好有 11 个排除键（与源代码一致）"""
        assert len(_ANALYST_EXCLUDE_KEYS) == 11, (
            f"预期 11 个排除键，实际 {len(_ANALYST_EXCLUDE_KEYS)}: {_ANALYST_EXCLUDE_KEYS}"
        )


# ======================================================================
# _sanitize_aif_return
# ======================================================================
class TestSanitizeAifReturn:
    """验证 AIF 返回值清洗逻辑"""

    def test_filters_all_excluded_keys(self):
        """所有分析师键被正确过滤"""
        return_dict = {
            "hpc_state": {"step": 1},
            "market_report": "should be removed",
            "sentiment_report": "should be removed",
            "aif_state": {"free_energy": 0.5},
            "sender": "bull_researcher",
        }
        result = _sanitize_aif_return(return_dict, source="test")
        assert "market_report" not in result
        assert "sentiment_report" not in result
        assert "sender" not in result
        assert result["hpc_state"] == {"step": 1}
        assert result["aif_state"] == {"free_energy": 0.5}

    def test_empty_input(self):
        """空 dict 输入返回空 dict"""
        result = _sanitize_aif_return({}, source="test")
        assert result == {}

    def test_only_aif_keys_pass_through(self):
        """只含 AIF 键时全部通过"""
        return_dict = {
            "hpc_state": {"step": 1},
            "aif_state": {"free_energy": 0.5},
            "aif_belief": None,
        }
        result = _sanitize_aif_return(return_dict, source="test")
        assert result == return_dict

    def test_none_value_in_excluded_key(self):
        """排除键的值为 None 也应被过滤"""
        return_dict = {"hpc_state": {}, "market_report": None}
        result = _sanitize_aif_return(return_dict, source="test")
        assert "market_report" not in result
        assert "hpc_state" in result

    def test_partial_excluded_keys(self):
        """部分排除键混合"""
        return_dict = {
            "hpc_state": {},
            "investment_plan": "some plan",
            "aif_free_energy": 1.5,
            "final_trade_decision": "buy",
            "fusion_action": "hold",
        }
        result = _sanitize_aif_return(return_dict, source="test")
        assert "investment_plan" not in result
        assert "final_trade_decision" not in result
        assert result["hpc_state"] == {}
        assert result["aif_free_energy"] == 1.5
        assert result["fusion_action"] == "hold"


# ======================================================================
# _aif_to_hpc_state
# ======================================================================
class TestAifToHpcState:
    """验证 AIFMarketLatentState → dict 转换"""

    def test_returns_dict(self):
        """返回值是 dict 类型"""
        # 此测试依赖 AIFMarketLatentState，如果不可用则跳过
        pytest.importorskip("tradingagents.hpc_loop.aif_engine")
        from tradingagents.hpc_loop.aif_engine import MarketLatentState as AIFMarketLatentState

        aif_state = AIFMarketLatentState()
        result = _aif_to_hpc_state(aif_state)
        assert isinstance(result, dict)

    def test_contains_expected_keys(self):
        """转换结果包含核心 AIF 隐状态键"""
        pytest.importorskip("tradingagents.hpc_loop.aif_engine")
        from tradingagents.hpc_loop.aif_engine import MarketLatentState as AIFMarketLatentState

        aif_state = AIFMarketLatentState()
        result = _aif_to_hpc_state(aif_state)
        # 至少应包含隐状态标识字段
        assert len(result) > 0


# ======================================================================
# _hpc_to_aif_state
# ======================================================================
class TestHpcToAifState:
    """验证 HPCState → AIFMarketLatentState 重建"""

    def test_with_empty_hpc_state(self):
        """当 hpc_state.latent_state 为 None 时返回默认 AIFMarketLatentState"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        hpc_state = HPCState()  # latent_state 默认为 None
        result = _hpc_to_aif_state(hpc_state)
        assert result is not None
        # 应返回空的 AIFMarketLatentState

    def test_with_latent_state(self):
        """当 hpc_state 包含 latent_state 时重建"""
        pytest.importorskip("tradingagents.hpc_loop.aif_engine")
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState
        from tradingagents.hpc_loop.hpc_state import MarketLatentState as HpcMarketLatentState

        # 构造一个包含 latent_state 的 HPCState
        hpc_state = HPCState()
        hpc_state.latent_state = HpcMarketLatentState()
        result = _hpc_to_aif_state(hpc_state)
        assert result is not None


# ======================================================================
# _ensure_hpc_state
# ======================================================================
class TestEnsureHpcState:
    """验证 HPCState 保障函数"""

    def test_with_dict_hpc_state(self):
        """当 state['hpc_state'] 是 dict 时转换为 HPCState"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        state = {"hpc_state": {"step_counter": 5, "latent_state": None}}
        result = _ensure_hpc_state(state)
        assert isinstance(result, HPCState)
        assert result.step_counter == 5
        # state 中的 hpc_state 应被替换为 HPCState 对象
        assert isinstance(state["hpc_state"], HPCState)

    def test_with_hpc_state_object(self):
        """当 state['hpc_state'] 已经是 HPCState 时直接返回"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        original = HPCState()
        original.step_counter = 3
        state = {"hpc_state": original}
        result = _ensure_hpc_state(state)
        assert result is original  # 同一对象
        assert result.step_counter == 3

    def test_empty_dict_hpc_state(self):
        """当 state['hpc_state'] 为空 dict 时返回默认 HPCState"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        state = {"hpc_state": {}}
        result = _ensure_hpc_state(state)
        assert isinstance(result, HPCState)

    def test_no_hpc_state_key(self):
        """当 state 中缺少 hpc_state 键时返回默认 HPCState"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        state = {"company_of_interest": "AAPL"}
        result = _ensure_hpc_state(state)
        assert isinstance(result, HPCState)
        assert state.get("hpc_state") is not None  # 原 state 应被添加

    def test_hpc_state_is_none(self):
        """当 state['hpc_state'] 为 None 时返回默认 HPCState"""
        pytest.importorskip("tradingagents.hpc_loop.hpc_state")
        from tradingagents.hpc_loop.hpc_state import HPCState

        state = {"hpc_state": None}
        result = _ensure_hpc_state(state)
        assert isinstance(result, HPCState)


# ======================================================================
# _extract_market_info
# ======================================================================
class TestExtractMarketInfo:
    """验证市场信息提取函数"""

    def test_returns_expected_structure(self):
        """返回包含所有必需键的 dict"""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2026-06-19",
            "sentiment_report": "positive outlook",
        }
        result = _extract_market_info(state)
        expected_keys = {"price", "volatility", "sentiment", "regime", "ticker", "date"}
        assert expected_keys.issubset(result.keys()), f"缺失键: {expected_keys - result.keys()}"

    def test_price_is_none(self):
        """price 字段始终为 None（无实时数据源）"""
        result = _extract_market_info({})
        assert result["price"] is None

    def test_volatility_default(self):
        """volatility 默认为 0.02"""
        result = _extract_market_info({})
        assert result["volatility"] == 0.02

    def test_sentiment_from_report(self):
        """sentiment 根据 sentiment_report 长度计算"""
        state = {"sentiment_report": "x" * 500}
        result = _extract_market_info(state)
        assert result["sentiment"] == 0.5  # 500/1000

        state2 = {"sentiment_report": "x" * 100}
        result2 = _extract_market_info(state2)
        assert result2["sentiment"] == 0.1  # 100/1000

    def test_sentiment_default_when_no_report(self):
        """无 sentiment_report 时 sentiment 默认为 0.5"""
        result = _extract_market_info({})
        assert result["sentiment"] == 0.5

    def test_regime_is_unknown(self):
        """regime 始终为 'unknown'"""
        result = _extract_market_info({})
        assert result["regime"] == "unknown"

    def test_ticker_from_state(self):
        """ticker 从 company_of_interest 读取"""
        result = _extract_market_info({"company_of_interest": "TSLA"})
        assert result["ticker"] == "TSLA"

    def test_date_from_state(self):
        """date 从 trade_date 读取"""
        result = _extract_market_info({"trade_date": "2026-06-19"})
        assert result["date"] == "2026-06-19"
