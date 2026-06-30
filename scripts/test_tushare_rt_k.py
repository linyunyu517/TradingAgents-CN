"""
测试 Tushare rt_k 接口
验证修复后的实时行情同步功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from tradingagents.dataflows.providers.china.tushare import TushareProvider

from app.worker.tushare_sync_service import TushareSyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


async def test_rt_k_interface():
    """测试 rt_k 接口"""
    logger.info("=" * 80)
    logger.info("测试 1: Tushare rt_k 接口")
    logger.info("=" * 80)

    provider = TushareProvider()

    # 连接
    logger.info("📡 连接 Tushare...")
    success = await provider.connect()
    if not success:
        logger.error("❌ Tushare 连接失败")
        return False

    logger.info("✅ Tushare 连接成功")

    # 测试批量获取
    logger.info("\n📊 测试批量获取全市场实时行情...")
    try:
        quotes_map = await provider.get_realtime_quotes_batch()

        if quotes_map:
            logger.info(f"✅ 成功获取 {len(quotes_map)} 只股票的实时行情")

            # 显示前5只股票
            logger.info("\n📈 前5只股票行情示例：")
            for i, (symbol, quote) in enumerate(list(quotes_map.items())[:5]):
                logger.info(f"  {i + 1}. {symbol} - {quote.get('name', 'N/A')}")
                logger.info(
                    f"     当前价: {quote.get('close', 'N/A')}, "
                    f"涨跌幅: {quote.get('pct_chg', 'N/A')}%, "
                    f"成交额: {quote.get('amount', 'N/A')}",
                )

            return True
        logger.warning("⚠️ 未获取到实时行情数据（可能不在交易时间）")
        return False

    except Exception as e:
        logger.error(f"❌ 批量获取实时行情失败: {e}")
        return False


async def test_single_stock():
    """测试单只股票获取"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 2: 单只股票实时行情")
    logger.info("=" * 80)

    provider = TushareProvider()
    await provider.connect()

    test_symbols = ["000001", "600000", "300001"]

    for symbol in test_symbols:
        logger.info(f"\n📊 获取 {symbol} 实时行情...")
        try:
            quote = await provider.get_stock_quotes(symbol)
            if quote:
                logger.info(f"✅ {symbol} - {quote.get('name', 'N/A')}")
                logger.info(f"   当前价: {quote.get('close', 'N/A')}, 涨跌幅: {quote.get('pct_chg', 'N/A')}%")
            else:
                logger.warning(f"⚠️ {symbol} 未获取到数据")
        except Exception as e:
            logger.error(f"❌ {symbol} 获取失败: {e}")


async def test_trading_time_check():
    """测试交易时间判断"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 3: 交易时间判断")
    logger.info("=" * 80)

    service = TushareSyncService()
    await service.initialize()

    is_trading = service._is_trading_time()
    logger.info(f"📅 当前是否在交易时间: {'✅ 是' if is_trading else '❌ 否'}")

    if not is_trading:
        logger.info("ℹ️ 不在交易时间，实时行情同步任务会自动跳过")


async def test_sync_service():
    """测试同步服务"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 4: 实时行情同步服务")
    logger.info("=" * 80)

    service = TushareSyncService()
    await service.initialize()

    logger.info("🔄 执行实时行情同步...")
    result = await service.sync_realtime_quotes()

    logger.info("\n📊 同步结果：")
    logger.info(f"  总处理: {result.get('total_processed', 0)} 只")
    logger.info(f"  成功: {result.get('success_count', 0)} 只")
    logger.info(f"  失败: {result.get('error_count', 0)} 只")
    logger.info(f"  耗时: {result.get('duration', 0):.2f} 秒")

    if result.get("skipped_non_trading_time"):
        logger.info("  ⏸️ 因非交易时间而跳过")

    if result.get("stopped_by_rate_limit"):
        logger.warning("  ⚠️ 因API限流而停止")

    if result.get("errors"):
        logger.warning(f"  ⚠️ 错误数量: {len(result['errors'])}")
        # 显示前3个错误
        for i, error in enumerate(result["errors"][:3]):
            logger.warning(f"    {i + 1}. {error.get('code', 'N/A')}: {error.get('error', 'N/A')}")


async def main():
    """主函数"""
    logger.info("🚀 开始测试 Tushare rt_k 接口修复")
    logger.info("=" * 80)

    try:
        # 测试1: rt_k 接口
        await test_rt_k_interface()

        # 测试2: 单只股票
        await test_single_stock()

        # 测试3: 交易时间判断
        await test_trading_time_check()

        # 测试4: 同步服务
        await test_sync_service()

        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有测试完成")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False

    return True


if __name__ == "__main__":
    asyncio.run(main())
