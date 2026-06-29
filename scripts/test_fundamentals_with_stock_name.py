#!/usr/bin/env python3
"""
测试基本面分析是否能正确获取股票名称
验证修复后的股票信息获取功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_fundamentals_stock_name():
    """测试基本面分析中的股票名称获取"""
    print("🔍 测试基本面分析中的股票名称获取")
    print("=" * 50)

    # 测试股票代码
    test_codes = ["603985", "000001", "300033"]

    for code in test_codes:
        print(f"\n📊 测试股票代码: {code}")
        print("-" * 30)

        try:
            # 1. 获取股票数据
            print("🔍 步骤1: 获取股票数据...")
            from tradingagents.dataflows.interface import get_china_stock_data_unified

            stock_data = get_china_stock_data_unified(code, "2025-07-01", "2025-07-17")
            print(f"✅ 股票数据获取完成，长度: {len(stock_data) if stock_data else 0}")

            # 2. 生成基本面报告
            print("🔍 步骤2: 生成基本面报告...")
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

            analyzer = OptimizedChinaDataProvider()

            fundamentals_report = analyzer._generate_fundamentals_report(code, stock_data)
            print(f"✅ 基本面报告生成完成，长度: {len(fundamentals_report)}")

            # 3. 检查股票名称
            print("🔍 步骤3: 检查股票名称...")
            if "股票名称**: 未知公司" in fundamentals_report:
                print("❌ 仍然显示'未知公司'")
            elif f"股票名称**: 股票{code}" in fundamentals_report:
                print("❌ 仍然显示默认股票名称")
            else:
                # 提取股票名称
                lines = fundamentals_report.split("\n")
                for line in lines:
                    if "**股票名称**:" in line:
                        company_name = line.split(":")[1].strip()
                        print(f"✅ 成功获取股票名称: {company_name}")
                        break
                else:
                    print("❌ 未找到股票名称行")

            # 4. 显示报告前几行
            print("📄 报告前10行:")
            report_lines = fundamentals_report.split("\n")[:10]
            for line in report_lines:
                print(f"   {line}")

        except Exception as e:
            print(f"❌ 测试{code}失败: {e}")
            import traceback

            traceback.print_exc()


def test_stock_info_direct():
    """直接测试股票信息获取"""
    print("\n🔍 直接测试股票信息获取")
    print("=" * 50)

    test_code = "603985"  # 恒润股份

    try:
        # 测试统一接口
        from tradingagents.dataflows.interface import get_china_stock_info_unified

        stock_info = get_china_stock_info_unified(test_code)
        print("✅ 统一接口结果:")
        print(stock_info)

        # 测试DataSourceManager
        from tradingagents.dataflows.data_source_manager import get_data_source_manager

        manager = get_data_source_manager()
        manager_result = manager.get_stock_info(test_code)
        print("\n✅ DataSourceManager结果:")
        print(manager_result)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_fundamentals_with_fallback():
    """测试基本面分析的降级机制"""
    print("\n🔍 测试基本面分析的降级机制")
    print("=" * 50)

    # 测试不存在的股票代码
    fake_code = "999999"

    try:
        print(f"📊 测试不存在的股票代码: {fake_code}")

        # 1. 获取股票数据（应该会降级）
        from tradingagents.dataflows.interface import get_china_stock_data_unified

        stock_data = get_china_stock_data_unified(fake_code, "2025-07-01", "2025-07-17")
        print(f"✅ 股票数据: {stock_data[:100] if stock_data else 'None'}...")

        # 2. 生成基本面报告
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        analyzer = OptimizedChinaDataProvider()

        fundamentals_report = analyzer._generate_fundamentals_report(fake_code, stock_data)

        # 3. 检查是否使用了降级机制
        if "数据来源: akshare" in fundamentals_report or "数据来源: baostock" in fundamentals_report:
            print("✅ 基本面分析成功使用了降级机制")
        else:
            print("❌ 基本面分析未使用降级机制")

        # 4. 显示报告前几行
        print("📄 报告前5行:")
        report_lines = fundamentals_report.split("\n")[:5]
        for line in report_lines:
            print(f"   {line}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_complete_fundamentals_flow():
    """测试完整的基本面分析流程"""
    print("\n🔍 测试完整的基本面分析流程")
    print("=" * 50)

    test_code = "603985"  # 恒润股份

    try:
        # 模拟完整的基本面分析调用
        from tradingagents.agents.utils.agent_utils import AgentUtils

        print("📊 调用统一基本面分析工具...")
        result = AgentUtils.get_stock_fundamentals_unified(
            ticker=test_code, start_date="2025-07-01", end_date="2025-07-17", curr_date="2025-07-17",
        )

        print(f"✅ 基本面分析完成，结果长度: {len(result)}")

        # 检查是否包含正确的股票名称
        if "恒润股份" in result:
            print("✅ 基本面分析包含正确的股票名称: 恒润股份")
        elif "未知公司" in result:
            print("❌ 基本面分析仍显示'未知公司'")
        elif f"股票{test_code}" in result:
            print("❌ 基本面分析仍显示默认股票名称")
        else:
            print("🤔 无法确定股票名称状态")

        # 显示结果前几行
        print("📄 基本面分析结果前10行:")
        result_lines = result.split("\n")[:10]
        for line in result_lines:
            print(f"   {line}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("🧪 基本面分析股票名称获取测试")
    print("=" * 80)
    print("📝 此测试验证基本面分析是否能正确获取股票名称")
    print("=" * 80)

    # 1. 测试基本面分析中的股票名称
    test_fundamentals_stock_name()

    # 2. 直接测试股票信息获取
    test_stock_info_direct()

    # 3. 测试降级机制
    test_fundamentals_with_fallback()

    # 4. 测试完整流程
    test_complete_fundamentals_flow()

    print("\n📋 测试总结")
    print("=" * 60)
    print("✅ 基本面分析股票名称获取测试完成")
    print("🎯 现在基本面分析应该能显示:")
    print("   - **股票名称**: 恒润股份 (而不是'未知公司')")
    print("   - **所属行业**: 电气设备 (而不是'未知')")
    print("   - **所属地区**: 江苏 (而不是'未知')")
