# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

# 导入技术指标模块（新路径）
try:
    from .technical import STOCKSTATS_AVAILABLE, StockstatsUtils
except ImportError:
    try:
        from .technical.stockstats import StockstatsUtils

        STOCKSTATS_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"⚠️ stockstats模块不可用: {e}")
        StockstatsUtils = None
        STOCKSTATS_AVAILABLE = False

from .interface import (
    get_china_stock_data_unified,
    get_china_stock_info_unified,
    get_current_china_data_source,
    get_stock_data_by_market,
    get_stock_stats_indicators_window,
    get_stockstats_indicator,
    switch_china_data_source,
)

__all__ = [
    "get_china_stock_data_unified",
    "get_china_stock_info_unified",
    "get_current_china_data_source",
    "get_stock_data_by_market",
    "get_stock_stats_indicators_window",
    "get_stockstats_indicator",
    "switch_china_data_source",
]
