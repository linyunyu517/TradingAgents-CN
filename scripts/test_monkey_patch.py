#!/usr/bin/env python3
"""
测试 monkey patch 是否在 Docker 环境中生效
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")

logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("🔧 测试 requests monkey patch")
    logger.info("=" * 60)

    # 1. 检查初始状态
    logger.info("\n【步骤1】检查 requests 初始状态")
    import requests

    logger.info(f"  requests._akshare_headers_patched: {hasattr(requests, '_akshare_headers_patched')}")
    logger.info(f"  requests.get 类型: {type(requests.get)}")

    # 2. 导入 AKShare 提供器
    logger.info("\n【步骤2】导入 AKShare 提供器")
    from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

    provider = get_akshare_provider()
    logger.info(f"  提供器连接状态: {provider.connected}")

    # 3. 再次检查 requests 状态
    logger.info("\n【步骤3】检查 requests 状态（初始化后）")
    logger.info(f"  requests._akshare_headers_patched: {hasattr(requests, '_akshare_headers_patched')}")
    logger.info(f"  requests.get 类型: {type(requests.get)}")
    logger.info(f"  requests.get 名称: {requests.get.__name__}")

    # 4. 测试一个简单的请求
    logger.info("\n【步骤4】测试 HTTP 请求")
    try:
        resp = requests.get("https://httpbin.org/headers", timeout=5)
        user_agent = resp.json().get("headers", {}).get("User-Agent", "N/A")
        logger.info("  ✅ 请求成功")
        logger.info(f"  User-Agent: {user_agent}")

        if "Mozilla" in user_agent:
            logger.info("  ✅ Monkey patch 生效！（使用了浏览器 User-Agent）")
        else:
            logger.warning("  ⚠️ Monkey patch 可能未生效（使用了默认 User-Agent）")
    except Exception as e:
        logger.error(f"  ❌ 请求失败: {e}")

    # 5. 测试 AKShare 新闻接口
    logger.info("\n【步骤5】测试 AKShare 新闻接口")
    try:
        news_list = await provider.get_stock_news(symbol="600089", limit=5)
        if news_list:
            logger.info(f"  ✅ 获取新闻成功: {len(news_list)} 条")
        else:
            logger.warning("  ⚠️ 未获取到新闻")
    except Exception as e:
        logger.error(f"  ❌ 获取新闻失败: {e}")
        import traceback

        traceback.print_exc()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
