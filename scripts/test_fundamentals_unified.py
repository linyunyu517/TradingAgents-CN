#!/usr/bin/env python
"""
测试基本面数据统一功能

验证 DataSourceManager 是否正确将基本面数据纳入统一管理
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager
from tradingagents.dataflows.interface import get_china_stock_fundamentals_tushare
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def test_fundamentals_from_mongodb():
    """测试从 MongoDB 获取基本面数据"""
    print("\n" + "=" * 70)
    print("🧪 测试从 MongoDB 获取基本面数据")
    print("=" * 70)

    # 创建数据源管理器
    print("\n📊 创建数据源管理器...")
    manager = DataSourceManager()

    # 检查当前数据源
    print(f"\n🔍 当前数据源: {manager.current_source.value}")
    print(f"🔍 MongoDB缓存启用: {manager.use_mongodb_cache}")

    if not manager.use_mongodb_cache:
        print("\n⚠️ MongoDB 缓存未启用，跳过 MongoDB 测试")
        return

    # 测试获取基本面数据
    print("\n" + "-" * 70)
    print("📈 测试获取基本面数据")
    print("-" * 70)

    test_symbol = "000001"

    print(f"\n📊 测试股票: {test_symbol}")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print("\n" + "-" * 70)

    # 获取基本面数据
    result = manager.get_fundamentals_data(test_symbol)

    # 显示结果摘要
    print("\n" + "-" * 70)
    print("📊 基本面数据获取结果")
    print("-" * 70)

    if result and "❌" not in result:
        print("✅ 基本面数据获取成功")
        print(f"📏 数据长度: {len(result)} 字符")
        print(f"🔍 数据来源: {manager.current_source.value}")

        # 显示前500个字符
        print("\n📄 数据预览（前500字符）:")
        print(result[:500])
        if len(result) > 500:
            print("...")
    else:
        print("❌ 基本面数据获取失败")
        print(f"📄 错误信息: {result[:200]}")


def test_fundamentals_from_tushare():
    """测试从 Tushare 获取基本面数据"""
    print("\n" + "=" * 70)
    print("🧪 测试从 Tushare 获取基本面数据")
    print("=" * 70)

    # 创建数据源管理器
    print("\n📊 创建数据源管理器...")
    manager = DataSourceManager()

    # 临时切换到 Tushare 数据源
    if ChinaDataSource.TUSHARE in manager.available_sources:
        original_source = manager.current_source
        manager.current_source = ChinaDataSource.TUSHARE

        print(f"\n🔄 临时切换数据源: {original_source.value} → {manager.current_source.value}")

        # 测试获取基本面数据
        test_symbol = "000001"

        print(f"\n📊 测试股票: {test_symbol}")
        print(f"🔍 当前数据源: {manager.current_source.value}")
        print("\n" + "-" * 70)

        # 获取基本面数据
        result = manager.get_fundamentals_data(test_symbol)

        # 显示结果摘要
        print("\n" + "-" * 70)
        print("📊 基本面数据获取结果")
        print("-" * 70)

        if result and "❌" not in result:
            print("✅ 基本面数据获取成功")
            print(f"📏 数据长度: {len(result)} 字符")
            print(f"🔍 数据来源: {manager.current_source.value}")

            # 显示前500个字符
            print("\n📄 数据预览（前500字符）:")
            print(result[:500])
            if len(result) > 500:
                print("...")
        else:
            print("❌ 基本面数据获取失败")
            print(f"📄 错误信息: {result[:200]}")

        # 恢复原数据源
        manager.current_source = original_source
        print(f"\n🔄 恢复数据源: {manager.current_source.value}")
    else:
        print("\n⚠️ Tushare 数据源不可用，跳过测试")


def test_fundamentals_fallback():
    """测试基本面数据降级机制"""
    print("\n" + "=" * 70)
    print("🧪 测试基本面数据降级机制")
    print("=" * 70)

    manager = DataSourceManager()

    # 测试一个可能在 MongoDB 中不存在的股票
    test_symbol = "688001"  # 科创板股票

    print(f"\n📊 测试股票: {test_symbol}")
    print("📅 预期行为: MongoDB 无数据 → 自动降级到 Tushare/AKShare")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print("\n" + "-" * 70)

    result = manager.get_fundamentals_data(test_symbol)

    print("\n" + "-" * 70)
    print("📊 降级测试结果")
    print("-" * 70)

    if result and "❌" not in result:
        print("✅ 降级成功，从备用数据源获取到基本面数据")
        print(f"🔍 最终数据来源: {manager.current_source.value}")
        print(f"📏 数据长度: {len(result)} 字符")

        # 显示前300个字符
        print("\n📄 数据预览（前300字符）:")
        print(result[:300])
        if len(result) > 300:
            print("...")
    else:
        print("⚠️ 所有数据源都无法获取基本面数据")
        print(f"📄 结果: {result[:200]}")


def test_interface_function():
    """测试统一接口函数"""
    print("\n" + "=" * 70)
    print("🧪 测试统一接口函数")
    print("=" * 70)

    print("\n📝 测试说明:")
    print("   验证 get_china_stock_fundamentals_tushare() 是否使用新的统一接口")

    test_symbol = "000001"

    print(f"\n📊 测试股票: {test_symbol}")
    print("🔍 调用接口: get_china_stock_fundamentals_tushare()")
    print("\n" + "-" * 70)

    # 调用接口函数
    result = get_china_stock_fundamentals_tushare(test_symbol)

    print("\n" + "-" * 70)
    print("📊 接口调用结果")
    print("-" * 70)

    if result and "❌" not in result:
        print("✅ 接口调用成功")
        print(f"📏 数据长度: {len(result)} 字符")

        # 显示前500个字符
        print("\n📄 数据预览（前500字符）:")
        print(result[:500])
        if len(result) > 500:
            print("...")
    else:
        print("❌ 接口调用失败")
        print(f"📄 错误信息: {result[:200]}")


def test_data_source_priority():
    """测试数据源优先级"""
    print("\n" + "=" * 70)
    print("🧪 测试数据源优先级")
    print("=" * 70)

    manager = DataSourceManager()

    print("\n📊 基本面数据源优先级:")
    if manager.use_mongodb_cache and ChinaDataSource.MONGODB in manager.available_sources:
        print("   1. ✅ MongoDB（最高优先级）- 财务数据")
        print("   2. ✅ Tushare - 基本面数据")
        print("   3. ✅ AKShare - 生成分析")
        print("   4. ✅ 生成分析（兜底）")

        print("\n📝 数据获取流程:")
        print("   1. 首先尝试从 MongoDB 获取财务数据")
        print("   2. 如果 MongoDB 没有数据，自动降级到 Tushare")
        print("   3. 如果 Tushare 失败，继续降级到 AKShare")
        print("   4. 如果所有数据源都失败，生成基本分析")
    else:
        print("   ⚠️ MongoDB 未启用，使用传统数据源优先级:")
        print(f"   1. {manager.default_source.value}（默认）")
        print("   2. 其他可用数据源")


if __name__ == "__main__":
    try:
        print("\n" + "=" * 70)
        print("🚀 基本面数据统一功能测试")
        print("=" * 70)

        print("\n📝 测试说明:")
        print("   本测试验证基本面数据是否被正确纳入 DataSourceManager")
        print("   统一管理，支持多数据源和自动降级")
        print("\n💡 配置要求:")
        print("   - TA_USE_APP_CACHE=true  # 启用 MongoDB 缓存")
        print("   - MongoDB 服务正常运行")
        print("   - 数据库中有财务数据")

        # 测试数据源优先级
        test_data_source_priority()

        # 测试从 MongoDB 获取
        test_fundamentals_from_mongodb()

        # 测试从 Tushare 获取
        test_fundamentals_from_tushare()

        # 测试降级机制
        test_fundamentals_fallback()

        # 测试统一接口
        test_interface_function()

        print("\n" + "=" * 70)
        print("✅ 所有测试完成")
        print("=" * 70)

        print("\n💡 提示：检查上面的日志，确认:")
        print("   1. 基本面数据是否从 MongoDB 优先获取")
        print("   2. 数据获取日志中是否显示 [数据来源: mongodb]")
        print("   3. 降级机制是否正常工作")
        print("   4. 统一接口是否正确调用")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
