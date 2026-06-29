#!/usr/bin/env python3
"""
详细数据显示测试脚本
完整显示基本面分析获取的所有数据内容
"""

import json
import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit


def test_detailed_data_display():
    """测试并完整显示基本面分析获取的数据"""

    print("=" * 80)
    print("📊 基本面分析数据详细显示测试")
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
        # 创建工具实例
        toolkit = Toolkit()

        print("🔄 正在获取基本面分析数据...")
        print("-" * 60)

        # 调用优化后的基本面数据获取函数
        result = toolkit.get_stock_fundamentals_unified.invoke(
            {
                "ticker": ticker,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "curr_date": curr_date.strftime("%Y-%m-%d"),
            },
        )

        print("✅ 数据获取成功！")
        print()

        # 显示原始结果的基本信息
        print("📋 原始结果基本信息:")
        print(f"   - 数据类型: {type(result)}")
        print(f"   - 数据长度: {len(str(result))} 字符")
        print()

        # 完整显示结果内容
        print("📄 完整数据内容:")
        print("=" * 80)

        if isinstance(result, str):
            print("🔤 字符串格式数据:")
            print(result)
        elif isinstance(result, dict):
            print("📚 字典格式数据:")
            for key, value in result.items():
                print(f"🔑 {key}:")
                if isinstance(value, (dict, list)):
                    print(json.dumps(value, ensure_ascii=False, indent=2))
                else:
                    print(f"   {value}")
                print("-" * 40)
        elif isinstance(result, list):
            print("📝 列表格式数据:")
            for i, item in enumerate(result):
                print(f"📌 项目 {i + 1}:")
                if isinstance(item, (dict, list)):
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                else:
                    print(f"   {item}")
                print("-" * 40)
        else:
            print("🔍 其他格式数据:")
            print(repr(result))

        print("=" * 80)

        # 数据统计信息
        print("\n📊 数据统计:")
        print(f"   - 总字符数: {len(str(result))}")
        print(f"   - 总行数: {str(result).count(chr(10)) + 1}")

        # 如果是字符串，显示前后部分内容
        if isinstance(result, str):
            lines = result.split("\n")
            print(f"   - 总行数: {len(lines)}")
            print(f"   - 首行: {lines[0][:100]}..." if len(lines[0]) > 100 else f"   - 首行: {lines[0]}")
            if len(lines) > 1:
                print(f"   - 末行: {lines[-1][:100]}..." if len(lines[-1]) > 100 else f"   - 末行: {lines[-1]}")

        print("\n🎉 数据显示完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e!s}")
        import traceback

        print("🔍 详细错误信息:")
        traceback.print_exc()


if __name__ == "__main__":
    test_detailed_data_display()
