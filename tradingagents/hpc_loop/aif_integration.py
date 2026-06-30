# TradingAgents/hpc_loop/aif_integration.py
"""
AIF-Engine LangGraph 集成模块

提供新的 AIF 引擎作为 LangGraph 节点函数，
与 hpc_integration.py 并行存在，通过 use_aif_engine 配置开关切换。

设计原则:
1. 非侵入式: 不修改现有代码，通过配置切换
2. 兼容性: 输出格式与现有 HPCState 兼容
3. 可观察: 所有自由能和 EFE 计算均可记录和可视化

与 hpc_integration.py 的对比:
    hpc_predict_node        → aif_predict_node       (生成模型预测)
    4 个分析师节点           → aif_llm_prior_node     (LLM 先验注入)
    hpc_gws_broadcast_node   → aif_observe_node       (市场观测)
    hpc_prediction_error_node→ aif_update_belief_node (变分信念更新)
    hpc_active_inference_node→ aif_select_action_node (EFE 最小化)
    (新增)                   → aif_learn_node          (长期学习)
"""

import logging

# [FIX] 2026-06-22: efinance 已移除，内联股票代码标准化函数
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from tradingagents.agents.utils.agent_utils import _safe_get_field

import pandas as pd

from tradingagents.core.price_cache import price_cache
from tradingagents.dataflows.data_source_manager import get_data_source_manager

from .hpc_config import HPCLoopConfig
from .hpc_state import HPCState, MarketPrediction
from .hpc_state import MarketLatentState as HpcMarketLatentState


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
        # 使用现有数据源管理器获取行情
        data = manager.get_stock_dataframe(symbol)
        if data is not None and not data.empty:
            # 写入缓存
            price_cache.set(symbol, data)
            return data
    return pd.DataFrame()


# AIF 引擎导入
from .aif_engine import (
    _JAX_AVAILABLE,
    ACTION_NAMES,
    DEFAULT_OBS_DIM,
    ActiveInference,
    BeliefUpdater,
    GenerativeModel,
    LLMPriorInjector,
)
from .aif_engine import (
    MarketLatentState as AIFMarketLatentState,
)

# 分层模型和元学习器（可选，可导入失败时静默降级）
try:
    from .hierarchical_model import (
        HierarchicalGenModel,
        LayerConfig,
        TimeScale,
        build_custom_model,
        build_default_4layer_model,
    )

    _HIERARCHICAL_AVAILABLE = True
except ImportError:
    _HIERARCHICAL_AVAILABLE = False
    HierarchicalGenModel = None  # type: ignore

try:
    from .meta_learner import (
        MetaLearner,
        MetaLearnerConfig,
        create_default_meta_learner,
        create_fast_meta_learner,
    )

    _META_AVAILABLE = True
except ImportError:
    _META_AVAILABLE = False
    MetaLearner = None  # type: ignore

logger = logging.getLogger("hpc_loop.aif_integration")


# ========================================================================
# [方案B] 防御性 AIF 返回值清洗工具
# ========================================================================
# 方案B 目标: 确保 AIF 节点绝不泄露分析师管线字段到 state 更新中，
# 防止 LangGraph InvalidUpdateError:
#   "At key 'market_report': Can receive only one value per step"
#
# 这些字段由分析师节点写入，AIF 节点不应修改它们。
# 在 Fusion 模式下，多条路径可能并发写入同一通道。
# 清洗函数作为 defense-in-depth，确保 AIF 节点返回值绝对不含这些键。
_ANALYST_EXCLUDE_KEYS: frozenset = frozenset(
    {
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
        "past_context",
    },
)


def _sanitize_aif_return(
    return_dict: dict[str, Any],
    source: str = "unknown",
) -> dict[str, Any]:
    """
    从 AIF 节点返回值中移除分析师管线字段，防止 LangGraph 通道冲突。

    Args:
        return_dict: AIF 节点的原始返回值
        source: 节点名称，用于日志标识

    Returns:
        清洗后的返回值（只含 AIF 相关字段）
    """
    sanitized = {}
    for key, value in return_dict.items():
        if key in _ANALYST_EXCLUDE_KEYS:
            logger.debug(f"[方案B] {source}: 过滤分析师字段 '{key}' — 防止 LangGraph 通道冲突")
        # 递归清理嵌套字典，防止分析师字段通过嵌套路径泄漏
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_aif_return(value, f"{source}.{key}")
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_aif_return(item, f"{source}.{key}[{i}]") if isinstance(item, dict) else item
                for i, item in enumerate(value)
            ]
        else:
            sanitized[key] = value
    return sanitized


# ====================================================================
# 辅助函数: 在 AIF 和 HPC 状态之间转换
# ====================================================================


def _aif_to_hpc_state(aif_state: AIFMarketLatentState) -> dict[str, Any]:
    """
    将 AIF MarketLatentState 转换为与 HPCState 兼容的 dict

    确保 LangGraph state 中的 hpc_state 字段格式一致。
    """
    return aif_state.to_dict()


def _hpc_to_aif_state(hpc_state: HPCState) -> AIFMarketLatentState:
    """
    从 HPCState 重建 AIF MarketLatentState

    用于在切换引擎时保持状态连续性。
    """
    if hpc_state.latent_state:
        return AIFMarketLatentState.from_dict(hpc_state.latent_state.to_dict())
    return AIFMarketLatentState()


def _ensure_hpc_state(state: dict[str, Any]) -> HPCState:
    """
    确保 state['hpc_state'] 是 HPCState 对象 (从 hpc_integration 复制)
    """
    hpc_data = state.get("hpc_state", {})
    if isinstance(hpc_data, dict):
        hpc_state = HPCState.from_dict(hpc_data) if hpc_data else HPCState()
        state["hpc_state"] = hpc_state
    else:
        hpc_state = hpc_data or HPCState()
    return hpc_state


def _extract_market_info(state: dict[str, Any]) -> dict[str, Any]:
    """从 LangGraph state 中提取市场信息（融合评估用）"""
    ticker = state.get("company_of_interest", "")
    real_price = None

    # 尝试 1: 通过 _safe_get_quote 获取（标准化后的英文列名优先）
    try:
        stock_code = _normalize_symbol(ticker)
        df = _safe_get_quote(stock_code)
        if df is not None and not df.empty:
            # [FIX P0] 优先搜索英文列名，兼容中文旧列名
            for col in ("close", "price", "最新价", "当前价"):
                if col in df.columns:
                    val = df[col].iloc[0]
                    if val is not None:
                        real_price = float(val)
                        break
            # 昨收回退
            if real_price is None:
                for col in ("pre_close", "昨收", "昨收价"):
                    if col in df.columns:
                        val = df[col].iloc[0]
                        if val is not None:
                            real_price = float(val)
                            break
    except Exception as e:
        logger.debug(f"[AIF] 价格获取尝试1失败: {e}")

    # 🔴 P0 FIX: 尝试 2 — 通过 BaoStock 回退（类似 HPC _fetch_realtime_price）
    if real_price is None:
        try:
            manager = get_data_source_manager()
            today = datetime.now()
            start = (today - timedelta(days=10)).strftime("%Y-%m-%d")
            end = today.strftime("%Y-%m-%d")
            df = manager.get_stock_dataframe(stock_code, start_date=start, end_date=end)
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                for col in ("close", "收盘", "收盘价", "Close", "pre_close", "昨收", "昨收价"):
                    if col in df.columns and pd.notna(last_row.get(col)):
                        real_price = float(last_row[col])
                        break
                if real_price is not None:
                    logger.info(f"[AIF] ✅ BaoStock 回退价格: {ticker} = {real_price}")
        except Exception as e:
            logger.debug(f"[AIF] 价格获取尝试2失败: {e}")

    if real_price is not None:
        logger.info(f"[AIF] ✅ 使用数据源管理器获取价格: {ticker} = {real_price}")
        return {
            "price": real_price,
            "volatility": 0.02,
            "sentiment": float(len(state.get("sentiment_report", ""))) / 1000.0
            if state.get("sentiment_report")
            else 0.5,
            "regime": "unknown",
            "ticker": ticker,
            "date": state.get("trade_date", ""),
        }

    logger.warning("[AIF] ⚠️ 价格数据不可用：数据源未返回有效价格数据，价格相关认知计算将被跳过。")
    return {
        "price": None,
        "volatility": 0.02,
        "sentiment": float(len(state.get("sentiment_report", ""))) / 1000.0 if state.get("sentiment_report") else 0.5,
        "regime": "unknown",
        "ticker": ticker,
        "date": state.get("trade_date", ""),
    }


# ====================================================================
# AIF LangGraph 节点函数
# ====================================================================


def create_aif_predict_node(generative_model: GenerativeModel, n_samples: int = 200) -> Callable:
    """
    创建 AIF 预测节点 (替代 hpc_predict_node)

    使用 GenerativeModel 的层级生成模型生成对未来市场的预测分布。
    输出是概率分布（均值 + 置信区间），而非单点估计。

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_predict_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[AIF] 🔮 生成模型预测 (GenerativeModel)...")

        hpc_state = _ensure_hpc_state(state)

        # ---- 1. 获取或初始化 AIF 隐状态 ----
        aif_belief = _hpc_to_aif_state(hpc_state)

        # ---- 2. 转化为隐状态向量 ----
        s_t = aif_belief.to_latent_vector(target_dim=generative_model.latent_dim)

        # === [BUG-NEW-006 修复] 维度防御 Layer-4: 入口维度验证 + 诊断日志 ===
        # 在进入 GenerativeModel 前捕获维度异常，记录详细诊断信息
        # [FIX P2-BUG3] 分层模式下应使用 total_latent_dim（120D）而非 latent_dim（8D）
        if generative_model.use_hierarchical and generative_model.hierarchical_model is not None:
            expected_dim = generative_model.hierarchical_model.total_latent_dim  # @property, 120D
        else:
            expected_dim = getattr(generative_model, "latent_dim", 8)
        if hasattr(s_t, "shape") and s_t.shape[0] != expected_dim:
            logger.warning(
                f"[AIF] ❌ [BUG-NEW-006] 维度不匹配检测: "
                f"s_t.shape=({s_t.shape[0]},), 期望 ({expected_dim},). "
                f"触发根因诊断...",
                exc_info=True,
            )
            # 深度诊断: 检查 to_latent_vector 各组件维度
            regime_probs = getattr(aif_belief, "regime_probs", None)
            diag_parts = {
                "regime_probs_shape": regime_probs.shape if hasattr(regime_probs, "shape") else "N/A",
                "regime_logits_shape": aif_belief.regime_logits.shape
                if hasattr(aif_belief.regime_logits, "shape")
                else "N/A",
                "volatility_mu": type(aif_belief.volatility_mu).__name__,
                "trend_mu": type(aif_belief.trend_mu).__name__,
                "momentum": type(aif_belief.momentum).__name__,
                "sentiment": type(aif_belief.sentiment).__name__,
                "hpc_latent_state_type": type(hpc_state.latent_state).__name__ if hpc_state.latent_state else "None",
            }
            logger.warning(f"[AIF] [BUG-NEW-006] 诊断: {diag_parts}", exc_info=True)

        # [FIX 2026-06-18 P0] 异常保护: 捕获 JAX/AIF 计算异常，返回降级预测
        try:
            prediction = generative_model.generate_prediction(
                s_t=s_t,
                n_samples=n_samples,
                horizon=1,
            )
        except Exception as e:
            logger.warning(f"[AIF] [FIX P0] ⚠️ 生成预测失败，降级到默认预测: {e}")
            prediction = {
                "price_mean": 0.0,
                "price_std": 0.02,
                "price_lower": -0.02,
                "price_upper": 0.02,
                "volatility_mean": 0.02,
                "volatility_std": 0.01,
            }

        # ---- 4. 同步回 HPCState ----
        hpc_state.latent_state = HpcMarketLatentState.from_dict(_aif_to_hpc_state(aif_belief))
        # 构造完整的 MarketPrediction 对象（替代原来 type('obj') 动态类，
        # 确保与 HPC_PredictionError 节点兼容，后者需要访问 sentiment_prediction 等字段）
        hpc_state.last_prediction = MarketPrediction(
            price_prediction={
                "mean": prediction.get("price_mean", 0.0),
                "lower": prediction.get("price_lower", -0.02),
                "upper": prediction.get("price_upper", 0.02),
            },
            volatility_prediction={
                "mean": prediction.get("volatility_mean", 0.02),
            },
            # 初始化为空 dict 确保任何 .get() 调用安全，避免 None.get() 崩溃
            sentiment_prediction={},
            confidence_scores={
                "overall": 1.0 / (1.0 + abs(prediction.get("price_std", 0.02))),
            },
            timestamp=datetime.now().isoformat(),
        )
        hpc_state.step_counter += 1

        logger.info(
            f"[AIF] ✅ 预测完成: "
            f"价格均值={prediction.get('price_mean', 0.0):.5f}, "
            f"价格标准差={prediction.get('price_std', 0.0):.4f}",
        )

        return _sanitize_aif_return(
            {"hpc_state": hpc_state, "aif_state": aif_belief.to_dict()},
            source="aif_predict_node",
        )

    return aif_predict_node


def create_aif_llm_prior_node(prior_injector: LLMPriorInjector) -> Callable:
    """
    创建 AIF LLM 先验注入节点 (替代 4 个独立分析师节点)

    将 LLM 分析从"生成独立报告"变为"提供先验分布参数"。
    所有分析师类型共享同一个注入器。

    输入: 从 state 中获取各分析师的 LLM 输出
    输出: 更新后的隐状态 (含先验注入)

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_llm_prior_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[AIF] 📝 LLM 先验注入...")

        hpc_state = _ensure_hpc_state(state)
        aif_belief = _hpc_to_aif_state(hpc_state)

        # ---- 1. 收集所有分析师的输出 ----
        analyst_outputs: list[tuple[str, str, str]] = [
            ("market", "市场分析师", state.get("market_report", "")),
            ("fundamentals", "基本面分析师", state.get("fundamentals_report", "")),
            ("news", "新闻分析师", state.get("news_report", "")),
            ("social", "社媒分析师", state.get("sentiment_report", "")),
        ]

        # ---- 2. 逐个注入先验 ----
        injection_summary = []
        for analyst_type, analyst_name, report in analyst_outputs:
            if not report:
                continue

            # 设置注入器的分析师类型
            prior_injector.analyst_type = analyst_type

            # 提取先验参数
            prior_params = prior_injector.extract_prior(report)

            # 注入先验
            aif_belief = prior_injector.inject_prior(aif_belief, prior_params)

            injection_summary.append(
                {
                    "analyst": analyst_name,
                    "type": analyst_type,
                    "confidence": prior_params.get("confidence", 0.5),
                    "regime_prior": prior_params.get("regime_prior", []).tolist()
                    if hasattr(prior_params.get("regime_prior", []), "tolist")
                    else list(prior_params.get("regime_prior", [])),
                },
            )

            logger.debug(f"[AIF]   {analyst_name}: 置信度={prior_params['confidence']:.2f}")

        # ---- 3. 同步回 HPCState ----
        hpc_state.latent_state = HpcMarketLatentState.from_dict(_aif_to_hpc_state(aif_belief))

        # 记录注入摘要到 state
        state["aif_prior_injections"] = injection_summary
        state["aif_current_belief"] = _aif_to_hpc_state(aif_belief)

        logger.info(f"[AIF] ✅ 先验注入完成: {len(injection_summary)} 个分析师, 当前体制={aif_belief.get_regime()}")

        return {
            "hpc_state": hpc_state,
            "aif_prior_injections": injection_summary,
            "aif_state": aif_belief.to_dict(),
        }

    return aif_llm_prior_node


def create_aif_observe_node() -> Callable:
    """
    创建 AIF 观测节点

    从 state 中提取市场观测数据，构建观测向量。
    这个节点不做推理，只做数据提取和格式化。

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_observe_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.debug("[AIF] 👁️ 获取市场观测...")

        hpc_state = _ensure_hpc_state(state)

        # ---- 提取观测数据 ----
        observation = {
            "price_change": state.get("price_change", 0.0),
            "volatility": state.get("volatility", 0.02),
            "sentiment": state.get("sentiment", 0.0),
            "volume": state.get("volume", 0.0),
            "spread": state.get("spread", 0.0),
            "timestamp": datetime.now().isoformat(),
        }

        # 如果没有真实数据，尝试从分析师报告估算
        if observation["price_change"] == 0.0:
            market_report = state.get("market_report", "")
            if market_report:
                # 使用报告长度作为代理 (与现有代码兼容)
                observation["price_change"] = len(market_report) * 0.0001

        # 保存观测到 state
        state["aif_observation"] = observation

        return _sanitize_aif_return(
            {"hpc_state": hpc_state},
            source="aif_observe_node",
        )

    return aif_observe_node


def create_aif_update_belief_node(
    belief_updater: BeliefUpdater | None,
    generative_model: GenerativeModel | None = None,
) -> Callable:
    """
    创建 AIF 信念更新节点 (替代 hpc_prediction_error_node)

    基于真实观测，使用变分贝叶斯方法更新隐状态信念。
    当 belief_updater 为 None 时使用退化模式（简单信念传播）。

    Args:
        belief_updater: BeliefUpdater 实例 (可选)
        generative_model: GenerativeModel 实例 (可选，用于自由能计算)

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_update_belief_node(state: dict[str, Any]) -> dict[str, Any]:
        hpc_state = _ensure_hpc_state(state)
        aif_belief = _hpc_to_aif_state(hpc_state)

        # ---- 获取观测 ----
        observation = state.get("aif_observation", {})
        if not observation:
            observation = {
                "price_change": state.get("price_change", 0.0),
                "volatility": state.get("volatility", 0.02),
                "sentiment": state.get("sentiment", 0.0),
            }

        if belief_updater is not None:
            logger.info("[AIF] 🔄 变分信念更新...")
            gm = generative_model
            if gm is None and hasattr(belief_updater, "generative_model"):
                gm = belief_updater.generative_model

            updated_belief = belief_updater.update(
                belief_state=aif_belief,
                observation=observation,
                generative_model=gm,
            )
            hpc_state.latent_state = HpcMarketLatentState.from_dict(_aif_to_hpc_state(updated_belief))

            # ---- 计算自由能 (用于日志) ----
            if gm is not None and _JAX_AVAILABLE:
                try:
                    import jax.numpy as jnp
                    obs_vec = jnp.array([
                        observation.get("price_change", 0.0),
                        observation.get("volatility", 0.02),
                        observation.get("sentiment", 0.0),
                        observation.get("volume", 0.0),
                        observation.get("spread", 0.0),
                    ], dtype=jnp.float32)
                    free_energy = gm.compute_free_energy(obs_vec, updated_belief)
                    logger.info(f"[AIF]   变分自由能 F = {free_energy:.5f}")
                    state["aif_free_energy"] = free_energy
                except Exception as e:
                    logger.debug(f"[AIF]   自由能计算跳过: {e}")

            current_regime = updated_belief.get_regime()
            current_uncertainty = updated_belief.total_uncertainty

            # === [FIX 2026-06-26] 临界慢化检测 — 信念历史自相关 ===
            # 参考: Dakos et al. 2012 Nature — 自相关时间作为体制切换前兆
            # 当信念的自相关系数持续升高时，系统接近临界点（体制切换）
            # =======================================================
            import time as _time
            belief_history = state.get("_aif_belief_history", [])
            belief_history.append({
                "time": _time.time(),
                "regime": current_regime,
                "uncertainty": float(current_uncertainty) if current_uncertainty else 0.5,
            })
            # 只保留最近20条
            if len(belief_history) > 20:
                belief_history = belief_history[-20:]
            state["_aif_belief_history"] = belief_history

            # 检测临界慢化（至少10个样本才计算）
            hsrc_critical_slowing = 0.0
            hsrc_regime_risk = 0.0
            if len(belief_history) >= 10:
                recent = belief_history[-10:]
                values = [h["uncertainty"] for h in recent]
                n_vals = len(values)
                mean_v = sum(values) / n_vals
                var_v = sum((v - mean_v) ** 2 for v in values) / (n_vals - 1)
                if var_v > 1e-8:
                    # 滞后1自相关: ρ₁ = E[(x_t-μ)(x_{t+1}-μ)] / σ²
                    ac = sum((values[i] - mean_v) * (values[i+1] - mean_v) for i in range(n_vals - 1)) / (var_v * (n_vals - 1))
                    hsrc_critical_slowing = max(0.0, min(1.0, ac))
                    # 切换风险: 自相关 > 0.7 时风险快速上升
                    hsrc_regime_risk = max(0.0, min(1.0, (ac - 0.5) * 2.0))

                    if hsrc_critical_slowing > 0.7:
                        logger.warning(
                            "[AIF-CSD] ⚠️ 临界慢化检测: ρ=%.4f, 体制切换风险=%.1f%%",
                            hsrc_critical_slowing,
                            hsrc_regime_risk * 100,
                        )

            state["hsrc_critical_slowing"] = hsrc_critical_slowing
            state["hsrc_regime_risk"] = hsrc_regime_risk

            logger.info(
                f"[AIF] ✅ 信念更新完成: "
                f"体制={current_regime}, "
                f"不确定性={current_uncertainty:.3f}, "
                f"更新次数={belief_updater.get_update_count()}, "
                f"临界慢化ρ={hsrc_critical_slowing:.3f}",
            )
            return _sanitize_aif_return(
                {"hpc_state": hpc_state, "aif_state": updated_belief.to_dict()},
            )
        else:
            logger.info("[AIF] ⚠️ 信念更新器不可用，使用退化模式（传递当前信念）")
            return _sanitize_aif_return(
                {"hpc_state": hpc_state, "aif_state": aif_belief.to_dict()},
            source="aif_update_belief_node",
        )

    return aif_update_belief_node


def create_aif_select_action_node(
    active_inference: ActiveInference,
    n_samples: int = 200,
    temperature: float = 1.2,
) -> Callable:
    """
    创建 AIF 行动选择节点 (替代 hpc_active_inference_node)

    使用期望自由能 (EFE) 最小化选择行动。
    不是硬编码 if-else 规则，而是真正的 Monte Carlo EFE 计算。

    Args:
        active_inference: ActiveInference 实例

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_select_action_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.info("[AIF] 🎯 期望自由能最小化 → 行动选择...")

        hpc_state = _ensure_hpc_state(state)
        aif_belief = _hpc_to_aif_state(hpc_state)

        # [FIX 2026-06-18 P0] 维度自动适配: 确保 belief 向量维度与 ActiveInference.generative_model 一致
        if active_inference is not None and active_inference.generative_model is not None:
            _adapted = aif_belief.to_latent_vector(target_dim=active_inference.generative_model.latent_dim)
            if _adapted.shape[0] != 8:  # 非默认8维 → 重建 belief 以匹配模型维度
                aif_belief = AIFMarketLatentState.from_latent_vector(
                    _adapted, temperature=getattr(aif_belief, "_temperature", 1.0),
                )

        # ---- 1. 获取候选行动 ----
        candidate_actions = state.get("aif_candidate_actions", ACTION_NAMES)

        # ---- 2. 计算 EFE 并选择行动 ----
        # [FIX P0] 先捕获闭包默认值，避免 Python 闭包变量在赋值语句中引用自身前被标记为局部变量
        _n_samples = n_samples
        _temperature = temperature
        n_samples = state.get("aif_efe_samples", _n_samples)
        temperature = state.get("aif_action_temperature", _temperature)
        # [移除 2026-06-22] 移除了错误的 Bug3 超时保护。
        # 根因分析确认 180 秒阻塞来自 diffusion_advisor_node 的 DDIM 采样，
        # 而非 select_action。真实修复在 diffusion 模块实现渐进式采样+自适应精度。
        # 详见 plans/ 中的根因存档。
        try:
            result = active_inference.select_action(
                belief_state=aif_belief,
                candidate_actions=candidate_actions,
                n_samples=n_samples,
                temperature=temperature,
            )
        except Exception as e:
            logger.warning(f"[AIF] [FIX P0] ⚠️ EFE 行动选择失败，回退到默认行动 'hold': {e}")
            result = {
                "selected_action": "hold",
                "efe": 0.0,
                "pragmatic": 0.0,
                "epistemic": 0.0,
                "all_evaluations": [],
            }
        selected_action = result["selected_action"]
        efe = result["efe"]
        pragmatic = result.get("pragmatic", 0.0)
        epistemic = result.get("epistemic", 0.0)
        evaluations = result.get("all_evaluations", [])

        # [Bug 7 修复] 2026-06-22: 不从 EFE 值推导置信度，改用候选行动间的 EFE 离散度
        # 原公式 `1.0 - min(abs(efe), 1.0)` 在 EFE 接近 0 时产生接近 1 的置信度，这不可靠
        if evaluations and len(evaluations) > 1:
            efe_values = [abs(e.get("efe", 0.0)) for e in evaluations]
            efe_range = max(efe_values) - min(efe_values)
            # EFE 离散度越大 → 区分度越高 → 置信度越高
            confidence = min(efe_range / (abs(efe) + 1e-8), 0.9) if abs(efe) > 1e-8 else 0.5
            confidence = max(confidence, 0.3)  # 最低 0.3
            confidence = min(confidence, 0.95)  # 最高 0.95
        else:
            confidence = 0.5  # 默认中等置信度

        # ---- 3. 同步到 HPCState (兼容格式) ----
        hpc_state.selected_action = {
            "action_id": selected_action,
            "expected_free_energy": efe,
            "epistemic_value": epistemic,
            "pragmatic_value": pragmatic,
            "confidence": confidence,
            "source": "aif_engine",
            "efe_decomposition": {
                "epistemic": epistemic,
                "pragmatic": pragmatic,
                "total": efe,
            },
        }

        hpc_state.candidate_actions = [
            {
                "action_id": e.get("action", "unknown"),
                "efe": e.get("efe", 0.0),
                "epistemic": e.get("epistemic", 0.0),
                "pragmatic": e.get("pragmatic", 0.0),
                "source": "aif_engine",
            }
            for e in evaluations
        ]

        # ---- 4. 记录到 AIF state ----
        state["aif_selection"] = result
        state["aif_action_trace"] = active_inference.get_action_trace()

        logger.info(
            f"[AIF] ✅ 行动选择: '{selected_action}' "
            f"(EFE={efe:.5f}, "
            f"实用={pragmatic:.5f}, "
            f"认知={epistemic:.5f}, "
            f"置信度={confidence:.3f})",  # [Bug 7] 日志输出修复后的置信度
        )

        return _sanitize_aif_return(
            {"hpc_state": hpc_state, "aif_state": aif_belief.to_dict()},
            source="aif_select_action_node",
        )

    return aif_select_action_node


def create_aif_learn_node(
    generative_model: GenerativeModel,
    belief_updater: BeliefUpdater | None = None,
) -> Callable:
    """
    创建 AIF 学习节点 (新增——hpc_integration 中没有对应节点)

    在每一步之后更新生成模型参数 (长期学习)。
    使用预测误差作为学习信号，通过 JAX 梯度下降更新参数。

    学习模式:
    1. online: 每步更新 (快速适应)
    2. batch: 积累经验后批量更新 (稳定学习)

    Args:
        generative_model: GenerativeModel 实例
        belief_updater: BeliefUpdater 实例 (可选)

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]
    """

    def aif_learn_node(state: dict[str, Any]) -> dict[str, Any]:
        logger.debug("[AIF] 📚 生成模型在线学习...")

        hpc_state = _ensure_hpc_state(state)
        aif_belief = _hpc_to_aif_state(hpc_state)

        # ---- 1. 获取观测 ----
        observation = state.get("aif_observation", {})
        if not observation:
            observation = {
                "price_change": state.get("price_change", 0.0),
                "volatility": state.get("volatility", 0.02),
                "sentiment": state.get("sentiment", 0.0),
            }

        # ---- 2. 更新归一化统计 ----
        s_t = aif_belief.to_latent_vector(target_dim=generative_model.latent_dim)
        generative_model.update_norm_stats(s_t.reshape(1, -1))

        # ---- 3. 计算并记录自由能 ----
        if _JAX_AVAILABLE and hasattr(generative_model, "compute_free_energy"):
            try:
                import jax.numpy as jnp

                obs_vec = jnp.array(
                    [
                        observation.get("price_change", 0.0),
                        observation.get("volatility", 0.02),
                        observation.get("sentiment", 0.0),
                        observation.get("volume", 0.0),
                        observation.get("spread", 0.0),
                    ],
                    dtype=jnp.float32,
                )
                free_energy = generative_model.compute_free_energy(obs_vec, aif_belief)
                state["aif_free_energy_history"] = (state.get("aif_free_energy_history") or []) + [free_energy]
            except Exception as e:
                logger.warning(f"AIF 集成调用失败: {e}", exc_info=True)

        # ---- 4. 触发 SVI 更新 (如果配置) ----
        if belief_updater is not None and belief_updater.use_svi:
            if hpc_state.step_counter % 10 == 0:  # 每 10 步
                svi_result = belief_updater.update_svi(observation, n_steps=50)
                if svi_result.get("status") == "completed":
                    logger.debug(f"[AIF]   SVI: loss={svi_result['final_loss']:.4f}")

        logger.debug(f"[AIF] ✅ 学习完成: 步骤={hpc_state.step_counter}")

        return _sanitize_aif_return(
            {"hpc_state": hpc_state, "aif_state": aif_belief.to_dict()},
            source="aif_learn_node",
        )

    return aif_learn_node


# ====================================================================
# 元循环节点 (Meta-Learning Self-Referential Cycle)
# ====================================================================


def create_meta_cycle_node(
    generative_model: GenerativeModel,
    meta_cycle_interval: int = 50,
) -> Callable:
    """
    创建 AIF 元循环节点（新增——双循环拓扑的内环）

    此节点每 meta_cycle_interval 步执行一次元学习自指循环：
    1. 调用 generative_model.run_meta_cycle() 诊断模型健康度
    2. 如果检测到性能退化，调整 meta_temperature 使行动更保守
    3. 输出诊断报告供观察和日志

    LangGraph 节点签名: (state: Dict[str, Any]) -> Dict[str, Any]

    Args:
        generative_model: GenerativeModel 实例（应已包含 meta_learner）
        meta_cycle_interval: 元循环执行间隔（步数）
    """
    _cycle_counter: list[int] = [0]  # 闭包可变计数器

    def aif_meta_cycle_node(state: dict[str, Any]) -> dict[str, Any]:
        _cycle_counter[0] += 1
        step = _cycle_counter[0]

        # 只在间隔步执行实际诊断
        if step % meta_cycle_interval != 0:
            return {}

        logger.info(f"[AIF] 🔁 元循环触发 (step={step}, interval={meta_cycle_interval})...")

        hpc_state = _ensure_hpc_state(state)
        aif_belief = _hpc_to_aif_state(hpc_state)

        # ---- 1. 运行元循环诊断 ----
        meta_result = generative_model.run_meta_cycle(
            step=step,
            meta_cycle_interval=meta_cycle_interval,
        )

        meta_triggered = meta_result.get("meta_triggered", False)
        meta_report = meta_result.get("meta_report", {})
        degradation_detected = meta_result.get("degradation_detected", False)

        # ---- 2. 如果检测到退化，建议保守行动 ----
        meta_temperature: float | None = None
        if degradation_detected:
            meta_temperature = 2.0  # 温度升高 → 行动更保守 / 更探索
            logger.warning(f"[AIF] ⚠️ 元学习器检测到退化，建议 meta_temperature={meta_temperature}")

        # ---- 3. 保存双自由能分解 ----
        dual_fe = generative_model.get_dual_free_energy(
            observation=state.get("aif_observation", {}),
            belief=aif_belief,
        )
        hierarchical_fe = dual_fe.get("hierarchical_free_energy")
        meta_fe = dual_fe.get("meta_free_energy")

        # ---- 4. 写回 state ----
        state["aif_meta_diagnostics"] = meta_report
        state["aif_meta_triggered"] = meta_triggered
        state["aif_meta_temperature"] = meta_temperature
        state["aif_hierarchical_free_energy"] = hierarchical_fe
        state["aif_meta_free_energy"] = meta_fe
        state["aif_meta_cycle_count"] = step // meta_cycle_interval

        # 如果有元学习器，记录当前误差窗口统计
        if hasattr(generative_model, "meta_learner") and generative_model.meta_learner is not None:
            try:
                window_stats = generative_model.meta_learner.get_window_stats()
                state["aif_meta_window_stats"] = window_stats
            except Exception as e:
                logger.warning(f"AIF 集成子步骤失败: {e}", exc_info=True)

        logger.info(f"[AIF] ✅ 元循环完成: meta_triggered={meta_triggered}, degradation={degradation_detected}")

        return _sanitize_aif_return(
            {"hpc_state": hpc_state, "aif_state": aif_belief.to_dict()},
            source="aif_meta_cycle_node",
        )

    return aif_meta_cycle_node


# ====================================================================
# Fusion: AIF_SelectAction_Evaluate 节点
# 在 HPC 因果推理后重新评估 AIF 的行动选择
# ====================================================================


def create_aif_select_action_evaluate_node(
    active_inference: ActiveInference | None = None,
    n_samples: int = 200,
    temperature: float = 1.2,
) -> Callable:
    """
    创建 AIF 行动选择评估节点（融合架构专用）。

    在 HPC 完成因果推理后，此节点：
    1. 从 HPC 因果推理结果中提取关键信号（因果假设、置信度）
    2. 调用 AIF 的 EFE 评估重新评估行动选择
    3. 输出融合后的行动决策

    Args:
        active_inference: 可选 AIF ActiveInference 实例

    Returns:
        Callable: LangGraph 节点函数
    """

    def aif_select_action_evaluate_node(state: dict[str, Any]) -> dict[str, Any]:
        # ---- AIF 推理迭代计数器递增 ----
        current_iter = state.get("_aif_iteration_count", 0) + 1
        max_iter = state.get("_aif_max_iterations", 3)
        state["_aif_iteration_count"] = current_iter
        logger.info(f"[AIF Loop] 🔄 AIF_SelectAction_Evaluate: 迭代 {current_iter}/{max_iter} — 融合评估行动选择...")

        # ---- 1. 从 state 中提取 HPC 因果推理结果 ----
        hpc_state = _ensure_hpc_state(state)
        causal_hypotheses = getattr(hpc_state, "causal_counterfactuals", [])
        causal_confidence = getattr(hpc_state, "causal_confidence", 0.0)

        # ---- 2. 提取当前市场观测 ----
        market_info = _extract_market_info(state)

        # ---- 3. 提取 AIF 当前信念 ----
        aif_belief = state.get("aif_belief")
        if aif_belief is None:
            # 尝试从 aif_state 恢复
            aif_raw = state.get("aif_state", {})
            if isinstance(aif_raw, dict):
                aif_belief = aif_raw.get("belief", None)

        # ---- 4. 从 state 收集分析师报告用于上下文 ----
        analyst_reports = {
            "market": state.get("market_report", ""),
            "sentiment": state.get("sentiment_report", ""),
            "news": state.get("news_report", ""),
            "fundamentals": state.get("fundamentals_report", ""),
        }

        # ---- 5. 先计算 AIF EFE 分数（自由能公式需要 EFE 作为输入） ----
        efe_scores = None
        if active_inference is not None:
            try:
                efe_belief = aif_belief
                if efe_belief is None:
                    efe_belief = _hpc_to_aif_state(hpc_state)

                efe_scores = {}
                if _JAX_AVAILABLE:
                    import jax.numpy as jnp

                    for action in ACTION_NAMES:
                        try:
                            action_idx = ACTION_NAMES.index(action)
                            action_vec = jnp.eye(len(ACTION_NAMES))[action_idx]

                            result = active_inference.compute_efe(efe_belief, action_vec, n_samples=n_samples)
                            if isinstance(result, dict):
                                efe_scores[action] = _safe_get_field(result, "efe", 0.0, float)
                            else:
                                try:
                                    efe_scores[action] = float(result)
                                except (TypeError, ValueError):
                                    efe_scores[action] = 0.0
                        except Exception as e:
                            logger.debug(f"[Fusion] EFE compute for '{action}' failed: {e}")
                            efe_scores[action] = 0.0
                else:
                    # 降级：JAX 不可用，使用启发式 EFE
                    sentiment = market_info.get("sentiment", 0.5)
                    price_change = market_info.get("price_change_pct", 0.0)
                    efe_scores = {
                        "buy": 0.3 * sentiment + 0.2 * max(0, price_change),
                        "sell": 0.3 * (1 - sentiment) - 0.2 * min(0, price_change),
                        "hold": 0.1,
                    }

                logger.info(f"[Fusion] AIF EFE scores: {efe_scores}")
            except Exception as e:
                logger.warning(f"[Fusion] AIF EFE compute failed (non-fatal): {e}")

        # ---- 6. 自由能融合: F(a) = EFE(a) + β * KL(π_model || π_prior) ----
        fusion_decision = _fusion_evaluate_action(
            causal_hypotheses=causal_hypotheses,
            causal_confidence=causal_confidence,
            market_info=market_info,
            analyst_reports=analyst_reports,
            aif_belief=aif_belief,
            efe_scores=efe_scores,
        )

        # ---- 7. 写入融合决策到 state ----
        state["fusion_action"] = fusion_decision.get("action", "hold")
        state["fusion_confidence"] = fusion_decision.get("confidence", 0.5)
        state["fusion_reasoning"] = fusion_decision.get("reasoning", "")
        state["fusion_probabilities"] = fusion_decision.get("probabilities", [1/3, 1/3, 1/3])
        state["fusion_free_energies"] = fusion_decision.get("free_energies", {})
        state["fusion_free_energy_temperature"] = fusion_decision.get("free_energy_temperature", 0.5)
        if efe_scores is not None:
            state["fusion_efe_scores"] = efe_scores

        # ---- 8. 更新 hpc_state 因果推理结果标记 ----
        hpc_state.enabled_features["fusion_evaluated"] = True
        state["hpc_state"] = hpc_state

        logger.info(
            f"[Fusion] ✅ 融合评估完成: action={fusion_decision.get('action')}, "
            f"confidence={fusion_decision.get('confidence'):.3f}",
        )
        # 🐛 [P0 修复] 只返回 AIF 相关键，排除 market_report/bull_report/bear_report/news_report 等分析师管线键，
        # 防止同一 tick 内 AIF 节点写入 market_report 通道导致 LangGraph InvalidUpdateError:
        #   "At key 'market_report': Can receive only one value per step. Use an Annotated key to handle multiple values."
        # [方案B] 使用 _sanitize_aif_return 作为 defense-in-depth 最终安全网
        return _sanitize_aif_return(
            {
                "hpc_state": state.get("hpc_state"),
                "aif_state": state.get("aif_state"),
                "_aif_iteration_count": state.get("_aif_iteration_count", 0),
                "_aif_max_iterations": state.get("_aif_max_iterations", 3),
                "fusion_action": state.get("fusion_action", "hold"),
                "fusion_confidence": state.get("fusion_confidence", 0.5),
                "fusion_reasoning": state.get("fusion_reasoning", ""),
                "fusion_probabilities": state.get("fusion_probabilities", [1/3, 1/3, 1/3]),
                "fusion_free_energies": state.get("fusion_free_energies", {}),
                "fusion_free_energy_temperature": state.get("fusion_free_energy_temperature", 0.5),
                "fusion_efe_scores": state.get("fusion_efe_scores"),
                "aif_selection": state.get("aif_selection"),
                "aif_action_trace": state.get("aif_action_trace"),
                "aif_belief": state.get("aif_belief"),
                "aif_free_energy": state.get("aif_free_energy"),
                "aif_prior_injections": state.get("aif_prior_injections"),
                "aif_current_belief": state.get("aif_current_belief"),
                "aif_observation": state.get("aif_observation"),
                "aif_meta_diagnostics": state.get("aif_meta_diagnostics"),
                "aif_meta_triggered": state.get("aif_meta_triggered"),
                "aif_meta_temperature": state.get("aif_meta_temperature"),
                "aif_meta_cycle_count": state.get("aif_meta_cycle_count"),
                "aif_hierarchical_free_energy": state.get("aif_hierarchical_free_energy"),
                "aif_meta_free_energy": state.get("aif_meta_free_energy"),
                "aif_meta_window_stats": state.get("aif_meta_window_stats"),
                "aif_free_energy_history": (state.get("aif_free_energy_history") or []),
            },
            source="aif_select_action_evaluate_node",
        )

    return aif_select_action_evaluate_node


# ====================================================================
# [FIX 2026-06-26] 辅助函数：BMA 融合用
# ====================================================================

def _softmax(x: list[float]) -> list[float]:
    """安全的 softmax（数值稳定）"""
    a = np.array(x, dtype=np.float64)
    e_x = np.exp(a - np.max(a))
    return (e_x / (e_x.sum() + 1e-30)).tolist()


def _softmin(x: list[float]) -> list[float]:
    """EFE 越小越好 → softmin"""
    return _softmax([-v for v in x])


def _is_causal_bullish(h: Any) -> bool:
    """判断因果假设是否看涨（数值+文本双通道）"""
    if isinstance(h, dict):
        effect = h.get("effect", h.get("impact", 0.0))
        if isinstance(effect, (int, float)) and effect > 0:
            return True
    h_str = str(h).lower()
    return any(kw in h_str for kw in ("bull", "up", "positive", "涨", "利好", "看涨", "反弹", "走强"))


def _is_causal_bearish(h: Any) -> bool:
    """判断因果假设是否看跌"""
    if isinstance(h, dict):
        effect = h.get("effect", h.get("impact", 0.0))
        if isinstance(effect, (int, float)) and effect < 0:
            return True
    h_str = str(h).lower()
    return any(kw in h_str for kw in ("bear", "down", "negative", "跌", "利空", "看跌", "回落", "走弱"))


def _extract_numeric_bias(causal_hypotheses: list[Any]) -> float:
    """从因果假设中提取数值偏倚"""
    values = []
    for h in causal_hypotheses:
        if isinstance(h, dict):
            v = h.get("effect", h.get("impact", None))
        else:
            v = getattr(h, "effect", getattr(h, "impact", None))
        if isinstance(v, (int, float)):
            values.append(v)
    return float(np.mean(values)) if values else 0.0


# ====================================================================
# [FIX 2026-06-26] Phase 2.1: 统一自由能目标
# 参考: Friston 2010 FEP, Parr+ 2022 "Active Inference"
#
# 将 BMA 加权乘积升级为完整的自由能公式:
#   F(a) = EFE_prior(a) + β * KL(π_model(a) || π_prior(a))
#
# 其中:
#   - EFE_prior: 来自 AIF-EFE 计算的期望自由能（越小越好）
#   - KL: 模型建议分布与先验分布的 KL 散度（探索-利用平衡）
#   - β: 温度参数，控制 KL 项的权重
# ====================================================================


def _fusion_evaluate_action(
    causal_hypotheses: list[Any],
    causal_confidence: float,
    market_info: dict[str, Any],
    analyst_reports: dict[str, str],
    aif_belief: Any = None,
    efe_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    统一自由能融合

    每个候选动作的自由能:
      F(a) = EFE(a) + β * D_KL(π_model(a) || π_prior(a))

    选择使自由能最小的动作。
    自由能天然平衡了"偏好满足"(EFE)和"信息探索"(KL)。
    """
    eps = 1e-30
    action_labels = ["buy", "sell", "hold"]
    # 自由能温度参数: β 越大 → 越不偏离先验（越保守）
    beta = 0.5

    try:
        # ===== 1. EFE 项: 来自 AIF（越小越偏好） =====
        if efe_scores and isinstance(efe_scores, dict):
            efe_vals = np.array([efe_scores.get(a, 0.0) for a in action_labels], dtype=np.float64)
        else:
            efe_vals = np.zeros(3)

        # ===== 2. 模型建议分布 π_model =====
        # 从 HPC 因果推理提取
        if causal_hypotheses and causal_confidence > 0.0:
            total = len(causal_hypotheses)
            bullish_n = sum(1 for h in causal_hypotheses if _is_causal_bullish(h))
            bearish_n = sum(1 for h in causal_hypotheses if _is_causal_bearish(h))
            buy_p = (bullish_n + 1) / (total + 2)
            sell_p = (bearish_n + 1) / (total + 2)
            hold_p = max(0.0, 1.0 - buy_p - sell_p)
            hpc_probs = np.array([buy_p, sell_p, hold_p])
            w_hpc = min(causal_confidence * 0.6, 0.5)
        else:
            hpc_probs = np.ones(3) / 3
            w_hpc = 0.0

        # 从 AIF 信念提取
        if aif_belief is not None:
            if hasattr(aif_belief, "get_regime_probs_dict"):
                regime_probs = aif_belief.get_regime_probs_dict()
            elif isinstance(aif_belief, dict):
                regime_probs = aif_belief
            else:
                regime_probs = {}

            bull = regime_probs.get("bull", regime_probs.get(0, 0.25))
            bear = regime_probs.get("bear", regime_probs.get(1, 0.25))
            crisis = regime_probs.get("crisis", regime_probs.get(3, 0.25))

            if all(isinstance(v, (int, float)) for v in (bull, bear, crisis)):
                buy_p = max(0.0, bull * (1.0 - crisis))
                sell_p = max(0.0, crisis * (1.0 - bull) + bear * 0.3)
                hold_p = max(0.0, 1.0 - buy_p - sell_p)
                tot = buy_p + sell_p + hold_p + eps
                aif_probs = np.array([buy_p, sell_p, hold_p]) / tot
            else:
                aif_probs = np.ones(3) / 3
            w_aif = 0.3
        else:
            aif_probs = np.ones(3) / 3
            w_aif = 0.0

        # 从数值信号提取
        price_change = market_info.get("price_change", 0.0)
        sentiment_val = market_info.get("sentiment", 0.5)
        numeric_bias = _extract_numeric_bias(causal_hypotheses)
        buy_raw = max(0.0, price_change * 0.4 + (sentiment_val - 0.5) * 0.3 + numeric_bias * 0.3)
        sell_raw = max(0.0, -price_change * 0.4 + (0.5 - sentiment_val) * 0.3 - numeric_bias * 0.3)
        hold_raw = max(0.0, 1.0 - buy_raw - sell_raw)
        tot_n = buy_raw + sell_raw + hold_raw + eps
        numeric_probs = np.array([buy_raw, sell_raw, hold_raw]) / tot_n

        # 融合模型 = 加权平均
        model_probs = (w_hpc * hpc_probs + w_aif * aif_probs + 0.2 * numeric_probs)
        model_probs = model_probs / (model_probs.sum() + eps)

        # ===== 3. 先验分布 π_prior =====
        # 均匀先验: 没有先验知识时对所有动作同等偏好
        prior_probs = np.ones(3) / 3

        # ===== 4. 自由能 =====
        free_energies = {}
        for i, action in enumerate(action_labels):
            # EFE 项（来自 AIF）
            efe_term = efe_vals[i]

            # KL 项
            p = model_probs[i]
            q = prior_probs[i]
            kl_term = p * np.log(p / (q + eps) + eps) if p > 0 else 0.0

            # 总自由能: F(a) = EFE(a) + β * KL(π_model || π_prior)
            F = efe_term + beta * kl_term
            free_energies[action] = float(F)

        # 选择自由能最小的动作
        best_action = min(free_energies, key=free_energies.get)
        # 置信度 = 自由能差距的 softmin
        fe_vals = np.array(list(free_energies.values()), dtype=np.float64)
        confidence = float(_softmin(fe_vals.tolist())[list(free_energies.keys()).index(best_action)])

        logger.info(
            "[Fusion-FEP] ✅ 自由能融合: action=%s, confidence=%.4f, β=%.2f, "
            "F(buy)=%.3f, F(sell)=%.3f, F(hold)=%.3f",
            best_action, confidence, beta,
            free_energies.get("buy", 0), free_energies.get("sell", 0), free_energies.get("hold", 0),
        )

        return {
            "action": best_action,
            "confidence": float(confidence),
            "probabilities": [float(model_probs[i]) for i in range(3)],
            "free_energies": free_energies,
            "free_energy_temperature": beta,
            "efe_values": {a: float(efe_vals[i]) for i, a in enumerate(action_labels)},
            "reasoning": (
                f"自由能融合: F(buy)={free_energies['buy']:.3f}, "
                f"F(sell)={free_energies['sell']:.3f}, "
                f"F(hold)={free_energies['hold']:.3f}, "
                f"β={beta}"
            ),
        }

    except Exception as e:
        logger.warning(f"[Fusion-FEP] ⚠️ 融合异常，回退到均匀决策: {e}", exc_info=True)
        return {
            "action": "hold",
            "confidence": 0.5,
            "probabilities": [1 / 3, 1 / 3, 1 / 3],
            "free_energies": {"buy": 0.0, "sell": 0.0, "hold": 0.0},
            "free_energy_temperature": beta,
            "efe_values": {},
            "reasoning": f"自由能回退 (异常: {e})",
        }


# ====================================================================
# AIF 引擎管理器
# ====================================================================


class AIFEngineManager:
    """
    AIF 引擎管理器

    集中管理所有 AIF 组件和它们在 LangGraph 中的集成。
    与 HPCLoopManager 并行存在，通过 use_aif_engine 配置切换。

    用法:
        config = HPCLoopConfig()
        aif_manager = AIFEngineManager(config)
        nodes = aif_manager.get_aif_nodes()
        edges = aif_manager.get_aif_edges(selected_analysts)
    """

    def __init__(
        self,
        config: dict[str, Any] | HPCLoopConfig | None = None,
    ):
        # 兼容两种传入方式: HPCLoopConfig 实例 或 主配置 dict
        if isinstance(config, HPCLoopConfig):
            self.config = config
        elif config:
            # dict 模式：从环境变量加载基础 HPCLoopConfig，再用 dict 覆盖
            hpc_config = HPCLoopConfig.from_env()
            if "use_aif_engine" in config:
                hpc_config.use_aif_engine = config["use_aif_engine"]
            if "aif_latent_dim" in config:
                hpc_config.aif_latent_dim = config["aif_latent_dim"]
            if "aif_n_samples" in config:
                hpc_config.aif_n_samples = config["aif_n_samples"]
            if "aif_learning_rate" in config:
                hpc_config.aif_learning_rate = config["aif_learning_rate"]
            if "aif_efe_temperature" in config:
                hpc_config.aif_efe_temperature = config["aif_efe_temperature"]
            # CRITICAL-4/5: 补充 meta_learning_rate 和 meta_cycle_interval 映射
            if "meta_learning_rate" in config:
                hpc_config.meta_learning_rate = config["meta_learning_rate"]
            if "meta_cycle_interval" in config:
                hpc_config.meta_cycle_interval = config["meta_cycle_interval"]
            self.config = hpc_config
        else:
            self.config = HPCLoopConfig.from_env()
        self.enabled = self.config.enabled

        # 提取常用配置参数为实例属性，供节点工厂函数使用
        self.aif_n_samples = self.config.aif_n_samples
        self.aif_efe_temperature = self.config.aif_efe_temperature

        # AIF 核心组件
        self.generative_model: GenerativeModel | None = None
        self.active_inference: ActiveInference | None = None
        self.llm_prior_injector: LLMPriorInjector | None = None
        self.belief_updater: BeliefUpdater | None = None

        if self.enabled:
            self._init_components()

    def _init_components(self) -> None:
        """初始化所有 AIF 组件（含分层模型和元学习器）"""
        logger.info("[AIF] 🚀 初始化 AIF 引擎组件...")

        # ---- 检查配置是否启用分层模式 ----
        use_hierarchical = getattr(self.config, "use_hierarchical_model", True)

        # ---- 准备分层模型和元学习器配置 ----
        meta_learner_config = None

        if use_hierarchical and _HIERARCHICAL_AVAILABLE and _JAX_AVAILABLE:
            try:
                meta_learner_config = (
                    MetaLearnerConfig(
                        meta_window_size=getattr(self.config, "meta_window_size", 50),
                        meta_learning_rate=getattr(self.config, "meta_learning_rate", 0.001),
                        cusum_threshold=getattr(self.config, "meta_cusum_threshold", 4.0),
                    )
                    if _META_AVAILABLE
                    else None
                )
                logger.info("[AIF]   分层模式: 启用 (4 层 GENESIS 架构)")
            except Exception as e:
                logger.warning(f"[AIF]   分层配置初始化失败，回退到扁平模式: {e}")
                use_hierarchical = False
        elif use_hierarchical and not _JAX_AVAILABLE:
            logger.warning("[AIF]   JAX 不可用，分层模型需要 JAX，回退到扁平模式")
            use_hierarchical = False
        else:
            logger.info("[AIF]   分层模式: 禁用 (扁平模式)")

        # 生成模型（含分层支持）— 关键组件，失败应快速上报
        try:
            self.generative_model = GenerativeModel(
                latent_dim=self.config.aif_latent_dim,
                obs_dim=DEFAULT_OBS_DIM,
                use_hierarchical=use_hierarchical,
                layer_configs=None,
                meta_learner_config=meta_learner_config,
            )
            logger.info(f"[AIF] ✅ GenerativeModel 已初始化 (hierarchical={use_hierarchical})")
        except Exception as e:
            logger.error(f"[AIF] ❌ GenerativeModel 初始化失败: {e} — AIF 引擎降级到退化模式")
            self.generative_model = None
            self.active_inference = None
            self.llm_prior_injector = None
            self.belief_updater = None
            # 不再 return，让 get_aif_nodes() 自行跳过不可用节点
            # 这样 AIF_Observe 和 AIF_SelectAction_Evaluate（无条件创建）仍然可用
            logger.warning("[AIF] ⚠️ GenerativeModel 不可用，AIF 将跳过: Predict/LLMPrior/UpdateBelief/SelectAction/Learn")
            # 继续执行，允许 LLMPriorInjector 和剩余流程正常初始化

        # 主动推理
        try:
            self.active_inference = ActiveInference(
                generative_model=self.generative_model,
                n_actions=3,
            )
            logger.info("[AIF] ✅ ActiveInference 已初始化")
        except Exception as e:
            logger.error(f"[AIF] ❌ ActiveInference 初始化失败: {e}")
            self.active_inference = None

        # LLM 先验注入器
        self.llm_prior_injector = LLMPriorInjector(
            llm_client=None,  # 运行时设置
            analyst_type="market",
        )
        logger.info("[AIF] ✅ LLMPriorInjector 已初始化")

        # 信念更新器
        try:
            self.belief_updater = BeliefUpdater(
                generative_model=self.generative_model,
                learning_rate=self.config.aif_learning_rate,
                use_svi=False,  # 默认不使用 SVI (需要 numpyro)
            )
            logger.info("[AIF] ✅ BeliefUpdater 已初始化")
        except Exception as e:
            logger.error(f"[AIF] ❌ BeliefUpdater 初始化失败: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            self.belief_updater = None

        logger.info("[AIF] 🚀 AIF 引擎初始化完成")

    def get_aif_nodes(self) -> dict[str, Callable]:
        """
        获取所有 AIF LangGraph 节点函数（含元循环节点）

        双循环拓扑:
        - 外环: Predict → LLMPrior → Observe → UpdateBelief → SelectAction → ... → Learn
        - 内环: MetaCycle → Learn → Predict (元学习自指循环)

        Returns:
            Dict[str, Callable]: {节点名称: 节点函数}
        """
        nodes = {}

        # 1. 预测节点
        if self.generative_model:
            nodes["AIF_Predict"] = create_aif_predict_node(
                self.generative_model,
                n_samples=self.aif_n_samples,
            )

        # 2. LLM 先验注入节点
        if self.llm_prior_injector:
            nodes["AIF_LLMPrior"] = create_aif_llm_prior_node(self.llm_prior_injector)

        # 3. 观测节点
        nodes["AIF_Observe"] = create_aif_observe_node()

        # 4. 信念更新节点（始终注册，belief_updater 为 None 时使用退化模式）
        nodes["AIF_UpdateBelief"] = create_aif_update_belief_node(
            self.belief_updater,
            self.generative_model,
        )

        # 5. 行动选择节点
        if self.active_inference:
            nodes["AIF_SelectAction"] = create_aif_select_action_node(
                self.active_inference,
                n_samples=self.aif_n_samples,
                temperature=self.aif_efe_temperature,
            )

        # 6. 学习节点
        if self.generative_model:
            nodes["AIF_Learn"] = create_aif_learn_node(
                self.generative_model,
                self.belief_updater,
            )

        # 7. Fusion: AIF_SelectAction_Evaluate 节点 (融合架构专用)
        # 在 HPC 因果推理后重新评估 AIF 行动选择
        nodes["AIF_SelectAction_Evaluate"] = create_aif_select_action_evaluate_node(
            active_inference=self.active_inference,
            n_samples=self.aif_n_samples,
            temperature=self.aif_efe_temperature,
        )

        # 8. 元循环节点 (双循环内环 — 仅当分层模式启用时)
        if self.generative_model is not None:
            meta_cycle_interval = getattr(self.config, "meta_cycle_interval", 50)
            nodes["AIF_MetaCycle"] = create_meta_cycle_node(
                generative_model=self.generative_model,
                meta_cycle_interval=meta_cycle_interval,
            )

        logger.info(f"[AIF] 节点已加载: {list(nodes.keys())}")

        return nodes

    def get_aif_edges(
        self,
        selected_analysts: list[str],
    ) -> list[dict[str, Any]]:
        """
        获取 AIF 引擎的边定义

        拓扑结构:
            START → AIF_Predict
            AIF_Predict → 分析师链 (...)
            ... → AIF_LLMPrior (替代原分析师输出处理)
            AIF_LLMPrior → AIF_Observe
            AIF_Observe → AIF_UpdateBelief
            AIF_UpdateBelief → AIF_SelectAction
            AIF_SelectAction → ... (后续交易决策)
            ... → AIF_Learn
            AIF_Learn → END

        Args:
            selected_analysts: 选中的分析师列表

        Returns:
            List[Dict]: 边定义列表
        """
        edges = []

        if not self.enabled:
            return edges

        # ================================================================
        # 外环（Outer Loop）— 标准 AIF 推理流程
        # ================================================================

        # ===== 以下边定义使用节点集守卫（防止条件性节点未注册时编译崩溃）=====
        _aif_nodes = self.get_aif_nodes() if hasattr(self, 'get_aif_nodes') else {}

        # 1. START → AIF_Predict (仅在节点注册时加边)
        if "AIF_Predict" in _aif_nodes:
            edges.append({"source": "START", "target": "AIF_Predict"})

        # 2. AIF_Predict → 第一个分析师
        if "AIF_Predict" in _aif_nodes and selected_analysts:
            first = selected_analysts[0].capitalize()
            edges.append({"source": "AIF_Predict", "target": f"{first} Analyst"})

        # 3. 最后一个分析师 → AIF_LLMPrior
        if "AIF_LLMPrior" in _aif_nodes and selected_analysts:
            last = selected_analysts[-1].capitalize()
            edges.append({"source": f"Msg Clear {last}", "target": "AIF_LLMPrior"})

        # 4. AIF_LLMPrior → AIF_Observe
        if "AIF_LLMPrior" in _aif_nodes and "AIF_Observe" in _aif_nodes:
            edges.append({"source": "AIF_LLMPrior", "target": "AIF_Observe"})

        # 5. AIF_Observe → AIF_UpdateBelief
        if "AIF_Observe" in _aif_nodes and "AIF_UpdateBelief" in _aif_nodes:
            edges.append({"source": "AIF_Observe", "target": "AIF_UpdateBelief"})

        # 6. AIF_UpdateBelief → AIF_SelectAction
        if "AIF_UpdateBelief" in _aif_nodes and "AIF_SelectAction" in _aif_nodes:
            edges.append({"source": "AIF_UpdateBelief", "target": "AIF_SelectAction"})

        # 7. AIF_SelectAction → Risk Judge
        if "AIF_SelectAction" in _aif_nodes:
            edges.append({"source": "AIF_SelectAction", "target": "Risk Judge"})

        # 8. AIF_SelectAction → AIF_MetaCycle
        if "AIF_SelectAction" in _aif_nodes and "AIF_MetaCycle" in _aif_nodes:
            edges.append({"source": "AIF_SelectAction", "target": "AIF_MetaCycle"})

        # 9. AIF_MetaCycle → AIF_Learn
        if "AIF_MetaCycle" in _aif_nodes and "AIF_Learn" in _aif_nodes:
            edges.append({"source": "AIF_MetaCycle", "target": "AIF_Learn"})

        # 10. AIF_Learn → END
        if "AIF_Learn" in _aif_nodes:
            edges.append({"source": "AIF_Learn", "target": "END"})

        # ================================================================
        # 内环（Inner Loop）— 元学习自指循环
        #   AIF_MetaCycle → AIF_Learn → AIF_Predict
        #   当 meta_triggered 时，内环提供自我修正信号
        # ================================================================

        # 使用条件边：如果元循环触发，从 Learn 回到 Predict
        edges.append(
            {
                "source": "AIF_Learn",
                "target": "AIF_Predict",
                "condition": "meta_triggered",
            },
        )

        return edges

    def get_initial_aif_state(self) -> HPCState:
        """
        获取初始 HPCState (包含 AIF 隐状态 + 双循环元状态)

        Returns:
            HPCState: 包含元循环字段的初始状态
        """
        state = HPCState()

        # 初始化 AIF 隐状态
        aif_belief = AIFMarketLatentState()
        state.latent_state = HpcMarketLatentState.from_dict(_aif_to_hpc_state(aif_belief))

        # 启用 AIF 特征（含分层/元学习器标志）
        use_hierarchical = getattr(self.config, "use_hierarchical_model", True)
        state.enabled_features = {
            "aif_engine": self.enabled,
            "aif_generative_model": self.generative_model is not None,
            "aif_active_inference": self.active_inference is not None,
            "aif_belief_updater": self.belief_updater is not None,
            "aif_llm_prior": self.llm_prior_injector is not None,
            "aif_hierarchical": use_hierarchical and _HIERARCHICAL_AVAILABLE,
            "aif_meta_learner": (
                self.generative_model is not None
                and hasattr(self.generative_model, "meta_learner")
                and self.generative_model.meta_learner is not None
            ),
        }

        # 初始化双循环状态字段（供 LangGraph 使用）
        if not hasattr(state, "meta_data"):
            state.meta_data = {}
        # 元循环诊断报告
        state.meta_data["aif_meta_diagnostics"] = {}
        state.meta_data["aif_meta_triggered"] = False
        state.meta_data["aif_meta_temperature"] = None
        state.meta_data["aif_meta_cycle_count"] = 0
        # 双自由能分解
        state.meta_data["aif_hierarchical_free_energy"] = None
        state.meta_data["aif_meta_free_energy"] = None
        # 元学习器窗口统计
        state.meta_data["aif_meta_window_stats"] = {}

        return state

    def set_llm_client(self, llm_client: Any) -> None:
        """设置 LLM 客户端到先验注入器"""
        if self.llm_prior_injector:
            self.llm_prior_injector.llm_client = llm_client

    def reset(self) -> None:
        """重置所有 AIF 组件"""
        if self.generative_model:
            self.generative_model.reset()
        if self.active_inference:
            self.active_inference.reset()
        if self.llm_prior_injector:
            self.llm_prior_injector.reset()
        if self.belief_updater:
            self.belief_updater.reset()
        logger.info("[AIF] 🔄 AIF 引擎已重置")
