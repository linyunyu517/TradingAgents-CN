#!/usr/bin/env python
"""
修复 stock_basic_info 集合中 full_symbol 为 null 的记录

问题：
- 数据库中有些记录的 full_symbol 字段为 null
- MongoDB 的 full_symbol 唯一索引不允许多个 null 值
- 导致数据同步时出现 E11000 duplicate key error

解决方案：
1. 查找所有 full_symbol 为 null 或空的记录
2. 根据 code 字段生成 full_symbol
3. 更新数据库记录
"""

import asyncio
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings

settings = get_settings()


def generate_full_symbol(code: str) -> str:
    """
    根据股票代码生成完整标准化代码

    Args:
        code: 6位股票代码

    Returns:
        完整标准化代码，如果无法识别则返回原始代码（确保不为空）
    """
    # 确保 code 不为空
    if not code:
        return ""

    # 标准化为字符串并去除空格
    code = str(code).strip()

    # 如果长度不是 6，返回原始代码
    if len(code) != 6:
        return code

    # 根据代码前缀判断交易所
    if code.startswith(("60", "68", "90")):  # 上海证券交易所
        return f"{code}.SS"
    if code.startswith(("00", "30", "20")):  # 深圳证券交易所
        return f"{code}.SZ"
    if code.startswith(("8", "4")):  # 北京证券交易所
        return f"{code}.BJ"
    # 无法识别的代码，返回原始代码（确保不为空）
    return code or ""


async def fix_null_full_symbol():
    """修复 full_symbol 为 null 的记录"""

    print(f"\n{'=' * 80}")
    print("修复 stock_basic_info 集合中 full_symbol 为 null 的记录")
    print(f"{'=' * 80}\n")

    # 连接数据库
    print("🔧 连接 MongoDB...")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db["stock_basic_info"]
    print("✅ MongoDB 连接成功\n")

    # 步骤 1：统计 full_symbol 为 null 或空的记录
    print("📊 [步骤1] 统计问题记录")
    print("-" * 80)

    # 查询条件：full_symbol 为 null 或空字符串
    query = {"$or": [{"full_symbol": None}, {"full_symbol": ""}, {"full_symbol": {"$exists": False}}]}

    null_count = await collection.count_documents(query)
    print(f"发现 {null_count} 条 full_symbol 为空的记录\n")

    if null_count == 0:
        print("✅ 没有需要修复的记录")
        await client.close()
        return

    # 步骤 2：获取所有需要修复的记录
    print("📋 [步骤2] 获取需要修复的记录")
    print("-" * 80)

    cursor = collection.find(query, {"_id": 1, "code": 1, "name": 1, "full_symbol": 1})
    records = await cursor.to_list(length=None)

    print(f"获取到 {len(records)} 条记录\n")

    # 步骤 3：修复记录
    print("🔧 [步骤3] 修复记录")
    print("-" * 80)

    success_count = 0
    error_count = 0
    skipped_count = 0

    for i, record in enumerate(records, 1):
        code = record.get("code")
        name = record.get("name", "未知")
        old_full_symbol = record.get("full_symbol")

        # 如果没有 code 字段，跳过
        if not code:
            print(f"⚠️  [{i}/{len(records)}] 记录缺少 code 字段，跳过")
            skipped_count += 1
            continue

        # 生成新的 full_symbol
        new_full_symbol = generate_full_symbol(code)

        # 如果新的 full_symbol 也为空，跳过
        if not new_full_symbol:
            print(f"⚠️  [{i}/{len(records)}] {code} ({name}) - 无法生成 full_symbol，跳过")
            skipped_count += 1
            continue

        # 更新数据库
        try:
            result = await collection.update_one(
                {"_id": record["_id"]}, {"$set": {"full_symbol": new_full_symbol, "updated_at": datetime.utcnow()}},
            )

            if result.modified_count > 0:
                # 每 10 条显示一次进度
                if i % 10 == 0 or i == len(records):
                    print(f"✅ [{i}/{len(records)}] {code} ({name}) - {old_full_symbol} → {new_full_symbol}")
                success_count += 1
            else:
                error_count += 1

        except Exception as e:
            print(f"❌ [{i}/{len(records)}] {code} ({name}) - 更新失败: {e}")
            error_count += 1

    print()

    # 步骤 4：验证结果
    print("📊 [步骤4] 验证结果")
    print("-" * 80)

    # 再次统计 full_symbol 为 null 的记录
    remaining_null_count = await collection.count_documents(query)

    print(f"修复前: {null_count} 条记录")
    print(f"修复后: {remaining_null_count} 条记录")
    print(f"成功修复: {success_count} 条")
    print(f"修复失败: {error_count} 条")
    print(f"跳过: {skipped_count} 条")

    if remaining_null_count == 0:
        print("\n✅ 所有记录的 full_symbol 字段都已正确设置")
    else:
        print(f"\n⚠️  仍有 {remaining_null_count} 条记录的 full_symbol 为空")

    # 步骤 5：检查索引
    print("\n📊 [步骤5] 检查索引")
    print("-" * 80)

    indexes = await collection.index_information()

    # 查找 full_symbol 相关的索引
    full_symbol_indexes = [
        (name, info) for name, info in indexes.items() if any("full_symbol" in str(key) for key in info.get("key", []))
    ]

    if full_symbol_indexes:
        print("发现 full_symbol 相关索引:")
        for name, info in full_symbol_indexes:
            unique = info.get("unique", False)
            print(f"  - {name}: {info.get('key', [])} (unique={unique})")

            if unique:
                print(f"\n⚠️  警告: {name} 是唯一索引")
                print("   如果仍有多条记录的 full_symbol 为空，可能需要删除此索引")
                print(f"   删除命令: db.stock_basic_info.dropIndex('{name}')")
    else:
        print("未发现 full_symbol 相关索引")

    # 关闭连接
    client.close()

    print(f"\n{'=' * 80}")
    print("修复完成")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    asyncio.run(fix_null_full_symbol())
