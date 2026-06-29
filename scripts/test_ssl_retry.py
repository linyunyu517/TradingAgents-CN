#!/usr/bin/env python3
"""
测试 SSL 重试机制
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")

logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 80)
    logger.info("🧪 测试 AKShare 新闻接口（带 SSL 重试机制）")
    logger.info("=" * 80)

    # 导入 AKShare 提供器
    logger.info("\n【步骤1】导入 AKShare 提供器")
    from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

    provider = get_akshare_provider()
    logger.info("  ✅ 提供器初始化完成")
    logger.info(f"  连接状态: {provider.connected}")

    # 测试连接
    logger.info("\n【步骤2】测试连接")
    connected = await provider.test_connection()
    logger.info(f"  连接状态: {'✅ 成功' if connected else '❌ 失败'}")

    # 测试获取新闻
    logger.info("\n【步骤3】测试获取新闻")
    test_symbols = ["600089", "000001", "002533"]

    success_count = 0
    fail_count = 0

    for symbol in test_symbols:
        logger.info(f"\n  测试股票: {symbol}")
        try:
            news_list = await provider.get_stock_news(symbol=symbol, limit=10)

            if news_list:
                logger.info(f"    ✅ 成功获取 {len(news_list)} 条新闻")
                success_count += 1

                # 显示第一条新闻
                first_news = news_list[0]
                logger.info(f"    标题: {first_news.get('title', 'N/A')[:60]}...")
                logger.info(f"    时间: {first_news.get('published_at', 'N/A')}")
            else:
                logger.warning("    ⚠️ 未获取到新闻")
                fail_count += 1

        except Exception as e:
            logger.error(f"    ❌ 获取失败: {e}")
            fail_count += 1

    # 统计结果
    logger.info("\n" + "=" * 80)
    logger.info("📊 测试结果统计")
    logger.info(f"  总计: {len(test_symbols)} 只股票")
    logger.info(f"  成功: {success_count} 只")
    logger.info(f"  失败: {fail_count} 只")
    logger.info(f"  成功率: {success_count / len(test_symbols) * 100:.1f}%")
    logger.info("=" * 80)

    return success_count > 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
