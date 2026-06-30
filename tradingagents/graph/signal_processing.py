# TradingAgents/graph/signal_processing.py

import contextlib

from langchain_openai import ChatOpenAI

# 导入统一日志系统和图处理模块日志装饰器
from tradingagents.agents.utils.agent_utils import _safe_get_field
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_graph_module

logger = get_logger("graph.signal_processing")


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI, use_json_mode: bool = True):
        """Initialize with an LLM for processing.

        Args:
            quick_thinking_llm: LLM instance for processing signals
            use_json_mode: When True, attempt to use response_format='json_object'
                          for OpenAI-compatible LLMs (DeepSeek, OpenAI, etc.)
                          The existing JSON repair fallback is always preserved.
        """
        self.quick_thinking_llm = quick_thinking_llm
        self._use_json_mode = use_json_mode
        self._json_mode_success = False
        # 🔧 [JSON Mode] 初始化时记录 JSON Mode 启用状态
        if use_json_mode:
            logger.info("🔧 [JSON Mode] SignalProcessor 已启用 JSON Mode")

    def _invoke_json_mode(self, messages: list) -> str:
        """调用 LLM，优先使用 JSON Mode (response_format=json_object)，失败时降级到普通模式。

        DeepSeek JSON Mode 要求:
          1. response_format={'type': 'json_object'}  — 由本方法通过 bind() 注入
          2. prompt 中包含 "json" 关键字              — 见 process_signal() 中的 system prompt
          3. 足够的 max_tokens 避免截断                — 由调用方保证

        已知限制: JSON Mode 可能返回空内容（DeepSeek 文档已注明），此时自动降级到普通模式。

        # [FIX] 2026-06-18: Fix 2.3 - DeepSeek API 不支持 model_kwargs 参数，
        # 检测 LLM 提供器类型，对 DeepSeek 跳过 bind(model_kwargs=...) 避免 TypeError。
        """
        if not self._use_json_mode:
            self._json_mode_success = False
            return self.quick_thinking_llm.invoke(messages).content

        # 仅对 OpenAI / DeepSeek / 兼容 API 启用 JSON Mode
        is_openai_compatible = isinstance(self.quick_thinking_llm, ChatOpenAI)

        # [FIX] 2026-06-18: Fix 2.3 - 检测 DeepSeek 提供器，跳过 model_kwargs
        # DeepSeek API 不支持 model_kwargs，尝试传递会导致 TypeError
        provider = getattr(self.quick_thinking_llm, "_provider", None)
        is_deepseek = provider == "deepseek" or "DeepSeek" in type(self.quick_thinking_llm).__name__

        if is_openai_compatible and not is_deepseek:
            try:
                logger.debug("🔍 [SignalProcessor] 🚀 启用 JSON Mode (response_format=json_object)")
                response = (
                    self.quick_thinking_llm.bind(model_kwargs={"response_format": {"type": "json_object"}})
                    .invoke(messages)
                    .content
                )

                if response and response.strip():
                    self._json_mode_success = True
                    # 🔧 [JSON Mode] 成功使用 JSON Mode 的明确日志标记
                    logger.info("✅ [JSON Mode] 成功使用 JSON Mode (response_format=json_object)")
                    return response
                # 🔧 [JSON Mode] 失败降级时使用更明显的日志格式
                logger.warning("⚠️ [JSON Mode] 降级到普通模式: JSON Mode 返回空内容")
            except TypeError as e:
                # [FIX] 2026-06-18: Fix 2.3 - 捕获 TypeError（model_kwargs 不被 API 支持）
                logger.info(f"🔧 [JSON Mode] DeepSeek 不支持 model_kwargs，已跳过（{e}）")
            except Exception as e:
                # 🔧 [JSON Mode] 失败降级时使用更明显的日志格式
                logger.warning(f"⚠️ [JSON Mode] 降级到普通模式: {e}")
        elif is_deepseek:
            # [FIX] 2026-06-18: Fix 2.3 - DeepSeek 不尝试 JSON Mode，直接使用普通模式
            logger.info("🔧 [JSON Mode] DeepSeek 提供器不支持 model_kwargs，跳过 JSON Mode")
        else:
            logger.debug(
                f"🔍 [SignalProcessor] LLM 类型 {type(self.quick_thinking_llm).__name__} 不支持 JSON Mode，使用普通模式",
            )

        # Fallback: 普通模式（不带 response_format）
        self._json_mode_success = False
        return self.quick_thinking_llm.invoke(messages).content

    @log_graph_module("signal_processing")
    def process_signal(self, full_signal: str, stock_symbol: str | None = None, state: dict | None = None) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text
            stock_symbol: Stock symbol to determine currency type
            state: Optional state dict for dynamic confidence extraction

        Returns:
            Dictionary containing extracted decision information
        """

        # 从 state 中动态提取置信度，提取失败则 fallback 到 0.5
        def _state_confidence(default: float = 0.5) -> float:
            if state and isinstance(state, dict):
                try:
                    return _safe_get_field(state, "confidence", default, float)
                except (TypeError, ValueError):
                    pass
            return default

        # 验证输入参数
        if not full_signal or not isinstance(full_signal, str) or len(full_signal.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] 输入信号为空或无效: {full_signal!r}")
            return {
                "action": "持有",
                "target_price": None,
                "confidence": _state_confidence(),
                "risk_score": 0.5,
                "reasoning": "输入信号无效，默认持有建议",
                "_analysis_mode": "real",
            }

        # 清理和验证信号内容
        full_signal = full_signal.strip()
        if len(full_signal) == 0:
            logger.error("❌ [SignalProcessor] 信号内容为空")
            return {
                "action": "持有",
                "target_price": None,
                "confidence": _state_confidence(),
                "risk_score": 0.5,
                "reasoning": "信号内容为空，默认持有建议",
                "_analysis_mode": "real",
            }

        # 检测股票类型和货币
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(stock_symbol)
        is_china = market_info["is_china"]
        market_info["is_hk"]
        currency = market_info["currency_name"]
        currency_symbol = market_info["currency_symbol"]

        logger.info(
            f"🔍 [SignalProcessor] 处理信号: 股票={stock_symbol}, 市场={market_info['market_name']}, 货币={currency}",
            extra={"stock_symbol": stock_symbol, "market": market_info["market_name"], "currency": currency},
        )

        messages = [
            (
                "system",
                f"""您是一位专业的金融分析助手，负责从交易员的分析报告中提取结构化的投资决策信息。
请严格以JSON格式（json）输出结果，不要包含任何其他文本、解释或标注。

请从提供的分析报告中提取以下信息，并以JSON格式返回：

{{
    "action": "买入/持有/卖出",
    "target_price": 数字({currency}价格，**必须提供具体数值，不能为null**),
    "confidence": 数字(0-1之间，如果没有明确提及则为0.7),
    "risk_score": 数字(0-1之间，如果没有明确提及则为0.5),
    "reasoning": "决策的主要理由摘要"
}}

请确保：
1. action字段必须是"买入"、"持有"或"卖出"之一（绝对不允许使用英文buy/hold/sell）
2. target_price必须是具体的数字,target_price应该是合理的{currency}价格数字（使用{currency_symbol}符号）
3. confidence和risk_score应该在0-1之间
4. reasoning应该是简洁的中文摘要
5. 所有内容必须使用中文，不允许任何英文投资建议

特别注意：
- 股票代码 {stock_symbol or "未知"} 是{market_info["market_name"]}，使用{currency}计价
- 目标价格必须与股票的交易货币一致（{currency_symbol}）

如果某些信息在报告中没有明确提及，请使用合理的默认值。

【重要】请只输出合法的JSON对象，不要包含任何其他文本、标记或解释。您的响应应该以{{开头，以}}结尾。""",
            ),
            ("human", full_signal),
        ]

        # 验证messages内容
        if not messages or len(messages) == 0:
            logger.error("❌ [SignalProcessor] messages为空")
            return self._get_default_decision(state)

        # 验证human消息内容
        human_content = messages[1][1] if len(messages) > 1 else ""
        if not human_content or len(human_content.strip()) == 0:
            logger.error("❌ [SignalProcessor] human消息内容为空")
            return self._get_default_decision(state)

        logger.debug(f"🔍 [SignalProcessor] 准备调用LLM，消息数量: {len(messages)}, 信号长度: {len(full_signal)}")

        try:
            # ================================================================
            # 🆕 [子任务F] DeepSeek JSON Mode 集成
            # 使用 _invoke_json_mode() 自动尝试 response_format=json_object，
            # 并在 JSON Mode 失败时自动降级到普通模式。
            # 现有 5 层 JSON 修复 (see _repair_and_parse_json) 作为 fallback 保留。
            # ================================================================
            response = self._invoke_json_mode(messages)
            logger.debug(f"🔍 [SignalProcessor] LLM响应: {response[:200]}...")

            # ================================================================
            # 🐛 [Bug #1 修复] 增强 JSON 解析容错
            # 问题: 快速模型返回格式错误的 JSON 时，降级到 _extract_simple_decision()
            #       使用正则匹配原始文本，错误提取了"买入"子串
            # 修复: 1) 先尝试自动修复常见 JSON 格式错误
            #       2) 修复失败后使用上下文感知提取（优先从结论部分匹配）
            #       3) 仍然失败则返回"持有"（安全默认），避免决策反转
            # ================================================================
            decision_data = self._repair_and_parse_json(response)

            if decision_data is not None:
                # JSON 解析成功，正常处理
                result = self._build_decision_from_parsed(decision_data, full_signal, is_china, stock_symbol)
                # [FIX] 2026-06-18 P3: 零输出守卫 — 检查 result 是否为有效 dict
                if not result or not isinstance(result, dict):
                    logger.error("[FIX] 2026-06-18 P3: 零输出守卫触发 — process_signal result 为空")
                    result = self._get_default_decision(state, analysis_failed=True)
                else:
                    # 检查关键字段是否为空
                    action = result.get("action", "")
                    if not action or action not in ("买入", "持有", "卖出"):
                        logger.warning(f"[FIX] 2026-06-18 P3: 零输出守卫触发 — action 无效: {action!r}")
                        result.update(self._get_default_decision(state, analysis_failed=True))
                # 标记 JSON Mode 是否实际生效（仅用于调试/监控）
                if self._use_json_mode:
                    result["_json_mode_used"] = self._json_mode_success
                return result
            # JSON 完全无法解析，使用增强的上下文感知提取
            logger.warning("⚠️ [SignalProcessor] JSON 解析失败，使用增强的上下文感知提取")
            return self._enhanced_simple_decision(full_signal, response, state)

        except Exception as e:
            logger.error(f"信号处理错误: {e}", exc_info=True, extra={"stock_symbol": stock_symbol})
            # 回退到增强提取
            return self._enhanced_simple_decision(full_signal, None, state)

    # ==================================================================
    # 🆕 [Bug #1] JSON 修复工具
    # ==================================================================
    def _repair_and_parse_json(self, text: str) -> dict | None:
        """尝试修复并解析 LLM 返回的残损 JSON"""
        import json
        import re

        # 提取 JSON 块
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return None

        raw = json_match.group()

        # 尝试 1: 直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("信号处理 JSON 解析失败，使用默认值")

        # 尝试 2: 补全缺失的逗号（键值对之间缺少逗号是最常见的 LLM 输出错误）
        # 模式: "值"后面紧跟换行然后 "键" → 中间缺逗号
        fixed = re.sub(
            r'("(?:[^"\\]|\\.)*"|\d+(?:\.\d+)?|true|false|null)\s*\n\s*("(?:[^"\\]|\\.)*"\s*:)',
            r"\1,\n\2",
            raw,
        )
        # 补全数字/布尔值后面的逗号
        fixed = re.sub(
            r'(\d+(?:\.\d+)?|true|false|null)\s*\n\s*(")',
            r"\1,\n\2",
            fixed,
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            logger.warning("信号处理 JSON 解析失败，使用默认值")

        # 尝试 3: 单引号 → 双引号
        try:
            return json.loads(raw.replace("'", '"'))
        except json.JSONDecodeError:
            logger.warning("信号处理 JSON 解析失败，使用默认值")

        # 尝试 4: 移除注释和尾部逗号
        cleaned = re.sub(r"//.*?(\n|$)", "", raw)
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("信号处理 JSON 解析失败，使用默认值")

        # ====================================================================
        # 🆕 [Bug #3 修复] 尝试 5: 正则提取关键字段（终极容错）
        # 当所有 JSON 解析都失败时，直接从文本中提取 action/target_price/
        # confidence/risk_score/reasoning 五个字段，手工组装 dict
        # ====================================================================
        try:
            extracted = {}

            # 提取 action：支持中英文
            action_match = re.search(
                r'["\']?action["\']?\s*[:：=]\s*["\']?(买入|持有|卖出|'
                r'buy|hold|sell|BUY|HOLD|SELL|购买|保持|出售)["\']?',
                raw,
                re.IGNORECASE,
            )
            if action_match:
                raw_action = action_match.group(1).lower()
                action_map = {
                    "买入": "买入",
                    "buy": "买入",
                    "购买": "买入",
                    "持有": "持有",
                    "hold": "持有",
                    "保持": "持有",
                    "卖出": "卖出",
                    "sell": "卖出",
                    "出售": "卖出",
                }
                extracted["action"] = action_map.get(raw_action, "持有")
            # 从文本语义推测动作
            elif any(w in raw for w in ["买入", "买进", "加仓", "看多", "做多"]):
                extracted["action"] = "买入"
            elif any(w in raw for w in ["卖出", "卖", "减仓", "看空", "做空"]):
                extracted["action"] = "卖出"
            else:
                extracted["action"] = "持有"

            # 提取 target_price
            price_match = re.search(
                r'["\']?target_price["\']?\s*[:：=]\s*["\']?(\d+(?:\.\d+)?)["\']?', raw, re.IGNORECASE,
            )
            if price_match:
                extracted["target_price"] = float(price_match.group(1))
            else:
                # 从上下文中找价格数字
                price_fallback = re.search(r"目标价[位格]?[：:]?\s*[¥$￥]?(\d+(?:\.\d+)?)", raw)
                if price_fallback:
                    extracted["target_price"] = float(price_fallback.group(1))
                else:
                    extracted["target_price"] = None

            # 提取 confidence
            conf_match = re.search(r'["\']?confidence["\']?\s*[:：=]\s*["\']?(\d+(?:\.\d+)?)["\']?', raw, re.IGNORECASE)
            if conf_match:
                val = float(conf_match.group(1))
                extracted["confidence"] = max(0.0, min(1.0, val))
            elif "action" in extracted:
                # 没有明确置信度时，根据动作赋予不同默认值
                if extracted["action"] == "买入":
                    extracted["confidence"] = 0.65
                elif extracted["action"] == "卖出":
                    extracted["confidence"] = 0.60
                else:
                    extracted["confidence"] = 0.55
            else:
                extracted["confidence"] = 0.5

            # 提取 risk_score
            risk_match = re.search(r'["\']?risk_score["\']?\s*[:：=]\s*["\']?(\d+(?:\.\d+)?)["\']?', raw, re.IGNORECASE)
            if risk_match:
                val = float(risk_match.group(1))
                extracted["risk_score"] = max(0.0, min(1.0, val))
            else:
                extracted["risk_score"] = 0.5

            # 提取 reasoning
            reason_match = re.search(
                r'["\']?reasoning["\']?\s*[:：=]\s*["\']?(.*?)["\']\s*[,\}\]]', raw, re.DOTALL | re.IGNORECASE,
            )
            if reason_match:
                extracted["reasoning"] = reason_match.group(1).strip()
            else:
                # 取整个文本的前100字作为reasoning
                cleaned_text = re.sub(r'["\']', "", raw)
                extracted["reasoning"] = cleaned_text[:100].strip()

            if extracted:
                logger.warning(
                    f"⚠️ [SignalProcessor] JSON 完全解析失败，第5层正则提取成功: "
                    f"action={extracted.get('action')}, "
                    f"confidence={extracted.get('confidence')}",
                )
                return extracted

        except Exception as e:
            logger.debug(f"⚠️ [SignalProcessor] 第5层正则提取失败: {e}")

        return None

    def _build_decision_from_parsed(
        self, decision_data: dict, full_signal: str, is_china: bool, stock_symbol: str | None = None,
    ) -> dict:
        """从解析后的 JSON 构建标准决策输出"""
        import re

        # 验证和标准化数据
        action = decision_data.get("action", "持有")
        if action not in ["买入", "持有", "卖出"]:
            # 尝试映射英文和其他变体
            action_map = {
                "buy": "买入",
                "hold": "持有",
                "sell": "卖出",
                "BUY": "买入",
                "HOLD": "持有",
                "SELL": "卖出",
                "购买": "买入",
                "保持": "持有",
                "出售": "卖出",
                "purchase": "买入",
                "keep": "持有",
                "dispose": "卖出",
            }
            action = action_map.get(action, "持有")
            if action != decision_data.get("action", "持有"):
                logger.debug(f"🔍 [SignalProcessor] 投资建议映射: {decision_data.get('action')} -> {action}")

        # 处理目标价格，确保正确提取
        target_price = decision_data.get("target_price")
        if target_price is None or target_price in {"null", ""}:
            # 如果JSON中没有目标价格，尝试从reasoning和完整文本中提取
            reasoning = decision_data.get("reasoning", "")
            full_text = f"{reasoning} {full_signal}"  # 扩大搜索范围

            # 增强的价格匹配模式
            price_patterns = [
                r"目标价[位格]?[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 目标价位: 45.50
                r"目标[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 目标: 45.50
                r"价格[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 价格: 45.50
                r"价位[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 价位: 45.50
                r"合理[价位格]?[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 合理价位: 45.50
                r"估值[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 估值: 45.50
                r"[¥\$](\d+(?:\.\d+)?)",  # ¥45.50 或 $190
                r"(\d+(?:\.\d+)?)元",  # 45.50元
                r"(\d+(?:\.\d+)?)美元",  # 190美元
                r"建议[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 建议: 45.50
                r"预期[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",  # 预期: 45.50
                r"看[到至]\s*[¥\$]?(\d+(?:\.\d+)?)",  # 看到45.50
                r"上涨[到至]\s*[¥\$]?(\d+(?:\.\d+)?)",  # 上涨到45.50
                r"(\d+(?:\.\d+)?)\s*[¥\$]",  # 45.50¥
            ]

            for pattern in price_patterns:
                price_match = re.search(pattern, full_text, re.IGNORECASE)
                if price_match:
                    try:
                        target_price = float(price_match.group(1))
                        logger.debug(f"🔍 [SignalProcessor] 从文本中提取到目标价格: {target_price} (模式: {pattern})")
                        break
                    except (ValueError, IndexError):
                        continue

            # 如果仍然没有找到价格，尝试智能推算
            if target_price is None or target_price in {"null", ""}:
                target_price = self._smart_price_estimation(full_text, action, is_china)
                if target_price:
                    logger.debug(f"🔍 [SignalProcessor] 智能推算目标价格: {target_price}")
                else:
                    target_price = None
                    logger.warning("🔍 [SignalProcessor] 未能提取到目标价格，设置为None")
        else:
            # 确保价格是数值类型
            try:
                if isinstance(target_price, str):
                    # 清理字符串格式的价格
                    clean_price = (
                        target_price.replace("$", "")
                        .replace("¥", "")
                        .replace("￥", "")
                        .replace("元", "")
                        .replace("美元", "")
                        .strip()
                    )
                    target_price = (
                        float(clean_price) if clean_price and clean_price.lower() not in ["none", "null", ""] else None
                    )
                elif isinstance(target_price, (int, float)):
                    target_price = float(target_price)
                logger.debug(f"🔍 [SignalProcessor] 处理后的目标价格: {target_price}")
            except (ValueError, TypeError):
                target_price = None
                logger.warning("🔍 [SignalProcessor] 价格转换失败，设置为None")

        result = {
            "action": action,
            "target_price": target_price,
            "confidence": _safe_get_field(decision_data, "confidence", 0.7, float),
            "risk_score": _safe_get_field(decision_data, "risk_score", 0.5, float),
            "reasoning": decision_data.get("reasoning", "基于综合分析的投资建议"),
        }
        logger.info(
            f"🔍 [SignalProcessor] 处理结果: {result}",
            extra={
                "action": result["action"],
                "target_price": result["target_price"],
                "confidence": result["confidence"],
                "stock_symbol": stock_symbol,
            },
        )
        return result

    # ==================================================================
    # 🆕 [Bug #1] 上下文感知的决策提取（替代原来的 _extract_simple_decision）
    # ==================================================================
    def _enhanced_simple_decision(self, full_signal: str, llm_response: str | None, state: dict | None = None) -> dict:
        """增强的决策提取 — 上下文感知，避免错误匹配中间文本

        设计原则:
        1. 优先从 LLM 返回的 response（有格式错误但可能包含正确答案）中提取
        2. 其次从 full_signal 的结论部分（末尾）提取
        3. 当"买入"/"卖出"同时出现时，优先选择出现在结论性上下文中的那个
        4. 最终兜底返回"持有"（安全默认），避免决策反转
        """

        # ---- 阶段 1: 尝试从 LLM response 中提取 ----
        if llm_response:
            resp_decision = self._extract_action_context_aware(llm_response)
            if resp_decision and resp_decision != "持有":
                # 如果 response 中有明确结论（非默认值），优先使用
                action = resp_decision
                logger.info(f"🔍 [SignalProcessor] 从 LLM 响应中提取到决策: {action}")
                return self._build_fallback_result(action, full_signal, state)

        # ---- 阶段 2: 从 full_signal 的结论部分提取 ----
        action = self._extract_action_context_aware(full_signal)
        if action:
            logger.info(f"🔍 [SignalProcessor] 从信号文本中提取到决策: {action}")
            return self._build_fallback_result(action, full_signal, state)

        # ---- 阶段 3: 兜底 — 安全默认 ----
        logger.warning("⚠️ [SignalProcessor] 所有提取方式均失败，返回安全默认")
        confidence = _safe_get_field(state, "confidence", 0.3, float) if isinstance(state, dict) else 0.3
        return {
            "action": "持有",
            "target_price": None,
            "confidence": confidence,
            "risk_score": 0.5,
            "reasoning": "信号处理异常，默认持有建议（置信度低）",
            "_analysis_mode": "simulated",
        }

    def _extract_action_context_aware(self, text: str) -> str | None:
        """上下文感知的动作提取

        策略:
        1. 将文本分割为"结尾部分"（后 20% 行，至少 5 行）和"全文"
        2. 优先从结尾部分提取（结论通常在末尾）
        3. 如果结尾部分有明确结论，使用它
        4. 如果结尾部分无结论，从全文提取但只取出现次数多的那个
        """
        import re

        lines = text.strip().split("\n")
        total_lines = len(lines)

        # 取后 25% 行作为"结论区"，至少 5 行，最多 30 行
        end_chunk_size = max(min(total_lines // 4, 30), min(total_lines, 5))
        end_text = "\n".join(lines[-end_chunk_size:]) if total_lines > 0 else text

        def count_action(t: str) -> dict:
            """统计文本中各动作的出现次数"""
            buy = len(re.findall(r"(?<!逢低)买入|BUY", t, re.IGNORECASE))
            sell = len(re.findall(r"卖出|SELL", t, re.IGNORECASE))
            hold = len(re.findall(r"持有|HOLD", t, re.IGNORECASE))
            return {"买入": buy, "卖出": sell, "持有": hold}

        end_counts = count_action(end_text)

        # ---- 优先从结尾部分判断 ----
        # 如果结尾部分只有一个动作出现，使用它
        present_actions = [k for k, v in end_counts.items() if v > 0]
        if len(present_actions) == 1:
            return present_actions[0]

        # 如果结尾部分有多个动作，取出现最多的
        if present_actions:
            max_action = max(end_counts, key=end_counts.get)
            if end_counts[max_action] > 0:
                return max_action

        # ---- 降级到全文 ----
        full_counts = count_action(text)
        present_full = [k for k, v in full_counts.items() if v > 0]

        if len(present_full) == 1:
            return present_full[0]

        if present_full:
            # 多个动作出现，取出现最多的
            max_action = max(full_counts, key=full_counts.get)
            if full_counts[max_action] > 0:
                return max_action

        return None

    def _build_fallback_result(self, action: str, full_signal: str, state: dict | None = None) -> dict:
        """构建降级决策结果（价格提取 + 低置信度标记）"""
        target_price = self._smart_price_estimation(full_signal, action, is_china=True)
        confidence = _safe_get_field(state, "confidence", 0.6, float) if isinstance(state, dict) else 0.6
        return {
            "action": action,
            "target_price": target_price,
            "confidence": confidence,  # 降级标记：置信度降低
            "risk_score": 0.5,
            "reasoning": "基于正则提取的决策（因快速模型JSON解析失败降级）",
            "_analysis_mode": "simulated",
        }

    def _smart_price_estimation(self, text: str, action: str, is_china: bool) -> float:
        """智能价格推算方法"""
        import re

        # 尝试从文本中提取当前价格和涨跌幅信息
        current_price = None
        percentage_change = None

        # 提取当前价格
        current_price_patterns = [
            r"当前价[格位]?[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"现价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"股价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"价格[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
        ]

        for pattern in current_price_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    current_price = float(match.group(1))
                    break
                except ValueError:
                    continue

        # 提取涨跌幅信息
        percentage_patterns = [
            r"上涨\s*(\d+(?:\.\d+)?)%",
            r"涨幅\s*(\d+(?:\.\d+)?)%",
            r"增长\s*(\d+(?:\.\d+)?)%",
            r"(\d+(?:\.\d+)?)%\s*的?上涨",
        ]

        for pattern in percentage_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    percentage_change = float(match.group(1)) / 100
                    break
                except ValueError:
                    continue

        # 基于动作和信息推算目标价
        if current_price and percentage_change:
            if action == "买入":
                return round(current_price * (1 + percentage_change), 2)
            if action == "卖出":
                return round(current_price * (1 - percentage_change), 2)

        # 如果有当前价格但没有涨跌幅，使用默认估算
        if current_price:
            if action == "买入":
                # 买入建议默认10-20%涨幅
                multiplier = 1.15 if is_china else 1.12
                return round(current_price * multiplier, 2)
            if action == "卖出":
                # 卖出建议默认5-10%跌幅
                multiplier = 0.95 if is_china else 0.92
                return round(current_price * multiplier, 2)
            # 持有
            # 持有建议使用当前价格
            return current_price

        return None

    def _get_default_decision(self, state: dict | None = None, analysis_failed: bool = False) -> dict:
        """返回默认的投资决策，优先从 state 中动态提取置信度

        Args:
            state: 可选的状态字典，用于动态提取置信度
            analysis_failed: 是否因分析失败（如 LLM 调用异常/返回无效结果）进入此路径。
                             为 True 时结果中标记 _analysis_mode: "simulated"，
                             为 False 时标记 _analysis_mode: "real"。
        """
        confidence = _safe_get_field(state, "confidence", 0.5, float) if isinstance(state, dict) else 0.5
        result = {
            "action": "持有",
            "target_price": None,
            "confidence": confidence,
            "risk_score": 0.5,
            "reasoning": "输入数据无效，默认持有建议",
        }
        result["_analysis_mode"] = "simulated" if analysis_failed else "real"
        return result
