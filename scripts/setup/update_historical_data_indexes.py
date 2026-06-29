#!/usr/bin/env python3
"""
更新历史数据集合索引
添加周期字段支持
"""

import asyncio
import logging
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_historical_data_indexes():
    """更新历史数据集合索引"""
    try:
        # 连接MongoDB（使用配置）
        from app.core.config import settings

        client = AsyncIOMotorClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]

        logger.info("🚀 开始更新历史数据集合索引...")

        # 获取集合
        collection = db.stock_daily_quotes

        # 1. 删除旧的唯一索引
        logger.info("🗑️ 删除旧的唯一索引...")
        try:
            await collection.drop_index("symbol_date_source_unique")
            logger.info("✅ 旧索引删除成功")
        except Exception as e:
            logger.info(f"⚠️ 旧索引不存在或删除失败: {e}")

        # 2. 为现有数据添加period字段
        logger.info("📝 为现有数据添加period字段...")
        result = await collection.update_many({"period": {"$exists": False}}, {"$set": {"period": "daily"}})
        logger.info(f"✅ 更新了 {result.modified_count} 条记录")

        # 3. 创建新的唯一索引
        logger.info("📊 创建新的唯一索引...")
        await collection.create_index(
            [("symbol", 1), ("trade_date", 1), ("data_source", 1), ("period", 1)],
            unique=True,
            name="symbol_date_source_period_unique",
        )

        # 4. 创建周期相关索引
        logger.info("📋 创建周期相关索引...")

        # 周期索引
        await collection.create_index([("period", 1)], name="period_index")

        # 复合索引：股票+周期+日期
        await collection.create_index(
            [("symbol", 1), ("period", 1), ("trade_date", -1)], name="symbol_period_date_index",
        )

        logger.info("✅ 新索引创建完成")

        # 5. 显示集合统计
        count = await collection.count_documents({})
        indexes = await collection.list_indexes().to_list(length=None)

        logger.info("\n📊 集合统计:")
        logger.info("  - 集合名: stock_daily_quotes")
        logger.info(f"  - 文档数量: {count}")
        logger.info(f"  - 索引数量: {len(indexes)}")

        logger.info("\n📋 索引列表:")
        for idx in indexes:
            logger.info(f"  - {idx['name']}: {idx.get('key', {})}")

        # 6. 按周期统计数据
        logger.info("\n📈 按周期统计:")
        pipeline = [{"$group": {"_id": "$period", "count": {"$sum": 1}}}]

        period_stats = await collection.aggregate(pipeline).to_list(length=None)
        for stat in period_stats:
            logger.info(f"  - {stat['_id']}: {stat['count']}条记录")

        logger.info("\n🎉 历史数据集合索引更新完成！")

        # 关闭连接
        client.close()
        return True

    except Exception as e:
        logger.error(f"❌ 更新历史数据集合索引失败: {e}")
        return False


async def main():
    """主函数"""
    print("🎯 历史数据集合索引更新工具")
    print("📊 添加周期字段支持，更新索引结构")
    print("=" * 60)

    success = await update_historical_data_indexes()

    if success:
        print("\n✅ 索引更新成功！")
        print("\n📝 更新内容:")
        print("  - 删除旧的三字段唯一索引")
        print("  - 为现有数据添加period字段")
        print("  - 创建新的四字段唯一索引")
        print("  - 添加周期相关查询索引")

        print("\n🔧 新的查询方式:")
        print("  # 查询日线数据")
        print('  db.stock_daily_quotes.find({"symbol": "000001", "period": "daily"})')
        print("  ")
        print("  # 查询周线数据")
        print('  db.stock_daily_quotes.find({"symbol": "000001", "period": "weekly"})')
        print("  ")
        print("  # 查询月线数据")
        print('  db.stock_daily_quotes.find({"symbol": "000001", "period": "monthly"})')

    else:
        print("\n❌ 索引更新失败，请检查MongoDB连接")

    return success


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        sys.exit(1)
