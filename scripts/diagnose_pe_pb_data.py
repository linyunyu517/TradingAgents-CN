#!/usr/bin/env python3
"""
诊断 PE/PB 数据问题

功能：
1. 检查 stock_basic_info 集合的财务字段
2. 检查 stock_financial_data 集合的数据
3. 检查 market_quotes 集合的实时价格
4. 测试 PE/PB 计算逻辑

使用方法：
    python scripts/diagnose_pe_pb_data.py 600036
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def diagnose_stock(code: str):
    """诊断单只股票的 PE/PB 数据"""
    logger.info("=" * 80)
    logger.info(f"🔍 诊断股票 {code} 的 PE/PB 数据")
    logger.info("=" * 80)

    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    code6 = str(code).zfill(6)

    try:
        # 1. 检查 stock_basic_info 集合
        logger.info("\n📋 1. 检查 stock_basic_info 集合")
        logger.info("-" * 80)

        basic_info = await db.stock_basic_info.find_one({"$or": [{"code": code6}, {"symbol": code6}]})

        if not basic_info:
            logger.error(f"❌ 未找到股票 {code6} 的基础信息")
        else:
            logger.info("✅ 找到股票基础信息")
            logger.info(f"   股票代码: {basic_info.get('code', 'N/A')}")
            logger.info(f"   股票名称: {basic_info.get('name', 'N/A')}")
            logger.info(f"   行业: {basic_info.get('industry', 'N/A')}")
            logger.info(f"   地区: {basic_info.get('area', 'N/A')}")

            # 检查财务字段
            logger.info("\n   财务字段:")
            logger.info(f"   - PE: {basic_info.get('pe', 'N/A')}")
            logger.info(f"   - PB: {basic_info.get('pb', 'N/A')}")
            logger.info(f"   - PE_TTM: {basic_info.get('pe_ttm', 'N/A')}")
            logger.info(f"   - PB_MRQ: {basic_info.get('pb_mrq', 'N/A')}")
            logger.info(f"   - 总股本 (total_share): {basic_info.get('total_share', 'N/A')}")
            logger.info(f"   - 净利润 (net_profit): {basic_info.get('net_profit', 'N/A')}")
            logger.info(
                f"   - 净资产 (total_hldr_eqy_exc_min_int): {basic_info.get('total_hldr_eqy_exc_min_int', 'N/A')}",
            )
            logger.info(f"   - 市值 (money_cap): {basic_info.get('money_cap', 'N/A')}")

        # 2. 检查 stock_financial_data 集合
        logger.info("\n📊 2. 检查 stock_financial_data 集合")
        logger.info("-" * 80)

        financial_data = await db.stock_financial_data.find_one(
            {"$or": [{"symbol": code6}, {"code": code6}]}, sort=[("report_period", -1)],
        )

        if not financial_data:
            logger.warning(f"⚠️  未找到股票 {code6} 的财务数据")
        else:
            logger.info("✅ 找到财务数据")
            logger.info(f"   报告期: {financial_data.get('report_period', 'N/A')}")
            logger.info(f"   数据来源: {financial_data.get('data_source', 'N/A')}")

            # 检查关键财务指标
            logger.info("\n   关键财务指标:")
            logger.info(f"   - ROE: {financial_data.get('roe', 'N/A')}")
            logger.info(f"   - ROA: {financial_data.get('roa', 'N/A')}")
            logger.info(f"   - 毛利率: {financial_data.get('gross_margin', 'N/A')}")
            logger.info(f"   - 净利率: {financial_data.get('netprofit_margin', 'N/A')}")
            logger.info(f"   - 资产负债率: {financial_data.get('debt_to_assets', 'N/A')}")
            logger.info(f"   - 营业收入: {financial_data.get('revenue', 'N/A')}")
            logger.info(f"   - 净利润: {financial_data.get('net_profit', 'N/A')}")
            logger.info(f"   - 总资产: {financial_data.get('total_assets', 'N/A')}")
            logger.info(f"   - 净资产: {financial_data.get('total_hldr_eqy_exc_min_int', 'N/A')}")

        # 3. 检查 market_quotes 集合（实时价格）
        logger.info("\n💹 3. 检查 market_quotes 集合（实时价格）")
        logger.info("-" * 80)

        quote = await db.market_quotes.find_one({"$or": [{"code": code6}, {"symbol": code6}]})

        if not quote:
            logger.warning(f"⚠️  未找到股票 {code6} 的实时行情")
        else:
            logger.info("✅ 找到实时行情")
            logger.info(f"   最新价: {quote.get('close', 'N/A')}")
            logger.info(f"   涨跌幅: {quote.get('pct_chg', 'N/A')}%")
            logger.info(f"   成交量: {quote.get('volume', 'N/A')}")
            logger.info(f"   更新时间: {quote.get('updated_at', 'N/A')}")

        # 4. 测试 PE/PB 计算
        logger.info("\n🧮 4. 测试 PE/PB 计算")
        logger.info("-" * 80)

        if basic_info and quote:
            price = quote.get("close")
            total_share = basic_info.get("total_share")
            net_profit = basic_info.get("net_profit")
            total_equity = basic_info.get("total_hldr_eqy_exc_min_int")

            logger.info("   计算参数:")
            logger.info(f"   - 股价: {price}")
            logger.info(f"   - 总股本: {total_share} 万股")
            logger.info(f"   - 净利润: {net_profit} 万元")
            logger.info(f"   - 净资产: {total_equity} 万元")

            if price and total_share:
                market_cap = price * total_share
                logger.info("\n   计算结果:")
                logger.info(f"   - 市值: {market_cap:.2f} 万元")

                if net_profit and net_profit > 0:
                    pe = market_cap / net_profit
                    logger.info(f"   - PE = 市值 / 净利润 = {market_cap:.2f} / {net_profit:.2f} = {pe:.2f}")
                else:
                    logger.warning("   - PE: 无法计算（净利润为空或为负）")

                if total_equity and total_equity > 0:
                    pb = market_cap / total_equity
                    logger.info(f"   - PB = 市值 / 净资产 = {market_cap:.2f} / {total_equity:.2f} = {pb:.2f}")
                else:
                    logger.warning("   - PB: 无法计算（净资产为空或为负）")
            else:
                logger.error("   ❌ 无法计算（缺少股价或总股本）")
        else:
            logger.error("   ❌ 无法计算（缺少基础信息或实时行情）")

        # 5. 测试实时 PE/PB 计算函数
        logger.info("\n🔧 5. 测试实时 PE/PB 计算函数")
        logger.info("-" * 80)

        try:
            from tradingagents.dataflows.realtime_metrics import get_pe_pb_with_fallback

            realtime_metrics = get_pe_pb_with_fallback(code6, client)

            if realtime_metrics:
                logger.info("✅ 实时 PE/PB 计算成功")
                logger.info(f"   - PE: {realtime_metrics.get('pe', 'N/A')}")
                logger.info(f"   - PB: {realtime_metrics.get('pb', 'N/A')}")
                logger.info(f"   - PE_TTM: {realtime_metrics.get('pe_ttm', 'N/A')}")
                logger.info(f"   - PB_MRQ: {realtime_metrics.get('pb_mrq', 'N/A')}")
                logger.info(f"   - 数据来源: {realtime_metrics.get('source', 'N/A')}")
                logger.info(f"   - 是否实时: {realtime_metrics.get('is_realtime', False)}")
                logger.info(f"   - 更新时间: {realtime_metrics.get('updated_at', 'N/A')}")
            else:
                logger.error("❌ 实时 PE/PB 计算失败（返回空）")
        except Exception as e:
            logger.error(f"❌ 实时 PE/PB 计算异常: {e}")
            import traceback

            logger.error(traceback.format_exc())

        # 6. 诊断结论
        logger.info("\n📋 6. 诊断结论")
        logger.info("=" * 80)

        issues = []

        if not basic_info:
            issues.append("❌ stock_basic_info 集合缺少该股票数据")
        else:
            if not basic_info.get("total_share"):
                issues.append("❌ stock_basic_info 缺少 total_share 字段")
            if not basic_info.get("net_profit"):
                issues.append("⚠️  stock_basic_info 缺少 net_profit 字段（PE 无法计算）")
            if not basic_info.get("total_hldr_eqy_exc_min_int"):
                issues.append("⚠️  stock_basic_info 缺少 total_hldr_eqy_exc_min_int 字段（PB 无法计算）")

        if not financial_data:
            issues.append("⚠️  stock_financial_data 集合缺少该股票数据（可选）")

        if not quote:
            issues.append("❌ market_quotes 集合缺少该股票数据（实时价格）")

        if issues:
            logger.info("\n发现以下问题:")
            for issue in issues:
                logger.info(f"   {issue}")

            logger.info("\n💡 建议:")
            if not basic_info or not basic_info.get("total_share"):
                logger.info(f"   1. 运行 'python scripts/sync_financial_data.py {code6}' 同步财务数据")
            if not quote:
                logger.info("   2. 确保实时行情同步服务正在运行")
            if not financial_data:
                logger.info(f"   3. 运行 'python scripts/sync_financial_data.py {code6}' 同步详细财务数据")
        else:
            logger.info("✅ 所有数据完整，PE/PB 应该可以正常计算")

    finally:
        client.close()

    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ 诊断完成")
    logger.info("=" * 80)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="诊断 PE/PB 数据问题", formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("code", type=str, help="股票代码（6位）")

    args = parser.parse_args()

    asyncio.run(diagnose_stock(args.code))


if __name__ == "__main__":
    main()
