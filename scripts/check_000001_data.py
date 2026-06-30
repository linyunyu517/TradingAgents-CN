#!/usr/bin/env python3
"""检查平安银行（000001）的财务数据"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


async def check_data():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    print("=" * 80)
    print("检查平安银行（000001）的数据")
    print("=" * 80)

    # 检查 stock_financial_data 中是否有 000001 的数据
    print("\n📊 检查 stock_financial_data 集合...")
    financial_data = await db["stock_financial_data"].find_one(
        {"$or": [{"symbol": "000001"}, {"code": "000001"}]}, sort=[("report_period", -1)],
    )

    if financial_data:
        print("✅ 找到财务数据")
        print(f"   报告期: {financial_data.get('report_period')}")
        print(f"   数据源: {financial_data.get('data_source')}")
        print(f"   ROE: {financial_data.get('roe')}")
        print(f"   debt_to_assets: {financial_data.get('debt_to_assets')}")
        print(f"   revenue_ttm: {financial_data.get('revenue_ttm')}")

        if financial_data.get("financial_indicators"):
            indicators = financial_data["financial_indicators"]
            print(f"   financial_indicators.roe: {indicators.get('roe')}")
            print(f"   financial_indicators.debt_to_assets: {indicators.get('debt_to_assets')}")
    else:
        print("❌ 未找到财务数据")

    # 检查 stock_basic_info 中的数据
    print("\n📋 检查 stock_basic_info 集合...")
    basic_info = await db["stock_basic_info"].find_one({"code": "000001"})
    if basic_info:
        print("✅ 找到基础信息")
        print(f"   数据源: {basic_info.get('source')}")
        print(f"   ROE: {basic_info.get('roe')}")
        print(f"   debt_to_assets: {basic_info.get('debt_to_assets')}")
        print(f"   total_share: {basic_info.get('total_share')}")
        print(f"   ps: {basic_info.get('ps')}")
        print(f"   revenue_ttm: {basic_info.get('revenue_ttm')}")
    else:
        print("❌ 未找到基础信息")

    # 检查有多少条财务数据
    print("\n📈 统计 stock_financial_data 中 000001 的记录数...")
    count = await db["stock_financial_data"].count_documents({"$or": [{"symbol": "000001"}, {"code": "000001"}]})
    print(f"   总共有 {count} 条记录")

    # 列出最近的几条记录
    if count > 0:
        print("\n   最近的5条记录:")
        cursor = db["stock_financial_data"].find(
            {"$or": [{"symbol": "000001"}, {"code": "000001"}]}, sort=[("report_period", -1)], limit=5,
        )
        async for doc in cursor:
            print(f"   - 报告期: {doc.get('report_period')}, 数据源: {doc.get('data_source')}, ROE: {doc.get('roe')}")

    # 详细检查每条记录的字段
    print("\n" + "=" * 80)
    print("详细检查每条财务数据记录")
    print("=" * 80)
    cursor = db["stock_financial_data"].find(
        {"$or": [{"symbol": "000001"}, {"code": "000001"}]}, sort=[("report_period", -1)],
    )
    async for doc in cursor:
        print(f"\n📄 报告期: {doc.get('report_period')} (数据源: {doc.get('data_source')})")
        print(f"   ROE: {doc.get('roe')}")
        print(f"   debt_to_assets: {doc.get('debt_to_assets')}")
        print(f"   revenue_ttm: {doc.get('revenue_ttm')}")
        print(f"   total_share: {doc.get('total_share')}")
        print(f"   float_share: {doc.get('float_share')}")
        print(f"   net_profit_ttm: {doc.get('net_profit_ttm')}")

        # 检查 financial_indicators
        if doc.get("financial_indicators"):
            indicators = doc["financial_indicators"]
            print(f"   financial_indicators.roe: {indicators.get('roe')}")
            print(f"   financial_indicators.debt_to_assets: {indicators.get('debt_to_assets')}")


asyncio.run(check_data())
