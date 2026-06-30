#!/usr/bin/env python3
"""
测试港股数据工具是否正确显示昨收字段
"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from tradingagents.dataflows.providers.hk.improved_hk import get_hk_stock_data_akshare


def test_hk_data_with_preclose():
    """测试港股数据是否包含昨收字段"""

    print("=" * 80)
    print("测试港股数据工具 - 验证昨收字段")
    print("=" * 80)

    # 测试腾讯控股 (00700)
    symbol = "00700.HK"
    start_date = "2025-11-01"
    end_date = "2025-11-09"

    print(f"\n📊 获取 {symbol} 的历史数据...")
    print(f"📅 日期范围: {start_date} ~ {end_date}")
    print()

    result = get_hk_stock_data_akshare(symbol, start_date, end_date)

    print(result)

    # 验证结果
    print("\n" + "=" * 80)
    print("验证结果:")
    print("=" * 80)

    if "pre_close" in result:
        print("✅ 结果包含 'pre_close' 字段")
    else:
        print("❌ 结果不包含 'pre_close' 字段")

    if "change" in result:
        print("✅ 结果包含 'change' 字段（涨跌额）")
    else:
        print("❌ 结果不包含 'change' 字段（涨跌额）")

    if "pct_change" in result:
        print("✅ 结果包含 'pct_change' 字段（涨跌幅）")
    else:
        print("❌ 结果不包含 'pct_change' 字段（涨跌幅）")

    # 检查最后一天的数据
    print("\n" + "=" * 80)
    print("最后一天数据验证 (2025-11-07):")
    print("=" * 80)
    print("预期值（百度财经）:")
    print("  今开: 638.000")
    print("  最高: 643.000")
    print("  最低: 628.500")
    print("  收盘: 634.000")
    print("  昨收: 644.000")
    print("  涨跌额: -10.00")
    print("  涨跌幅: -1.55%")
    print()

    # 从结果中提取最后一天的数据
    lines = result.split("\n")
    for _i, line in enumerate(lines):
        if "2025-11-07" in line:
            print("实际值（工具返回）:")
            print(f"  {line}")

            # 解析数据
            parts = line.split()
            if len(parts) >= 9:
                parts[0]
                open_price = float(parts[1])
                high = float(parts[2])
                low = float(parts[3])
                close = float(parts[4])
                pre_close = float(parts[5]) if parts[5] != "NaN" else None
                change = float(parts[6]) if parts[6] != "NaN" else None
                pct_change = float(parts[7]) if parts[7] != "NaN" else None

                print()
                print("解析结果:")
                print(f"  今开: {open_price}")
                print(f"  最高: {high}")
                print(f"  最低: {low}")
                print(f"  收盘: {close}")
                print(f"  昨收: {pre_close}")
                print(f"  涨跌额: {change}")
                print(f"  涨跌幅: {pct_change}%")

                # 验证
                print()
                print("验证结果:")
                if abs(open_price - 638.0) < 0.01:
                    print("  ✅ 今开正确")
                else:
                    print(f"  ❌ 今开错误: 预期 638.0, 实际 {open_price}")

                if abs(high - 643.0) < 0.01:
                    print("  ✅ 最高正确")
                else:
                    print(f"  ❌ 最高错误: 预期 643.0, 实际 {high}")

                if abs(low - 628.5) < 0.01:
                    print("  ✅ 最低正确")
                else:
                    print(f"  ❌ 最低错误: 预期 628.5, 实际 {low}")

                if abs(close - 634.0) < 0.01:
                    print("  ✅ 收盘正确")
                else:
                    print(f"  ❌ 收盘错误: 预期 634.0, 实际 {close}")

                if pre_close and abs(pre_close - 644.0) < 0.01:
                    print("  ✅ 昨收正确")
                else:
                    print(f"  ❌ 昨收错误: 预期 644.0, 实际 {pre_close}")

                if change and abs(change - (-10.0)) < 0.01:
                    print("  ✅ 涨跌额正确")
                else:
                    print(f"  ❌ 涨跌额错误: 预期 -10.0, 实际 {change}")

                if pct_change and abs(pct_change - (-1.55)) < 0.01:
                    print("  ✅ 涨跌幅正确")
                else:
                    print(f"  ❌ 涨跌幅错误: 预期 -1.55%, 实际 {pct_change}%")

            break


if __name__ == "__main__":
    test_hk_data_with_preclose()
