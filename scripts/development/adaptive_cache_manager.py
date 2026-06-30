#!/usr/bin/env python3
"""
自适应缓存管理器 - 根据可用服务自动选择最佳缓存策略
支持文件缓存、Redis缓存、MongoDB缓存的智能切换
"""

import hashlib
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")

# 导入智能配置
try:
    from smart_config import get_config, get_smart_config

    SMART_CONFIG_AVAILABLE = True
except ImportError:
    SMART_CONFIG_AVAILABLE = False


class AdaptiveCacheManager:
    """自适应缓存管理器 - 智能选择缓存后端"""

    def __init__(self, cache_dir: str = "data_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # 获取智能配置
        self._load_smart_config()

        # 初始化缓存后端
        self._init_backends()

        self.logger.info(f"缓存管理器初始化完成，主要后端: {self.primary_backend}")

    def _load_smart_config(self):
        """加载智能配置"""
        if SMART_CONFIG_AVAILABLE:
            try:
                config_manager = get_smart_config()
                self.config = config_manager.get_config()
                self.primary_backend = self.config["cache"]["primary_backend"]
                self.mongodb_enabled = self.config["database"]["mongodb"]["enabled"]
                self.redis_enabled = self.config["database"]["redis"]["enabled"]
                self.fallback_enabled = self.config["cache"]["fallback_enabled"]
                self.ttl_settings = self.config["cache"]["ttl_settings"]

                self.logger.info("✅ 智能配置加载成功")
                return
            except Exception as e:
                self.logger.warning(f"智能配置加载失败: {e}")

        # 默认配置（纯文件缓存）
        self.config = {
            "cache": {
                "primary_backend": "file",
                "fallback_enabled": True,
                "ttl_settings": {
                    "us_stock_data": 7200,
                    "china_stock_data": 3600,
                    "us_news": 21600,
                    "china_news": 14400,
                    "us_fundamentals": 86400,
                    "china_fundamentals": 43200,
                },
            },
        }
        self.primary_backend = "file"
        self.mongodb_enabled = False
        self.redis_enabled = False
        self.fallback_enabled = True
        self.ttl_settings = self.config["cache"]["ttl_settings"]

        self.logger.info("使用默认配置（纯文件缓存）")

    def _init_backends(self):
        """初始化缓存后端"""
        self.mongodb_client = None
        self.redis_client = None

        # 初始化MongoDB
        if self.mongodb_enabled:
            try:
                import pymongo

                self.mongodb_client = pymongo.MongoClient("localhost", 27017, serverSelectionTimeoutMS=2000)
                # 测试连接
                self.mongodb_client.server_info()
                self.mongodb_db = self.mongodb_client.tradingagents
                self.logger.info("✅ MongoDB后端初始化成功")
            except Exception as e:
                self.logger.warning(f"MongoDB初始化失败: {e}")
                self.mongodb_enabled = False
                self.mongodb_client = None

        # 初始化Redis
        if self.redis_enabled:
            try:
                import redis

                self.redis_client = redis.Redis(host="localhost", port=6379, socket_timeout=2)
                # 测试连接
                self.redis_client.ping()
                self.logger.info("✅ Redis后端初始化成功")
            except Exception as e:
                self.logger.warning(f"Redis初始化失败: {e}")
                self.redis_enabled = False
                self.redis_client = None

        # 如果主要后端不可用，自动降级
        if self.primary_backend == "redis" and not self.redis_enabled:
            if self.mongodb_enabled:
                self.primary_backend = "mongodb"
                self.logger.info("Redis不可用，降级到MongoDB")
            else:
                self.primary_backend = "file"
                self.logger.info("Redis不可用，降级到文件缓存")

        elif self.primary_backend == "mongodb" and not self.mongodb_enabled:
            if self.redis_enabled:
                self.primary_backend = "redis"
                self.logger.info("MongoDB不可用，降级到Redis")
            else:
                self.primary_backend = "file"
                self.logger.info("MongoDB不可用，降级到文件缓存")

    def _get_cache_key(self, symbol: str, start_date: str, end_date: str, data_source: str = "default") -> str:
        """生成缓存键"""
        key_data = f"{symbol}_{start_date}_{end_date}_{data_source}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_ttl_seconds(self, symbol: str, data_type: str = "stock_data") -> int:
        """获取TTL秒数"""
        # 判断市场类型
        market = "china" if len(symbol) == 6 and symbol.isdigit() else "us"

        # 获取TTL配置
        ttl_key = f"{market}_{data_type}"
        ttl_hours = self.ttl_settings.get(ttl_key, 7200)  # 默认2小时
        return ttl_hours

    def _is_cache_valid(self, cache_time: datetime, ttl_seconds: int) -> bool:
        """检查缓存是否有效"""
        if cache_time is None:
            return False

        expiry_time = cache_time + timedelta(seconds=ttl_seconds)
        return datetime.now() < expiry_time

    def _save_to_file(self, cache_key: str, data: Any, metadata: dict) -> bool:
        """保存到文件缓存"""
        try:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            cache_data = {"data": data, "metadata": metadata, "timestamp": datetime.now()}

            with open(cache_file, "wb") as f:
                pickle.dump(cache_data, f)

            return True
        except Exception as e:
            self.logger.error(f"文件缓存保存失败: {e}")
            return False

    def _load_from_file(self, cache_key: str) -> dict | None:
        """从文件缓存加载"""
        try:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            if not cache_file.exists():
                return None

            with open(cache_file, "rb") as f:
                cache_data = pickle.load(f)

            return cache_data
        except Exception as e:
            self.logger.error(f"文件缓存加载失败: {e}")
            return None

    def _save_to_redis(self, cache_key: str, data: Any, metadata: dict, ttl_seconds: int) -> bool:
        """保存到Redis缓存"""
        if not self.redis_client:
            return False

        try:
            cache_data = {"data": data, "metadata": metadata, "timestamp": datetime.now().isoformat()}

            serialized_data = pickle.dumps(cache_data)
            self.redis_client.setex(cache_key, ttl_seconds, serialized_data)
            return True
        except Exception as e:
            self.logger.error(f"Redis缓存保存失败: {e}")
            return False

    def _load_from_redis(self, cache_key: str) -> dict | None:
        """从Redis缓存加载"""
        if not self.redis_client:
            return None

        try:
            serialized_data = self.redis_client.get(cache_key)
            if not serialized_data:
                return None

            cache_data = pickle.loads(serialized_data)
            # 转换时间戳
            if isinstance(cache_data["timestamp"], str):
                cache_data["timestamp"] = datetime.fromisoformat(cache_data["timestamp"])

            return cache_data
        except Exception as e:
            self.logger.error(f"Redis缓存加载失败: {e}")
            return None

    def save_stock_data(
        self,
        symbol: str,
        data: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        data_source: str = "default",
    ) -> str:
        """保存股票数据到缓存"""
        # 生成缓存键
        cache_key = self._get_cache_key(symbol, start_date or "", end_date or "", data_source)

        # 准备元数据
        metadata = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "data_source": data_source,
            "data_type": "stock_data",
        }

        # 获取TTL
        ttl_seconds = self._get_ttl_seconds(symbol, "stock_data")

        # 根据主要后端保存
        success = False

        if self.primary_backend == "redis":
            success = self._save_to_redis(cache_key, data, metadata, ttl_seconds)
        elif self.primary_backend == "mongodb":
            # MongoDB保存逻辑（简化版）
            success = self._save_to_file(cache_key, data, metadata)

        # 如果主要后端失败，使用文件缓存作为备用
        if not success and self.fallback_enabled:
            success = self._save_to_file(cache_key, data, metadata)
            if success:
                self.logger.info(f"使用文件缓存备用保存: {cache_key}")

        if success:
            self.logger.info(f"数据保存成功: {symbol} -> {cache_key}")
        else:
            self.logger.error(f"数据保存失败: {symbol}")

        return cache_key

    def load_stock_data(self, cache_key: str) -> Any | None:
        """从缓存加载股票数据"""
        cache_data = None

        # 根据主要后端加载
        if self.primary_backend == "redis":
            cache_data = self._load_from_redis(cache_key)
        elif self.primary_backend == "mongodb":
            # MongoDB加载逻辑（简化版）
            cache_data = self._load_from_file(cache_key)

        # 如果主要后端失败，尝试文件缓存
        if not cache_data and self.fallback_enabled:
            cache_data = self._load_from_file(cache_key)
            if cache_data:
                self.logger.info(f"使用文件缓存备用加载: {cache_key}")

        if not cache_data:
            return None

        # 检查缓存是否有效
        symbol = cache_data["metadata"].get("symbol", "")
        data_type = cache_data["metadata"].get("data_type", "stock_data")
        ttl_seconds = self._get_ttl_seconds(symbol, data_type)

        if not self._is_cache_valid(cache_data["timestamp"], ttl_seconds):
            self.logger.info(f"缓存已过期: {cache_key}")
            return None

        return cache_data["data"]

    def find_cached_stock_data(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None, data_source: str = "default",
    ) -> str | None:
        """查找缓存的股票数据"""
        cache_key = self._get_cache_key(symbol, start_date or "", end_date or "", data_source)

        # 检查缓存是否存在且有效
        if self.load_stock_data(cache_key) is not None:
            return cache_key

        return None

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "primary_backend": self.primary_backend,
            "mongodb_enabled": self.mongodb_enabled,
            "redis_enabled": self.redis_enabled,
            "fallback_enabled": self.fallback_enabled,
            "cache_directory": str(self.cache_dir),
            "file_cache_count": len(list(self.cache_dir.glob("*.pkl"))),
        }

        # Redis统计
        if self.redis_client:
            try:
                redis_info = self.redis_client.info()
                stats["redis_memory_used"] = redis_info.get("used_memory_human", "N/A")
                stats["redis_keys"] = self.redis_client.dbsize()
            except Exception:
                stats["redis_status"] = "Error"

        return stats


# 全局缓存管理器实例
_cache_manager = None


def get_cache() -> AdaptiveCacheManager:
    """获取全局自适应缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = AdaptiveCacheManager()
    return _cache_manager


def main():
    """测试自适应缓存管理器"""
    logger.info("🔧 测试自适应缓存管理器")
    logger.info("=")

    # 创建缓存管理器
    cache = get_cache()

    # 显示状态
    stats = cache.get_cache_stats()
    logger.info("\n📊 缓存状态:")
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")

    # 测试缓存功能
    logger.info("\n💾 测试缓存功能...")

    test_data = "测试股票数据 - AAPL"
    cache_key = cache.save_stock_data(
        symbol="AAPL", data=test_data, start_date="2024-01-01", end_date="2024-12-31", data_source="test",
    )
    logger.info(f"✅ 数据保存: {cache_key}")

    # 加载数据
    loaded_data = cache.load_stock_data(cache_key)
    if loaded_data == test_data:
        logger.info("✅ 数据加载成功")
    else:
        logger.error("❌ 数据加载失败")

    # 查找缓存
    found_key = cache.find_cached_stock_data(
        symbol="AAPL", start_date="2024-01-01", end_date="2024-12-31", data_source="test",
    )

    if found_key:
        logger.info(f"✅ 缓存查找成功: {found_key}")
    else:
        logger.error("❌ 缓存查找失败")

    logger.info("\n🎉 自适应缓存管理器测试完成!")


if __name__ == "__main__":
    main()
