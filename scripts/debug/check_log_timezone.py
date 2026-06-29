#!/usr/bin/env python3
"""
检查操作日志的时区问题
"""

import asyncio
import datetime
import os
import sys

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def check_log_timezone():
    """检查操作日志的时区问题"""
    print("🕐 检查操作日志时区问题...")

    try:
        # 导入数据库模块
        from app.core.database import get_mongo_db, init_db
        from app.models.operation_log import ActionType
        from app.services.operation_log_service import log_operation

        # 初始化数据库
        await init_db()
        print("✅ 数据库连接成功")

        # 显示当前时间信息
        now_local = datetime.datetime.now()
        now_utc = datetime.datetime.utcnow()
        print(f"📅 当前本地时间: {now_local}")
        print(f"📅 当前UTC时间: {now_utc}")
        print(f"📅 时差: {now_local - now_utc}")

        # 检查现有日志的时间
        print("\n🔍 检查现有操作日志:")
        db = get_mongo_db()
        cursor = db.operation_logs.find().sort("timestamp", -1).limit(5)
        logs = await cursor.to_list(length=5)

        if logs:
            print(f"📋 找到 {len(logs)} 条最新日志:")
            for i, log in enumerate(logs, 1):
                stored_time = log.get("timestamp")
                action = log.get("action", "N/A")
                username = log.get("username", "N/A")

                print(f"  {i}. {stored_time} | {username} | {action}")

                if stored_time:
                    # 计算与当前时间的差异
                    local_diff = abs((stored_time - now_local).total_seconds())
                    utc_diff = abs((stored_time - now_utc).total_seconds())

                    if local_diff < 3600:  # 1小时内
                        print(f"     ✅ 接近本地时间 (差{local_diff:.0f}秒)")
                    elif utc_diff < 3600:  # 1小时内
                        print(f"     ⚠️ 接近UTC时间 (差{utc_diff:.0f}秒)")
                    else:
                        print("     ❓ 时间差异较大")
        else:
            print("📋 没有找到操作日志")

        # 创建一个新的测试日志
        print(f"\n📝 创建新的测试日志 (当前时间: {now_local})...")
        log_id = await log_operation(
            user_id="admin",
            username="admin",
            action_type=ActionType.SYSTEM_SETTINGS,
            action="时区测试 - 检查时间存储",
            details={"test_time": now_local.isoformat(), "test_utc": now_utc.isoformat(), "timezone": "Asia/Shanghai"},
            success=True,
            duration_ms=50,
            ip_address="127.0.0.1",
            user_agent="Timezone Test Script",
        )
        print(f"✅ 创建测试日志成功，ID: {log_id}")

        # 立即查询这条新日志
        print("\n🔍 查询刚创建的日志:")
        from bson import ObjectId

        new_log = await db.operation_logs.find_one({"_id": ObjectId(log_id)})

        if new_log:
            stored_time = new_log["timestamp"]
            print(f"📄 存储的时间: {stored_time}")
            print(f"📄 创建时间: {now_local}")

            time_diff = (stored_time - now_local).total_seconds()
            print(f"📄 时间差: {time_diff:.2f}秒")

            if abs(time_diff) < 60:  # 1分钟内
                print("✅ 时间存储正确 (本地时间)")
            elif abs(time_diff - 28800) < 60:  # 接近8小时差
                print("⚠️ 存储的是UTC时间，需要修复")
            else:
                print("❓ 时间差异不明确")

        # 测试API返回的格式
        print("\n🌐 测试API返回格式:")
        from app.models.operation_log import OperationLogQuery
        from app.services.operation_log_service import get_operation_log_service

        service = get_operation_log_service()
        query = OperationLogQuery(page=1, page_size=1)
        api_logs, _total = await service.get_logs(query)

        if api_logs:
            api_log = api_logs[0]
            print(f"📋 API返回时间: {api_log.timestamp}")
            print(f"📋 时间类型: {type(api_log.timestamp)}")

            # 如果是datetime对象，检查时区
            if isinstance(api_log.timestamp, datetime.datetime):
                print(f"📋 时区信息: {api_log.timestamp.tzinfo}")

        print("\n🎉 时区检查完成！")

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_log_timezone())
