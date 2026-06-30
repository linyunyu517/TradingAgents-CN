#!/usr/bin/env python3
"""检查数据库中数据源配置的名称"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from app.core.database import get_mongo_db_sync

db = get_mongo_db_sync()

# 先列出所有集合
print("📋 数据库中的集合:")
for collection_name in db.list_collection_names():
    print(f"  - {collection_name}")
print()

# 查询激活的配置
config = db.system_configs.find_one({"is_active": True})

if not config:
    print("⚠️ 没有找到激活的配置，查找最新的配置...")
    config = db.system_configs.find_one(sort=[("version", -1)])

if not config:
    print("❌ 数据库中没有找到 system_config")
    sys.exit(1)

print("✅ 找到配置")
print(f"版本: {config.get('version')}")
print(f"是否激活: {config.get('is_active')}")
print()

datasources = config.get("data_source_configs", [])
print(f"📊 数据源配置数量: {len(datasources)}")
print()

for ds in datasources:
    name = ds.get("name", "N/A")
    ds_type = ds.get("type", "N/A")
    api_key = ds.get("api_key", "")
    enabled = ds.get("enabled", False)

    print(f"数据源: {name}")
    print(f"  类型: {ds_type}")
    print(f"  启用: {enabled}")
    print(f"  API Key: {'✅ 已配置' if api_key and len(api_key) > 10 else '❌ 未配置'}")
    if api_key:
        print(f"  API Key 长度: {len(api_key)}")
        print(f"  API Key 前缀: {api_key[:10]}...")
    print()
