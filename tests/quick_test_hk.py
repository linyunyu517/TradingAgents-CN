"""
快速测试港股功能
"""

import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_stock_recognition():
    """测试股票识别"""
    print("🧪 测试股票识别...")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        test_cases = [
            "0700.HK",  # 腾讯港股
            "000001",  # 平安银行A股
            "AAPL",  # 苹果美股
        ]

        for ticker in test_cases:
            info = StockUtils.get_market_info(ticker)
            print(f"  {ticker}: {info['market_name']} ({info['currency_symbol']})")

        print("✅ 股票识别测试完成")
        return True

    except Exception as e:
        print(f"❌ 股票识别测试失败: {e}")
        return False


def test_akshare_basic():
    """测试AKShare基本功能"""
    print("\n🧪 测试AKShare基本功能...")

    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider

        provider = get_akshare_provider()

        if provider.connected:
            print("  ✅ AKShare连接成功")

            # 测试港股代码标准化
            test_symbol = "0700.HK"
            normalized = provider._normalize_hk_symbol_for_akshare(test_symbol)
            print(f"  港股代码标准化: {test_symbol} -> {normalized}")

            return True
        print("  ⚠️ AKShare未连接")
        return False

    except Exception as e:
        print(f"❌ AKShare基本功能测试失败: {e}")
        return False


def test_unified_interface():
    """测试统一接口"""
    print("\n🧪 测试统一接口...")

    try:
        from tradingagents.dataflows.interface import get_hk_stock_info_unified

        symbol = "0700.HK"
        print(f"  获取 {symbol} 信息...")

        info = get_hk_stock_info_unified(symbol)

        if info and "symbol" in info:
            print(f"    代码: {info['symbol']}")
            print(f"    名称: {info['name']}")
            print(f"    货币: {info['currency']}")
            print(f"    数据源: {info['source']}")
            print("  ✅ 统一接口测试成功")
            return True
        print("  ❌ 统一接口测试失败")
        return False

    except Exception as e:
        print(f"❌ 统一接口测试失败: {e}")
        return False


def main():
    """运行快速测试"""
    print("🇭🇰 港股功能快速测试")
    print("=" * 30)

    tests = [test_stock_recognition, test_akshare_basic, test_unified_interface]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")

    print("\n" + "=" * 30)
    print(f"🇭🇰 测试完成: {passed}/{total} 通过")

    if passed >= 2:
        print("🎉 港股功能基本正常！")
    else:
        print("⚠️ 港股功能可能有问题")


if __name__ == "__main__":
    main()
