"""
中国市场数据提供器
包含 A股、港股等中国市场的数据源

主数据源: Tushare Pro
"""

import logging

logger = logging.getLogger(__name__)

# 导入中间抽象层
from .china_stock_data_provider import ChinaStockDataProvider

# 导入 Tushare 提供器（主数据源）
try:
    from .tushare import TushareProvider, get_tushare_provider

    TUSHARE_AVAILABLE = True
except ImportError as e:
    TushareProvider = None
    get_tushare_provider = None
    TUSHARE_AVAILABLE = False
    logger.warning("Tushare 不可用: %s", e)

__all__ = [
    "TUSHARE_AVAILABLE",
    "TushareProvider",
    "ChinaStockDataProvider",
    "get_tushare_provider",
]
