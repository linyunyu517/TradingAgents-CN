#!/usr/bin/env python3
"""
诊断扩展字段缺失问题
分析为什么部分股票没有获取到扩展字段数据
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

# 加载环境变量
load_dotenv()


def build_mongo_uri():
    host = os.getenv("MONGODB_HOST", "localhost")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    db = os.getenv("MONGODB_DATABASE", "tradingagents")
    user = os.getenv("MONGODB_USERNAME", "")
    pwd = os.getenv("MONGODB_PASSWORD", "")
    auth_src = os.getenv("MONGODB_AUTH_SOURCE", "admin")
    if user and pwd:
        return f"mongodb://{user}:{pwd}@{host}:{port}/{db}?authSource={auth_src}"
    return f"mongodb://{host}:{port}/{db}"


def diagnose_missing_fields():
    """诊断扩展字段缺失问题"""
    print("🔍 诊断扩展字段缺失问题")
    print("=" * 60)

    try:
        # 连接 MongoDB
        uri = build_mongo_uri()
        client = MongoClient(uri)
        dbname = os.getenv("MONGODB_DATABASE", "tradingagents")
        db = client[dbname]
        collection = db.stock_basic_info

        # 总记录数
        total_count = collection.count_documents({})
        print(f"📊 总股票数量: {total_count}")

        # 统计有/无扩展字段的股票数量
        has_extended = collection.count_documents(
            {
                "$or": [
                    {"circ_mv": {"$exists": True, "$ne": None}},
                    {"pe": {"$exists": True, "$ne": None}},
                    {"pb": {"$exists": True, "$ne": None}},
                    {"turnover_rate": {"$exists": True, "$ne": None}},
                ],
            },
        )

        missing_extended = total_count - has_extended

        print(f"✅ 有扩展字段的股票: {has_extended} ({has_extended / total_count * 100:.1f}%)")
        print(f"❌ 缺少扩展字段的股票: {missing_extended} ({missing_extended / total_count * 100:.1f}%)")

        # 分析缺少扩展字段的股票特征
        print("\n🔍 缺少扩展字段的股票分析:")
        print("-" * 50)

        # 按市场分析
        missing_by_market = list(
            collection.aggregate(
                [
                    {
                        "$match": {
                            "circ_mv": {"$exists": False},
                            "pe": {"$exists": False},
                            "pb": {"$exists": False},
                            "turnover_rate": {"$exists": False},
                        },
                    },
                    {"$group": {"_id": "$market", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
            ),
        )

        print("按市场分布:")
        for stat in missing_by_market:
            market = stat["_id"] if stat["_id"] else "未知"
            print(f"  {market:10}: {stat['count']:4d} 只")

        # 按交易所分析
        missing_by_sse = list(
            collection.aggregate(
                [
                    {
                        "$match": {
                            "circ_mv": {"$exists": False},
                            "pe": {"$exists": False},
                            "pb": {"$exists": False},
                            "turnover_rate": {"$exists": False},
                        },
                    },
                    {"$group": {"_id": "$sse", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
            ),
        )

        print("\n按交易所分布:")
        for stat in missing_by_sse:
            sse = stat["_id"] if stat["_id"] else "未知"
            print(f"  {sse:10}: {stat['count']:4d} 只")

        # 查看具体的缺失案例
        print("\n📋 缺少扩展字段的股票示例 (前10只):")
        print("-" * 60)

        missing_stocks = list(
            collection.find(
                {
                    "circ_mv": {"$exists": False},
                    "pe": {"$exists": False},
                    "pb": {"$exists": False},
                    "turnover_rate": {"$exists": False},
                },
            ).limit(10),
        )

        for i, stock in enumerate(missing_stocks, 1):
            print(
                f"  {i:2d}. {stock.get('code', 'N/A'):8} - {stock.get('name', 'N/A'):15} - "
                f"{stock.get('market', 'N/A'):8} - {stock.get('sse', 'N/A')}",
            )

        # 对比：查看有扩展字段的股票示例
        print("\n📋 有扩展字段的股票示例 (前5只):")
        print("-" * 60)

        has_extended_stocks = list(collection.find({"circ_mv": {"$exists": True, "$ne": None}}).limit(5))

        for i, stock in enumerate(has_extended_stocks, 1):
            print(
                f"  {i:2d}. {stock.get('code', 'N/A'):8} - {stock.get('name', 'N/A'):15} - "
                f"PE: {stock.get('pe', 'N/A'):8} - PB: {stock.get('pb', 'N/A'):8}",
            )

        # 检查特定股票 000001
        print("\n🔍 检查股票 000001 (平安银行):")
        print("-" * 40)
        stock_000001 = collection.find_one({"code": "000001"})
        if stock_000001:
            print(f"  代码: {stock_000001.get('code')}")
            print(f"  名称: {stock_000001.get('name')}")
            print(f"  市场: {stock_000001.get('market')}")
            print(f"  交易所: {stock_000001.get('sse')}")
            print(f"  总市值: {stock_000001.get('total_mv', 'N/A')}")
            print(f"  流通市值: {stock_000001.get('circ_mv', '❌ 缺失')}")
            print(f"  市盈率: {stock_000001.get('pe', '❌ 缺失')}")
            print(f"  市净率: {stock_000001.get('pb', '❌ 缺失')}")
            print(f"  换手率: {stock_000001.get('turnover_rate', '❌ 缺失')}")
        else:
            print("  ❌ 未找到股票 000001")

        print("\n✅ 诊断完成!")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        return False

    return True


if __name__ == "__main__":
    success = diagnose_missing_fields()
    sys.exit(0 if success else 1)
