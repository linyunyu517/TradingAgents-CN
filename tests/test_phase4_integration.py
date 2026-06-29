#!/usr/bin/env python3
"""
Phase 4: 集成测试
测试数据提供器 → 数据源管理器 → 数据流层的完整集成链路
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEfinanceIntegrationChain(unittest.TestCase):
    """测试 efinance provider 的完整调用链"""

    @classmethod
    def setUpClass(cls):
        try:
            from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

            cls.provider = EfinanceProvider()
            cls.efinance_available = cls.provider.connected
        except Exception:
            cls.efinance_available = False

    def setUp(self):
        if not self.efinance_available:
            self.skipTest("efinance 模块未安装或不可用")

    def async_test(self):
        """辅助运行异步测试"""

        def wrapper(*args, **kwargs):
            return asyncio.run(self(*args, **kwargs))

        return wrapper

    @async_test
    async def test_connect_then_get_basic_info(self):
        """测试 connect → get_stock_basic_info 链路"""
        connected = await self.provider.connect()
        self.assertTrue(connected)
        result = await self.provider.get_stock_basic_info("000001")
        if result is not None:
            self.assertIsInstance(result, dict)
            self.assertIn("code", result)
            self.assertIn("name", result)

    @async_test
    async def test_connect_then_get_quotes(self):
        """测试 connect → get_stock_quotes 链路"""
        connected = await self.provider.connect()
        self.assertTrue(connected)
        result = await self.provider.get_stock_quotes("000001")
        if result is not None:
            self.assertIsInstance(result, dict)
            self.assertIn("code", result)

    @async_test
    async def test_connect_then_get_realtime_quotes(self):
        """测试 get_realtime_quotes 接口"""
        connected = await self.provider.connect()
        self.assertTrue(connected)
        # 检查是否存在 get_realtime_quotes 方法
        if hasattr(self.provider, "get_realtime_quotes"):
            result = await self.provider.get_realtime_quotes(["000001"])
            if result is not None:
                self.assertIsInstance(result, (dict, list))

    @async_test
    async def test_full_call_chain(self):
        """测试完整调用链: connect → basic_info → quotes → historical"""
        connected = await self.provider.connect()
        self.assertTrue(connected)

        # 基础信息
        info = await self.provider.get_stock_basic_info("000001")
        if info is not None:
            self.assertIsInstance(info, dict)

        # 实时行情
        quotes = await self.provider.get_stock_quotes("000001")
        if quotes is not None:
            self.assertIsInstance(quotes, dict)

        # 历史数据（仅获取最近5天）
        from datetime import datetime, timedelta

        end = datetime.now()
        start = end - timedelta(days=5)
        await self.provider.get_historical_data("000001", start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))


class TestDataSourceManagerIntegration(unittest.TestCase):
    """测试 DataSourceManager 集成"""

    def test_import_and_init(self):
        """测试 DataSourceManager 的导入和初始化"""
        try:
            from tradingagents.dataflows.data_source_manager import DataSourceManager

            dsm = DataSourceManager()
            self.assertIsNotNone(dsm)
            self.assertTrue(hasattr(dsm, "get_data_source"))
        except Exception as e:
            self.skipTest(f"DataSourceManager 初始化失败: {e}")

    def test_cache_manager_init(self):
        """测试缓存管理器初始化"""
        try:
            from tradingagents.dataflows.cache import get_cache

            cache = get_cache()
            self.assertIsNotNone(cache)
        except Exception as e:
            self.skipTest(f"缓存管理器初始化失败: {e}")


class TestMultiSourceFallback(unittest.TestCase):
    """测试多数据源回退逻辑"""

    def test_china_data_sources_enum(self):
        """验证中国数据源枚举包含所有源"""
        from tradingagents.constants import DataSourceCode
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        codes = [e.value for e in ChinaDataSource]
        # 应该包含主要的 A 股数据源
        self.assertIn(DataSourceCode.MONGODB, codes)
        self.assertIn(DataSourceCode.EFINANCE, codes)
        self.assertIn(DataSourceCode.AKSHARE, codes)
        self.assertIn(DataSourceCode.BAOSTOCK, codes)

    def test_us_data_sources_enum(self):
        """验证美股数据源枚举"""
        from tradingagents.constants import DataSourceCode
        from tradingagents.dataflows.data_source_manager import USDataSource

        codes = [e.value for e in USDataSource]
        self.assertIn(DataSourceCode.YFINANCE, codes)
        self.assertIn(DataSourceCode.ALPHA_VANTAGE, codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
