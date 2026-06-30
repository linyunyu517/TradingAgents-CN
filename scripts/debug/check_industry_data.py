#!/usr/bin/env python3
"""
检查数据库中的实际行业数据
"""

import asyncio

from app.core.database import get_mongo_db, init_db


async def check_industries():
    """检查数据库中的行业数据"""
    await init_db()
    db = get_mongo_db()
    collection = db["stock_basic_info"]

    print("🔍 检查数据库中的行业数据...")
    print("=" * 50)

    # 获取所有不同的行业
    industries = await collection.distinct("industry")
    industries = [ind for ind in industries if ind]  # 过滤空值
    industries.sort()

    print(f"📊 数据库中的行业总数: {len(industries)}")
    print("\n📋 所有行业列表:")
    for i, industry in enumerate(industries):
        print(f"  {i + 1:2d}. {industry}")

    # 检查银行相关行业
    bank_industries = [ind for ind in industries if "银行" in ind]
    print(f"\n🏦 银行相关行业: {bank_industries}")

    # 统计每个行业的股票数量
    print("\n📈 各行业股票数量统计:")
    industry_counts = {}
    async for doc in collection.find({}, {"industry": 1}):
        industry = doc.get("industry")
        if industry:
            industry_counts[industry] = industry_counts.get(industry, 0) + 1

    # 按股票数量排序
    sorted_industries = sorted(industry_counts.items(), key=lambda x: x[1], reverse=True)

    for industry, count in sorted_industries[:20]:  # 显示前20个
        print(f"  {industry}: {count}只")

    if len(sorted_industries) > 20:
        print(f"  ... 还有 {len(sorted_industries) - 20} 个行业")

    return industries


if __name__ == "__main__":
    asyncio.run(check_industries())
