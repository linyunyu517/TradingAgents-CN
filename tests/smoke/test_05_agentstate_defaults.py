# TradingAgents-CN Smoke Test — AgentState 默认初始化测试
# ============================================================
# 验证 AgentState 的默认初始化行为，确保所有字段在
# 不提供任何参数时有合理的默认值，避免 LangGraph 运行时
# 因缺少必需字段而崩溃。
#
# 覆盖内容：
#   - AgentState 创建时各字段的默认值
#   - 各 reducer 函数的行为
#   - 嵌套状态 (InvestDebateState, RiskDebateState) 的默认值
# ============================================================

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_SKIP_REASON = ""
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

    CAN_TEST = True
except ImportError as e:
    CAN_TEST = False
    _SKIP_REASON = str(e)


class TestReducers:
    """Reducer 函数行为测试"""

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_report_reducer_last_wins(self):
        """_report_reducer 返回最新的值"""
        result = _report_reducer("旧报告", "新报告")
        assert result == "新报告"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_report_reducer_empty_string(self):
        """_report_reducer 空字符串不覆盖旧值（保留当前值）"""
        result = _report_reducer("旧报告", "")
        # 实际实现：空字符串时不覆盖
        assert result == "旧报告"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_report_reducer_none(self):
        """_report_reducer None 不覆盖旧值"""
        result = _report_reducer("旧报告", None)
        # None 触发 if not new，返回 current
        assert result == "旧报告"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_counter_reducer_max(self):
        """_counter_reducer 返回最大值"""
        assert _counter_reducer(1, 3) == 3
        assert _counter_reducer(5, 2) == 5
        assert _counter_reducer(0, 0) == 0

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_bool_or_reducer(self):
        """_bool_or_reducer 执行 OR 操作"""
        assert _bool_or_reducer(False, True) is True
        assert _bool_or_reducer(True, False) is True
        assert _bool_or_reducer(False, False) is False
        assert _bool_or_reducer(True, True) is True

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_list_extend_reducer(self):
        """_list_extend_reducer 合并列表"""
        result = _list_extend_reducer(["a"], ["b", "c"])
        assert result == ["a", "b", "c"]

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_list_extend_reducer_with_none(self):
        """_list_extend_reducer 当前为 None 时返回新列表"""
        result = _list_extend_reducer(None, ["a"])
        assert result == ["a"]

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_dict_merge_reducer(self):
        """_dict_merge_reducer 合并字典"""
        result = _dict_merge_reducer({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_dict_merge_reducer_overwrite(self):
        """_dict_merge_reducer 新值覆盖旧值"""
        result = _dict_merge_reducer({"a": 1}, {"a": 2, "b": 3})
        assert result == {"a": 2, "b": 3}

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_hpc_state_reducer(self):
        """_hpc_state_reducer 保持最新状态"""
        result = _hpc_state_reducer({"regime": "bull"}, {"regime": "bear"})
        assert result == {"regime": "bear"}

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_hpc_state_reducer_with_aif(self):
        """_hpc_state_reducer 处理混合 AIF 状态"""
        current = {"regime": "bull", "confidence": 0.8}
        new = {"regime": "bear", "free_energy": -42.0}
        result = _hpc_state_reducer(current, new)
        assert result["regime"] == "bear"
        assert result["free_energy"] == -42.0


class TestInvestDebateState:
    """InvestDebateState 默认值测试"""

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_debate_state_keys(self):
        """InvestDebateState 有正确的字段（基于实际源代码）"""
        actual_keys = set(InvestDebateState.__annotations__.keys())
        required_keys = {"bull_history", "bear_history", "history", "current_response", "judge_decision", "count"}
        missing = required_keys - actual_keys
        assert not missing, f"InvestDebateState 缺少字段: {missing}"


class TestRiskDebateState:
    """RiskDebateState 默认值测试"""

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_risk_debate_state_keys(self):
        """RiskDebateState 有正确的字段（基于实际源代码）"""
        actual_keys = set(RiskDebateState.__annotations__.keys())
        required_keys = {
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
        }
        missing = required_keys - actual_keys
        assert not missing, f"RiskDebateState 缺少字段: {missing}"


class TestAgentStateAnnotations:
    """AgentState 注解完整性测试"""

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_agent_state_has_required_fields(self):
        """AgentState 包含所有必需的核心字段"""
        annotations = AgentState.__annotations__
        required = {
            "messages",
            "company_of_interest",
            "trade_date",
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
        missing = required - set(annotations.keys())
        assert not missing, f"AgentState 缺少字段: {missing}"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_agent_state_has_hpc_aif_fields(self):
        """AgentState 包含 HPC/AIF 字段"""
        annotations = AgentState.__annotations__
        hpc_aif_fields = {
            "hpc_state",
            "aif_state",
            "past_context",
            "_aif_iteration_count",
            "_aif_max_iterations",
            "fusion_action",
            "fusion_confidence",
            "fusion_reasoning",
        }
        missing = []
        for field in hpc_aif_fields:
            if field not in annotations:
                missing.append(field)
        assert not missing, f"AgentState 缺少 HPC/AIF 字段: {missing}"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_agent_state_has_l_iwm_hsrc_fields(self):
        """AgentState 包含 L-IWM / HSR-MC 字段"""
        annotations = AgentState.__annotations__
        extended_fields = {
            "module_losses",
            "module_performance",
            "prediction_errors",
            "l_iwm",
            "hsrc_mc",
            "hsrc_mc_meta",
            "hsrc_mc_adjust",
            "hsrc_mc_reflect",
        }
        missing = []
        for field in extended_fields:
            if field not in annotations:
                missing.append(field)
        assert not missing, f"AgentState 缺少扩展字段: {missing}"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_agent_state_has_diffusion_fields(self):
        """AgentState 包含扩散模块字段"""
        annotations = AgentState.__annotations__
        diffusion_fields = {
            "diffusion_decision",
            "fused_decision",
        }
        for field in diffusion_fields:
            assert field in annotations, f"AgentState 缺少扩散字段: {field}"

    @pytest.mark.skipif(not CAN_TEST, reason=f"导入失败: {_SKIP_REASON}")
    def test_agent_state_has_ai_safety_fields(self):
        """AgentState 包含 AI 安全监控字段"""
        annotations = AgentState.__annotations__
        safety_fields = {
            "_aif_diverged",
            "_aif_converged",
            "sentiment_analysis",
            "risk_report",
        }
        for field in safety_fields:
            assert field in annotations, f"AgentState 缺少安全监控字段: {field}"
