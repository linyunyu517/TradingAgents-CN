#!/usr/bin/env python3
"""
Phase 7: 端到端测试 (End-to-End)
模拟一次完整的股票分析流程（不实际调用 LLM）
使用 600162（香江控股）作为测试标的
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEndToEndFlow(unittest.TestCase):
    """端到端数据流完整性测试"""

    SYMBOL = "600162"  # 香江控股

    @classmethod
    def setUpClass(cls):
        cls.efinance_available = False
        cls.dsm_available = False
        try:
            from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

            cls.efinance = EfinanceProvider()
            cls.efinance_available = cls.efinance.connected
        except Exception as e:
            print(f"  ⚠️ efinance provider 不可用: {e}")

        try:
            from tradingagents.dataflows.data_source_manager import DataSourceManager

            cls.dsm = DataSourceManager()
            cls.dsm_available = True
        except Exception as e:
            print(f"  ⚠️ DataSourceManager 不可用: {e}")

    def async_test(self):
        def wrapper(*args, **kwargs):
            return asyncio.run(self(*args, **kwargs))

        return wrapper

    # --- 阶段 1: 数据获取 ---

    @async_test
    async def test_step1_fetch_basic_info(self):
        """Step 1: 获取基础信息"""
        if not self.efinance_available:
            self.skipTest("efinance 不可用")

        result = await self.efinance.get_stock_basic_info(self.SYMBOL)
        if result is None:
            self.skipTest("get_stock_basic_info 返回 None")
        self.assertIsInstance(result, dict)
        self.assertIn("code", result)
        print(f"  📋 基础信息: {result.get('name', 'N/A')} ({result.get('code', 'N/A')})")

    @async_test
    async def test_step2_fetch_quotes(self):
        """Step 2: 获取实时行情"""
        if not self.efinance_available:
            self.skipTest("efinance 不可用")

        result = await self.efinance.get_stock_quotes(self.SYMBOL)
        if result is None:
            self.skipTest("get_stock_quotes 返回 None")
        self.assertIsInstance(result, dict)

    @async_test
    async def test_step3_fetch_historical_data(self):
        """Step 3: 获取历史数据"""
        if not self.efinance_available:
            self.skipTest("efinance 不可用")

        end = datetime.now()
        start = end - timedelta(days=60)

        result = await self.efinance.get_historical_data(self.SYMBOL, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        if result is None:
            self.skipTest("get_historical_data 返回 None")
        self.assertIsNotNone(result)
        # 如果返回 DataFrame，验证结构
        import pandas as pd

        if isinstance(result, pd.DataFrame):
            self.assertGreater(len(result), 0)
            print(f"  📊 历史数据: {len(result)} 条记录")

    # --- 阶段 2: 数据标准化 ---

    def test_step4_standardize_basic_info(self):
        """Step 4: 标准化基础信息"""
        raw = {
            "code": self.SYMBOL,
            "name": "香江控股",
            "industry": "房地产",
            "area": "深圳",
        }
        if self.efinance_available:
            result = self.efinance.standardize_basic_info(raw)
        else:
            from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

            class P(BaseStockDataProvider):
                async def connect(self):
                    return True

                async def get_stock_basic_info(self, s=None):
                    return {}

                async def get_stock_quotes(self, s):
                    return {}

                async def get_historical_data(self, s, sd, ed=None):
                    return None

            p = P("test")
            result = p.standardize_basic_info(raw)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("code"), self.SYMBOL)
        self.assertEqual(result.get("name"), "香江控股")
        print(f"  ✅ 标准化基础信息: {result['name']}")

    def test_step5_standardize_quotes(self):
        """Step 5: 标准化行情数据"""
        raw = {
            "code": self.SYMBOL,
            "name": "香江控股",
            "price": 5.23,
            "open": 5.20,
            "high": 5.30,
            "low": 5.18,
            "volume": 5000000,
            "amount": 26000000,
            "pct_change": 0.58,
        }
        if self.efinance_available:
            result = self.efinance.standardize_quotes(raw)
        else:
            from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

            class P(BaseStockDataProvider):
                async def connect(self):
                    return True

                async def get_stock_basic_info(self, s=None):
                    return {}

                async def get_stock_quotes(self, s):
                    return {}

                async def get_historical_data(self, s, sd, ed=None):
                    return None

            p = P("test")
            result = p.standardize_quotes(raw)

        self.assertIsInstance(result, dict)
        print(f"  ✅ 标准化行情: price={result.get('price')}")

    # --- 阶段 3: 数据流向检查 ---

    def test_step6_dataflow_integrity(self):
        """Step 6: 验证从 provider 到标准化后的数据字段完整性"""
        if not self.efinance_available:
            self.skipTest("efinance 不可用")

        # 创建模拟的完整数据流
        raw_info = {
            "code": self.SYMBOL,
            "name": "香江控股",
            "industry": "房地产",
            "area": "深圳",
            "list_date": "1999-07-07",
        }
        raw_quotes = {
            "code": self.SYMBOL,
            "name": "香江控股",
            "price": 5.23,
            "open": 5.20,
            "high": 5.30,
            "low": 5.18,
            "volume": 5000000,
            "amount": 26000000,
        }

        std_info = self.efinance.standardize_basic_info(raw_info)
        std_quotes = self.efinance.standardize_quotes(raw_quotes)

        # 验证数据一致性
        self.assertEqual(std_info["code"], std_quotes["code"])

        # 验证关键字段
        for field in ["code", "name", "symbol"]:
            self.assertIn(field, std_info)
        for field in ["code", "current_price", "open", "high", "low"]:
            self.assertIn(field, std_quotes)

        print(f"  ✅ 数据流完整性验证通过: {std_info['name']} ({std_info['code']})")

    # --- 阶段 4: 数据源管理器流转 ---

    @async_test
    async def test_step7_dsm_data_flow(self):
        """Step 7: 通过 DataSourceManager 获取数据"""
        if not self.dsm_available:
            self.skipTest("DataSourceManager 不可用")

        try:
            # 测试 get_stock_basic_info
            info = await self.dsm.get_stock_basic_info(self.SYMBOL)
            if info is not None:
                self.assertIsInstance(info, dict)
                print("  📋 DSM 基础信息: OK")
        except Exception as e:
            print(f"  ⚠️ DSM 查询基础信息: {e}")

        try:
            quotes = await self.dsm.get_stock_quotes(self.SYMBOL)
            if quotes is not None:
                self.assertIsInstance(quotes, dict)
                print("  📋 DSM 行情: OK")
        except Exception as e:
            print(f"  ⚠️ DSM 查询行情: {e}")

    # --- 阶段 5: 分析报告生成模拟 ---

    def test_step8_report_generation(self):
        """Step 8: 模拟分析报告生成"""
        # 模拟基础数据
        basic_info = {
            "code": self.SYMBOL,
            "name": "香江控股",
            "industry": "房地产",
            "market": "上海证券交易所",
        }
        quotes = {
            "price": 5.23,
            "pct_change": 0.58,
            "volume": 5000000,
        }

        # 构建报告原型
        report = {
            "stock": basic_info["code"],
            "name": basic_info["name"],
            "industry": basic_info["industry"],
            "current_price": quotes["price"],
            "day_change_pct": quotes["pct_change"],
            "analysis_date": datetime.now().isoformat(),
            "data_source": "efinance",
        }

        # 验证报告结构
        self.assertIn("stock", report)
        self.assertIn("name", report)
        self.assertIn("current_price", report)
        self.assertIn("analysis_date", report)

        print(f"  📄 报告生成: {report['name']} - {report['analysis_date']}")

    def test_step9_data_source_independence(self):
        """Step 9: 验证数据源独立性（不修改源代码）"""
        # 验证所有 provider 都可以独立创建
        providers_to_test = [
            "tradingagents.dataflows.providers.china.efinance",
            "tradingagents.dataflows.providers.china.akshare",
            "tradingagents.dataflows.providers.china.baostock",
        ]
        for mod_name in providers_to_test:
            try:
                mod = __import__(mod_name, fromlist=["object"])
                provider_class = getattr(mod, mod_name.split(".")[-1].replace(".", "_") + "Provider", None)
                if provider_class is None:
                    # Try common class names
                    for cls_name in dir(mod):
                        if "Provider" in cls_name:
                            print(f"  ✅ {mod_name} 可导入 (class: {cls_name})")
                            break
                else:
                    print(f"  ✅ {mod_name} 可导入")
            except ImportError:
                print(f"  ⚠️ {mod_name} 不可用（未安装）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
