# TradingAgents/graph/propagation.py

from typing import Any

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")
from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    # ===== [PR#1-C1] 数据源预检查: 在 graph.stream() 前快速判断 =====
    def pre_check_data_sources(self, symbol: str) -> dict:
        """在 graph 执行前快速检查数据源可用性。
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: {"available": True/False, "details": {...}}
                  当 available=False 时，调用方应终止分析流程
        """
        result = {"available": False, "details": {}, "reason": ""}
        try:
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
            
            provider = OptimizedChinaDataProvider()
            
            # 尝试获取市场数据和基本面数据
            checks = {}
            try:
                market_data = provider.get_stock_data(symbol, "20200101", "20260101")
                checks["market"] = bool(market_data and market_data.strip())
            except Exception as e:
                checks["market"] = False
                logger.warning(f"⚠️ [数据源预检查] market数据获取失败: {e}")
            
            try:
                fund_data = provider.get_fundamentals_data(symbol)
                checks["fundamentals"] = bool(fund_data and fund_data.strip())
            except Exception as e:
                checks["fundamentals"] = False
                logger.warning(f"⚠️ [数据源预检查] fundamentals数据获取失败: {e}")
            
            result["details"] = checks
            available_count = sum(1 for v in checks.values() if v)
            result["available"] = available_count > 0
            
            if available_count == 0:
                result["reason"] = f"所有数据源均不可用 (market={checks.get('market')}, fundamentals={checks.get('fundamentals')})"
                logger.error(f"❌ [数据源预检查] {symbol} 所有数据源均不可用")
            else:
                logger.info(f"✅ [数据源预检查] {symbol}: {available_count}/{len(checks)} 数据源可用")
                
        except Exception as e:
            result["reason"] = f"预检查过程异常: {e}"
            logger.error(f"❌ [数据源预检查] 检查过程异常: {e}")
            
        return result

    def create_initial_state(self, company_name: str, trade_date: str, stock_code: str | None = None) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        Args:
            company_name: 公司名称（如"旗滨集团"）
            trade_date: 交易日期
            stock_code: 原始股票代码（如"601636"），用于市场类型识别
        """
        from langchain_core.messages import HumanMessage

        # 🔥 修复：创建明确的分析请求消息，而不是只传递股票代码
        # 这样可以确保所有LLM（包括DeepSeek）都能理解任务
        analysis_request = f"请对股票 {company_name} 进行全面分析，交易日期为 {trade_date}。"

        # 确定市场类型：优先使用 stock_code 判断
        market_type = "unknown"
        ticker_for_market = stock_code or company_name
        if ticker_for_market:
            try:
                from tradingagents.utils.stock_utils import StockUtils

                market_info = StockUtils.get_market_info(ticker_for_market)
                market_type = market_info.get("market_name", "unknown")
                logger.info(f"🔍 [市场识别] ticker={ticker_for_market} → market_type={market_type}")
            except Exception as e:
                logger.warning(f"⚠️ [市场识别] 识别失败: {e}")

        # 🔥 [Bug D 修复] company_of_interest 设为股票代码，确保下游 agent 能正确识别市场类型
        # 下游 agent 使用 state["company_of_interest"] 调用 StockUtils.get_market_info()，
        # 公司名称已由 analysis_request 传入 LLM，agent 内部通过 _get_company_name() 解析显示名
        effective_code = stock_code or company_name
        return {
            "messages": [HumanMessage(content=analysis_request)],
            "company_of_interest": effective_code,
            "stock_code": effective_code,
            "market_type": market_type,
            "trade_date": str(trade_date),
            "investment_debate_state": InvestDebateState({"history": "", "current_response": "", "count": 0, "debate_summary": ""}),
            "risk_debate_state": RiskDebateState(
                {
                    "history": "",
                    "current_risky_response": "",
                    "current_safe_response": "",
                    "current_neutral_response": "",
                    "count": 0,
                },
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            # 🔧 [H10 数据源全故障降级] 初始化空研究计数和数据源故障标记
            "empty_research_count": 0,
            "data_source_failure": False,
        }

    def get_graph_args(self, use_progress_callback: bool = False, timeout: int | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            use_progress_callback: If True, use 'updates' mode for node-level progress tracking.
                                  If False, use 'values' mode for complete state updates.
            timeout: Optional overall timeout (in seconds) for the graph execution.
                    当设置了此参数时，LangGraph 会在超过指定秒数后终止执行。
        """
        # 使用 'updates' 模式可以获取节点级别的更新，用于进度跟踪
        # 使用 'values' 模式可以获取完整的状态更新
        stream_mode = "updates" if use_progress_callback else "values"

        config: dict[str, Any] = {"recursion_limit": self.max_recur_limit}
        # 🐛 [P0 Fix] 传递 timeout 到 LangGraph config，防止 graph 执行因单个节点阻塞而无限挂起
        if timeout is not None:
            config["timeout"] = timeout

        return {
            "stream_mode": stream_mode,
            "config": config,
        }
