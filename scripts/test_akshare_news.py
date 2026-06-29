"""
测试 AKShare 获取股票新闻数据
测试 000002 万科的最新新闻时间
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_akshare_news():
    """测试 AKShare 获取新闻数据"""
    print("=" * 70)
    print("🧪 测试 AKShare 获取股票新闻数据")
    print("=" * 70)

    test_symbol = "000002"  # 万科A

    try:
        # 1. 导入 AKShare Provider
        print("\n📦 步骤1: 导入 AKShare Provider...")
        from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

        provider = get_akshare_provider()
        print("✅ AKShare Provider 初始化成功")

        # 2. 连接 Provider
        print("\n🔌 步骤2: 连接 Provider...")
        await provider.connect()
        print("✅ Provider 连接成功")

        # 3. 检查可用性
        print("\n🔍 步骤3: 检查 Provider 可用性...")
        is_available = provider.is_available()
        print(f"✅ Provider 可用性: {is_available}")

        if not is_available:
            print("❌ AKShare Provider 不可用，测试终止")
            return

        # 4. 获取新闻数据
        print(f"\n📰 步骤4: 获取 {test_symbol} 的新闻数据...")
        print(f"   股票代码: {test_symbol}")
        print("   获取数量: 10条")

        news_data = await provider.get_stock_news(symbol=test_symbol, limit=10)

        if not news_data:
            print(f"❌ 未获取到 {test_symbol} 的新闻数据")
            return

        print(f"✅ 成功获取 {len(news_data)} 条新闻")

        # 5. 分析新闻数据
        print("\n" + "=" * 70)
        print("📊 新闻数据分析")
        print("=" * 70)

        for i, news in enumerate(news_data, 1):
            print(f"\n【新闻 {i}】")
            print(f"  标题: {news.get('title', 'N/A')}")
            print(f"  来源: {news.get('source', 'N/A')}")

            # 发布时间
            publish_time = news.get("publish_time")
            if publish_time:
                if isinstance(publish_time, str):
                    print(f"  发布时间: {publish_time}")
                elif isinstance(publish_time, datetime):
                    print(f"  发布时间: {publish_time.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"  发布时间: {publish_time} (类型: {type(publish_time).__name__})")
            else:
                print("  发布时间: N/A")

            # URL
            url = news.get("url", "N/A")
            if len(url) > 80:
                print(f"  链接: {url[:80]}...")
            else:
                print(f"  链接: {url}")

            # 内容摘要
            content = news.get("content", "")
            if content:
                content_preview = content[:100] + "..." if len(content) > 100 else content
                print(f"  内容: {content_preview}")

        # 6. 统计最新和最旧的新闻时间
        print("\n" + "=" * 70)
        print("📅 新闻时间统计")
        print("=" * 70)

        times = []
        for news in news_data:
            publish_time = news.get("publish_time")
            if publish_time:
                if isinstance(publish_time, str):
                    try:
                        # 尝试解析时间字符串
                        dt = datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                        times.append(dt)
                    except Exception:
                        try:
                            dt = datetime.strptime(publish_time, "%Y-%m-%d")
                            times.append(dt)
                        except Exception:
                            print(f"⚠️ 无法解析时间: {publish_time}")
                elif isinstance(publish_time, datetime):
                    times.append(publish_time)

        if times:
            latest_time = max(times)
            oldest_time = min(times)
            print(f"✅ 最新新闻时间: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"✅ 最旧新闻时间: {oldest_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 计算时间跨度
            time_span = latest_time - oldest_time
            print(f"✅ 时间跨度: {time_span.days} 天 {time_span.seconds // 3600} 小时")

            # 计算距离现在的时间
            now = datetime.now()
            time_diff = now - latest_time
            print(f"✅ 最新新闻距离现在: {time_diff.days} 天 {time_diff.seconds // 3600} 小时")
        else:
            print("⚠️ 没有找到有效的时间信息")

        # 7. 原始数据结构
        print("\n" + "=" * 70)
        print("🔍 第一条新闻的原始数据结构")
        print("=" * 70)
        if news_data:
            first_news = news_data[0]
            print(f"字段列表: {list(first_news.keys())}")
            print("\n详细数据:")
            for key, value in first_news.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {value[:100]}... (长度: {len(value)})")
                else:
                    print(f"  {key}: {value}")

        print("\n" + "=" * 70)
        print("✅ 测试完成")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_akshare_news())
