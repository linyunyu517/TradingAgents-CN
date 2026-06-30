"""
调试脚本：检查 MongoDB 中 601288 的 daily 数据

这个脚本会：
1. 连接到 MongoDB
2. 查询 stock_daily_quotes 集合
3. 检查 601288 的数据是否存在
4. 显示查询条件和结果
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient


async def debug_mongodb_daily_data():
    """调试 MongoDB daily 数据"""

    print("=" * 80)
    print("调试：MongoDB daily 数据查询")
    print("=" * 80)

    # 连接 MongoDB
    from app.core.config import settings

    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.stock_daily_quotes

    symbol = "601288"
    code6 = symbol.zfill(6)

    print("\n📊 查询参数：")
    print(f"  - 股票代码: {symbol}")
    print(f"  - 6位代码: {code6}")
    print("  - 集合名称: stock_daily_quotes")

    # 1. 检查集合是否存在
    collections = await db.list_collection_names()
    print("\n📋 数据库中的集合：")
    for coll in collections:
        print(f"  - {coll}")

    if "stock_daily_quotes" not in collections:
        print("\n❌ 集合 stock_daily_quotes 不存在！")
        return

    # 2. 查询所有 601288 的数据（不限制 period）
    print(f"\n🔍 查询1：所有 {code6} 的数据（不限制 period）")
    query1 = {"symbol": code6}
    print(f"  查询条件: {query1}")

    cursor1 = collection.find(query1).limit(5)
    data1 = await cursor1.to_list(length=5)

    if data1:
        print(f"  ✅ 找到 {len(data1)} 条数据（显示前5条）：")
        for i, doc in enumerate(data1, 1):
            print(
                f"    {i}. trade_date={doc.get('trade_date')}, period={doc.get('period')}, "
                f"close={doc.get('close')}, data_source={doc.get('data_source')}",
            )
    else:
        print("  ❌ 未找到任何数据")

    # 3. 查询 period="daily" 的数据
    print(f"\n🔍 查询2：{code6} 的 daily 数据")
    query2 = {"symbol": code6, "period": "daily"}
    print(f"  查询条件: {query2}")

    cursor2 = collection.find(query2).limit(5)
    data2 = await cursor2.to_list(length=5)

    if data2:
        print(f"  ✅ 找到 {len(data2)} 条数据（显示前5条）：")
        for i, doc in enumerate(data2, 1):
            print(
                f"    {i}. trade_date={doc.get('trade_date')}, close={doc.get('close')}, "
                f"data_source={doc.get('data_source')}",
            )
    else:
        print("  ❌ 未找到任何 daily 数据")

    # 4. 统计不同 period 的数据量
    print(f"\n📊 统计：{code6} 各周期的数据量")

    pipeline = [
        {"$match": {"symbol": code6}},
        {"$group": {"_id": "$period", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]

    cursor3 = collection.aggregate(pipeline)
    stats = await cursor3.to_list(length=None)

    if stats:
        print("  周期统计：")
        for stat in stats:
            print(f"    - {stat['_id']}: {stat['count']} 条")
    else:
        print("  ❌ 没有任何数据")

    # 5. 检查索引
    print("\n🔍 集合索引：")
    indexes = await collection.list_indexes().to_list(length=None)
    for idx in indexes:
        print(f"  - {idx.get('name')}: {idx.get('key')}")

    # 6. 查询最近的数据
    print(f"\n🔍 查询3：{code6} 最近的数据（不限制 period）")
    cursor4 = collection.find({"symbol": code6}).sort("trade_date", -1).limit(5)
    data4 = await cursor4.to_list(length=5)

    if data4:
        print(f"  ✅ 最近的 {len(data4)} 条数据：")
        for i, doc in enumerate(data4, 1):
            print(f"    {i}. trade_date={doc.get('trade_date')}, period={doc.get('period')}, close={doc.get('close')}")
    else:
        print("  ❌ 未找到任何数据")

    # 7. 检查 period 字段的所有可能值
    print("\n📊 所有股票的 period 字段值：")
    pipeline2 = [{"$group": {"_id": "$period", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]

    cursor5 = collection.aggregate(pipeline2)
    all_periods = await cursor5.to_list(length=None)

    if all_periods:
        print("  所有 period 值：")
        for period in all_periods:
            print(f"    - '{period['_id']}': {period['count']} 条")
    else:
        print("  ❌ 没有任何数据")

    print("\n" + "=" * 80)
    print("调试完成！")
    print("=" * 80)

    # 关闭连接
    client.close()


if __name__ == "__main__":
    asyncio.run(debug_mongodb_daily_data())
