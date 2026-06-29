"""ProviderRegistry - 插件式数据源注册中心

提供统一的注册、发现、优先级管理和实例化功能。
新增数据源时只需在 register_provider 中注册即可。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .base_provider import BaseStockDataProvider
from .provider_pool import get_provider_pool

logger = logging.getLogger(__name__)


@dataclass
class ProviderRegistration:
    """数据源提供器注册信息"""

    name: str  # 唯一标识符
    provider_class: type[BaseStockDataProvider]  # Provider 类
    description: str  # 描述
    priority: int = 0  # 优先级（数字越大越优先）
    enabled: bool = True  # 是否启用
    requires_api_key: bool = False  # 是否需要 API Key
    is_free: bool = True  # 是否免费
    supported_features: list[str] = field(default_factory=list)  # 支持的特性列表
    factory: Callable | None = None  # 工厂函数（可选）

    def create_instance(self) -> BaseStockDataProvider:
        """创建 Provider 实例"""
        pool = get_provider_pool()
        if self.factory:
            return pool.get_or_create(self.factory, key=self.name)  # type: ignore[no-any-return,arg-type]
        return pool.get_or_create(self.provider_class, key=self.name)  # type: ignore[no-any-return]


class ProviderRegistry:
    """数据源提供器注册中心（单例）"""

    _instance = None
    _registrations: dict[str, ProviderRegistration]  # 在 initialize() 中初始化
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self):
        """初始化注册中心，注册所有内置 Provider"""
        if self._initialized:
            return

        self._registrations = {}

        # 注册 Tushare（主数据源）
        self._register_tushare()

        self._initialized = True
        logger.info(f"✅ [ProviderRegistry] 已注册 {len(self._registrations)} 个数据源提供器")

    def _register_tushare(self):
        """注册 Tushare Provider（主数据源）"""
        try:
            from .china.tushare import TushareProvider, get_tushare_provider

            self._registrations["tushare"] = ProviderRegistration(
                name="tushare",
                provider_class=TushareProvider,
                description="Tushare Pro - 专业A股数据",
                priority=90,  # 最高优先级（低于 MongoDB 的 100）
                enabled=True,
                requires_api_key=True,
                is_free=False,
                supported_features=[
                    "daily_kline",
                    "weekly_kline",
                    "monthly_kline",
                    "realtime_quote",
                    "stock_basic_info",
                    "financial_data",
                    "stock_list",
                    "daily_basic",
                    "trade_calendar",
                ],
                factory=get_tushare_provider,
            )
            logger.debug("  ✓ 注册 Tushare")
        except ImportError as e:
            logger.warning(f"  ⚠️ Tushare 注册失败: {e}")

    # _register_baostock() and _register_zzshare() removed

    def register(self, registration: ProviderRegistration) -> None:
        """动态注册 Provider（用于外部/插件注册）"""
        self._registrations[registration.name] = registration
        logger.info(f"✅ [ProviderRegistry] 注册 '{registration.name}': {registration.description}")

    def get_registration(self, name: str) -> ProviderRegistration | None:
        """获取注册信息"""
        return self._registrations.get(name)

    def get_instance(self, name: str) -> BaseStockDataProvider | None:
        """获取 Provider 实例"""
        reg = self._registrations.get(name)
        if reg and reg.enabled:
            return reg.create_instance()
        return None

    def get_all_registrations(self) -> dict[str, ProviderRegistration]:
        """获取所有注册"""
        return dict(self._registrations)

    def get_enabled_registrations(self) -> dict[str, ProviderRegistration]:
        """获取所有已启用的注册"""
        return {k: v for k, v in self._registrations.items() if v.enabled}

    def get_sorted_by_priority(self) -> list[ProviderRegistration]:
        """按优先级降序排列"""
        return sorted(self._registrations.values(), key=lambda r: r.priority, reverse=True)

    def get_enabled_sorted_by_priority(self) -> list[ProviderRegistration]:
        """获取已启用并按优先级降序排列"""
        return sorted((r for r in self._registrations.values() if r.enabled), key=lambda r: r.priority, reverse=True)

    def disable(self, name: str) -> None:
        """禁用 Provider"""
        if name in self._registrations:
            self._registrations[name].enabled = False
            logger.info(f"⛔ [ProviderRegistry] 禁用 '{name}'")

    def enable(self, name: str) -> None:
        """启用 Provider"""
        if name in self._registrations:
            self._registrations[name].enabled = True
            logger.info(f"✅ [ProviderRegistry] 启用 '{name}'")

    def has_feature(self, name: str, feature: str) -> bool:
        """检查 Provider 是否支持某个特性"""
        reg = self._registrations.get(name)
        if reg:
            return feature in reg.supported_features
        return False


# 全局单例
_registry = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    """获取全局 ProviderRegistry 单例"""
    _registry.initialize()
    return _registry
