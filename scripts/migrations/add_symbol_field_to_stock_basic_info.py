#!/usr/bin/env python3
"""
迁移脚本：为 stock_basic_info 集合添加 symbol 字段

背景：
- 之前的同步服务没有添加 symbol 字段
- 现在需要为现有数据添加 symbol 字段以支持新的查询逻辑
- symbol 字段应该等于 code 字段

使用方法：
    python scripts/migrations/add_symbol_field_to_stock_basic_info.py
"""

import asyncio
import logging
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def get_mongo_db() -> AsyncIOMotorDatabase | None:
    """获取 MongoDB 数据库连接"""
    try:
        from app.core.config import get_settings

        settings = get_settings()
        client = AsyncIOMotorClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        # 测试连接
        await db.command("ping")
        logger.info(f"✅ MongoDB 连接成功: {settings.MONGO_DB}")
        return db
    except Exception as e:
        logger.error(f"❌ MongoDB 连接失败: {e}")
        return None


async def migrate_add_symbol_field():
    """为 stock_basic_info 集合添加 symbol 字段"""
    db = await get_mongo_db()
    if db is None:
        logger.error("❌ 无法连接到 MongoDB，迁移中止")
        return False

    collection = db["stock_basic_info"]

    try:
        logger.info("=" * 80)
        logger.info("开始迁移：为 stock_basic_info 添加 symbol 字段")
        logger.info("=" * 80)

        # 1. 检查集合状态
        total_count = await collection.count_documents({})
        logger.info("\n📊 集合状态检查:")
        logger.info(f"  总记录数: {total_count}")

        # 检查有多少记录已经有 symbol 字段
        with_symbol = await collection.count_documents({"symbol": {"$exists": True}})
        logger.info(f"  已有 symbol 字段的记录: {with_symbol}")

        # 检查有多少记录没有 symbol 字段
        without_symbol = await collection.count_documents({"symbol": {"$exists": False}})
        logger.info(f"  缺少 symbol 字段的记录: {without_symbol}")

        if without_symbol == 0:
            logger.info("\n✅ 所有记录都已有 symbol 字段，无需迁移")
            return True

        # 2. 执行迁移
        logger.info(f"\n📝 开始为 {without_symbol} 条记录添加 symbol 字段...")

        result = await collection.update_many({"symbol": {"$exists": False}}, [{"$set": {"symbol": "$code"}}])

        logger.info("\n✅ 迁移完成:")
        logger.info(f"  修改的记录数: {result.modified_count}")
        logger.info(f"  匹配的记录数: {result.matched_count}")

        # 3. 验证迁移结果
        logger.info("\n🔍 验证迁移结果...")

        after_with_symbol = await collection.count_documents({"symbol": {"$exists": True}})
        after_without_symbol = await collection.count_documents({"symbol": {"$exists": False}})

        logger.info(f"  现在有 symbol 字段的记录: {after_with_symbol}")
        logger.info(f"  现在缺少 symbol 字段的记录: {after_without_symbol}")

        if after_without_symbol == 0:
            logger.info("\n✅ 迁移验证成功！所有记录都已有 symbol 字段")

            # 4. 检查数据一致性
            logger.info("\n🔍 检查数据一致性...")

            # 检查是否有 symbol != code 的记录
            inconsistent = await collection.count_documents({"$expr": {"$ne": ["$symbol", "$code"]}})

            if inconsistent == 0:
                logger.info("  ✅ 所有记录的 symbol 和 code 字段一致")
            else:
                logger.warning(f"  ⚠️ 发现 {inconsistent} 条记录的 symbol 和 code 不一致")

            # 5. 显示示例数据
            logger.info("\n📋 示例数据（前5条）:")
            sample_docs = (
                await collection.find({"symbol": {"$exists": True}}, {"_id": 0, "code": 1, "symbol": 1, "name": 1})
                .limit(5)
                .to_list(5)
            )

            for i, doc in enumerate(sample_docs, 1):
                logger.info(f"  {i}. code={doc.get('code')}, symbol={doc.get('symbol')}, name={doc.get('name')}")

            logger.info("\n" + "=" * 80)
            logger.info("✅ 迁移成功完成！")
            logger.info("=" * 80)
            return True
        logger.error(f"\n❌ 迁移验证失败！仍有 {after_without_symbol} 条记录缺少 symbol 字段")
        return False

    except Exception as e:
        logger.error(f"\n❌ 迁移失败: {e}", exc_info=True)
        return False


async def main():
    """主函数"""
    success = await migrate_add_symbol_field()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
