"""共享事件循环池 - 统一管理异步事件循环，解决线程泄漏和事件循环冲突"""

import asyncio
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EventLoopPool:
    """
    共享事件循环池
    - 维护一个后台线程运行事件循环
    - 通过 run_coroutine_threadsafe 提交任务
    - 关闭时自动清理所有循环
    - 线程安全
    """

    def __init__(self, name: str = "EventLoopPool"):
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False
        self._timers: list[asyncio.TimerHandle] = []

    def start(self) -> None:
        """启动后台事件循环线程"""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, name=f"{self._name}_thread", daemon=True)
            self._thread.start()
            logger.info(f"✅ [EventLoopPool] '{self._name}' 后台事件循环已启动")

    def _run_loop(self) -> None:
        """运行事件循环（在后台线程中）"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()  # type: ignore[union-attr]  # start() 确保 _loop 在 _run_loop 前赋值

    def run_coroutine(self, coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """
        提交协程到事件循环池中同步等待结果
        这是 _run_async_in_new_loop 的直接替代品
        """
        if not self._loop or not self._running:
            self.start()
        assert self._loop is not None  # 类型窄化：start() 确保 loop 已创建

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            logger.error(f"❌ [EventLoopPool] 协程执行失败: {e}")
            raise

    async def run_coroutine_async(self, coro: Coroutine[Any, Any, T], _timeout: float | None = None) -> T:
        """
        在事件循环池中异步等待另一个协程
        适用于异步协程中调用另一个可能需要独立循环的协程

        Args:
            coro: 要执行的协程
            _timeout: 保留参数，当前版本自动等待
        """
        if not self._loop or not self._running:
            self.start()
        assert self._loop is not None  # 类型窄化：start() 确保 loop 已创建

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return await asyncio.wrap_future(future)
        except Exception as e:
            logger.error(f"❌ [EventLoopPool] 异步协程执行失败: {e}")
            raise

    def run_coroutine_with_new_loop(self, coro: Coroutine[Any, Any, T], _timeout: float | None = None) -> T:
        """
        临时创建新事件循环执行协程后关闭
        用于无法使用共享池的特殊场景（如已在事件循环中）

        Args:
            coro: 要执行的协程
            _timeout: 保留参数，当前版本自动等待
        """
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def shutdown(self) -> None:
        """关闭事件循环池"""
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            if self._loop and not self._loop.is_closed():
                self._loop.close()
            logger.info(f"✅ [EventLoopPool] '{self._name}' 已关闭")

    @property
    def is_running(self) -> bool:
        return self._running


# 全局默认实例
_default_pool = EventLoopPool("default")


def get_event_loop_pool() -> EventLoopPool:
    """获取默认事件循环池"""
    return _default_pool


def shutdown_all_pools() -> None:
    """关闭所有事件循环池"""
    _default_pool.shutdown()
