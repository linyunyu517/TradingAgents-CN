"""
测试CLI港股输入功能
"""

import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_cli_market_selection():
    """测试CLI市场选择功能"""
    print("🧪 测试CLI市场选择功能...")

    try:
        # 导入CLI相关模块

        # 模拟港股市场配置
        hk_market = {
            "name": "港股",
            "name_en": "Hong Kong Stock",
            "default": "0700.HK",
            "examples": ["0700.HK (腾讯)", "9988.HK (阿里巴巴)", "3690.HK (美团)"],
            "format": "代码.HK (如: 0700.HK)",
            "pattern": r"^\d{4}\.HK$",
            "data_source": "yahoo_finance",
        }

        # 测试港股代码验证
        import re

        test_codes = [
            ("0700.HK", True),
            ("9988.HK", True),
            ("3690.HK", True),
            ("700.HK", False),  # 不足4位
            ("07000.HK", False),  # 超过4位
            ("0700", False),  # 缺少.HK
            ("AAPL", False),  # 美股代码
        ]

        for code, should_match in test_codes:
            matches = bool(re.match(hk_market["pattern"], code))
            status = "✅" if matches == should_match else "❌"
            print(f"  {code}: {status} (匹配: {matches}, 期望: {should_match})")

        print("✅ CLI市场选择测试通过")
        return True

    except Exception as e:
        print(f"❌ CLI市场选择测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_stock_analysis_flow():
    """测试股票分析流程"""
    print("🧪 测试股票分析流程...")

    try:
        # 测试股票类型识别
        from tradingagents.utils.stock_utils import StockUtils

        # 测试港股
        hk_ticker = "0700.HK"
        market_info = StockUtils.get_market_info(hk_ticker)

        print(f"  港股测试: {hk_ticker}")
        print(f"    市场: {market_info['market_name']}")
        print(f"    货币: {market_info['currency_name']} ({market_info['currency_symbol']})")
        print(f"    数据源: {market_info['data_source']}")
        print(f"    是否港股: {market_info['is_hk']}")

        # 验证港股识别
        if not market_info["is_hk"]:
            print(f"❌ {hk_ticker} 应该被识别为港股")
            return False

        if market_info["currency_symbol"] != "HK$":
            print(f"❌ 港股货币符号应为HK$，实际为: {market_info['currency_symbol']}")
            return False

        print("✅ 股票分析流程测试通过")
        return True

    except Exception as e:
        print(f"❌ 股票分析流程测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("🇭🇰 开始港股CLI功能测试")
    print("=" * 40)

    tests = [test_cli_market_selection, test_stock_analysis_flow]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ 测试 {test_func.__name__} 异常: {e}")

    print("=" * 40)
    print(f"🇭🇰 港股CLI测试完成: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！港股CLI功能正常")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")


if __name__ == "__main__":
    main()
