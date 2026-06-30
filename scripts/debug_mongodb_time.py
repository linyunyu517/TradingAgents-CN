"""
调试脚本：检查 MongoDB 中存储的时间格式
直接使用 pymongo 同步客户端，避免异步初始化问题
"""

import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_mongodb_time():
    """检查 MongoDB 中的时间存储格式"""
    try:
        # 从环境变量读取 MongoDB 连接信息
        from dotenv import load_dotenv

        load_dotenv()

        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db_name = os.getenv("MONGO_DB", "tradingagents")

        print(f"连接 MongoDB: {mongo_uri}")
        print(f"数据库: {mongo_db_name}")
        print()

        # 创建同步 MongoDB 客户端
        client = MongoClient(mongo_uri)
        db = client[mongo_db_name]

        # 查询指定的任务记录
        task_id = "aa1d58b3-b73c-4a51-b807-99cfbd46a0ae"
        task = db.analysis_tasks.find_one({"task_id": task_id})

        if not task:
            # 如果找不到，查询最近的一条任务记录
            print(f"⚠️ 未找到任务 {task_id}，查询最近的任务...")
            task = db.analysis_tasks.find_one({}, sort=[("created_at", -1)])

        if not task:
            print("❌ 没有找到任务记录")
            return

        print("=" * 80)
        print("📋 MongoDB 任务记录分析")
        print("=" * 80)
        print(f"\n任务ID: {task.get('task_id')}")
        print(f"股票代码: {task.get('stock_code') or task.get('symbol')}")
        print(f"状态: {task.get('status')}")

        # 检查时间字段
        time_fields = ["created_at", "started_at", "completed_at"]

        for field in time_fields:
            value = task.get(field)
            if value:
                print(f"\n{'=' * 80}")
                print(f"字段: {field}")
                print(f"{'=' * 80}")
                print(f"原始值: {value}")
                print(f"类型: {type(value)}")

                if isinstance(value, datetime):
                    print(f"是否带时区: {value.tzinfo is not None}")
                    if value.tzinfo:
                        print(f"时区信息: {value.tzinfo}")

                    # 测试不同的序列化方式
                    print("\n序列化测试:")
                    print(f"  .isoformat(): {value.isoformat()}")

                    # 如果是 naive datetime，尝试添加时区
                    if value.tzinfo is None:
                        print("\n  ⚠️ 这是 naive datetime（没有时区信息）")

                        # 方法1：假设是 UTC 时间
                        utc_time = value.replace(tzinfo=timezone.utc)
                        print(f"  假设为UTC: {utc_time.isoformat()}")

                        # 方法2：假设是 UTC+8 时间
                        from datetime import timedelta

                        china_tz = timezone(timedelta(hours=8))
                        china_time = value.replace(tzinfo=china_tz)
                        print(f"  假设为UTC+8: {china_time.isoformat()}")
                    else:
                        print("\n  ✅ 这是 aware datetime（带时区信息）")

        print(f"\n{'=' * 80}")
        print("💡 建议:")
        print("=" * 80)
        print("如果时间字段是 naive datetime，需要在序列化时添加时区信息")
        print("通常 MongoDB 存储的是 UTC 时间，但应用层可能按本地时间（UTC+8）存储")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    check_mongodb_time()
