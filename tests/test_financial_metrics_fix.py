#!/usr/bin/env python3
"""
测试财务指标修复效果
验证是否使用真实财务数据而不是分类估算
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

# 设置日志级别
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_financial_metrics():
    """测试财务指标获取"""
    print("🔧 测试财务指标修复效果")
    print("=" * 80)

    # 测试股票列表
    test_symbols = [
        "000001",  # 平安银行
        "000002",  # 万科A
        "300001",  # 特锐德（创业板）
        "600036",  # 招商银行
        "600519",  # 贵州茅台
    ]

    provider = OptimizedChinaDataProvider()

    for symbol in test_symbols:
        print(f"\n📊 测试股票: {symbol}")
        print("-" * 50)

        try:
            # 获取基本面数据
            fundamentals = provider.get_fundamentals_data(symbol, force_refresh=True)

            # 检查是否包含数据来源说明
            if "✅ **数据说明**: 财务指标基于Tushare真实财务数据计算" in fundamentals:
                print(f"✅ {symbol}: 使用真实财务数据")
            elif "⚠️ **数据说明**: 部分财务指标为估算值" in fundamentals:
                print(f"⚠️ {symbol}: 使用估算财务数据")
            else:
                print(f"❓ {symbol}: 数据来源不明确")

            # 提取关键财务指标
            lines = fundamentals.split("\n")
            pe_line = next((line for line in lines if "市盈率(PE)" in line), None)
            pb_line = next((line for line in lines if "市净率(PB)" in line), None)
            roe_line = next((line for line in lines if "净资产收益率(ROE)" in line), None)

            if pe_line:
                print(f"  PE: {pe_line.split(':')[1].strip()}")
            if pb_line:
                print(f"  PB: {pb_line.split(':')[1].strip()}")
            if roe_line:
                print(f"  ROE: {roe_line.split(':')[1].strip()}")

        except Exception as e:
            print(f"❌ {symbol}: 测试失败 - {e}")


def test_tushare_connection():
    """测试Tushare连接"""
    print("\n🔧 测试Tushare连接")
    print("=" * 80)

    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider

        provider = get_tushare_provider()
        if provider.connected:
            print("✅ Tushare连接成功")

            # 测试获取财务数据
            test_symbol = "000001"
            financial_data = provider.get_financial_data(test_symbol)

            if financial_data:
                print(f"✅ 成功获取{test_symbol}财务数据")
                print(f"  资产负债表: {len(financial_data.get('balance_sheet', []))}条记录")
                print(f"  利润表: {len(financial_data.get('income_statement', []))}条记录")
                print(f"  现金流量表: {len(financial_data.get('cash_flow', []))}条记录")
            else:
                print(f"⚠️ 未获取到{test_symbol}财务数据")
        else:
            print("❌ Tushare连接失败")

    except Exception as e:
        print(f"❌ Tushare测试失败: {e}")


def main():
    """主函数"""
    print("🚀 开始测试财务指标修复效果")
    print("=" * 80)

    # 测试Tushare连接
    test_tushare_connection()

    # 测试财务指标
    test_financial_metrics()

    print("\n✅ 测试完成")
    print("=" * 80)
    print("说明:")
    print("- ✅ 表示使用真实财务数据")
    print("- ⚠️ 表示使用估算数据（Tushare不可用时的备用方案）")
    print("- ❌ 表示测试失败")


if __name__ == "__main__":
    main()
