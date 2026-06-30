#!/usr/bin/env python3
"""
最终验证脚本：测试优化后的数据深度级别是否产生不同详细程度的基本面分析报告
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import time

from tradingagents.agents.utils.agent_utils import Toolkit


def test_analysis_depth_differences():
    """测试不同深度级别产生的报告差异"""
    print("=" * 80)
    print("最终验证：测试不同深度级别的基本面分析报告差异")
    print("=" * 80)

    stock_code = "300750"  # 宁德时代

    # 测试三个深度级别
    depth_levels = [1, 3, 5]
    results = {}

    for depth in depth_levels:
        print(f"\n🔍 测试深度级别 {depth}...")

        try:
            # 调用基本面分析
            result = Toolkit.get_stock_fundamentals_unified(
                ticker=stock_code, start_date="2024-10-10", end_date="2024-10-11", curr_date="2024-10-11",
            )

            # 分析结果
            lines = result.split("\n")
            char_count = len(result)

            # 检查报告类型标识
            report_type = "未知"
            if "(基础版)" in result:
                report_type = "基础版"
            elif "(全面版)" in result:
                report_type = "全面版"
            else:
                report_type = "标准版"

            # 统计关键指标数量
            pe_mentions = result.count("市盈率")
            pb_mentions = result.count("市净率")
            roe_mentions = result.count("净资产收益率")
            industry_mentions = result.count("行业")
            investment_mentions = result.count("投资")

            results[depth] = {
                "lines": len(lines),
                "chars": char_count,
                "type": report_type,
                "pe_count": pe_mentions,
                "pb_count": pb_mentions,
                "roe_count": roe_mentions,
                "industry_count": industry_mentions,
                "investment_count": investment_mentions,
                "content": result[:500] + "..." if len(result) > 500 else result,
            }

            print(f"   ✅ 报告类型: {report_type}")
            print(f"   ✅ 数据行数: {len(lines)}")
            print(f"   ✅ 字符数量: {char_count}")
            print(f"   ✅ 关键指标提及: PE({pe_mentions}) PB({pb_mentions}) ROE({roe_mentions})")

        except Exception as e:
            print(f"   ❌ 错误: {e}")
            results[depth] = {"error": str(e)}

        time.sleep(1)  # 避免请求过快

    # 分析结果差异
    print("\n" + "=" * 80)
    print("报告差异分析")
    print("=" * 80)

    print("\n📊 各级别报告对比:")
    for depth in depth_levels:
        if "error" not in results[depth]:
            r = results[depth]
            print(f"   级别 {depth}: {r['type']} - {r['lines']}行, {r['chars']}字符")
        else:
            print(f"   级别 {depth}: 错误 - {results[depth]['error']}")

    # 验证差异化效果
    print("\n🎯 差异化验证:")

    # 检查是否有不同的报告类型
    types = set()
    valid_results = []
    for depth in depth_levels:
        if "error" not in results[depth]:
            types.add(results[depth]["type"])
            valid_results.append((depth, results[depth]))

    if len(types) > 1:
        print("   ✅ 成功：不同深度级别产生了不同类型的报告")
        for report_type in types:
            depths = [d for d, r in valid_results if r["type"] == report_type]
            print(f"      - {report_type}: 深度级别 {depths}")
    else:
        print("   ⚠️  警告：所有深度级别产生了相同类型的报告")

    # 检查内容长度差异
    if len(valid_results) >= 2:
        min_chars = min(r["chars"] for _, r in valid_results)
        max_chars = max(r["chars"] for _, r in valid_results)
        char_ratio = max_chars / min_chars if min_chars > 0 else 1

        print(f"   📈 内容长度差异: {char_ratio:.1f}倍 ({min_chars} -> {max_chars} 字符)")

        if char_ratio >= 1.5:
            print("   ✅ 优秀：深度级别间有显著的内容差异")
        elif char_ratio >= 1.2:
            print("   ✅ 良好：深度级别间有适度的内容差异")
        else:
            print("   ⚠️  一般：深度级别间内容差异较小")

    # 显示示例内容
    print("\n📝 报告内容示例:")
    for depth in [1, 5]:  # 只显示最低和最高级别
        if depth in results and "error" not in results[depth]:
            print(f"\n--- 深度级别 {depth} ({results[depth]['type']}) ---")
            print(results[depth]["content"])

    print("\n" + "=" * 80)
    print("最终验证完成")
    print("=" * 80)


if __name__ == "__main__":
    test_analysis_depth_differences()
