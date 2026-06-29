#!/usr/bin/env python3
"""
测试时间估算算法
验证不同配置下的预估时间是否合理
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.progress.tracker import RedisProgressTracker


def format_time(seconds):
    """格式化时间显示"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}分{secs}秒"


def test_time_estimation():
    """测试时间估算"""
    print("=" * 80)
    print("📊 时间估算算法测试")
    print("=" * 80)

    # 测试配置（基于实际测试数据）
    test_cases = [
        # (深度, 分析师数量, 模型, 期望时间范围, 实测数据)
        ("快速", 1, "dashscope", "2-4分钟", ""),
        ("快速", 2, "dashscope", "4-5分钟", "实测：4-5分钟"),
        ("快速", 3, "dashscope", "5-6分钟", ""),
        ("基础", 1, "dashscope", "4-6分钟", ""),
        ("基础", 2, "dashscope", "5-6分钟", "实测：5-6分钟"),
        ("基础", 3, "dashscope", "6-8分钟", ""),
        ("标准", 1, "dashscope", "6-10分钟", ""),
        ("标准", 2, "dashscope", "8-12分钟", ""),
        ("标准", 3, "dashscope", "10-15分钟", ""),
        ("深度", 1, "dashscope", "10-15分钟", ""),
        ("深度", 2, "dashscope", "12-18分钟", ""),
        ("深度", 3, "dashscope", "11分钟", "实测：11.02分钟 ✅"),
        ("全面", 1, "dashscope", "15-25分钟", ""),
        ("全面", 2, "dashscope", "20-30分钟", ""),
        ("全面", 3, "dashscope", "25-35分钟", ""),
    ]

    print(f"\n{'深度':<8} {'分析师':<8} {'模型':<12} {'预估时间':<12} {'期望范围':<15} {'实测数据':<20}")
    print("-" * 100)

    for depth, analyst_count, model, expected_range, actual_data in test_cases:
        # 创建虚拟分析师列表
        analysts = ["analyst"] * analyst_count

        # 创建跟踪器（不会真正初始化Redis）
        tracker = RedisProgressTracker(task_id="test", analysts=analysts, research_depth=depth, llm_provider=model)

        # 获取预估时间
        estimated_time = tracker._get_base_total_time()

        # 显示结果
        print(
            f"{depth:<8} {analyst_count:<8} {model:<12} {format_time(estimated_time):<12} {expected_range:<15} {actual_data:<20}",
        )

    print("\n" + "=" * 80)
    print("✅ 测试完成！")
    print("=" * 80)

    # 特别测试：用户的实际场景
    print("\n" + "=" * 80)
    print("🎯 用户实际场景测试")
    print("=" * 80)

    print("\n场景：4级深度分析 + 3个分析师（市场、基本面、新闻）")
    tracker = RedisProgressTracker(
        task_id="test", analysts=["market", "fundamentals", "news"], research_depth="深度", llm_provider="dashscope",
    )
    estimated_time = tracker._get_base_total_time()
    print(f"预估时间：{format_time(estimated_time)}")
    print("期望范围：10-15分钟（前端显示）")

    # 测试不同模型的影响
    print("\n" + "=" * 80)
    print("🚀 模型速度影响测试（3级标准分析 + 2个分析师）")
    print("=" * 80)

    for model in ["dashscope", "deepseek", "google"]:
        tracker = RedisProgressTracker(
            task_id="test", analysts=["market", "fundamentals"], research_depth="标准", llm_provider=model,
        )
        estimated_time = tracker._get_base_total_time()
        print(f"{model:<12}: {format_time(estimated_time)}")


if __name__ == "__main__":
    test_time_estimation()
