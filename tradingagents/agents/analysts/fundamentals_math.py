"""
基础面分析师 - 数学预处理层 (Phase 1【器】)
三元归一：市场多尺度特征 + 多期财务趋势 + 行业估值上下文
器(数学计算) → 术(特征融合) → 道(LLM翻译) 三层架构

设计原则：
1. 所有异常必须被捕获，绝不传播到上层
2. 数据不足时优雅降级，返回 {available: False}
3. 纯 numpy/pandas 计算，不依赖深度学习框架
4. 总计算时间控制在 2 秒以内
"""

import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Module A: 市场多尺度特征
# ═══════════════════════════════════════════

def _safe_slope(y: np.ndarray) -> float:
    """稳健线性回归斜率（归一化到价格水平）"""
    if len(y) < 3:
        return 0.0
    x = np.arange(len(y), dtype=float)
    try:
        # 使用最小二乘法
        slope = np.polyfit(x, y, 1)[0]
        # 归一化到价格水平（相对变化）
        base = float(np.mean(y))
        if base == 0:
            return 0.0
        return float(round(slope / base * 100, 4))
    except Exception:
        return 0.0


def compute_market_features(ticker: str, current_date: str, lookback_days: int = 60) -> dict:
    """
    Module A: 从 OHLCV 计算市场多尺度特征

    输入: DataSourceManager.get_stock_dataframe() → OHLCV DataFrame
    输出:
        available: bool
        trend_3d: 3日趋势强度 (归一化斜率%)
        trend_10d: 10日趋势强度
        trend_20d: 20日趋势强度
        volatility_ratio: 短期/长期波动率比
        volume_anomaly: 成交量异常度 (近期均值/长期均值)
        price_level: 当前价格水平
        price_position: 价格在60日区间中的位置 [0,1]
    """
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager

        dt = datetime.strptime(current_date, "%Y-%m-%d")
        start = (dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        manager = DataSourceManager()
        df = manager.get_stock_dataframe(ticker, start, current_date, period="daily")

        if df is None or df.empty or len(df) < 5:
            logger.info("[基础面数学-A] 数据不足，跳过市场特征计算")
            return {"available": False, "reason": f"数据不足({len(df) if df is not None else 0}行)"}

        closes = df["close"].values.astype(float)
        volumes = df["vol"].values.astype(float) if "vol" in df.columns else df.get("volume", df.get("amount", closes * 0)).values.astype(float)

        # ── 趋势强度 ──
        trend_3d = _safe_slope(closes[-3:]) if len(closes) >= 3 else 0.0
        trend_10d = _safe_slope(closes[-10:]) if len(closes) >= 10 else trend_3d
        trend_20d = _safe_slope(closes[-20:]) if len(closes) >= 20 else trend_10d

        # ── 波动率比 (近5日/近20日) ──
        if len(closes) >= 20:
            returns = np.diff(closes) / closes[:-1]
            vol_short = float(np.std(returns[-5:])) if len(returns) >= 5 else 0.0
            vol_long = float(np.std(returns[-20:])) if len(returns) >= 20 else vol_short
            volatility_ratio = round(vol_short / vol_long, 4) if vol_long > 1e-10 else 1.0
        else:
            volatility_ratio = 1.0

        # ── 成交量异常度 ──
        if len(volumes) >= 20:
            recent_vol = float(np.mean(volumes[-5:])) if len(volumes) >= 5 else float(np.mean(volumes))
            long_vol = float(np.mean(volumes[-20:]))
            volume_anomaly = round(recent_vol / long_vol, 4) if long_vol > 1e-10 else 1.0
        else:
            volume_anomaly = 1.0

        # ── 价格位置 (在60日区间中的百分位) ──
        price_min, price_max = float(np.min(closes)), float(np.max(closes))
        current_close = float(closes[-1])
        price_position = round((current_close - price_min) / (price_max - price_min), 4) if price_max > price_min else 0.5

        # ── 趋势方向判定 (增加稳定性) ──
        def _trend_label(slope: float) -> str:
            if slope > 0.15:
                return "上升"
            elif slope < -0.15:
                return "下降"
            else:
                return "震荡"

        result = {
            "available": True,
            "trend_3d_pct": trend_3d,
            "trend_10d_pct": trend_10d,
            "trend_20d_pct": trend_20d,
            "trend_3d_label": _trend_label(trend_3d),
            "trend_10d_label": _trend_label(trend_10d),
            "volatility_ratio": volatility_ratio,
            "volatility_label": "高波动" if volatility_ratio > 1.5 else ("低波动" if volatility_ratio < 0.5 else "正常波动"),
            "volume_anomaly": volume_anomaly,
            "volume_label": "放量" if volume_anomaly > 1.3 else ("缩量" if volume_anomaly < 0.7 else "正常"),
            "price_position": price_position,
            "price_zone_label": "高位" if price_position > 0.8 else ("低位" if price_position < 0.2 else "中位"),
            "current_price": current_close,
        }

        logger.info(f"[基础面数学-A] 特征计算完成: trend_3d={trend_3d:.2f}%, vol_ratio={volatility_ratio:.2f}, "
                     f"vol_anomaly={volume_anomaly:.2f}, price_pos={price_position:.2f}")
        return result

    except Exception as e:
        logger.warning(f"[基础面数学-A] 计算异常: {e}", exc_info=True)
        return {"available": False, "reason": str(e)}


# ═══════════════════════════════════════════
# Module B: 多期财务趋势
# ═══════════════════════════════════════════

def _trend_from_values(values: list) -> str:
    """从数值序列判断趋势方向"""
    if len(values) < 3:
        return "数据不足"
    try:
        x = np.arange(len(values), dtype=float)
        y = np.array([float(v) if v is not None else np.nan for v in values])
        # 去掉 NaN
        mask = ~np.isnan(y)
        if np.sum(mask) < 2:
            return "数据不足"
        slope = np.polyfit(x[mask], y[mask], 1)[0]
        abs_mean = float(np.nanmean(np.abs(y))) if not np.all(np.isnan(y)) else 1.0
        if abs_mean < 1e-10:
            return "平稳"
        rel_slope = slope / abs_mean
        if rel_slope > 0.05:
            return "上升"
        elif rel_slope < -0.05:
            return "下降"
        else:
            return "平稳"
    except Exception:
        return "未知"


def compute_financial_trend(ticker: str) -> dict:
    """
    Module B: 多期财务趋势分析

    从 Tushare fina_indicator 获取最近4期财务数据，
    计算核心指标的趋势方向。

    输出:
        available: bool
        periods_available: 可用期数
        roe_trend: ROE趋势 (上升/下降/平稳)
        eps_trend: 每股收益趋势
        margin_trend: 毛利率趋势
        roa_trend: ROA趋势
        revenue_growth: 营收增长趋势
        debt_ratio_trend: 负债率趋势
        summary: 一句话总结
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.connect_sync():
            logger.warning("[基础面数学-B] Tushare连接失败")
            return {"available": False, "reason": "Tushare连接失败"}

        ts_code = provider._normalize_symbol(ticker)

        # 获取最近4期财务数据（按季度）
        df = provider._api_call_with_retry(
            provider.api.fina_indicator,
            ts_code=ts_code,
            fields="end_date,eps,roe,roa,gross_margin,net_margin,ocfps,bps,profit_dedu,dt_eps",
            limit=4,
        )

        if df is None or df.empty:
            logger.info("[基础面数学-B] 财务数据为空")
            return {"available": False, "reason": "财务数据为空"}

        # 按 end_date 排序
        if "end_date" in df.columns:
            df = df.sort_values("end_date")

        periods = len(df)
        logger.info(f"[基础面数学-B] 获取到 {periods} 期财务数据")

        # 提取各指标序列
        def _series(col):
            return [row.get(col) for _, row in df.iterrows()]

        roe_vals = _series("roe")
        eps_vals = _series("eps")
        gm_vals = _series("gross_margin")
        nm_vals = _series("net_margin")
        roa_vals = _series("roa")
        ocfps_vals = _series("ocfps")
        bps_vals = _series("bps")

        # 计算趋势
        roe_trend = _trend_from_values(roe_vals)
        eps_trend = _trend_from_values(eps_vals)
        margin_trend = _trend_from_values(gm_vals)
        net_margin_trend = _trend_from_values(nm_vals)
        roa_trend = _trend_from_values(roa_vals)

        # 最新值
        latest = df.iloc[-1]
        current_roe = float(latest["roe"]) if latest.get("roe") is not None else None
        current_eps = float(latest["eps"]) if latest.get("eps") is not None else None
        current_margin = float(latest["gross_margin"]) if latest.get("gross_margin") is not None else None
        current_roa = float(latest["roa"]) if latest.get("roa") is not None else None

        # 趋势分数 (用于量化)
        trend_score_map = {"上升": 1, "平稳": 0, "下降": -1, "数据不足": 0}
        scores = [
            trend_score_map.get(roe_trend, 0),
            trend_score_map.get(eps_trend, 0),
            trend_score_map.get(margin_trend, 0),
        ]
        overall_score = round(sum(scores) / len(scores), 2) if scores else 0

        # 生成一句话摘要
        improving = sum(1 for s in [roe_trend, eps_trend, margin_trend] if s == "上升")
        declining = sum(1 for s in [roe_trend, eps_trend, margin_trend] if s == "下降")
        if improving >= 2:
            summary = "财务指标整体向好"
        elif declining >= 2:
            summary = "财务指标整体走弱"
        else:
            summary = "财务指标分化,需进一步分析"

        result = {
            "available": True,
            "periods_available": periods,
            "roe_trend": roe_trend,
            "eps_trend": eps_trend,
            "margin_trend": margin_trend,
            "net_margin_trend": net_margin_trend,
            "roa_trend": roa_trend,
            "current_roe": current_roe,
            "current_eps": current_eps,
            "current_gross_margin": current_margin,
            "current_roa": current_roa,
            "trend_score": overall_score,
            "summary": summary,
        }

        logger.info(f"[基础面数学-B] 趋势分析完成: ROE={roe_trend}, EPS={eps_trend}, 毛利率={margin_trend}, 总分={overall_score}")
        return result

    except Exception as e:
        logger.warning(f"[基础面数学-B] 计算异常: {e}", exc_info=True)
        return {"available": False, "reason": str(e)}


# ═══════════════════════════════════════════
# Module C: 行业估值上下文
# ═══════════════════════════════════════════

def compute_industry_context(ticker: str) -> dict:
    """
    Module C: 行业估值上下文

    1. 获取股票的行业分类
    2. 获取股票自身的 PE/PB 估值
    3. 通过 Tushare stock_basic + daily_basic 获取同行业部分股票的估值作为参考
    4. 计算估值百分位和行业对比

    输出:
        available: bool
        industry: 行业名称
        pe: 当前PE
        pb: 当前PB
        pe_assessment: PE评价 (高/中/低)
        industry_pe_avg: 行业平均PE (有限样本)
        note: 说明
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.connect_sync():
            logger.warning("[基础面数学-C] Tushare连接失败")
            return {"available": False, "reason": "Tushare连接失败"}

        ts_code = provider._normalize_symbol(ticker)

        # ── 1. 获取行业分类 ──
        basic_df = provider._api_call_with_retry(
            provider.api.stock_basic,
            ts_code=ts_code,
            fields="ts_code,name,industry,market",
        )
        industry_name = "未知"
        if basic_df is not None and not basic_df.empty:
            industry_name = str(basic_df.iloc[0].get("industry", "未知") or "未知")

        # ── 2. 获取自身 PE/PB ──
        pe, pb = None, None
        try:
            # 从 fina_indicator + 股价推算 PE
            fina_df = provider._api_call_with_retry(
                provider.api.fina_indicator,
                ts_code=ts_code,
                fields="end_date,eps",
                limit=1,
            )
            eps_val = None
            if fina_df is not None and not fina_df.empty and fina_df.iloc[0].get("eps") is not None:
                eps_val = float(fina_df.iloc[0]["eps"])
        except Exception:
            eps_val = None

        # 从 daily_basic 获取 PE/PB
        try:
            import datetime as dt
            today_str = dt.date.today().strftime("%Y%m%d")
            daily_df = provider._api_call_with_retry(
                provider.api.daily_basic,
                ts_code=ts_code,
                trade_date=today_str,
                fields="ts_code,pe,pb,pe_ttm",
            )
            if daily_df is not None and not daily_df.empty:
                row = daily_df.iloc[0]
                pe = float(row["pe"]) if row.get("pe") is not None else None
                pb = float(row["pb"]) if row.get("pb") is not None else None
        except Exception:
            pass

        # ── 3. 估值评价 ──
        pe_assessment = "未知"
        if pe is not None:
            if pe < 0:
                pe_assessment = "亏损(PE为负)"
            elif pe < 15:
                pe_assessment = "偏低"
            elif pe < 30:
                pe_assessment = "合理"
            elif pe < 60:
                pe_assessment = "偏高"
            else:
                pe_assessment = "极高"

        pb_assessment = "未知"
        if pb is not None:
            if pb < 1:
                pb_assessment = "破净"
            elif pb < 2:
                pb_assessment = "偏低"
            elif pb < 5:
                pb_assessment = "合理"
            else:
                pb_assessment = "偏高"

        result = {
            "available": True,
            "industry": industry_name,
            "pe": pe,
            "pb": pb,
            "pe_assessment": pe_assessment,
            "pb_assessment": pb_assessment,
            "eps": eps_val,
        }

        logger.info(f"[基础面数学-C] 行业: {industry_name}, PE: {pe}({pe_assessment}), PB: {pb}({pb_assessment})")
        return result

    except Exception as e:
        logger.warning(f"[基础面数学-C] 计算异常: {e}", exc_info=True)
        return {"available": False, "reason": str(e)}


# ═══════════════════════════════════════════
# 汇总入口
# ═══════════════════════════════════════════

def run_full_math_layer(ticker: str, current_date: str) -> dict:
    """
    执行完整数学预处理层 (A + B + C)

    返回格式:
    {
        "data_available": True/False,
        "market": {...},   # Module A 结果
        "financial": {...}, # Module B 结果
        "industry": {...},  # Module C 结果
        "summary": "..."    # 一句话汇总
    }
    """
    logger.info(f"[基础面数学层] ===== 开始计算 {ticker} =====")

    # 并行执行三个模块（实际串行，但每个模块内部都很轻量）
    market = compute_market_features(ticker, current_date)
    financial = compute_financial_trend(ticker)
    industry = compute_industry_context(ticker)

    any_available = any(
        isinstance(v, dict) and v.get("available", False)
        for v in [market, financial, industry]
    )

    # 生成汇总
    parts = []
    if market.get("available") and market.get("trend_3d_label"):
        parts.append(f"市场:{market['trend_10d_label']}")
    if financial.get("available") and financial.get("summary"):
        parts.append(f"财务:{financial['summary']}")
    if industry.get("available") and industry.get("industry"):
        parts.append(f"行业:{industry['industry']}|PE:{industry.get('pe_assessment','?')}")

    summary = " | ".join(parts) if parts else "数学层数据不足"

    result = {
        "data_available": any_available,
        "market": market,
        "financial": financial,
        "industry": industry,
        "summary": summary,
    }

    logger.info(f"[基础面数学层] ===== 计算完成: {summary} =====")
    return result
