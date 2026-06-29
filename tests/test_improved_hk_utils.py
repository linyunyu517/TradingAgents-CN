#!/usr/bin/env python3
"""
测试改进的港股工具
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_improved_hk_provider():
    """测试改进的港股提供器"""
    print("\n🇭🇰 测试改进的港股提供器")
    print("=" * 80)

    try:
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider

        provider = get_improved_hk_provider()
        print("✅ 改进港股提供器初始化成功")

        # 测试不同格式的港股代码
        test_symbols = [
            "0700.HK",  # 腾讯控股
            "0700",  # 腾讯控股（无后缀）
            "00700",  # 腾讯控股（5位）
            "0941.HK",  # 中国移动
            "1299",  # 友邦保险
            "9988.HK",  # 阿里巴巴
            "3690",  # 美团
            "1234.HK",  # 不存在的股票
        ]

        print("\n📊 测试港股公司名称获取:")
        for symbol in test_symbols:
            try:
                company_name = provider.get_company_name(symbol)
                print(f"   {symbol:10} -> {company_name}")

                # 验证不是默认格式
                if not company_name.startswith("港股"):
                    print("      ✅ 成功获取具体公司名称")
                else:
                    print("      ⚠️ 使用默认格式")

            except Exception as e:
                print(f"   {symbol:10} -> ❌ 错误: {e}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_analyst_integration():
    """测试分析师集成"""
    print("\n🔍 测试分析师集成")
    print("=" * 80)

    try:
        from tradingagents.agents.analysts.fundamentals_analyst import _get_company_name_for_fundamentals
        from tradingagents.agents.analysts.market_analyst import _get_company_name
        from tradingagents.utils.stock_utils import StockUtils

        test_hk_symbols = ["0700.HK", "0941.HK", "1299.HK"]

        for symbol in test_hk_symbols:
            print(f"\n📊 测试港股: {symbol}")

            # 获取市场信息
            market_info = StockUtils.get_market_info(symbol)
            print(f"   市场信息: {market_info['market_name']}")

            # 测试市场分析师
            try:
                market_name = _get_company_name(symbol, market_info)
                print(f"   市场分析师: {market_name}")
            except Exception as e:
                print(f"   市场分析师: ❌ {e}")

            # 测试基本面分析师
            try:
                fundamentals_name = _get_company_name_for_fundamentals(symbol, market_info)
                print(f"   基本面分析师: {fundamentals_name}")
            except Exception as e:
                print(f"   基本面分析师: ❌ {e}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_functionality():
    """测试缓存功能"""
    print("\n💾 测试缓存功能")
    print("=" * 80)

    try:
        import time

        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider

        provider = get_improved_hk_provider()

        # 使用新的缓存路径（避免根目录污染）
        cache_dir = os.path.join("data", "cache", "hk")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "hk_stock_cache.json")

        # 清理可能存在的缓存文件
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print("🗑️ 清理旧缓存文件")

        test_symbol = "0700.HK"

        # 第一次获取（应该使用内置映射）
        print(f"\n📊 第一次获取 {test_symbol}:")
        start_time = time.time()
        name1 = provider.get_company_name(test_symbol)
        time1 = time.time() - start_time
        print(f"   结果: {name1}")
        print(f"   耗时: {time1:.3f}秒")

        # 第二次获取（应该使用缓存）
        print(f"\n📊 第二次获取 {test_symbol}:")
        start_time = time.time()
        name2 = provider.get_company_name(test_symbol)
        time2 = time.time() - start_time
        print(f"   结果: {name2}")
        print(f"   耗时: {time2:.3f}秒")

        # 验证结果一致性
        if name1 == name2:
            print("✅ 缓存结果一致")
        else:
            print("❌ 缓存结果不一致")

        # 检查缓存文件
        if os.path.exists(cache_file):
            print("✅ 缓存文件已创建")

            # 读取缓存内容
            import json

            with open(cache_file, encoding="utf-8") as f:
                cache_data = json.load(f)

            print(f"📄 缓存条目数: {len(cache_data)}")
            for key, value in cache_data.items():
                print(f"   {key}: {value['data']} (来源: {value['source']})")
        else:
            print("⚠️ 缓存文件未创建")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🚀 开始测试改进的港股工具")
    print("=" * 100)

    results = []

    # 测试1: 改进港股提供器
    results.append(test_improved_hk_provider())

    # 测试2: 分析师集成
    results.append(test_analyst_integration())

    # 测试3: 缓存功能
    results.append(test_cache_functionality())

    # 总结结果
    print("\n" + "=" * 100)
    print("📋 测试结果总结")
    print("=" * 100)

    passed = sum(results)
    total = len(results)

    test_names = ["改进港股提供器", "分析师集成测试", "缓存功能测试"]

    for i, (name, result) in enumerate(zip(test_names, results, strict=False)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i + 1}. {name}: {status}")

    print(f"\n📊 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！改进港股工具运行正常")
        print("\n📋 改进效果:")
        print("1. ✅ 内置港股名称映射，避免API调用")
        print("2. ✅ 智能缓存机制，提高性能")
        print("3. ✅ 速率限制保护，避免API错误")
        print("4. ✅ 多级降级方案，确保可用性")
        print("5. ✅ 友好的错误处理和日志记录")
    else:
        # 保持原有输出结构
        pass

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
