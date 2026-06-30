#!/usr/bin/env python3
"""
缓存优化功能测试
测试美股和A股数据的缓存策略和性能
"""

import os
import sys
import time
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)


def test_cache_manager():
    """测试缓存管理器基本功能"""
    print("🧪 测试缓存管理器...")

    try:
        from tradingagents.dataflows.cache_manager import get_cache

        cache = get_cache()
        print("✅ 缓存管理器初始化成功")
        print(f"📁 缓存目录: {cache.cache_dir}")

        # 测试缓存配置
        if hasattr(cache, "cache_config"):
            print("⚙️ 缓存配置:")
            for config_name, config_data in cache.cache_config.items():
                print(f"  - {config_name}: TTL={config_data.get('ttl_hours')}h, 描述={config_data.get('description')}")

        # 测试缓存统计
        stats = cache.get_cache_stats()
        print(f"📊 缓存统计: {stats}")

        return True

    except Exception as e:
        print(f"❌ 缓存管理器测试失败: {e}")
        return False


def test_us_stock_cache():
    """测试美股数据缓存"""
    print("\n🇺🇸 测试美股数据缓存...")

    try:
        from tradingagents.dataflows.optimized_us_data import get_optimized_us_data_provider

        provider = get_optimized_us_data_provider()
        symbol = "AAPL"
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        print(f"📈 测试股票: {symbol} ({start_date} 到 {end_date})")

        # 第一次调用（应该从API获取）
        print("🌐 第一次调用（从API获取）...")
        start_time = time.time()
        result1 = provider.get_stock_data(symbol, start_date, end_date)
        time1 = time.time() - start_time
        print(f"⏱️ 第一次调用耗时: {time1:.2f}秒")

        # 第二次调用（应该从缓存获取）
        print("⚡ 第二次调用（从缓存获取）...")
        start_time = time.time()
        result2 = provider.get_stock_data(symbol, start_date, end_date)
        time2 = time.time() - start_time
        print(f"⏱️ 第二次调用耗时: {time2:.2f}秒")

        # 验证结果一致性
        if result1 == result2:
            print("✅ 缓存数据一致性验证通过")
        else:
            print("⚠️ 缓存数据不一致")

        # 性能提升
        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"🚀 缓存性能提升: {improvement:.1f}%")

        return True

    except Exception as e:
        print(f"❌ 美股缓存测试失败: {e}")
        return False


def test_china_stock_cache():
    """测试A股数据缓存"""
    print("\n🇨🇳 测试A股数据缓存...")

    try:
        from tradingagents.dataflows.optimized_china_data import get_optimized_china_data_provider

        provider = get_optimized_china_data_provider()
        symbol = "000001"
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        print(f"📈 测试股票: {symbol} ({start_date} 到 {end_date})")

        # 第一次调用（应该从API获取）
        print("🌐 第一次调用（从Tushare数据接口获取）...")
        start_time = time.time()
        result1 = provider.get_stock_data(symbol, start_date, end_date)
        time1 = time.time() - start_time
        print(f"⏱️ 第一次调用耗时: {time1:.2f}秒")

        # 第二次调用（应该从缓存获取）
        print("⚡ 第二次调用（从缓存获取）...")
        start_time = time.time()
        result2 = provider.get_stock_data(symbol, start_date, end_date)
        time2 = time.time() - start_time
        print(f"⏱️ 第二次调用耗时: {time2:.2f}秒")

        # 验证结果一致性
        if result1 == result2:
            print("✅ 缓存数据一致性验证通过")
        else:
            print("⚠️ 缓存数据不一致")

        # 性能提升
        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"🚀 缓存性能提升: {improvement:.1f}%")

        # 测试基本面数据缓存
        print("\n📊 测试A股基本面数据缓存...")
        start_time = time.time()
        fundamentals1 = provider.get_fundamentals_data(symbol)
        time1 = time.time() - start_time
        print(f"⏱️ 基本面数据第一次调用耗时: {time1:.2f}秒")

        start_time = time.time()
        fundamentals2 = provider.get_fundamentals_data(symbol)
        time2 = time.time() - start_time
        print(f"⏱️ 基本面数据第二次调用耗时: {time2:.2f}秒")

        if fundamentals1 == fundamentals2:
            print("✅ 基本面数据缓存一致性验证通过")

        return True

    except Exception as e:
        print(f"❌ A股缓存测试失败: {e}")
        return False


def test_cache_ttl():
    """测试缓存TTL功能"""
    print("\n⏰ 测试缓存TTL功能...")

    try:
        from tradingagents.dataflows.cache_manager import get_cache

        cache = get_cache()

        # 测试美股缓存TTL
        us_cache_key = cache.find_cached_stock_data(
            symbol="AAPL",
            start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
            data_source="yfinance",
        )

        if us_cache_key:
            is_valid = cache.is_cache_valid(us_cache_key, symbol="AAPL", data_type="stock_data")
            print(f"📈 美股缓存有效性: {'✅ 有效' if is_valid else '❌ 过期'}")

        # 测试A股缓存TTL
        china_cache_key = cache.find_cached_stock_data(
            symbol="000001",
            start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
            data_source="tdx",
        )

        if china_cache_key:
            is_valid = cache.is_cache_valid(china_cache_key, symbol="000001", data_type="stock_data")
            print(f"📈 A股缓存有效性: {'✅ 有效' if is_valid else '❌ 过期'}")

        return True

    except Exception as e:
        print(f"❌ 缓存TTL测试失败: {e}")
        return False


def test_cache_cleanup():
    """测试缓存清理功能"""
    print("\n🧹 测试缓存清理功能...")

    try:
        from tradingagents.dataflows.cache_manager import get_cache

        cache = get_cache()

        # 获取清理前的统计
        stats_before = cache.get_cache_stats()
        print(f"📊 清理前统计: {stats_before}")

        # 执行清理（清理7天前的缓存）
        print("🧹 执行缓存清理...")
        cache.clear_old_cache(max_age_days=7)

        # 获取清理后的统计
        stats_after = cache.get_cache_stats()
        print(f"📊 清理后统计: {stats_after}")

        # 计算清理效果
        files_removed = stats_before["total_files"] - stats_after["total_files"]
        size_freed = stats_before["total_size_mb"] - stats_after["total_size_mb"]

        print(f"🗑️ 清理结果: 删除 {files_removed} 个文件，释放 {size_freed:.2f} MB 空间")

        return True

    except Exception as e:
        print(f"❌ 缓存清理测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始缓存优化功能测试")
    print("=" * 50)

    test_results = []

    # 测试缓存管理器
    test_results.append(("缓存管理器", test_cache_manager()))

    # 测试美股缓存
    test_results.append(("美股数据缓存", test_us_stock_cache()))

    # 测试A股缓存
    test_results.append(("A股数据缓存", test_china_stock_cache()))

    # 测试缓存TTL
    test_results.append(("缓存TTL", test_cache_ttl()))

    # 测试缓存清理
    test_results.append(("缓存清理", test_cache_cleanup()))

    # 输出测试结果
    print("\n" + "=" * 50)
    print("📋 测试结果汇总:")

    passed = 0
    total = len(test_results)

    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有缓存优化功能测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查系统配置")


if __name__ == "__main__":
    main()
