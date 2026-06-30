"""
港股和美股数据服务
已移除 yfinance、finnhub、alpha_vantage、akshare 等数据源引用
当前仅保留缓存基础设施
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from tradingagents.dataflows.cache import get_cache

logger = logging.getLogger(__name__)


class ForeignStockService:
    """港股和美股数据服务（数据源已移除，保留缓存基础设施）"""

    def __init__(self, db=None):
        self.cache = get_cache()
        self.db = db
        self._request_locks = defaultdict(asyncio.Lock)
        self._pending_requests = {}
        logger.info("✅ ForeignStockService 初始化完成（数据源已移除）")

    async def get_quote(self, market: str, code: str, force_refresh: bool = False) -> dict:
        raise NotImplementedError("Foreign stock data sources have been removed")

    async def get_basic_info(self, market: str, code: str, force_refresh: bool = False) -> dict:
        raise NotImplementedError("Foreign stock data sources have been removed")

    async def get_kline(
        self, market: str, code: str, period: str = "day", limit: int = 120, force_refresh: bool = False,
    ) -> list[dict]:
        raise NotImplementedError("Foreign stock data sources have been removed")

    async def get_hk_news(self, code: str, days: int = 2, limit: int = 50) -> dict:
        raise NotImplementedError("Foreign stock data sources have been removed")

    async def get_us_news(self, code: str, days: int = 2, limit: int = 50) -> dict:
        raise NotImplementedError("Foreign stock data sources have been removed")
