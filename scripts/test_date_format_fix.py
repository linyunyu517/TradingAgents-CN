"""
测试脚本：验证日期格式修复

这个脚本会：
1. 测试修复前后的日期格式
2. 验证 MongoDB 查询是否正常
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_date_format():
    """测试日期格式"""

    print("=" * 80)
    print("测试：日期格式修复")
    print("=" * 80)

    limit = 100

    # 修复前的格式（错误）
    print("\n❌ 修复前的格式（错误）：")
    end_date_wrong = datetime.now().strftime("%Y-%m-%d")
    start_date_wrong = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y-%m-d")  # 错误格式

    print(f"  end_date: {end_date_wrong}")
    print(f"  start_date: {start_date_wrong}")
    print("  ⚠️ start_date 格式错误！应该是 YYYY-MM-DD，实际是 YYYY-MM-d")

    # 修复后的格式（正确）
    print("\n✅ 修复后的格式（正确）：")
    end_date_correct = datetime.now().strftime("%Y-%m-%d")
    start_date_correct = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y-%m-%d")  # 正确格式

    print(f"  end_date: {end_date_correct}")
    print(f"  start_date: {start_date_correct}")
    print("  ✅ start_date 格式正确！")

    print("\n" + "=" * 80)


async def test_mongodb_query():
    """测试 MongoDB 查询"""

    print("\n测试：MongoDB 查询")
    print("=" * 80)

    from motor.motor_asyncio import AsyncIOMotorClient

    from app.core.config import settings

    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.stock_daily_quotes

    symbol = "601288"
    code6 = symbol.zfill(6)
    period = "daily"
    limit = 100

    # 使用正确的日期格式
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y-%m-%d")

    print("\n📊 查询参数：")
    print(f"  - 股票代码: {code6}")
    print(f"  - 周期: {period}")
    print(f"  - 开始日期: {start_date}")
    print(f"  - 结束日期: {end_date}")

    query = {"symbol": code6, "period": period, "trade_date": {"$gte": start_date, "$lte": end_date}}

    print(f"\n🔍 查询条件: {query}")

    cursor = collection.find(query).sort("trade_date", 1)
    data = await cursor.to_list(length=None)

    if data:
        print(f"\n✅ 查询成功！找到 {len(data)} 条数据")
        print(f"  日期范围: {data[0].get('trade_date')} ~ {data[-1].get('trade_date')}")
    else:
        print("\n❌ 查询失败！未找到数据")

    client.close()

    print("\n" + "=" * 80)


async def test_adapter():
    """测试适配器"""

    print("\n测试：MongoDB 适配器")
    print("=" * 80)

    from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

    adapter = get_mongodb_cache_adapter()

    symbol = "601288"
    limit = 100

    # 使用正确的日期格式
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y-%m-%d")

    print("\n📊 查询参数：")
    print(f"  - 股票代码: {symbol}")
    print(f"  - 开始日期: {start_date}")
    print(f"  - 结束日期: {end_date}")

    df = adapter.get_historical_data(symbol, start_date, end_date, period="daily")

    if df is not None and not df.empty:
        print(f"\n✅ 适配器查询成功！找到 {len(df)} 条数据")
        print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    else:
        print("\n❌ 适配器查询失败！未找到数据")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    import asyncio

    # 测试日期格式
    test_date_format()

    # 测试 MongoDB 查询
    asyncio.run(test_mongodb_query())

    # 测试适配器
    asyncio.run(test_adapter())

    print("\n✅ 所有测试完成！")
