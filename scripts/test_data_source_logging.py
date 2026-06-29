#!/usr/bin/env python
"""
测试数据来源日志功能

验证在获取数据时是否正确打印数据来源信息
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tradingagents.dataflows.optimized_us_data import get_us_stock_data_cached

from tradingagents.dataflows.optimized_china_data import get_china_stock_data_cached
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def test_china_stock_data():
    """测试A股数据获取的日志"""
    print("\n" + "=" * 60)
    print("🧪 测试A股数据获取 - 数据来源日志")
    print("=" * 60)

    # 测试股票
    test_symbol = "000001"
    start_date = "2025-09-01"
    end_date = "2025-09-30"

    print(f"\n📊 测试股票: {test_symbol}")
    print(f"📅 日期范围: {start_date} 到 {end_date}")
    print("\n" + "-" * 60)
    print("第一次调用（应该从API或MongoDB获取）:")
    print("-" * 60)

    # 第一次调用 - 应该从API或MongoDB获取
    data1 = get_china_stock_data_cached(
        symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=False,
    )

    print(f"\n✅ 获取到数据长度: {len(data1)} 字符")

    print("\n" + "-" * 60)
    print("第二次调用（应该从缓存获取）:")
    print("-" * 60)

    # 第二次调用 - 应该从缓存获取
    data2 = get_china_stock_data_cached(
        symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=False,
    )

    print(f"\n✅ 获取到数据长度: {len(data2)} 字符")

    print("\n" + "-" * 60)
    print("第三次调用（强制刷新，应该从API获取）:")
    print("-" * 60)

    # 第三次调用 - 强制刷新
    data3 = get_china_stock_data_cached(
        symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=True,
    )

    print(f"\n✅ 获取到数据长度: {len(data3)} 字符")


def test_us_stock_data():
    """测试美股数据获取的日志"""
    print("\n" + "=" * 60)
    print("🧪 测试美股数据获取 - 数据来源日志")
    print("=" * 60)

    # 测试股票
    test_symbol = "AAPL"
    start_date = "2025-09-01"
    end_date = "2025-09-30"

    print(f"\n📊 测试股票: {test_symbol}")
    print(f"📅 日期范围: {start_date} 到 {end_date}")
    print("\n" + "-" * 60)
    print("第一次调用（应该从API获取）:")
    print("-" * 60)

    # 第一次调用 - 应该从API获取
    data1 = get_us_stock_data_cached(symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=False)

    print(f"\n✅ 获取到数据长度: {len(data1)} 字符")

    print("\n" + "-" * 60)
    print("第二次调用（应该从缓存获取）:")
    print("-" * 60)

    # 第二次调用 - 应该从缓存获取
    data2 = get_us_stock_data_cached(symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=False)

    print(f"\n✅ 获取到数据长度: {len(data2)} 字符")


def test_hk_stock_data():
    """测试港股数据获取的日志"""
    print("\n" + "=" * 60)
    print("🧪 测试港股数据获取 - 数据来源日志")
    print("=" * 60)

    # 测试股票
    test_symbol = "0700.HK"
    start_date = "2025-09-01"
    end_date = "2025-09-30"

    print(f"\n📊 测试股票: {test_symbol}")
    print(f"📅 日期范围: {start_date} 到 {end_date}")
    print("\n" + "-" * 60)
    print("第一次调用（应该从API获取）:")
    print("-" * 60)

    # 第一次调用 - 应该从API获取
    data1 = get_us_stock_data_cached(symbol=test_symbol, start_date=start_date, end_date=end_date, force_refresh=False)

    print(f"\n✅ 获取到数据长度: {len(data1)} 字符")


if __name__ == "__main__":
    try:
        print("\n" + "=" * 60)
        print("🚀 数据来源日志测试")
        print("=" * 60)
        print("\n📝 说明：观察日志中的 [数据来源: xxx] 标记")
        print("   - MongoDB: 从MongoDB数据库获取")
        print("   - 文件缓存: 从本地文件缓存获取")
        print("   - API调用: 从远程API获取")
        print("   - 备用数据: 生成的备用数据")

        # 测试A股
        test_china_stock_data()

        # 测试美股
        test_us_stock_data()

        # 测试港股
        test_hk_stock_data()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        print("\n💡 提示：检查上面的日志，确认每次数据获取都标注了数据来源")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
