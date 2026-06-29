"""
检查脚本：查看 gemini-2.5-flash 在数据库中的完整配置
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def check_gemini_config():
    """检查 gemini-2.5-flash 配置"""

    print("=" * 80)
    print("检查：gemini-2.5-flash 数据库配置")
    print("=" * 80)

    from motor.motor_asyncio import AsyncIOMotorClient

    from app.core.config import settings

    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.llm_configs

    # 查询 gemini-2.5-flash
    doc = await collection.find_one({"model_name": "gemini-2.5-flash"})

    if doc:
        print("\n✅ 找到 gemini-2.5-flash 配置：\n")

        # 打印所有字段
        for key, value in doc.items():
            if key == "_id":
                continue
            print(f"  {key}: {value}")

        # 特别关注 features 字段
        print("\n🔍 features 字段详情：")
        features = doc.get("features", [])
        print(f"  - 类型: {type(features)}")
        print(f"  - 值: {features}")
        print(f"  - 长度: {len(features)}")

        if features:
            print("  - 内容：")
            for i, feature in enumerate(features, 1):
                print(f"    {i}. {feature} (类型: {type(feature).__name__})")
        else:
            print("  - ⚠️ features 字段为空！")

        # 特别关注 suitable_roles 字段
        print("\n🔍 suitable_roles 字段详情：")
        roles = doc.get("suitable_roles", [])
        print(f"  - 类型: {type(roles)}")
        print(f"  - 值: {roles}")
        print(f"  - 长度: {len(roles)}")

        if roles:
            print("  - 内容：")
            for i, role in enumerate(roles, 1):
                print(f"    {i}. {role} (类型: {type(role).__name__})")
    else:
        print("\n❌ 未找到 gemini-2.5-flash 配置")

    # 查询所有 Google 模型
    print("\n" + "=" * 80)
    print("所有 Google 模型配置：")
    print("=" * 80)

    cursor = collection.find({"provider": "google"})
    docs = await cursor.to_list(length=None)

    if docs:
        for doc in docs:
            model_name = doc.get("model_name")
            features = doc.get("features", [])
            roles = doc.get("suitable_roles", [])
            capability = doc.get("capability_level", 0)

            print(f"\n📊 {model_name}:")
            print(f"  - capability_level: {capability}")
            print(f"  - suitable_roles: {roles}")
            print(f"  - features: {features}")
    else:
        print("\n❌ 未找到任何 Google 模型配置")

    client.close()

    print("\n" + "=" * 80)
    print("检查完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(check_gemini_config())
