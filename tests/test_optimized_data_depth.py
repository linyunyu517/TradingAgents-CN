#!/usr/bin/env python3
"""
测试优化后的数据深度级别逻辑
验证基本面分析不再获取不必要的历史数据
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

from tradingagents.agents.utils.agent_utils import Toolkit


def test_optimized_data_depth():
    """测试优化后的数据深度级别"""

    # 测试股票代码
    stock_code = "300750"  # 宁德时代

    print("=" * 80)
    print("测试优化后的数据深度级别逻辑")
    print("=" * 80)

    # 测试不同深度级别
    depth_levels = [1, 3, 5]
    depth_names = ["快速", "标准", "全面"]

    results = {}

    for i, depth in enumerate(depth_levels):
        print(f"\n🔍 测试深度级别 {depth} ({depth_names[i]})...")

        # 设置研究深度
        Toolkit._config["research_depth"] = depth

        try:
            # 获取基本面数据
            data = Toolkit.get_stock_fundamentals_unified(stock_code)

            # 分析数据内容
            lines = data.split("\n")
            line_count = len(lines)

            # 统计模块数量（以##开头的行）
            module_count = sum(1 for line in lines if line.strip().startswith("##"))

            # 检查是否包含历史数据相关内容
            historical_data_mentions = sum(
                1 for line in lines if "历史" in line or "天数据" in line or "days" in line.lower()
            )

            results[depth] = {
                "line_count": line_count,
                "module_count": module_count,
                "historical_mentions": historical_data_mentions,
                "data_length": len(data),
            }

            print(f"   ✅ 数据行数: {line_count}")
            print(f"   ✅ 模块数量: {module_count}")
            print(f"   ✅ 历史数据提及次数: {historical_data_mentions}")
            print(f"   ✅ 数据总长度: {len(data)} 字符")

        except Exception as e:
            print(f"   ❌ 获取数据失败: {e}")
            results[depth] = None

    # 分析结果
    print("\n" + "=" * 80)
    print("优化结果分析")
    print("=" * 80)

    valid_results = {k: v for k, v in results.items() if v is not None}

    if len(valid_results) >= 2:
        print("\n📊 数据深度级别对比:")
        for depth in depth_levels:
            if depth in valid_results:
                result = valid_results[depth]
                depth_name = depth_names[depth_levels.index(depth)]
                print(
                    f"   级别 {depth} ({depth_name}): {result['module_count']} 模块, {result['line_count']} 行, {result['data_length']} 字符",
                )

        # 检查优化效果
        print("\n🎯 优化效果验证:")

        # 1. 检查是否还有历史数据相关内容
        total_historical_mentions = sum(r["historical_mentions"] for r in valid_results.values())
        if total_historical_mentions == 0:
            print("   ✅ 成功移除历史数据相关内容")
        else:
            print(f"   ⚠️  仍有 {total_historical_mentions} 处历史数据相关内容")

        # 2. 检查不同级别的差异是否合理
        level_1_modules = valid_results.get(1, {}).get("module_count", 0)
        level_3_modules = valid_results.get(3, {}).get("module_count", 0)
        level_5_modules = valid_results.get(5, {}).get("module_count", 0)

        if level_1_modules < level_3_modules <= level_5_modules:
            print("   ✅ 数据深度级别递增合理")
        else:
            print(f"   ⚠️  数据深度级别可能需要调整: L1={level_1_modules}, L3={level_3_modules}, L5={level_5_modules}")

        # 3. 性能改进估算
        if 1 in valid_results and 5 in valid_results:
            level_1_size = valid_results[1]["data_length"]
            level_5_size = valid_results[5]["data_length"]
            if level_5_size > level_1_size:
                size_ratio = level_5_size / level_1_size
                print(f"   📈 级别5相比级别1数据量增加: {size_ratio:.1f}倍")
            else:
                print("   ✅ 高级别数据量控制良好")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    test_optimized_data_depth()
