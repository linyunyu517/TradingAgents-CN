#!/usr/bin/env python3
"""
股票数据服务测试程序
测试MongoDB -> Tushare数据接口的完整降级机制
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from tradingagents.api.stock_api import (
        check_service_status,
        get_all_stocks,
        get_market_summary,
        get_stock_data,
        get_stock_info,
        search_stocks,
    )
    from tradingagents.dataflows.stock_data_service import StockDataService, get_stock_data_service

    SERVICES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 服务不可用: {e}")
    SERVICES_AVAILABLE = False


class TestStockDataService(unittest.TestCase):
    """股票数据服务测试类"""

    def setUp(self):
        """测试前准备"""
        if not SERVICES_AVAILABLE:
            self.skipTest("股票数据服务不可用")

        self.service = StockDataService()

    def test_service_initialization(self):
        """测试服务初始化"""
        print("\n🧪 测试服务初始化...")

        # 检查服务是否正确初始化
        self.assertIsNotNone(self.service)

        # 检查各组件的初始化状态
        print(f"  📊 数据库管理器: {'✅' if self.service.db_manager else '❌'}")
        print(f"  📡 统一数据接口: {'✅' if hasattr(self.service, 'get_stock_data') else '❌'}")

        print("  ✅ 服务初始化测试通过")

    def test_get_stock_basic_info_single(self):
        """测试获取单个股票基础信息"""
        print("\n🧪 测试获取单个股票基础信息...")

        test_codes = ["000001", "600000", "300001"]

        for code in test_codes:
            print(f"  🔍 测试股票代码: {code}")

            result = self.service.get_stock_basic_info(code)

            # 结果不应该为None
            self.assertIsNotNone(result)

            if isinstance(result, dict):
                if "error" in result:
                    print(f"    ⚠️ 获取失败: {result['error']}")
                else:
                    print(f"    ✅ 获取成功: {result.get('name', 'N/A')}")
                    # 检查必要字段
                    self.assertIn("code", result)
                    self.assertIn("name", result)
                    self.assertIn("source", result)

        print("  ✅ 单个股票信息测试完成")

    def test_get_stock_basic_info_all(self):
        """测试获取所有股票基础信息"""
        print("\n🧪 测试获取所有股票基础信息...")

        result = self.service.get_stock_basic_info()

        # 结果不应该为None
        self.assertIsNotNone(result)

        if isinstance(result, list) and len(result) > 0:
            print(f"  ✅ 获取成功: {len(result)} 只股票")

            # 检查第一个股票的字段
            first_stock = result[0]
            if "error" not in first_stock:
                self.assertIn("code", first_stock)
                self.assertIn("name", first_stock)
                print(f"  📊 示例股票: {first_stock.get('code')} - {first_stock.get('name')}")
        elif isinstance(result, dict) and "error" in result:
            print(f"  ⚠️ 获取失败: {result['error']}")
        else:
            print("  ⚠️ 未获取到数据")

        print("  ✅ 所有股票信息测试完成")

    def test_market_classification(self):
        """测试市场分类功能"""
        print("\n🧪 测试市场分类功能...")

        test_cases = [
            ("000001", "深圳", "深市主板"),
            ("600000", "上海", "沪市主板"),
            ("300001", "深圳", "创业板"),
            ("688001", "上海", "科创板"),
        ]

        for code, expected_market, expected_category in test_cases:
            market = self.service._get_market_name(code)
            category = self.service._get_stock_category(code)

            print(f"  📊 {code}: {market} - {category}")

            self.assertEqual(market, expected_market)
            self.assertEqual(category, expected_category)

        print("  ✅ 市场分类测试通过")

    def test_fallback_data(self):
        """测试降级数据功能"""
        print("\n🧪 测试降级数据功能...")

        # 测试单个股票的降级数据
        fallback_single = self.service._get_fallback_data("999999")
        self.assertIsInstance(fallback_single, dict)
        self.assertIn("code", fallback_single)
        self.assertIn("error", fallback_single)
        print(f"  📊 单个股票降级: {fallback_single['code']} - {fallback_single.get('name')}")

        # 测试所有股票的降级数据
        fallback_all = self.service._get_fallback_data()
        self.assertIsInstance(fallback_all, dict)
        self.assertIn("error", fallback_all)
        print(f"  📊 所有股票降级: {fallback_all['error']}")

        print("  ✅ 降级数据测试通过")


class TestStockAPI(unittest.TestCase):
    """股票API测试类"""

    def setUp(self):
        """测试前准备"""
        if not SERVICES_AVAILABLE:
            self.skipTest("股票API不可用")

    def test_service_status(self):
        """测试服务状态检查"""
        print("\n🧪 测试服务状态检查...")

        status = check_service_status()

        self.assertIsInstance(status, dict)
        self.assertIn("service_available", status)

        print("  📊 服务状态:")
        for key, value in status.items():
            print(f"    {key}: {value}")

        print("  ✅ 服务状态测试通过")

    def test_get_stock_info_api(self):
        """测试股票信息API"""
        print("\n🧪 测试股票信息API...")

        test_codes = ["000001", "600000", "999999"]  # 包含一个不存在的代码

        for code in test_codes:
            print(f"  🔍 测试API获取: {code}")

            result = get_stock_info(code)

            self.assertIsInstance(result, dict)

            if "error" in result:
                print(f"    ⚠️ 预期错误: {result['error']}")
            else:
                print(f"    ✅ 获取成功: {result.get('name')}")
                self.assertIn("code", result)
                self.assertIn("name", result)

        print("  ✅ 股票信息API测试完成")

    def test_search_stocks_api(self):
        """测试股票搜索API"""
        print("\n🧪 测试股票搜索API...")

        keywords = ["平安", "银行", "000001", "xyz123"]  # 包含一个不存在的关键词

        for keyword in keywords:
            print(f"  🔍 搜索关键词: '{keyword}'")

            results = search_stocks(keyword)

            self.assertIsInstance(results, list)

            if not results or (len(results) == 1 and "error" in results[0]):
                print("    ⚠️ 未找到匹配结果")
            else:
                print(f"    ✅ 找到 {len(results)} 个匹配结果")
                # 检查第一个结果
                if results and "error" not in results[0]:
                    first_result = results[0]
                    print(f"    📊 示例: {first_result.get('code')} - {first_result.get('name')}")

        print("  ✅ 股票搜索API测试完成")

    def test_market_summary_api(self):
        """测试市场概览API"""
        print("\n🧪 测试市场概览API...")

        summary = get_market_summary()

        self.assertIsInstance(summary, dict)

        if "error" in summary:
            print(f"  ⚠️ 获取失败: {summary['error']}")
        else:
            print("  ✅ 获取成功:")
            print(f"    📊 总股票数: {summary.get('total_count', 0):,}")
            print(f"    🏢 沪市股票: {summary.get('shanghai_count', 0):,}")
            print(f"    🏢 深市股票: {summary.get('shenzhen_count', 0):,}")
            print(f"    🔗 数据源: {summary.get('data_source', 'unknown')}")

            # 检查必要字段
            self.assertIn("total_count", summary)
            self.assertIn("data_source", summary)

        print("  ✅ 市场概览API测试完成")

    def test_stock_data_api(self):
        """测试股票数据API"""
        print("\n🧪 测试股票数据API...")

        # 测试获取股票历史数据
        stock_code = "000001"
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        print(f"  📊 获取 {stock_code} 从 {start_date} 到 {end_date} 的数据")

        result = get_stock_data(stock_code, start_date, end_date)

        self.assertIsInstance(result, str)

        # 检查结果是否包含预期内容
        if "❌" in result:
            print("    ⚠️ 获取失败（预期情况）")
        else:
            print(f"    ✅ 获取成功（数据长度: {len(result)} 字符）")

        print("  ✅ 股票数据API测试完成")


class TestFallbackMechanism(unittest.TestCase):
    """降级机制测试类"""

    def setUp(self):
        """测试前准备"""
        if not SERVICES_AVAILABLE:
            self.skipTest("降级机制测试不可用")

    @patch("tradingagents.dataflows.stock_data_service.DATABASE_MANAGER_AVAILABLE", False)
    def test_mongodb_unavailable_fallback(self):
        """测试MongoDB不可用时的降级"""
        print("\n🧪 测试MongoDB不可用时的降级...")

        # 创建一个新的服务实例（模拟MongoDB不可用）
        service = StockDataService()

        # 数据库管理器应该为None
        self.assertIsNone(service.db_manager)

        # 尝试获取股票信息（应该降级到Tushare数据接口）
        result = service.get_stock_basic_info("000001")

        self.assertIsNotNone(result)

        if isinstance(result, dict):
            if "error" in result:
                print(f"    ⚠️ 降级失败: {result['error']}")
            else:
                print(f"    ✅ 降级成功: {result.get('name')}")
                self.assertEqual(result.get("source"), "unified_api")

        print("  ✅ MongoDB降级测试完成")

    def test_invalid_stock_code_fallback(self):
        """测试无效股票代码的降级"""
        print("\n🧪 测试无效股票代码的降级...")

        service = StockDataService()

        # 测试明显无效的股票代码
        invalid_codes = ["999999", "INVALID", "123456"]

        for code in invalid_codes:
            print(f"  🔍 测试无效代码: {code}")

            result = service.get_stock_basic_info(code)

            self.assertIsNotNone(result)

            if isinstance(result, dict):
                # 应该包含错误信息或降级数据
                if "error" in result:
                    print("    ✅ 正确识别无效代码")
                else:
                    print(f"    ⚠️ 返回了数据: {result.get('name')}")

        print("  ✅ 无效代码降级测试完成")


def run_comprehensive_test():
    """运行综合测试"""
    print("🚀 股票数据服务综合测试")
    print("=" * 60)

    if not SERVICES_AVAILABLE:
        print("❌ 服务不可用，无法运行测试")
        return None

    # 创建测试套件
    test_suite = unittest.TestSuite()

    # 添加测试用例
    test_suite.addTest(unittest.makeSuite(TestStockDataService))
    test_suite.addTest(unittest.makeSuite(TestStockAPI))
    test_suite.addTest(unittest.makeSuite(TestFallbackMechanism))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # 输出测试结果摘要
    print("\n" + "=" * 60)
    print("📊 测试结果摘要:")
    print(f"  ✅ 成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  ❌ 失败: {len(result.failures)}")
    print(f"  💥 错误: {len(result.errors)}")
    print(f"  ⏭️ 跳过: {len(result.skipped)}")

    if result.failures:
        print("\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")

    if result.errors:
        print("\n💥 错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")

    # 总体评估
    if result.wasSuccessful():
        print("\n🎉 所有测试通过！股票数据服务工作正常")
    else:
        print("\n⚠️ 部分测试失败，请检查相关配置")

    return result.wasSuccessful()


def run_manual_test():
    """运行手动测试（用于调试）"""
    print("🔧 手动测试模式")
    print("=" * 40)

    if not SERVICES_AVAILABLE:
        print("❌ 服务不可用")
        return

    try:
        # 测试服务状态
        print("\n1. 检查服务状态:")
        status = check_service_status()
        for key, value in status.items():
            print(f"   {key}: {value}")

        # 测试获取股票信息
        print("\n2. 获取股票信息:")
        stock_info = get_stock_info("000001")
        if "error" in stock_info:
            print(f"   错误: {stock_info['error']}")
        else:
            print(f"   成功: {stock_info.get('code')} - {stock_info.get('name')}")

        # 测试搜索功能
        print("\n3. 搜索股票:")
        results = search_stocks("平安")
        if results and "error" not in results[0]:
            print(f"   找到 {len(results)} 只股票")
            for i, stock in enumerate(results[:3], 1):
                print(f"   {i}. {stock.get('code')} - {stock.get('name')}")
        else:
            print("   未找到匹配的股票")

        # 测试市场概览
        print("\n4. 市场概览:")
        summary = get_market_summary()
        if "error" in summary:
            print(f"   错误: {summary['error']}")
        else:
            print(f"   总股票数: {summary.get('total_count', 0):,}")
            print(f"   数据源: {summary.get('data_source')}")

        print("\n✅ 手动测试完成")

    except Exception as e:
        print(f"\n❌ 手动测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="股票数据服务测试程序")
    parser.add_argument("--manual", action="store_true", help="运行手动测试模式")
    parser.add_argument("--comprehensive", action="store_true", help="运行综合测试")

    args = parser.parse_args()

    if args.manual:
        run_manual_test()
    elif args.comprehensive:
        run_comprehensive_test()
    else:
        # 默认运行综合测试
        print("💡 提示: 使用 --manual 运行手动测试，--comprehensive 运行综合测试")
        print("默认运行综合测试...\n")
        run_comprehensive_test()
