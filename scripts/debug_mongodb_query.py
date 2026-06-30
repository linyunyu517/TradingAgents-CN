"""
调试脚本：测试 MongoDB 查询条件

这个脚本会：
1. 模拟实际的查询条件
2. 测试不同的日期格式
3. 找出查询失败的原因
"""

import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient


async def test_mongodb_query():
    """测试 MongoDB 查询"""

    print("=" * 80)
    print("测试：MongoDB 查询条件")
    print("=" * 80)

    # 连接 MongoDB
    from app.core.config import settings

    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.stock_daily_quotes

    symbol = "601288"
    code6 = symbol.zfill(6)
    period = "daily"

    print("\n📊 基本信息：")
    print(f"  - 股票代码: {symbol}")
    print(f"  - 6位代码: {code6}")
    print(f"  - 周期: {period}")

    # 测试1：不带日期条件的查询
    print("\n🔍 测试1：不带日期条件")
    query1 = {"symbol": code6, "period": period}
    print(f"  查询条件: {query1}")

    cursor1 = collection.find(query1).limit(5)
    data1 = await cursor1.to_list(length=5)

    if data1:
        print(f"  ✅ 找到 {len(data1)} 条数据")
        for i, doc in enumerate(data1, 1):
            print(f"    {i}. trade_date={doc.get('trade_date')} (类型: {type(doc.get('trade_date')).__name__})")
    else:
        print("  ❌ 未找到数据")

    # 测试2：使用字符串日期
    print("\n🔍 测试2：使用字符串日期")
    start_date_str = "2024-10-01"
    end_date_str = "2024-11-30"

    query2 = {"symbol": code6, "period": period, "trade_date": {"$gte": start_date_str, "$lte": end_date_str}}
    print(f"  查询条件: {query2}")

    cursor2 = collection.find(query2).limit(5)
    data2 = await cursor2.to_list(length=5)

    if data2:
        print(f"  ✅ 找到 {len(data2)} 条数据")
        for i, doc in enumerate(data2, 1):
            print(f"    {i}. trade_date={doc.get('trade_date')}")
    else:
        print("  ❌ 未找到数据")

    # 测试3：使用 datetime 对象
    print("\n🔍 测试3：使用 datetime 对象")
    start_date_dt = datetime(2024, 10, 1)
    end_date_dt = datetime(2024, 11, 30)

    query3 = {"symbol": code6, "period": period, "trade_date": {"$gte": start_date_dt, "$lte": end_date_dt}}
    print(f"  查询条件: {query3}")

    cursor3 = collection.find(query3).limit(5)
    data3 = await cursor3.to_list(length=5)

    if data3:
        print(f"  ✅ 找到 {len(data3)} 条数据")
        for i, doc in enumerate(data3, 1):
            print(f"    {i}. trade_date={doc.get('trade_date')}")
    else:
        print("  ❌ 未找到数据（datetime 对象无法匹配字符串字段）")

    # 测试4：检查实际调用时传入的参数类型
    print("\n🔍 测试4：模拟实际调用")

    # 模拟 get_historical_data 的调用
    from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

    adapter = get_mongodb_cache_adapter()

    # 测试不同的日期格式
    test_cases = [
        ("字符串日期", "2024-10-01", "2024-11-30"),
        ("None", None, None),
    ]

    for test_name, start, end in test_cases:
        print(f"\n  测试场景：{test_name}")
        print(f"    start_date={start} (类型: {type(start).__name__})")
        print(f"    end_date={end} (类型: {type(end).__name__})")

        df = adapter.get_historical_data(symbol, start, end, period="daily")

        if df is not None and not df.empty:
            print(f"    ✅ 成功获取 {len(df)} 条数据")
        else:
            print("    ❌ 未获取到数据")

    # 测试5：检查 MongoDB 中实际存储的日期类型
    print("\n🔍 测试5：检查 MongoDB 中的日期字段类型")

    cursor5 = collection.find({"symbol": code6, "period": period}).limit(1)
    sample = await cursor5.to_list(length=1)

    if sample:
        doc = sample[0]
        trade_date = doc.get("trade_date")
        print(f"  trade_date 值: {trade_date}")
        print(f"  trade_date 类型: {type(trade_date).__name__}")

        # 如果是字符串，测试字符串比较
        if isinstance(trade_date, str):
            print("\n  ✅ trade_date 是字符串类型")
            print("  字符串比较测试：")
            print(f"    '{trade_date}' >= '2024-10-01': {trade_date >= '2024-10-01'}")
            print(f"    '{trade_date}' <= '2024-11-30': {trade_date <= '2024-11-30'}")

    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)

    # 关闭连接
    client.close()


if __name__ == "__main__":
    asyncio.run(test_mongodb_query())
