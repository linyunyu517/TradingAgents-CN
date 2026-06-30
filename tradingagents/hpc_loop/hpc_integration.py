# TradingAgents/hpc_loop/hpc_integration.py
"""
HPC-Loop LangGraph 集成模块

提供 HPC-Loop 各组件作为 LangGraph 节点函数，
以及用于集成到现有 trading_graph.py 的工具函数。

设计原则: 最小侵入式修改，保持向后兼容。
"""

import logging

# [FIX] 2026-06-22: efinance 已移除，内联股票代码标准化函数
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from tradingagents.core.price_cache import price_cache
from tradingagents.dataflows.data_source_manager import get_data_source_manager
from tradingagents.utils.safe_access import safe_get

from .generative_model import MarketGenerativeModel
from .hpc_config import HPCLoopConfig
from .hpc_state import HPCState, MarketPrediction


def _normalize_symbol(symbol: str) -> str:
    """标准化股票代码：去掉 .SH/.SZ 后缀，补齐到6位"""
    if symbol is None:
        return ""
    code = str(symbol).strip().upper()
    code = re.sub(r"\.(SH|SZ|BJ)$", "", code)
    code = code.zfill(6)
    return code


def _safe_get_quote(symbol: str):
    """获取股票最新报价（简化版本 - 返回空DataFrame供调用方处理）

    使用 PriceCache 跨模块共享缓存，避免同一交易循环内重复查询。
    """
    # 查缓存
    cached = price_cache.get(symbol)
    if cached is not None:
        return cached

    with suppress(Exception):
        manager = get_data_source_manager()
        data = manager.get_stock_dataframe(symbol)
        if data is not None and not data.empty:
            # 写入缓存
            price_cache.set(symbol, data)
            return data
    return pd.DataFrame()


from .active_inference import ActiveInferenceEngine
from .causal_counterfactual import CausalCounterfactualEngine
from .complementary_memory import ComplementaryLearningMemory, TradingEpisode
from .global_workspace import GlobalWorkspace

# L-IWM 可选导入 — 仅在 l_iwm_enabled 时使用
try:
    from ..l_iwm import LIWMConfig, LIWMManager

    _L_IWM_AVAILABLE = True
except ImportError:
    LIWMManager = None  # type: ignore
    LIWMConfig = None  # type: ignore
    _L_IWM_AVAILABLE = False

# HSR-MC 超网络自指涉元控制器 (Round 4)
try:
    from ..hsrc_mc import HSRMCConfig, HSRMCManager

    _HSRC_MC_AVAILABLE = True
except ImportError:
    HSRMCConfig = None  # type: ignore
    HSRMCManager = None  # type: ignore
    _HSRC_MC_AVAILABLE = False

logger = logging.getLogger("hpc_loop")


# ==================== LangGraph 节点函数 ====================
# 这些函数可以用作 LangGraph 图中的节点


def create_hpc_prediction_node(generative_model: MarketGenerativeModel) -> Callable:
    """
    创建 HPC 预测节点 (在分析师之前执行)

    生成模型先生成对市场的预测，作为分析师的先验。
    """

    def hpc_predict_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 🔮 生成市场预测...")

        # 从 state 中提取当前市场信息
        _extract_market_info(state)

        # 生成预测
        prediction = generative_model.generate_prediction()
        latent_state = generative_model.get_latent_state()

        # 保存到 hpc_state
        hpc_state = _ensure_hpc_state(state)
        hpc_state.latent_state = latent_state
        hpc_state.last_prediction = prediction
        hpc_state.step_counter += 1
        hpc_state.enabled_features = {
            "generative_model": True,
            "global_workspace": True,
            "active_inference": True,
            "causal_inference": True,
            "memory": True,
        }

        logger.info(
            f"[HPC] ✅ 预测完成: 市场体制={latent_state.get_regime()}, 不确定性={latent_state.total_uncertainty:.3f}",
        )

        return {"hpc_state": hpc_state}

    return hpc_predict_node


def create_hpc_gws_broadcast_node(gws: GlobalWorkspace) -> Callable:
    """
    创建全局工作空间广播节点 (在分析师之后执行)

    收集所有分析师报告，提交到 GWS，广播关键信息。
    """

    def gws_broadcast_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 🌐 全局工作空间广播...")

        hpc_state = _ensure_hpc_state(state)

        # 收集分析师报告
        analyst_reports = [
            ("市场分析师", state.get("market_report", ""), 0.75),
            ("社媒分析师", state.get("sentiment_report", ""), 0.70),
            ("新闻分析师", state.get("news_report", ""), 0.75),
            ("基本面分析师", state.get("fundamentals_report", ""), 0.70),
        ]

        # 提交到 GWS
        for agent_id, report, confidence in analyst_reports:
            if report:
                gws.submit_agent_output(agent_id, report, confidence)

        # 广播
        broadcast_contents = gws.broadcast()
        broadcast_summary = gws.get_broadcast_summary()

        # 保存到 hpc_state
        hpc_state.workspace_contents = [c.to_dict() for c in broadcast_contents]
        hpc_state.workspace_broadcast = [c.content for c in broadcast_contents]

        logger.info(f"[HPC] ✅ GWS 广播: {len(broadcast_contents)} 个内容进入工作空间")

        # 将 GWS 摘要注入到 state (供后续节点使用)
        return {
            "hpc_state": hpc_state,
            "gws_broadcast_summary": broadcast_summary,
        }

    return gws_broadcast_node


def create_hpc_prediction_error_node(
    generative_model: MarketGenerativeModel,
) -> Callable:
    """
    创建预测误差计算节点 (在分析师/GWS之后执行)

    将生成模型的预测与实际分析结果对比，计算预测误差。
    """

    def prediction_error_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 📊 计算预测误差...")

        hpc_state = _ensure_hpc_state(state)

        # [DIAG] 记录 last_prediction 状态
        logger.info(
            f"[HPC-DIAG] last_prediction 状态: "
            f"存在={hpc_state.last_prediction is not None}, "
            f"类型={type(hpc_state.last_prediction).__name__ if hpc_state.last_prediction else 'N/A'}, "
            f"类型模块={type(hpc_state.last_prediction).__module__ if hpc_state.last_prediction else 'N/A'}",
        )

        # 从分析师报告中提取"实际观测"的近似值
        actual_observation = _extract_actual_observation(state)

        if hpc_state.last_prediction:
            # 防御性检查：确保 last_prediction 是 MarketPrediction 实例而非动态类
            if not isinstance(hpc_state.last_prediction, MarketPrediction):
                logger.warning(
                    f"[HPC] ⚠️ last_prediction 类型异常: {type(hpc_state.last_prediction).__name__}, 跳过预测误差计算",
                )
                return {"hpc_state": hpc_state}

            # 计算预测误差
            error = generative_model.compute_prediction_error(hpc_state.last_prediction, actual_observation)

            # 更新信念
            generative_model.update_beliefs(error)

            # 保存误差
            hpc_state.last_prediction_error = error

            # === [FIX 2026-06-26] 预测编码闭环 — EMA 误差反馈 ===
            # 参考: PredNet (Lotter et al. 2016) 的误差反馈机制
            # 让误差不仅被记录，还反馈到预测模型中，实现闭环学习
            # 用EMA平滑误差作为"预测可信度"的调制信号
            # =====================================================
            # 获取或初始化平滑误差
            smooth_error = getattr(hpc_state, "_smoothed_error", None)
            alpha = 0.7  # EMA平滑系数 (越大越平滑)
            current_error = float(error.total_error) if hasattr(error, "total_error") else 0.0
            
            if smooth_error is None:
                smooth_error = current_error
            else:
                smooth_error = alpha * smooth_error + (1.0 - alpha) * current_error
            
            hpc_state._smoothed_error = smooth_error
            
            # 计算预测学习率：误差越大 → 学习率越高（需要更快调整预测）
            # 范围 [0.01, 0.3]，smooth_error=0时→0.01，smooth_error=1时→0.3
            pred_learning_rate = max(0.01, min(0.3, smooth_error * 0.3))
            hpc_state._prediction_learning_rate = pred_learning_rate
            
            logger.info(
                "[HPC-PC] ✅ 预测编码闭环: raw_error=%.4f, smooth_error=%.4f, pred_lr=%.4f",
                current_error,
                smooth_error,
                pred_learning_rate,
            )

            # 检测相变
            phase_transition = generative_model.detect_phase_transition()
            if phase_transition["is_transitioning"]:
                logger.warning(
                    f"[HPC] ⚠️ 检测到市场相变! {phase_transition['from_regime']} → {phase_transition['to_regime']}",
                )

            logger.info(
                f"[HPC] ✅ 预测误差: total={error.total_error:.4f}, "
                f"surprise={error.surprise_magnitude:.2f}, "
                f"相变={phase_transition['is_transitioning']}",
            )
        else:
            logger.debug("[HPC] ⚠️ 无预测可计算误差")

        return {
            "hpc_state": hpc_state,
            "hpc_phase_transition": phase_transition if "phase_transition" in dir() else None,
            "hpc_smoothed_error": getattr(hpc_state, "_smoothed_error", 0.0),
            "hpc_prediction_learning_rate": getattr(hpc_state, "_prediction_learning_rate", 0.05),
        }

    return prediction_error_node


def create_hpc_prediction_error_node_stub() -> Callable:
    """创建 HPC_PredictionError 退化模式节点（生成模型不可用时的替补）"""
    def prediction_error_node_stub(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 📊 预测误差计算（退化模式 — 无生成模型）")
        hpc_state = _ensure_hpc_state(state)
        return {"hpc_state": hpc_state, "hpc_prediction_error_stub": True}
    return prediction_error_node_stub


def create_hpc_active_inference_node(
    active_inference: ActiveInferenceEngine,
    generative_model: MarketGenerativeModel | None = None,
) -> Callable:
    """
    创建主动推理节点 (在决策之前执行)

    评估候选行动的 EFE，提供探索-利用平衡的决策建议。
    """

    def active_inference_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 🧠 主动推理: 评估候选行动...")

        hpc_state = _ensure_hpc_state(state)

        # 构建当前市场状态
        current_state = _extract_market_info(state)
        current_state["uncertainty"] = hpc_state.latent_state.total_uncertainty if hpc_state.latent_state else 0.5
        current_state["entropy"] = hpc_state.latent_state.get_entropy() if hpc_state.latent_state else 1.0

        # 候选行动
        candidate_actions = ["买入", "持有", "卖出"]

        # 评估
        prediction = hpc_state.last_prediction
        selection = active_inference.select_action(candidate_actions, current_state, generative_model, prediction)

        # 保存到 hpc_state
        hpc_state.candidate_actions = [e.to_dict() for e in selection.all_evaluations]
        hpc_state.selected_action = selection.selected_action.to_dict() if selection.selected_action else None

        logger.info(
            f"[HPC] ✅ 主动推理: 选择 '{selection.selected_action.action_id if selection.selected_action else 'N/A'}' "
            f"(EFE={selection.selected_action.expected_free_energy:.3f} "
            f"if selection.selected_action else 'N/A')",
        )

        return {"hpc_state": hpc_state}

    return active_inference_node


def create_hpc_causal_node(
    causal_engine: CausalCounterfactualEngine,
) -> Callable:
    """
    创建因果反事实节点 (在决策之前执行)

    对候选决策进行反事实推理。
    """

    def causal_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 🔗 因果反事实推理...")

        hpc_state = _ensure_hpc_state(state)

        # 获取当前市场状态作为证据
        evidence = _extract_market_info(state)

        # 对每个候选行动执行反事实推理
        counterfactuals = []
        for action in ["买入", "卖出", "持有"]:
            cf_result = causal_engine.counterfactual_query("trading_action", "trading_return", evidence)
            cf_result.query = f"如果执行 {action}"
            counterfactuals.append(cf_result.to_dict())

        hpc_state.causal_counterfactuals = counterfactuals

        logger.info(f"[HPC] ✅ 因果推理完成: {len(counterfactuals)} 个反事实评估")

        return {"hpc_state": hpc_state}

    return causal_node


def create_hpc_memory_store_node(
    memory: ComplementaryLearningMemory,
) -> Callable:
    """
    创建记忆存储节点 (在决策之后执行)

    将当前交易事件存储到互补学习记忆系统。
    """

    def memory_store_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC] 💾 存储交易事件到记忆系统...")

        hpc_state = _ensure_hpc_state(state)
        getattr(hpc_state, "_config", None)

        # 构建交易事件
        episode = TradingEpisode(
            ticker=state.get("company_of_interest", ""),
            timestamp=datetime.now().isoformat(),
            market_context=_extract_market_info(state),
            action=hpc_state.selected_action.get("action_id", "unknown") if hpc_state.selected_action else "unknown",
            decision_rationale=state.get("final_trade_decision", ""),
            outcome=None,  # 交易结果尚未可知
            confidence=hpc_state.selected_action.get("confidence", 0.0) if hpc_state.selected_action else 0.0,
            prediction_error=hpc_state.last_prediction_error.total_error if hpc_state.last_prediction_error else 0.0,
            metadata={
                "source": "hpc_loop",
                "timestamp": datetime.now().isoformat(),
            },
        )

        # 存储到海马体
        memory.store_episode(episode)

        # 尝试触发记忆巩固
        consolidated = memory.consolidate()
        if consolidated > 0:
            logger.info(f"[HPC] 🔄 记忆巩固: {consolidated} 个事件已巩固")

        hpc_state.current_episode = episode.to_dict()
        hpc_state.step_counter += 1

        # 执行睡眠回放 (每10步触发一次)
        if hpc_state.step_counter % 10 == 0:
            replay_stats = memory.sleep_replay()
            logger.info(
                f"[HPC] 💤 睡眠回放: {replay_stats['replayed']} 个事件重放, "
                f"{replay_stats['patterns_extracted']} 个模式提取",
            )

        return {"hpc_state": hpc_state}

    return memory_store_node


# ==================== L-IWM 增强节点工厂函数 ====================
# 这些节点在 l_iwm_enabled=True 时替代原始 HPC 节点
# 设计原则: 当 L-IWM 子模块启用时使用 L-IWM 增强版本，
#           子模块禁用时自动回退到原始行为。


def create_l_iwm_prediction_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 增强预测节点 (当 rssm_enabled 时替代 HPC_Predict)。

    使用 RSSM 世界模型生成基于隐变量的预测序列，
    替代 MarketGenerativeModel.generate_prediction 的硬编码 ±0.5% 预测。
    """

    def l_iwm_predict_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC:L-IWM] 🧠 L-IWM 增强预测...")

        hpc_state = _ensure_hpc_state(state)

        # 从 state 中提取市场信息
        market_info = _extract_market_info(state)

        # 调用 L-IWM 的增强预测
        enhanced_pred = l_iwm_manager.get_enhanced_prediction(market_info)

        if enhanced_pred and enhanced_pred.get("rssm_available", True):
            # 成功使用 L-IWM 增强预测
            enhanced_pred.get("latent_state", {})
            hpc_state.latent_state._uncertainty = 0.3  # placeholder
            hpc_state.enabled_features["l_iwm_rssm"] = True
            logger.info(f"[HPC:L-IWM] ✅ RSSM 预测完成: steps={enhanced_pred.get('num_steps', 0)}")

            # ----- Bug #1 修复: 从 RSSM 预测设置 last_prediction -----
            try:
                rssm_predictions = enhanced_pred.get("predictions", [])
                if rssm_predictions:
                    last_rssm_pred = rssm_predictions[-1]
                    if hasattr(last_rssm_pred, "to_dict"):
                        pred_dict = last_rssm_pred.to_dict()
                        hpc_state.last_prediction = MarketPrediction.from_dict(pred_dict)
                    elif isinstance(last_rssm_pred, dict):
                        hpc_state.last_prediction = MarketPrediction.from_dict(last_rssm_pred)
                    else:
                        # fallback: 尝试用 getattr 提取字段
                        hpc_state.last_prediction = MarketPrediction(
                            price_prediction=getattr(last_rssm_pred, "price_prediction", None),
                            volatility_prediction=getattr(last_rssm_pred, "volatility_prediction", None),
                            sentiment_prediction=getattr(last_rssm_pred, "sentiment_prediction", None),
                            timestamp=datetime.now().isoformat(),
                        )
                    logger.info("[HPC:L-IWM] ✅ last_prediction 已从 RSSM 预测设置")
                else:
                    logger.warning("[HPC:L-IWM] ⚠️ RSSM 预测列表为空，last_prediction 未设置")
            except Exception as e:
                logger.error(f"[HPC:L-IWM] ❌ 从 RSSM 预测设置 last_prediction 失败: {e}")

            # [DIAG] 记录 RSSM 可用时 last_prediction 未设置的情况
            if hpc_state.last_prediction is None:
                logger.warning(
                    f"[HPC:L-IWM-DIAG] ⚠️ RSSM 可用但未设置 last_prediction！"
                    f"这会导致下游 HPC_PredictionError 节点跳过预测误差计算。"
                    f"增强预测的键: {list(enhanced_pred.keys())}",
                )
        else:
            # RSSM 不可用，记录原因并回退到原始生成模型
            reason = enhanced_pred.get("reason", "unknown") if enhanced_pred else "None返回"
            logger.info(f"[HPC:L-IWM] RSSM 不可用({reason})，回退到原始生成模型")
            if hasattr(l_iwm_manager, "_hpc_generative_model"):
                prediction = l_iwm_manager._hpc_generative_model.generate_prediction()
                latent_state = l_iwm_manager._hpc_generative_model.get_latent_state()
                hpc_state.latent_state = latent_state
                hpc_state.last_prediction = prediction
            hpc_state.enabled_features["l_iwm_rssm"] = False

        hpc_state.step_counter += 1

        # 将 L-IWM 增强数据存入 state 供下游节点使用
        state["l_iwm"] = state.get("l_iwm", {})
        state["l_iwm"]["prediction"] = enhanced_pred

        return {"hpc_state": hpc_state, "l_iwm": state.get("l_iwm")}

    return l_iwm_predict_node


def create_l_iwm_market_info_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 增强市场信息节点 (当 real_data_enabled 时替代 _extract_market_info)。

    使用 RealDataPipeline 获取真实技术指标，替代文本长度代理。
    """

    def l_iwm_market_info_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC:L-IWM] 📊 L-IWM 增强市场信息...")

        symbol = state.get("company_of_interest", "000001.SH")
        enhanced_info = l_iwm_manager.get_enhanced_market_info(state, symbol)

        if enhanced_info and enhanced_info.get("has_real_data"):
            # 成功使用真实市场数据
            features = enhanced_info.get("features", [])
            state["l_iwm"] = state.get("l_iwm", {})
            state["l_iwm"]["market_data"] = {
                "regime": enhanced_info.get("regime", "unknown"),
                "regime_confidence": enhanced_info.get("regime_confidence", 0.0),
                "price_trend": enhanced_info.get("price_trend", "neutral"),
                "volatility_level": enhanced_info.get("volatility_level", "medium"),
                "features": features,
                "has_real_data": True,
            }
            logger.info(
                f"[HPC:L-IWM] ✅ 真实市场数据: "
                f"regime={enhanced_info.get('regime')}, "
                f"trend={enhanced_info.get('price_trend')}",
            )
        else:
            # 数据管道未启用，使用原始代理
            market_info = _extract_market_info(state)
            state["l_iwm"] = state.get("l_iwm", {})
            state["l_iwm"]["market_data"] = {
                "regime": market_info.get("regime", "unknown"),
                "has_real_data": False,
            }

        return state

    return l_iwm_market_info_node


def create_l_iwm_efe_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 增强 EFE 节点 (当 learnable_efe_enabled 时替代 HPC_ActiveInference)。

    使用 LearnableEFEEvaluator 学习到的价值网络评估动作 EFE，
    替代 ActiveInferenceEngine 的手工 epistemic/pragmatic 权重。
    """

    def l_iwm_efe_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC:L-IWM] 🧠 L-IWM 增强 EFE 评估...")

        hpc_state = _ensure_hpc_state(state)

        # 获取隐状态 (优先使用 L-IWM 预测节点的输出)
        l_iwm_data = state.get("l_iwm", {})
        latent_state = l_iwm_data.get("prediction", {}).get("latent_state", {})
        if not latent_state:
            # 回退: 使用 HPC latent_state
            latent_state = {
                "h": hpc_state.latent_state.get_h() if hasattr(hpc_state.latent_state, "get_h") else None,
                "z": None,
            }

        # 候选动作
        candidate_actions = ["买入", "持有", "卖出"]

        # 调用 L-IWM 的增强 EFE
        efe_result = l_iwm_manager.get_enhanced_efe(latent_state, candidate_actions)

        if efe_result and efe_result.get("action_results"):
            # 成功使用可学习 EFE
            best_action = efe_result.get("best_action", "持有")
            best_efe = efe_result.get("best_efe", 0.0)

            # 构造与原有 EFEDecomposition 兼容的输出
            hpc_state.selected_action = {
                "action_id": best_action,
                "expected_free_energy": best_efe,
                "epistemic_value": efe_result.get("epistemic_value", 0.0),
                "pragmatic_value": efe_result.get("pragmatic_value", 0.0),
                "exploration_bonus": efe_result.get("exploration_bonus", 0.0),
                "confidence": max(0.3, 1.0 - min(abs(best_efe), 1.0)),
                "source": "learnable_efe",
            }
            hpc_state.candidate_actions = [
                {
                    "action_id": act,
                    "efe": info.get("expected_free_energy", 0.0),
                    "epistemic": info.get("epistemic_value", 0.0),
                    "pragmatic": info.get("pragmatic_value", 0.0),
                    "exploration_bonus": info.get("exploration_bonus", 0.0),
                }
                for act, info in efe_result.get("action_results", {}).items()
            ]
            hpc_state.enabled_features["l_iwm_efe"] = True

            logger.info(f"[HPC:L-IWM] ✅ EFE 评估: 选择 '{best_action}' (EFE={best_efe:.3f})")
        else:
            # EFE 评估器未启用，回退到原始主动推理
            hpc_state.enabled_features["l_iwm_efe"] = False

        # 将 EFE 结果写入 l_iwm state 供下游使用
        state["l_iwm"] = state.get("l_iwm", {})
        state["l_iwm"]["efe_result"] = efe_result

        return {"hpc_state": hpc_state, "l_iwm": state.get("l_iwm")}

    return l_iwm_efe_node


def create_l_iwm_causal_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 增强因果节点 (当 diff_causal_enabled 时替代 HPC_CausalReasoning)。

    使用 DifferentiableCausalDiscovery 学习到的因果权重，
    替代 CausalCounterfactualEngine 的手工 10-node/13-edge 因果图。
    """

    def l_iwm_causal_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC:L-IWM] 🔗 L-IWM 增强因果推理...")

        hpc_state = _ensure_hpc_state(state)

        # 对每个候选行动执行 L-IWM 因果分析
        counterfactuals = []
        for action in ["买入", "卖出", "持有"]:
            causal_result = l_iwm_manager.get_enhanced_causal(
                action_node="trading_action",
                target_node="price_movement",
            )

            if causal_result and "intervention" in causal_result:
                counterfactuals.append(
                    {
                        "action": action,
                        "direct_effect": causal_result["intervention"]["direct_effect"],
                        "total_effect": causal_result["intervention"]["total_effect"],
                        "confidence": causal_result["intervention"]["confidence"],
                        "is_dag": causal_result.get("causal_graph", {}).get("is_dag", False),
                        "num_edges": causal_result.get("causal_graph", {}).get("num_edges", 0),
                        "source": "differentiable_causal",
                    },
                )
                hpc_state.enabled_features["l_iwm_causal"] = True
            else:
                # 因果发现未启用，回退到原始引擎
                hpc_state.enabled_features["l_iwm_causal"] = False
                break

        hpc_state.causal_counterfactuals = counterfactuals

        logger.info(f"[HPC:L-IWM] ✅ 因果推理完成: {len(counterfactuals)} 个反事实评估")

        # 将因果结果写入 l_iwm state
        state["l_iwm"] = state.get("l_iwm", {})
        state["l_iwm"]["causal_result"] = counterfactuals

        return {"hpc_state": hpc_state, "l_iwm": state.get("l_iwm")}

    return l_iwm_causal_node


def create_l_iwm_gws_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 增强 GWS 广播节点 (当 learnable_gws_enabled 时替代 HPC_GWS_Broadcast)。

    使用 LearnableSaliencyEvaluator 学习到的显著性评分，
    替代 GlobalWorkspace 的关键词匹配启发式评估。
    """

    def l_iwm_gws_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[HPC:L-IWM] 🌐 L-IWM 增强 GWS 广播...")

        hpc_state = _ensure_hpc_state(state)

        # 收集分析师报告
        analyst_reports = [
            ("市场分析师", state.get("market_report", ""), 0.75),
            ("社媒分析师", state.get("sentiment_report", ""), 0.70),
            ("新闻分析师", state.get("news_report", ""), 0.75),
            ("基本面分析师", state.get("fundamentals_report", ""), 0.70),
        ]

        # 过滤空报告并构造内容列表
        contents = [(agent_id, report, confidence) for agent_id, report, confidence in analyst_reports if report]

        if not contents:
            return {"hpc_state": hpc_state}

        # 调用 L-IWM 的增强广播
        broadcast_result = l_iwm_manager.get_enhanced_broadcast(
            contents,
            belief=state.get("belief"),
        )

        if broadcast_result and broadcast_result.get("details"):
            # 成功使用可学习显著性评估器
            details = broadcast_result.get("details", [])
            selected_ids = broadcast_result.get("selected_ids", [])

            # 构造与原有 GWS 广播兼容的输出
            broadcast_contents = [
                {
                    "agent_id": d["content_id"],
                    "content": f"[L-IWM] {d['text_preview']}",
                    "novelty": d["novelty"],
                    "impact": d["impact"],
                    "urgency": d["urgency"],
                    "saliency": d["saliency"],
                    "selected": d["selected"],
                    "source": "learnable_gws",
                }
                for d in details
            ]

            hpc_state.workspace_contents = broadcast_contents
            hpc_state.workspace_broadcast = [c["content"] for c in broadcast_contents if c["selected"]]
            hpc_state.enabled_features["l_iwm_gws"] = True

            # 构造广播摘要
            broadcast_summary = (
                f"L-IWM 广播: {len(selected_ids)}/{len(contents)} 内容被选中 "
                f"(显著性阈值={broadcast_result.get('saliency_weights', [0.3])[0]:.2f})"
            )

            logger.info(f"[HPC:L-IWM] ✅ GWS 广播: {broadcast_summary}")
        else:
            # GWS 评估器未启用，回退到原始 GWS
            hpc_state.enabled_features["l_iwm_gws"] = False
            broadcast_summary = ""

        # ========== Fusion: 将 GWS 结果写入通用 state 供 AIF 消费 ==========
        fusion_gws_summary = None
        if state.get("fusion_mode") == "unified":
            try:
                # 提取广播内容摘要供 AIF 后续节点使用
                broadcast_text = hpc_state.workspace_broadcast
                if broadcast_text:
                    state["fusion_gws_summary"] = " | ".join(broadcast_text[:5])
                else:
                    state["fusion_gws_summary"] = ""
                fusion_gws_summary = state["fusion_gws_summary"]
                # 标记 AIF 可用的观测就绪
                state["fusion_gws_ready"] = True
                logger.info("[Fusion] GWS 广播结果已桥接到 fusion state")
            except Exception as e:
                logger.warning(f"[Fusion] GWS→AIF 桥接失败 (非致命): {e}")

        # 构建返回字典，包含所有在 state 中写入的数据
        ret = {
            "hpc_state": hpc_state,
            "gws_broadcast_summary": broadcast_summary,
        }
        if fusion_gws_summary is not None:
            ret["fusion_gws_summary"] = fusion_gws_summary
            ret["fusion_gws_ready"] = True

        return ret

    return l_iwm_gws_node


def create_l_iwm_bridge_node(l_iwm_manager: "LIWMManager") -> Callable:
    """
    创建 L-IWM 桥接节点 — 在所有 L-IWM 节点执行后运行。

    执行以下操作:
    1. 将 L-IWM 增强结果与原始 hpc_state 同步
    2. 触发 EWC 正则化损失计算
    3. 更新模块依赖 (如 RSSM→EFE 的状态传递)
    """

    def l_iwm_bridge_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.debug("[HPC:L-IWM] 🔄 L-IWM 桥接同步...")

        hpc_state = _ensure_hpc_state(state)

        # 1. 如果启用了 EWC，将 EWC 正则化损失附加到 state
        if l_iwm_manager.ewc_memory is not None:
            ewc_loss = l_iwm_manager.get_ewc_regularization()
            state["l_iwm"] = state.get("l_iwm", {})
            state["l_iwm"]["ewc_loss"] = ewc_loss

        # 2. 检查是否所有 L-IWM 节点都成功启用了
        l_iwm_features = hpc_state.enabled_features
        l_iwm_active = any(v for k, v in l_iwm_features.items() if k.startswith("l_iwm_"))

        if l_iwm_active:
            logger.debug(
                f"[HPC:L-IWM] ✅ L-IWM 活跃特征: "
                f"{ {k: v for k, v in l_iwm_features.items() if k.startswith('l_iwm_')} }",
            )

        # === HSR-MC 数据管道：提取 L-IWM 训练数据写入 state ===
        try:
            # 如果尚未训练，触发一次训练以产生数据供 HSR-MC 消费
            if l_iwm_manager.train_step == 0:
                symbol = state.get("company_of_interest", "000001.SH")
                # 从 state 中提取决策信息作为训练 context（action/reward）
                # 优先使用 AIF 选择，其次用交易员决策，最后用 diffusion 决策
                aif_action = state.get("aif_selection", {})
                trader_action = safe_get(state, ["final_trade_decision", "action"], "") or safe_get(state, ["fused_decision", "decision"], "")
                diffusion_action = state.get("diffusion_decision", {}).get("action")
                best_action = (
                    aif_action.get("selected_action") or
                    trader_action or
                    diffusion_action
                )
                train_context = {
                    "action": best_action,
                    "reward": state.get("reward", 0.0),
                    "done": False,
                }
                if best_action:
                    logger.info(f"[HPC→HSR-MC] 首次训练 context 含 action={best_action}")
                logger.info(f"[HPC→HSR-MC] 首次训练触发: symbol={symbol}, context={ {k:v for k,v in train_context.items() if v is not None} }")
                l_iwm_manager.train_on_batch(symbol=symbol, context=train_context)

            # 获取最新模块统计信息
            stats = l_iwm_manager.get_statistics()
            modules_stats = stats.get("modules", {})

            # ===== 1. 收集模块损失 =====
            module_losses = {}

            # EFE: avg_td_error 作为损失代理（包含 0 值以供 HSR-MC 跟踪）
            efe_stats = modules_stats.get("efe_evaluator", {})
            module_losses["efe"] = float(efe_stats.get("avg_td_error", 0.0))

            # EWC: ewc_loss_avg 作为损失
            ewc_stats = modules_stats.get("ewc_memory", {})
            module_losses["ewc"] = float(ewc_stats.get("ewc_loss_avg", 0.0))

            # Causal: h_value 作为 DAG 约束损失代理
            causal_stats = modules_stats.get("causal_discovery", {})
            module_losses["causal"] = float(causal_stats.get("h_value", 0.0))

            # RSSM: buffer_size 作为活性指标 → 构造代理损失
            rssm_stats = modules_stats.get("rssm", {})
            buf_size = rssm_stats.get("buffer_size", 0)
            module_losses["rssm"] = 1.0 / (1.0 + float(buf_size)) if buf_size > 0 else 0.5

            # GWS: feedback_buffer_size 作为活性指标
            gws_stats = modules_stats.get("gws_evaluator", {})
            if gws_stats.get("feedback_buffer_size", 0) > 0:
                module_losses["gws"] = 0.01  # 小正数表示活跃
            else:
                module_losses["gws"] = 0.5  # 默认中值供 HSR-MC 跟踪

            # RealDataPipeline: lookback_days 作为活跃指标
            data_pipeline_stats = modules_stats.get("data_pipeline", {})
            lookback = data_pipeline_stats.get("lookback_days", 0)
            module_losses["data_pipeline"] = 1.0 / (1.0 + float(lookback)) if lookback > 0 else 0.5

            # 键名映射：L-IWM 内部名 → HSR-MC MODULE_NAMES 期望名（混合大小写）
            MODULE_KEY_MAP = {
                "rssm": "RSSM",
                "data_pipeline": "RealDataPipeline",
                "efe": "EFE",
                "causal": "Causal",
                "ewc": "EWC",
                "gws": "GWS",
            }
            module_losses = {MODULE_KEY_MAP.get(k, k): v for k, v in module_losses.items()}

            state["module_losses"] = module_losses
            logger.info(f"[HPC→HSR-MC] 已注入 module_losses: { {k: f'{v:.4f}' for k, v in module_losses.items()} }")

            # ===== 2. 收集模块性能 =====
            module_performance = {}
            for name, loss_key in [
                ("RSSM", "RSSM"),
                ("RealDataPipeline", "RealDataPipeline"),
                ("EFE", "EFE"),
                ("Causal", "Causal"),
                ("EWC", "EWC"),
                ("GWS", "GWS"),
            ]:
                loss_val = module_losses.get(loss_key, 0.5)
                module_performance[name] = 1.0 / (1.0 + abs(float(loss_val)))

            state["module_performance"] = module_performance

            # ===== 3. 收集预测误差 =====
            # HSR-MC 的 online_meta_step() 期望 Optional[List[float]]
            # 因此将 dict 转为 list，避免 deque.extend(dict) 迭代 key 字符串
            prediction_errors_raw = {}
            if "EFE" in module_losses:
                prediction_errors_raw["efe_td"] = float(module_losses["EFE"])
            if "Causal" in module_losses:
                prediction_errors_raw["causal_h"] = float(module_losses["Causal"])

            if prediction_errors_raw:
                error_values = list(prediction_errors_raw.values())
                state["prediction_errors"] = error_values
            else:
                state["prediction_errors"] = [0.5]  # 默认值，避免空列表导致短路

            # 注意：不注入 gradient_info。
            # 桥接节点无法获取真实的梯度张量（Dict[str, np.ndarray]），
            # 若传入 Dict[str, Dict] 会导致 MetaObserver._analyze_gradients()
            # 对 dict 调用 .flatten() 抛出 AttributeError。
            # MetaObserver 收到 None 时自动跳过梯度分析，行为正确。

            logger.info(
                f"[HPC→HSR-MC] 数据管道已填充: "
                f"module_losses={len(module_losses)}, "
                f"module_performance={len(module_performance)}, "
                f"prediction_errors={len(state.get('prediction_errors', []))}",
            )
        except Exception as e:
            logger.warning(f"[HPC→HSR-MC] 数据管道填充失败（非致命）: {e}")

        # 🔥 [Bug #5 修复] 将 in-place 写入 state 的数据也通过返回值传递，
        #    因为 final_state 只从节点返回值构建
        ret = {"hpc_state": hpc_state}
        if "module_losses" in state:
            ret["module_losses"] = state["module_losses"]
        if "module_performance" in state:
            ret["module_performance"] = state["module_performance"]
        if "prediction_errors" in state:
            ret["prediction_errors"] = state["prediction_errors"]
        if "l_iwm" in state:
            ret["l_iwm"] = state["l_iwm"]

        # 🔍 [Bug #5 诊断] 节点内部确认返回值键
        logger.info(f"[HPC:L-IWM] 🔍 DIAG: l_iwm_bridge_node 返回键: {list(ret.keys())}")
        return ret

    return l_iwm_bridge_node


# ==================== HPC-Loop 管理器 ====================


class HPCLoopManager:
    """
    HPC-Loop 管理器

    集中管理所有 HPC-Loop 组件和它们在 LangGraph 中的集成。
    作为 TradingAgentsGraph 的扩展注入点。
    """

    def __init__(
        self,
        config: dict[str, Any] | HPCLoopConfig | None = None,
        l_iwm_manager: Optional["LIWMManager"] = None,
        hsrc_mc_config: Optional["HSRMCConfig"] = None,
    ):
        # 兼容两种传入方式: HPCLoopConfig 实例 或 主配置 dict
        if isinstance(config, HPCLoopConfig):
            self.config = config
        elif config:
            # dict 模式：从环境变量加载基础 HPCLoopConfig，再用 dict 覆盖
            hpc_config = HPCLoopConfig.from_env()
            if "hpc_loop_enabled" in config:
                hpc_config.enabled = config["hpc_loop_enabled"]
            if "use_aif_engine" in config:
                hpc_config.use_aif_engine = config["use_aif_engine"]
            # ── HPC 核心参数映射 ──
            if "hpc_parallel_analysts" in config:
                hpc_config.parallel_analysts = config["hpc_parallel_analysts"]
            if "hpc_gws_enabled" in config:
                hpc_config.gws_enabled = config["hpc_gws_enabled"]
            if "hpc_memory_window_size" in config:
                hpc_config.generative_model_history_window = config["hpc_memory_window_size"]
            if "hpc_causal_max_hypotheses" in config:
                hpc_config.causal_graph_max_nodes = config["hpc_causal_max_hypotheses"]
            if "hpc_prediction_error_threshold" in config:
                hpc_config.prediction_error_surprise_threshold = config["hpc_prediction_error_threshold"]
            # ── 修复 CRITICAL-2: hpc_prediction_error_rate 映射 ──
            if "hpc_prediction_error_rate" in config:
                hpc_config.prediction_error_rate = config["hpc_prediction_error_rate"]
            # ── 修复 CRITICAL-3: diffusion_num_timesteps 映射 ──
            if "diffusion_num_timesteps" in config:
                hpc_config.diffusion_num_timesteps = config["diffusion_num_timesteps"]
            # ── 修复 HIGH-1: diffusion_generative_enabled 映射 ──
            if "diffusion_generative_enabled" in config:
                hpc_config.diffusion_generative_enabled = config["diffusion_generative_enabled"]
            # ── 修复 CRITICAL-4/5: meta_learning_rate / meta_cycle_interval 映射 ──
            if "meta_learning_rate" in config:
                hpc_config.meta_learning_rate = config["meta_learning_rate"]
            if "meta_cycle_interval" in config:
                hpc_config.meta_cycle_interval = config["meta_cycle_interval"]
            # ── L6: L-IWM / HSR-MC 开关映射 ──
            if "l_iwm_enabled" in config:
                hpc_config.l_iwm_enabled = config["l_iwm_enabled"]
            if "hsrc_mc_enabled" in config:
                hpc_config.hsrc_mc_enabled = config["hsrc_mc_enabled"]
            if "diffusion_enabled" in config:
                hpc_config.diffusion_enabled = config["diffusion_enabled"]
            self.config = hpc_config
        else:
            self.config = HPCLoopConfig.from_env()
        self.enabled = self.config.enabled

        # ── 存储外部传递的 L-IWM 数据源配置 (CD-2 修复) ──
        self._l_iwm_data_sources: list[str] | None = None
        if isinstance(config, dict) and "l_iwm_real_data_sources" in config:
            self._l_iwm_data_sources = config["l_iwm_real_data_sources"]

        # 核心组件 (延迟初始化)
        self.generative_model: MarketGenerativeModel | None = None
        self.global_workspace: GlobalWorkspace | None = None
        self.active_inference: ActiveInferenceEngine | None = None
        self.causal_engine: CausalCounterfactualEngine | None = None
        self.memory: ComplementaryLearningMemory | None = None

        # L-IWM 可学习模块管理器
        self.l_iwm_manager: LIWMManager | None = l_iwm_manager

        # HSR-MC 超网络自指涉元控制器
        self.hsrc_mc_manager: HSRMCManager | None = None
        self._hsrc_mc_config: HSRMCConfig | None = hsrc_mc_config

        if self.enabled:
            self._init_components()

    def _init_components(self) -> None:
        """初始化所有 HPC-Loop 组件 (包括可选的 L-IWM 和 HSR-MC 模块)"""
        logger.info("[HPC] 🚀 初始化 HPC-Loop 组件...")

        if self.config.generative_model_enabled:
            self.generative_model = MarketGenerativeModel(self.config)
            logger.info("[HPC] ✅ 生成模型已初始化")

        if self.config.gws_enabled:
            self.global_workspace = GlobalWorkspace(self.config)
            logger.info(f"[HPC] ✅ 全局工作空间已初始化 (容量={self.config.gws_capacity})")

        if self.config.active_inference_enabled:
            self.active_inference = ActiveInferenceEngine(self.config)
            logger.info(f"[HPC] ✅ 主动推理引擎已初始化 (认知权重={self.config.epistemic_weight})")

        if self.config.causal_inference_enabled:
            self.causal_engine = CausalCounterfactualEngine(self.config)
            logger.info("[HPC] ✅ 因果反事实引擎已初始化")

        if self.config.memory_enabled:
            self.memory = ComplementaryLearningMemory(self.config)
            logger.info("[HPC] ✅ 互补学习记忆系统已初始化")

        # ===== L-IWM 可学习模块初始化 =====
        if self.config.l_iwm_enabled:
            self._init_l_iwm()

        # ===== HSR-MC 超网络自指涉元控制器初始化 =====
        if self.config.hsrc_mc_enabled:
            self._init_hsrc_mc()

        logger.info("[HPC] 🚀 HPC-Loop 初始化完成")

    def _init_l_iwm(self) -> None:
        """初始化 L-IWM 可学习模块管理器"""
        if not _L_IWM_AVAILABLE:
            logger.warning(
                "[HPC] ⚠️ L-IWM 模块不可用 (l_iwm 包未安装或导入失败)。请确保 tradingagents.l_iwm 包已正确安装。",
            )
            self.config.l_iwm_enabled = False
            return

        try:
            # 如果外部未注入 l_iwm_manager，则根据配置自动创建
            if self.l_iwm_manager is None:
                # 从 HPCLoopConfig 的 l_iwm_config_path 加载 LIWMConfig
                if self.config.l_iwm_config_path:
                    import json

                    with open(self.config.l_iwm_config_path, encoding="utf-8") as f:
                        l_iwm_config_dict = json.load(f)
                    l_iwm_config = LIWMConfig.from_dict(l_iwm_config_dict)
                else:
                    l_iwm_config = LIWMConfig()

                # ── CD-2 修复: 将 default_config.py 的 l_iwm_real_data_sources 传递到 LIWMConfig ──
                if self._l_iwm_data_sources is not None:
                    l_iwm_config.real_data_sources = list(self._l_iwm_data_sources)
                    logger.info(f"[HPC] ✅ L-IWM 数据源已从配置覆写: {self._l_iwm_data_sources}")

                self.l_iwm_manager = LIWMManager(
                    config=l_iwm_config,
                    input_dim=self.config.l_iwm_input_dim,
                )

            # 初始化所有子模块
            init_status = self.l_iwm_manager.init_modules()
            n_ok = sum(1 for v in init_status.values() if v)
            n_total = len(init_status)
            logger.info(f"[HPC] ✅ L-IWM 管理器已初始化: {n_ok}/{n_total} 子模块启用")

            # 存储生成模型引用供 L-IWM 回退使用
            if self.generative_model is not None:
                self.l_iwm_manager._hpc_generative_model = self.generative_model

        except Exception as e:
            logger.error(f"[HPC] ❌ L-IWM 初始化失败: {e}")
            self.config.l_iwm_enabled = False
            self.l_iwm_manager = None

    def _init_hsrc_mc(self) -> None:
        """初始化 HSR-MC 超网络自指涉元控制器"""
        if not _HSRC_MC_AVAILABLE:
            logger.warning(
                "[HPC] ⚠️ HSR-MC 模块不可用 (hsrc_mc 包未安装或导入失败)。请确保 tradingagents.hsrc_mc 包已正确安装。",
            )
            self.config.hsrc_mc_enabled = False
            return

        try:
            # 如果外部未注入 hsrc_mc_config，则从环境变量加载
            hsrc_mc_config = self._hsrc_mc_config
            if hsrc_mc_config is None:
                hsrc_mc_config = HSRMCConfig.from_env()

            # 创建 HSRMCManager，传入 LIWMManager 以便调整模块
            self.hsrc_mc_manager = HSRMCManager(
                config=hsrc_mc_config,
                l_iwm_manager=self.l_iwm_manager,
            )

            logger.info(
                f"[HPC] ✅ HSR-MC 管理器已初始化: "
                f"enabled={hsrc_mc_config.enabled}, "
                f"meta_interval={hsrc_mc_config.meta_learning_interval}",
            )

        except Exception as e:
            logger.error(f"[HPC] ❌ HSR-MC 初始化失败: {e}")
            self.config.hsrc_mc_enabled = False
            self.hsrc_mc_manager = None

    def get_initial_hpc_state(self) -> HPCState:
        """获取初始 HPC 状态 (含 L-IWM 特征)"""
        state = HPCState()

        if self.generative_model:
            state.latent_state = self.generative_model.get_latent_state()

        state.enabled_features = {
            "generative_model": self.config.generative_model_enabled,
            "global_workspace": self.config.gws_enabled,
            "active_inference": self.config.active_inference_enabled,
            "causal_inference": self.config.causal_inference_enabled,
            "memory": self.config.memory_enabled,
            # L-IWM 特征
            "l_iwm_enabled": self.config.l_iwm_enabled,
            "l_iwm_rssm": self.config.l_iwm_enabled and (self.l_iwm_manager is not None),
            "l_iwm_efe": self.config.l_iwm_enabled and (self.l_iwm_manager is not None),
            "l_iwm_causal": self.config.l_iwm_enabled and (self.l_iwm_manager is not None),
            "l_iwm_gws": self.config.l_iwm_enabled and (self.l_iwm_manager is not None),
            # HSR-MC 特征
            "hsrc_mc_enabled": self.config.hsrc_mc_enabled,
            "hsrc_mc_initialized": (self.config.hsrc_mc_enabled and self.hsrc_mc_manager is not None),
            # L5: AIF 引擎状态（从 aif_engine_manager 读取，兼容无 manager 的情况）
            "aif_engine": getattr(self, 'aif_engine_manager', None) is not None and self.aif_engine_manager.enabled,
        }

        return state

    def get_enhanced_nodes(self) -> dict[str, Callable]:
        """
        获取所有 HPC-Loop LangGraph 节点函数

        当 L-IWM 启用时，L-IWM 增强节点替换对应的原始 HPC 节点。
        当 L-IWM 子模块禁用时，节点内部自动回退到原始行为。

        Returns:
            Dict[str, Callable]: {节点名称: 节点函数}
        """
        nodes = {}

        # ===== L-IWM 增强节点 (优先) =====
        if self.config.l_iwm_enabled and self.l_iwm_manager is not None:
            # 预测节点 — 使用 RSSM 世界模型
            nodes["HPC_Predict"] = create_l_iwm_prediction_node(self.l_iwm_manager)

            # 市场信息节点 — 使用真实数据管道
            if self.l_iwm_manager.data_pipeline is not None:
                nodes["HPC_MarketInfo"] = create_l_iwm_market_info_node(self.l_iwm_manager)

            # GWS 广播节点 — 使用可学习显著性评估器
            nodes["HPC_GWS_Broadcast"] = create_l_iwm_gws_node(self.l_iwm_manager)

            # EFE 节点 — 使用可学习 EFE 评估器
            if self.l_iwm_manager.efe_evaluator is not None:
                nodes["HPC_ActiveInference"] = create_l_iwm_efe_node(self.l_iwm_manager)

            # 因果节点 — 使用可微分因果发现
            if self.l_iwm_manager.causal_discovery is not None:
                nodes["HPC_CausalReasoning"] = create_l_iwm_causal_node(self.l_iwm_manager)

            # L-IWM 桥接节点 (始终添加，负责 EWC 正则化等)
            nodes["HPC_LIWMBridge"] = create_l_iwm_bridge_node(self.l_iwm_manager)

            # 预测误差节点 — 使用生成模型计算预测误差
            # 注意：setup.py 和 get_enhanced_edges() 均依赖此节点，
            #       L-IWM 分支也必须注册，否则 LangGraph 编译报错
            #       "Found edge starting at unknown node 'HPC_PredictionError'"
            # 不再依赖 prediction_error_enabled 开关，只要生成模型可用就注册
            if self.generative_model:
                nodes["HPC_PredictionError"] = create_hpc_prediction_error_node(self.generative_model)
            else:
                # 即使无生成模型也注册，使用退化模式
                logger.warning("[HPC] ⚠️ 生成模型不可用，注册 HPC_PredictionError 退化模式")
                nodes["HPC_PredictionError"] = create_hpc_prediction_error_node_stub()

            # 记忆存储节点 — 仍然使用原始 HPC 记忆系统
            if self.memory and self.config.memory_enabled:
                nodes["HPC_MemoryStore"] = create_hpc_memory_store_node(self.memory)

            logger.info(f"[HPC] L-IWM 节点已加载: {[k for k in nodes if k.startswith('HPC_')]}")

        else:
            # ===== 原始 HPC 节点 (L-IWM 未启用) =====
            if self.generative_model and self.config.generative_model_enabled:
                nodes["HPC_Predict"] = create_hpc_prediction_node(self.generative_model)

            if self.global_workspace and self.config.gws_enabled:
                nodes["HPC_GWS_Broadcast"] = create_hpc_gws_broadcast_node(self.global_workspace)

            if self.generative_model:
                nodes["HPC_PredictionError"] = create_hpc_prediction_error_node(self.generative_model)

            if self.active_inference and self.config.active_inference_enabled:
                nodes["HPC_ActiveInference"] = create_hpc_active_inference_node(
                    self.active_inference, self.generative_model,
                )

            if self.causal_engine and self.config.causal_inference_enabled:
                nodes["HPC_CausalReasoning"] = create_hpc_causal_node(self.causal_engine)

            if self.memory and self.config.memory_enabled:
                nodes["HPC_MemoryStore"] = create_hpc_memory_store_node(self.memory)

        # ===== HSR-MC 节点独立注册（与 L-IWM 解耦）=====
        if self.config.hsrc_mc_enabled and self.hsrc_mc_manager is not None:
            hsrc_nodes = self.hsrc_mc_manager.get_enhanced_nodes()
            nodes.update(hsrc_nodes)
            logger.info(f"[HPC] HSR-MC 节点已独立加载（与 L-IWM 解耦）: {list(hsrc_nodes.keys())}")

        return nodes

    def get_enhanced_edges(
        self,
        selected_analysts: list[str],
    ) -> list[dict[str, Any]]:
        """
        获取 HPC-Loop 增强的边定义

        当 L-IWM 启用时，自动插入 L-IWM 相关边以适配可学习模块的拓扑结构：
          - HPC_MarketInfo: 在 HPC_Predict 之后插入实时市场数据增强节点
          - HPC_LIWMBridge: 在 HPC_GWS_Broadcast 之后插入后处理桥接节点
            (负责 EWC 正则化、状态同步、模块健康检查)

        原始边作为 L-IWM 禁用时的回退路径。

        Returns:
            List[Dict]: 边定义列表
            [{source: str, target: str, condition: Optional[str]}]
        """
        edges = []

        if not self.enabled:
            return edges

        # ── 前置条件检查 ──
        has_l_iwm = self.config.l_iwm_enabled and self.l_iwm_manager is not None
        has_market_info = has_l_iwm and self.l_iwm_manager.data_pipeline is not None
        has_hsrc_mc = self.config.hsrc_mc_enabled and self.hsrc_mc_manager is not None

        # ────────────────────────────────────────────────────────────
        # 1. START → HPC_Predict
        # ────────────────────────────────────────────────────────────
        if self.config.generative_model_enabled:
            edges.append({"source": "START", "target": "HPC_Predict"})

        # ────────────────────────────────────────────────────────────
        # 2. HPC_Predict → [HPC_MarketInfo →] 第一个分析师
        #    L-IWM 启用且 data_pipeline 可用时，在预测和市场数据
        #    增强后进入分析师链
        # ────────────────────────────────────────────────────────────
        if self.config.generative_model_enabled and selected_analysts:
            first = selected_analysts[0].capitalize()
            if has_market_info:
                edges.append({"source": "HPC_Predict", "target": "HPC_MarketInfo"})
                edges.append({"source": "HPC_MarketInfo", "target": f"{first} Analyst"})
            else:
                edges.append({"source": "HPC_Predict", "target": f"{first} Analyst"})

        # ────────────────────────────────────────────────────────────
        # 3. 分析师链 → HPC_GWS_Broadcast
        #    最后一个分析师的消息清除节点触发全局工作空间广播
        # ────────────────────────────────────────────────────────────
        if self.config.gws_enabled and selected_analysts:
            last = selected_analysts[-1].capitalize()
            edges.append(
                {
                    "source": f"Msg Clear {last}",
                    "target": "HPC_GWS_Broadcast",
                },
            )

        # ────────────────────────────────────────────────────────────
        # 4. HPC_GWS_Broadcast → [HPC_LIWMBridge →] [HSR-MC →] HPC_PredictionError
        #    L-IWM 启用时，桥接节点在广播后执行 EWC 正则化等。
        #    HSR-MC 启用时，在桥接节点后插入 HSR-MC 元学习流程：
        #      hsrc_observe → hsrc_adjust → hsrc_reflect → hsrc_meta_update
        #    然后再进入预测误差计算。
        #    HSR-MC 边使用 HPC 图的节点名，而非 hsrc_mc 默认的节点名。
        # ────────────────────────────────────────────────────────────
        if has_l_iwm:
            edges.append(
                {
                    "source": "HPC_GWS_Broadcast",
                    "target": "HPC_LIWMBridge",
                },
            )

            if has_hsrc_mc:
                # HSR-MC 内部链路 (使用 HPC 图节点名)
                edges.append({"source": "HPC_LIWMBridge", "target": "hsrc_observe"})
                edges.append({"source": "hsrc_observe", "target": "hsrc_adjust"})
                edges.append({"source": "hsrc_adjust", "target": "hsrc_reflect"})
                edges.append({"source": "hsrc_reflect", "target": "hsrc_meta_update"})
                # hsrc_meta_update → HPC_PredictionError 在步骤 5 处理
            elif self.config.prediction_error_enabled:
                edges.append(
                    {
                        "source": "HPC_LIWMBridge",
                        "target": "HPC_PredictionError",
                    },
                )
            elif selected_analysts:
                edges.append(
                    {
                        "source": "HPC_LIWMBridge",
                        "target": "Bull Researcher",
                    },
                )
        elif self.config.gws_enabled and self.config.prediction_error_enabled:
            edges.append(
                {
                    "source": "HPC_GWS_Broadcast",
                    "target": "HPC_PredictionError",
                },
            )

        # ────────────────────────────────────────────────────────────
        # 5. HPC_PredictionError → Bull Researcher (辩论流程入口)
        #    当 HSR-MC 启用时，hsrc_meta_update 连接 HPC_PredictionError，
        #    再连接 Bull Researcher。
        # ────────────────────────────────────────────────────────────
        if self.config.prediction_error_enabled:
            if has_hsrc_mc:
                # HSR-MC 最后一步 → 预测误差
                edges.append(
                    {
                        "source": "hsrc_meta_update",
                        "target": "HPC_PredictionError",
                    },
                )
            # 预测误差 → 辩论流程入口 (始终添加)
            edges.append(
                {
                    "source": "HPC_PredictionError",
                    "target": "Bull Researcher",
                },
            )

        # ────────────────────────────────────────────────────────────
        # 6. HPC_ActiveInference & HPC_CausalReasoning
        #    注意: 这些节点需要插入到 Trader → Risky Analyst 之间
        #    具体位置需要根据 setup.py 中的现有边调整
        #    当前保持 pass，因为分析师链内部已处理推理步骤
        # ────────────────────────────────────────────────────────────
        if self.config.active_inference_enabled or self.config.causal_inference_enabled:
            pass

        # ────────────────────────────────────────────────────────────
        # 7. Risk Judge → HPC_MemoryStore → END
        # ────────────────────────────────────────────────────────────
        if self.config.memory_enabled:
            edges.append(
                {
                    "source": "Risk Judge",
                    "target": "HPC_MemoryStore",
                },
            )
            edges.append(
                {
                    "source": "HPC_MemoryStore",
                    "target": "END",
                },
            )

        return edges


# ==================== 辅助函数 ====================


def _ensure_hpc_state(state: dict[str, Any]) -> HPCState:
    """确保 state['hpc_state'] 是 HPCState 对象而非 dict。

    trading_graph.py 在初始化时调用 HPCState.to_dict() 将对象序列化为 dict 存入
    AgentState，此函数在需要时重建 HPCState 对象，解决 dict/object 类型不匹配问题。
    """
    hpc_data = state.get("hpc_state", {})
    if isinstance(hpc_data, dict):
        hpc_state = HPCState.from_dict(hpc_data) if hpc_data else HPCState()
        state["hpc_state"] = hpc_state  # 回写对象，避免后续节点重复转换
    else:
        hpc_state = hpc_data or HPCState()
    return hpc_state


# [FIX] 2026-06-22: efinance 已移除，改用标准化列名搜索 + BaoStock 回退
def _fetch_realtime_price(ticker: str) -> float | None:
    """获取股价：优先通过 _safe_get_quote 查询（标准化列名），回退 BaoStock 最近日收盘价

    用户需求：只需要昨天收盘价即可。
    """
    if not ticker:
        return None

    stock_code = _normalize_symbol(ticker)

    # 方案 A：通过 _safe_get_quote 获取（标准化后的英文列名优先）
    try:
        df = _safe_get_quote(stock_code)
        if df is not None and not df.empty:
            # [FIX P0] 优先搜索标准化后的英文列名，兼容中文旧列名
            for col in ("close", "price", "最新价", "当前价"):
                if col in df.columns:
                    val = df[col].iloc[0]
                    if val is not None:
                        price = float(val)
                        logger.info(f"[HPC] ✅ 实时价格: {ticker} = {price}")
                        return price
            # [FIX 2026-06-21] 新 API 列名回退（昨收）
            for col in ("pre_close", "昨收", "昨收价"):
                if col in df.columns:
                    val = df[col].iloc[0]
                    if val is not None:
                        price = float(val)
                        logger.info(f"[HPC] ✅ 实时价格（昨收回退）: {ticker} = {price}")
                        return price
        logger.warning(f"[HPC] ⚠️ _safe_get_quote 未返回价格数据: {ticker}")
    except ImportError:
        logger.debug("[HPC] 数据源模块未安装")
    except Exception as e:
        logger.warning(f"[HPC] ⚠️ 实时价格获取失败: {e}")

    # 方案 B：回退 BaoStock 最近日收盘价 —— 用户明确只需要昨天数据
    try:
        from datetime import datetime, timedelta

        import pandas as pd

        from tradingagents.dataflows.data_source_manager import get_data_source_manager

        manager = get_data_source_manager()
        # 取最近 10 个自然日确保覆盖交易日间隔
        today = datetime.now()
        start = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        df = manager.get_stock_dataframe(stock_code, start_date=start, end_date=end)
        if df is not None and not df.empty:
            last_row = df.iloc[-1]
            close_price = None
            for col in ("close", "收盘", "收盘价", "Close", "pre_close", "昨收", "昨收价"):
                if col in df.columns and pd.notna(last_row.get(col)):
                    close_price = float(last_row[col])
                    break
            if close_price is not None:
                date_str = last_row.get("date") or last_row.get("日期") or "N/A"
                logger.info(f"[HPC] ✅ BaoStock 最近日收盘价: {ticker} = {close_price} (日期: {date_str})")
                return close_price

        logger.warning(f"[HPC] ⚠️ BaoStock 回退也未获取到价格数据: {ticker}")
    except Exception as e:
        logger.warning(f"[HPC] ⚠️ BaoStock 回退价格获取失败: {e}")

    return None


def _extract_market_info(state: dict[str, Any]) -> dict[str, Any]:
    """从 LangGraph state 中提取市场信息"""
    ticker = state.get("company_of_interest", "")
    state.get("market_report", "")

    # 尝试获取实时价格
    real_price = _fetch_realtime_price(ticker)
    has_real_price = real_price is not None

    if has_real_price:
        logger.info(f"[HPC] ✅ 使用实时市场数据: {ticker} 当前价 = {real_price}")
    else:
        logger.warning("[HPC] ⚠️ 实时价格数据不可用，价格相关认知计算将使用占位值。请确认网络连接或数据源配置。")

    return {
        "price": real_price,  # 有实时数据则使用，None 由上游调用方处理
        "volatility": 0.02,
        "sentiment": float(len(state.get("sentiment_report", ""))) / 1000.0 if state.get("sentiment_report") else 0.5,
        "regime": "unknown",
        "ticker": ticker,
        "date": state.get("trade_date", ""),
    }


def _extract_aif_observation_for_hsrc(state: dict[str, Any]) -> dict[str, Any]:
    """
    融合架构辅助函数:
    从 AIF state 中提取观测信息，供 HSR-MC 元控制器使用。

    在融合模式下，AIF 的观测 (AIF_Observe) 发生在 HSR-MC 之前，
    此函数将 AIF 观测结果桥接到 HSR-MC 的输入格式。
    """
    hpc_state = _ensure_hpc_state(state)
    aif_state = state.get("aif_state", {})

    # 从 AIF state 提取观测
    if isinstance(aif_state, dict):
        aif_observation = {
            "aif_obs": aif_state.get("observation", ""),
            "aif_belief_mean": aif_state.get("belief", {}).get("mean", [0.0])[0]
            if isinstance(aif_state.get("belief"), dict)
            else 0.0,
            "aif_prediction_error": aif_state.get("prediction_error", 0.0),
            "aif_efe": aif_state.get("efe", 0.0),
        }
    else:
        aif_observation = {
            "aif_obs": "",
            "aif_belief_mean": 0.0,
            "aif_prediction_error": 0.0,
            "aif_efe": 0.0,
        }

    # 融合到 hpc_state 供 HSR-MC 消费
    hpc_state.enabled_features["aif_observation_available"] = True
    state["hpc_state"] = hpc_state

    logger.info(
        f"[Fusion:HPC] AIF 观测已桥接到 HSR-MC: "
        f"belief_mean={aif_observation['aif_belief_mean']:.3f}, "
        f"prediction_error={aif_observation['aif_prediction_error']:.3f}",
    )

    return aif_observation


def _extract_actual_observation(state: dict[str, Any]) -> dict[str, Any]:
    """
    从分析师报告中提取"实际观测"的近似值
    """
    ticker = state.get("company_of_interest", "")

    # 尝试获取实时价格作为观测值
    real_price = _fetch_realtime_price(ticker)
    if real_price is not None:
        logger.info(f"[HPC] ✅ 使用实时价格作为实际观测: {ticker} = {real_price}")
        return {
            "price": real_price,
            "volatility": 0.02,
            "sentiment": 0.5,
            "macro": None,
        }

    logger.warning("[HPC] ⚠️ 实际观测数据不可用，预测误差计算将使用占位值。")

    return {
        "price": None,
        "volatility": 0.02,
        "sentiment": 0.5,
        "macro": None,
    }
