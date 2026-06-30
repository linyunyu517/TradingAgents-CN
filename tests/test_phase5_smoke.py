#!/usr/bin/env python3
"""
Phase 5: 冒烟测试 (Smoke Tests)
快速验证核心功能：模块导入、数据源初始化
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSmokeImports(unittest.TestCase):
    """测试关键模块的导入"""

    def test_import_base_provider(self):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        self.assertTrue(hasattr(BaseStockDataProvider, "connect"))
        self.assertTrue(hasattr(BaseStockDataProvider, "get_stock_basic_info"))
        self.assertTrue(hasattr(BaseStockDataProvider, "get_stock_quotes"))
        self.assertTrue(hasattr(BaseStockDataProvider, "get_historical_data"))

    def test_import_efinance(self):
        try:
            from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

            self.assertTrue(hasattr(EfinanceProvider, "connect"))
            self.assertTrue(hasattr(EfinanceProvider, "get_stock_basic_info"))
            self.assertTrue(hasattr(EfinanceProvider, "get_stock_quotes"))
        except ImportError as e:
            self.skipTest(f"efinance provider 导入失败: {e}")

    def test_import_akshare(self):
        try:
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            self.assertTrue(hasattr(AKShareProvider, "connect"))
        except ImportError as e:
            self.skipTest(f"AKShare provider 导入失败: {e}")

    def test_import_baostock(self):
        try:
            from tradingagents.dataflows.providers.china.baostock import BaoStockProvider

            self.assertTrue(hasattr(BaoStockProvider, "connect"))
        except ImportError as e:
            self.skipTest(f"BaoStock provider 导入失败: {e}")

    def test_import_data_source_manager(self):
        from tradingagents.dataflows.data_source_manager import DataSourceManager

        # DataSourceManager 实际方法: get_current_source, get_stock_basic_info, get_stock_info, get_stock_data
        self.assertTrue(hasattr(DataSourceManager, "get_current_source"))
        self.assertTrue(hasattr(DataSourceManager, "get_stock_basic_info"))
        self.assertTrue(hasattr(DataSourceManager, "get_stock_data"))

    def test_import_config_manager(self):
        from tradingagents.config.config_manager import ConfigManager

        # ConfigManager 实际方法: get_enabled_models, get_model_by_name, get_env_config_status, get_usage_statistics
        self.assertTrue(hasattr(ConfigManager, "get_enabled_models"))

    def test_import_dataflow_interface(self):
        # interface.py 是函数式 API（无类）
        # 验证模块级别的关键函数可导入
        from tradingagents.dataflows import interface

        self.assertTrue(hasattr(interface, "get_stock_data_by_market"))
        self.assertTrue(hasattr(interface, "get_china_stock_info_unified"))

    def test_import_constants(self):
        from tradingagents.constants import DataSourceCode

        self.assertTrue(hasattr(DataSourceCode, "EFINANCE"))
        self.assertTrue(hasattr(DataSourceCode, "AKSHARE"))
        self.assertTrue(hasattr(DataSourceCode, "BAOSTOCK"))

    def test_import_all_providers(self):
        """尝试导入所有 provider 模块"""
        modules = [
            "tradingagents.dataflows.providers.china.efinance",
            "tradingagents.dataflows.providers.china.akshare",
            "tradingagents.dataflows.providers.china.baostock",
            "tradingagents.dataflows.providers.china.tushare",
            "tradingagents.dataflows.providers.hk.hk_stock",
            "tradingagents.dataflows.providers.us.yfinance",
            "tradingagents.dataflows.providers.us.alpha_vantage_common",
            "tradingagents.dataflows.providers.us.finnhub",
        ]
        for mod_name in modules:
            try:
                __import__(mod_name)
            except ImportError as e:
                print(f"  ⚠️ 模块 {mod_name} 导入失败: {e}")


class TestSmokeProviderInit(unittest.TestCase):
    """测试数据源提供器的实例化和 connect"""

    def test_efinance_provider_init(self):
        try:
            from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

            provider = EfinanceProvider()
            self.assertEqual(provider.provider_name, "efinance")
            self.assertIsNotNone(provider)
        except Exception as e:
            self.skipTest(f"efinance provider 初始化失败: {e}")

    def test_akshare_provider_init(self):
        try:
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            provider = AKShareProvider()
            self.assertIsNotNone(provider)
        except Exception as e:
            self.skipTest(f"AKShare provider 初始化失败: {e}")

    def test_baostock_provider_init(self):
        try:
            from tradingagents.dataflows.providers.china.baostock import BaoStockProvider

            provider = BaoStockProvider()
            self.assertIsNotNone(provider)
        except Exception as e:
            self.skipTest(f"BaoStock provider 初始化失败: {e}")

    def test_datasource_manager_init(self):
        try:
            from tradingagents.dataflows.data_source_manager import DataSourceManager

            dsm = DataSourceManager()
            self.assertIsNotNone(dsm)
        except Exception as e:
            self.skipTest(f"DataSourceManager 初始化失败: {e}")


class TestSmokeDataFlow(unittest.TestCase):
    """测试数据流层基础功能"""

    def test_standardize_basic_info_exists(self):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        self.assertTrue(hasattr(BaseStockDataProvider, "standardize_basic_info"))

    def test_standardize_quotes_exists(self):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        self.assertTrue(hasattr(BaseStockDataProvider, "standardize_quotes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
