# TradingAgents/graph/setup.py

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_bear_researcher,
    create_bull_researcher,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_research_manager,
    create_risk_manager,
    create_risky_debator,
    create_safe_debator,
    create_social_media_analyst,
    create_trader,
)
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import Toolkit

# [Plan C] 认知架构 — 全局工作空间 + 注意力分配 + 收敛检测
from tradingagents.agents.utils.agent_utils import (
    _safe_get_field,
    build_global_workspace,
    compute_attention,
    apply_attention_to_prompt,
    check_convergence,
)

# AIF (Active Inference Framework) 引擎导入
from tradingagents.dataflows.data_source_manager import get_data_source_manager
from tradingagents.hpc_loop.aif_integration import AIFEngineManager

# ========== 三轮改造 (HPC-Loop / L-IWM / HSR-MC) 导入 ==========
from tradingagents.hpc_loop.hpc_integration import HPCLoopManager

from .conditional_logic import ConditionalLogic

# L-IWM 工作记忆模块扩展点 (可选)
try:
    from tradingagents.l_iwm.l_iwm_config import LIWMConfig
    from tradingagents.l_iwm.l_iwm_integration import LIWMManager

    _L_IWM_AVAILABLE = True
except ImportError:
    LIWMManager = None  # type: ignore
    LIWMConfig = None  # type: ignore
    _L_IWM_AVAILABLE = False

# HSR-MC 超网络自指涉元控制器扩展点 (可选)
try:
    from tradingagents.hsrc_mc.hsrc_config import HSRMCConfig
    from tradingagents.hsrc_mc.hsrc_integration import HSRMCManager

    _HSRC_MC_AVAILABLE = True
except ImportError:
    HSRMCManager = None  # type: ignore
    HSRMCConfig = None  # type: ignore
    _HSRC_MC_AVAILABLE = False

# ========== Phase 3: 扩散模块 (Diffusion) 集成 ==========
try:
    from tradingagents.diffusion import DiffusionConfig, TradingDecisionDiffuser, uniform_prior

    _DIFFUSION_AVAILABLE = True
except ImportError:
    TradingDecisionDiffuser = None  # type: ignore
    DiffusionConfig = None  # type: ignore
    uniform_prior = None  # type: ignore
    _DIFFUSION_AVAILABLE = False

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# ========== AIF 推理迭代循环配置 ==========
AIF_MAX_ITERATIONS = max(1, int(os.environ.get("TRADINGAGENTS_AIF_MAX_ITERATIONS", "3")))
logger.info(f"[AIF Loop] 最大迭代次数配置: {AIF_MAX_ITERATIONS} (可通过 TRADINGAGENTS_AIF_MAX_ITERATIONS 环境变量覆盖)")


# ========== 扩散顾问节点 (Parallel Advisor Pattern) ==========
def diffusion_advisor_node(state) -> dict:
    """扩散顾问节点 — 作为独立并行顾问，不阻塞原始决策路径

    设计原则:
        - 并行顾问模式: 扩散模块运行在独立分支上
        - 非降级机制: 失败 → 均匀先验 (max entropy, confidence=0.0)
        - 对原始 Trader 决策零侵入

    Args:
        state: AgentState，包含 trader_investment_plan 等字段

    Returns:
        dict: 写入 state.diffusion_decision 的更新字典
    """
    # 🐛 [Bug #4 修复] 添加显式计时和采样诊断
    import time

    _node_start = time.time()

    trader_plan = state.get("trader_investment_plan", "")
    plan_available = bool(trader_plan and len(trader_plan) > 50)

    if not _DIFFUSION_AVAILABLE:
        logger.info("[Diffusion] 模块未加载，使用文本启发式替代")
        if plan_available:
            import re
            buy_signals = len(re.findall(r"(?:买入|买|看多|利好|上涨|反弹|抄底)", trader_plan))
            sell_signals = len(re.findall(r"(?:卖出|卖|看空|利空|下跌|清仓|止损)", trader_plan))
            total_signals = buy_signals + sell_signals
            if total_signals > 0:
                heuristic_confidence = 0.3
                heuristic_weight = 0.3
            else:
                heuristic_confidence = 0.2
                heuristic_weight = 0.2
        else:
            heuristic_confidence = 0.1
            heuristic_weight = 0.1
        return {
            "diffusion_decision": {
                "action": "heuristic",
                "confidence": heuristic_confidence,
                "weight": heuristic_weight,
                "source": "text_heuristic",
                "model_unavailable": True,
            },
        }

    if not plan_available:
        logger.warning("[Diffusion] 交易员计划为空或太短，使用低置信度中性立场")
        return {
            "diffusion_decision": {
                "action": "neutral",
                "confidence": 0.15,
                "weight": 0.15,
                "source": "degraded_neutral",
            },
        }

    try:
        # 初始化扩散决策器（延迟初始化，避免导入时加载）
        diffuser = TradingDecisionDiffuser()

        # ===== [FIX 2026-06-26] 用真实行情替换随机数 =====
        # 从 state 获取股票代码，标准化后从数据源拉取真实行情
        stock_symbol = state.get("company_of_interest", "")
        stock_code = str(stock_symbol).strip().upper() if stock_symbol else ""
        # 去掉 .SH/.SZ 后缀，补齐6位
        import re as _re
        stock_code = _re.sub(r"\.(SH|SZ|BJ)$", "", stock_code) if stock_code else ""
        stock_code = stock_code.zfill(6) if stock_code else ""

        market_data_raw = None
        if stock_code:
            try:
                _manager = get_data_source_manager()
                _today_str = datetime.now().strftime("%Y-%m-%d")
                _start_str = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
                _df = _manager.get_stock_dataframe(
                    stock_code,
                    start_date=_start_str,
                    end_date=_today_str,
                    period="daily",
                )
                if _df is not None and not _df.empty:
                    market_data_raw = _df
                    logger.info(
                        "[Diffusion] ✅ 获取到行情数据: %s, %d 行, %d 列",
                        stock_code, len(_df), len(_df.columns),
                    )
            except Exception as _e:
                logger.warning("[Diffusion] ⚠️ 行情获取失败: %s", _e)

        if market_data_raw is not None:
            # 提取数值列（与 train_diffusion.py 的 build_market_dataset 一致）
            _numeric = market_data_raw.select_dtypes(include=[np.number]).values  # (T, raw_feat)

            # Z-score 标准化
            _mean = np.nanmean(_numeric, axis=0)
            _std = np.nanstd(_numeric, axis=0) + 1e-8
            _normed = (_numeric - _mean) / _std
            _normed = np.nan_to_num(_normed, nan=0.0)  # (T, raw_feat)

            _raw_feat = _normed.shape[1]

            # 对齐到 16 维（pad 或 truncate）
            if _raw_feat < 16:
                _pad = np.zeros((_normed.shape[0], 16 - _raw_feat), dtype=np.float64)
                _aligned = np.concatenate([_normed, _pad], axis=1)
            elif _raw_feat > 16:
                _aligned = _normed[:, :16]
            else:
                _aligned = _normed

            # 取最后 20 天，不够则在前面补零
            _avail = _aligned.shape[0]
            _seq = min(20, _avail)
            _last20 = _aligned[-_seq:]  # (_seq, 16)
            if _seq < 20:
                _pad_front = np.zeros((20 - _seq, 16), dtype=np.float64)
                market_state = np.concatenate([_pad_front, _last20], axis=0)
            else:
                market_state = _last20

            market_state = market_state[np.newaxis, ...].astype(np.float32)  # (1, 20, 16)
            logger.info(
                "[Diffusion] ✅ 真实市场数据就绪: %s, %d 天, %d→16 特征",
                stock_code, _avail, _raw_feat,
            )
        else:
            # 降级：无数据时用均匀随机数
            logger.warning(
                "[Diffusion] ⚠️ 无 %s 行情数据, 使用随机回退",
                stock_code or "未知股票",
            )
            market_state = np.random.randn(1, 20, 16).astype(np.float32)

        _t0 = time.time()
        # 执行扩散决策
        result = diffuser.decide(
            market_state=market_state,
            debate_result=None,
            horizon=5,
            num_samples=20,
            risk_preference=1.0,
        )
        _decide_elapsed = time.time() - _t0

        confidence = float(result["confidence"])
        action_weights = result["action_weights"][0]  # (horizon,)
        preferred = result["preferred_action"][0]  # (horizon,)

        # 🐛 [Bug #4 诊断] 检查是否所有样本都退化为均匀先验
        # raw_samples shape: (num_samples, batch, horizon, n_actions)
        if "raw_samples" in result:
            raw = result["raw_samples"]
            n_total = raw.shape[0]
            # 均匀先验的判定：所有采样结果完全相同（uniform_prior 返回固定值）
            # 取每个样本的第一个元素判断是否完全相同
            first_vals = raw[:, 0, 0, 0]  # (num_samples,)
            all_identical = bool(__import__("numpy").all(first_vals == first_vals[0]))
            if all_identical:
                logger.warning(
                    f"[Diffusion] ⚠️ 所有 {n_total} 个 DDIM 样本完全相同 "
                    f"(退化为均匀先验)，模型可能未正确执行。"
                    f"decide() 耗时: {_decide_elapsed:.3f}s",
                )
            else:
                logger.info(
                    f"[Diffusion] ✓ 扩散模型成功执行: "
                    f"{n_total} 个样本均来自 DDIM 采样 (非退化)。"
                    f"decide() 耗时: {_decide_elapsed:.3f}s",
                )
        else:
            logger.warning(
                f"[Diffusion] ⚠️ result 中缺少 raw_samples 字段，无法诊断退化情况。decide() 耗时: {_decide_elapsed:.3f}s",
            )

        logger.info(
            "[Diffusion] 扩散顾问决策完成 — confidence=%.4f, weights=%s, preferred=%s, total_node_time=%.3fs",
            confidence,
            __import__("numpy").array_str(action_weights, precision=3),
            preferred,
            time.time() - _node_start,
        )

        # [FIX 2026-06-26] Phase 1.3: 增加动作概率分布和不确定性分解供 BMA 使用
        # 从 raw_samples 计算动作概率分布
        action_probs_list = [1/3, 1/3, 1/3]
        epistemic_val = float(getattr(result, "epistemic", _safe_get_field(result, "epistemic", 0.5, float)))
        aleatoric_val = float(getattr(result, "aleatoric", _safe_get_field(result, "aleatoric", 0.5, float)))
        if "raw_samples" in result:
            raw = result["raw_samples"]
            if raw is not None and hasattr(raw, "shape"):
                # raw: (num_samples, batch, horizon, n_actions)
                mean_probs = np.mean(raw, axis=0)[0]  # (horizon, n_actions)
                horizon_mean = np.mean(mean_probs, axis=0)  # (n_actions,)
                action_probs_list = (horizon_mean / (horizon_mean.sum() + 1e-30)).tolist()

        return {
            "diffusion_decision": {
                "action_weights": action_weights.tolist(),
                "preferred_action": preferred.tolist(),
                "confidence": confidence,
                "weight": confidence,
                "action_probs": action_probs_list,  # [P1.3] 新增: [buy, sell, hold] 概率
                "epistemic": epistemic_val,          # [P1.3] 新增: 认知不确定性
                "aleatoric": aleatoric_val,          # [P1.3] 新增: 偶然不确定性
            },
        }

    except Exception as exc:
        logger.warning("[Diffusion] 扩散顾问推理异常: %s (耗时 %.3fs)，使用低置信度回退", exc, time.time() - _node_start)
        fallback_confidence = 0.1
        return {
            "diffusion_decision": {
                "action": "fallback",
                "confidence": fallback_confidence,
                "weight": fallback_confidence,
                "source": "exception_fallback",
                "error": str(exc)[:200],
            },
        }


# ====================================================================
# [FIX 2026-06-26] Phase 1.1: BMA 融合 — 替代旧版硬编码加权融合
# 参考: Hoeting+ 1999 "Bayesian Model Averaging"
# ====================================================================


def _extract_trader_probs(plan: str) -> list[float]:
    """从交易员计划文本中提取买/卖/持概率（启发式但比硬编码好）"""
    if not plan or len(plan) < 20:
        return [1/3, 1/3, 1/3]
    plan_lower = plan.lower()
    buy_kw = ("买入", "买", "看多", "上涨", "利好", "反弹", "增持", "走强", "bull", "buy", "long")
    sell_kw = ("卖出", "卖", "看空", "下跌", "利空", "清仓", "减持", "走弱", "bear", "sell", "short")
    buy_c = sum(plan_lower.count(kw) for kw in buy_kw)
    sell_c = sum(plan_lower.count(kw) for kw in sell_kw)
    hold_c = max(0, len(plan) // 50 - buy_c - sell_c) + 1
    tot = buy_c + sell_c + hold_c + 1e-8
    return [buy_c / tot, sell_c / tot, hold_c / tot]


def _weights_to_probs(weights: list[float]) -> list[float]:
    """[-1,1] 权重序列转 buy/sell/hold 概率"""
    if not weights:
        return [1/3, 1/3, 1/3]
    w = np.mean(weights)
    buy_p = max(0.0, w)
    sell_p = max(0.0, -w)
    hold_p = max(0.0, 1.0 - buy_p - sell_p)
    tot = buy_p + sell_p + hold_p + 1e-30
    return [buy_p / tot, sell_p / tot, hold_p / tot]


# ========== [FIX 2026-06-27] Phase 1.4: MoA Synthesizer — 智能综合器节点 ==========
# 参考: Wang et al. 2024 "Mixture-of-Agions" (arXiv:2406.04692)
# 设计: 替代 BMA 数值融合, 由 LLM 综合所有模块定性+定量输出
# 退化路径: MoA → BMA(数值融合) → 均匀分布


import json
import re as _re


def _fmt_report(header: str, text: str, max_len: int = 600) -> str:
    """格式化报告段，处理空输入和截断"""
    if not text or not text.strip():
        return f"### {header}\n（未获取到数据）\n"
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len] + "...（截断）"
    return f"### {header}\n{text}\n"


def _softmin_efe(efe_dict: dict) -> list[float]:
    """EFE 越小越好 → softmin → [buy, sell, hold] 概率"""
    eps = 1e-30
    e = np.array([efe_dict.get(a, 0.0) for a in ("buy", "sell", "hold")], dtype=np.float64)
    probs = np.exp(-e) / (np.exp(-e).sum() + eps)
    return probs.tolist()


def _build_moa_collection(state: dict) -> dict[str, Any]:
    """从 state 收集所有模块输出，构建供综合器使用的结构化数据"""
    c: dict[str, Any] = {}

    # 1. 交易员
    trader_plan = state.get("trader_investment_plan", "")
    c["trader"] = {
        "plan": trader_plan or "（未生成投资计划）",
        "probs": _extract_trader_probs(trader_plan),
    }

    # 2. 扩散模型
    diff_dec = state.get("diffusion_decision", {})
    if diff_dec and isinstance(diff_dec, dict):
        c["diffusion"] = {
            "action_probs": diff_dec.get("action_probs", [1 / 3, 1 / 3, 1 / 3]),
            "confidence": diff_dec.get("confidence", 0.0),
            "epistemic": diff_dec.get("epistemic", "N/A"),
            "aleatoric": diff_dec.get("aleatoric", "N/A"),
            "source": diff_dec.get("source", "unknown"),
        }
    else:
        c["diffusion"] = {"action_probs": [1 / 3, 1 / 3, 1 / 3], "confidence": 0.0, "source": "unavailable"}

    # 3. AIF-EFE
    efe = state.get("fusion_efe_scores", {})
    if efe and isinstance(efe, dict) and any(efe.values()):
        c["aif"] = {
            "efe_scores": dict(efe),
            "efe_probs": _softmin_efe(efe),
            "belief": str(state.get("aif_belief", "N/A"))[:300],
        }
    else:
        c["aif"] = {"efe_scores": {}, "efe_probs": [1 / 3, 1 / 3, 1 / 3], "belief": "N/A"}

    # 4. HSR-MC（4 个 state 键聚合）
    hsrc = state.get("hsrc_mc", {}) or {}
    hsrc_meta = state.get("hsrc_mc_meta", {}) or {}
    hsrc_reflect = state.get("hsrc_mc_reflect", {}) or {}
    hsrc_adjust = state.get("hsrc_mc_adjust", {}) or {}
    # 提取健康分：优先取 overall_health 字符串映射，其次取数值均值
    _raw_health = hsrc.get("health", {}) or {}
    _health_map = {"healthy": 1.0, "degraded": 0.5, "warning": 0.3, "unhealthy": 0.0, "critical": 0.0}
    if isinstance(_raw_health, dict):
        _overall = _raw_health.get("overall_health", "healthy")
        _health_score = _health_map.get(str(_overall).lower(), 1.0)
    elif isinstance(_raw_health, (int, float)):
        _health_score = float(_raw_health)
    else:
        _health_score = 1.0
    c["hsrc_mc"] = {
        "regime": hsrc.get("regime", {}),
        "health": _raw_health,
        "health_score": _health_score,
        "anomalies": (hsrc.get("anomalies", []) or [])[:5],
        "interventions": (hsrc.get("intervention_suggestions", []) or [])[:5],
        "self_model": hsrc_meta.get("self_model_stats", {}),
        "hyper_stats": hsrc_meta.get("hyper_stats", {}),
        "reflection": {
            "deception": hsrc_reflect.get("deception", "N/A"),
            "reflexivity": str(hsrc_reflect.get("reflexivity_vector", []))[:200],
        },
        "adjustments": hsrc_adjust.get("adjustments", {}),
    }

    # 5. L-IWM
    liwm = state.get("l_iwm", {}) or {}
    hpc_state_val = state.get("hpc_state", {})
    pe = None
    if isinstance(hpc_state_val, dict):
        last_pe = hpc_state_val.get("last_prediction_error")
        if isinstance(last_pe, dict):
            pe = last_pe
    c["l_iwm"] = {
        "ewc_loss": liwm.get("ewc_loss", "N/A"),
        "module_performance": state.get("module_performance", {}),
        "prediction_error": pe or "N/A",
    }

    # 6. 分析师報告
    c["analysts"] = {
        "market": state.get("market_report", ""),
        "fundamentals": state.get("fundamentals_report", ""),
        "news": state.get("news_report", "") or "（未获取到新闻数据）",
        "sentiment": state.get("sentiment_report", "") or "（未获取到情绪数据）",
    }

    return c


def _build_moa_prompt(c: dict) -> str:
    """构建 MoA 综合提示词"""
    d = c["diffusion"]
    a = c["aif"]
    h = c["hsrc_mc"]
    lw = c["l_iwm"]
    an = c["analysts"]

    lines = [
        "你是一位顶级股票投资决策综合师。你的任务是综合所有分析模块的输出，给出最终交易决策。",
        "",
        "请严格输出 JSON 格式，不要包含其他内容：",
        "",
        "## 证据 1：交易员计划（基于所有分析的初始决策）",
        f"计划内容：{c['trader']['plan'][:1500]}",
        f"关键词概率→ buy={c['trader']['probs'][0]:.3f} sell={c['trader']['probs'][1]:.3f} hold={c['trader']['probs'][2]:.3f}",
        "",
        "## 证据 2：扩散模型（CSDI DDIM 时序扩散）",
        f"动作概率：buy={d['action_probs'][0]:.3f} sell={d['action_probs'][1]:.3f} hold={d['action_probs'][2]:.3f}",
        f"置信度={d['confidence']:.3f}",
        f"认知不确定性（epistemic）={d['epistemic']}",
        f"偶然不确定性（aleatoric）={d['aleatoric']}",
        f"数据来源={d['source']}",
        "",
        "## 证据 3：AIF 主动推理（自由能最小化）",
        f"EFE 评分（越小越好）：buy={a['efe_scores'].get('buy','N/A')} sell={a['efe_scores'].get('sell','N/A')} hold={a['efe_scores'].get('hold','N/A')}",
        f"EFE→概率：buy={a['efe_probs'][0]:.3f} sell={a['efe_probs'][1]:.3f} hold={a['efe_probs'][2]:.3f}",
        f"AIF 信念状态：{a['belief']}",
        "",
        "## 证据 4：HSR-MC 元认知监控（高阶自指涉分析）",
        f"市场制度：{h['regime']}",
        f"系统健康度：{h['health']}",
        f"异常检测：{h['anomalies']}",
        f"干预建议：{h['interventions']}",
        f"自模型统计：{h['self_model']}",
        f"超网络更新：{h['hyper_stats']}",
        f"反射分析——欺骗检测={h['reflection']['deception']} 反身性={h['reflection']['reflexivity']}",
        f"调整操作：{h['adjustments']}",
        "",
        "## 证据 5：L-IWM 学习型内在工作记忆",
        f"EWC 遗忘指标（越小越稳定）：{lw['ewc_loss']}",
        f"RSSM 预测误差：{lw['prediction_error']}",
        f"模块性能：{lw['module_performance']}",
        "",
        "## 证据 6：分析师原始报告摘要",
        _fmt_report("市场技术分析", an["market"]),
        _fmt_report("基本面分析", an["fundamentals"]),
        _fmt_report("新闻分析", an["news"]),
        _fmt_report("社交媒体情绪分析", an["sentiment"]),
        "",
        "## 输出格式（严格 JSON，不要 markdown 包裹）",
        '{',
        '  "action": "buy" | "sell" | "hold",',
        '  "confidence": 0.0 ~ 1.0,',
        '  "target_price": float | null,',
        '  "reasoning": "综合分析，2-5 句，引用主要证据",',
        '  "key_factors": ["factor1", "factor2", ...]',
        '}',
    ]
    return "\n".join(lines)


def _json_strip_inline(code: str) -> str:
    """从 LLM 回复中提取最内层 JSON 块，支持 markdown ```json 包裹"""
    # 尝试 ```json ... ``` 块
    m = _re.search(r'```(?:json)?\s*\n?(.*?)\n?```', code, _re.DOTALL)
    if m:
        return m.group(1).strip()
    # 尝试裸 { ... } 对象（最深层的）
    m = _re.search(r'\{[^{}]*"action"[^{}]*\}', code, _re.DOTALL)
    if m:
        return m.group(0).strip()
    # 回退：直接返回原内容（假设它已经是 JSON）
    return code.strip()


_MOA_OUTPUT_SCHEMA = frozenset({"action", "confidence", "reasoning"})
_ACTION_MAP = {"buy": 0, "sell": 1, "hold": 2}


def _validate_moa_output(parsed: dict) -> tuple[str, float, list[float], str, list[str]]:
    """验证并归一化 MoA 输出，返回 (action, confidence, probs, reasoning, key_factors)"""
    action = str(parsed.get("action", "hold")).lower().strip()
    if action not in _ACTION_MAP:
        action = "hold"

    confidence = _safe_get_field(parsed, "confidence", 0.5, float)
    confidence = max(0.0, min(1.0, confidence))

    # 概率分布映射（从 action + confidence 构造软分布）
    idx = _ACTION_MAP[action]
    probs = [0.05, 0.05, 0.9]
    probs[idx] = confidence
    total = sum(probs) + 1e-30
    probs = [p / total for p in probs]

    reasoning = str(parsed.get("reasoning", ""))[:2000]
    key_factors = parsed.get("key_factors", [])
    if not isinstance(key_factors, list):
        key_factors = [str(key_factors)] if key_factors else []

    return action, confidence, probs, reasoning, key_factors


def _create_moa_node_fn(state: dict, llm) -> dict:
    """MoA Synthesizer 核心逻辑：收集→综合→决策（含退化回退）"""
    # 1. 收集所有模块输出
    collection = _build_moa_collection(state)

    # 2. 尝试 MoA LLM 综合（L4: 最多3次重试）
    from tradingagents.agents.utils.agent_utils import safe_llm_invoke, safe_extract_content

    max_attempts = 3
    last_error = None
    last_raw = ""

    for attempt in range(1, max_attempts + 1):
        try:
            prompt = _build_moa_prompt(collection)
            result = safe_llm_invoke(llm, [{"role": "user", "content": prompt}])
            raw = safe_extract_content(result)
            last_raw = raw or ""

            if raw and len(raw.strip()) > 10:
                json_str = _json_strip_inline(raw)
                parsed = json.loads(json_str)
                # L4: 宽松 schema 检查 — 缺失字段用默认值填充
                action, confidence, probs, reasoning, key_factors = _validate_moa_output(parsed)
                # 只要 action 和 reasoning 存在就算成功
                if action and reasoning and len(reasoning.strip()) > 5:
                    logger.info(
                        "[MoA] ✅ 综合完成 (attempt=%d/%d): action=%s, confidence=%.4f, reasoning_len=%d",
                        attempt, max_attempts, action, confidence, len(reasoning),
                    )
                    return {
                        "fused_decision": {
                            "decision": action,
                            "confidence": confidence,
                            "probabilities": probs,
                            "reasoning": reasoning,
                            "key_factors": key_factors,
                            "source": "moa_synthesis",
                        },
                    }
                else:
                    logger.warning(f"[MoA] ⚠️ 输出内容不足 (attempt=%d/%d): action={action!r}, reasoning_len={len(reasoning or '')}", attempt, max_attempts)
                    last_error = "insufficient_output"
            else:
                logger.warning(f"[MoA] ⚠️ LLM 返回内容过短 (attempt=%d/%d): raw_len={len(raw or '')}", attempt, max_attempts)
                last_error = "empty_output"
        except json.JSONDecodeError as e:
            logger.warning(f"[MoA] ⚠️ JSON 解析失败 (attempt=%d/%d): {e}", attempt, max_attempts)
            last_error = str(e)
        except Exception as e:
            logger.warning(f"[MoA] ⚠️ 综合器异常 (attempt=%d/%d): {type(e).__name__}: {e}", attempt, max_attempts)
            last_error = str(e)
            if attempt < max_attempts:
                import time
                time.sleep(0.5)  # 重试前短暂等待

    # 3. 退化路径：BMA 数值融合（所有重试失败后）
    logger.info("[MoA] ⤵️ %d 次尝试全部失败 (%s)，回退到 BMA 数值融合", max_attempts, last_error)
    return fusion_node(state)


def create_moa_synthesizer_node(llm) -> callable:
    """创建 MoA Synthesizer LangGraph 节点

    Args:
        llm: 用于综合推理的 LLM 实例（推荐使用 deep_thinking_llm）

    Returns:
        callable: LangGraph 节点函数 (state) -> dict
    """
    if llm is None:
        logger.warning("[MoA] LLM 为 None，退化到纯 BMA 模式")
        return fusion_node

    def moa_synthesizer_node(state) -> dict:
        return _create_moa_node_fn(state, llm)

    moa_synthesizer_node.__name__ = "MoASynthesizer"
    moa_synthesizer_node.__qualname__ = "MoASynthesizer"
    return moa_synthesizer_node


# ===========================================================================
# [Plan C] 认知架构 — 全局工作空间填充 + 注意力分配 + 道家中枢 + 迭代精炼
# 参考:
#   Baars 1988 "Global Workspace Theory"
#   Dehaene 2001 "Cortical mechanisms of conscious access"
#   Friston 2009 "Predictive coding under the free-energy principle"
#   Haken 1983 "Synergetics — 序参量"
#   道家"无为"; 佛学"空性"; 物演通论"递弱代偿"
# ===========================================================================


def create_workspace_populator():
    """创建 GlobalWorkspace 填充节点。

    在每轮迭代开始前调用, 从当前 state 收集所有模块的最新输出,
    标准化后填充到 global_workspace。
    """
    def populator_node(state: dict) -> dict:
        workspace = build_global_workspace(state)

        # 保留上一轮的迭代状态（如果有）
        prev_ws = state.get("global_workspace", None)
        if isinstance(prev_ws, dict):
            prev_meta = prev_ws.get("_meta", {})
            if isinstance(prev_meta, dict) and prev_meta.get("iteration", 0) > 0:
                workspace["_meta"] = dict(prev_meta)

        logger.info(
            "[GlobalWorkspace] ✅ 填充完成: %d 个模块, 迭代#%d",
            len(workspace),
            workspace["_meta"]["iteration"],
        )
        return {"global_workspace": workspace}

    populator_node.__name__ = "GlobalWorkspacePopulate"
    return populator_node


def create_attention_allocator_node(config: dict | None = None):
    """创建注意力分配器节点。

    在每轮迭代开始时调用, 根据当前 workspace 内容计算各模块的注意力权重。
    输出写入 state["attention_allocation"]。

    参考:
    - 类脑AI: 注意力机制 + 全局工作空间理论 (Baars 1988, Dehaene 2001)
    - 复杂系统: 协同学序参量 (Haken 1983) — 注意力是系统的"序参量"
    - AgentVerse (arXiv:2308.10848): 动态代理优先级分配
    """
    def attention_allocator_node(state: dict) -> dict:
        workspace = state.get("global_workspace", None)
        if not isinstance(workspace, dict) or not workspace:
            logger.warning("[AttentionAllocator] ⚠️ 工作空间为空, 使用均匀注意力")
            return {"attention_allocation": {}}

        result = compute_attention(workspace, config)
        att_map = result.get("attention", {})

        # 找出最高注意力模块
        top_module = max(att_map.items(), key=lambda x: x[1]) if att_map else ("none", 0)

        logger.info(
            "[AttentionAllocator] ✅ 分配完成: top=%s(%.3f), entropy=%.3f, conflict=%.3f",
            top_module[0], top_module[1],
            result.get("_entropy", 0),
            result.get("_conflict", 0),
        )
        return {"attention_allocation": result}

    attention_allocator_node.__name__ = "AttentionAllocator"
    return attention_allocator_node


def create_daoist_center(config: dict | None = None):
    """创建道家虛靜中樞节点。

    在迭代收敛后、最终决策前调用。检测"空信号"状态:
      - 所有模块注意力权重 < 阈值 → 无显著信号
      - 所有模块置信度 < 阈值 → 高度不确定
      - 模块平均概率分布接近均匀 → 无方向

    空信号时: 不强迫出决策, 输出"持有"和"无观点"
    非空信号: 返回 "daoist_skip=true", 让下游正常走

    参考:
    - 道家: 无为 — 无强制行动, 顺应自然
    - 佛学: 空性 — 无自性即无偏见 ("色即是空, 空即是色")
    - 物演通论 (王东岳): 系统复杂到一定程度, "不做"比"做错"的代偿成本更低
    - 量化金融: 无显著信号时持有是最优策略
    """
    if config is None:
        config = {}
    # Soft Gate 参数: 权重向量[注意力熵, 置信度均值, 波动率, 预测误差], 偏置, 判决阈值
    soft_gate_w = np.array(config.get("soft_gate_weights",
                                        [2.0, 3.0, -1.0, -0.5]), dtype=np.float64)
    soft_gate_b = float(config.get("soft_gate_bias", -1.5))
    soft_gate_threshold = float(config.get("soft_gate_threshold", 0.20))
    eps = 1e-30

    def daoist_center_node(state: dict) -> dict:
        workspace = state.get("global_workspace", None)
        attention = state.get("attention_allocation", None)

        if not isinstance(workspace, dict) or not isinstance(attention, dict):
            return {"fused_decision": {}, "_daoist_skip": True}

        att_map = attention.get("attention", {})
        if not att_map:
            return {"fused_decision": {}, "_daoist_skip": True}

        # ===== Soft Gate 特征提取 =====
        # 特征1: 注意力熵 (反应注意力分散程度)
        att_vals = list(att_map.values())
        if att_vals:
            att_probs = np.array(att_vals, dtype=np.float64) / (sum(att_vals) + eps)
            att_entropy = -np.sum(att_probs * np.log(att_probs + eps)) / np.log(len(att_vals) + eps)
        else:
            att_entropy = 1.0

        # 特征2: 各模块置信度均值
        confidences: list[float] = []
        for key in ("trader", "diffusion"):
            entry = workspace.get(key, None)
            if isinstance(entry, dict):
                c = entry.get("confidence", None)
                if isinstance(c, (int, float)):
                    confidences.append(float(c))
        conf_mean = float(np.mean(confidences)) if confidences else 0.0

        # 特征3: 市场波动率 (来自 HPC-Loop 或默认值)
        vol = state.get("market_volatility", 0.15)

        # 特征4: 预测误差 (来自 AIF 或扩散模型)
        pred_err = state.get("prediction_error", 0.5)

        # ===== Soft Gate 计算 =====
        gate_input = np.array([att_entropy, conf_mean, vol, pred_err], dtype=np.float64)
        gate = 1.0 / (1.0 + np.exp(-(np.dot(gate_input, soft_gate_w) + soft_gate_b)))

        logger.info(
            "[DaoistCenter] ☯️ Soft Gate: score=%.4f (阈值=%.2f) | "
            "entropy=%.3f conf=%.3f vol=%.3f err=%.3f",
            gate, soft_gate_threshold,
            att_entropy, conf_mean, vol, pred_err,
        )

        if gate < soft_gate_threshold:
            logger.info(
                "[DaoistCenter] ☯️ 空信号(gate=%.4f < %.2f), 输出'持有'",
                gate, soft_gate_threshold,
            )
            return {
                "fused_decision": {
                    "decision": "hold",
                    "confidence": 0.30,
                    "probabilities": [0.10, 0.10, 0.80],
                    "source": "daoist_empty_center",
                    "reasoning": (
                        f"系统信号强度不足 (Soft Gate score={gate:.3f})。"
                        f"注意力熵={att_entropy:.2f}, 置信度均值={conf_mean:.2f}, "
                        f"波动率={vol:.2f}, 预测误差={pred_err:.2f}。"
                        "根据道家'无为'原则, 不强迫出决策, 输出'持有'以避免不必要交易成本。"
                    ),
                    "key_factors": ["信号强度不足", f"gate={gate:.3f}"],
                    "daoist_triggered": True,
                },
                "_soft_gate_score": gate,
            }

        # 非空信号 → 传空 dict 让下游继续（None 会导致 _dict_merge_reducer 崩溃）
        logger.info("[DaoistCenter] ✅ 非空信号(gate=%.4f), 继续正常流程", gate)
        return {"fused_decision": {}, "_daoist_skip": True, "_soft_gate_score": gate}

    daoist_center_node.__name__ = "DaoistCenter"
    return daoist_center_node


def create_iterative_belief_refinement(llm):
    """创建迭代信念精炼节点（替代单次 MoA 综合器）。

    流程 (函数内部循环, 不依赖 LangGraph 外循环边):
    第 1 轮: 用当前 workspace 分配注意力 → 生成加权 MoA 提示词 → LLM 综合
         → 记录到 decision_trace → 检查收敛
    第 2 轮: (未收敛) → 将上轮 MoA 输出写回 workspace → 重新分配注意力
         → 生成新一轮加权提示词 (包含上一轮结果) → LLM 综合 → 检查
    第 3 轮: (未收敛) → 最终综合, 强制输出

    收敛检测: check_convergence() 检查 decision_trace

    参考:
    - MoA (arXiv:2406.04692): 分层 LLM 综合实现 SOTA
    - 计算神经科学: 皮层-丘脑环的递归预测精炼 (Llinás 2003)
    - 物演通论: 多轮迭代是系统对复杂性的代偿
    - 道家"反者道之动": 每轮迭代的信念变化本身就是信息
    """
    if llm is None:
        logger.warning("[IBRefinement] LLM 为 None, 退化到 MoA 综合器")
        return create_moa_synthesizer_node(None)

    def ib_refinement_node(state: dict) -> dict:
        # 获取或初始化迭代状态
        workspace = state.get("global_workspace", {})
        if not isinstance(workspace, dict):
            workspace = build_global_workspace(state)

        decision_trace = state.get("decision_trace", None)
        if not isinstance(decision_trace, list):
            decision_trace = []

        meta = workspace.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {"iteration": 0, "max_iterations": 3, "converged": False}

        max_iter = int(meta.get("max_iterations", 3))
        start_iter = int(meta.get("iteration", 0))

        # ===== 函数内循环迭代 =====
        for iteration in range(start_iter, max_iter):
            iteration_num = iteration + 1  # 1-indexed for logging

            # 步骤1: 更新 workspace
            workspace = build_global_workspace(state)

            # 注入上轮 MoA 输出（如果有）作为本轮上下文
            prev_moa = workspace.pop("_moa_feedback", None)
            if prev_moa and isinstance(prev_moa, dict):
                workspace["_previous_moa"] = prev_moa

            # 步骤2: 注意力分配
            attention = compute_attention(workspace)

            # [Plan C] 显式日志确认循环执行（修复时序假象）
            logger.info(
                "[IBRefinement] 🔄 迭代 #%d/%d 开始 — 注意力: %s, workspace_modules: %s",
                iteration_num, max_iter,
                {k: f"{v:.3f}" for k, v in attention.get("attention", {}).items()},
                list(workspace.keys()),
            )

            # 步骤3: 生成加权提示词并调用 LLM
            try:
                weighted_prompt = apply_attention_to_prompt(workspace, attention)
                from tradingagents.agents.utils.agent_utils import safe_llm_invoke, safe_extract_content

                result = safe_llm_invoke(llm, [{"role": "user", "content": weighted_prompt}])
                raw = safe_extract_content(result)

                if raw and len(raw.strip()) > 10:
                    json_str = _json_strip_inline(raw)
                    parsed = json.loads(json_str)
                    if _MOA_OUTPUT_SCHEMA.issubset(parsed.keys()):
                        action, confidence, probs, reasoning, key_factors = _validate_moa_output(parsed)
                    else:
                        logger.warning(
                            "[IBRefinement] 轮#%d schema不完整: %s, 用默认",
                            iteration_num, list(parsed.keys()),
                        )
                        action, confidence, probs, reasoning, key_factors = "hold", 0.5, [1/3]*3, "schema缺失", []
                else:
                    logger.warning("[IBRefinement] 轮#%d LLM返回空", iteration_num)
                    action, confidence, probs, reasoning, key_factors = "hold", 0.3, [1/3]*3, "LLM返回空", []
            except Exception as e:
                logger.warning("[IBRefinement] 轮#%d 异常: %s", iteration_num, e)
                action, confidence, probs, reasoning, key_factors = "hold", 0.3, [1/3]*3, f"异常: {e}", []

            # 步骤4: 记录决策轨迹
            att_map = attention.get("attention", {}) or {}
            dominant_module = max(att_map.items(), key=lambda x: x[1])[0] if att_map else "unknown"
            trace_entry = {
                "iteration": iteration_num,
                "action": action,
                "confidence": confidence,
                "dominant_module": dominant_module,
            }
            decision_trace.append(trace_entry)

            logger.info(
                "[IBRefinement] 轮#%d: action=%s conf=%.3f dom=%s",
                iteration_num, action, confidence, dominant_module,
            )

            # 步骤5: 检查收敛
            converged, conv_info = check_convergence(decision_trace)
            if converged:
                logger.info(
                    "[IBRefinement] ✅ 收敛于第%d轮: %s (原因: %s)",
                    iteration_num, action, conv_info.get("reason", ""),
                )
                # 输出最终决策
                best = max(decision_trace, key=lambda x: x["confidence"])
                return _build_refinement_output(
                    best, conv_info, probs, reasoning, key_factors, decision_trace, workspace,
                )

            # 未收敛 → 为下轮准备: 将本轮 MoA 输出注入 workspace
            workspace["_moa_feedback"] = {
                "action": action,
                "confidence": confidence,
                "probs": probs,
                "reasoning": reasoning[:200],
                "dominant_module": dominant_module,
            }
            workspace["_meta"] = {"iteration": iteration_num, "max_iterations": max_iter, "converged": False}
            state["global_workspace"] = workspace
            state["attention_allocation"] = attention
            state["decision_trace"] = decision_trace

        # ===== 达到最大迭代 — 取置信度最高的输出 =====
        best = max(decision_trace, key=lambda x: x["confidence"]) if decision_trace else trace_entry
        logger.info(
            "[IBRefinement] ⏹️ 达最大迭代(%d轮), 取最高: %s(conf=%.3f)",
            max_iter, best["action"], best["confidence"],
        )
        best_probs = best.get("probs", [1/3]*3)
        if not isinstance(best_probs, (list, tuple)) or len(best_probs) != 3:
            best_probs = [1/3]*3
        return _build_refinement_output(
            best, {"reason": f"max_iterations({max_iter})"},
            best_probs, best.get("reasoning", ""), [],
            decision_trace, workspace,
        )

    def _build_refinement_output(
        best: dict,
        conv_info: dict,
        probs: list[float],
        reasoning: str,
        key_factors: list[str],
        trace: list,
        ws: dict,
    ) -> dict:
        """构建 IterativeRefinement 的最终输出。"""
        _trace = list(trace) if trace else [best]
        return {
            "global_workspace": ws,
            "decision_trace": _trace,
            "fused_decision": {
                "decision": best["action"],
                "confidence": best["confidence"],
                "probabilities": probs,
                "source": "moa_iterative_refinement",
                "reasoning": reasoning[:2000] if reasoning else best.get("reasoning", ""),
                "key_factors": key_factors or best.get("key_factors", []),
                "convergence_info": conv_info,
                "n_iterations": len(_trace),
                "decision_trace": [{"action": t.get("action"), "confidence": t.get("confidence"),
                                    "dominant_module": t.get("dominant_module")} for t in _trace],
            },
        }

    ib_refinement_node.__name__ = "IterativeRefinement"
    return ib_refinement_node


# ========== [Plan C] 路由函数 ==========


def create_cognitive_diagnostic_node() -> Callable:
    """创建认知诊断节点 — 分析 workspace/attention/trace 生成结构化诊断。

    位置: IterativeRefinement 之后, DaoistCenter 之前
    输出: cognitive_diagnosis dict (被 risk_manager.py 消费)

    诊断内容:
    - top_module: 注意力最高的模块
    - n_iterations: 迭代轮数
    - converged: 是否收敛
    - attention_entropy: 注意力熵 (0=极端集中, ~1.8=均匀)
    - conflict: 模块间 Jensen-Shannon 散度
    - workspace_missing: 预期模块中缺失的
    - health_status: overall status
    - warnings: 告警列表

    参考:
    - Baars 1988 全局工作空间理论: consciousness = global workspace content
    - Dehaene 2001: 注意是意识的门户
    - 物演通论: 系统复杂度越高, 自我诊断代偿必须越强
    """
    def cognitive_diagnostic_node(state: dict) -> dict:
        _t0 = time.time()

        workspace = state.get("global_workspace", {}) or {}
        attention = state.get("attention_allocation", {}) or {}
        trace = state.get("decision_trace", []) or []

        if not isinstance(workspace, dict):
            workspace = {}
        if not isinstance(attention, dict):
            attention = {}
        if not isinstance(trace, list):
            trace = []

        # 1. 注意力分析: 哪个模块获得最高关注
        att_map = attention.get("attention", {}) or {}
        top_module = max(att_map.items(), key=lambda x: x[1])[0] if att_map else "unknown"
        top_weight = max(att_map.values()) if att_map else 0.0

        # 2. 迭代分析: 轮数和收敛状态
        n_iterations = len(trace)
        converged = False
        trace_actions: list[str] = []
        if trace and len(trace) >= 2:
            valid_entries = [t for t in trace if isinstance(t, dict)]
            if len(valid_entries) >= 2:
                last = valid_entries[-1]
                prev = valid_entries[-2]
                trace_actions = [t.get("action", "?") for t in valid_entries]
                converged = last.get("action") == prev.get("action")

        # 3. 注意力熵和冲突 (从 attention_allocation 读取)
        att_entropy = attention.get("_entropy", 0.0)
        conflict = attention.get("_conflict", 0.0)
        if not isinstance(att_entropy, (int, float)):
            att_entropy = 0.0
        if not isinstance(conflict, (int, float)):
            conflict = 0.0

        # 4. workspace 完整性检查
        expected_modules = {"trader", "diffusion", "aif", "hsrc_mc", "l_iwm", "hpc", "analysts"}
        workspace_missing = sorted([m for m in expected_modules if m not in workspace])

        # 5. 健康状态 (分类而非连续评分)
        health_status = "healthy"
        if n_iterations == 0:
            health_status = "no_iterations"
        elif att_entropy > 1.5:
            health_status = "attention_diffuse"
        elif conflict > 0.5:
            health_status = "high_conflict"
        elif top_weight > 0.8:
            health_status = "attention_overfocused"

        # 6. 告警列表
        warnings: list[str] = []
        if n_iterations == 0:
            warnings.append("IterativeRefinement 未产生迭代轨迹")
        if workspace_missing:
            warnings.append(f"workspace 缺失模块: {workspace_missing}")
        if conflict > 0.8:
            warnings.append(f"模块间冲突极高 ({conflict:.3f})")
        if att_entropy < 0.05:
            warnings.append("注意力极端集中 (熵≈0)")
        if top_weight > 0.95:
            warnings.append(f"单模块主导: {top_module}={top_weight:.3f}")

        diagnosis = {
            "top_module": top_module,
            "top_weight": float(top_weight),
            "n_iterations": n_iterations,
            "converged": converged,
            "trace_actions": trace_actions,
            "attention_entropy": float(att_entropy),
            "conflict": float(conflict),
            "workspace_missing": workspace_missing,
            "health_status": health_status,
            "warnings": warnings,
            "elapsed": time.time() - _t0,
        }

        logger.info(
            "[CognitiveDiagnostic] 诊断完成: top=%s(%.3f), "
            "iters=%d, conv=%s, entropy=%.3f, conflict=%.3f, health=%s",
            top_module, top_weight,
            n_iterations, converged, att_entropy, conflict, health_status,
        )
        if warnings:
            logger.warning(
                "[CognitiveDiagnostic] 警告: %s",
                "; ".join(warnings),
            )

        return {"cognitive_diagnosis": diagnosis}

    cognitive_diagnostic_node.__name__ = "CognitiveDiagnostic"
    return cognitive_diagnostic_node


def _route_from_ib_refinement(state: dict) -> str:
    """根据 IterativeRefinement 的输出路由。

    返回:
        "to_daoist_center" — 正常路径
        "fallback_to_bma" — IterativeRefinement 失败
    """
    fused = state.get("fused_decision", None)
    if fused is None:
        logger.warning("[Route] IterativeRefinement 无输出, 回退 BMA")
        return "fallback_to_bma"

    source = str(fused.get("source", ""))
    if "moa_iterative" in source:
        return "to_daoist_center"

    # 非迭代 MoA 或 BMA 输出 → 仍然传给道家中枢检查
    if "moa" in source or "bma" in source:
        return "to_daoist_center"

    return "fallback_to_bma"


def _route_from_daoist_center(state: dict) -> str:
    """根据 DaoistCenter 输出路由。

    返回:
        "to_risky_analyst" — 空信号决策或正常输出 → 传给风控
        "fallback_to_bma" — 异常状态
    """
    fused = state.get("fused_decision", None)

    # DaoistCenter 触发了空信号 → 已有决策 (hold)
    if isinstance(fused, dict) and fused.get("daoist_triggered"):
        logger.info("[Route] ☯️ DaoistCenter 空信号, 传给 Risky Analyst")
        return "to_risky_analyst"

    # 正常 fused_decision (MoA 或 BMA)
    if isinstance(fused, dict) and fused.get("decision"):
        logger.info("[Route] ✅ 正常决策, 传给 Risky Analyst")
        return "to_risky_analyst"

    # 退化
    logger.warning("[Route] 异常状态, 回退 BMA")
    return "fallback_to_bma"


def _route_to_risky_analyst_plan_c(state: dict) -> str:
    """统一路由到 Risky Analyst (或回退 BMA)。

    这是 Section C 最终路由, 接收 DaoistCenter 之后的输出。
    """
    fused = state.get("fused_decision", None)
    if isinstance(fused, dict) and fused.get("decision"):
        return "to_risky"
    return "to_fallback"


def fusion_node(state) -> dict:
    """
    BMA 贝叶斯模型平均融合节点

    融合 3 个来源的决策:
      1. 交易员 (Trader) — 从 trader_investment_plan 文本提取
      2. 扩散模型 (Diffusion) — 从 diffusion_decision 读取
      3. AIF-EFE (来自融合点 #1) — 从融合点 #1 的输出读取

    权重由各模型置信度和配置参数共同决定。
    """
    eps = 1e-30
    trader_plan = state.get("trader_investment_plan", "")
    diff_decision = state.get("diffusion_decision", {})

    # ===== 退化检测（保留旧逻辑）=====
    is_degraded = diff_decision.get("degraded", False)
    confidence = diff_decision.get("confidence", 0.0)
    timestamp_str = diff_decision.get("timestamp", None)
    is_stale = False
    if timestamp_str:
        try:
            ts = datetime.fromisoformat(timestamp_str)
            age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
            if age_seconds > 300:
                is_stale = True
        except (ValueError, TypeError):
            pass

    if not diff_decision or confidence <= 0.0 or is_stale:
        reasons = []
        if not diff_decision: reasons.append("空决策")
        if confidence <= 0.0: reasons.append(f"confidence={confidence}")
        if is_stale: reasons.append("时间戳过期")
        logger.info("[Fusion-BMA] 扩散决策退化 (%s)，使用交易员+BMA可用信号", ", ".join(reasons))
        # 退化为仅使用交易员 + AIF（如果有）
        diff_probs = [1/3, 1/3, 1/3]
        w_diff = 0.0
    else:
        # 扩散模型概率（来自 Phase 1.3 增强）
        diff_probs = diff_decision.get("action_probs", [1/3, 1/3, 1/3])
        diff_conf = diff_decision.get("confidence", 0.0)
        diffusion_weight_config = state.get("diffusion_weight", 0.4)  # L3: 从 config 读取
        w_diff = min(diff_conf * 0.5, diffusion_weight_config)  # L3: 使用配置权重而非硬编码 0.4

    # ===== 信号 1: 交易员 =====
    trader_probs = _extract_trader_probs(trader_plan)
    w_trader = 0.35  # 固定权重（将被动态权重调制）

    # ===== 信号 2: 扩散模型 =====
    # diff_probs + w_diff 已在上方获取

    # ===== 信号 3: AIF-EFE（来自融合点 #1） =====
    fusion_efe = state.get("fusion_efe_scores", {})
    if fusion_efe and isinstance(fusion_efe, dict):
        efe_vals = [fusion_efe.get(a, 0.0) for a in ("buy", "sell", "hold")]
        e = np.array(efe_vals, dtype=np.float64)
        # EFE 越小越好 → softmin
        efe_probs = np.exp(-e) / (np.exp(-e).sum() + eps)
        aif_probs = efe_probs.tolist()
        w_aif = 0.25
    else:
        aif_probs = [1/3, 1/3, 1/3]
        w_aif = 0.0

    # ===== L8: 动态权重校准（从历史准确率追踪器读取） =====
    # 在冷启动时返回等权重 → 不影响现有逻辑
    # 积累数据后校准各模块的相对权重
    try:
        from tradingagents.graph.fusion_weight_tracker import fusion_tracker
        _tw = fusion_tracker.get_weights()
        # scale_factor = 相对均匀值的倍数（冷启动=1.0，有数据后漂移）
        _scale_t = _tw.get("trader", 1/3) * 3
        _scale_d = _tw.get("diffusion", 1/3) * 3
        _scale_a = _tw.get("aif", 1/3) * 3
        w_trader = w_trader * _scale_t
        w_diff = w_diff * _scale_d
        w_aif = w_aif * _scale_a
        logger.info("[Fusion-BMA] 📊 动态权重校准: 原={trader=%.3f,diff=%.3f,aif=%.3f} "
                     "调后={trader=%.3f,diff=%.3f,aif=%.3f} (scale=%s)",
                     0.35, w_diff / _scale_d if _scale_d > 0 else 0,
                     w_aif / _scale_a if _scale_a > 0 else 0,
                     w_trader, w_diff, w_aif,
                     f"t={_scale_t:.2f},d={_scale_d:.2f},a={_scale_a:.2f}")
    except Exception:
        pass  # 追踪器不可用不影响核心逻辑

    # ===== BMA 融合 =====
    log_fused = np.zeros(3)
    for i in range(3):
        log_fused[i] = (
            w_trader * np.log(trader_probs[i] + eps)
            + w_diff * np.log(diff_probs[i] + eps)
            + w_aif * np.log(aif_probs[i] + eps)
        )
    # 如果所有权重为0 → 检查 Soft Gate 是否允许非均匀退火
    if w_trader + w_diff + w_aif < eps:
        sg = state.get("_soft_gate_score", 0.0)
        if sg >= 0.2:
            fused_probs = [float(p) for p in trader_probs]
            logger.info("[Fusion-BMA] ⚡ Soft Gate 退火: 使用交易员信号 (sg=%.3f)", sg)
        else:
            fused_probs = [1/3, 1/3, 1/3]
    else:
        log_fused -= np.max(log_fused)  # 数值稳定
        fused_probs = (np.exp(log_fused) / (np.exp(log_fused).sum() + eps)).tolist()

    best_idx = int(np.argmax(fused_probs))
    action_map = ["buy", "sell", "hold"]

    logger.info(
        "[Fusion-BMA] ✅ 融合完成: action=%s, confidence=%.4f, "
        "weights={trader=%.3f, diffusion=%.3f, aif=%.3f}",
        action_map[best_idx],
        fused_probs[best_idx],
        w_trader, w_diff, w_aif,
    )

    return {
        "fused_decision": {
            "decision": action_map[best_idx],
            "confidence": float(fused_probs[best_idx]),
            "probabilities": [float(p) for p in fused_probs],
            "weights": {"trader": w_trader, "diffusion": w_diff, "aif": w_aif},
            "fusion_weight": float(fused_probs[best_idx]),  # L1: 标量键，兼容旧消费者
            "trader_weight": w_trader,
            "diff_weight": w_diff,
            "source": "bma_fusion",
        },
    }


# ========== AIF 推理迭代循环路由函数 ==========
def aif_should_continue_iteration(state) -> str:
    """判断 AIF 推理迭代是否应继续

    读取 state 中的 _aif_iteration_count 和 _aif_max_iterations，
    当当前迭代次数 < 最大迭代次数时返回 "continue_iteration" 进入下一轮，
    否则返回 "exit_iteration" 退出循环进入 DiffusionAdvisor 模块。

    Returns:
        str: "continue_iteration" 或 "exit_iteration"
    """
    iteration = state.get("_aif_iteration_count", 0)
    max_iter = state.get("_aif_max_iterations", AIF_MAX_ITERATIONS)

    if iteration < max_iter:
        logger.info(f"[AIF Loop] 迭代 {iteration + 1}/{max_iter} — 继续循环")
        return "continue_iteration"
    logger.info(f"[AIF Loop] ✅ 迭代完成 ({iteration}/{max_iter}) — 退出循环，进入 DiffusionAdvisor")
    return "exit_iteration"


# ========== AIF_UpdateBelief 条件路由 (P0 扇出 Bug 修复) ==========
def aif_route_from_update_belief(state) -> str:
    """AIF_UpdateBelief 的条件路由，解决 P0 扇出 Bug (H12)

    区分两条路径:
    - 分析师管线路径 (_aif_iteration_count == 0): AIF_UpdateBelief → Bull Researcher
    - AIF 迭代循环路径 (_aif_iteration_count > 0): AIF_UpdateBelief → AIF_Observe

    设计原理:
        _aif_iteration_count 在 AIF_SelectAction_Evaluate 节点中递增 (aif_integration.py:671)，
        因此 AIF_UpdateBelief 被调用时:
        - count == 0: 来自分析师管线，应进入研究员+辩论流程
        - count > 0:  来自 AIF 循环，应继续迭代

    🐛 [Bug 3 修复] 迭代循环不再路由到 AIF_Predict，改为路由到 AIF_Observe。
        AIF_Predict 有两条静态出边 (→AIF_LLMPrior/News Analyst, →AIF_Observe)，
        路由到 AIF_Predict 会导致 LangGraph 扇出，同时执行分析师管线路径，
        重启全流程管线，造成无限循环。
        改为路由到 AIF_Observe 后，AIF_Predict 仅在首次入口被访问，
        迭代循环完全绕过 AIF_Predict，杜绝扇出可能。

    🐛 [Bug 4 修复] 当 _aif_iteration_count >= _aif_max_iterations 时，
        也路由到 exit_iteration，防止外部无限循环。
        问题场景: AIF 循环正常退出后 (count >= max)，主流程 (Section B)
        通过 HPC_PredictionError → AIF_Observe → AIF_UpdateBelief 再次触发，
        此时 count > 0 但已达到最大迭代，应退出而非继续循环。

    Returns:
        str: "exit_iteration" → Bull Researcher, "continue_iteration" → AIF_Observe
    """
    iteration = state.get("_aif_iteration_count", 0)
    max_iter = state.get("_aif_max_iterations", AIF_MAX_ITERATIONS)
    if iteration == 0 or iteration >= max_iter:
        if iteration == 0:
            logger.info("[AIF Route] 分析师管线路径 → exit_iteration (Bull Researcher)")
        else:
            logger.info(f"[AIF Route] AIF 循环已达最大迭代 ({iteration}/{max_iter}) → exit_iteration (Bull Researcher)")
        return "exit_iteration"
    logger.info(f"[AIF Route] AIF 循环路径 (iter={iteration}/{max_iter}) → continue_iteration (AIF_Observe)")
    return "continue_iteration"


# ========== AIF_Observe 条件路由 (Bug-New-006 修复: 双静态出边) ==========
def _route_aif_observe(state) -> str:
    """AIF_Observe 条件路由，解决双静态出边导致的 InvalidUpdateError (Bug-New-006)

    AIF_Observe 在 Fusion 模式中可能被两条路径同时访问:
    - 首次通过 (Section B, _aif_iteration_count == 0): HPC_PredictionError → AIF_Observe → AIF_UpdateBelief
    - 迭代循环 (Section C, _aif_iteration_count > 0): AIF_UpdateBelief → AIF_Observe → AIF_LLMPrior

    两条静态出边会导致 LangGraph 在同一 superstep 中并行写入 aif_state，
    从而触发 "Can receive only one value per step" 错误。

    此条件边确保同一时间只有一条出边生效，完全串行化 AIF_Observe 的出边。

    Returns:
        str: "AIF_UpdateBelief" (首次通过) 或 "AIF_LLMPrior" (迭代循环)
    """
    _aif_iter = state.get("_aif_iteration_count", 0)
    if _aif_iter == 0:
        logger.info("[AIF Route] AIF_Observe 首次通过路径 → AIF_UpdateBelief")
        return "AIF_UpdateBelief"
    logger.info(f"[AIF Route] AIF_Observe 迭代循环路径 (iter={_aif_iter}) → AIF_LLMPrior")
    return "AIF_LLMPrior"


# ========== AIF_LLMPrior 条件路由 (Bug 3b 修复: 双出边扇出) ==========
def aif_route_from_llm_prior(state) -> str:
    """AIF_LLMPrior 的条件路由，解决 AIF_LLMPrior 双出边扇出 Bug (Bug 3b)

    区分两条路径:
    - 首次通过路径 (_aif_iteration_count == 0): AIF_LLMPrior → 分析师管线
    - AIF 迭代循环路径 (_aif_iteration_count > 0): AIF_LLMPrior → AIF_SelectAction_Evaluate

    设计原理:
        LangGraph 不允许一个节点有两条静态出边，这会被解释为并行扇出。
        AIF_LLMPrior 的首次通过路径和迭代循环路径是互斥的，必须用条件边统一路由。

    Returns:
        str: "to_analyst_pipeline" → 分析师管线, "to_aif_evaluate" → AIF_SelectAction_Evaluate
    """
    iteration = state.get("_aif_iteration_count", 0)
    if iteration == 0:
        logger.info("[AIF Route] AIF_LLMPrior 首次通过路径 → to_analyst_pipeline")
        return "to_analyst_pipeline"
    logger.info(f"[AIF Route] AIF_LLMPrior 迭代循环路径 (iter={iteration}) → to_aif_evaluate")
    return "to_aif_evaluate"


# ========== 扩散路由守卫 ==========
def _route_to_risky_analyst(workflow, all_node_names, source_node):
    """路由经过 DiffusionAdvisor → MoASynthesizer（LLM 综合）→ Risky Analyst

    这是并行顾问 + MoA 综合器模式的核心路由策略:
    - 优先走扩散+MoA分支: source → DiffusionAdvisor → MoASynthesizer → Risky Analyst
    - 退化路径: source → Risky Analyst (扩散不可用时)
    若 MoASynthesizer 内部失败，自动回退到 BMA 数值融合。
    """
    if "DiffusionAdvisor" in all_node_names:
        workflow.add_edge(source_node, "DiffusionAdvisor")
        workflow.add_edge("DiffusionAdvisor", "MoASynthesizer")
        workflow.add_edge("MoASynthesizer", "Risky Analyst")
    else:
        workflow.add_edge(source_node, "Risky Analyst")


# ⚡ [RaceGuard] ToolNode 前置保护包装函数
def _create_defensive_tool_node(tool_node, analyst_type: str):
    """创建带前置保护的 ToolNode 包装器。

    在 ToolNode 执行前检查 messages 中是否存在含 tool_calls 的 AIMessage。
    如果缺失（可能因并发竞态导致消息被清除），则返回空 dict 避免
    "No AIMessage found in input" ValueError。

    🔧 [Bug Fix H6] 安全网：当跳过 ToolNode 时，如果消息历史中存在未配对
    tool_calls（AIMessage 的 tool_calls 已被之前的 Msg Clear 清除但其
    ToolMessage 仍残留），则生成对应的占位 ToolMessage，防止这些孤立
    ToolMessage 污染后续分析导致 DeepSeek API 400 错误。

    Args:
        tool_node: 原始 ToolNode 实例
        analyst_type: 分析师类型（"market"/"social"/"news"/"fundamentals"）

    Returns:
        包装后的节点函数（兼容 LangGraph node 签名）
    """

    def defensive_tool_node(state, config=None):
        from tradingagents.agents.utils.agent_utils import clean_orphaned_tool_calls

        messages = state.get("messages", [])
        has_ai_with_tool_calls = any(hasattr(msg, "tool_calls") and msg.tool_calls for msg in messages)
        if not has_ai_with_tool_calls:
            logger.warning(
                f"🛡️ [RaceGuard] 分析师[{analyst_type}] ToolNode 前置保护触发："
                f"消息列表中未找到含 tool_calls 的 AIMessage "
                f"(共 {len(messages)} 条消息)，跳过工具执行",
            )
            # 🔧 [Bug Fix H6] 清理消息中残留的孤立 tool_calls（如果存在），
            # 防止后续分析节点因 DeepSeek API 校验不通过而报 400 错误。
            # 注意：不返回 cleaned 消息到 state（这里无法修改 state），
            # 依赖各分析师节点的 clean_orphaned_tool_calls 来实际清理。
            cleaned = clean_orphaned_tool_calls(messages)
            if len(cleaned) != len(messages):
                logger.warning(
                    f"🛡️ [RaceGuard] 分析师[{analyst_type}] 消息列表中发现孤立 tool_calls，"
                    f"已清理 (共 {len(messages)}→{len(cleaned)} 条)",
                )
            return {}
        return tool_node.invoke(state)

    return defensive_tool_node


# ========================================================================
# [方案A Part 2] 通道类型强制转换安全网
# ========================================================================
def _force_channel_to_binary_operator_aggregate(
    channels: dict,
    channel_name: str,
    reducer_name: str,
) -> bool:
    """
    强制将指定通道转换为 BinaryOperatorAggregate 类型。

    用于 LangGraph 0.6.x 中 Annotated 类型解析错误的补偿修复:
        Annotated[str, _report_reducer] 被错误解析为 LastValue 而非
        BinaryOperatorAggregate，导致多节点并发写入时抛出:
        "Can receive only one value per step. Use an Annotated key to handle multiple values."

    LangGraph >= 0.7.0 已修复此解析问题，此函数仅作为降级安全网。

    Returns:
        True 表示转换成功，False 表示无需转换或转换失败。
    """
    channel = channels.get(channel_name)
    if channel is None:
        return False

    type_name = type(channel).__name__
    if "BinaryOperator" in type_name:
        return False  # 通道类型已正确

    logger.warning(f"🔄 强制转换通道 [{channel_name}]: {type_name} → BinaryOperatorAggregate")

    try:
        from langgraph.channels.binop import BinaryOperatorAggregate

        from tradingagents.agents.utils.agent_states import (
            _counter_reducer,
            _report_reducer,
        )

        reducer_map = {
            "_report_reducer": (_report_reducer, str),
            "_counter_reducer": (_counter_reducer, int),
        }
        reducer_entry = reducer_map.get(reducer_name)
        if reducer_entry is None:
            logger.warning(f"⚠️ 无法确定 [{channel_name}] 的 reducer ({reducer_name})，跳过强制转换")
            return False
        reducer_func, channel_type = reducer_entry
        new_channel = BinaryOperatorAggregate(typ=channel_type, operator=reducer_func)
        channels[channel_name] = new_channel
        logger.info(f"✅ 已强制转换 [{channel_name}] 为 BinaryOperatorAggregate")
        return True
    except ImportError:
        logger.warning(
            "⚠️ langgraph.channels.binop.BinaryOperatorAggregate 不可用 "
            "(可能 LangGraph 版本不支持 BinaryOperatorAggregate)，跳过强制转换",
        )
        return False
    except Exception as e:
        logger.warning(f"⚠️ 强制转换 [{channel_name}] 失败: {e}")
        return False


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        toolkit: Toolkit,
        tool_nodes: dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
        config: dict[str, Any] | None = None,
        react_llm=None,
        hpc_loop_manager: HPCLoopManager | None = None,
        aif_engine_manager: AIFEngineManager | None = None,
        use_fusion_mode: bool = False,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.toolkit = toolkit
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.config = config or {}
        self.react_llm = react_llm
        self.hpc_loop = hpc_loop_manager
        self.aif_engine = aif_engine_manager
        self.use_fusion_mode = use_fusion_mode

    def setup_graph(self, selected_analysts=None) -> CompiledStateGraph:
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        if not selected_analysts:
            selected_analysts = ["market", "social", "news", "fundamentals"]

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            # 现在所有LLM都使用标准市场分析师（包括阿里百炼的OpenAI兼容适配器）
            llm_provider = self.config.get("llm_provider", "").lower()

            # 检查是否使用OpenAI兼容的阿里百炼适配器
            using_dashscope_openai = (
                "dashscope" in llm_provider
                and hasattr(self.quick_thinking_llm, "__class__")
                and "OpenAI" in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug("📈 [DEBUG] 使用标准市场分析师（阿里百炼OpenAI兼容模式）")
            elif "dashscope" in llm_provider or "阿里百炼" in self.config.get("llm_provider", ""):
                logger.debug("📈 [DEBUG] 使用标准市场分析师（阿里百炼原生模式）")
            elif "deepseek" in llm_provider:
                logger.debug("📈 [DEBUG] 使用标准市场分析师（DeepSeek）")
            else:
                logger.debug("📈 [DEBUG] 使用标准市场分析师")

            # 所有LLM都使用标准分析师
            analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm, self.toolkit)
            # ⚡ [RaceGuard] 传入 analyst_type 启用并发安全消息清除
            delete_nodes["market"] = create_msg_delete(analyst_type="market")
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(self.quick_thinking_llm, self.toolkit)
            # ⚡ [RaceGuard] 传入 analyst_type 启用并发安全消息清除
            delete_nodes["social"] = create_msg_delete(analyst_type="social")
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(self.quick_thinking_llm, self.toolkit)
            # ⚡ [RaceGuard] 传入 analyst_type 启用并发安全消息清除
            delete_nodes["news"] = create_msg_delete(analyst_type="news")
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            # 现在所有LLM都使用标准基本面分析师（包括阿里百炼的OpenAI兼容适配器）
            llm_provider = self.config.get("llm_provider", "").lower()

            # 检查是否使用OpenAI兼容的阿里百炼适配器
            using_dashscope_openai = (
                "dashscope" in llm_provider
                and hasattr(self.quick_thinking_llm, "__class__")
                and "OpenAI" in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug("📊 [DEBUG] 使用标准基本面分析师（阿里百炼OpenAI兼容模式）")
            elif "dashscope" in llm_provider or "阿里百炼" in self.config.get("llm_provider", ""):
                logger.debug("📊 [DEBUG] 使用标准基本面分析师（阿里百炼原生模式）")
            elif "deepseek" in llm_provider:
                logger.debug("📊 [DEBUG] 使用标准基本面分析师（DeepSeek）")
            else:
                logger.debug("📊 [DEBUG] 使用标准基本面分析师")

            # 所有LLM都使用标准分析师（包含强制工具调用机制）
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(self.quick_thinking_llm, self.toolkit)
            # ⚡ [RaceGuard] 传入 analyst_type 启用并发安全消息清除
            delete_nodes["fundamentals"] = create_msg_delete(analyst_type="fundamentals")
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(self.deep_thinking_llm, self.invest_judge_memory)
        # [FIX] 2026-06-18 P3: trader_node 零输出守卫包装
        _trader_node_raw = create_trader(self.quick_thinking_llm, self.trader_memory)

        def _guarded_trader_node(state):
            """带零输出守卫的 trader_node"""
            result = _trader_node_raw(state)
            if not result or not isinstance(result, dict):
                logger.warning("[FIX] 2026-06-18 P3: 零输出守卫触发 — trader_node 返回空结果，注入安全默认值")
                return {
                    "messages": [],
                    "trader_investment_plan": "默认投资计划：基于当前市场数据，建议持有观望，等待更明确的信号。",
                    "sender": "Trader",
                }
            plan = result.get("trader_investment_plan", "")
            if not plan or not isinstance(plan, str) or not plan.strip():
                logger.warning("[FIX] 2026-06-18 P3: 零输出守卫触发 — trader_investment_plan 为空，注入安全默认值")
                result["trader_investment_plan"] = "默认投资计划：基于当前市场数据，建议持有观望，等待更明确的信号。"
            return result

        trader_node = _guarded_trader_node

        # Create risk analysis nodes
        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(self.deep_thinking_llm, self.risk_manager_memory)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            # ⚡ [RaceGuard] 使用带前置保护的 ToolNode 包装器
            defensive_node = _create_defensive_tool_node(tool_nodes[analyst_type], analyst_type)
            workflow.add_node(f"tools_{analyst_type}", defensive_node)

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # ========== 融合架构 (Fusion) 路由优先级: use_unified > use_aif > hpc_enabled > else ==========
        use_unified = self.use_fusion_mode
        # 🔧 [Bug Fix] hpc_enabled/use_aif 同时检查主配置键，避免关闭后仍被激活
        _hpc_conf_enabled = self.config.get("hpc_loop_enabled", True)
        _aif_conf_enabled = self.config.get("use_aif_engine", True)
        use_aif = self.aif_engine is not None and _aif_conf_enabled and (use_unified or self.aif_engine.enabled)
        hpc_enabled = self.hpc_loop is not None and _hpc_conf_enabled and (use_unified or self.hpc_loop.enabled)

        # --- Fusion / AIF 引擎节点集成 ---
        if use_aif:
            aif_nodes = self.aif_engine.get_aif_nodes()
            for node_name, node_fn in aif_nodes.items():
                workflow.add_node(node_name, node_fn)
            logger.info(f"[AIF] add {len(aif_nodes)} AIF engine nodes (fusion={use_unified})")

        # --- HPC-Loop 节点集成 (含 L-IWM / HSR-MC 扩展) ---
        if hpc_enabled:
            hpc_nodes = self.hpc_loop.get_enhanced_nodes()
            for node_name, node_fn in hpc_nodes.items():
                workflow.add_node(node_name, node_fn)
            logger.info(f"[HPC] add {len(hpc_nodes)} HPC-Loop nodes (fusion={use_unified})")

        # --- Phase 3: 扩散模块 + MoA 综合器节点集成 ---
        diffusion_enabled = self.config.get("diffusion_enabled", True)
        if diffusion_enabled and _DIFFUSION_AVAILABLE:
            workflow.add_node("DiffusionAdvisor", diffusion_advisor_node)
            # [Plan C] 认知架构节点注册
            # 1. MoA 综合器 — 仍保留作为 IterativeRefinement 的内核
            moa_node = create_moa_synthesizer_node(self.deep_thinking_llm)
            workflow.add_node("MoASynthesizer", moa_node)
            # 2. 全局工作空间填充器
            ws_populator = create_workspace_populator()
            workflow.add_node("GlobalWorkspacePopulate", ws_populator)
            # 3. 注意力分配器
            att_node = create_attention_allocator_node()
            workflow.add_node("AttentionAllocator", att_node)
            # 4. 迭代信念精炼（替代 MoA 综合器作为主融合节点）
            refine_node = create_iterative_belief_refinement(self.deep_thinking_llm)
            workflow.add_node("IterativeRefinement", refine_node)
            # 5. 认知诊断 (新增: 分析 workspace/attention/trace 生成诊断)
            diag_node = create_cognitive_diagnostic_node()
            workflow.add_node("CognitiveDiagnostic", diag_node)
            # 6. 道家中枢
            daoist_node = create_daoist_center()
            workflow.add_node("DaoistCenter", daoist_node)
            # 7. BMA 数值融合 — 保留为最终退化路径
            workflow.add_node("FusionNode", fusion_node)
            logger.info(
                "[Plan C] 注册认知架构节点: GlobalWorkspacePopulate + "
                "AttentionAllocator + IterativeRefinement + CognitiveDiagnostic + DaoistCenter "
                "(degradation: IterativeRefinement → BMA → uniform)"
            )
        else:
            logger.info(
                "[Diffusion] 扩散模块未启用或不可用 (enabled=%s, available=%s)", diffusion_enabled, _DIFFUSION_AVAILABLE,
            )

        # 获取所有已注册节点名，用于边缘可用性守卫（防止节点因初始化失败缺失导致编译崩溃）
        all_node_names = set(workflow.nodes.keys())
        HSRC_NODES = {"hsrc_observe", "hsrc_adjust", "hsrc_reflect", "hsrc_meta_update"}

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]

        # ========== Section A: START 路由 (3 层优先级 + 节点存在性守卫) ==========
        if use_unified:
            # Fusion: START → HPC_Predict → AIF_Predict → AIF_LLMPrior → 分析师
            # 🐛 [Bug Fix] 添加 all_node_names 守卫，防止 AIF/HPC 节点未注册时加边导致编译崩溃
            if "HPC_Predict" in all_node_names:
                workflow.add_edge(START, "HPC_Predict")
                if "AIF_Predict" in all_node_names:
                    workflow.add_edge("HPC_Predict", "AIF_Predict")
                    if "AIF_LLMPrior" in all_node_names:
                        workflow.add_edge("AIF_Predict", "AIF_LLMPrior")
                        # 🐛 [Bug 3b 修复] 用条件边替代静态边，解决 AIF_LLMPrior 双出边扇出问题。
                        # AIF_LLMPrior 同时被 Section A (首次入口) 和 Section C (迭代循环) 访问，
                        # 静态边会导致 LangGraph 扇出，同时执行分析师管线路径和评估路径，重启管线。
                        workflow.add_conditional_edges(
                            "AIF_LLMPrior",
                            aif_route_from_llm_prior,
                            {
                                "to_analyst_pipeline": f"{first_analyst.capitalize()} Analyst",
                                "to_aif_evaluate": "AIF_SelectAction_Evaluate",
                            },
                        )
                    else:
                        workflow.add_edge("AIF_Predict", f"{first_analyst.capitalize()} Analyst")
                else:
                    workflow.add_edge("HPC_Predict", f"{first_analyst.capitalize()} Analyst")
            else:
                workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")
        elif use_aif:
            if "AIF_Predict" in all_node_names:
                workflow.add_edge(START, "AIF_Predict")
                workflow.add_edge("AIF_Predict", f"{first_analyst.capitalize()} Analyst")
            else:
                workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")
        elif hpc_enabled and self.hpc_loop.config.generative_model_enabled:
            if "HPC_Predict" in all_node_names:
                workflow.add_edge(START, "HPC_Predict")
                workflow.add_edge("HPC_Predict", f"{first_analyst.capitalize()} Analyst")
            else:
                workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")
        else:
            workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            # ========== Section B: 分析师链后路由 (3 层优先级 + 节点存在性守卫) ==========
            elif use_unified:
                # Fusion: analyst_clear → HPC_GWS_Broadcast → [HSR-MC 段] → HPC_PredictionError
                #         → AIF_Observe → AIF_UpdateBelief → Bull Researcher
                # 🐛 [Bug Fix] 添加节点存在性守卫，防止 HPC/AIF 节点未注册时加边导致编译崩溃
                if "HPC_GWS_Broadcast" in all_node_names:
                    workflow.add_edge(current_clear, "HPC_GWS_Broadcast")

                    # ===== HSR-MC 链：独立于 prediction_error_enabled，始终注册（如果有）=====
                    hsrc_available = HSRC_NODES.issubset(all_node_names)
                    l_iwm_bridge_available = "HPC_LIWMBridge" in all_node_names
                    prediction_error_available = "HPC_PredictionError" in all_node_names

                    if hsrc_available:
                        # HPC_GWS_Broadcast → [HPC_LIWMBridge →] hsrc_observe → hsrc_adjust → hsrc_reflect → hsrc_meta_update
                        if l_iwm_bridge_available:
                            workflow.add_edge("HPC_GWS_Broadcast", "HPC_LIWMBridge")
                            workflow.add_edge("HPC_LIWMBridge", "hsrc_observe")
                        else:
                            workflow.add_edge("HPC_GWS_Broadcast", "hsrc_observe")
                        workflow.add_edge("hsrc_observe", "hsrc_adjust")
                        workflow.add_edge("hsrc_adjust", "hsrc_reflect")
                        workflow.add_edge("hsrc_reflect", "hsrc_meta_update")

                        # HSR-MC 链末端 → HPC_PredictionError（如果可用）或直接到 AIF/Bull
                        hsrc_chain_end = "hsrc_meta_update"
                    elif l_iwm_bridge_available:
                        # 无 HSR-MC，但有 L-IWM Bridge：GWS → LIWMBridge
                        workflow.add_edge("HPC_GWS_Broadcast", "HPC_LIWMBridge")
                        hsrc_chain_end = "HPC_LIWMBridge"
                    else:
                        # 无 HSR-MC 也无 Bridge：直接从 GWS 继续
                        hsrc_chain_end = "HPC_GWS_Broadcast"

                    # HSR-MC 链末端 → [HPC_PredictionError（如果可用）→] AIF/Bull
                    if prediction_error_available:
                        if hsrc_chain_end != "HPC_GWS_Broadcast":
                            workflow.add_edge(hsrc_chain_end, "HPC_PredictionError")
                        else:
                            workflow.add_edge("HPC_GWS_Broadcast", "HPC_PredictionError")
                        hsrc_chain_end = "HPC_PredictionError"

                    # 从链末端 → AIF（如果可用）→ Bull Researcher
                    if "AIF_Observe" in all_node_names:
                        # 从 hsrc_chain_end 连接到 AIF_Observe
                        # hsrc_chain_end 可能是: hsrc_meta_update / HPC_LIWMBridge / HPC_PredictionError / HPC_GWS_Broadcast
                        if hsrc_chain_end != "HPC_GWS_Broadcast":
                            workflow.add_edge(hsrc_chain_end, "AIF_Observe")
                        else:
                            workflow.add_edge("HPC_GWS_Broadcast", "AIF_Observe")
                        if "AIF_UpdateBelief" in all_node_names:
                            _aif_obs_ub_avail = "AIF_UpdateBelief" in all_node_names
                            _aif_obs_llm_avail = "AIF_LLMPrior" in all_node_names
                            if _aif_obs_ub_avail and _aif_obs_llm_avail:
                                workflow.add_conditional_edges(
                                    "AIF_Observe",
                                    _route_aif_observe,
                                    {
                                        "AIF_UpdateBelief": "AIF_UpdateBelief",
                                        "AIF_LLMPrior": "AIF_LLMPrior",
                                    },
                                )
                            elif _aif_obs_ub_avail:
                                workflow.add_edge("AIF_Observe", "AIF_UpdateBelief")
                            else:
                                workflow.add_edge("AIF_Observe", "Bull Researcher")
                            _aif_observe_avail = "AIF_Observe" in all_node_names
                            workflow.add_conditional_edges(
                                "AIF_UpdateBelief",
                                aif_route_from_update_belief,
                                {
                                    "continue_iteration": "AIF_Observe"
                                    if _aif_observe_avail
                                    else "Bull Researcher",
                                    "exit_iteration": "Bull Researcher",
                                },
                            )
                        else:
                            workflow.add_edge("AIF_Observe", "Bull Researcher")
                    else:
                        # 无 AIF：链末端直连 Bull Researcher
                        if hsrc_chain_end != "HPC_GWS_Broadcast":
                            workflow.add_edge(hsrc_chain_end, "Bull Researcher")
                        else:
                            workflow.add_edge("HPC_GWS_Broadcast", "Bull Researcher")
                else:
                    # HPC_GWS_Broadcast 不可用，直接路由到 Bull Researcher
                    workflow.add_edge(current_clear, "Bull Researcher")
            elif use_aif:
                if "AIF_LLMPrior" in all_node_names:
                    workflow.add_edge(current_clear, "AIF_LLMPrior")
                    if "AIF_Observe" in all_node_names:
                        workflow.add_edge("AIF_LLMPrior", "AIF_Observe")
                        if "AIF_UpdateBelief" in all_node_names:
                            workflow.add_edge("AIF_Observe", "AIF_UpdateBelief")
                            if "AIF_SelectAction" in all_node_names:
                                workflow.add_edge("AIF_UpdateBelief", "AIF_SelectAction")
                                workflow.add_edge("AIF_SelectAction", "Bull Researcher")
                            else:
                                workflow.add_edge("AIF_UpdateBelief", "Bull Researcher")
                        else:
                            workflow.add_edge("AIF_Observe", "Bull Researcher")
                    else:
                        workflow.add_edge("AIF_LLMPrior", "Bull Researcher")
                else:
                    workflow.add_edge(current_clear, "Bull Researcher")
            # [FIX 2026-06-26] Phase 1.5: 删除 HPC-only 路径（已废弃）
            # 现在只有 Fusion (use_unified) 和 AIF (use_aif) 两种模式
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                "__END__": END,
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
                "__END__": END,
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        # ========== Section C: Trader 后路由 (3 层优先级 + 扩散并行顾问 + AIF 推理迭代循环) ==========
        if use_unified:
            # Fusion: Trader → [HPC_ActiveInference → HPC_CausalReasoning] → [AIF_SelectAction_Evaluate]
            #         → [AIF 推理迭代循环] (N 轮: AIF_UpdateBelief → AIF_Observe → AIF_LLMPrior → AIF_SelectAction_Evaluate)
            #         → [DiffusionAdvisor → FusionNode] → Risky Analyst
            if "HPC_ActiveInference" in all_node_names:
                workflow.add_edge("Trader", "HPC_ActiveInference")
                if "HPC_CausalReasoning" in all_node_names:
                    workflow.add_edge("HPC_ActiveInference", "HPC_CausalReasoning")
                    if "AIF_SelectAction_Evaluate" in all_node_names:
                        workflow.add_edge("HPC_CausalReasoning", "AIF_SelectAction_Evaluate")

                        # ---- AIF 推理迭代循环 ----
                        # 根据 DiffusionAdvisor 可用性决定退出目标
                        exit_target = "DiffusionAdvisor" if "DiffusionAdvisor" in all_node_names else "Risky Analyst"
                        logger.info(
                            f"[AIF Loop] 迭代循环退出目标: {exit_target} "
                            f"(DiffusionAdvisor={'可用' if 'DiffusionAdvisor' in all_node_names else '不可用'})",
                        )
                        # 条件路由: 根据迭代计数器决定继续循环或退出
                        workflow.add_conditional_edges(
                            "AIF_SelectAction_Evaluate",
                            aif_should_continue_iteration,
                            {
                                "continue_iteration": "AIF_UpdateBelief",  # 回环: 继续下一轮推理
                                "exit_iteration": exit_target,  # 退出: 进入扩散顾问或直接到 Risky Analyst
                            },
                        )
                        # 🐛 [Bug 3 修复] AIF 迭代循环路径:
                        #   AIF_UpdateBelief → (条件边) → AIF_Observe → AIF_LLMPrior → AIF_SelectAction_Evaluate
                        #   迭代循环从 AIF_UpdateBelief（Section B 条件边）直接进入 AIF_Observe，
                        #   不再经过 AIF_Predict，彻底杜绝 AIF_Predict 扇出（双出边）导致的无限循环。
                        #   详情参见 aif_route_from_update_belief 的 docstring。
                        if all(node_name in all_node_names for node_name in ("AIF_Observe", "AIF_LLMPrior")):
                            # 🐛 [Bug-New-006 修复] L902 静态边 AIF_Observe→AIF_LLMPrior 已删除。
                            # 此静态边与 Section B 的条件边冲突，导致 LangGraph 扇出：
                            # Section B 的 AIF_Observe 条件边 + Section C 的 AIF_Observe 静态边同时生效，
                            # 两条出边并行 → aif_state 被两个目标节点写入 → InvalidUpdateError。
                            # AIF_Observe 的出边已完全由 Section B 的条件边 _route_aif_observe 统一管理，
                            # 迭代循环路径在 _aif_iteration_count > 0 时由条件边路由到 AIF_LLMPrior。
                            # workflow.add_edge("AIF_Observe", "AIF_LLMPrior")  # 【已删除】
                            # 🐛 [Bug 3b 修复] 移除冗余静态边，AIF_LLMPrior→AIF_SelectAction_Evaluate
                            # 已在 Section A 的条件边中统一管理。保留重复静态边会导致 LangGraph 扇出，
                            # 同时通过条件边和静态边并行执行两条路径，重启管线。
                            # workflow.add_edge("AIF_LLMPrior", "AIF_SelectAction_Evaluate")
                            logger.info(
                                "[AIF Loop] 迭代循环路径 — AIF_Observe 出边由 Section B 条件边统一管理（静态边已移除）",
                            )
                        else:
                            logger.warning("[AIF Loop] 迭代循环路径节点不完整，跳过循环边")

                        # [Plan C] 认知架构路径: DiffusionAdvisor → GlobalWorkspacePopulate
                        #   → AttentionAllocator → IterativeRefinement
                        #   → CognitiveDiagnostic → (DaoistCenter | FusionNode) → Risky Analyst
                        # 退化路径: IterativeRefinement失败→BMA→Risky Analyst
                        if "DiffusionAdvisor" in all_node_names:
                            # 主路径: 全局工作空间 → 注意力分配 → 迭代精炼
                            workflow.add_edge("DiffusionAdvisor", "GlobalWorkspacePopulate")
                            workflow.add_edge("GlobalWorkspacePopulate", "AttentionAllocator")
                            workflow.add_edge("AttentionAllocator", "IterativeRefinement")
                            # IterativeRefinement → CognitiveDiagnostic (pass-through)
                            workflow.add_edge("IterativeRefinement", "CognitiveDiagnostic")
                            # CognitiveDiagnostic 路由: 正常→DaoistCenter, 异常→BMA
                            workflow.add_conditional_edges(
                                "CognitiveDiagnostic",
                                _route_from_ib_refinement,
                                {
                                    "to_daoist_center": "DaoistCenter",
                                    "fallback_to_bma": "FusionNode",
                                },
                            )
                            # DaoistCenter 路由: 空信号或正常→Risky, 异常→BMA
                            workflow.add_conditional_edges(
                                "DaoistCenter",
                                _route_from_daoist_center,
                                {
                                    "to_risky_analyst": "Risky Analyst",
                                    "fallback_to_bma": "FusionNode",
                                },
                            )
                            # BMA退化路径: FusionNode → Risky Analyst
                            workflow.add_edge("FusionNode", "Risky Analyst")
                    else:
                        logger.warning(
                            "[Fusion] AIF_SelectAction_Evaluate 节点不可用，HPC_CausalReasoning 直连 Risky Analyst",
                        )
                        _route_to_risky_analyst(workflow, all_node_names, "HPC_CausalReasoning")
                else:
                    logger.warning("[Fusion] HPC_CausalReasoning 节点不可用，HPC_ActiveInference 直连 Risky Analyst")
                    _route_to_risky_analyst(workflow, all_node_names, "HPC_ActiveInference")
            else:
                logger.warning("[Fusion] HPC_ActiveInference 节点不可用，Trader 直连 Risky Analyst（跳过 HPC 段）")
                _route_to_risky_analyst(workflow, all_node_names, "Trader")
        elif use_aif:
            # AIF 模式下 Trader 直接连接扩散模块 (跳过 HPC 主动推理)
            _route_to_risky_analyst(workflow, all_node_names, "Trader")
        elif hpc_enabled:
            ai_enabled = self.hpc_loop.config.active_inference_enabled
            causal_enabled = self.hpc_loop.config.causal_inference_enabled
            if ai_enabled and causal_enabled:
                workflow.add_edge("Trader", "HPC_ActiveInference")
                workflow.add_edge("HPC_ActiveInference", "HPC_CausalReasoning")
                _route_to_risky_analyst(workflow, all_node_names, "HPC_CausalReasoning")
            elif ai_enabled:
                workflow.add_edge("Trader", "HPC_ActiveInference")
                _route_to_risky_analyst(workflow, all_node_names, "HPC_ActiveInference")
            elif causal_enabled:
                workflow.add_edge("Trader", "HPC_CausalReasoning")
                _route_to_risky_analyst(workflow, all_node_names, "HPC_CausalReasoning")
            else:
                _route_to_risky_analyst(workflow, all_node_names, "Trader")
        else:
            _route_to_risky_analyst(workflow, all_node_names, "Trader")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        # ========== Section D: 终结路由 (3 层优先级) ==========
        if use_unified:
            # Fusion: Risk Judge → [HPC_MemoryStore] → [AIF_Learn] → END
            if "HPC_MemoryStore" in all_node_names:
                workflow.add_edge("Risk Judge", "HPC_MemoryStore")
                if "AIF_Learn" in all_node_names:
                    workflow.add_edge("HPC_MemoryStore", "AIF_Learn")
                    workflow.add_edge("AIF_Learn", END)
                else:
                    logger.warning("[Fusion] AIF_Learn 节点不可用，HPC_MemoryStore 直连 END")
                    workflow.add_edge("HPC_MemoryStore", END)
            else:
                logger.warning("[Fusion] HPC_MemoryStore 节点不可用，Risk Judge 直连 END")
                if "AIF_Learn" in all_node_names:
                    workflow.add_edge("Risk Judge", "AIF_Learn")
                    workflow.add_edge("AIF_Learn", END)
                else:
                    workflow.add_edge("Risk Judge", END)
        elif use_aif:
            workflow.add_edge("Risk Judge", "AIF_Learn")
            workflow.add_edge("AIF_Learn", END)
        # HPC-Loop: Risk Judge 后插入 MemoryStore 节点
        elif hpc_enabled and self.hpc_loop.config.memory_enabled:
            workflow.add_edge("Risk Judge", "HPC_MemoryStore")
            workflow.add_edge("HPC_MemoryStore", END)
        else:
            workflow.add_edge("Risk Judge", END)

        # Compile
        compiled = workflow.compile()
        self.graph = compiled

        # ========== 通道类型运行时验证与修复 (方案A: LangGraph 通道冲突诊断与补偿) ==========
        try:
            channels = workflow.channels

            # 需要检查的所有报告通道（使用 _report_reducer 的通道）
            # 方案A: 升级 LangGraph >=0.7.0 后 Annotated 解析应正确生成 BinaryOperatorAggregate，
            # 但保留此验证作为安全网，并在检测到错误类型时强制转换。
            report_channels = [
                ("market_report", "_report_reducer"),
                ("sentiment_report", "_report_reducer"),
                ("news_report", "_report_reducer"),
                ("fundamentals_report", "_report_reducer"),
                ("sender", "_report_reducer"),
                ("investment_plan", "_report_reducer"),
                ("trader_investment_plan", "_report_reducer"),
                ("final_trade_decision", "_report_reducer"),
                ("past_context", "_report_reducer"),
                ("_aif_iteration_count", "_counter_reducer"),
                ("_aif_max_iterations", "_counter_reducer"),
            ]

            all_correct = True
            for ch_name, reducer_name in report_channels:
                ch = channels.get(ch_name)
                if ch is None:
                    logger.debug(f"ℹ️ {ch_name} 通道未注册 (可选字段，非预期时忽略)")
                    continue

                type_name = type(ch).__name__
                if "BinaryOperator" not in type_name:
                    logger.error(
                        f"❌ {ch_name} 通道类型异常: {type_name}，"
                        f"预期 BinaryOperatorAggregate (reducer={reducer_name})。"
                        f"这可能导致同一 tick 多节点写入时抛出 InvalidUpdateError。",
                    )
                    all_correct = False
                    # 尝试强制转换 (安全网: 如果升级不可行或环境问题)
                    _force_channel_to_binary_operator_aggregate(channels, ch_name, reducer_name)
                else:
                    logger.debug(f"✅ {ch_name} 通道类型正确: {type_name}")

            if all_correct:
                logger.info("✅ 所有 AgentState 通道类型验证通过 (BinaryOperatorAggregate)")
            else:
                logger.warning("⚠️ 部分通道类型异常，已尝试强制转换。建议升级 LangGraph 至 >=0.7.0 以彻底修复。")
        except Exception as e:
            logger.warning(f"⚠️ 通道类型验证异常: {e} (非致命，跳过验证)")

        return compiled
