"""
检查 stock_financial_data 集合中的数据
验证 ROE 和负债率数据是否存在
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from app.core.config import get_settings
from app.core.database import get_mongo_db, init_mongodb

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


async def check_financial_data():
    """检查财务数据集合"""
    logger.info("=" * 80)
    logger.info("检查 stock_financial_data 集合")
    logger.info("=" * 80)

    # 初始化数据库连接
    settings = get_settings()
    await init_mongodb(settings.MONGO_URI, settings.MONGO_DB)

    db = get_mongo_db()

    # 1. 检查集合是否存在
    collections = await db.list_collection_names()
    if "stock_financial_data" not in collections:
        logger.error("❌ stock_financial_data 集合不存在！")
        logger.info("\n💡 解决方案：")
        logger.info("   1. 运行财务数据同步：python scripts/sync_financial_data.py")
        logger.info("   2. 或启用定时任务：TUSHARE_FINANCIAL_SYNC_ENABLED=true")
        return False

    logger.info("✅ stock_financial_data 集合存在")

    # 2. 检查数据总量
    total_count = await db.stock_financial_data.count_documents({})
    logger.info(f"📊 财务数据总量: {total_count} 条")

    if total_count == 0:
        logger.warning("⚠️ stock_financial_data 集合为空！")
        logger.info("\n💡 解决方案：")
        logger.info("   需要同步财务数据，运行：")
        logger.info("   python -m app.worker.tushare_sync_service sync_financial")
        return False

    # 3. 检查示例股票的财务数据
    test_symbols = ["601288", "000001", "600000"]

    for symbol in test_symbols:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"检查股票: {symbol}")
        logger.info(f"{'=' * 60}")

        # 查询最新财务数据
        financial_doc = await db.stock_financial_data.find_one(
            {"symbol": symbol}, {"_id": 0}, sort=[("report_period", -1)],
        )

        if not financial_doc:
            logger.warning(f"⚠️ {symbol} 没有财务数据")
            continue

        logger.info(f"✅ 找到 {symbol} 的财务数据")
        logger.info(f"   报告期: {financial_doc.get('report_period', 'N/A')}")
        logger.info(f"   数据源: {financial_doc.get('data_source', 'N/A')}")

        # 检查数据结构
        logger.info("\n📋 数据结构:")
        logger.info(f"   顶层字段: {list(financial_doc.keys())}")

        # 检查 financial_indicators
        if "financial_indicators" in financial_doc:
            indicators = financial_doc["financial_indicators"]
            logger.info("\n📊 financial_indicators 字段:")
            logger.info(f"   ROE: {indicators.get('roe', 'N/A')}")
            logger.info(f"   负债率 (debt_to_assets): {indicators.get('debt_to_assets', 'N/A')}")
            logger.info(f"   所有指标: {list(indicators.keys())[:10]}...")  # 显示前10个
        else:
            logger.warning("   ⚠️ 没有 financial_indicators 字段")

        # 检查顶层字段
        logger.info("\n📊 顶层财务字段:")
        logger.info(f"   ROE: {financial_doc.get('roe', 'N/A')}")
        logger.info(f"   负债率 (debt_to_assets): {financial_doc.get('debt_to_assets', 'N/A')}")

    # 4. 统计有 ROE 数据的股票数量
    logger.info(f"\n{'=' * 80}")
    logger.info("统计数据完整性")
    logger.info(f"{'=' * 80}")

    # 统计有 financial_indicators.roe 的数量
    roe_in_indicators = await db.stock_financial_data.count_documents(
        {"financial_indicators.roe": {"$exists": True, "$ne": None}},
    )
    logger.info(f"📊 有 ROE 数据的股票: {roe_in_indicators} / {total_count}")

    # 统计有 financial_indicators.debt_to_assets 的数量
    debt_in_indicators = await db.stock_financial_data.count_documents(
        {"financial_indicators.debt_to_assets": {"$exists": True, "$ne": None}},
    )
    logger.info(f"📊 有负债率数据的股票: {debt_in_indicators} / {total_count}")

    # 5. 检查 stock_basic_info 中的 ROE
    logger.info(f"\n{'=' * 80}")
    logger.info("检查 stock_basic_info 集合中的 ROE")
    logger.info(f"{'=' * 80}")

    basic_total = await db.stock_basic_info.count_documents({})
    logger.info(f"📊 stock_basic_info 总量: {basic_total} 条")

    roe_in_basic = await db.stock_basic_info.count_documents({"roe": {"$exists": True, "$ne": None}})
    logger.info(f"📊 有 ROE 数据的股票: {roe_in_basic} / {basic_total}")

    # 6. 测试 API 接口逻辑
    logger.info(f"\n{'=' * 80}")
    logger.info("模拟 API 接口逻辑")
    logger.info(f"{'=' * 80}")

    test_code = "601288"
    logger.info(f"测试股票: {test_code}")

    # 模拟 /api/stocks/{code}/fundamentals 接口逻辑
    code6 = test_code.zfill(6)

    # 1. 获取基础信息
    b = await db.stock_basic_info.find_one({"code": code6}, {"_id": 0})
    if not b:
        logger.error(f"❌ 未找到 {test_code} 的基础信息")
        return False

    logger.info(f"✅ 找到基础信息: {b.get('name', 'N/A')}")

    # 2. 获取财务数据
    financial_data = await db.stock_financial_data.find_one({"symbol": code6}, {"_id": 0}, sort=[("report_period", -1)])

    if financial_data:
        logger.info(f"✅ 找到财务数据，报告期: {financial_data.get('report_period', 'N/A')}")
    else:
        logger.warning("⚠️ 未找到财务数据")

    # 3. 构建返回数据
    data = {"roe": None, "debt_ratio": None}

    # 4. 从财务数据中提取
    if financial_data:
        if financial_data.get("financial_indicators"):
            indicators = financial_data["financial_indicators"]
            data["roe"] = indicators.get("roe")
            data["debt_ratio"] = indicators.get("debt_to_assets")

        if data["roe"] is None:
            data["roe"] = financial_data.get("roe")
        if data["debt_ratio"] is None:
            data["debt_ratio"] = financial_data.get("debt_to_assets")

    # 5. 降级到 stock_basic_info
    if data["roe"] is None:
        data["roe"] = b.get("roe")

    logger.info("\n📊 最终返回数据:")
    logger.info(f"   ROE: {data['roe']}")
    logger.info(f"   负债率: {data['debt_ratio']}")

    if data["roe"] is None and data["debt_ratio"] is None:
        logger.error(f"\n❌ 问题确认：{test_code} 的 ROE 和负债率都为空！")
        logger.info("\n💡 解决方案：")
        logger.info("   1. 同步财务数据：")
        logger.info("      python -m app.worker.tushare_sync_service sync_financial")
        logger.info("   2. 或启用定时任务：")
        logger.info("      TUSHARE_FINANCIAL_SYNC_ENABLED=true")
        logger.info("   3. 检查 Tushare 权限是否支持财务数据接口")
        return False
    logger.info("\n✅ 数据正常！")
    return True


async def main():
    """主函数"""
    try:
        result = await check_financial_data()

        if result:
            logger.info("\n" + "=" * 80)
            logger.info("✅ 检查完成：数据正常")
            logger.info("=" * 80)
        else:
            logger.info("\n" + "=" * 80)
            logger.info("⚠️ 检查完成：发现问题，请按照上述解决方案处理")
            logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"❌ 检查失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    asyncio.run(main())
