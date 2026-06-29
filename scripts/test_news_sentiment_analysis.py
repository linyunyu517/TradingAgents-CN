#!/usr/bin/env python3
"""
测试新闻情绪分析和关键词提取功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.providers.akshare_provider import get_akshare_provider

from app.core.database import close_database


async def test_sentiment_analysis():
    """测试情绪分析功能"""
    print("=" * 60)
    print("🧪 测试AKShare新闻情绪分析和关键词提取")
    print("=" * 60)
    print()

    try:
        # 1. 获取 AKShare Provider
        provider = get_akshare_provider()
        print("✅ AKShare Provider 初始化成功")
        print()

        # 2. 获取测试股票的新闻
        test_symbol = "000001"
        print(f"🔍 获取 {test_symbol} 的新闻数据...")
        print()

        news_data = await provider.get_stock_news(symbol=test_symbol, limit=5)

        # 3. 显示新闻数据及分析结果
        if news_data:
            print(f"✅ 获取到 {len(news_data)} 条新闻")
            print()

            for i, news in enumerate(news_data, 1):
                print("=" * 60)
                print(f"📰 新闻 {i}")
                print("=" * 60)
                print(f"标题: {news.get('title', 'N/A')}")
                print(f"来源: {news.get('source', 'N/A')}")
                print(f"时间: {news.get('publish_time', 'N/A')}")
                print()

                # 显示分析结果
                print("📊 分析结果:")
                print(f"  分类: {news.get('category', 'N/A')}")
                print(f"  情绪: {news.get('sentiment', 'N/A')}")
                print(f"  情绪分数: {news.get('sentiment_score', 0):.2f}")
                print(f"  重要性: {news.get('importance', 'N/A')}")
                print(f"  关键词: {', '.join(news.get('keywords', []))}")
                print()

                # 显示部分内容
                content = news.get("content", "")
                if content:
                    print(f"内容摘要: {content[:100]}...")
                print()
        else:
            print("⚠️ 未获取到新闻数据")

        print("✅ 测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # 关闭数据库连接（如果有初始化）
        try:
            await close_database()
        except Exception:
            pass  # 这个脚本不使用数据库，忽略错误


if __name__ == "__main__":
    asyncio.run(test_sentiment_analysis())
