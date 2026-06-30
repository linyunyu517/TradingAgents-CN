"""
测试异步事件循环在线程池中的修复

问题：在线程池中调用 asyncio.get_event_loop() 会抛出 RuntimeError
解决：使用 asyncio.new_event_loop() 创建新的事件循环
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from tradingagents.dataflows.data_source_manager import DataSourceManager


def test_asyncio_in_thread_pool():
    """测试在线程池中使用异步方法"""

    def run_in_thread():
        """在线程池中运行的函数"""
        # 这应该不会抛出 RuntimeError
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # 在线程池中没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 测试运行一个简单的异步函数
        async def simple_async():
            await asyncio.sleep(0.01)
            return "success"

        result = loop.run_until_complete(simple_async())
        return result

    # 在线程池中执行
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(run_in_thread)
        result = future.result(timeout=5)
        assert result == "success"


def test_data_source_manager_in_thread_pool():
    """测试 DataSourceManager 在线程池中的使用"""

    def get_stock_data():
        """在线程池中获取股票数据"""
        manager = DataSourceManager()
        # 这应该不会抛出 RuntimeError
        # 注意：实际数据获取可能失败（如果没有配置API key），但不应该是事件循环错误
        try:
            result = manager.get_stock_data(
                symbol="000001", start_date="2025-01-01", end_date="2025-01-10", period="daily",
            )
            return result
        except Exception as e:
            # 如果是事件循环错误，测试失败
            if "There is no current event loop" in str(e):
                raise AssertionError(f"事件循环错误未修复: {e}")
            # 其他错误（如API配置问题）可以接受
            return f"其他错误（可接受）: {type(e).__name__}"

    # 在线程池中执行
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(get_stock_data)
        result = future.result(timeout=30)

        # 验证不是事件循环错误
        assert "There is no current event loop" not in str(result)
        print(f"✅ 测试通过，结果: {result[:200] if isinstance(result, str) else result}")


def test_multiple_threads():
    """测试多个线程同时使用异步方法"""

    def run_async_task(task_id):
        """在线程中运行异步任务"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def task():
            await asyncio.sleep(0.01)
            return f"Task {task_id} completed"

        return loop.run_until_complete(task())

    # 在多个线程中同时执行
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_async_task, i) for i in range(5)]
        results = [f.result(timeout=5) for f in futures]

        # 验证所有任务都成功完成
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result == f"Task {i} completed"


if __name__ == "__main__":
    print("🧪 测试1: 线程池中的异步方法")
    test_asyncio_in_thread_pool()
    print("✅ 测试1通过\n")

    print("🧪 测试2: DataSourceManager 在线程池中")
    test_data_source_manager_in_thread_pool()
    print("✅ 测试2通过\n")

    print("🧪 测试3: 多线程并发")
    test_multiple_threads()
    print("✅ 测试3通过\n")

    print("🎉 所有测试通过！")
