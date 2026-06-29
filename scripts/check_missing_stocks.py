#!/usr/bin/env python3
"""
检查缺失的股票数据

功能：
1. 对比 AKShare 股票列表和数据库中的股票
2. 找出缺失的股票
3. 尝试获取缺失股票的详细信息，分析失败原因

使用方法：
    python scripts/check_missing_stocks.py
    python scripts/check_missing_stocks.py --test-fetch  # 测试获取缺失股票的信息
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import logging

from motor.motor_asyncio import AsyncIOMotorClient
from tradingagents.dataflows.providers.china.akshare import AKShareProvider

from app.core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def get_akshare_stock_codes() -> set[str]:
    """获取 AKShare 的所有股票代码"""
    logger.info("📋 获取 AKShare 股票列表...")

    provider = AKShareProvider()
    await provider.connect()

    stock_list = await provider.get_stock_list()
    codes = {stock["code"] for stock in stock_list}

    logger.info(f"✅ AKShare 股票列表: {len(codes)} 只")
    return codes


async def get_db_stock_codes() -> set[str]:
    """获取数据库中的所有股票代码"""
    logger.info("🗄️  获取数据库股票列表...")

    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db["stock_basic_info"]

    cursor = collection.find({}, {"code": 1, "symbol": 1, "_id": 0})
    docs = await cursor.to_list(length=None)

    codes = set()
    for doc in docs:
        code = doc.get("code") or doc.get("symbol")
        if code:
            codes.add(code)

    client.close()

    logger.info(f"✅ 数据库股票列表: {len(codes)} 只")
    return codes


async def test_fetch_missing_stocks(missing_codes: list[str], limit: int = 10):
    """测试获取缺失股票的信息"""
    logger.info(f"\n🔍 测试获取前 {limit} 只缺失股票的信息...")

    provider = AKShareProvider()
    await provider.connect()

    success_count = 0
    failed_count = 0

    for i, code in enumerate(missing_codes[:limit], 1):
        try:
            logger.info(f"   [{i}/{limit}] 获取 {code} 的信息...")
            basic_info = await provider.get_stock_basic_info(code)

            if basic_info:
                logger.info(
                    f"      ✅ 成功: {basic_info.get('name', 'N/A')}, "
                    f"行业={basic_info.get('industry', 'N/A')}, "
                    f"地区={basic_info.get('area', 'N/A')}",
                )
                success_count += 1
            else:
                logger.warning("      ❌ 失败: 返回 None")
                failed_count += 1

            # 延迟，避免API限流
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"      ❌ 异常: {e}")
            failed_count += 1

    logger.info(f"\n📊 测试结果: 成功 {success_count}/{limit}, 失败 {failed_count}/{limit}")


async def main(test_fetch: bool = False):
    """主函数"""
    logger.info("=" * 80)
    logger.info("🔍 检查缺失的股票数据")
    logger.info("=" * 80)

    # 1. 获取 AKShare 和数据库的股票代码
    akshare_codes = await get_akshare_stock_codes()
    db_codes = await get_db_stock_codes()

    # 2. 找出缺失的股票
    missing_codes = akshare_codes - db_codes
    extra_codes = db_codes - akshare_codes

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 对比结果")
    logger.info("=" * 80)
    logger.info(f"   AKShare 股票总数: {len(akshare_codes)}")
    logger.info(f"   数据库股票总数: {len(db_codes)}")
    logger.info(f"   缺失股票数量: {len(missing_codes)} (AKShare有但数据库没有)")
    logger.info(f"   多余股票数量: {len(extra_codes)} (数据库有但AKShare没有)")
    logger.info("=" * 80)

    # 3. 显示缺失的股票
    if missing_codes:
        logger.info("\n❌ 缺失的股票 (前50只):")
        for i, code in enumerate(sorted(missing_codes)[:50], 1):
            logger.info(f"   {i}. {code}")

        if len(missing_codes) > 50:
            logger.info(f"   ... 还有 {len(missing_codes) - 50} 只未显示")

        # 保存到文件
        output_file = project_root / "missing_stocks.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            for code in sorted(missing_codes):
                f.write(f"{code}\n")
        logger.info(f"\n💾 完整列表已保存到: {output_file}")

    # 4. 显示多余的股票
    if extra_codes:
        logger.info("\n⚠️  多余的股票 (前20只):")
        for i, code in enumerate(sorted(extra_codes)[:20], 1):
            logger.info(f"   {i}. {code}")

        if len(extra_codes) > 20:
            logger.info(f"   ... 还有 {len(extra_codes) - 20} 只未显示")

    # 5. 测试获取缺失股票的信息
    if test_fetch and missing_codes:
        await test_fetch_missing_stocks(sorted(missing_codes), limit=10)

    logger.info("")
    logger.info("✅ 检查完成！")

    if missing_codes:
        logger.info("\n💡 建议:")
        logger.info("   1. 运行 'python scripts/akshare_force_sync_all.py' 强制全量同步")
        logger.info("   2. 或运行 'python scripts/sync_missing_stocks.py' 只同步缺失的股票")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="检查缺失的股票数据", formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--test-fetch", action="store_true", help="测试获取缺失股票的信息")

    args = parser.parse_args()

    asyncio.run(main(test_fetch=args.test_fetch))
