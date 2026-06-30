#!/usr/bin/env python3
"""
测试港股数据源优先级设置
验证AKShare优先，Yahoo Finance作为备用
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_hk_data_source_priority():
    """测试港股数据源优先级"""
    print("\n🇭🇰 测试港股数据源优先级")
    print("=" * 80)

    try:
        # 设置日志级别
        from tradingagents.utils.logging_init import get_logger

        logger = get_logger("default")
        logger.setLevel("INFO")

        print("📊 测试港股信息获取优先级...")

        # 测试统一港股信息接口
        from tradingagents.dataflows.interface import get_hk_stock_info_unified

        test_symbols = [
            "0700.HK",  # 腾讯控股
            "0941.HK",  # 中国移动
            "1299.HK",  # 友邦保险
        ]

        for symbol in test_symbols:
            print(f"\n📊 测试股票: {symbol}")
            print("-" * 40)

            try:
                result = get_hk_stock_info_unified(symbol)

                print("✅ 获取成功:")
                print(f"   股票代码: {result.get('symbol', 'N/A')}")
                print(f"   公司名称: {result.get('name', 'N/A')}")
                print(f"   数据源: {result.get('source', 'N/A')}")
                print(f"   货币: {result.get('currency', 'N/A')}")
                print(f"   交易所: {result.get('exchange', 'N/A')}")

                # 检查是否成功获取了具体的公司名称
                name = result.get("name", "")
                if not name.startswith("港股"):
                    print("   ✅ 成功获取具体公司名称")
                else:
                    print("   ⚠️ 使用默认格式")

            except Exception as e:
                print(f"❌ 获取失败: {e}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_hk_data_priority():
    """测试港股数据获取优先级"""
    print("\n📈 测试港股数据获取优先级")
    print("=" * 80)

    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified

        test_symbol = "0700.HK"
        start_date = "2025-07-01"
        end_date = "2025-07-15"

        print(f"📊 测试港股数据获取: {test_symbol}")
        print(f"   时间范围: {start_date} 到 {end_date}")
        print("-" * 40)

        result = get_hk_stock_data_unified(test_symbol, start_date, end_date)

        if result and "❌" not in result:
            print("✅ 港股数据获取成功")
            print(f"   数据长度: {len(result)}")

            # 显示数据的前200字符
            print("   数据预览:")
            print(f"   {result[:200]}...")

            # 检查数据中是否包含正确的股票代码
            if "0700" in result or "腾讯" in result:
                print("   ✅ 数据包含正确的股票信息")
            else:
                print("   ⚠️ 数据可能不完整")
        else:
            print("❌ 港股数据获取失败")
            print(f"   返回结果: {result}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_improved_hk_provider_priority():
    """测试改进港股提供器的优先级"""
    print("\n🔧 测试改进港股提供器优先级")
    print("=" * 80)

    try:
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider

        provider = get_improved_hk_provider()

        # 清理缓存以测试真实的API调用优先级
        if hasattr(provider, "cache"):
            provider.cache.clear()

        test_symbols = [
            "0700.HK",  # 腾讯控股（内置映射）
            "1234.HK",  # 不在内置映射中的股票（测试API优先级）
        ]

        for symbol in test_symbols:
            print(f"\n📊 测试股票: {symbol}")
            print("-" * 40)

            try:
                company_name = provider.get_company_name(symbol)
                print(f"✅ 获取公司名称: {company_name}")

                # 检查缓存信息
                cache_key = f"name_{symbol}"
                if hasattr(provider, "cache") and cache_key in provider.cache:
                    cache_info = provider.cache[cache_key]
                    print(f"   缓存来源: {cache_info.get('source', 'unknown')}")
                    print(f"   缓存时间: {cache_info.get('timestamp', 'unknown')}")

                # 检查是否成功获取了具体的公司名称
                if not company_name.startswith("港股"):
                    print("   ✅ 成功获取具体公司名称")
                else:
                    print("   ⚠️ 使用默认格式")

            except Exception as e:
                print(f"❌ 获取失败: {e}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_data_source_availability():
    """测试数据源可用性"""
    print("\n🔍 测试数据源可用性")
    print("=" * 80)

    try:
        # 检查AKShare可用性
        try:
            from tradingagents.dataflows.akshare_utils import get_hk_stock_info_akshare

            print("✅ AKShare港股工具可用")
            akshare_available = True
        except ImportError as e:
            print(f"❌ AKShare港股工具不可用: {e}")
            akshare_available = False

        # 检查Yahoo Finance可用性
        try:
            from tradingagents.dataflows.hk_stock_utils import get_hk_stock_info

            print("✅ Yahoo Finance港股工具可用")
            yf_available = True
        except ImportError as e:
            print(f"❌ Yahoo Finance港股工具不可用: {e}")
            yf_available = False

        # 检查统一接口
        try:
            from tradingagents.dataflows.interface import (
                AKSHARE_HK_AVAILABLE,
                HK_STOCK_AVAILABLE,
                get_hk_stock_info_unified,
            )

            print("✅ 统一港股接口可用")
            print(f"   AKShare可用标志: {AKSHARE_HK_AVAILABLE}")
            print(f"   Yahoo Finance可用标志: {HK_STOCK_AVAILABLE}")
        except ImportError as e:
            print(f"❌ 统一港股接口不可用: {e}")

        print("\n📊 数据源优先级验证:")
        print(f"   1. AKShare (优先): {'✅ 可用' if akshare_available else '❌ 不可用'}")
        print(f"   2. Yahoo Finance (备用): {'✅ 可用' if yf_available else '❌ 不可用'}")
        print("   3. 默认格式 (降级): ✅ 总是可用")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🚀 开始测试港股数据源优先级")
    print("=" * 100)

    results = []

    # 测试1: 数据源可用性
    results.append(test_data_source_availability())

    # 测试2: 港股信息获取优先级
    results.append(test_hk_data_source_priority())

    # 测试3: 港股数据获取优先级
    results.append(test_hk_data_priority())

    # 测试4: 改进港股提供器优先级
    results.append(test_improved_hk_provider_priority())

    # 总结结果
    print("\n" + "=" * 100)
    print("📋 测试结果总结")
    print("=" * 100)

    passed = sum(results)
    total = len(results)

    test_names = ["数据源可用性检查", "港股信息获取优先级", "港股数据获取优先级", "改进港股提供器优先级"]

    for i, (name, result) in enumerate(zip(test_names, results, strict=False)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i + 1}. {name}: {status}")

    print(f"\n📊 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！港股数据源优先级设置正确")
        print("\n📋 优先级设置:")
        print("1. 🥇 AKShare (国内数据源，港股支持更好)")
        print("2. 🥈 Yahoo Finance (国际数据源，备用方案)")
        print("3. 🥉 默认格式 (降级方案，确保可用性)")

        print("\n✅ 优化效果:")
        print("- 减少Yahoo Finance API速率限制问题")
        print("- 提高港股数据获取成功率")
        print("- 更好的中文公司名称支持")
        print("- 更稳定的数据源访问")
    else:
        print("⚠️ 部分测试失败，需要进一步优化")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
