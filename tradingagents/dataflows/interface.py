import os
import time
from datetime import datetime
from typing import Annotated

import logging

logger = logging.getLogger(__name__)


# === Phase 3: CSDI 扩散插补 (条件 Score-based Diffusion 时序补全) ===
try:
    from tradingagents.diffusion import CSDIImputer

    _CSDI_AVAILABLE = True
except ImportError:
    CSDIImputer = None  # type: ignore
    _CSDI_AVAILABLE = False

try:
    from .technical.stockstats import StockstatsUtils

    STOCKSTATS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ stockstats工具不可用: {e}")
    STOCKSTATS_AVAILABLE = False

import pandas as pd
from dateutil.relativedelta import relativedelta

from tradingagents.config.config_manager import config_manager

# 获取数据目录
DATA_DIR = config_manager.get_data_dir()


def get_config():
    """获取配置（兼容性包装）"""
    return config_manager.load_settings()


def set_config(config):
    """设置配置（兼容性包装）"""
    config_manager.save_settings(config)





def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
    online: Annotated[bool, "to fetch data online or offline"],
) -> str:

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}")

    end_date = curr_date
    curr_date = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date - relativedelta(days=look_back_days)

    if not online:
        # read from YFin data
        data = pd.read_csv(
            os.path.join(
                DATA_DIR,
                f"market_data/price_data/{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
            ),
        )
        data["Date"] = pd.to_datetime(data["Date"], utc=True)
        dates_in_df = data["Date"].astype(str).str[:10]

        ind_string = ""
        while curr_date >= before:
            # only do the trading dates
            if curr_date.strftime("%Y-%m-%d") in dates_in_df.values:
                indicator_value = get_stockstats_indicator(symbol, indicator, curr_date.strftime("%Y-%m-%d"), online)

                ind_string += f"{curr_date.strftime('%Y-%m-%d')}: {indicator_value}\n"

            curr_date = curr_date - relativedelta(days=1)
    else:
        # online gathering
        ind_string = ""
        while curr_date >= before:
            indicator_value = get_stockstats_indicator(symbol, indicator, curr_date.strftime("%Y-%m-%d"), online)

            ind_string += f"{curr_date.strftime('%Y-%m-%d')}: {indicator_value}\n"

            curr_date = curr_date - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    online: Annotated[bool, "to fetch data online or offline"],
) -> str:

    curr_date = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
            os.path.join(DATA_DIR, "market_data", "price_data"),
            online=online,
        )
    except Exception as e:
        print(f"Error getting stockstats indicator data for indicator {indicator} on {curr_date}: {e}")
        return ""

    return str(indicator_value)





# ==================== 统一数据源接口 ====================


def get_china_stock_data_unified(
    ticker: Annotated[str, "中国股票代码，如：000001、600036等"],
    start_date: Annotated[str, "开始日期，格式：YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期，格式：YYYY-MM-DD"],
) -> str:
    """
    统一的中国A股数据获取接口
    自动使用配置的数据源，支持备用数据源

    Args:
        ticker: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的股票数据报告
    """
    # 🔧 智能日期范围处理：自动扩展到配置的回溯天数，处理周末/节假日
    from app.core.config import get_settings
    from tradingagents.utils.dataflow_utils import get_trading_date_range

    original_start_date = start_date
    original_end_date = end_date

    # 从配置获取市场分析回溯天数（默认30天）
    try:
        settings = get_settings()
        lookback_days = settings.MARKET_ANALYST_LOOKBACK_DAYS
        logger.info("📅 [配置验证] ===== MARKET_ANALYST_LOOKBACK_DAYS 配置检查 =====")
        logger.info(f"📅 [配置验证] 从配置文件读取: {lookback_days}天")
        logger.info("📅 [配置验证] 配置来源: app.core.config.Settings")
        logger.info(f"📅 [配置验证] 环境变量: MARKET_ANALYST_LOOKBACK_DAYS={lookback_days}")
    except Exception as e:
        lookback_days = 30  # 默认30天
        logger.warning(f"⚠️ [配置验证] 无法获取配置，使用默认值: {lookback_days}天")
        logger.warning(f"⚠️ [配置验证] 错误详情: {e}")

    # 使用 end_date 作为目标日期，向前回溯指定天数
    start_date, end_date = get_trading_date_range(end_date, lookback_days=lookback_days)

    logger.info("📅 [智能日期] ===== 日期范围计算结果 =====")
    logger.info(f"📅 [智能日期] 原始输入: {original_start_date} 至 {original_end_date}")
    logger.info(f"📅 [智能日期] 回溯天数: {lookback_days}天")
    logger.info(f"📅 [智能日期] 计算结果: {start_date} 至 {end_date}")
    logger.info(
        f"📅 [智能日期] 实际天数: {(datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days}天",
    )
    logger.info("💡 [智能日期] 说明: 自动扩展日期范围以处理周末、节假日和数据延迟")

    # 记录详细的输入参数
    logger.info(
        "📊 [统一接口] 开始获取中国股票数据",
        extra={
            "function": "get_china_stock_data_unified",
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "event_type": "unified_data_call_start",
        },
    )

    # 添加详细的股票代码追踪日志
    logger.info(
        f"🔍 [股票代码追踪] get_china_stock_data_unified 接收到的原始股票代码: '{ticker}' (类型: {type(ticker)})",
    )
    logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(ticker))}")
    logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(ticker))}")

    start_time = time.time()

    try:
        from .data_source_manager import get_china_stock_data_unified

        result = get_china_stock_data_unified(ticker, start_date, end_date)

        # 记录详细的输出结果
        duration = time.time() - start_time
        result_length = len(result) if result else 0
        is_success = result and "❌" not in result and "错误" not in result

        if is_success:
            logger.info(
                "✅ [统一接口] 中国股票数据获取成功",
                extra={
                    "function": "get_china_stock_data_unified",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                    "duration": duration,
                    "result_length": result_length,
                    "result_preview": result[:300] + "..." if result_length > 300 else result,
                    "event_type": "unified_data_call_success",
                },
            )
        else:
            logger.warning(
                "⚠️ [统一接口] 中国股票数据质量异常",
                extra={
                    "function": "get_china_stock_data_unified",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                    "duration": duration,
                    "result_length": result_length,
                    "result_preview": result[:300] + "..." if result_length > 300 else result,
                    "event_type": "unified_data_call_warning",
                },
            )

        return result

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"❌ [统一接口] 获取股票数据失败: {e}",
            extra={
                "function": "get_china_stock_data_unified",
                "ticker": ticker,
                "start_date": start_date,
                "end_date": end_date,
                "duration": duration,
                "error": str(e),
                "event_type": "unified_data_call_error",
            },
            exc_info=True,
        )
        return f"❌ 获取{ticker}股票数据失败: {e}"


def get_china_stock_info_unified(ticker: Annotated[str, "中国股票代码，如：000001、600036等"]) -> str:
    """
    统一的中国A股基本信息获取接口
    自动使用配置的数据源

    Args:
        ticker: 股票代码

    Returns:
        str: 股票基本信息
    """
    try:
        from .data_source_manager import get_china_stock_info_unified

        logger.info(f"📊 [统一接口] 获取{ticker}基本信息...")

        info = get_china_stock_info_unified(ticker)

        if info and info.get("name"):
            result = f"股票代码: {ticker}\n"
            result += f"股票名称: {info.get('name', '未知')}\n"
            result += f"所属地区: {info.get('area', '未知')}\n"
            result += f"所属行业: {info.get('industry', '未知')}\n"
            result += f"上市市场: {info.get('market', '未知')}\n"
            result += f"上市日期: {info.get('list_date', '未知')}\n"
            # 附加快照行情（若存在）
            cp = info.get("current_price")
            pct = info.get("change_pct")
            vol = info.get("volume")
            if cp is not None:
                result += f"当前价格: {cp}\n"
            if pct is not None:
                try:
                    pct_str = f"{float(pct):+.2f}%"
                except Exception:
                    pct_str = str(pct)
                result += f"涨跌幅: {pct_str}\n"
            if vol is not None:
                result += f"成交量: {vol}\n"
            result += f"数据来源: {info.get('source', 'unknown')}\n"

            return result
        return f"❌ 未能获取{ticker}的基本信息"

    except Exception as e:
        logger.error(f"❌ [统一接口] 获取股票信息失败: {e}")
        return f"❌ 获取{ticker}股票信息失败: {e}"


def switch_china_data_source(source: Annotated[str, "数据源名称：tushare"]) -> str:
    """
    切换中国股票数据源

    Args:
        source: 数据源名称

    Returns:
        str: 切换结果
    """
    try:
        from .data_source_manager import ChinaDataSource, get_data_source_manager

        source_mapping = {
            "tushare": ChinaDataSource.TUSHARE,
            "mongodb": ChinaDataSource.MONGODB,
        }

        if source.lower() not in source_mapping:
            return f"❌ 不支持的数据源: {source}。支持的数据源: {list(source_mapping.keys())}"

        manager = get_data_source_manager()
        target_source = source_mapping[source.lower()]

        if manager.set_current_source(target_source):
            return f"✅ 数据源已切换到: {source}"
        return f"❌ 数据源切换失败: {source} 不可用"

    except Exception as e:
        logger.error(f"❌ 数据源切换失败: {e}")
        return f"❌ 数据源切换失败: {e}"


def get_current_china_data_source() -> str:
    """
    获取当前中国股票数据源

    Returns:
        str: 当前数据源信息
    """
    try:
        from .data_source_manager import get_data_source_manager

        manager = get_data_source_manager()
        current = manager.get_current_source()
        available = manager.available_sources

        result = f"当前数据源: {current.value}\n"
        result += f"可用数据源: {[s.value for s in available]}\n"
        result += f"默认数据源: {manager.default_source.value}\n"

        return result

    except Exception as e:
        logger.error(f"❌ 获取数据源信息失败: {e}")
        return f"❌ 获取数据源信息失败: {e}"


# === Phase 3: CSDI 数据补全辅助函数 ===
_CSDI_IMPUTER_INSTANCE = None


def _maybe_csdi_impute(data_str: str, symbol: str) -> str:
    """如果 CSDI 可用且数据中包含 NaN，则对数据进行扩散插补

    此函数在统一数据接口的尾部调用，对已获取的数据进行后处理。
    如果配置项 diffusion_csdi_enabled 为 False 或 CSDI 模块不可用，
    则直接返回原始数据（零侵入）。

    实现:
        1. 尝试将字符串解析为 pandas DataFrame
        2. 检测 NaN 值
        3. 若无 NaN，直接返回
        4. 若有 NaN 且 CSDI 可用，将其转换为 numpy 数组后调用 impute()
        5. 将插补结果转回字符串格式

    Args:
        data_str: 原始数据字符串
        symbol: 股票代码（用于日志）

    Returns:
        str: 插补后的数据字符串（或原样返回）
    """
    # 配置检查: diffusion_csdi_enabled 为 False 时跳过
    try:
        from tradingagents.config.config_manager import config_manager

        settings = config_manager.load_settings()
        if not settings.get("diffusion_csdi_enabled", False):
            return data_str
    except Exception:
        return data_str

    # 模块可用性检查
    if not _CSDI_AVAILABLE or CSDIImputer is None:
        return data_str

    # 尝试解析为 DataFrame
    from io import StringIO

    import numpy as np
    import pandas as pd

    try:
        df = pd.read_csv(StringIO(data_str))
    except Exception:
        return data_str

    if df.empty:
        return data_str

    # 仅处理数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if numeric_cols.empty:
        return data_str

    numeric_data = df[numeric_cols].values  # (seq_len, feat)

    # 检测 NaN
    if not np.isnan(numeric_data).any():
        return data_str

    logger.info(
        "[CSDI] 检测到 NaN，启动扩散插补 — symbol=%s, shape=%s, nan_count=%d",
        symbol,
        numeric_data.shape,
        np.isnan(numeric_data).sum(),
    )

    # CSDI 插补
    global _CSDI_IMPUTER_INSTANCE
    if _CSDI_IMPUTER_INSTANCE is None:
        _CSDI_IMPUTER_INSTANCE = CSDIImputer()

    try:
        # CSDIImputer 需要 (batch, seq, feat) 格式
        observed = numeric_data[np.newaxis, :, :]  # (1, seq_len, feat)
        result = _CSDI_IMPUTER_INSTANCE.impute(observed, return_uncertainty=True)
        imputed = result["imputed"][0]  # (seq_len, feat)
        uncertainty = result["uncertainty"][0]  # (seq_len, feat)

        # 仅替换原始数据中的 NaN 位置
        nan_mask = np.isnan(numeric_data)
        numeric_data_clean = numeric_data.copy()
        numeric_data_clean[nan_mask] = imputed[nan_mask]

        nan_count = nan_mask.sum()
        logger.info(
            "[CSDI] 插补完成 — symbol=%s, filled=%d NaN values, max_uncertainty=%.4f",
            symbol,
            nan_count,
            uncertainty[nan_mask].max() if nan_mask.any() else 0.0,
        )

        # 写回 DataFrame
        df[numeric_cols] = numeric_data_clean

        # 转回字符串
        buffer = StringIO()
        df.to_csv(buffer, index=False)
        return buffer.getvalue()

    except Exception as exc:
        logger.warning("[CSDI] 插补失败 — symbol=%s, error=%s，返回原始数据", symbol, exc)
        return data_str


def get_stock_data_by_market(symbol: str, start_date: str | None = None, end_date: str | None = None) -> str:
    """
    根据股票市场类型自动选择数据源获取数据

    Args:
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的股票数据
    """
    try:
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(symbol)

        if market_info["is_china"]:
            data = get_china_stock_data_unified(symbol, start_date, end_date)
            return _maybe_csdi_impute(data, symbol)

        return f"❌ 不支持的市场类型: {symbol}"

    except Exception as e:
        logger.error(f"❌ 获取股票数据失败: {e}")
        return f"❌ 获取股票{symbol}数据失败: {e}"
