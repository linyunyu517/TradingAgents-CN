#!/usr/bin/env python3
"""
调试bulk_write问题
检查为什么数据没有真正写入
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from pymongo import ReplaceOne

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_database, init_database

# 设置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def debug_bulk_write_issue():
    """调试bulk_write问题"""

    print("🔍 调试bulk_write问题")
    print("=" * 60)

    try:
        # 1. 初始化数据库
        print("1️⃣ 初始化数据库")
        await init_database()
        db = get_database()
        collection = db.stock_daily_quotes
        print("   ✅ 数据库初始化成功")

        # 2. 准备测试数据
        print("\n2️⃣ 准备测试数据")
        test_symbol = "TEST001"
        test_records = [
            {
                "symbol": test_symbol,
                "full_symbol": f"{test_symbol}.SZ",
                "market": "CN",
                "trade_date": "2024-01-02",
                "period": "daily",
                "data_source": "test",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000000,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "version": 1,
            },
            {
                "symbol": test_symbol,
                "full_symbol": f"{test_symbol}.SZ",
                "market": "CN",
                "trade_date": "2024-01-03",
                "period": "daily",
                "data_source": "test",
                "open": 10.2,
                "high": 10.8,
                "low": 10.0,
                "close": 10.5,
                "volume": 1200000,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "version": 1,
            },
        ]

        print(f"   准备了 {len(test_records)} 条测试记录")

        # 3. 检查数据库状态（保存前）
        print("\n3️⃣ 检查数据库状态（保存前）")
        before_count = await collection.count_documents({"symbol": test_symbol})
        print(f"   {test_symbol} 记录数: {before_count}")

        # 4. 创建bulk_write操作
        print("\n4️⃣ 创建bulk_write操作")
        operations = []
        for record in test_records:
            filter_doc = {
                "symbol": record["symbol"],
                "trade_date": record["trade_date"],
                "data_source": record["data_source"],
                "period": record["period"],
            }

            operations.append(ReplaceOne(filter=filter_doc, replacement=record, upsert=True))

            print(f"   操作: {filter_doc}")

        print(f"   ✅ 创建了 {len(operations)} 个操作")

        # 5. 执行bulk_write
        print("\n5️⃣ 执行bulk_write")
        try:
            result = await collection.bulk_write(operations)
            print("   ✅ bulk_write执行成功")
            print(f"     插入数量: {result.upserted_count}")
            print(f"     更新数量: {result.modified_count}")
            print(f"     匹配数量: {result.matched_count}")

            if hasattr(result, "upserted_ids"):
                print(f"     新插入的ID: {result.upserted_ids}")

        except Exception as e:
            print(f"   ❌ bulk_write执行失败: {e}")
            import traceback

            traceback.print_exc()
            return

        # 6. 检查数据库状态（保存后）
        print("\n6️⃣ 检查数据库状态（保存后）")
        after_count = await collection.count_documents({"symbol": test_symbol})
        print(f"   {test_symbol} 记录数: {after_count}")
        print(f"   新增记录数: {after_count - before_count}")

        # 7. 查询保存的数据
        print("\n7️⃣ 查询保存的数据")
        saved_records = []
        async for record in collection.find({"symbol": test_symbol}).sort("trade_date", 1):
            saved_records.append(record)

        print(f"   查询到 {len(saved_records)} 条记录:")
        for record in saved_records:
            trade_date = record.get("trade_date", "N/A")
            close = record.get("close", "N/A")
            data_source = record.get("data_source", "N/A")
            print(f"     {trade_date}: 收盘={close}, 数据源={data_source}")

        # 8. 清理测试数据
        print("\n8️⃣ 清理测试数据")
        delete_result = await collection.delete_many({"symbol": test_symbol})
        print(f"   删除了 {delete_result.deleted_count} 条测试记录")

    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("🎯 调试完成！")


if __name__ == "__main__":
    asyncio.run(debug_bulk_write_issue())
