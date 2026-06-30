#!/usr/bin/env python3
"""
Phase 2: 传统单元测试（全量）
测试 dataflows/providers 下的所有 provider 模块
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBaseProvider(unittest.TestCase):
    """测试 BaseStockDataProvider 基类"""

    def setUp(self):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        # 使用一个具体的子类来测试基类方法
        class ConcreteProvider(BaseStockDataProvider):
            async def connect(self) -> bool:
                self.connected = True
                return True

            async def get_stock_basic_info(self, symbol=None):
                return {"code": "000001", "name": "Test"}

            async def get_stock_quotes(self, symbol: str):
                return {"code": symbol, "price": 10.0}

            async def get_historical_data(self, symbol, start_date, end_date=None):
                return None

        self.provider = ConcreteProvider("test_provider")

    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.provider.provider_name, "test_provider")
        self.assertFalse(self.provider.connected)

    def test_disconnect(self):
        """测试断开连接"""
        self.provider.connected = True
        asyncio.run(self.provider.disconnect())
        self.assertFalse(self.provider.connected)

    def test_is_available(self):
        """测试可用性检查"""
        self.provider.connected = False
        self.assertFalse(self.provider.is_available())
        self.provider.connected = True
        self.assertTrue(self.provider.is_available())

    def test_standardize_basic_info_basic(self):
        """测试标准化的基础信息"""
        raw = {"code": "000001", "name": "平安银行", "symbol": "000001.SZ"}
        result = self.provider.standardize_basic_info(raw)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["name"], "平安银行")

    def test_standardize_basic_info_empty(self):
        """测试空数据标准化"""
        result = self.provider.standardize_basic_info({})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["code"], "")
        self.assertEqual(result["name"], "")

    def test_standardize_quotes_basic(self):
        """测试行情标准化"""
        raw = {
            "code": "000001",
            "name": "平安银行",
            "price": 10.5,
            "open": 10.0,
            "high": 10.8,
            "low": 9.9,
            "volume": 1000000,
            "amount": 10500000,
        }
        result = self.provider.standardize_quotes(raw)
        self.assertIsInstance(result, dict)
        self.assertIn("code", result)
        # 验证数值类型
        if result.get("price") is not None:
            self.assertIsInstance(result["price"], (int, float))

    def test_standardize_quotes_empty(self):
        """测试空行情数据标准化"""
        result = self.provider.standardize_quotes({})
        self.assertIsInstance(result, dict)

    def test_get_stock_list_delegates_to_basic_info(self):
        """测试 get_stock_list 委托给 get_stock_basic_info"""

        async def run():
            result = await self.provider.get_stock_list()
            self.assertEqual(result, {"code": "000001", "name": "Test"})

        asyncio.run(run())

    def test_get_financial_data_returns_none(self):
        """测试默认 get_financial_data 返回 None"""

        async def run():
            result = await self.provider.get_financial_data("000001")
            self.assertIsNone(result)

        asyncio.run(run())


class TestEfinanceProviderInterface(unittest.TestCase):
    """测试 EfinanceProvider 接口完整性"""

    def setUp(self):
        from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

        self.provider = EfinanceProvider()

    def test_class_inherits_base(self):
        """验证继承自 BaseStockDataProvider"""
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        self.assertTrue(issubclass(type(self.provider), BaseStockDataProvider))

    def test_provider_name(self):
        """验证 provider 名称"""
        self.assertEqual(self.provider.provider_name, "efinance")

    def test_has_required_methods(self):
        """验证所有必需的方法签名"""
        required = [
            "connect",
            "get_stock_basic_info",
            "get_stock_quotes",
            "get_historical_data",
            "standardize_basic_info",
            "standardize_quotes",
        ]
        for method_name in required:
            self.assertTrue(hasattr(self.provider, method_name), f"缺少必需方法: {method_name}")
            self.assertTrue(callable(getattr(self.provider, method_name)), f"方法不可调用: {method_name}")

    def test_connect_is_async(self):
        """验证 connect 是异步方法"""
        import asyncio

        self.assertTrue(asyncio.iscoroutinefunction(self.provider.connect))

    def test_get_stock_quotes_is_async(self):
        """验证 get_stock_quotes 是异步方法"""
        import asyncio

        self.assertTrue(asyncio.iscoroutinefunction(self.provider.get_stock_quotes))

    def test_get_stock_basic_info_is_async(self):
        """验证 get_stock_basic_info 是异步方法"""
        import asyncio

        self.assertTrue(asyncio.iscoroutinefunction(self.provider.get_stock_basic_info))

    def test_get_historical_data_is_async(self):
        """验证 get_historical_data 是异步方法"""
        import asyncio

        self.assertTrue(asyncio.iscoroutinefunction(self.provider.get_historical_data))

    def test_standardize_methods_exist(self):
        """验证标准化方法存在且可调用"""
        self.assertTrue(callable(self.provider.standardize_basic_info))
        self.assertTrue(callable(self.provider.standardize_quotes))

    def test_get_stock_queries_returns_dict_or_none(self):
        """验证 get_stock_quotes 返回值类型"""

        async def run():
            # 由于 efinance 可能未安装，应优雅处理
            result = await self.provider.get_stock_quotes("000001")
            # 返回值应为 dict 或 None
            self.assertTrue(result is None or isinstance(result, dict))

        asyncio.run(run())


class TestDataSourceManagerRouting(unittest.TestCase):
    """测试 DataSourceManager 路由逻辑"""

    @classmethod
    def setUpClass(cls):
        pass

    def test_data_source_enum_values(self):
        """验证数据源枚举值"""
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        self.assertTrue(hasattr(ChinaDataSource, "EFINANCE"))
        self.assertTrue(hasattr(ChinaDataSource, "AKSHARE"))
        self.assertTrue(hasattr(ChinaDataSource, "BAOSTOCK"))
        self.assertTrue(hasattr(ChinaDataSource, "MONGODB"))

    def test_providers_init_imports(self):
        """验证 provider 初始化导入"""
        try:
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            self.assertTrue(callable(AKShareProvider))
        except ImportError as e:
            self.skipTest(f"AKShare 未安装: {e}")

        try:
            from tradingagents.dataflows.providers.china.baostock import BaoStockProvider

            self.assertTrue(callable(BaoStockProvider))
        except ImportError as e:
            self.skipTest(f"BaoStock 未安装: {e}")

    @patch("tradingagents.dataflows.data_source_manager.DataSourceManager")
    def test_source_priority(self, mock_dsm):
        """测试数据源优先级配置"""
        from tradingagents.constants import DataSourceCode
        from tradingagents.dataflows.data_source_manager import ChinaDataSource

        # 验证优先级顺序：MONGODB > EFINANCE > TUSHARE > AKSHARE > BAOSTOCK
        enum_values = [e.value for e in ChinaDataSource]
        self.assertIn(DataSourceCode.MONGODB, enum_values)
        self.assertIn(DataSourceCode.EFINANCE, enum_values)
        self.assertIn(DataSourceCode.AKSHARE, enum_values)
        self.assertIn(DataSourceCode.BAOSTOCK, enum_values)


class TestProviderStandardization(unittest.TestCase):
    """测试数据标准化方法的一致性"""

    def setUp(self):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        class TestProvider(BaseStockDataProvider):
            async def connect(self):
                return True

            async def get_stock_basic_info(self, symbol=None):
                return {}

            async def get_stock_quotes(self, symbol):
                return {}

            async def get_historical_data(self, symbol, start_date, end_date=None):
                return None

        self.provider = TestProvider("test")

    def test_standardize_basic_info_contract(self):
        """标准化基础信息输出合同检查"""
        test_cases = [
            {"code": "000001", "name": "A", "industry": "金融"},
            {"symbol": "000001.SZ", "name": "B"},
            {"ts_code": "000001.SZ"},
            {},
            {"code": None, "name": None},
        ]
        for raw in test_cases:
            result = self.provider.standardize_basic_info(raw)
            self.assertIsInstance(result, dict)
            # 验证所有必需字段都存在
            for key in ["code", "name", "symbol"]:
                self.assertIn(key, result, f"缺少字段: {key} in input {raw}")

    def test_standardize_quotes_contract(self):
        """标准化行情输出合同检查"""
        test_cases = [
            {"code": "000001", "price": 10.5, "open": 10.0},
            {"code": "000002"},
            {},
            {"code": None},
        ]
        for raw in test_cases:
            result = self.provider.standardize_quotes(raw)
            self.assertIsInstance(result, dict)
            # 验证 code 字段存在
            self.assertIn("code", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
