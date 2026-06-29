#!/usr/bin/env python3
"""
原始数据显示测试脚本
直接调用底层数据接口，显示原始的财务数据
"""

import json
import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_raw_data_display():
    """测试并显示原始的基本面数据"""

    print("=" * 80)
    print("📊 原始基本面数据显示测试")
    print("=" * 80)

    # 测试参数
    ticker = "000001"  # 平安银行
    curr_date = datetime.now()
    start_date = curr_date - timedelta(days=2)  # 优化后只获取2天数据
    end_date = curr_date

    print(f"🎯 测试股票: {ticker}")
    print(f"📅 数据范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"⏰ 当前时间: {curr_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        # 直接调用底层数据接口
        from tradingagents.dataflows.interface import get_china_stock_data_unified

        print("🔄 正在获取原始股票数据...")
        print("-" * 60)

        # 调用底层数据接口
        raw_data = get_china_stock_data_unified(ticker, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        print("✅ 原始数据获取成功！")
        print()

        # 显示原始数据的基本信息
        print("📋 原始数据基本信息:")
        print(f"   - 数据类型: {type(raw_data)}")
        print(f"   - 数据长度: {len(str(raw_data))} 字符")
        print()

        # 完整显示原始数据内容
        print("📄 完整原始数据内容:")
        print("=" * 80)

        if isinstance(raw_data, str):
            print("🔤 字符串格式原始数据:")
            print(raw_data)
        elif isinstance(raw_data, dict):
            print("📚 字典格式原始数据:")
            print(json.dumps(raw_data, ensure_ascii=False, indent=2))
        elif isinstance(raw_data, list):
            print("📝 列表格式原始数据:")
            for i, item in enumerate(raw_data):
                print(f"📌 项目 {i + 1}:")
                if isinstance(item, (dict, list)):
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                else:
                    print(f"   {item}")
                print("-" * 40)
        else:
            print("🔍 其他格式原始数据:")
            print(repr(raw_data))

        print("=" * 80)

        # 数据统计信息
        print("\n📊 原始数据统计:")
        print(f"   - 总字符数: {len(str(raw_data))}")

        # 如果是字符串，显示详细信息
        if isinstance(raw_data, str):
            lines = raw_data.split("\n")
            print(f"   - 总行数: {len(lines)}")
            print(f"   - 首行: {lines[0]}")
            if len(lines) > 1:
                print(f"   - 末行: {lines[-1]}")

            # 查找关键信息
            if "股票代码" in raw_data:
                print("   ✅ 包含股票代码信息")
            if "股票名称" in raw_data:
                print("   ✅ 包含股票名称信息")
            if "当前价格" in raw_data:
                print("   ✅ 包含当前价格信息")
            if "财务指标" in raw_data:
                print("   ✅ 包含财务指标信息")
            if "历史价格" in raw_data:
                print("   ✅ 包含历史价格信息")

        print("\n🎉 原始数据显示完成！")

        # 测试获取财务数据
        print("\n" + "=" * 80)
        print("📊 测试获取财务基本面数据")
        print("=" * 80)

        try:
            from tradingagents.dataflows.interface import get_china_stock_fundamentals_tushare

            print("🔄 正在获取财务基本面数据...")

            fundamentals_data = get_china_stock_fundamentals_tushare(ticker)

            print("✅ 财务基本面数据获取成功！")
            print()

            print("📋 财务基本面数据基本信息:")
            print(f"   - 数据类型: {type(fundamentals_data)}")
            print(f"   - 数据长度: {len(str(fundamentals_data))} 字符")
            print()

            print("📄 完整财务基本面数据内容:")
            print("=" * 80)

            if isinstance(fundamentals_data, str):
                print("🔤 字符串格式财务数据:")
                print(fundamentals_data)
            elif isinstance(fundamentals_data, dict):
                print("📚 字典格式财务数据:")
                print(json.dumps(fundamentals_data, ensure_ascii=False, indent=2))
            else:
                print("🔍 其他格式财务数据:")
                print(repr(fundamentals_data))

            print("=" * 80)

        except Exception as e:
            print(f"❌ 财务基本面数据获取失败: {e!s}")
            import traceback

            print("🔍 详细错误信息:")
            traceback.print_exc()

    except Exception as e:
        print(f"❌ 测试失败: {e!s}")
        import traceback

        print("🔍 详细错误信息:")
        traceback.print_exc()


if __name__ == "__main__":
    test_raw_data_display()
