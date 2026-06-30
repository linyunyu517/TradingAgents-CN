"""
检查 stock_daily_quotes 集合的字段
"""

import os
import sys

from pymongo import MongoClient


def check_fields():
    """检查集合字段"""
    print("🔍 检查 stock_daily_quotes 集合字段")
    print("=" * 70)

    # 连接 MongoDB
    try:
        mongo_password = os.getenv("MONGODB_PASSWORD", "")
        if not mongo_password:
            print("错误：请设置 MONGODB_PASSWORD 环境变量")
            sys.exit(1)
        client = MongoClient(f"mongodb://admin:{mongo_password}@localhost:27017/")
        db = client["tradingagents"]
        collection = db["stock_daily_quotes"]

        # 统计总记录数
        total_count = collection.count_documents({})
        print(f"\n📊 总记录数: {total_count}")

        if total_count == 0:
            print("\n⚠️  集合为空，没有数据")
            return

        # 获取一条示例数据
        print("\n📋 示例数据（第1条）:")
        print("-" * 70)
        sample = collection.find_one({}, {"_id": 0})
        if sample:
            for key, value in sample.items():
                print(f"  {key}: {value}")

        # 检查是否有 symbol 字段
        print("\n" + "=" * 70)
        print("🔍 字段检查:")
        print("-" * 70)

        has_symbol = collection.count_documents({"symbol": {"$exists": True}})
        has_code = collection.count_documents({"code": {"$exists": True}})

        print(f"  有 symbol 字段的记录数: {has_symbol} ({has_symbol / total_count * 100:.1f}%)")
        print(f"  有 code 字段的记录数: {has_code} ({has_code / total_count * 100:.1f}%)")

        # 检查不同的字段组合
        print("\n" + "=" * 70)
        print("📊 字段组合统计:")
        print("-" * 70)

        both = collection.count_documents({"symbol": {"$exists": True}, "code": {"$exists": True}})
        only_symbol = collection.count_documents({"symbol": {"$exists": True}, "code": {"$exists": False}})
        only_code = collection.count_documents({"symbol": {"$exists": False}, "code": {"$exists": True}})
        neither = collection.count_documents({"symbol": {"$exists": False}, "code": {"$exists": False}})

        print(f"  同时有 symbol 和 code: {both} ({both / total_count * 100:.1f}%)")
        print(f"  只有 symbol: {only_symbol} ({only_symbol / total_count * 100:.1f}%)")
        print(f"  只有 code: {only_code} ({only_code / total_count * 100:.1f}%)")
        print(f"  都没有: {neither} ({neither / total_count * 100:.1f}%)")

        # 如果有只有 code 的记录，显示示例
        if only_code > 0:
            print("\n" + "=" * 70)
            print("⚠️  发现只有 code 字段的记录（示例）:")
            print("-" * 70)
            sample_code_only = collection.find_one(
                {"symbol": {"$exists": False}, "code": {"$exists": True}}, {"_id": 0},
            )
            if sample_code_only:
                for key, value in sample_code_only.items():
                    print(f"  {key}: {value}")

        # 检查所有字段
        print("\n" + "=" * 70)
        print("📋 所有字段列表:")
        print("-" * 70)

        # 使用聚合获取所有字段
        pipeline = [
            {"$limit": 100},  # 只检查前100条
            {"$project": {"arrayofkeyvalue": {"$objectToArray": "$$ROOT"}}},
            {"$unwind": "$arrayofkeyvalue"},
            {"$group": {"_id": None, "allkeys": {"$addToSet": "$arrayofkeyvalue.k"}}},
        ]

        result = list(collection.aggregate(pipeline))
        if result:
            all_fields = sorted(result[0]["allkeys"])
            for i, field in enumerate(all_fields, 1):
                print(f"  {i:2d}. {field}")

        # 检查索引
        print("\n" + "=" * 70)
        print("🔍 索引列表:")
        print("-" * 70)

        indexes = collection.list_indexes()
        for idx in indexes:
            print(f"  • {idx['name']}")
            print(f"    键: {idx['key']}")
            if idx.get("unique"):
                print("    唯一索引: 是")

        print("\n" + "=" * 70)
        print("✅ 检查完成")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    check_fields()
