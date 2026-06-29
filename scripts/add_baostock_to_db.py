#!/usr/bin/env python3
"""
将 BaoStock 数据源添加到 MongoDB 现有配置中。

此脚本执行以下操作：
1. 检查 system_configs 集合中是否已有 BaoStock 数据源配置
2. 如果没有，将 BaoStock 添加到 data_source_configs 数组
3. 检查 datasource_groupings 集合中是否已有 BaoStock 的 A股分组
4. 如果没有，添加 BaoStock 到 A股市场分类中
5. 检查 market_categories 集合中是否已有 A股分类
6. 如果没有，创建默认市场分类

用法:
    python scripts/add_baostock_to_db.py [--mongo-uri URI] [--dry-run]

示例:
    python scripts/add_baostock_to_db.py --dry-run    # 预览模式，不实际修改
    python scripts/add_baostock_to_db.py               # 实际执行
"""

import argparse
import os
import sys
from datetime import datetime, timezone

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from pymongo import MongoClient, errors
except ImportError:
    print("❌ 需要安装 pymongo: pip install pymongo")
    sys.exit(1)


def now_tz():
    """返回带时区的当前时间"""
    return datetime.now(timezone.utc).isoformat()


# BaoStock 数据源配置
BAOSTOCK_DATASOURCE = {
    "name": "BaoStock",
    "type": "baostock",
    "api_key": None,
    "api_secret": None,
    "endpoint": "http://baostock.com",
    "timeout": 30,
    "rate_limit": 100,
    "enabled": True,
    "priority": 3,
    "config_params": {},
    "description": "BaoStock免费证券数据平台（免费无需密钥）",
    "market_categories": ["a_shares"],
    "display_name": None,
    "provider": None,
    "created_at": now_tz(),
    "updated_at": now_tz(),
}

# BaoStock 数据源分组关系
BAOSTOCK_GROUPING = {
    "data_source_name": "BaoStock",
    "market_category_id": "a_shares",
    "priority": 3,
    "enabled": True,
    "created_at": now_tz(),
    "updated_at": now_tz(),
}


def get_mongo_db(mongo_uri: str, db_name: str = "tradingagentscn"):
    """连接 MongoDB 并返回数据库实例"""
    print(f"🔌 连接 MongoDB: {mongo_uri}")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    # 测试连接
    try:
        client.admin.command("ping")
        print(f"✅ MongoDB 连接成功，数据库: {db_name}")
    except errors.ConnectionFailure:
        print("❌ MongoDB 连接失败，请检查连接字符串")
        sys.exit(1)
    return db


def add_baostock_to_datasource_configs(db, dry_run: bool = False) -> bool:
    """将 BaoStock 添加到 system_configs 的 data_source_configs 数组中"""
    config_collection = db.system_configs

    # 查找活跃的配置
    active_config = config_collection.find_one({"is_active": True})
    if not active_config:
        print("ℹ️  没有找到活跃的系统配置（system_configs），跳过数据源配置更新")
        print("   ➡ 新配置将在下次应用启动时通过 _create_default_config() 自动创建")
        return False

    # 检查是否已存在 BaoStock
    existing_sources = active_config.get("data_source_configs", [])
    for ds in existing_sources:
        if ds.get("name") == "BaoStock":
            print("✅ BaoStock 已存在于 system_configs.data_source_configs 中")
            print(f"   当前状态: enabled={ds.get('enabled')}, priority={ds.get('priority')}")
            return False

    # 添加 BaoStock
    print("📝 将 BaoStock 添加到 system_configs.data_source_configs...")
    if dry_run:
        print("   [DRY RUN] 跳过实际写入")
        return True

    result = config_collection.update_one(
        {"is_active": True},
        {
            "$push": {"data_source_configs": BAOSTOCK_DATASOURCE},
            "$set": {"updated_at": now_tz()},
            "$inc": {"version": 1},
        },
    )

    if result.modified_count > 0:
        print("✅ 成功添加 BaoStock 到 system_configs (版本 +1)")
        return True
    print("❌ 添加 BaoStock 到 system_configs 失败")
    return False


def add_baostock_to_datasource_groupings(db, dry_run: bool = False) -> bool:
    """将 BaoStock 添加到 datasource_groupings 集合（A股分组）"""
    groupings_collection = db.datasource_groupings

    # 检查是否已存在
    existing = groupings_collection.find_one({"data_source_name": "BaoStock", "market_category_id": "a_shares"})
    if existing:
        print("✅ BaoStock 已存在于 datasource_groupings (a_shares 分类)")
        print(f"   当前状态: enabled={existing.get('enabled')}, priority={existing.get('priority')}")
        return False

    # 检查 a_shares 市场分类是否存在
    categories_collection = db.market_categories
    a_shares = categories_collection.find_one({"id": "a_shares"})
    if not a_shares:
        print("ℹ️  A股市场分类 (a_shares) 不存在，需要在添加分组前创建")
        # 尝试创建默认市场分类
        print("📝 创建默认 A股市场分类...")
        if not dry_run:
            a_shares_category = {
                "id": "a_shares",
                "name": "a_shares",
                "display_name": "A股",
                "description": "中国A股市场数据源",
                "enabled": True,
                "sort_order": 1,
                "created_at": now_tz(),
                "updated_at": now_tz(),
            }
            categories_collection.insert_one(a_shares_category)
            print("✅ 已创建 A股市场分类")
        else:
            print("   [DRY RUN] 跳过创建")

    # 添加分组
    print("📝 将 BaoStock 添加到 datasource_groupings (a_shares 分类)...")
    if dry_run:
        print("   [DRY RUN] 跳过实际写入")
        return True

    result = groupings_collection.insert_one(BAOSTOCK_GROUPING)
    if result.inserted_id:
        print(f"✅ 成功添加 BaoStock 到 datasource_groupings (ID: {result.inserted_id})")
        return True
    print("❌ 添加 BaoStock 到 datasource_groupings 失败")
    return False


def show_current_status(db):
    """显示当前 MongoDB 中数据源配置状态"""
    print("\n" + "=" * 60)
    print("📊 当前 MongoDB 数据源状态")
    print("=" * 60)

    # 1. 系统配置中的 data_source_configs
    config_collection = db.system_configs
    active_config = config_collection.find_one({"is_active": True})
    if active_config:
        ds_configs = active_config.get("data_source_configs", [])
        print(f"\n📁 system_configs.data_source_configs ({len(ds_configs)} 个):")
        for ds in ds_configs:
            name = ds.get("name", "?")
            ds_type = ds.get("type", "?")
            enabled = ds.get("enabled", False)
            priority = ds.get("priority", 0)
            status = "✅ 已启用" if enabled else "❌ 未启用"
            print(f"   - {name:15s} | type={ds_type:15s} | priority={priority:3d} | {status}")
    else:
        print("\n⚠️  没有活跃的系统配置")

    # 2. 数据源分组
    groupings_collection = db.datasource_groupings
    groupings = list(groupings_collection.find({}))
    print(f"\n📁 datasource_groupings ({len(groupings)} 个):")
    for g in groupings:
        ds_name = g.get("data_source_name", "?")
        cat_id = g.get("market_category_id", "?")
        enabled = g.get("enabled", False)
        priority = g.get("priority", 0)
        print(f"   - {ds_name:15s} → {cat_id:15s} | priority={priority:3d} | enabled={enabled}")

    # 3. 市场分类
    categories_collection = db.market_categories
    categories = list(categories_collection.find({}))
    print(f"\n📁 market_categories ({len(categories)} 个):")
    for c in categories:
        print(f"   - {c.get('id', '?'):15s} | {c.get('display_name', '?'):10s} | enabled={c.get('enabled', False)}")


def main():
    parser = argparse.ArgumentParser(description="将 BaoStock 数据源添加到 MongoDB")
    parser.add_argument(
        "--mongo-uri", default="mongodb://localhost:27017", help="MongoDB 连接字符串 (默认: mongodb://localhost:27017)",
    )
    parser.add_argument("--db-name", default="tradingagentscn", help="数据库名称 (默认: tradingagentscn)")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改数据库")
    args = parser.parse_args()

    print("🚀 BaoStock MongoDB 配置迁移脚本")
    print("=" * 60)

    # 连接数据库
    db = get_mongo_db(args.mongo_uri, args.db_name)

    # 显示当前状态
    show_current_status(db)

    print("\n" + "=" * 60)
    print("🔧 执行配置更新")
    print("=" * 60)

    # 添加数据源配置
    print("\n[步骤 1/2] 更新 system_configs.data_source_configs")
    added_to_config = add_baostock_to_datasource_configs(db, dry_run=args.dry_run)

    # 添加数据源分组
    print("\n[步骤 2/2] 更新 datasource_groupings")
    added_to_grouping = add_baostock_to_datasource_groupings(db, dry_run=args.dry_run)

    # 总结
    print("\n" + "=" * 60)
    if args.dry_run:
        print("🏁 预览完成（未实际修改数据库）")
        print("   移除 --dry-run 参数以实际执行修改")
    elif added_to_config or added_to_grouping:
        print("✅ MongoDB 配置更新完成")
        if added_to_config:
            print("   - system_configs.data_source_configs: ✅ BaoStock 已添加")
        else:
            print("   - system_configs.data_source_configs: ℹ️  无需更新（已存在或无活跃配置）")
        if added_to_grouping:
            print("   - datasource_groupings (a_shares): ✅ BaoStock 已添加")
        else:
            print("   - datasource_groupings (a_shares): ℹ️  无需更新（已存在）")
    else:
        print("ℹ️  无需更新，BaoStock 数据源已完整配置")
    print("=" * 60)

    # 验证
    if not args.dry_run:
        print("\n📋 验证最终状态...")
        show_current_status(db)


if __name__ == "__main__":
    main()
