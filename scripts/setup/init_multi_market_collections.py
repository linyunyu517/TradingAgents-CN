#!/usr/bin/env python3
"""
MongoDB多市场集合初始化脚本（支持多数据源）

功能：
1. 创建港股集合（stock_basic_info_hk, market_quotes_hk 等）
2. 创建美股集合（stock_basic_info_us, market_quotes_us 等）
3. 创建对应索引（与A股集合保持一致）
4. 支持多数据源：(code, source) 联合唯一索引

设计说明：
- 参考A股多数据源设计，同一股票可有多个数据源记录
- 通过 (code, source) 联合唯一索引区分不同数据源
- 港股支持：yfinance, akshare
- 美股支持：yfinance, alphavantage（可选）

使用方法：
    python scripts/setup/init_multi_market_collections.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
from app.core.config import settings


async def create_hk_collections(db):
    """创建港股集合和索引"""
    logger.info("📊 开始创建港股集合...")

    # 1. 股票基础信息集合
    collection_name = "stock_basic_info_hk"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    # 创建索引（与A股保持一致，支持多数据源）
    collection = db[collection_name]
    # 🔥 联合唯一索引：(code, source) - 允许同一股票有多个数据源
    await collection.create_index([("code", 1), ("source", 1)], unique=True)
    await collection.create_index([("code", 1)])  # 非唯一索引，用于查询所有数据源
    await collection.create_index([("source", 1)])  # 数据源索引
    await collection.create_index([("market", 1)])
    await collection.create_index([("industry", 1)])
    await collection.create_index([("sector", 1)])  # GICS行业
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name} (支持多数据源)")

    # 2. 实时行情集合
    collection_name = "market_quotes_hk"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1)], unique=True)
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 3. 历史K线集合
    collection_name = "stock_daily_quotes_hk"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("trade_date", -1)])
    await collection.create_index([("code", 1), ("period", 1), ("trade_date", -1)])
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 4. 财务数据集合
    collection_name = "stock_financial_data_hk"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("report_date", 1)])
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 5. 新闻数据集合
    collection_name = "stock_news_hk"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("published_at", -1)])
    await collection.create_index([("published_at", -1)])
    await collection.create_index([("title", "text"), ("content", "text")])
    logger.info(f"✅ 创建索引: {collection_name}")

    logger.info("✅ 港股集合创建完成")


async def create_us_collections(db):
    """创建美股集合和索引"""
    logger.info("📊 开始创建美股集合...")

    # 1. 股票基础信息集合
    collection_name = "stock_basic_info_us"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    # 创建索引（与A股保持一致，支持多数据源）
    collection = db[collection_name]
    # 🔥 联合唯一索引：(code, source) - 允许同一股票有多个数据源
    await collection.create_index([("code", 1), ("source", 1)], unique=True)
    await collection.create_index([("code", 1)])  # 非唯一索引，用于查询所有数据源
    await collection.create_index([("source", 1)])  # 数据源索引
    await collection.create_index([("market", 1)])
    await collection.create_index([("industry", 1)])
    await collection.create_index([("sector", 1)])  # GICS行业
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name} (支持多数据源)")

    # 2. 实时行情集合
    collection_name = "market_quotes_us"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1)], unique=True)
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 3. 历史K线集合
    collection_name = "stock_daily_quotes_us"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("trade_date", -1)])
    await collection.create_index([("code", 1), ("period", 1), ("trade_date", -1)])
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 4. 财务数据集合
    collection_name = "stock_financial_data_us"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("report_date", 1)])
    await collection.create_index([("updated_at", 1)])
    logger.info(f"✅ 创建索引: {collection_name}")

    # 5. 新闻数据集合
    collection_name = "stock_news_us"
    if collection_name not in await db.list_collection_names():
        await db.create_collection(collection_name)
        logger.info(f"✅ 创建集合: {collection_name}")

    collection = db[collection_name]
    await collection.create_index([("code", 1), ("published_at", -1)])
    await collection.create_index([("published_at", -1)])
    await collection.create_index([("title", "text"), ("content", "text")])
    logger.info(f"✅ 创建索引: {collection_name}")

    logger.info("✅ 美股集合创建完成")


async def verify_collections(db):
    """验证集合创建情况"""
    logger.info("\n📋 验证集合创建情况...")

    all_collections = await db.list_collection_names()

    # 检查港股集合
    hk_collections = [
        "stock_basic_info_hk",
        "market_quotes_hk",
        "stock_daily_quotes_hk",
        "stock_financial_data_hk",
        "stock_news_hk",
    ]

    logger.info("\n港股集合:")
    for col in hk_collections:
        status = "✅" if col in all_collections else "❌"
        logger.info(f"  {status} {col}")

    # 检查美股集合
    us_collections = [
        "stock_basic_info_us",
        "market_quotes_us",
        "stock_daily_quotes_us",
        "stock_financial_data_us",
        "stock_news_us",
    ]

    logger.info("\n美股集合:")
    for col in us_collections:
        status = "✅" if col in all_collections else "❌"
        logger.info(f"  {status} {col}")

    # 统计索引数量
    logger.info("\n索引统计:")
    for col in hk_collections + us_collections:
        if col in all_collections:
            indexes = await db[col].list_indexes().to_list(length=None)
            logger.info(f"  {col}: {len(indexes)} 个索引")


async def main():
    """主函数"""
    logger.info("🚀 开始初始化多市场MongoDB集合...")

    try:
        # 连接MongoDB
        mongo_uri = settings.MONGO_URI
        client = AsyncIOMotorClient(mongo_uri)
        db = client[settings.MONGO_DB]

        logger.info(f"✅ 连接MongoDB成功: {settings.MONGO_DB}")

        # 创建港股集合
        await create_hk_collections(db)

        # 创建美股集合
        await create_us_collections(db)

        # 验证集合
        await verify_collections(db)

        logger.info("\n🎉 多市场集合初始化完成！")

        # 关闭连接
        client.close()

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
