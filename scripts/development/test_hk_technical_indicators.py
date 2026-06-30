#!/usr/bin/env python3
"""
测试港股技术指标计算是否正确
"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from tradingagents.dataflows.providers.hk.improved_hk import get_hk_stock_data_akshare


def test_hk_technical_indicators():
    """测试港股技术指标计算"""

    print("=" * 80)
    print("测试港股技术指标计算")
    print("=" * 80)

    # 测试腾讯控股 (00700)
    symbol = "00700.HK"
    start_date = "2024-11-09"
    end_date = "2025-11-09"

    print(f"\n📊 测试股票: {symbol}")
    print(f"📅 日期范围: {start_date} ~ {end_date}")
    print()

    result = get_hk_stock_data_akshare(symbol, start_date, end_date)

    print("\n" + "=" * 80)
    print("返回结果:")
    print("=" * 80)
    print(result)

    # 验证结果
    print("\n" + "=" * 80)
    print("验证结果:")
    print("=" * 80)

    # 检查是否包含技术指标
    indicators = {
        "MA5": "MA5",
        "MA10": "MA10",
        "MA20": "MA20",
        "MA60": "MA60",
        "MACD": "MACD",
        "DIF": "DIF",
        "DEA": "DEA",
        "RSI": "RSI",
        "布林带": "布林带",
        "上轨": "上轨",
        "中轨": "中轨",
        "下轨": "下轨",
    }

    print("\n📊 技术指标检查:")
    for name, keyword in indicators.items():
        if keyword in result:
            print(f"  ✅ {name}: 已包含")
        else:
            print(f"  ❌ {name}: 缺失")

    # 提取技术指标数值
    print("\n📈 技术指标数值:")
    import re

    # 提取 MA 值
    ma_pattern = r"MA(\d+): HK\$([0-9.]+)"
    ma_matches = re.findall(ma_pattern, result)
    if ma_matches:
        print("\n  移动平均线:")
        for period, value in ma_matches:
            print(f"    MA{period}: HK${value}")

    # 提取 MACD 值
    macd_patterns = {"DIF": r"DIF: ([0-9.-]+)", "DEA": r"DEA: ([0-9.-]+)", "MACD": r"MACD: ([0-9.-]+)"}
    print("\n  MACD指标:")
    for name, pattern in macd_patterns.items():
        match = re.search(pattern, result)
        if match:
            print(f"    {name}: {match.group(1)}")

    # 提取 RSI 值
    rsi_pattern = r"RSI\(14\): ([0-9.]+)"
    rsi_match = re.search(rsi_pattern, result)
    if rsi_match:
        print("\n  RSI指标:")
        print(f"    RSI(14): {rsi_match.group(1)}")

    # 提取布林带值
    boll_patterns = {"上轨": r"上轨: HK\$([0-9.]+)", "中轨": r"中轨: HK\$([0-9.]+)", "下轨": r"下轨: HK\$([0-9.]+)"}
    print("\n  布林带:")
    for name, pattern in boll_patterns.items():
        match = re.search(pattern, result)
        if match:
            print(f"    {name}: HK${match.group(1)}")

    # 检查数据条数
    data_count_pattern = r"数据条数.*?(\d+)\s*条"
    data_count_match = re.search(data_count_pattern, result)
    if data_count_match:
        data_count = int(data_count_match.group(1))
        print(f"\n📊 数据条数: {data_count} 条")

        if data_count >= 200:
            print("  ✅ 数据量充足（>= 200条，约1年数据）")
        else:
            print(f"  ⚠️ 数据量偏少（{data_count}条）")


if __name__ == "__main__":
    test_hk_technical_indicators()
