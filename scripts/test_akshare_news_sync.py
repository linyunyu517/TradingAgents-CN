#!/usr/bin/env python3
"""
测试AKShare新闻数据同步功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import close_database, get_mongo_db, init_database
from app.worker.akshare_sync_service import get_akshare_sync_service


async def test_akshare_news_sync():
    """测试AKShare新闻数据同步"""
    print("=" * 60)
    print("🧪 测试AKShare新闻数据同步功能")
    print("=" * 60)
    print()

    try:
        # 1. 初始化数据库
        print("🔄 初始化数据库连接...")
        await init_database()
        print("✅ 数据库连接成功")
        print()

        # 2. 获取同步服务
        print("🔄 初始化同步服务...")
        sync_service = await get_akshare_sync_service()
        print("✅ 同步服务初始化完成")
        print()

        # 3. 检查新闻数据库状态
        db = get_mongo_db()
        news_count_before = await db.stock_news.count_documents({"data_source": "akshare"})
        print(f"📊 同步前AKShare新闻数量: {news_count_before:,}条")
        print()

        # 4. 测试同步少量股票的新闻（测试用）
        test_symbols = ["000001", "600000", "000002"]  # 测试3只股票
        print(f"🚀 开始同步测试股票新闻: {', '.join(test_symbols)}")
        print("   每只股票最大新闻数: 20条")
        print()

        result = await sync_service.sync_news_data(symbols=test_symbols, max_news_per_stock=20)

        # 5. 显示结果
        print()
        print("=" * 60)
        print("📊 同步结果统计")
        print("=" * 60)
        print(f"  总处理股票数: {result['total_processed']}")
        print(f"  成功数量: {result['success_count']}")
        print(f"  错误数量: {result['error_count']}")
        print(f"  获取新闻数: {result['news_count']}")
        print(f"  耗时: {result.get('duration', 0):.2f}秒")

        if result["errors"]:
            print("\n⚠️ 错误列表:")
            for error in result["errors"][:5]:  # 只显示前5个错误
                print(f"  - {error}")

        # 6. 检查新闻数据库状态
        news_count_after = await db.stock_news.count_documents({"data_source": "akshare"})
        print(f"\n📊 同步后AKShare新闻数量: {news_count_after:,}条")
        print(f"   新增: {news_count_after - news_count_before:,}条")

        # 7. 查看最新的几条新闻
        if news_count_after > 0:
            print("\n📰 最新新闻示例:")
            latest_news = (
                await db.stock_news.find({"data_source": "akshare"}).sort("publish_time", -1).limit(3).to_list(3)
            )

            for i, news in enumerate(latest_news, 1):
                print(f"\n  {i}. {news.get('title', 'N/A')}")
                print(f"     股票: {news.get('symbol', 'N/A')}")
                print(f"     来源: {news.get('source', 'N/A')}")
                print(f"     时间: {news.get('publish_time', 'N/A')}")
                if news.get("url"):
                    print(f"     链接: {news.get('url')[:60]}...")

        print("\n✅ 测试完成")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # 关闭数据库连接
        try:
            await close_database()
        except Exception as e:
            print(f"关闭数据库连接失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_akshare_news_sync())
