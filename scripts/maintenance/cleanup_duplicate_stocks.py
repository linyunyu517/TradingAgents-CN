#!/usr/bin/env python3
"""
清理重复股票记录
合并带前导零和不带前导零的股票代码记录
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


def cleanup_duplicate_stocks():
    """清理重复股票记录"""
    print("🧹 清理重复股票记录")
    print("=" * 60)

    try:
        # 连接 MongoDB
        uri = build_mongo_uri()
        client = MongoClient(uri)
        dbname = os.getenv("MONGODB_DATABASE", "tradingagents")
        db = client[dbname]
        collection = db.stock_basic_info

        # 统计清理前的数据
        total_before = collection.count_documents({})
        print(f"📊 清理前总记录数: {total_before}")

        # 查找所有可能的重复对
        print("\n🔍 查找重复记录...")

        # 获取所有股票名称
        all_names = collection.distinct("name")
        print(f"发现 {len(all_names)} 个不同的股票名称")

        duplicates_found = 0
        records_to_delete = []
        records_updated = 0

        for name in all_names:
            if not name:
                continue

            # 查找同名股票的所有记录
            records = list(collection.find({"name": name}))

            if len(records) > 1:
                duplicates_found += 1

                # 按是否有扩展字段排序，优先保留有扩展字段的记录
                records.sort(
                    key=lambda x: (
                        x.get("pe") is not None,
                        x.get("pb") is not None,
                        x.get("circ_mv") is not None,
                        x.get("turnover_rate") is not None,
                    ),
                    reverse=True,
                )

                # 保留第一条记录（最完整的），删除其他记录
                keep_record = records[0]
                delete_records = records[1:]

                print(f"  {name}:")
                print(f"    保留: code={keep_record.get('code')}, PE={keep_record.get('pe', 'N/A')}")

                for record in delete_records:
                    print(f"    删除: code={record.get('code')}, PE={record.get('pe', 'N/A')}")
                    records_to_delete.append(record["_id"])

                # 如果保留的记录使用的是不带前导零的代码，但没有扩展字段
                # 而删除的记录有前导零但可能有其他有用信息，则合并信息
                keep_code = str(keep_record.get("code", ""))
                if len(keep_code) < 6:  # 不带前导零
                    for del_record in delete_records:
                        del_code = str(del_record.get("code", ""))
                        if len(del_code) == 6:  # 带前导零
                            # 如果删除的记录有一些保留记录没有的字段，则更新保留记录
                            update_fields = {}
                            for field in ["area", "industry", "market", "list_date"]:
                                if not keep_record.get(field) and del_record.get(field):
                                    update_fields[field] = del_record[field]

                            if update_fields:
                                collection.update_one({"_id": keep_record["_id"]}, {"$set": update_fields})
                                records_updated += 1
                                print(f"    更新保留记录的字段: {list(update_fields.keys())}")

        print(f"\n📈 发现 {duplicates_found} 组重复记录")
        print(f"📈 计划删除 {len(records_to_delete)} 条记录")
        print(f"📈 更新了 {records_updated} 条记录")

        # 执行删除操作
        if records_to_delete:
            print("\n🗑️  执行删除操作...")
            result = collection.delete_many({"_id": {"$in": records_to_delete}})
            print(f"✅ 成功删除 {result.deleted_count} 条记录")

        # 统计清理后的数据
        total_after = collection.count_documents({})
        print(f"\n📊 清理后总记录数: {total_after}")
        print(f"📊 减少记录数: {total_before - total_after}")

        # 验证清理效果
        print("\n🔍 验证清理效果...")
        remaining_duplicates = 0
        for name in all_names[:10]:  # 检查前10个
            if not name:
                continue
            count = collection.count_documents({"name": name})
            if count > 1:
                remaining_duplicates += 1
                print(f"  ⚠️  {name}: 仍有 {count} 条记录")

        if remaining_duplicates == 0:
            print("✅ 未发现剩余重复记录")
        else:
            print(f"⚠️  仍有 {remaining_duplicates} 组重复记录")

        print("\n✅ 清理完成!")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"❌ 清理失败: {e}")
        return False

    return True


if __name__ == "__main__":
    success = cleanup_duplicate_stocks()
    sys.exit(0 if success else 1)
