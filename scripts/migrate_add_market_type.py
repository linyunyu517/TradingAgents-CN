#!/usr/bin/env python3
"""
数据迁移脚本：为已有的分析报告添加 market_type 字段

使用方法：
    python scripts/migrate_add_market_type.py [--dry-run]

参数：
    --dry-run: 只显示将要更新的数据，不实际执行更新
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import close_database, get_mongo_db, init_database
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.stock_utils import StockUtils

logger = get_logger("default")


async def migrate_add_market_type(dry_run: bool = False):
    """为已有的分析报告添加 market_type 字段"""

    logger.info("=" * 60)
    logger.info("开始数据迁移：添加 market_type 字段")
    logger.info("=" * 60)

    if dry_run:
        logger.info("🔍 DRY RUN 模式：只显示将要更新的数据，不实际执行更新")

    try:
        # 初始化数据库连接
        logger.info("📡 正在连接数据库...")
        await init_database()
        logger.info("✅ 数据库连接成功")

        # 获取数据库连接
        db = get_mongo_db()

        # 查找所有缺少 market_type 字段的报告
        query = {"market_type": {"$exists": False}}
        cursor = db.analysis_reports.find(query)

        # 统计
        total_count = await db.analysis_reports.count_documents(query)
        logger.info(f"📊 找到 {total_count} 条需要更新的报告")

        if total_count == 0:
            logger.info("✅ 所有报告都已包含 market_type 字段，无需迁移")
            return

        # 市场类型映射
        market_type_map = {"china_a": "A股", "hong_kong": "港股", "us": "美股", "unknown": "A股"}

        # 更新统计
        updated_count = 0
        error_count = 0

        # 逐条处理
        async for doc in cursor:
            try:
                analysis_id = doc.get("analysis_id", "unknown")
                stock_symbol = doc.get("stock_symbol", "")

                if not stock_symbol:
                    logger.warning(f"⚠️ 跳过：{analysis_id} - 缺少 stock_symbol")
                    error_count += 1
                    continue

                # 根据股票代码推断市场类型
                market_info = StockUtils.get_market_info(stock_symbol)
                market_type = market_type_map.get(market_info.get("market", "unknown"), "A股")

                logger.info(f"📝 {analysis_id}: {stock_symbol} -> {market_type}")

                if not dry_run:
                    # 执行更新
                    result = await db.analysis_reports.update_one(
                        {"_id": doc["_id"]}, {"$set": {"market_type": market_type}},
                    )

                    if result.modified_count > 0:
                        updated_count += 1
                    else:
                        logger.warning(f"⚠️ 更新失败：{analysis_id}")
                        error_count += 1
                else:
                    # DRY RUN 模式，只统计
                    updated_count += 1

            except Exception as e:
                logger.error(f"❌ 处理失败：{doc.get('analysis_id', 'unknown')} - {e}")
                error_count += 1

        # 输出统计结果
        logger.info("=" * 60)
        logger.info("迁移完成")
        logger.info("=" * 60)
        logger.info(f"📊 总数：{total_count}")
        logger.info(f"✅ 成功：{updated_count}")
        logger.info(f"❌ 失败：{error_count}")

        if dry_run:
            logger.info("\n💡 提示：移除 --dry-run 参数以实际执行更新")

    except Exception as e:
        logger.error(f"❌ 迁移失败：{e}")
        import traceback

        logger.error(traceback.format_exc())


async def verify_migration():
    """验证迁移结果"""

    logger.info("\n" + "=" * 60)
    logger.info("验证迁移结果")
    logger.info("=" * 60)

    try:
        db = get_mongo_db()

        # 统计各市场类型的报告数量
        pipeline = [{"$group": {"_id": "$market_type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]

        cursor = db.analysis_reports.aggregate(pipeline)

        logger.info("📊 各市场类型的报告数量：")
        total = 0
        async for doc in cursor:
            market_type = doc["_id"] or "未知"
            count = doc["count"]
            total += count
            logger.info(f"   {market_type}: {count}")

        logger.info(f"   总计: {total}")

        # 检查是否还有缺少 market_type 的报告
        missing_count = await db.analysis_reports.count_documents({"market_type": {"$exists": False}})

        if missing_count > 0:
            logger.warning(f"⚠️ 仍有 {missing_count} 条报告缺少 market_type 字段")
        else:
            logger.info("✅ 所有报告都已包含 market_type 字段")

    except Exception as e:
        logger.error(f"❌ 验证失败：{e}")


async def main():
    """主函数"""

    try:
        # 解析命令行参数
        dry_run = "--dry-run" in sys.argv

        # 执行迁移
        await migrate_add_market_type(dry_run=dry_run)

        # 验证结果（仅在非 DRY RUN 模式下）
        if not dry_run:
            await verify_migration()

    finally:
        # 关闭数据库连接
        logger.info("\n📡 正在关闭数据库连接...")
        await close_database()
        logger.info("✅ 数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())
