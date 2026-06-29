from __future__ import annotations

"""
数据源提供器配置管理

从 tradingagents/dataflows/providers_config.py 迁移而来
统一管理所有数据源提供器的配置
"""
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class DataSourceConfig:
    """数据源配置管理器"""

    def __init__(self):
        self._configs = {}
        self._load_configs()

    def _load_configs(self):
        """加载所有数据源配置"""
        # Tushare Pro 配置 - 主数据源
        self._configs["tushare"] = {
            "enabled": self._get_bool_env("TUSHARE_ENABLED", True),
            "token": os.getenv("TUSHARE_TOKEN", ""),
            "timeout": self._get_int_env("TUSHARE_TIMEOUT", 30),
            "rate_limit": self._get_float_env("TUSHARE_RATE_LIMIT", 0.2),
            "max_retries": self._get_int_env("TUSHARE_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("TUSHARE_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("TUSHARE_CACHE_TTL", 1800),
        }

        # 通达信配置 - 已移除
        # TDX 数据源已不再支持
        # self._configs["tdx"] = {
        #     "enabled": False,
        # }

        # [FIX] 2026-06-26: real_data_pipeline 配置 - 主数据源改为 tushare
        self._configs["real_data_pipeline"] = {
            "enabled": self._get_bool_env("REAL_DATA_PIPELINE_ENABLED", True),
            "primary_source": os.getenv("REAL_DATA_PRIMARY_SOURCE", "tushare"),
            "fallback_sources": os.getenv("REAL_DATA_FALLBACK_SOURCES", "tushare").split(","),
            "cache_enabled": self._get_bool_env("REAL_DATA_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("REAL_DATA_CACHE_TTL", 60),  # 实时数据缓存60秒
            "max_retries": self._get_int_env("REAL_DATA_MAX_RETRIES", 2),
            "timeout": self._get_int_env("REAL_DATA_TIMEOUT", 15),
        }

        logger.debug("✅ 数据源配置加载完成")

    def get_provider_config(self, provider_name: str) -> dict[str, Any]:
        """
        获取指定提供器的配置

        Args:
            provider_name: 提供器名称

        Returns:
            配置字典
        """
        config = self._configs.get(provider_name.lower(), {})
        if not config:
            logger.warning(f"⚠️ 未找到 {provider_name} 的配置")
        return config

    def is_provider_enabled(self, provider_name: str) -> bool:
        """检查提供器是否启用"""
        config = self.get_provider_config(provider_name)
        return config.get("enabled", False)

    def get_all_enabled_providers(self) -> list:
        """获取所有启用的提供器名称"""
        enabled = []
        for name, config in self._configs.items():
            if config.get("enabled", False):
                enabled.append(name)
        return enabled

    def _get_bool_env(self, key: str, default: bool) -> bool:
        """获取布尔型环境变量"""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    def _get_int_env(self, key: str, default: int) -> int:
        """获取整型环境变量"""
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    def _get_float_env(self, key: str, default: float) -> float:
        """获取浮点型环境变量"""
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default


# 全局配置实例
_config_instance = None


def get_data_source_config() -> DataSourceConfig:
    """获取全局数据源配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = DataSourceConfig()
    return _config_instance


def get_provider_config(provider_name: str) -> dict[str, Any]:
    """获取指定提供器配置的便捷函数"""
    config = get_data_source_config()
    return config.get_provider_config(provider_name)
