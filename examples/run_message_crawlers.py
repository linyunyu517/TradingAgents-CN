#!/usr/bin/env python3
"""
消息数据爬虫运行示例
演示如何使用社媒消息和内部消息爬虫
"""

import asyncio
import logging
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_social_media_crawler_example():
    """运行社媒消息爬虫示例"""
    logger.info("🕷️ 社媒消息爬虫示例")

    try:
        from examples.crawlers.social_media_crawler import crawl_and_save_social_media

        # 测试股票列表
        symbols = ["000001", "000002"]
        platforms = ["weibo", "douyin"]

        logger.info(f"开始爬取社媒消息: {symbols}")
        saved_count = await crawl_and_save_social_media(symbols, platforms)

        logger.info(f"✅ 社媒消息爬取完成: {saved_count} 条")
        return saved_count

    except Exception as e:
        logger.error(f"❌ 社媒消息爬虫示例失败: {e}")
        return 0


async def run_internal_message_crawler_example():
    """运行内部消息爬虫示例"""
    logger.info("📊 内部消息爬虫示例")

    try:
        from examples.crawlers.internal_message_crawler import crawl_and_save_internal_messages

        # 测试股票列表
        symbols = ["000001", "000002"]
        message_types = ["research_report", "analyst_note"]

        logger.info(f"开始爬取内部消息: {symbols}")
        saved_count = await crawl_and_save_internal_messages(symbols, message_types)

        logger.info(f"✅ 内部消息爬取完成: {saved_count} 条")
        return saved_count

    except Exception as e:
        logger.error(f"❌ 内部消息爬虫示例失败: {e}")
        return 0


async def run_scheduler_example():
    """运行调度器示例"""
    logger.info("🤖 爬虫调度器示例")

    try:
        from examples.crawlers.message_crawler_scheduler import MessageCrawlerScheduler

        # 创建调度器
        scheduler = MessageCrawlerScheduler()

        # 运行完整爬取
        result = await scheduler.run_full_crawl()

        logger.info(f"✅ 调度器运行完成: {result['total_saved']} 条消息")
        return result["total_saved"]

    except Exception as e:
        logger.error(f"❌ 调度器示例失败: {e}")
        return 0


async def query_saved_messages():
    """查询已保存的消息"""
    logger.info("🔍 查询已保存的消息")

    try:
        from app.core.database import init_db
        from app.services.internal_message_service import get_internal_message_service
        from app.services.social_media_service import get_social_media_service

        # 初始化数据库
        await init_db()

        # 获取服务
        social_service = await get_social_media_service()
        internal_service = await get_internal_message_service()

        # 获取统计信息
        social_stats = await social_service.get_social_media_statistics()
        internal_stats = await internal_service.get_internal_statistics()

        logger.info("📊 数据库统计:")
        logger.info(f"   - 社媒消息总数: {social_stats.total_count}")
        logger.info(f"   - 内部消息总数: {internal_stats.total_count}")
        logger.info(f"   - 消息总数: {social_stats.total_count + internal_stats.total_count}")

        # 查询示例消息
        from app.services.internal_message_service import InternalMessageQueryParams
        from app.services.social_media_service import SocialMediaQueryParams

        # 查询000001的社媒消息
        social_messages = await social_service.query_social_media_messages(
            SocialMediaQueryParams(symbol="000001", limit=5),
        )

        # 查询000001的内部消息
        internal_messages = await internal_service.query_internal_messages(
            InternalMessageQueryParams(symbol="000001", limit=5),
        )

        logger.info("📝 000001 消息示例:")
        logger.info(f"   - 社媒消息: {len(social_messages)} 条")
        logger.info(f"   - 内部消息: {len(internal_messages)} 条")

        if social_messages:
            logger.info(f"   - 最新社媒消息: {social_messages[0]['content'][:50]}...")

        if internal_messages:
            logger.info(f"   - 最新内部消息: {internal_messages[0]['title']}")

        return True

    except Exception as e:
        logger.error(f"❌ 查询消息失败: {e}")
        return False


async def main():
    """主函数 - 演示所有爬虫功能"""
    logger.info("🚀 消息数据爬虫系统演示")

    print("\n" + "=" * 60)
    print("📋 可用的演示选项:")
    print("1. 社媒消息爬虫示例")
    print("2. 内部消息爬虫示例")
    print("3. 统一调度器示例")
    print("4. 查询已保存消息")
    print("5. 运行所有示例")
    print("=" * 60)

    choice = input("\n请选择要运行的示例 (1-5): ").strip()

    total_saved = 0

    if choice == "1":
        total_saved = await run_social_media_crawler_example()
    elif choice == "2":
        total_saved = await run_internal_message_crawler_example()
    elif choice == "3":
        total_saved = await run_scheduler_example()
    elif choice == "4":
        await query_saved_messages()
    elif choice == "5":
        logger.info("🎯 运行所有示例")

        # 运行社媒爬虫
        social_saved = await run_social_media_crawler_example()
        await asyncio.sleep(2)

        # 运行内部消息爬虫
        internal_saved = await run_internal_message_crawler_example()
        await asyncio.sleep(2)

        # 查询消息
        await query_saved_messages()

        total_saved = social_saved + internal_saved
    else:
        logger.warning("❓ 无效选择，退出程序")
        return

    # 最终统计
    if total_saved > 0:
        logger.info(f"\n🎉 演示完成! 总计处理: {total_saved} 条消息")
    else:
        logger.info("\n✅ 演示完成!")

    logger.info("💡 提示: 您可以查看以下文件了解更多:")
    logger.info("   - examples/crawlers/social_media_crawler.py")
    logger.info("   - examples/crawlers/internal_message_crawler.py")
    logger.info("   - examples/crawlers/message_crawler_scheduler.py")
    logger.info("   - docs/guides/message_data_system/README.md")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 用户中断，程序退出")
    except Exception as e:
        logger.error(f"\n💥 程序异常: {e}")
        sys.exit(1)
