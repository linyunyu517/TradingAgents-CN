import time

from tradingagents.agents.utils.agent_utils import safe_llm_invoke
from tradingagents.agents.utils.instrument_utils import build_instrument_context

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


# =============================================================================
# [Plan C] SourceFormatterRegistry: 决策来源格式化策略
# 解决: risk_manager.py 中 if-elif 链无法扩展新决策来源的问题
# 参考: 策略模式 (Strategy Pattern) — GoF
# 注册式设计: 新增决策来源只需 register(), 无需改 risk_manager.py
# =============================================================================

class _DecisionSourceFormatter:
    """格式化决策来源的显示标签和推理文本。

    用法:
        formatted = _FORMATTER_REGISTRY.format(fused_decision)
        # formatted = "【MoA 综合决策】推理: 看空...关键因素: PE偏高 | RSI超买"
    """
    def __init__(self):
        self._formatters: dict[str, callable] = {}

    def register(self, source: str, formatter: callable):
        """注册一个来源格式化函数。

        Args:
            source: decision source 字符串 (如 "moa_synthesis", "daoist_empty_center")
            formatter: callable(dict) -> str, 接收 fused_decision 返回格式化文本
        """
        self._formatters[source] = formatter

    def format(self, fused_decision: dict) -> str:
        """格式化决策显示文本。

        按注册的 formatter 格式化, 未注册的来源走默认格式化。
        """
        if not fused_decision or not isinstance(fused_decision, dict):
            return "【决策】无数据"
        source = fused_decision.get("source", "unknown")
        formatter = self._formatters.get(source)
        if formatter is not None:
            try:
                return formatter(fused_decision)
            except Exception as e:
                logger.warning(f"[Formatter] {source} 格式化异常: {e}")
        return self._default_formatter(fused_decision)

    @staticmethod
    def _default_formatter(fd: dict) -> str:
        """默认格式化: 显示来源 + 权重 (兼容旧版 fused_decision)"""
        source = fd.get("source", "unknown")
        weight = fd.get("fusion_weight", fd.get("confidence", 0))
        action = fd.get("decision", "hold")
        return f"【BMA 融合决策】来源={source}, 行动={action}, 权重={weight:.2f}"


# 全局单例
_FORMATTER_REGISTRY = _DecisionSourceFormatter()

# ----- 注册各决策来源的格式化函数 -----

def _fmt_moa_synthesis(fd: dict) -> str:
    """MoA 综合器输出格式化"""
    parts = ["【MoA 综合决策】"]
    reasoning = fd.get("reasoning", "")
    factors = fd.get("key_factors", [])
    if reasoning:
        parts.append(f"推理: {reasoning[:500]}")
    if factors and isinstance(factors, list):
        factors_str = " | ".join(str(f) for f in factors[:5])
        parts.append(f"关键因素: {factors_str}")
    return "\n".join(parts)

_FORMATTER_REGISTRY.register("moa_synthesis", _fmt_moa_synthesis)


def _fmt_daoist_center(fd: dict) -> str:
    """道家中枢输出格式化"""
    action = fd.get("decision", "hold")
    confidence = fd.get("confidence", 0.0)
    reasoning = fd.get("reasoning", "")
    factors = fd.get("key_factors", [])
    # 检测是否触发了空信号
    daoist = fd.get("daoist_triggered", False)
    if daoist:
        parts = [f"☯️ 【道家中枢 — 空信号】行动={action}, 置信度={confidence:.2f}"]
    else:
        parts = [f"☯️ 【道家中枢】行动={action}, 置信度={confidence:.2f}"]
    if reasoning:
        parts.append(f"推理: {reasoning[:500]}")
    if factors and isinstance(factors, list):
        factors_str = " | ".join(str(f) for f in factors[:5])
        parts.append(f"关键因素: {factors_str}")
    return "\n".join(parts)

_FORMATTER_REGISTRY.register("daoist_empty_center", _fmt_daoist_center)


def _fmt_iterative_refinement(fd: dict) -> str:
    """迭代信念精炼输出格式化"""
    action = fd.get("decision", "hold")
    confidence = fd.get("confidence", 0.0)
    reasoning = fd.get("reasoning", "")
    n_iters = fd.get("n_iterations", fd.get("convergence_info", {}).get("n_iterations", 1))
    conv_info = fd.get("convergence_info", {})
    conv_reason = conv_info.get("reason", "")
    parts = [
        f"【迭代信念精炼】行动={action}, 置信度={confidence:.2f}, "
        f"迭代{n_iters}轮"
    ]
    if conv_reason:
        parts.append(f"收敛: {conv_reason[:200]}")
    if reasoning:
        parts.append(f"推理: {reasoning[:500]}")
    factors = fd.get("key_factors", [])
    if factors and isinstance(factors, list):
        factors_str = " | ".join(str(f) for f in factors[:5])
        parts.append(f"关键因素: {factors_str}")
    trace = fd.get("decision_trace", [])
    if trace and isinstance(trace, list):
        trace_str = " → ".join(
            f"#{t.get('iteration', i+1)}={t.get('action','?')}({t.get('confidence',0):.2f})"
            for i, t in enumerate(trace)
        )
        parts.append(f"迭代轨迹: {trace_str}")
    return "\n".join(parts)

_FORMATTER_REGISTRY.register("moa_iterative_refinement", _fmt_iterative_refinement)


def _fmt_bma_fusion(fd: dict) -> str:
    """BMA 数值融合输出格式化"""
    action = fd.get("decision", "hold")
    confidence = fd.get("confidence", 0.0)
    weights = fd.get("weights", {})
    probs = fd.get("probabilities", [])
    parts = [f"【BMA 数值融合】行动={action}, 置信度={confidence:.2f}"]
    if weights and isinstance(weights, dict):
        w_str = ", ".join(f"{k}={v:.2f}" for k, v in weights.items() if isinstance(v, (int, float)))
        if w_str:
            parts.append(f"权重: {w_str}")
    if probs and isinstance(probs, list) and len(probs) == 3:
        parts.append(f"概率: buy={probs[0]:.2f}, sell={probs[1]:.2f}, hold={probs[2]:.2f}")
    return " | ".join(parts)

_FORMATTER_REGISTRY.register("bma_fusion", _fmt_bma_fusion)


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        # ========== [FIX] 2026-06-26: 注入 AI 增强分析模块的量化评估结果 ==========
        # 让 AIF/HPC/Diffusion/Fusion 的量化输出直接影响最终决策
        aif_plan = state.get("diffusion_decision", {})
        fusion_result = state.get("fused_decision", {})
        efe_scores = state.get("fusion_efe_scores", {})

        enhanced_analysis_parts = []
        if efe_scores:
            efe_str = ", ".join(f"{k}={v:.2f}" for k, v in efe_scores.items() if isinstance(v, (int, float)))
            if efe_str:
                enhanced_analysis_parts.append(f"【AIF-EFE 评估】{efe_str}")
        if aif_plan:
            conf = aif_plan.get("confidence", 0)
            if conf and conf > 0:
                action_weights = aif_plan.get("action_weights", [])
                preferred = aif_plan.get("preferred_action", [])
                weights_str = f"权重分布={action_weights}" if action_weights else ""
                prefer_str = f"偏好={preferred}" if preferred else ""
                enhanced_analysis_parts.append(f"【扩散模型决策】置信度={conf:.3f} {weights_str} {prefer_str}")
        if fusion_result:
            # [Plan C] 使用 SourceFormatterRegistry 统一格式化
            formatted = _FORMATTER_REGISTRY.format(fusion_result)
            enhanced_analysis_parts.append(formatted)

        # [Plan C] 注入认知诊断（从 CognitiveDiagnostic 节点输出）
        cognitive_diag = state.get("cognitive_diagnosis", {})
        if cognitive_diag and isinstance(cognitive_diag, dict):
            diag_parts = []
            top_module = cognitive_diag.get("top_module", "?")
            n_iters = cognitive_diag.get("n_iterations", 0)
            converged = cognitive_diag.get("converged", False)
            entropy = cognitive_diag.get("attention_entropy", 0.0)
            conflict = cognitive_diag.get("conflict", 0.0)
            diag_parts.append(
                f"【认知诊断】top模块={top_module}, 迭代{n_iters}轮, "
                f"收敛={'是' if converged else '否'}, "
                f"注意力熵={entropy:.3f}, 冲突={conflict:.3f}"
            )
            missing = cognitive_diag.get("workspace_missing", [])
            if missing:
                diag_parts.append(f"缺失模块: {missing}")
            health = cognitive_diag.get("health_status", "")
            if health:
                diag_parts.append(f"健康状态: {health}")
            warnings = cognitive_diag.get("warnings", [])
            if warnings and isinstance(warnings, list):
                diag_parts.append(f"警告: {'; '.join(str(w) for w in warnings[:3])}")
            enhanced_analysis_parts.append(" | ".join(diag_parts))

        # [Plan C] 注入注意力分配摘要
        att_allocation = state.get("attention_allocation", {})
        if att_allocation and isinstance(att_allocation, dict):
            att_map = att_allocation.get("attention", {})
            if att_map and isinstance(att_map, dict):
                # 按注意力降序排列
                sorted_att = sorted(att_map.items(), key=lambda x: -x[1])
                att_str = " | ".join(f"{k}={v:.2f}" for k, v in sorted_att)
                enhanced_analysis_parts.append(f"【注意力分布】{att_str}")
            conflict_val = att_allocation.get("_conflict", 0)
            entropy_val = att_allocation.get("_entropy", 0)
            if isinstance(conflict_val, (int, float)) and isinstance(entropy_val, (int, float)):
                enhanced_analysis_parts.append(f"【注意力统计】冲突={conflict_val:.3f}, 熵={entropy_val:.3f}")

        # [MoA] 直接从 HSR-MC state 键读取元认知监控数据
        hsrc_state = state.get("hsrc_mc", {})
        if hsrc_state and isinstance(hsrc_state, dict):
            regime = hsrc_state.get("regime", {})
            if regime and isinstance(regime, dict):
                regime_summary = ", ".join(f"{k}={v}" for k, v in regime.items())
                enhanced_analysis_parts.append(f"【HSR-MC 市场制度】{regime_summary}")
            anomalies = hsrc_state.get("anomalies", [])
            if anomalies and isinstance(anomalies, list):
                enhanced_analysis_parts.append(f"【HSR-MC 异常检测】{anomalies[:3]}")

        # [FIX 2026-06-26] 从 hpc_state 提取市场体制概率（精确量化AIF信念的补充）
        hpc_state_raw = state.get("hpc_state", {})
        # [FIX 2026-06-26] 从 state 读取 EFE 分解（pragmatic vs epistemic）
        aif_selection = state.get("aif_selection", {})
        if isinstance(aif_selection, dict):
            efe_decomp = aif_selection.get("efe_decomposition", {})
            if efe_decomp:
                prag = efe_decomp.get("pragmatic", 0)
                epi = efe_decomp.get("epistemic", 0)
                if isinstance(prag, (int, float)) and isinstance(epi, (int, float)):
                    enhanced_analysis_parts.append(f"【EFE分解】利用(exploit)={prag:.2f}, 探索(explore)={epi:.2f}")

        # [FIX 2026-06-26] 读取临界慢化预警
        regime_risk = state.get("hsrc_regime_risk", 0.0)
        critical_slowing = state.get("hsrc_critical_slowing", 0.0)
        if isinstance(regime_risk, (int, float)) and regime_risk > 0.3:
            enhanced_analysis_parts.append(
                f"【体制预警】临界慢化ρ={critical_slowing:.2f}, 切换风险={regime_risk:.0%}"
            )

        # [FIX 2026-06-26] Phase 2.2: 读取自由能融合分解
        fusion_free_energies = state.get("fusion_free_energies", {})
        if fusion_free_energies and isinstance(fusion_free_energies, dict):
            fe_str = ", ".join(f"{k}={v:.3f}" for k, v in fusion_free_energies.items() if isinstance(v, (int, float)))
            if fe_str:
                enhanced_analysis_parts.append(f"【自由能分解】{fe_str}")

        if hpc_state_raw:
            # 兼容 HPCState 对象和 dict 两种形式
            hpc_dict = hpc_state_raw.to_dict() if hasattr(hpc_state_raw, "to_dict") else (hpc_state_raw if isinstance(hpc_state_raw, dict) else {})
            latent = hpc_dict.get("latent_state", {}) if isinstance(hpc_dict, dict) else {}
            if isinstance(latent, dict):
                regime_probs = latent.get("market_regime_probs", {})
                if regime_probs and isinstance(regime_probs, dict):
                    prob_str = ", ".join(f"{k}: {v:.1%}" for k, v in regime_probs.items() if isinstance(v, (int, float)))
                    if prob_str:
                        enhanced_analysis_parts.append(f"【市场体制概率】{prob_str}")

        enhanced_section = ""
        if enhanced_analysis_parts:
            enhanced_section = "\n\n---\n**AI 增强分析模块量化评估（供参考）：**\n" + "\n".join(enhanced_analysis_parts) + "\n---"
        # ==================================================================

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # [FIX] 2026-06-18: Fix 2.6 - 检查报告是否全部为空，避免零输出
        _all_reports_empty = all(
            not r or not r.strip() for r in [market_research_report, sentiment_report, news_report, fundamentals_report]
        )
        if _all_reports_empty:
            logger.warning("🔧 [Fix 2.6] 风险管理器: 所有报告均为空，使用占位文本继续分析")
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

        prompt = f"""作为风险管理委员会主席和辩论主持人，您的目标是评估三位风险分析师——激进、中性和安全/保守——之间的辩论，并确定交易员的最佳行动方案。您的决策必须产生明确的建议：买入、卖出或持有。只有在有具体论据强烈支持时才选择持有，而不是在所有方面都似乎有效时作为后备选择。力求清晰和果断。{enhanced_section}

决策指导原则：
1. **总结关键论点**：提取每位分析师的最强观点，重点关注与背景的相关性。
2. **提供理由**：用辩论中的直接引用和反驳论点支持您的建议。
3. **完善交易员计划**：从交易员的原始计划**{trader_plan}**开始，根据分析师的见解进行调整。
4. **从过去的错误中学习**：使用**{past_memory_str}**中的经验教训来解决先前的误判，改进您现在做出的决策，确保您不会做出错误的买入/卖出/持有决定而亏损。

交付成果：
- 明确且可操作的建议：买入、卖出或持有。
- 基于辩论和过去反思的详细推理。

标的约束：
{instrument_context}

---

**分析师辩论历史：**
{history}

---

专注于可操作的见解和持续改进。建立在过去经验教训的基础上，批判性地评估所有观点，确保每个决策都能带来更好的结果。请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        # 粗略估算 token 数量（中文约 1.5-2 字符/token，英文约 4 字符/token）
        estimated_tokens = int(prompt_length / 1.8)  # 保守估计

        logger.info("📊 [Risk Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 交易员计划长度: {len(trader_plan)} 字符")
        logger.info(f"   - 历史记忆长度: {len(past_memory_str)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # 增强的LLM调用，包含错误处理和重试机制
        max_retries = 3
        retry_count = 0
        response_content = ""

        while retry_count < max_retries:
            try:
                logger.info(f"🔄 [Risk Manager] 调用LLM生成交易决策 (尝试 {retry_count + 1}/{max_retries})")

                # ⏱️ 记录开始时间
                start_time = time.time()

                response = safe_llm_invoke(llm, prompt)

                # ⏱️ 记录结束时间
                elapsed_time = time.time() - start_time

                if response and hasattr(response, "content") and response.content:
                    response_content = response.content.strip()

                    # 📊 统计响应信息
                    response_length = len(response_content)
                    estimated_output_tokens = int(response_length / 1.8)

                    # 尝试获取实际的 token 使用情况（如果 LLM 返回了）
                    usage_info = ""
                    if hasattr(response, "response_metadata") and response.response_metadata:
                        metadata = response.response_metadata
                        if "token_usage" in metadata:
                            token_usage = metadata["token_usage"]
                            usage_info = f", 实际Token: 输入={token_usage.get('prompt_tokens', 'N/A')} 输出={token_usage.get('completion_tokens', 'N/A')} 总计={token_usage.get('total_tokens', 'N/A')}"

                    logger.info(f"⏱️ [Risk Manager] LLM调用耗时: {elapsed_time:.2f}秒")
                    logger.info(
                        f"📊 [Risk Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens{usage_info}",
                    )

                    if len(response_content) > 10:  # 确保响应有实质内容
                        logger.info("✅ [Risk Manager] LLM调用成功")
                        break
                    logger.warning(f"⚠️ [Risk Manager] LLM响应内容过短: {len(response_content)} 字符")
                    response_content = ""
                else:
                    logger.warning("⚠️ [Risk Manager] LLM响应为空或无效")
                    response_content = ""

            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(f"❌ [Risk Manager] LLM调用失败 (尝试 {retry_count + 1}): {e!s}")
                logger.error(f"⏱️ [Risk Manager] 失败前耗时: {elapsed_time:.2f}秒")
                response_content = ""

            retry_count += 1
            if retry_count < max_retries and not response_content:
                logger.info("🔄 [Risk Manager] 等待2秒后重试...")
                time.sleep(2)

        # 如果所有重试都失败，返回明确错误标记而非伪造"持有"决策
        if not response_content:
            logger.error(f"❌ [Risk Manager] 风险经理评估失败，所有 {max_retries} 次重试均失败")
            # 返回明确标记为非正常评估的结果
            new_risk_debate_state = {
                "judge_decision": f"风险评估失败：无法完成分析（{max_retries}次重试均失败）",
                "history": risk_debate_state["history"],
                "risky_history": risk_debate_state["risky_history"],
                "safe_history": risk_debate_state["safe_history"],
                "neutral_history": risk_debate_state["neutral_history"],
                "latest_speaker": "Judge",
                "current_risky_response": risk_debate_state["current_risky_response"],
                "current_safe_response": risk_debate_state["current_safe_response"],
                "current_neutral_response": risk_debate_state["current_neutral_response"],
                "count": risk_debate_state["count"],
            }

            logger.info("📋 [Risk Manager] 返回错误标记（重试耗尽），fallback_action=hold")
            return {
                "risk_debate_state": new_risk_debate_state,
                "final_trade_decision": "风险评估失败：无法完成分析",
                "risk_management_error": True,
                "risk_management_fallback": "hold",
                "risk_management_reason": "risk_analysis_exhausted_retries",
            }

        new_risk_debate_state = {
            "judge_decision": response_content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        logger.info(f"📋 [Risk Manager] 最终决策生成完成，内容长度: {len(response_content)} 字符")

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response_content,
        }

    return risk_manager_node
