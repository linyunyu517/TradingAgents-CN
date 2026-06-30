#!/usr/bin/env python3
"""
检查MongoDB中所有股票相关的集合
"""

from tradingagents.config.database_manager import get_database_manager


def check_stock_collections():
    """检查股票相关集合"""
    print("=== 检查MongoDB中的股票相关集合 ===")

    try:
        db_manager = get_database_manager()

        if not db_manager.is_mongodb_available():
            print("❌ MongoDB不可用")
            return

        client = db_manager.get_mongodb_client()
        db = client["tradingagents"]

        # 获取所有集合
        collections = db.list_collection_names()
        print(f"\n📋 所有集合 ({len(collections)}个):")

        stock_collections = []
        for collection in collections:
            if "stock" in collection.lower():
                stock_collections.append(collection)
                print(f"  📊 {collection}")
            else:
                print(f"  📄 {collection}")

        print(f"\n🎯 股票相关集合 ({len(stock_collections)}个):")

        # 检查每个股票集合的数据
        for collection_name in stock_collections:
            print(f"\n--- {collection_name} ---")
            collection = db[collection_name]

            # 获取文档数量
            count = collection.count_documents({})
            print(f"  文档数量: {count}")

            if count > 0:
                # 获取样本文档
                sample = collection.find_one()
                if sample:
                    print(f"  样本字段 ({len(sample.keys())}个):")
                    for i, key in enumerate(list(sample.keys())[:10], 1):
                        value = sample[key]
                        if isinstance(value, str) and len(value) > 50:
                            value = value[:50] + "..."
                        print(f"    {i:2d}. {key}: {value}")

                    if len(sample.keys()) > 10:
                        print(f"    ... 还有 {len(sample.keys()) - 10} 个字段")

                # 检查是否有300750的数据
                if "code" in sample:
                    doc_300750 = collection.find_one({"code": "300750"})
                    if doc_300750:
                        print("  ✅ 包含300750数据")
                    else:
                        print("  ❌ 不包含300750数据")
                        # 查看有哪些股票代码
                        codes = collection.distinct("code")[:5]
                        print(f"  样本代码: {codes}")

        # 特别检查股价数据集合
        print("\n🔍 查找股价数据集合:")
        price_keywords = ["price", "quote", "daily", "market", "trading"]

        for collection_name in collections:
            if any(keyword in collection_name.lower() for keyword in price_keywords):
                print(f"  💰 {collection_name}")
                collection = db[collection_name]
                count = collection.count_documents({})
                print(f"    文档数量: {count}")

                if count > 0:
                    sample = collection.find_one()
                    if sample and "code" in sample:
                        # 检查300750
                        doc_300750 = collection.find_one({"code": "300750"})
                        if doc_300750:
                            print("    ✅ 包含300750数据")
                            # 显示价格相关字段
                            price_fields = ["price", "close", "open", "high", "low"]
                            for field in price_fields:
                                if field in doc_300750:
                                    print(f"      {field}: {doc_300750[field]}")
                        else:
                            print("    ❌ 不包含300750数据")

    except Exception as e:
        print(f"检查集合时出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    check_stock_collections()
