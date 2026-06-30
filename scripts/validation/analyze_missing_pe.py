#!/usr/bin/env python3
"""
分析PE为空的股票
了解为什么某些股票没有PE数据
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


def analyze_missing_pe():
    """分析PE为空的股票"""
    print("🔍 分析PE为空的股票")
    print("=" * 60)

    try:
        # 连接 MongoDB
        uri = build_mongo_uri()
        client = MongoClient(uri)
        dbname = os.getenv("MONGODB_DATABASE", "tradingagents")
        db = client[dbname]
        collection = db.stock_basic_info

        # 统计总体情况
        total_count = collection.count_documents({})
        has_pe_count = collection.count_documents({"pe": {"$exists": True, "$ne": None}})
        no_pe_count = total_count - has_pe_count

        print("📊 总体统计:")
        print(f"   总股票数: {total_count}")
        print(f"   有PE数据: {has_pe_count} ({has_pe_count / total_count * 100:.1f}%)")
        print(f"   无PE数据: {no_pe_count} ({no_pe_count / total_count * 100:.1f}%)")

        # 按市场分析无PE数据的分布
        print("\n📈 无PE数据的股票按市场分布:")
        no_pe_by_market = list(
            collection.aggregate(
                [
                    {"$match": {"$or": [{"pe": {"$exists": False}}, {"pe": None}]}},
                    {"$group": {"_id": "$market", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
            ),
        )

        for stat in no_pe_by_market:
            market = stat["_id"] if stat["_id"] else "未知"
            count = stat["count"]
            print(f"   {market:10}: {count:4d} 只")

        # 按行业分析无PE数据的分布
        print("\n🏭 无PE数据的股票按行业分布 (前10个行业):")
        no_pe_by_industry = list(
            collection.aggregate(
                [
                    {"$match": {"$or": [{"pe": {"$exists": False}}, {"pe": None}]}},
                    {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 10},
                ],
            ),
        )

        for stat in no_pe_by_industry:
            industry = stat["_id"] if stat["_id"] else "未知"
            count = stat["count"]
            print(f"   {industry:15}: {count:4d} 只")

        # 分析无PE但有其他财务数据的股票
        print("\n💰 无PE但有其他财务数据的股票:")
        no_pe_but_has_other = collection.count_documents(
            {
                "$and": [
                    {"$or": [{"pe": {"$exists": False}}, {"pe": None}]},
                    {
                        "$or": [
                            {"pb": {"$exists": True, "$ne": None}},
                            {"total_mv": {"$exists": True, "$ne": None}},
                            {"circ_mv": {"$exists": True, "$ne": None}},
                        ],
                    },
                ],
            },
        )
        print(f"   有其他财务数据但无PE: {no_pe_but_has_other} 只")

        # 查看具体的无PE股票示例
        print("\n📋 无PE数据的股票示例 (前15只):")
        print("-" * 80)
        print(f"{'代码':>8} {'名称':15} {'市场':8} {'行业':15} {'PB':>8} {'总市值':>12}")
        print("-" * 80)

        no_pe_stocks = list(collection.find({"$or": [{"pe": {"$exists": False}}, {"pe": None}]}).limit(15))

        for stock in no_pe_stocks:
            code = stock.get("code", "N/A")
            name = stock.get("name", "N/A")[:15]
            market = stock.get("market", "N/A")
            industry = stock.get("industry", "N/A")[:15]
            pb = stock.get("pb", "N/A")
            total_mv = stock.get("total_mv", "N/A")

            pb_str = f"{pb:.2f}" if isinstance(pb, (int, float)) else str(pb)
            mv_str = f"{total_mv:.0f}" if isinstance(total_mv, (int, float)) else str(total_mv)

            print(f"{code:>8} {name:15} {market:8} {industry:15} {pb_str:>8} {mv_str:>12}")

        # 分析可能的原因
        print("\n🔍 可能的原因分析:")

        # 1. ST股票
        st_no_pe = collection.count_documents(
            {
                "$and": [
                    {"$or": [{"pe": {"$exists": False}}, {"pe": None}]},
                    {"name": {"$regex": "^\\*?ST", "$options": "i"}},
                ],
            },
        )
        print(f"   1. ST股票 (特别处理): {st_no_pe} 只")

        # 2. 亏损股票 (有负的净利润，无法计算正PE)
        # 这里我们通过PB很高但无PE来推测可能是亏损
        high_pb_no_pe = collection.count_documents(
            {
                "$and": [
                    {"$or": [{"pe": {"$exists": False}}, {"pe": None}]},
                    {"pb": {"$gt": 10}},  # PB很高可能暗示亏损
                ],
            },
        )
        print(f"   2. 可能亏损股票 (PB>10但无PE): {high_pb_no_pe} 只")

        # 3. 新上市股票 (可能数据不全)
        recent_list = collection.count_documents(
            {
                "$and": [
                    {"$or": [{"pe": {"$exists": False}}, {"pe": None}]},
                    {"list_date": {"$gte": "20240101"}},  # 2024年以后上市
                ],
            },
        )
        print(f"   3. 2024年后上市股票: {recent_list} 只")

        # 4. 停牌或交易异常股票
        no_turnover = collection.count_documents(
            {
                "$and": [
                    {"$or": [{"pe": {"$exists": False}}, {"pe": None}]},
                    {"$or": [{"turnover_rate": {"$exists": False}}, {"turnover_rate": None}, {"turnover_rate": 0}]},
                ],
            },
        )
        print(f"   4. 无换手率数据股票 (可能停牌): {no_turnover} 只")

        print("\n💡 PE为空的主要原因:")
        print("   • 公司亏损 - 净利润为负，无法计算正的市盈率")
        print("   • ST股票 - 特别处理股票，财务数据可能异常")
        print("   • 停牌股票 - 没有交易，无法获取实时财务指标")
        print("   • 新上市股票 - 财务数据可能还未完整")
        print("   • 数据源限制 - Tushare可能对某些股票的PE数据有限制")

        print("\n✅ 分析完成!")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        return False

    return True


if __name__ == "__main__":
    success = analyze_missing_pe()
    sys.exit(0 if success else 1)
