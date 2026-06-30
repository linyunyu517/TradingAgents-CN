#!/usr/bin/env python3
"""
专门查看AKShare财务数据中的PE、PB、ROE指标
"""

import logging
import os
import sys

# 设置日志级别
logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)-8s | %(message)s")

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.akshare_utils import AKShareProvider


def check_key_metrics():
    """检查关键财务指标"""
    print("=" * 60)
    print("🔍 检查AKShare关键财务指标")
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

    # 获取最新数据列
    latest_col = main_indicators.columns[2]  # 第3列是最新数据
    print(f"📅 最新数据期间: {latest_col}")

    # 查找ROE
    roe_row = main_indicators[main_indicators["指标"] == "净资产收益率(ROE)"]
    if not roe_row.empty:
        roe_value = roe_row.iloc[0][latest_col]
        print(f"📈 净资产收益率(ROE): {roe_value}")
    else:
        print("❌ 未找到ROE指标")

    # 查找每股收益（用于计算PE）
    eps_row = main_indicators[main_indicators["指标"] == "每股收益"]
    if not eps_row.empty:
        eps_value = eps_row.iloc[0][latest_col]
        print(f"💰 每股收益(EPS): {eps_value}")
    else:
        print("❌ 未找到每股收益指标")

    # 查找每股净资产（用于计算PB）
    bps_row = main_indicators[main_indicators["指标"] == "每股净资产_最新股数"]
    if not bps_row.empty:
        bps_value = bps_row.iloc[0][latest_col]
        print(f"📊 每股净资产(BPS): {bps_value}")
    else:
        print("❌ 未找到每股净资产指标")

    # 显示所有包含"每股"的指标
    print("\n📋 所有每股相关指标:")
    eps_indicators = main_indicators[main_indicators["指标"].str.contains("每股", na=False)]
    for _, row in eps_indicators.iterrows():
        indicator_name = row["指标"]
        value = row[latest_col]
        print(f"   {indicator_name}: {value}")

    # 显示所有包含"收益率"的指标
    print("\n📋 所有收益率相关指标:")
    roe_indicators = main_indicators[main_indicators["指标"].str.contains("收益率", na=False)]
    for _, row in roe_indicators.iterrows():
        indicator_name = row["指标"]
        value = row[latest_col]
        print(f"   {indicator_name}: {value}")

    print("\n" + "=" * 60)
    print("✅ 关键指标检查完成")
    print("=" * 60)


if __name__ == "__main__":
    check_key_metrics()
