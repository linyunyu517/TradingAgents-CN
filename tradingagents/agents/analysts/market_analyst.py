import traceback
from datetime import timedelta, datetime

from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 🔧 导入消息清理工具和 LLM 安全包装器
from tradingagents.agents.utils.agent_utils import (
    clean_orphaned_tool_calls,
    get_tool_names,
    invoke_with_timeout,
    safe_chain_invoke,
    safe_extract_content,
    safe_llm_invoke,
)

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

# 导入分析模块日志装饰器

logger = get_logger("default")

# 导入Google工具调用处理器
# [B08][B09] 引入统一公司名称解析器，消除7个文件中的重复定义
from tradingagents.agents.utils.company_name_resolver import get_company_name
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.instrument_utils import build_instrument_context

# ===== 市场数学层（因果拓扑流形分析器 Phase1【器】）=====
from tradingagents.agents.analysts.market_math import compute_all_features


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        logger.debug("📈 [DEBUG] ===== 市场分析师节点开始 =====")

        # 🔧 工具调用计数器 - 防止无限循环
        tool_call_count = state.get("market_tool_call_count", 0)
        max_tool_calls = 3  # 最大工具调用次数
        logger.info(f"🔧 [死循环修复] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        # ========== BUG-002 修复: 死循环风险防御 ==========
        # 1. 检查是否已有报告 - 如果有则跳过 LLM 调用
        existing_report = state.get("market_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"📈 [市场分析师] ✅ 报告已存在 (长度: {len(existing_report)}), 跳过节点")
            return {
                "market_report": existing_report,
                "market_tool_call_count": tool_call_count,
            }

        # 2. 检查是否已达到最大工具调用次数
        messages = state.get("messages", [])
        actual_tool_messages = sum(1 for msg in messages if isinstance(msg, ToolMessage))
        tool_call_count = max(tool_call_count, actual_tool_messages)
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [BUG-002] 工具调用已达上限 {max_tool_calls}，强制结束")
            fallback = f"市场分析（股票代码：{state['company_of_interest']}）\n\n由于达到最大工具调用次数限制，使用简化分析模式。"
            return {
                "market_report": fallback,
                "market_tool_call_count": tool_call_count,
            }
        # ========== BUG-002 修复结束 ==========

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        logger.debug(f"📈 [DEBUG] 输入参数: ticker={ticker}, date={current_date}")
        logger.debug(f"📈 [DEBUG] 当前状态中的消息数量: {len(state.get('messages', []))}")
        logger.debug(f"📈 [DEBUG] 现有市场报告: {state.get('market_report', 'None')}")

        # 根据股票代码格式选择数据源
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(ticker)

        logger.debug(
            f"📈 [DEBUG] 股票类型检查: {ticker} -> {market_info['market_name']} ({market_info['currency_name']})",
        )

        # 获取公司名称
        company_name = get_company_name(ticker, market_info, "市场分析师")
        instrument_context = build_instrument_context(ticker)
        logger.debug(f"📈 [DEBUG] 公司名称: {ticker} -> {company_name}")

        # 统一使用 get_stock_market_data_unified 工具
        # 该工具内部会自动识别股票类型（A股/港股/美股）并调用相应的数据源
        logger.info("📊 [市场分析师] 使用统一市场数据工具，自动识别股票类型")
        tools = [toolkit.get_stock_market_data_unified]

        tool_names_debug = get_tool_names(tools)
        logger.info(f"📊 [市场分析师] 绑定的工具: {tool_names_debug}")
        logger.info(f"📊 [市场分析师] 目标市场: {market_info['market_name']}")

        # 🔥 优化：将输出格式要求放在系统提示的开头，确保LLM遵循格式
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位专业的股票技术分析师，与其他分析师协作。\n"
                    "\n"
                    "📋 **分析对象：**\n"
                    "- 公司名称：{company_name}\n"
                    "- 股票代码：{ticker}\n"
                    "- 所属市场：{market_name}\n"
                    "- 计价货币：{currency_name}（{currency_symbol}）\n"
                    "- 分析日期：{current_date}\n"
                    "- 标的约束：{instrument_context}\n"
                    "\n"
                    "🔧 **工具使用：**\n"
                    "你可以使用以下工具：{tool_names}\n"
                    "⚠️ 重要工作流程：\n"
                    "1. 如果消息历史中没有工具结果，立即调用 get_stock_market_data_unified 工具\n"
                    "   - ticker: {ticker}\n"
                    "   - start_date: {current_date}\n"
                    "   - end_date: {current_date}\n"
                    "   注意：系统会自动扩展到365天历史数据，你只需要传递当前分析日期即可\n"
                    "2. 如果消息历史中已经有工具结果（ToolMessage），立即基于工具数据生成最终分析报告\n"
                    "3. 不要重复调用工具！一次工具调用就足够了！\n"
                    "4. 接收到工具数据后，必须立即生成完整的技术分析报告，不要再调用任何工具\n"
                    "\n"
                    "📝 **输出格式要求（必须严格遵守）：**\n"
                    "\n"
                    "## 📊 股票基本信息\n"
                    "- 公司名称：{company_name}\n"
                    "- 股票代码：{ticker}\n"
                    "- 所属市场：{market_name}\n"
                    "\n"
                    "## 📈 技术指标分析\n"
                    "[在这里分析移动平均线、MACD、RSI、布林带等技术指标，提供具体数值]\n"
                    "\n"
                    "## 📉 价格趋势分析\n"
                    "[在这里分析价格趋势，考虑{market_name}市场特点]\n"
                    "\n"
                    "## 💭 投资建议\n"
                    "[在这里给出明确的投资建议：买入/持有/卖出]\n"
                    "\n"
                    "⚠️ **重要提醒：**\n"
                    "- 必须使用上述格式输出，不要自创标题格式\n"
                    "- 所有价格数据使用{currency_name}（{currency_symbol}）表示\n"
                    '- 确保在分析中正确使用公司名称"{company_name}"和股票代码"{ticker}"\n'
                    '- 不要在标题中使用"技术分析报告"等自创标题\n'
                    "- 如果你有明确的技术面投资建议（买入/持有/卖出），请在投资建议部分明确标注\n"
                    "- 不要使用'最终交易建议'前缀，因为最终决策需要综合所有分析师的意见\n"
                    "\n"
                    "请使用中文，基于真实数据进行分析。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ],
        )

        tool_names = get_tool_names(tools)

        # 🔥 设置所有模板变量
        prompt = prompt.partial(tool_names=", ".join(tool_names))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        prompt = prompt.partial(company_name=company_name)
        prompt = prompt.partial(market_name=market_info["market_name"])
        prompt = prompt.partial(currency_name=market_info["currency_name"])
        prompt = prompt.partial(currency_symbol=market_info["currency_symbol"])
        prompt = prompt.partial(instrument_context=instrument_context)

        # 添加详细日志
        logger.info(f"📊 [市场分析师] LLM类型: {llm.__class__.__name__}")
        logger.info(f"📊 [市场分析师] LLM模型: {getattr(llm, 'model_name', 'unknown')}")
        logger.info(f"📊 [市场分析师] 消息历史数量: {len(state['messages'])}")
        logger.info(f"📊 [市场分析师] 公司名称: {company_name}")
        logger.info(f"📊 [市场分析师] 股票代码: {ticker}")

        # 打印提示词模板信息
        logger.info("📊 [市场分析师] ========== 提示词模板信息 ==========")
        logger.info(
            f"📊 [市场分析师] 模板变量已设置: company_name={company_name}, ticker={ticker}, market={market_info['market_name']}",
        )
        logger.info("📊 [市场分析师] ==========================================")

        # 打印实际传递给LLM的消息
        logger.info("📊 [市场分析师] ========== 传递给LLM的消息 ==========")
        for i, msg in enumerate(state["messages"]):
            msg_type = type(msg).__name__
            # 🔥 修复：更安全地提取消息内容
            if hasattr(msg, "content"):
                msg_content = str(msg.content)[:500]  # 增加到500字符以便查看完整内容
            elif isinstance(msg, tuple) and len(msg) >= 2:
                # 处理旧格式的元组消息 ("human", "content")
                msg_content = f"[元组消息] 类型={msg[0]}, 内容={str(msg[1])[:500]}"
            else:
                msg_content = str(msg)[:500]
            logger.info(f"📊 [市场分析师] 消息[{i}] 类型={msg_type}, 内容={msg_content}")
        logger.info("📊 [市场分析师] ========== 消息列表结束 ==========")

        chain = prompt | llm.bind_tools(tools)

        logger.info("📊 [市场分析师] 开始调用LLM...")
        # 🔧 消息清理：移除孤立的 tool_calls，防止 DeepSeek API 400 错误
        cleaned_messages = clean_orphaned_tool_calls(state["messages"])
        logger.info(f"[市场分析师] 消息清理完成: {len(state['messages'])}→{len(cleaned_messages)} 条")

        # ========== BUG-033 修复: 上下文过大导致 LLM 超时 ==========
        # 在 Fusion/AIF 循环中，Market Analyst 可能被调用两次。
        # 第二轮时 state["messages"] 已累积 Bull/Bear/Research Manager/Trader 等
        # 所有中间节点的消息（50-60+条，200K+ tokens），导致 LLM API 调用超时。
        # 裁剪策略：保留头部系统/HPC 上下文 + 尾部最新消息，删除中间冗余消息。
        MAX_MESSAGES = 25
        if len(cleaned_messages) > MAX_MESSAGES:
            # 保留前 5 条（系统指令 + HPC 报告 + 第一轮系统提示）
            HEAD_KEEP = 5
            # 保留后 15 条（最近交互上下文）
            TAIL_KEEP = MAX_MESSAGES - HEAD_KEEP
            pruned_messages = cleaned_messages[:HEAD_KEEP] + cleaned_messages[-TAIL_KEEP:]
            logger.warning(
                f"📊 [市场分析师] 🐛 [BUG-033] 消息裁剪: {len(cleaned_messages)}→{len(pruned_messages)} 条 "
                f"(保留头部{HEAD_KEEP}+尾部{TAIL_KEEP})",
            )
            cleaned_messages = pruned_messages
        # ========== BUG-033 修复结束 ==========

        # 🛡️ [H14 集中化防御] 使用 safe_chain_invoke 自动清理孤儿 tool_calls
        result = safe_chain_invoke(chain, {"messages": cleaned_messages})
        logger.info("📊 [市场分析师] LLM调用完成")

        # 打印LLM响应
        logger.info("📊 [市场分析师] ========== LLM响应开始 ==========")
        logger.info(f"📊 [市场分析师] 响应类型: {type(result).__name__}")
        logger.info(f"📊 [市场分析师] 响应内容: {str(result.content)[:1000]}...")
        if hasattr(result, "tool_calls") and result.tool_calls:
            logger.info(f"📊 [市场分析师] 工具调用: {result.tool_calls}")
        logger.info("📊 [市场分析师] ========== LLM响应结束 ==========")

        # 使用统一的Google工具调用处理器
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info("📊 [市场分析师] 检测到Google模型，使用统一工具调用处理器")

            # 创建分析提示词
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="市场分析",
                specific_requirements="重点关注市场数据、价格走势、交易量变化等市场指标。",
            )

            # 处理Google模型工具调用
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="市场分析师",
            )

            # 🔧 更新工具调用计数器
            return {"messages": [result], "market_report": report, "market_tool_call_count": tool_call_count + 1}
        # 非Google模型的处理逻辑
        logger.info(f"📊 [市场分析师] 非Google模型 ({llm.__class__.__name__})，使用标准处理逻辑")
        logger.info("📊 [市场分析师] 检查LLM返回结果...")
        logger.info(f"📊 [市场分析师] - 是否有tool_calls: {hasattr(result, 'tool_calls')}")
        if hasattr(result, "tool_calls"):
            logger.info(f"📊 [市场分析师] - tool_calls数量: {len(result.tool_calls)}")
            if result.tool_calls:
                for i, tc in enumerate(result.tool_calls):
                    logger.info(f"📊 [市场分析师] - tool_call[{i}]: {tc.get('name', 'unknown')}")

        # 处理市场分析报告
        if len(result.tool_calls) == 0:
            # 没有工具调用，直接使用LLM的回复
            report = safe_extract_content(result)
            logger.info(f"📊 [市场分析师] ✅ 直接回复（无工具调用），长度: {len(report)}")
            logger.debug(f"📊 [DEBUG] 直接回复内容预览: {report[:200]}...")
        else:
            # 有工具调用，执行工具并生成完整分析报告
            logger.info(
                f"📊 [市场分析师] 🔧 检测到工具调用: {[call.get('name', 'unknown') for call in result.tool_calls]}",
            )

            try:
                # 执行工具调用
                from langchain_core.messages import HumanMessage

                tool_messages = []
                for tool_call in result.tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args", {})
                    tool_id = tool_call.get("id")

                    logger.debug(f"📊 [DEBUG] 执行工具: {tool_name}, 参数: {tool_args}")

                    # 找到对应的工具并执行
                    tool_result = None
                    for tool in tools:
                        # 安全地获取工具名称进行比较
                        current_tool_name = None
                        if hasattr(tool, "name"):
                            current_tool_name = tool.name
                        elif hasattr(tool, "__name__"):
                            current_tool_name = tool.__name__

                        if current_tool_name == tool_name:
                            try:
                                # 执行工具调用（get_china_stock_data 已移除，统一使用 get_stock_market_data_unified）
                                tool_result = invoke_with_timeout(
                                    tool.invoke,
                                    tool_args,
                                    timeout=60,
                                    timeout_msg=f"市场分析工具 {tool_name} 数据获取",
                                )
                                logger.debug(f"📊 [DEBUG] 工具执行成功，结果长度: {len(str(tool_result))}")
                                break
                            except Exception as tool_error:
                                logger.error(f"❌ [DEBUG] 工具执行失败: {tool_error}")
                                tool_result = f"工具执行失败: {tool_error!s}"

                    if tool_result is None:
                        tool_result = f"未找到工具: {tool_name}"

                    # 创建工具消息
                    tool_message = ToolMessage(content=str(tool_result), tool_call_id=tool_id)
                    tool_messages.append(tool_message)

                # ===== Phase 1【器】: 因果拓扑流形分析 - 数学结构提取 =====
                math_section = ""
                try:
                    from tradingagents.dataflows.data_source_manager import DataSourceManager

                    manager = DataSourceManager()
                    # 使用250天回看确保有足够数据点计算TDA/VMD/Regime
                    _lookback_days = 250
                    _start = (datetime.strptime(str(current_date), "%Y-%m-%d") - timedelta(days=_lookback_days)).strftime("%Y-%m-%d")
                    raw_df = manager.get_stock_dataframe(ticker, _start, current_date)
                    if raw_df is not None and not raw_df.empty:
                        if 'close' in raw_df.columns and len(raw_df['close']) > 10:
                            close_arr = raw_df['close'].values.astype(float)
                            vol_arr = raw_df['vol'].values.astype(float) if 'vol' in raw_df.columns else None
                            math_features = compute_all_features(close_arr, vol_arr)

                            tda = math_features.get("tda", {})
                            vmd = math_features.get("vmd", {})
                            regime = math_features.get("regime", {})
                            causal = math_features.get("causal", {})

                            if tda.get("available") or regime.get("available"):
                                parts = []
                                if tda.get("available"):
                                    parts.append(f"拓扑结构: {tda.get('betti_1', 'N/A')}个模式")
                                if regime.get("available"):
                                    parts.append(f"市场状态: {regime.get('combined_state', 'N/A')}")
                                    if regime.get("critical_slowing"):
                                        parts.append("⚠️ 临界预警")
                                if causal.get("available") and causal.get("causal_direction") != "无显著因果":
                                    parts.append(f"量价因果: {causal.get('causal_direction')}")

                                math_section = " | ".join(parts)
                                logger.info(
                                    f"📈 [市场分析师] 【器】{math_section} "
                                    f"(耗时={math_features.get('computation_time_ms', 0)}ms)",
                                )
                except Exception as e:
                    logger.warning(f"📈 [市场分析师] 【器】计算跳过(非致命): {e}")

                # 构建最终提示词（数据驱动翻译模式 = Phase 2【术】+ Phase 3【道】）
                if math_section:
                    math_instruction = f"""
**数学结构特征（由因果拓扑流形分析器计算）：**
{math_section}

请将以上数学特征融入分析中，特别关注拓扑异常和市场状态转换信号。"""
                else:
                    math_instruction = ""

                analysis_prompt = (
                    f"你现在是{company_name}({ticker})的技术分析师。\n"
                    f"分析日期：{current_date} | 市场：{market_info['market_name']}\n"
                    f"{math_instruction}\n"
                    f"---\n"
                    f"请基于工具数据中的技术指标（MA/MACD/RSI/BOLL）生成专业的技术分析报告。\n"
                    f"格式：股票基本信息 → 技术指标分析(含具体数值) → 趋势分析 → 投资建议\n"
                    f"报告标题：# **{company_name}（{ticker}）技术分析报告**\n"
                    f"要求：数据驱动、具体数值、明确评级(买入/持有/卖出)、使用中文"
                )

                # 构建完整的消息序列
                messages = [*cleaned_messages, result, *tool_messages, HumanMessage(content=analysis_prompt)]

                # 生成最终分析报告
                # 🛡️ [H14 集中化防御] 使用 safe_llm_invoke 自动清理孤儿 tool_calls
                final_result = safe_llm_invoke(llm, messages)
                report = final_result.content

                logger.info(f"📊 [市场分析师] 生成完整分析报告，长度: {len(report)}")

                # 返回包含工具调用和最终分析的完整消息序列
                # 🔧 更新工具调用计数器
                return {
                    "messages": [result, *tool_messages, final_result],
                    "market_report": report,
                    "market_tool_call_count": tool_call_count + 1,
                }

            except Exception as e:
                logger.error(f"❌ [市场分析师] 工具执行或分析生成失败: {e}")
                traceback.print_exc()

                # 降级处理：返回工具调用信息
                report = f"市场分析师调用了工具但分析生成失败: {[call.get('name', 'unknown') for call in result.tool_calls]}"

                # 🔧 BUG-002: 没有实际工具调用，不递增计数器
                return {"messages": [result], "market_report": report, "market_tool_call_count": tool_call_count}

        # 🔧 更新工具调用计数器
        return {"messages": [result], "market_report": report, "market_tool_call_count": tool_call_count + 1}

    return market_analyst_node
