import json
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 🔧 导入消息清理工具、DeepSeek检测工具和安全包装器
from tradingagents.agents.utils.agent_utils import (
    clean_orphaned_tool_calls,
    get_tool_names,
    is_deepseek_via_openai,
    safe_chain_invoke,
    safe_extract_content,
    safe_llm_invoke,
)

# 导入Google工具调用处理器
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.instrument_utils import build_instrument_context

# 导入统一新闻工具
from tradingagents.tools.unified_news_tool import create_unified_news_tool

# 导入数学层
from tradingagents.agents.analysts.news_math import run_full_math_layer

# 导入统一日志系统和分析模块日志装饰器
from tradingagents.utils.logging_init import get_logger

# 导入股票工具类
from tradingagents.utils.stock_utils import StockUtils
from tradingagents.utils.tool_logging import log_analyst_module

logger = get_logger("analysts.news")


def create_news_analyst(llm, toolkit):
    @log_analyst_module("news")
    def news_analyst_node(state):
        start_time = datetime.now()

        # 🔧 工具调用计数器 - 防止无限循环
        tool_call_count = state.get("news_tool_call_count", 0)
        max_tool_calls = 3  # 最大工具调用次数
        logger.info(f"🔧 [死循环修复] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        logger.info(f"[新闻分析师] 开始分析 {ticker} 的新闻，交易日期: {current_date}")
        session_id = state.get("session_id", "未知会话")
        logger.info(f"[新闻分析师] 会话ID: {session_id}，开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 获取市场信息
        market_info = StockUtils.get_market_info(ticker)
        logger.info(f"[新闻分析师] 股票类型: {market_info['market_name']}")

        # 获取公司名称
        from tradingagents.agents.utils.company_name_resolver import get_company_name

        company_name = get_company_name(ticker, market_info, "新闻分析师")
        instrument_context = build_instrument_context(ticker)
        logger.info(f"[新闻分析师] 公司名称: {company_name}")

        # 🔧 使用统一新闻工具，简化工具调用
        logger.info("[新闻分析师] 使用统一新闻工具，自动识别股票类型并获取相应新闻")
        # 创建统一新闻工具
        unified_news_tool = create_unified_news_tool(toolkit)
        unified_news_tool.name = "get_stock_news_unified"

        tools = [unified_news_tool]
        logger.info("[新闻分析师] 已加载统一新闻工具: get_stock_news_unified")

        system_message = """您是一位专业的财经新闻分析师，负责分析最新的市场新闻和事件对股票价格的潜在影响。

您的主要职责包括：
1. 获取和分析最新的实时新闻（优先15-30分钟内的新闻）
2. 评估新闻事件的紧急程度和市场影响
3. 识别可能影响股价的关键信息
4. 分析新闻的时效性和可靠性
5. 提供基于新闻的交易建议和价格影响评估

重点关注的新闻类型：
- 财报发布和业绩指导
- 重大合作和并购消息
- 政策变化和监管动态
- 突发事件和危机管理
- 行业趋势和技术突破
- 管理层变动和战略调整

分析要点：
- 新闻的时效性（发布时间距离现在多久）
- 新闻的可信度（来源权威性）
- 市场影响程度（对股价的潜在影响）
- 投资者情绪变化（正面/负面/中性）
- 与历史类似事件的对比

📊 新闻影响分析要求：
- 评估新闻对股价的短期影响（1-3天）和市场情绪变化
- 分析新闻的利好/利空程度和可能的市场反应
- 评估新闻对公司基本面和长期投资价值的影响
- 识别新闻中的关键信息点和潜在风险
- 对比历史类似事件的市场反应
- 不允许回复'无法评估影响'或'需要更多信息'

请特别注意：
⚠️ 如果新闻数据存在滞后（超过2小时），请在分析中明确说明时效性限制
✅ 优先分析最新的、高相关性的新闻事件
📊 提供新闻对市场情绪和投资者信心的影响评估
💰 必须包含基于新闻的市场反应预期和投资建议
🎯 聚焦新闻内容本身的解读，不涉及技术指标分析

请撰写详细的中文分析报告，并在报告末尾附上Markdown表格总结关键发现。"""

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位专业的财经新闻分析师。"
                    "\n🚨 CRITICAL REQUIREMENT - 绝对强制要求："
                    "\n"
                    "\n❌ 禁止行为："
                    "\n- 绝对禁止在没有调用工具的情况下直接回答"
                    "\n- 绝对禁止基于推测或假设生成任何分析内容"
                    "\n- 绝对禁止跳过工具调用步骤"
                    "\n- 绝对禁止说'我无法获取实时数据'等借口"
                    "\n"
                    "\n✅ 强制执行步骤："
                    "\n1. 您的第一个动作必须是调用 get_stock_news_unified 工具"
                    "\n2. 该工具会自动识别股票类型（A股、港股、美股）并获取相应新闻"
                    "\n3. 只有在成功获取新闻数据后，才能开始分析"
                    "\n4. 您的回答必须基于工具返回的真实数据"
                    "\n"
                    "\n🔧 工具调用格式示例："
                    "\n调用: get_stock_news_unified(stock_code='{ticker}', max_news=10)"
                    "\n"
                    "\n⚠️ 如果您不调用工具，您的回答将被视为无效并被拒绝。"
                    "\n⚠️ 您必须先调用工具获取数据，然后基于数据进行分析。"
                    "\n⚠️ 没有例外，没有借口，必须调用工具。"
                    "\n"
                    "\n您可以访问以下工具：{tool_names}。"
                    "\n标的约束：{instrument_context}"
                    "\n{system_message}"
                    "\n供您参考，当前日期是{current_date}。我们正在查看公司{ticker}。"
                    "\n请按照上述要求执行，用中文撰写所有分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ],
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(get_tool_names(tools)))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        prompt = prompt.partial(instrument_context=instrument_context)

        # 获取模型信息用于统一新闻工具的特殊处理
        model_info = ""
        try:
            if hasattr(llm, "model_name"):
                model_info = f"{llm.__class__.__name__}:{llm.model_name}"
            else:
                model_info = llm.__class__.__name__
        except Exception:
            model_info = "Unknown"

        logger.info(f"[新闻分析师] 准备调用LLM进行新闻分析，模型: {model_info}")

        # 🚨 DashScope/DeepSeek/Zhipu预处理：强制获取新闻数据
        # 🔧 修复：使用 is_deepseek_via_openai() 检测 ChatOpenAI 包装的 DeepSeek
        pre_fetched_news = None
        if "DashScope" in llm.__class__.__name__ or is_deepseek_via_openai(llm) or "Zhipu" in llm.__class__.__name__:
            logger.warning(
                f"[新闻分析师] 🚨 检测到{llm.__class__.__name__}模型（DeepSeek兼容），启动预处理强制新闻获取...",
            )
            try:
                # 强制预先获取新闻数据
                logger.info("[新闻分析师] 🔧 预处理：强制调用统一新闻工具...")
                logger.info(f"[新闻分析师] 📊 调用参数: stock_code={ticker}, max_news=10, model_info={model_info}")

                pre_fetched_news = unified_news_tool(stock_code=ticker, max_news=10, model_info=model_info)

                logger.info(
                    f"[新闻分析师] 📋 预处理返回结果长度: {len(pre_fetched_news) if pre_fetched_news else 0} 字符",
                )
                logger.info(
                    f"[新闻分析师] 📄 预处理返回结果预览 (前500字符): {pre_fetched_news[:500] if pre_fetched_news else 'None'}",
                )

                if pre_fetched_news and len(pre_fetched_news.strip()) > 100:
                    logger.info(f"[新闻分析师] ✅ 预处理成功获取新闻: {len(pre_fetched_news)} 字符")

                    # 直接基于预获取的新闻生成分析，跳过工具调用
                    # 🔧 重要：构建不包含工具调用指导的系统提示词
                    # ===== Phase 1: 数学层计算 (预取模式) =====
                    try:
                        math_features = run_full_math_layer(pre_fetched_news, ticker)
                        math_context = json.dumps(math_features, ensure_ascii=False)
                        logger.info(
                            f"[新闻分析师] ✅ 数学层计算完成: sentiment={math_features['overall_sentiment']:.3f}, "
                            f"belief={math_features['belief_update']['direction']}, "
                            f"{math_features['news_count']}条新闻, {math_features['compute_time_ms']}ms",
                        )
                    except Exception as e:
                        logger.warning(f"[新闻分析师] ⚠️ 数学层计算失败: {e}, 回退到无特征模式")
                        math_context = "{}"

                    analysis_system_prompt = "您是一位专业的财经新闻分析师。系统已完成数学层分析, 请基于提供的分析结果和新闻数据撰写中文报告。"

                    enhanced_prompt = f"""请对 {ticker}（{company_name}）进行新闻分析。

【系统数学层分析结果】
{math_context}

【原始新闻数据(前3000字符)】
{pre_fetched_news[:3000]}

请撰写简洁的中文新闻分析报告, 直接给出判断结论。"""

                    logger.info("[新闻分析师] 🔄 使用预获取新闻数据直接生成分析...")
                    logger.info(f"[新闻分析师] 📝 系统提示词长度: {len(analysis_system_prompt)} 字符")
                    logger.info(f"[新闻分析师] 📝 用户提示词长度: {len(enhanced_prompt)} 字符")

                    llm_start_time = datetime.now()
                    # 🔧 重要：传递系统消息和用户消息，不包含工具调用
                    result = safe_llm_invoke(
                        llm,
                        [
                            {"role": "system", "content": analysis_system_prompt},
                            {"role": "user", "content": enhanced_prompt},
                        ],
                    )

                    llm_end_time = datetime.now()
                    llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
                    logger.info(f"[新闻分析师] LLM调用完成（预处理模式），耗时: {llm_time_taken:.2f}秒")

                    # 直接返回结果，跳过后续的工具调用检测
                    report = safe_extract_content(result)
                    if report:
                        logger.info(f"[新闻分析师] ✅ 预处理模式成功，报告长度: {len(report)} 字符")
                        logger.info(f"[新闻分析师] 📄 报告预览 (前300字符): {report[:300]}")

                        # 跳转到最终处理
                        from langchain_core.messages import AIMessage

                        clean_message = AIMessage(content=report)

                        end_time = datetime.now()
                        time_taken = (end_time - start_time).total_seconds()
                        logger.info(f"[新闻分析师] 新闻分析完成（预处理模式），总耗时: {time_taken:.2f}秒")
                        # 🔧 更新工具调用计数器
                        return {
                            "messages": [clean_message],
                            "news_report": report,
                            "news_tool_call_count": tool_call_count + 1,
                        }
                    logger.warning("[新闻分析师] ⚠️ LLM返回结果为空，回退到标准模式")

                else:
                    logger.warning(
                        f"[新闻分析师] ⚠️ 预处理获取新闻失败或内容过短（{len(pre_fetched_news) if pre_fetched_news else 0}字符），回退到标准模式",
                    )
                    if pre_fetched_news:
                        logger.warning(f"[新闻分析师] 📄 失败的新闻内容: {pre_fetched_news}")

            except Exception as e:
                logger.error(f"[新闻分析师] ❌ 预处理失败: {e}，回退到标准模式")
                import traceback

                logger.error(f"[新闻分析师] 📋 异常堆栈: {traceback.format_exc()}")

        # 🔧 消息清理：移除孤立的 tool_calls，防止 DeepSeek API 400 错误
        cleaned_messages = clean_orphaned_tool_calls(state["messages"])
        logger.info(f"[新闻分析师] 消息清理完成: {len(state['messages'])}→{len(cleaned_messages)} 条")

        # 使用统一的Google工具调用处理器
        llm_start_time = datetime.now()
        chain = prompt | llm.bind_tools(tools)
        logger.info(f"[新闻分析师] 开始LLM调用，分析 {ticker} 的新闻")
        # 🛡️ [H14 集中化防御] 使用 safe_chain_invoke 自动清理孤儿 tool_calls
        result = safe_chain_invoke(chain, {"messages": cleaned_messages})

        llm_end_time = datetime.now()
        llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
        logger.info(f"[新闻分析师] LLM调用完成，耗时: {llm_time_taken:.2f}秒")

        # 使用统一的Google工具调用处理器
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info("📊 [新闻分析师] 检测到Google模型，使用统一工具调用处理器")

            # 创建分析提示词
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="新闻分析",
                specific_requirements="重点关注新闻事件对股价的影响、市场情绪变化、政策影响等。",
            )

            # 处理Google模型工具调用
            report, _messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="新闻分析师",
            )
        else:
            # 非Google模型的处理逻辑
            logger.info(f"[新闻分析师] 非Google模型 ({llm.__class__.__name__})，使用标准处理逻辑")

            # 检查工具调用情况
            current_tool_calls = len(result.tool_calls) if hasattr(result, "tool_calls") else 0
            logger.info(f"[新闻分析师] LLM调用了 {current_tool_calls} 个工具")
            logger.debug(f"📊 [DEBUG] 累计工具调用次数: {tool_call_count}/{max_tool_calls}")

            if current_tool_calls == 0:
                logger.warning(f"[新闻分析师] ⚠️ {llm.__class__.__name__} 没有调用任何工具，启动补救机制...")
                logger.warning(
                    f"[新闻分析师] 📄 LLM原始响应内容 (前500字符): {(safe_extract_content(result)[:500]) or 'No content'}",
                )

                try:
                    # 强制获取新闻数据
                    logger.info("[新闻分析师] 🔧 强制调用统一新闻工具获取新闻数据...")
                    logger.info(f"[新闻分析师] 📊 调用参数: stock_code={ticker}, max_news=10")

                    forced_news = unified_news_tool(stock_code=ticker, max_news=10, model_info=model_info)

                    logger.info(f"[新闻分析师] 📋 强制获取返回结果长度: {len(forced_news) if forced_news else 0} 字符")
                    logger.info(
                        f"[新闻分析师] 📄 强制获取返回结果预览 (前500字符): {forced_news[:500] if forced_news else 'None'}",
                    )

                    if forced_news and len(forced_news.strip()) > 100:
                        logger.info(f"[新闻分析师] ✅ 强制获取新闻成功: {len(forced_news)} 字符")

                        # 基于真实新闻数据重新生成分析
                        # ===== Phase 1: 数学层计算 (强制模式) =====
                        try:
                            math_features = run_full_math_layer(forced_news, ticker)
                            math_context = json.dumps(math_features, ensure_ascii=False)
                        except Exception as e:
                            logger.warning(f"[新闻分析师] ⚠️ 强制模式数学层失败: {e}")
                            math_context = "{}"

                        forced_prompt = f"""
您是一位专业的财经新闻分析师。

【系统数学层分析结果】
{math_context}

【最新新闻数据(前3000字符)】
{forced_news[:3000]}

请撰写简洁的中文分析报告，直接给出结论和判断。"""

                        logger.info("[新闻分析师] 🔄 基于强制获取的新闻数据重新生成完整分析...")
                        logger.info(f"[新闻分析师] 📝 强制提示词长度: {len(forced_prompt)} 字符")

                        forced_result = safe_llm_invoke(llm, [{"role": "user", "content": forced_prompt}])

                        report = safe_extract_content(forced_result)
                        if report:
                            logger.info(
                                f"[新闻分析师] ✅ 强制补救成功，生成基于真实数据的报告，长度: {len(report)} 字符",
                            )
                            logger.info(f"[新闻分析师] 📄 报告预览 (前300字符): {report[:300]}")
                        else:
                            logger.warning("[新闻分析师] ⚠️ 强制补救LLM返回为空，使用原始结果")
                            report = safe_extract_content(result) or ""
                    else:
                        logger.warning(
                            f"[新闻分析师] ⚠️ 统一新闻工具获取失败或内容过短（{len(forced_news) if forced_news else 0}字符），使用原始结果",
                        )
                        if forced_news:
                            logger.warning(f"[新闻分析师] 📄 失败的新闻内容: {forced_news}")
                        report = safe_extract_content(result) or ""

                except Exception as e:
                    logger.error(f"[新闻分析师] ❌ 强制补救过程失败: {e}")
                    import traceback

                    logger.error(f"[新闻分析师] 📋 异常堆栈: {traceback.format_exc()}")
                    report = safe_extract_content(result) or ""
            else:
                # 有工具调用，直接使用结果
                report = safe_extract_content(result) or ""

        total_time_taken = (datetime.now() - start_time).total_seconds()
        logger.info(f"[新闻分析师] 新闻分析完成，总耗时: {total_time_taken:.2f}秒")

        # [FIX] 2026-06-18: Fix 2.6 - 最终空报告保护，确保不为空
        if not report or not report.strip():
            logger.warning("[新闻分析师] ⚠️ [Fix 2.6] 最终报告为空，设置最低限度的占位内容")
            report = (
                f"📰 **{ticker} 新闻分析报告**（{current_date}）\n\n"
                f"⚠️ 当前未获取到有效新闻数据，无法进行详细新闻分析。\n\n"
                f"**可能原因：**\n"
                f"- 数据源暂时不可用\n"
                f"- 该股票在查询时段内无新新闻\n"
                f"- 网络连接异常\n\n"
                f"**建议：**\n"
                f"- 稍后重新查询新闻数据\n"
                f"- 结合其他分析报告综合判断\n"
                f"- 关注公司官方公告和定期报告"
            )

        # 🔧 修复死循环问题：返回清洁的AIMessage，不包含tool_calls
        # 这确保工作流图能正确判断分析已完成，避免重复调用
        from langchain_core.messages import AIMessage

        clean_message = AIMessage(content=report)

        logger.info(f"[新闻分析师] ✅ 返回清洁消息，报告长度: {len(report)} 字符")

        # 🔧 更新工具调用计数器
        return {"messages": [clean_message], "news_report": report, "news_tool_call_count": tool_call_count + 1}

    return news_analyst_node
