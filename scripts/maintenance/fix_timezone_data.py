#!/usr/bin/env python3
"""
修复操作日志的时区数据
将UTC时间转换为本地时间
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


async def fix_timezone_data():
    """修复时区数据"""
    print("🔧 修复操作日志时区数据...")

    try:
        # 导入数据库模块
        from app.core.database import get_mongo_db, init_db

        # 初始化数据库
        await init_db()
        print("✅ 数据库连接成功")

        db = get_mongo_db()

        # 查找所有需要修复的日志（UTC时间的特征：小时数在0-7之间，且与当前时间差8小时左右）
        print("\n🔍 查找需要修复的日志...")

        # 获取所有日志
        cursor = db.operation_logs.find().sort("timestamp", 1)
        all_logs = await cursor.to_list(length=None)

        print(f"📋 总共找到 {len(all_logs)} 条日志")

        # 分析哪些是UTC时间
        utc_logs = []
        local_logs = []

        current_local = datetime.datetime.now()
        current_utc = datetime.datetime.utcnow()

        for log in all_logs:
            timestamp = log.get("timestamp")
            if not timestamp:
                continue

            # 判断是否为UTC时间：检查时间是否更接近UTC
            local_diff = abs((timestamp - current_local).total_seconds())
            utc_diff = abs((timestamp - current_utc).total_seconds())

            # 如果时间戳的小时在0-7之间，且更接近UTC时间，则认为是UTC时间
            if timestamp.hour <= 7 and utc_diff < local_diff:
                utc_logs.append(log)
            else:
                local_logs.append(log)

        print("📊 分析结果:")
        print(f"  - UTC时间日志: {len(utc_logs)} 条")
        print(f"  - 本地时间日志: {len(local_logs)} 条")

        if not utc_logs:
            print("✅ 没有需要修复的UTC时间日志")
            return

        # 显示需要修复的日志示例
        print("\n📝 需要修复的日志示例:")
        for i, log in enumerate(utc_logs[:5]):
            timestamp = log.get("timestamp")
            action = log.get("action", "N/A")
            print(f"  {i + 1}. {timestamp} | {action}")

        # 询问是否继续
        print(f"\n⚠️ 将修复 {len(utc_logs)} 条UTC时间日志")
        print("🔧 修复方法：UTC时间 + 8小时 = 本地时间")

        # 自动确认修复（在生产环境中可能需要手动确认）
        confirm = input("是否继续修复？(y/N): ").lower().strip()
        if confirm != "y":
            print("❌ 用户取消修复")
            return

        # 执行修复
        print(f"\n🔧 开始修复 {len(utc_logs)} 条日志...")

        fixed_count = 0
        for log in utc_logs:
            try:
                # 计算本地时间（UTC + 8小时）
                utc_time = log["timestamp"]
                local_time = utc_time + datetime.timedelta(hours=8)

                # 更新数据库
                result = await db.operation_logs.update_one(
                    {"_id": log["_id"]},
                    {
                        "$set": {
                            "timestamp": local_time,
                            "created_at": local_time,
                            "timezone_fixed": True,  # 标记已修复
                            "original_utc_time": utc_time,  # 保留原始时间
                        },
                    },
                )

                if result.modified_count > 0:
                    fixed_count += 1
                    if fixed_count <= 5:  # 只显示前5条的详细信息
                        print(f"  ✅ 修复: {utc_time} -> {local_time}")

            except Exception as e:
                print(f"  ❌ 修复失败: {log.get('_id')} - {e}")

        print("\n🎉 修复完成！")
        print(f"  - 成功修复: {fixed_count} 条")
        print(f"  - 失败: {len(utc_logs) - fixed_count} 条")

        # 验证修复结果
        print("\n🔍 验证修复结果...")
        cursor = db.operation_logs.find().sort("timestamp", -1).limit(5)
        recent_logs = await cursor.to_list(length=5)

        print("📋 最新的5条日志:")
        for i, log in enumerate(recent_logs, 1):
            timestamp = log.get("timestamp")
            action = log.get("action", "N/A")
            fixed = "🔧" if log.get("timezone_fixed") else ""
            print(f"  {i}. {timestamp} | {action} {fixed}")

        print("\n✅ 时区数据修复完成！")
        print("💡 提示：现在前端应该显示正确的本地时间了")

    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(fix_timezone_data())
