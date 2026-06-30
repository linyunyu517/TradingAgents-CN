#!/usr/bin/env python3
"""
测试时区修复
"""

import asyncio
import datetime
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import get_mongo_db, init_db
from app.models.operation_log import ActionType
from app.services.operation_log_service import log_operation


async def test_timezone_fix():
    """测试时区修复"""
    print("🕐 测试时区修复...")

    try:
        # 初始化数据库
        await init_db()
        print("✅ 数据库初始化成功")

        # 显示当前时间信息
        now_local = datetime.datetime.now()
        now_utc = datetime.datetime.utcnow()
        print(f"📅 当前本地时间: {now_local}")
        print(f"📅 当前UTC时间: {now_utc}")
        print(f"📅 时差: {now_local - now_utc}")

        # 创建一个测试日志
        print("\n📝 创建测试日志...")
        log_id = await log_operation(
            user_id="admin",
            username="admin",
            action_type=ActionType.SYSTEM_SETTINGS,
            action="时区测试",
            details={"test_type": "timezone_fix", "local_time": now_local.isoformat(), "utc_time": now_utc.isoformat()},
            success=True,
            duration_ms=100,
            ip_address="127.0.0.1",
            user_agent="Timezone Test",
        )
        print(f"✅ 创建日志成功，ID: {log_id}")

        # 直接从数据库查询这条记录
        print("\n🔍 从数据库查询记录...")
        db = get_mongo_db()
        from bson import ObjectId

        doc = await db.operation_logs.find_one({"_id": ObjectId(log_id)})
        if doc:
            print("📄 数据库中存储的时间:")
            print(f"  timestamp: {doc['timestamp']}")
            print(f"  created_at: {doc['created_at']}")
            print(f"  action: {doc['action']}")

            # 比较时间
            stored_time = doc["timestamp"]
            print("\n⏰ 时间比较:")
            print(f"  存储时间: {stored_time}")
            print(f"  本地时间: {now_local}")
            print(f"  UTC时间: {now_utc}")

            # 判断存储的是哪种时间
            if abs((stored_time - now_local).total_seconds()) < 60:
                print("✅ 存储的是本地时间")
            elif abs((stored_time - now_utc).total_seconds()) < 60:
                print("⚠️ 存储的是UTC时间")
            else:
                print("❓ 存储的时间不明确")
        else:
            print("❌ 未找到记录")

        # 测试API返回的时间格式
        print("\n🌐 测试API返回格式...")
        from app.models.operation_log import OperationLogQuery
        from app.services.operation_log_service import get_operation_log_service

        service = get_operation_log_service()
        query = OperationLogQuery(page=1, page_size=1)
        logs, _total = await service.get_logs(query)

        if logs:
            log = logs[0]
            print(f"📋 API返回的时间: {log.timestamp}")
            print(f"📋 时间类型: {type(log.timestamp)}")

            # 如果是字符串，尝试解析
            if isinstance(log.timestamp, str):
                try:
                    parsed_time = datetime.datetime.fromisoformat(log.timestamp.replace("Z", ""))
                    print(f"📋 解析后的时间: {parsed_time}")
                except Exception:
                    print("❌ 时间字符串解析失败")

        print("\n🎉 时区测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_timezone_fix())
