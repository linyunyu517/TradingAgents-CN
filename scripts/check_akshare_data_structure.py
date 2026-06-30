#!/usr/bin/env python3
"""检查数据库中 AKShare 财务数据的结构"""

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
    print("检查数据库中 AKShare 财务数据的结构")
    print("=" * 80)

    # 查找 AKShare 的财务数据
    doc = await db["stock_financial_data"].find_one({"data_source": "akshare"}, sort=[("report_period", -1)])

    if doc:
        print("\n✅ 找到 AKShare 财务数据")
        print(f"   代码: {doc.get('code')} / {doc.get('symbol')}")
        print(f"   报告期: {doc.get('report_period')}")
        print(f"   数据源: {doc.get('data_source')}")

        print("\n📋 所有字段:")
        for key in sorted(doc.keys()):
            if key != "_id":
                value = doc[key]
                if isinstance(value, dict):
                    print(f"   {key}: <dict with {len(value)} keys>")
                elif isinstance(value, list):
                    print(f"   {key}: <list with {len(value)} items>")
                else:
                    print(f"   {key}: {value}")

        # 检查 financial_indicators
        if doc.get("financial_indicators"):
            print("\n📊 financial_indicators 字段:")
            indicators = doc["financial_indicators"]
            for key, value in indicators.items():
                print(f"   {key}: {value}")
    else:
        print("❌ 未找到 AKShare 财务数据")

    # 对比 Tushare 的数据
    print("\n" + "=" * 80)
    print("对比 Tushare 财务数据的结构")
    print("=" * 80)

    doc_tushare = await db["stock_financial_data"].find_one({"data_source": "tushare"}, sort=[("report_period", -1)])

    if doc_tushare:
        print("\n✅ 找到 Tushare 财务数据")
        print(f"   代码: {doc_tushare.get('code')} / {doc_tushare.get('symbol')}")
        print(f"   报告期: {doc_tushare.get('report_period')}")
        print(f"   数据源: {doc_tushare.get('data_source')}")

        print("\n📋 所有字段:")
        for key in sorted(doc_tushare.keys()):
            if key != "_id":
                value = doc_tushare[key]
                if isinstance(value, dict):
                    print(f"   {key}: <dict with {len(value)} keys>")
                elif isinstance(value, list):
                    print(f"   {key}: <list with {len(value)} items>")
                else:
                    print(f"   {key}: {value}")

        # 检查 financial_indicators
        if doc_tushare.get("financial_indicators"):
            print("\n📊 financial_indicators 字段:")
            indicators = doc_tushare["financial_indicators"]
            for key, value in indicators.items():
                print(f"   {key}: {value}")


asyncio.run(check_data())
