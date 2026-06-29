"""
直接测试 MongoDB 读取
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient

from app.core.config import settings


def test_direct():
    """直接测试"""

    print("=" * 80)
    print("直接测试 MongoDB 读取")
    print("=" * 80)

    print("\n📊 连接信息：")
    print(f"  MONGO_URI: {settings.MONGO_URI}")
    print(f"  MONGO_DB: {settings.MONGO_DB}")

    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.system_configs

    print("\n🔍 查询 system_configs 集合（所有文档）...")
    all_docs = list(collection.find())
    print(f"  总文档数: {len(all_docs)}")

    for i, doc in enumerate(all_docs, 1):
        print(f"\n📄 文档 {i}:")
        print(f"  _id: {doc.get('_id')}")
        print(f"  is_active: {doc.get('is_active')}")
        print(f"  version: {doc.get('version')}")
        print(f"  llm_configs 数量: {len(doc.get('llm_configs', []))}")

    print("\n🔍 查询 system_configs 集合（is_active=True）...")
    doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

    if doc:
        print("✅ 找到文档")
        print(f"  _id: {doc.get('_id')}")
        print(f"  is_active: {doc.get('is_active')}")
        print(f"  version: {doc.get('version')}")

        if "llm_configs" in doc:
            llm_configs = doc["llm_configs"]
            print(f"  llm_configs 数量: {len(llm_configs)}")

            # 查找 gemini-2.5-flash
            for config in llm_configs:
                if config.get("model_name") == "gemini-2.5-flash":
                    print("\n✅ 找到 gemini-2.5-flash:")
                    print(f"  - model_name: {config.get('model_name')}")
                    print(f"  - provider: {config.get('provider')}")
                    print(f"  - capability_level: {config.get('capability_level')}")
                    print(f"  - suitable_roles: {config.get('suitable_roles')}")
                    print(f"  - features: {config.get('features')}")
                    break
            else:
                print("\n❌ 未找到 gemini-2.5-flash")
                print("\n📋 所有模型名称：")
                for i, config in enumerate(llm_configs[:10], 1):
                    print(f"  {i}. {config.get('model_name')}")
        else:
            print("  ❌ 没有 llm_configs 字段")
    else:
        print("❌ 未找到文档")

    client.close()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_direct()
