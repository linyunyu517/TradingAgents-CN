# LLM Adapters for TradingAgents
# ========== BUG-012 修复: 添加线程安全的适配器注册表 ==========
import threading
from typing import Any, Dict, Type

from .dashscope_openai_adapter import ChatDashScopeOpenAI
from .google_openai_adapter import ChatGoogleOpenAI


class AdapterRegistry:
    """线程安全的适配器注册表（单例模式）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "AdapterRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._registry: dict[str, type[Any]] = {}
                    cls._instance._registry_lock = threading.RLock()
        return cls._instance

    def register(self, name: str, adapter_class: type[Any]) -> None:
        """线程安全地注册适配器"""
        with self._registry_lock:
            self._registry[name] = adapter_class

    def get(self, name: str) -> type[Any]:
        """线程安全地获取适配器"""
        with self._registry_lock:
            return self._registry[name]

    def get_all(self) -> dict[str, type[Any]]:
        """线程安全地获取所有适配器"""
        with self._registry_lock:
            return dict(self._registry)

    def __contains__(self, name: str) -> bool:
        with self._registry_lock:
            return name in self._registry


# 全局适配器注册表单例
adapter_registry = AdapterRegistry()

# 自动注册内置适配器
adapter_registry.register("dashscope", ChatDashScopeOpenAI)
adapter_registry.register("google", ChatGoogleOpenAI)

__all__ = [
    "AdapterRegistry",
    "ChatDashScopeOpenAI",
    "ChatGoogleOpenAI",
    "adapter_registry",
]
