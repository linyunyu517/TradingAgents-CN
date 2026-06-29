"""Provider 实例池 - 线程安全的单例提供器管理"""

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class ProviderPool:
    """
    线程安全的 Provider 实例池
    - 每个 Provider 类只有一个实例（单例）
    - 线程安全，适用于多线程并发访问
    - 自动管理生命周期
    """

    def __init__(self):
        self._instances: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._connect_lock = threading.Lock()

    def get_or_create(self, provider_class: type, key: str | None = None, *args, **kwargs) -> Any:
        """
        获取或创建 Provider 实例（线程安全）
        - provider_class: Provider 类
        - key: 自定义键（默认用类名）
        """
        instance_key = key or provider_class.__name__
        with self._lock:
            if instance_key not in self._instances:
                logger.info(f"🔄 [ProviderPool] 创建 {instance_key} 实例")
                instance = provider_class(*args, **kwargs)
                self._instances[instance_key] = instance
            return self._instances[instance_key]

    def get(self, key: str) -> Any | None:
        """获取已有实例"""
        with self._lock:
            return self._instances.get(key)

    def register(self, key: str, instance: Any) -> None:
        """注册实例"""
        with self._lock:
            self._instances[key] = instance

    def remove(self, key: str) -> None:
        """移除实例"""
        with self._lock:
            self._instances.pop(key, None)

    def shutdown_all(self) -> None:
        """关闭所有 Provider"""
        with self._lock:
            for key, instance in self._instances.items():
                if hasattr(instance, "shutdown") and callable(instance.shutdown):
                    try:
                        instance.shutdown()
                    except Exception as e:
                        logger.error(f"❌ 关闭 {key} 失败: {e}")
            self._instances.clear()


# 全局默认实例
_default_provider_pool = ProviderPool()


def get_provider_pool() -> ProviderPool:
    """获取默认 Provider 实例池"""
    return _default_provider_pool
