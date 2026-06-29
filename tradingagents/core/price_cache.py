"""PriceCache - 跨模块共享的价格数据缓存，避免重复查询。"""

import threading
import time

import pandas as pd


class PriceCache:
    """线程安全的进程内价格缓存。"""

    _instance = None
    _lock = threading.Lock()
    # mypy: 类级别类型注解（无默认值避免 RUF012，__new__ 会在首次创建时设置实例属性）
    _cache: "dict[str, pd.DataFrame]"
    _ttl: "dict[str, float]"
    _default_ttl: int = 60

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._ttl = {}
                    cls._instance._default_ttl = 60  # 60秒
        return cls._instance

    def get(self, symbol: str) -> pd.DataFrame | None:
        """返回缓存的数据帧，若不存在或已过期则返回 None。"""
        if symbol in self._cache:
            if time.time() - self._ttl.get(symbol, 0) < self._default_ttl:
                return self._cache[symbol]
            del self._cache[symbol]
            del self._ttl[symbol]
        return None

    def set(self, symbol: str, data: pd.DataFrame) -> None:
        """缓存指定标的的数据帧。"""
        self._cache[symbol] = data
        self._ttl[symbol] = time.time()

    def invalidate(self, symbol: str | None = None) -> None:
        """使缓存失效。若 symbol 为 None 则清空全部。"""
        if symbol:
            self._cache.pop(symbol, None)
            self._ttl.pop(symbol, None)
        else:
            self._cache.clear()
            self._ttl.clear()


# 全局单例
price_cache = PriceCache()
