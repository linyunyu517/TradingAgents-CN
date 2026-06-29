# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")
# 🛡️ [H14 集中化防御] 导入安全 LLM 调用包装器和公共工具函数
from tradingagents.agents.utils.agent_utils import (
    are_all_reports_empty,
    safe_extract_content,
    safe_llm_invoke,
    is_data_fetch_failed,  # [PR #2] ContextVar 数据源故障检测
)

# 🔧 [H10 数据源全故障降级] 使用 agent_utils 公共函数 is_report_empty / are_all_reports_empty


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        logger.debug("🐂 [DEBUG] ===== 看涨研究员节点开始 =====")

        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # 🔧 [H10 数据源全故障降级] 检测所有报告是否为空
        # [PR #2] 新增 ContextVar 检测：只要有一个工具函数抛出异常就标记故障
        if is_data_fetch_failed() or are_all_reports_empty(state):
            if is_data_fetch_failed():
                logger.warning(
                    f"🔧 [PR #2 ContextVar故障检测] 检测到数据源故障标记 (ContextVar)，跳过 LLM 调用",
                )
            empty_count = state.get("empty_research_count", 0) + 1
            logger.warning(
                f"🔧 [H10 数据源全故障降级] 所有分析师报告为空 (empty_research_count={empty_count})，跳过 LLM 调用",
            )
            placeholder = (
                "⚠️ 数据源不可用：所有外部数据源（市场、情绪、新闻、基本面）"
                "均无法获取数据。当前仅能基于股票基本信息进行分析。"
            )
            new_count = investment_debate_state["count"] + 1
            new_investment_debate_state = {
                "history": history + "\n" + f"Bull Analyst: {placeholder}",
                "bull_history": bull_history + "\n" + f"Bull Analyst: {placeholder}",
                "bear_history": investment_debate_state.get("bear_history", ""),
                "current_response": placeholder,
                "count": new_count,
            }
            return {
                "investment_debate_state": new_investment_debate_state,
                "data_source_failure": True,
                "empty_research_count": empty_count,
            }

        # 使用统一的股票类型检测
        ticker = state.get("company_of_interest", "Unknown")
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info["is_china"]

        # 获取公司名称
        from tradingagents.agents.utils.company_name_resolver import get_company_name

        company_name = get_company_name(ticker, market_info, "多头研究员")
        is_hk = market_info["is_hk"]
        is_us = market_info["is_us"]

        currency = market_info["currency_name"]
        currency_symbol = market_info["currency_symbol"]

        logger.debug("🐂 [DEBUG] 接收到的报告:")
        logger.debug(f"🐂 [DEBUG] - 市场报告长度: {len(market_research_report)}")
        logger.debug(f"🐂 [DEBUG] - 情绪报告长度: {len(sentiment_report)}")
        logger.debug(f"🐂 [DEBUG] - 新闻报告长度: {len(news_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告前200字符: {fundamentals_report[:200]}...")
        logger.debug(
            f"🐂 [DEBUG] - 股票代码: {ticker}, 公司名称: {company_name}, 类型: {market_info['market_name']}, 货币: {currency}",
        )
        logger.debug(f"🐂 [DEBUG] - 市场详情: 中国A股={is_china}, 港股={is_hk}, 美股={is_us}")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # [FIX] 2026-06-18: Fix 2.6 - 检查报告是否全部为空，避免零输出
        _all_reports_empty = all(
            not r or not r.strip() for r in [market_research_report, sentiment_report, news_report, fundamentals_report]
        )
        if _all_reports_empty:
            logger.warning("🔧 [Fix 2.6] 多头研究员: 所有报告均为空，使用占位文本继续分析")
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

        prompt = f"""你是一位看涨分析师，负责为股票 {company_name}（股票代码：{ticker}）的投资建立强有力的论证。

⚠️ 重要提醒：当前分析的是 {"中国A股" if is_china else "海外股票"}，所有价格和估值请使用 {currency}（{currency_symbol}）作为单位。
⚠️ 在你的分析中，请始终使用公司名称"{company_name}"而不是股票代码"{ticker}"来称呼这家公司。

你的任务是构建基于证据的强有力案例，强调增长潜力、竞争优势和积极的市场指标。利用提供的研究和数据来解决担忧并有效反驳看跌论点。

请用中文回答，重点关注以下几个方面：
- 增长潜力：突出公司的市场机会、收入预测和可扩展性
- 竞争优势：强调独特产品、强势品牌或主导市场地位等因素
- 积极指标：使用财务健康状况、行业趋势和最新积极消息作为证据
- 反驳看跌观点：用具体数据和合理推理批判性分析看跌论点，全面解决担忧并说明为什么看涨观点更有说服力
- 参与讨论：以对话风格呈现你的论点，直接回应看跌分析师的观点并进行有效辩论，而不仅仅是列举数据

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论对话历史：{history}
最后的看跌论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}

请使用这些信息提供令人信服的看涨论点，反驳看跌担忧，并参与动态辩论，展示看涨立场的优势。你还必须处理反思并从过去的经验教训和错误中学习。

请确保所有回答都使用中文。
"""

        # 🛡️ [H14 集中化防御] 使用 safe_llm_invoke 自动清理孤儿 tool_calls
        response = safe_llm_invoke(llm, prompt)

        argument = (
            f"Bull Analyst: {safe_extract_content(response)}"
            if safe_extract_content(response)
            else "Bull Analyst: (内容为空)"
        )

        new_count = investment_debate_state["count"] + 1
        logger.info(f"🐂 [多头研究员] 发言完成，计数: {investment_debate_state['count']} -> {new_count}")

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": new_count,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
