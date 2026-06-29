"""
修复数据库中厂家 ID 类型不一致的问题

问题：部分厂家的 _id 字段是字符串类型，而不是 ObjectId 类型
原因：使用 model_dump(by_alias=True) 时，PyObjectId 被序列化为字符串
解决：将字符串类型的 _id 转换为 ObjectId 类型
"""

import asyncio
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


async def fix_provider_id_types():
    """修复厂家 ID 类型"""
    # 使用配置文件中的数据库连接信息
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    providers_collection = db.llm_providers

    print("🔍 检查数据库中的厂家 ID 类型...")

    # 获取所有厂家
    all_providers = await providers_collection.find().to_list(length=None)

    string_id_providers = []
    objectid_providers = []

    for provider in all_providers:
        provider_id = provider["_id"]
        display_name = provider.get("display_name", "未知")

        if isinstance(provider_id, str):
            string_id_providers.append(provider)
            print(f"❌ 字符串 ID: {provider_id} - {display_name}")
        elif isinstance(provider_id, ObjectId):
            objectid_providers.append(provider)
            print(f"✅ ObjectId: {provider_id} - {display_name}")
        else:
            print(f"⚠️ 未知类型 ({type(provider_id)}): {provider_id} - {display_name}")

    print("\n📊 统计:")
    print(f"   - ObjectId 类型: {len(objectid_providers)} 个")
    print(f"   - 字符串类型: {len(string_id_providers)} 个")

    if not string_id_providers:
        print("\n✅ 所有厂家 ID 都是 ObjectId 类型，无需修复")
        return

    print(f"\n🔧 开始修复 {len(string_id_providers)} 个字符串类型的 ID...")

    fixed_count = 0
    failed_count = 0

    for provider in string_id_providers:
        old_id = provider["_id"]
        display_name = provider.get("display_name", "未知")

        try:
            # 创建新的 ObjectId
            new_id = ObjectId()

            # 复制数据（除了 _id）
            new_provider = {k: v for k, v in provider.items() if k != "_id"}
            new_provider["_id"] = new_id
            new_provider["updated_at"] = datetime.utcnow()

            # 插入新记录
            await providers_collection.insert_one(new_provider)

            # 删除旧记录
            await providers_collection.delete_one({"_id": old_id})

            print(f"✅ 修复成功: {display_name}")
            print(f"   旧 ID (字符串): {old_id}")
            print(f"   新 ID (ObjectId): {new_id}")

            fixed_count += 1

        except Exception as e:
            print(f"❌ 修复失败: {display_name} - {e}")
            failed_count += 1

    print("\n📊 修复结果:")
    print(f"   - 成功: {fixed_count} 个")
    print(f"   - 失败: {failed_count} 个")

    if fixed_count > 0:
        print("\n⚠️ 注意：厂家 ID 已更改，前端可能需要刷新页面")

    client.close()


if __name__ == "__main__":
    asyncio.run(fix_provider_id_types())
