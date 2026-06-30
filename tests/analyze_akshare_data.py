#!/usr/bin/env python3
"""
检查AKShare财务数据结构
"""

import logging
import os
import sys

# 设置日志级别
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.akshare_utils import AKShareProvider


def analyze_akshare_data():
    """分析AKShare财务数据结构"""
    print("=" * 60)
    print("🔍 分析AKShare财务数据结构")
    print("=" * 60)

    provider = AKShareProvider()
    if not provider.connected:
        print("❌ AKShare未连接")
        return

    symbol = "600519"
    financial_data = provider.get_financial_data(symbol)

    if not financial_data:
        print("❌ 未获取到财务数据")
        return

    main_indicators = financial_data.get("main_indicators")
    if main_indicators is None:
        print("❌ 未获取到主要财务指标")
        return

    print("\n📊 主要财务指标数据结构分析:")
    print(f"   数据类型: {type(main_indicators)}")
    print(f"   数据形状: {main_indicators.shape}")
    print(f"   列名: {list(main_indicators.columns)}")

    print("\n📋 前5行数据:")
    print(main_indicators.head())

    print("\n🔍 查找PE、PB、ROE相关指标:")

    # 查找包含关键词的行
    pe_rows = main_indicators[main_indicators["指标"].str.contains("市盈率|PE", na=False, case=False)]
    pb_rows = main_indicators[main_indicators["指标"].str.contains("市净率|PB", na=False, case=False)]
    roe_rows = main_indicators[main_indicators["指标"].str.contains("净资产收益率|ROE", na=False, case=False)]

    # 获取最新数据列（第3列，索引为2）
    latest_col = main_indicators.columns[2] if len(main_indicators.columns) > 2 else None
    print(f"   最新数据列: {latest_col}")

    print(f"\n📈 PE相关指标 ({len(pe_rows)}条):")
    if not pe_rows.empty:
        for _, row in pe_rows.iterrows():
            latest_value = row[latest_col] if latest_col else "N/A"
            print(f"   {row['指标']}: {latest_value}")
    else:
        print("   未找到PE相关指标")

    print(f"\n📈 PB相关指标 ({len(pb_rows)}条):")
    if not pb_rows.empty:
        for _, row in pb_rows.iterrows():
            latest_value = row[latest_col] if latest_col else "N/A"
            print(f"   {row['指标']}: {latest_value}")
    else:
        print("   未找到PB相关指标")

    print(f"\n📈 ROE相关指标 ({len(roe_rows)}条):")
    if not roe_rows.empty:
        for _, row in roe_rows.iterrows():
            latest_value = row[latest_col] if latest_col else "N/A"
            print(f"   {row['指标']}: {latest_value}")
    else:
        print("   未找到ROE相关指标")

    # 专门查找ROE指标
    roe_exact = main_indicators[main_indicators["指标"] == "净资产收益率(ROE)"]
    if not roe_exact.empty:
        roe_value = roe_exact.iloc[0][latest_col] if latest_col else "N/A"
        print(f"\n🎯 精确匹配 - 净资产收益率(ROE): {roe_value}")

        # 显示ROE的历史数据（前5个季度）
        print("   历史数据:")
        for i in range(2, min(7, len(main_indicators.columns))):
            col_name = main_indicators.columns[i]
            value = roe_exact.iloc[0][col_name]
            print(f"     {col_name}: {value}")

    # 查找可能的PE、PB替代指标
    print("\n🔍 查找可能的PE、PB替代指标:")

    # 查找每股相关指标
    eps_rows = main_indicators[main_indicators["指标"].str.contains("每股收益|每股净利润", na=False, case=False)]
    print(f"\n📈 每股收益相关指标 ({len(eps_rows)}条):")
    for _, row in eps_rows.iterrows():
        latest_value = row[latest_col] if latest_col else "N/A"
        print(f"   {row['指标']}: {latest_value}")

    # 查找每股净资产相关指标
    bps_rows = main_indicators[main_indicators["指标"].str.contains("每股净资产", na=False, case=False)]
    print(f"\n📈 每股净资产相关指标 ({len(bps_rows)}条):")
    for _, row in bps_rows.iterrows():
        latest_value = row[latest_col] if latest_col else "N/A"
        print(f"   {row['指标']}: {latest_value}")

    # 显示所有指标名称
    print("\n📋 所有指标名称:")
    for i, indicator in enumerate(main_indicators["指标"]):
        print(f"   {i:2d}. {indicator}")

    print("\n" + "=" * 60)
    print("✅ 数据结构分析完成")
    print("=" * 60)


if __name__ == "__main__":
    analyze_akshare_data()
