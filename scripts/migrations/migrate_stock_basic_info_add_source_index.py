#!/usr/bin/env python3
"""
数据迁移脚本：为 stock_basic_info 集合添加 (code, source) 联合唯一索引

背景：
- 原来的设计：每只股票只有一条记录，使用 code 唯一索引
- 新的设计：每只股票可以有多条记录（来自不同数据源），使用 (code, source) 联合唯一索引

迁移步骤：
1. 检查现有数据的 source 字段
2. 为没有 source 字段的数据添加默认值
3. 删除旧的 code 唯一索引
4. 创建新的 (code, source) 联合唯一索引
5. 验证迁移结果

运行方式：
    python scripts/migrations/migrate_stock_basic_info_add_source_index.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def migrate_stock_basic_info():
    """迁移 stock_basic_info 集合"""

    # 🔥 使用配置文件中的连接信息
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db["stock_basic_info"]

    try:
        logger.info("=" * 60)
        logger.info("开始迁移 stock_basic_info 集合")
        logger.info("=" * 60)

        # 步骤1：检查现有数据
        logger.info("\n📊 步骤1：检查现有数据")
        total_count = await collection.count_documents({})
        logger.info(f"   总记录数: {total_count}")

        # 统计各数据源的记录数
        pipeline = [{"$group": {"_id": "$source", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
        source_stats = await collection.aggregate(pipeline).to_list(None)

        logger.info("   数据源分布:")
        for stat in source_stats:
            source = stat["_id"] if stat["_id"] else "无 source 字段"
            count = stat["count"]
            logger.info(f"      {source}: {count} 条")

        # 步骤2：为没有 source 字段的数据添加默认值
        logger.info("\n🔧 步骤2：为没有 source 字段的数据添加默认值")
        no_source_count = await collection.count_documents({"source": {"$exists": False}})

        if no_source_count > 0:
            logger.info(f"   发现 {no_source_count} 条记录没有 source 字段")
            logger.info("   将为这些记录添加 source='unknown'")

            result = await collection.update_many(
                {"source": {"$exists": False}}, {"$set": {"source": "unknown", "updated_at": datetime.now()}},
            )
            logger.info(f"   ✅ 已更新 {result.modified_count} 条记录")
        else:
            logger.info("   ✅ 所有记录都有 source 字段")

        # 步骤3：检查是否有重复的 (code, source) 组合
        logger.info("\n🔍 步骤3：检查是否有重复的 (code, source) 组合")
        pipeline = [
            {"$group": {"_id": {"code": "$code", "source": "$source"}, "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        duplicates = await collection.aggregate(pipeline).to_list(None)

        if duplicates:
            logger.warning(f"   ⚠️ 发现 {len(duplicates)} 组重复数据")
            logger.info("   处理重复数据（保留最新的，删除旧的）...")

            for dup in duplicates:
                code = dup["_id"]["code"]
                source = dup["_id"]["source"]
                ids = dup["ids"]

                # 获取所有重复记录，按 updated_at 排序
                docs = await collection.find({"_id": {"$in": ids}}).sort("updated_at", -1).to_list(None)

                # 保留第一条（最新的），删除其他的
                docs[0]["_id"]
                delete_ids = [doc["_id"] for doc in docs[1:]]

                if delete_ids:
                    result = await collection.delete_many({"_id": {"$in": delete_ids}})
                    logger.info(f"      删除重复记录: code={code}, source={source}, 删除 {result.deleted_count} 条")
        else:
            logger.info("   ✅ 没有重复的 (code, source) 组合")

        # 步骤4：删除旧的唯一索引
        logger.info("\n🗑️  步骤4：删除旧的唯一索引")
        indexes = await collection.index_information()

        # 查找 code 唯一索引
        code_unique_index = None
        for idx_name, idx_info in indexes.items():
            if idx_info.get("unique") and idx_info.get("key") == [("code", 1)]:
                code_unique_index = idx_name
                break

        if code_unique_index:
            logger.info(f"   发现旧的 code 唯一索引: {code_unique_index}")
            await collection.drop_index(code_unique_index)
            logger.info(f"   ✅ 已删除索引: {code_unique_index}")
        else:
            logger.info("   ⚠️ 未找到 code 唯一索引（可能已被删除）")

        # 🔥 查找并删除 full_symbol 唯一索引
        full_symbol_unique_index = None
        for idx_name, idx_info in indexes.items():
            if idx_info.get("unique") and idx_info.get("key") == [("full_symbol", 1)]:
                full_symbol_unique_index = idx_name
                break

        if full_symbol_unique_index:
            logger.info(f"   发现旧的 full_symbol 唯一索引: {full_symbol_unique_index}")
            await collection.drop_index(full_symbol_unique_index)
            logger.info(f"   ✅ 已删除索引: {full_symbol_unique_index}")
        else:
            logger.info("   ⚠️ 未找到 full_symbol 唯一索引（可能已被删除）")

        # 步骤5：创建新的 (code, source) 联合唯一索引
        logger.info("\n🔧 步骤5：创建新的 (code, source) 联合唯一索引")

        # 检查是否已存在
        existing_index = None
        indexes = await collection.index_information()
        for idx_name, idx_info in indexes.items():
            if idx_info.get("key") == [("code", 1), ("source", 1)]:
                existing_index = idx_name
                break

        if existing_index:
            logger.info(f"   ⚠️ 索引已存在: {existing_index}")
        else:
            await collection.create_index(
                [("code", ASCENDING), ("source", ASCENDING)], unique=True, name="uniq_code_source",
            )
            logger.info("   ✅ 已创建联合唯一索引: uniq_code_source")

        # 步骤6：创建辅助索引
        logger.info("\n🔧 步骤6：创建辅助索引")

        # code 非唯一索引（用于查询所有数据源）
        await collection.create_index([("code", ASCENDING)], name="idx_code")
        logger.info("   ✅ 已创建索引: idx_code")

        # source 索引（用于按数据源查询）
        await collection.create_index([("source", ASCENDING)], name="idx_source")
        logger.info("   ✅ 已创建索引: idx_source")

        # 步骤7：验证迁移结果
        logger.info("\n✅ 步骤7：验证迁移结果")

        # 重新统计数据
        total_count_after = await collection.count_documents({})
        logger.info(f"   迁移后总记录数: {total_count_after}")

        # 统计各数据源的记录数
        source_stats_after = await collection.aggregate(pipeline).to_list(None)
        logger.info("   迁移后数据源分布:")
        for stat in source_stats_after:
            source = stat["_id"] if stat["_id"] else "无 source 字段"
            count = stat["count"]
            logger.info(f"      {source}: {count} 条")

        # 列出所有索引
        indexes_after = await collection.index_information()
        logger.info("   当前索引:")
        for idx_name, idx_info in indexes_after.items():
            unique = " (唯一)" if idx_info.get("unique") else ""
            logger.info(f"      {idx_name}: {idx_info.get('key')}{unique}")

        logger.info("\n" + "=" * 60)
        logger.info("✅ 迁移完成！")
        logger.info("=" * 60)

        # 提示
        logger.info("\n📝 后续步骤:")
        logger.info("   1. 重新运行数据同步任务，确保每个数据源独立存储")
        logger.info("   2. 查询时可以指定 source 参数，或使用默认优先级")
        logger.info("   3. 监控日志，确认数据源隔离正常工作")

    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}", exc_info=True)
        raise
    finally:
        client.close()


async def rollback_migration():
    """回滚迁移（恢复到单数据源模式）"""

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["tradingagents"]
    collection = db["stock_basic_info"]

    try:
        logger.info("=" * 60)
        logger.info("开始回滚迁移")
        logger.info("=" * 60)

        # 删除联合唯一索引
        logger.info("\n🗑️  删除 (code, source) 联合唯一索引")
        try:
            await collection.drop_index("uniq_code_source")
            logger.info("   ✅ 已删除索引: uniq_code_source")
        except Exception as e:
            logger.warning(f"   ⚠️ 删除索引失败: {e}")

        # 删除辅助索引
        try:
            await collection.drop_index("idx_source")
            logger.info("   ✅ 已删除索引: idx_source")
        except Exception as e:
            logger.warning(f"   ⚠️ 删除索引失败: {e}")

        # 恢复 code 唯一索引
        logger.info("\n🔧 恢复 code 唯一索引")

        # 先删除重复数据（保留 tushare 数据源）
        logger.info("   处理重复数据（保留 tushare 数据源）...")
        pipeline = [
            {"$group": {"_id": "$code", "count": {"$sum": 1}, "docs": {"$push": "$$ROOT"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        duplicates = await collection.aggregate(pipeline).to_list(None)

        if duplicates:
            logger.info(f"   发现 {len(duplicates)} 只股票有多个数据源")

            for dup in duplicates:
                code = dup["_id"]
                docs = dup["docs"]

                # 优先保留 tushare，其次 multi_source，最后其他
                priority = {"tushare": 3, "multi_source": 2}
                docs_sorted = sorted(docs, key=lambda x: priority.get(x.get("source"), 1), reverse=True)

                docs_sorted[0]["_id"]
                delete_ids = [doc["_id"] for doc in docs_sorted[1:]]

                if delete_ids:
                    result = await collection.delete_many({"_id": {"$in": delete_ids}})
                    logger.info(
                        f"      code={code}: 保留 {docs_sorted[0].get('source')}，删除 {result.deleted_count} 条",
                    )

        # 创建 code 唯一索引
        await collection.create_index([("code", ASCENDING)], unique=True, name="uniq_code")
        logger.info("   ✅ 已创建索引: uniq_code")

        logger.info("\n✅ 回滚完成！")

    except Exception as e:
        logger.error(f"❌ 回滚失败: {e}", exc_info=True)
        raise
    finally:
        client.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        # 回滚模式
        asyncio.run(rollback_migration())
    else:
        # 正常迁移
        asyncio.run(migrate_stock_basic_info())
