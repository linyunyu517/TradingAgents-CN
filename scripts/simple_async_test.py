#!/usr/bin/env python3
"""
简单的异步进度跟踪测试
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_basic_functionality():
    """测试基本功能"""
    print("🧪 测试异步进度跟踪基本功能...")

    try:
        from web.utils.async_progress_tracker import AsyncProgressTracker, get_progress_by_id

        print("✅ 导入成功")

        # 创建跟踪器
        analysis_id = "test_simple_123"
        tracker = AsyncProgressTracker(
            analysis_id=analysis_id, analysts=["market", "fundamentals"], research_depth=2, llm_provider="dashscope",
        )
        print(f"✅ 创建跟踪器成功: {analysis_id}")

        # 更新进度
        tracker.update_progress("🚀 开始股票分析...")
        print("✅ 更新进度成功")

        # 获取进度
        progress = get_progress_by_id(analysis_id)
        if progress:
            print(f"✅ 获取进度成功: {progress['progress_percentage']:.1f}%")
            print(f"   当前步骤: {progress['current_step_name']}")
            print(f"   最后消息: {progress['last_message']}")
        else:
            print("❌ 获取进度失败")

        # 模拟几个步骤
        test_messages = [
            "[进度] 🔍 验证股票代码并预获取数据...",
            "[进度] 检查环境变量配置...",
            "📊 [模块开始] market_analyst - 股票: 000858",
            "📊 [模块完成] market_analyst - ✅ 成功 - 股票: 000858, 耗时: 41.73s",
            "✅ 分析完成",
        ]

        for i, message in enumerate(test_messages):
            print(f"\n--- 步骤 {i + 2} ---")
            tracker.update_progress(message)

            progress = get_progress_by_id(analysis_id)
            if progress:
                print(
                    f"📊 步骤 {progress['current_step'] + 1}/{progress['total_steps']} ({progress['progress_percentage']:.1f}%)",
                )
                print(f"   {progress['current_step_name']}: {message[:50]}...")

            time.sleep(0.5)

        # 最终状态
        final_progress = get_progress_by_id(analysis_id)
        if final_progress:
            print("\n🎯 最终状态:")
            print(f"   状态: {final_progress['status']}")
            print(f"   进度: {final_progress['progress_percentage']:.1f}%")
            print(f"   总耗时: {final_progress['elapsed_time']:.1f}秒")

        print("\n✅ 测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_basic_functionality()
