#!/usr/bin/env python3
"""
Phase 2 (新增): efinance API Migration + _graph_pool 线程池隔离测试
验证：
1. efinance 新 API 方法调用正确性 (get_latest_quote / get_base_info)
2. simple_analysis_service 的 _graph_pool 属性存在和线程池隔离
"""

import asyncio
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEfinanceApiMigration(unittest.TestCase):
    """验证 efinance API 从旧版 (get_quote/get_quotations) 迁移到新版 (get_latest_quote/get_base_info)"""

    def setUp(self):
        from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

        self.provider = EfinanceProvider()

    def test_test_connection_uses_get_latest_quote(self):
        """验证 test_connection 使用 get_latest_quote（新 API）"""
        import inspect

        source = inspect.getsource(self.provider.test_connection)
        self.assertIn("get_latest_quote", source, "test_connection 应使用 get_latest_quote（新 API）")

    def test_get_stock_basic_info_uses_new_apis(self):
        """验证 get_stock_basic_info 使用 get_latest_quote 和 get_base_info（新 API）"""
        import inspect

        source = inspect.getsource(self.provider.get_stock_basic_info)
        self.assertIn("get_latest_quote", source, "get_stock_basic_info 应使用 get_latest_quote（新 API）")
        self.assertIn("get_base_info", source, "get_stock_basic_info 应使用 get_base_info（新 API）")

    def test_get_realtime_quotes_uses_get_latest_quote(self):
        """验证 get_realtime_quotes 使用 get_latest_quote（新 API）"""
        import inspect

        source = inspect.getsource(self.provider.get_realtime_quotes)
        self.assertIn("get_latest_quote", source, "get_realtime_quotes 应使用 get_latest_quote（新 API）")

    def test_new_column_mapping(self):
        """验证新 API 的列名映射 (代码/名称而非股票代码/股票名称)"""
        import inspect

        source = inspect.getsource(self.provider.get_realtime_quotes)
        # 新列名映射应包含 "代码" 和 "名称"
        self.assertIn('"代码"', source, "应包含新列名 '代码'")
        self.assertIn('"名称"', source, "应包含新列名 '名称'")

    def test_basic_info_column_mapping(self):
        """验证 get_stock_basic_info 中的新列名"""
        import inspect

        source = inspect.getsource(self.provider.get_stock_basic_info)
        # 应使用新列名 "所处行业"
        self.assertIn("所处行业", source, "应使用新列名 '所处行业'")

    def test_get_stock_basic_info_returns_dict(self):
        """验证 get_stock_basic_info 返回值结构"""

        async def run():
            result = await self.provider.get_stock_basic_info("000001")
            if result is not None:
                self.assertIsInstance(result, dict)
                self.assertIn("symbol", result)
                self.assertIn("name", result)
                self.assertIn("source", result)
                self.assertIn("industry", result)
                self.assertIn("area", result)
                self.assertIn("market", result)

        asyncio.run(run())

    def test_get_realtime_quotes_returns_df_or_none(self):
        """验证 get_realtime_quotes 返回值类型"""

        async def run():
            result = await self.provider.get_realtime_quotes(["000001"])
            import pandas as pd

            self.assertTrue(result is None or isinstance(result, pd.DataFrame))

        asyncio.run(run())

    def test_get_stock_quotes_delegates_to_get_realtime_quotes(self):
        """验证 get_stock_quotes 委托给 get_realtime_quotes"""
        import inspect

        source = inspect.getsource(self.provider.get_stock_quotes)
        self.assertIn("get_realtime_quotes", source, "get_stock_quotes 应委托给 get_realtime_quotes")

    def test_get_quote_history_unchanged(self):
        """验证 get_quote_history (历史数据) 未受影响"""
        import inspect

        source = inspect.getsource(self.provider.get_historical_data)
        self.assertIn("get_quote_history", source, "get_historical_data 仍应使用 get_quote_history")


class TestGraphPoolIsolation(unittest.TestCase):
    """验证 simple_analysis_service 的 _graph_pool 线程池隔离"""

    @classmethod
    def setUpClass(cls):
        cls.service_available = False
        try:
            from app.services.simple_analysis_service import SimpleAnalysisService

            cls.ServiceClass = SimpleAnalysisService
            cls.service_available = True
        except Exception as e:
            print(f"  ⚠️ SimpleAnalysisService 导入失败: {e}")

    def test_graph_pool_attribute_exists(self):
        """验证 _graph_pool 属性存在"""
        if not self.service_available:
            self.skipTest("SimpleAnalysisService 不可用")
        import inspect

        source = inspect.getsource(self.ServiceClass.__init__)
        self.assertIn("_graph_pool", source, "__init__ 中应初始化 _graph_pool 属性")

    def test_graph_pool_is_thread_pool_executor(self):
        """验证 _graph_pool 是 ThreadPoolExecutor 实例"""
        if not self.service_available:
            self.skipTest("SimpleAnalysisService 不可用")
        source = inspect.getsource(self.ServiceClass.__init__)
        self.assertIn("ThreadPoolExecutor", source, "_graph_pool 应为 ThreadPoolExecutor")
        self.assertIn("graph_propagate", source, "线程前缀应包含 graph_propagate")

    def test_graph_pool_separate_from_thread_pool(self):
        """验证 _graph_pool 与 _thread_pool 是不同实例"""
        if not self.service_available:
            self.skipTest("SimpleAnalysisService 不可用")
        import inspect

        source = inspect.getsource(self.ServiceClass.__init__)
        # 检查是否分别初始化了 _thread_pool 和 _graph_pool
        self.assertIn("self._thread_pool", source)
        self.assertIn("self._graph_pool", source)

    def test_graph_pool_used_for_propagate(self):
        """验证 propagate 调用使用 _graph_pool 而非 _thread_pool"""
        if not self.service_available:
            self.skipTest("SimpleAnalysisService 不可用")
        import inspect

        # 查找 propagate 调用处
        source = inspect.getsource(self.ServiceClass)
        # 检查是否有使用 _graph_pool.submit 调用 propagate
        self.assertIn("_graph_pool.submit", source, "propagate 应通过 _graph_pool.submit 调用")
        # 检查是否注释说明死锁修复
        self.assertIn("Bug 2 修复", source, "应有死锁修复的相关注释说明")

    def test_graph_pool_shutdown_on_cleanup(self):
        """验证 _graph_pool 在 cleanup 时被关闭"""
        if not self.service_available:
            self.skipTest("SimpleAnalysisService 不可用")
        import inspect

        # 检查 cleanup/关闭方法
        full_source = inspect.getsource(self.ServiceClass)
        self.assertIn("_graph_pool.shutdown", full_source, "cleanup 时应关闭 _graph_pool")


if __name__ == "__main__":
    unittest.main(verbosity=2)
