"""
检查脚本：查看 MongoDB 中的 system_config 集合
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from pymongo import MongoClient

from app.core.config import settings


def check_system_config():
    """检查 system_config 集合"""

    print("=" * 80)
    print("检查：MongoDB system_config 集合")
    print("=" * 80)

    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    # 列出所有集合
    print("\n📋 数据库中的集合：")
    collections = db.list_collection_names()
    for coll in collections:
        print(f"  - {coll}")

    # 检查 system_config 集合
    if "system_config" in collections:
        print("\n✅ system_config 集合存在")

        collection = db.system_config

        # 查询所有文档
        docs = list(collection.find())
        print(f"\n📊 system_config 集合中的文档数量: {len(docs)}")

        for i, doc in enumerate(docs, 1):
            print(f"\n📄 文档 {i}:")
            print(f"  _id: {doc.get('_id')}")

            if "llm_configs" in doc:
                llm_configs = doc["llm_configs"]
                print(f"  llm_configs 数量: {len(llm_configs)}")

                # 查找 gemini-2.5-flash
                for config in llm_configs:
                    if config.get("model_name") == "gemini-2.5-flash":
                        print("\n  ✅ 找到 gemini-2.5-flash:")
                        print(f"    - model_name: {config.get('model_name')}")
                        print(f"    - provider: {config.get('provider')}")
                        print(f"    - capability_level: {config.get('capability_level')}")
                        print(f"    - suitable_roles: {config.get('suitable_roles')}")
                        print(f"    - features: {config.get('features')}")
                        print(f"    - recommended_depths: {config.get('recommended_depths')}")
                        break
                else:
                    print("\n  ❌ 未找到 gemini-2.5-flash")
            else:
                print("  ❌ 没有 llm_configs 字段")
    else:
        print("\n❌ system_config 集合不存在")

    client.close()

    print("\n" + "=" * 80)
    print("检查完成！")
    print("=" * 80)


if __name__ == "__main__":
    check_system_config()
