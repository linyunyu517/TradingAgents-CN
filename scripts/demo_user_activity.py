#!/usr/bin/env python3
"""
用户活动记录系统演示脚本
演示如何使用用户活动记录功能
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

try:
    from web.utils.user_activity_logger import UserActivityLogger

    print("✅ 成功导入用户活动记录器")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)


def demo_user_activities():
    """演示用户活动记录功能"""
    print("🚀 用户活动记录系统演示")
    print("=" * 50)

    # 创建活动记录器实例
    logger = UserActivityLogger()

    # 模拟用户登录
    print("\n1. 模拟用户登录...")
    logger.log_login(username="demo_user", success=True)
    time.sleep(1)

    # 模拟页面访问
    print("2. 模拟页面访问...")
    logger.log_page_visit(page_name="📊 股票分析", page_params={"access_method": "sidebar_navigation"})
    time.sleep(1)

    # 模拟分析请求
    print("3. 模拟分析请求...")
    start_time = time.time()
    logger.log_analysis_request(stock_code="AAPL", analysis_type="美股_深度分析", success=True)
    time.sleep(2)  # 模拟分析耗时

    # 记录分析完成
    duration_ms = int((time.time() - start_time) * 1000)
    logger.log_activity(
        action_type="analysis",
        action_name="analysis_completed",
        success=True,
        duration_ms=duration_ms,
        details={"stock_code": "AAPL", "result_sections": ["基本信息", "技术分析", "基本面分析", "风险评估"]},
    )

    # 模拟配置更改
    print("4. 模拟配置更改...")
    logger.log_config_change(
        config_type="model_settings",
        changes={
            "default_model": {"old": "qwen-turbo", "new": "qwen-plus"},
            "change_reason": "performance_optimization",
        },
    )
    time.sleep(1)

    # 模拟数据导出
    print("5. 模拟数据导出...")
    logger.log_data_export(
        export_type="analysis_results",
        data_info={
            "stock_code": "AAPL",
            "file_format": "pdf",
            "file_size_mb": 2.5,
            "export_sections": ["summary", "charts", "recommendations"],
        },
        success=True,
    )
    time.sleep(1)

    # 模拟用户登出
    print("6. 模拟用户登出...")
    logger.log_logout(username="demo_user")

    print("\n✅ 演示完成！")

    # 显示统计信息
    print("\n📊 活动统计:")
    stats = logger.get_activity_statistics(days=1)
    print(f"   总活动数: {stats['total_activities']}")
    print(f"   活跃用户: {stats['unique_users']}")
    print(f"   成功率: {stats['success_rate']:.1f}%")

    print("\n📋 按类型统计:")
    for activity_type, count in stats["activity_types"].items():
        print(f"   {activity_type}: {count}")

    # 显示最近的活动
    print("\n📝 最近的活动记录:")
    recent_activities = logger.get_user_activities(limit=5)
    for i, activity in enumerate(recent_activities, 1):
        timestamp = datetime.fromtimestamp(activity["timestamp"])
        success_icon = "✅" if activity.get("success", True) else "❌"
        print(f"   {i}. {success_icon} {timestamp.strftime('%H:%M:%S')} - {activity['action_name']}")


def demo_activity_management():
    """演示活动管理功能"""
    print("\n🔧 活动管理功能演示")
    print("=" * 50)

    logger = UserActivityLogger()

    # 获取活动统计
    print("\n📈 获取活动统计...")
    stats = logger.get_activity_statistics(days=7)
    print(f"   过去7天总活动数: {stats['total_activities']}")
    print(f"   活跃用户数: {stats['unique_users']}")
    print(f"   平均成功率: {stats['success_rate']:.1f}%")

    # 按用户统计
    if stats["user_activities"]:
        print("\n👥 用户活动排行:")
        for username, count in list(stats["user_activities"].items())[:5]:
            print(f"   {username}: {count} 次活动")

    # 按日期统计
    if stats["daily_activities"]:
        print("\n📅 每日活动统计:")
        for date_str, count in list(stats["daily_activities"].items())[-3:]:
            print(f"   {date_str}: {count} 次活动")

    print("\n✅ 管理功能演示完成！")


def main():
    """主函数"""
    print("🎯 用户活动记录系统完整演示")
    print("=" * 60)

    try:
        # 演示基本功能
        demo_user_activities()

        # 演示管理功能
        demo_activity_management()

        print("\n🎉 所有演示完成！")
        print("\n💡 提示:")
        print("   - 活动记录已保存到 web/data/user_activities/ 目录")
        print("   - 可以使用 scripts/user_activity_manager.py 查看和管理记录")
        print("   - 在Web界面的'📈 历史记录'页面可以查看活动仪表板")

    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
