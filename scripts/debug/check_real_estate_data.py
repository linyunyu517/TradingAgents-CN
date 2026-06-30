#!/usr/bin/env python3
"""
检查房地产行业的数据
"""

import asyncio

from app.core.database import get_mongo_db, init_db


async def check_real_estate():
    """检查房地产行业的数据"""
    await init_db()
    db = get_mongo_db()
    collection = db["stock_basic_info"]

    print("🏠 检查房地产行业数据...")
    print("=" * 50)

    # 1. 查找所有包含"房地产"的行业
    real_estate_industries = []
    async for doc in collection.find({"industry": {"$regex": "房地产", "$options": "i"}}, {"industry": 1}):
        industry = doc.get("industry")
        if industry and industry not in real_estate_industries:
            real_estate_industries.append(industry)

    print(f"📊 包含'房地产'的行业: {real_estate_industries}")

    # 2. 查找所有包含"地产"的行业
    real_estate_related = []
    async for doc in collection.find({"industry": {"$regex": "地产", "$options": "i"}}, {"industry": 1}):
        industry = doc.get("industry")
        if industry and industry not in real_estate_related:
            real_estate_related.append(industry)

    print(f"📊 包含'地产'的行业: {real_estate_related}")

    # 3. 查找所有包含"房"的行业
    housing_related = []
    async for doc in collection.find({"industry": {"$regex": "房", "$options": "i"}}, {"industry": 1}):
        industry = doc.get("industry")
        if industry and industry not in housing_related:
            housing_related.append(industry)

    print(f"📊 包含'房'的行业: {housing_related}")

    # 4. 查找一些知名房地产公司
    known_real_estate_companies = ["万科", "恒大", "碧桂园", "保利", "融创", "中海", "华润", "绿地", "龙湖", "世茂"]

    print("\n🔍 查找知名房地产公司:")
    for company in known_real_estate_companies:
        async for doc in collection.find(
            {"name": {"$regex": company, "$options": "i"}}, {"code": 1, "name": 1, "industry": 1, "total_mv": 1},
        ):
            total_mv = doc.get("total_mv", 0)
            print(
                f"  {doc.get('code', 'N/A')} - {doc.get('name', 'N/A')} - {doc.get('industry', 'N/A')} - {total_mv:.2f}亿元",
            )

    # 5. 查找市值最大的前20家公司，看看有没有房地产相关的
    print("\n📈 市值最大的前20家公司:")
    async for doc in (
        collection.find({}, {"code": 1, "name": 1, "industry": 1, "total_mv": 1}).sort("total_mv", -1).limit(20)
    ):
        total_mv = doc.get("total_mv", 0)
        industry = doc.get("industry", "N/A")
        name = doc.get("name", "N/A")
        code = doc.get("code", "N/A")

        # 检查是否可能是房地产相关
        is_real_estate = any(
            keyword in name
            for keyword in ["万科", "恒大", "碧桂园", "保利", "融创", "中海", "华润", "绿地", "龙湖", "世茂"]
        ) or any(keyword in industry for keyword in ["房", "地产", "建筑"])

        marker = "🏠" if is_real_estate else "  "
        print(f"{marker} {code} - {name} - {industry} - {total_mv:.2f}亿元")

    # 6. 统计所有行业
    print("\n📋 所有行业统计:")
    industries = {}
    async for doc in collection.find({}, {"industry": 1}):
        industry = doc.get("industry")
        if industry:
            industries[industry] = industries.get(industry, 0) + 1

    # 按股票数量排序
    sorted_industries = sorted(industries.items(), key=lambda x: x[1], reverse=True)

    for industry, count in sorted_industries:
        if any(keyword in industry for keyword in ["房", "地产", "建筑", "装修", "家居"]):
            print(f"🏠 {industry}: {count}只")
        elif count >= 50:  # 只显示大行业
            print(f"   {industry}: {count}只")


if __name__ == "__main__":
    asyncio.run(check_real_estate())
