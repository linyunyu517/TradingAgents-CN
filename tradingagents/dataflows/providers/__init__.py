"""数据源提供器包 - 统一导入出口"""

from .base_provider import BaseStockDataProvider

from .errors import (
    ConnectionError,
    DataNotFoundError,
    DataSourceError,
    DataSourceErrorCode,
    RateLimitError,
    TokenRequiredError,
)
from .event_loop_pool import EventLoopPool, get_event_loop_pool, shutdown_all_pools
from .provider_pool import ProviderPool, get_provider_pool

__all__ = [
    # 基类和基础设施
    "BaseStockDataProvider",
    "ConnectionError",
    "DataNotFoundError",
    "DataSourceError",
    "DataSourceErrorCode",
    "EventLoopPool",
    "ProviderPool",
    "RateLimitError",
    "TokenRequiredError",
    "get_event_loop_pool",
    "get_provider_pool",
    "shutdown_all_pools",
]
