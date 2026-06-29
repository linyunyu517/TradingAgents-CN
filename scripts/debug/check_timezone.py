#!/usr/bin/env python3
"""
检查系统时区信息
"""

import datetime
import os
import sys
import time


def check_timezone():
    print("🕐 系统时区信息:")
    print(f"当前时间: {datetime.datetime.now()}")
    print(f"UTC时间: {datetime.datetime.utcnow()}")
    print(f"时区偏移: {time.timezone}秒 ({time.timezone / 3600}小时)")
    print(f"时区名称: {time.tzname}")
    print(f"夏令时: {time.daylight}")

    # 检查环境变量
    tz_env = os.environ.get("TZ", "未设置")
    print(f"TZ环境变量: {tz_env}")

    # 计算时差
    local_time = datetime.datetime.now()
    utc_time = datetime.datetime.utcnow()
    diff = local_time - utc_time
    print(f"本地时间与UTC时差: {diff}")

    # 检查MongoDB时间
    print("\n🗄️ 检查MongoDB中的时间:")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import asyncio

        from app.core.database import get_mongo_db

        async def check_mongo_time():
            db = get_mongo_db()
            # 插入一个测试文档来检查MongoDB的时间
            test_doc = {
                "test": True,
                "python_now": datetime.datetime.now(),
                "python_utcnow": datetime.datetime.utcnow(),
                "created_at": datetime.datetime.now(),
            }

            result = await db.timezone_test.insert_one(test_doc)
            print(f"✅ 插入测试文档成功: {result.inserted_id}")

            # 读取文档查看时间
            doc = await db.timezone_test.find_one({"_id": result.inserted_id})
            print("📄 MongoDB中存储的时间:")
            print(f"  python_now: {doc['python_now']}")
            print(f"  python_utcnow: {doc['python_utcnow']}")
            print(f"  created_at: {doc['created_at']}")

            # 清理测试文档
            await db.timezone_test.delete_one({"_id": result.inserted_id})
            print("🗑️ 清理测试文档完成")

        asyncio.run(check_mongo_time())

    except Exception as e:
        print(f"❌ MongoDB时间检查失败: {e}")


if __name__ == "__main__":
    check_timezone()
