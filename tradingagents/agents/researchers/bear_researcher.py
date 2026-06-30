# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")
# 🛡️ [H14 集中化防御] 导入安全 LLM 调用包装器和公共工具函数
from tradingagents.agents.utils.agent_utils import safe_extract_content, safe_llm_invoke

# 🧠 [渐进辩论摘要] 导入关键点提取工具
from tradingagents.agents.utils.debate_utils import extract_debate_key_points, merge_key_points


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        # 🔧 [H10 数据源全故障降级] 如果 Bull Researcher 已检测到数据源故障，直接跳过
        if state.get("data_source_failure", False):
            empty_count = state.get("empty_research_count", 0) + 1
            logger.warning(
                f"🔧 [H10 数据源全故障降级] 空头研究员检测到 data_source_failure=True，"
                f"跳过 LLM 调用 (empty_research_count={empty_count})",
            )
            investment_debate_state = state["investment_debate_state"]
            placeholder = "⚠️ 数据源不可用：所有外部数据源均无法获取数据。当前仅能基于股票基本信息进行分析。"
            new_count = investment_debate_state["count"] + 1
            new_investment_debate_state = {
                "history": investment_debate_state.get("history", "") + "\n" + f"Bear Analyst: {placeholder}",
                "bear_history": investment_debate_state.get("bear_history", "") + "\n" + f"Bear Analyst: {placeholder}",
                "bull_history": investment_debate_state.get("bull_history", ""),
                "current_response": placeholder,
                "count": new_count,
            }
            return {
                "investment_debate_state": new_investment_debate_state,
                "empty_research_count": empty_count,
            }

        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # 使用统一的股票类型检测
        ticker = state.get("company_of_interest", "Unknown")
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(ticker)
        market_info["is_china"]

        # 获取公司名称
        from tradingagents.agents.utils.company_name_resolver import get_company_name

        company_name = get_company_name(ticker, market_info, "空头研究员")
        market_info["is_hk"]
        market_info["is_us"]

        currency = market_info["currency_name"]
        currency_symbol = market_info["currency_symbol"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # [FIX] 2026-06-18: Fix 2.6 - 检查报告是否全部为空，避免零输出
        _all_reports_empty = all(
            not r or not r.strip() for r in [market_research_report, sentiment_report, news_report, fundamentals_report]
        )
        if _all_reports_empty:
            logger.warning("🔧 [Fix 2.6] 空头研究员: 所有报告均为空，使用占位文本继续分析")
            # 设置最低限度的占位内容，确保 prompt 有实质输入
            market_research_report = "（当前无市场研究报告数据）"
            sentiment_report = "（当前无情绪分析数据）"
            news_report = "（当前无新闻数据）"
            fundamentals_report = "（当前无基本面数据）"
            curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning("⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        for _i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""你是一位看跌分析师，负责论证不投资股票 {company_name}（股票代码：{ticker}）的理由。

⚠️ 重要提醒：当前分析的是 {market_info["market_name"]}，所有价格和估值请使用 {currency}（{currency_symbol}）作为单位。
⚠️ 在你的分析中，请始终使用公司名称"{company_name}"而不是股票代码"{ticker}"来称呼这家公司。

你的目标是提出合理的论证，强调风险、挑战和负面指标。利用提供的研究和数据来突出潜在的不利因素并有效反驳看涨论点。

请用中文回答，重点关注以下几个方面：

- 风险和挑战：突出市场饱和、财务不稳定或宏观经济威胁等可能阻碍股票表现的因素
- 竞争劣势：强调市场地位较弱、创新下降或来自竞争对手威胁等脆弱性
- 负面指标：使用财务数据、市场趋势或最近不利消息的证据来支持你的立场
- 反驳看涨观点：用具体数据和合理推理批判性分析看涨论点，揭露弱点或过度乐观的假设
- 参与讨论：以对话风格呈现你的论点，直接回应看涨分析师的观点并进行有效辩论，而不仅仅是列举事实

可用资源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论对话历史：{history}
最后的看涨论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}

请使用这些信息提供令人信服的看跌论点，反驳看涨声明，并参与动态辩论，展示投资该股票的风险和弱点。你还必须处理反思并从过去的经验教训和错误中学习。

请确保所有回答都使用中文。
"""

        # 🛡️ [H14 集中化防御] 使用 safe_llm_invoke 自动清理孤儿 tool_calls
        response = safe_llm_invoke(llm, prompt)

        argument = (
            f"Bear Analyst: {safe_extract_content(response)}"
            if safe_extract_content(response)
            else "Bear Analyst: (内容为空)"
        )

        # 🧠 [渐进辩论摘要] 从本轮发言中提取关键论点（纯规则，~1ms）
        key_points = extract_debate_key_points(argument, "Bear")
        existing_summary = investment_debate_state.get("debate_summary", "")
        new_summary = merge_key_points(existing_summary, key_points)

        new_count = investment_debate_state["count"] + 1
        logger.info(f"🐻 [空头研究员] 发言完成，计数: {investment_debate_state['count']} -> {new_count}")

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": new_count,
            "debate_summary": new_summary,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
