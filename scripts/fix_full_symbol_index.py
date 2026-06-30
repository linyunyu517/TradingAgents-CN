#!/usr/bin/env python
"""
修复 stock_basic_info 集合的 full_symbol 唯一索引问题

问题：
- MongoDB 的 stock_basic_info 集合有一个 full_symbol 字段的唯一索引
- 多条记录的 full_symbol 字段都是 null
- MongoDB 唯一索引不允许多个 null 值
- 导致数据同步时出现 E11000 duplicate key error

解决方案：
1. 删除 full_symbol 的唯一索引
2. 为所有记录生成 full_symbol 字段
3. 重新创建 full_symbol 的唯一索引（可选）
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.core.database import get_mongo_db, init_database


def generate_full_symbol(code: str) -> str:
    """
    根据股票代码生成完整标准化代码

    Args:
        code: 6位股票代码

    Returns:
        完整标准化代码（如 000001.SZ）
    """
    if not code or len(code) != 6:
        return None

    # 根据代码判断交易所
    if code.startswith(("60", "68", "90")):
        return f"{code}.SS"  # 上海证券交易所
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"  # 深圳证券交易所
    if code.startswith("8") or code.startswith("4"):
        return f"{code}.BJ"  # 北京证券交易所
    return f"{code}.SZ"  # 默认深圳


async def fix_full_symbol_index():
    """修复 full_symbol 索引问题"""

    print(f"\n{'=' * 80}")
    print("修复 stock_basic_info 集合的 full_symbol 唯一索引问题")
    print(f"{'=' * 80}\n")

    # 初始化数据库连接
    print("🔧 初始化 MongoDB 连接...")
    await init_database()
    db = get_mongo_db()
    collection = db["stock_basic_info"]
    print("✅ MongoDB 连接成功\n")

    # 步骤 1：检查现有索引
    print("📊 [步骤1] 检查现有索引")
    print("-" * 80)

    indexes = await collection.index_information()
    print("当前索引列表:")
    for index_name, index_info in indexes.items():
        print(f"  - {index_name}: {index_info}")

    # 检查是否存在 full_symbol 唯一索引
    full_symbol_index_exists = False
    full_symbol_index_name = None

    for index_name, index_info in indexes.items():
        if "full_symbol" in str(index_info.get("key", [])):
            full_symbol_index_exists = True
            full_symbol_index_name = index_name
            is_unique = index_info.get("unique", False)
            print(f"\n✅ 找到 full_symbol 索引: {index_name} (unique={is_unique})")
            break

    if not full_symbol_index_exists:
        print("\n⚠️ 未找到 full_symbol 索引")

    # 步骤 2：删除 full_symbol 唯一索引
    if full_symbol_index_exists and full_symbol_index_name:
        print("\n📊 [步骤2] 删除 full_symbol 唯一索引")
        print("-" * 80)

        try:
            await collection.drop_index(full_symbol_index_name)
            print(f"✅ 成功删除索引: {full_symbol_index_name}")
        except Exception as e:
            print(f"❌ 删除索引失败: {e}")
            return
    else:
        print("\n📊 [步骤2] 跳过（无需删除索引）")
        print("-" * 80)

    # 步骤 3：统计需要更新的记录
    print("\n📊 [步骤3] 统计需要更新的记录")
    print("-" * 80)

    total_count = await collection.count_documents({})
    null_count = await collection.count_documents({"full_symbol": None})
    missing_count = await collection.count_documents({"full_symbol": {"$exists": False}})

    print(f"总记录数: {total_count}")
    print(f"full_symbol 为 null 的记录: {null_count}")
    print(f"full_symbol 不存在的记录: {missing_count}")
    print(f"需要更新的记录: {null_count + missing_count}")

    # 步骤 4：为所有记录生成 full_symbol
    print("\n📊 [步骤4] 为所有记录生成 full_symbol")
    print("-" * 80)

    # 查询所有需要更新的记录
    cursor = collection.find({"$or": [{"full_symbol": None}, {"full_symbol": {"$exists": False}}]}, {"code": 1})

    updated_count = 0
    error_count = 0

    async for doc in cursor:
        code = doc.get("code")
        if not code:
            continue

        full_symbol = generate_full_symbol(code)
        if not full_symbol:
            error_count += 1
            continue

        try:
            await collection.update_one({"_id": doc["_id"]}, {"$set": {"full_symbol": full_symbol}})
            updated_count += 1

            if updated_count % 100 == 0:
                print(f"  已更新 {updated_count} 条记录...")
        except Exception as e:
            print(f"  ❌ 更新失败 code={code}: {e}")
            error_count += 1

    print("\n✅ 更新完成:")
    print(f"  成功: {updated_count} 条")
    print(f"  失败: {error_count} 条")

    # 步骤 5：验证结果
    print("\n📊 [步骤5] 验证结果")
    print("-" * 80)

    null_count_after = await collection.count_documents({"full_symbol": None})
    missing_count_after = await collection.count_documents({"full_symbol": {"$exists": False}})

    print("更新后统计:")
    print(f"  full_symbol 为 null 的记录: {null_count_after}")
    print(f"  full_symbol 不存在的记录: {missing_count_after}")

    if null_count_after == 0 and missing_count_after == 0:
        print("\n✅ 所有记录的 full_symbol 字段都已正确设置")
    else:
        print(f"\n⚠️ 仍有 {null_count_after + missing_count_after} 条记录的 full_symbol 未设置")

    # 步骤 6：重新创建 full_symbol 唯一索引（可选）
    print("\n📊 [步骤6] 是否重新创建 full_symbol 唯一索引？")
    print("-" * 80)
    print("⚠️ 注意：只有在所有记录的 full_symbol 都已正确设置后才能创建唯一索引")
    print("⚠️ 当前不建议创建唯一索引，因为 basics_sync_service 还未更新")
    print("⚠️ 建议：等待 basics_sync_service 更新后再创建唯一索引")

    # 不自动创建唯一索引，等待代码更新后再手动创建
    # try:
    #     await collection.create_index([("full_symbol", ASCENDING)], unique=True, name="full_symbol_unique")
    #     print(f"✅ 成功创建 full_symbol 唯一索引")
    # except Exception as e:
    #     print(f"❌ 创建索引失败: {e}")

    print(f"\n{'=' * 80}")
    print("修复完成！")
    print(f"{'=' * 80}\n")

    print("📝 后续步骤:")
    print("  1. ✅ 已删除 full_symbol 唯一索引")
    print("  2. ✅ 已为所有记录生成 full_symbol 字段")
    print("  3. ⬜ 更新 basics_sync_service.py 添加 full_symbol 生成逻辑")
    print("  4. ⬜ 重新运行数据同步测试")
    print("  5. ⬜ （可选）重新创建 full_symbol 唯一索引")


async def main():
    """主函数"""

    # 设置环境变量
    os.environ["TA_USE_APP_CACHE"] = "true"

    await fix_full_symbol_index()


if __name__ == "__main__":
    asyncio.run(main())
