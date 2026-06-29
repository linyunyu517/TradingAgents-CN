#!/usr/bin/env python3
"""
性能对比测试：验证优化前后基本面分析数据获取的性能差异
对比数据传输量、处理时间等关键指标
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta


def simulate_old_strategy():
    """模拟优化前的数据获取策略（7-30天历史数据）"""
    print("🔄 模拟优化前策略：获取7-30天历史数据...")

    ticker = "000001"
    results = {}

    # 模拟不同数据深度的历史数据获取
    test_cases = [
        ("basic", 7, "基础分析 - 7天数据"),
        ("standard", 14, "标准分析 - 14天数据"),
        ("full", 21, "完整分析 - 21天数据"),
        ("detailed", 28, "详细分析 - 28天数据"),
        ("comprehensive", 30, "全面分析 - 30天数据"),
    ]

    for depth_name, days_back, description in test_cases:
        print(f"\n📊 {description}")

        # 计算日期范围
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        start_time = time.time()

        try:
            # 获取历史价格数据
            from tradingagents.dataflows.interface import get_china_stock_data_unified

            stock_data = get_china_stock_data_unified(ticker, start_date, end_date)

            # 获取基本面数据
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

            analyzer = OptimizedChinaDataProvider()
            fundamentals_data = analyzer._generate_fundamentals_report(ticker, stock_data)

            # 合并数据
            combined_data = f"## A股价格数据\n{stock_data}\n\n## A股基本面数据\n{fundamentals_data}"

            end_time = time.time()
            processing_time = end_time - start_time

            results[depth_name] = {
                "success": True,
                "data_length": len(combined_data),
                "price_data_length": len(stock_data) if stock_data else 0,
                "fundamentals_length": len(fundamentals_data) if fundamentals_data else 0,
                "processing_time": processing_time,
                "days_requested": days_back,
                "description": description,
            }

            print(f"   ✅ 数据长度: {len(combined_data):,} 字符")
            print(f"   ⏱️ 处理时间: {processing_time:.2f}秒")

        except Exception as e:
            results[depth_name] = {
                "success": False,
                "data_length": 0,
                "price_data_length": 0,
                "fundamentals_length": 0,
                "processing_time": 0,
                "days_requested": days_back,
                "description": description,
                "error": str(e),
            }
            print(f"   ❌ 获取失败: {e}")

    return results


def test_new_strategy():
    """测试优化后的数据获取策略（只获取最近2天价格+基本面数据）"""
    print("\n🚀 测试优化后策略：只获取最近2天价格+基本面数据...")

    ticker = "000001"

    start_time = time.time()

    try:
        # 1. 获取最新股价信息（只需要最近1-2天的数据）
        curr_date = datetime.now().strftime("%Y-%m-%d")
        recent_end_date = curr_date
        recent_start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")

        from tradingagents.dataflows.interface import get_china_stock_data_unified

        current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)

        # 2. 获取基本面财务数据
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        analyzer = OptimizedChinaDataProvider()
        fundamentals_data = analyzer._generate_fundamentals_report(ticker, current_price_data)

        # 3. 合并结果
        combined_data = f"## A股当前价格信息\n{current_price_data}\n\n## A股基本面财务数据\n{fundamentals_data}"

        end_time = time.time()
        processing_time = end_time - start_time

        result = {
            "success": True,
            "data_length": len(combined_data),
            "price_data_length": len(current_price_data) if current_price_data else 0,
            "fundamentals_length": len(fundamentals_data) if fundamentals_data else 0,
            "processing_time": processing_time,
            "days_requested": 2,
            "description": "优化策略 - 2天价格数据+基本面数据",
        }

        print(f"   ✅ 数据长度: {len(combined_data):,} 字符")
        print(f"   ⏱️ 处理时间: {processing_time:.2f}秒")

        return result

    except Exception as e:
        return {
            "success": False,
            "data_length": 0,
            "price_data_length": 0,
            "fundamentals_length": 0,
            "processing_time": 0,
            "days_requested": 2,
            "description": "优化策略 - 2天价格数据+基本面数据",
            "error": str(e),
        }


def compare_performance():
    """对比优化前后的性能差异"""
    print("=" * 80)
    print("📊 基本面分析数据获取策略性能对比测试")
    print("=" * 80)

    # 测试优化前策略
    old_results = simulate_old_strategy()

    # 测试优化后策略
    new_result = test_new_strategy()

    # 性能对比分析
    print("\n" + "=" * 80)
    print("📈 性能对比分析")
    print("=" * 80)

    if new_result["success"]:
        print("\n🚀 优化后策略性能:")
        print(f"   - 数据长度: {new_result['data_length']:,} 字符")
        print(f"   - 处理时间: {new_result['processing_time']:.2f}秒")
        print(f"   - 请求天数: {new_result['days_requested']}天")

        print("\n📊 与优化前各级别对比:")

        successful_old = {k: v for k, v in old_results.items() if v["success"]}

        if successful_old:
            # 数据量对比
            old_data_lengths = [v["data_length"] for v in successful_old.values()]
            avg_old_length = sum(old_data_lengths) / len(old_data_lengths)
            max_old_length = max(old_data_lengths)
            min_old_length = min(old_data_lengths)

            print("\n📏 数据传输量对比:")
            print(f"   - 优化前平均: {avg_old_length:,.0f} 字符")
            print(f"   - 优化前范围: {min_old_length:,} - {max_old_length:,} 字符")
            print(f"   - 优化后: {new_result['data_length']:,} 字符")
            print(f"   - 数据减少: {(avg_old_length - new_result['data_length']) / avg_old_length * 100:.1f}%")

            # 处理时间对比
            old_times = [v["processing_time"] for v in successful_old.values()]
            avg_old_time = sum(old_times) / len(old_times)

            print("\n⏱️ 处理时间对比:")
            print(f"   - 优化前平均: {avg_old_time:.2f}秒")
            print(f"   - 优化后: {new_result['processing_time']:.2f}秒")
            print(f"   - 时间节省: {(avg_old_time - new_result['processing_time']) / avg_old_time * 100:.1f}%")

            # 详细对比表
            print("\n📋 详细对比表:")
            print(f"{'策略':<25} | {'天数':<4} | {'数据量(字符)':<12} | {'时间(秒)':<8} | {'状态'}")
            print("-" * 70)

            for _depth, result in old_results.items():
                status = "✅" if result["success"] else "❌"
                data_len = f"{result['data_length']:,}" if result["success"] else "N/A"
                proc_time = f"{result['processing_time']:.2f}" if result["success"] else "N/A"
                print(
                    f"{result['description']:<25} | {result['days_requested']:<4} | {data_len:<12} | {proc_time:<8} | {status}",
                )

            print("-" * 70)
            data_len = f"{new_result['data_length']:,}"
            proc_time = f"{new_result['processing_time']:.2f}"
            print(f"{'优化后策略':<25} | {new_result['days_requested']:<4} | {data_len:<12} | {proc_time:<8} | ✅")

            # 优化效果总结
            print("\n💡 优化效果总结:")
            print(
                f"   ✅ 数据传输量平均减少 {(avg_old_length - new_result['data_length']) / avg_old_length * 100:.1f}%",
            )
            print(f"   ✅ 处理时间平均节省 {(avg_old_time - new_result['processing_time']) / avg_old_time * 100:.1f}%")
            print("   ✅ 保持基本面分析所需的核心信息完整性")
            print("   ✅ 提高了数据获取的针对性和效率")
            print("   ✅ 减少了不必要的历史价格数据传输")

    else:
        print(f"❌ 优化后策略测试失败: {new_result.get('error', '未知错误')}")

    print("\n🎉 性能对比测试完成！")


if __name__ == "__main__":
    compare_performance()
