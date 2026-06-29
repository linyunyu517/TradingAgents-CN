#!/usr/bin/env python3
"""
调试行业数据 - 直接查询MongoDB
"""

import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def debug_industries():
    """调试行业数据"""
    try:
        # 直接导入MongoDB客户端
        from motor.motor_asyncio import AsyncIOMotorClient

        # 连接MongoDB
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["tradingagents"]
        collection = db["stock_basic_info"]

        print("🔍 调试行业数据...")
        print("=" * 50)

        # 1. 获取所有不同的行业
        industries = await collection.distinct("industry")
        industries = [ind for ind in industries if ind]  # 过滤空值
        industries.sort()

        print(f"📊 数据库中的行业总数: {len(industries)}")

        # 2. 查找房地产相关行业
        real_estate_related = []
        for industry in industries:
            if any(keyword in industry for keyword in ["房", "地产", "建筑", "装修", "家居", "水泥", "钢铁"]):
                real_estate_related.append(industry)

        print(f"\n🏠 房地产相关行业 ({len(real_estate_related)}个):")
        for industry in real_estate_related:
            # 统计该行业的股票数量
            count = await collection.count_documents({"industry": industry})
            print(f"  - {industry}: {count}只股票")

        # 3. 查找一些知名房地产公司
        print("\n🔍 查找知名房地产公司:")
        known_companies = ["万科", "恒大", "碧桂园", "保利", "融创", "中海", "华润", "绿地", "龙湖", "世茂"]

        for company in known_companies:
            cursor = collection.find(
                {"name": {"$regex": company, "$options": "i"}}, {"code": 1, "name": 1, "industry": 1, "total_mv": 1},
            )
            async for doc in cursor:
                total_mv = doc.get("total_mv", 0)
                print(
                    f"  {doc.get('code', 'N/A')} - {doc.get('name', 'N/A')} - {doc.get('industry', 'N/A')} - {total_mv:.2f}亿元",
                )

        # 4. 查找市值超过500亿的所有公司
        print("\n💰 市值超过500亿的公司:")
        cursor = collection.find(
            {"total_mv": {"$gte": 500}}, {"code": 1, "name": 1, "industry": 1, "total_mv": 1},
        ).sort("total_mv", -1)

        count = 0
        async for doc in cursor:
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

            count += 1
            if count >= 30:  # 只显示前30个
                break

        # 5. 专门查找"房地产"行业的公司
        print("\n🏘️ '房地产'行业的所有公司:")
        cursor = collection.find({"industry": "房地产"}, {"code": 1, "name": 1, "total_mv": 1}).sort("total_mv", -1)

        count = 0
        async for doc in cursor:
            total_mv = doc.get("total_mv", 0)
            name = doc.get("name", "N/A")
            code = doc.get("code", "N/A")
            print(f"  {code} - {name} - {total_mv:.2f}亿元")
            count += 1

        if count == 0:
            print("  ❌ 没有找到'房地产'行业的公司")
        else:
            print(f"  📊 总共找到 {count} 家'房地产'行业的公司")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_industries())
