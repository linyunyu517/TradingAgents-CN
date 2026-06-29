#!/usr/bin/env python
"""
测试新闻数据统一功能

验证DataSourceManager是否正确支持新闻数据获取
"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置环境变量
os.environ["TA_USE_APP_CACHE"] = "true"


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"🎯 {title}")
    print("=" * 70 + "\n")


def test_data_source_priority():
    """测试数据源优先级"""
    print_section("测试新闻数据统一功能")

    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    manager = get_data_source_manager()

    print("📰 新闻数据支持:")
    print("   1. ✅ MongoDB - 从数据库缓存获取新闻")
    print("   2. ✅ Tushare - 从Tushare API获取新闻")
    print("   3. ✅ AKShare - 从AKShare API获取新闻")
    print()
    print("📝 数据获取流程:")
    print("   1. 首先尝试从 MongoDB 获取新闻数据")
    print("   2. 如果 MongoDB 没有数据，自动降级到 Tushare")
    print("   3. 如果 Tushare 失败，自动降级到 AKShare")
    print()
    print("🔍 当前数据源: " + manager.current_source.value)
    print("🔍 MongoDB缓存启用: " + str(manager.use_mongodb_cache))


def test_stock_news():
    """测试个股新闻获取"""
    print_section("测试个股新闻获取")

    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    manager = get_data_source_manager()

    test_symbol = "000001"
    hours_back = 24
    limit = 10

    print(f"📊 测试股票: {test_symbol}")
    print(f"⏰ 回溯时间: {hours_back}小时")
    print(f"📊 数量限制: {limit}条")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print()

    print("-" * 70)
    news_data = manager.get_news_data(symbol=test_symbol, hours_back=hours_back, limit=limit)
    print()

    print("-" * 70)
    print("📰 个股新闻获取结果")
    print("-" * 70)
    if news_data and len(news_data) > 0:
        print("✅ 新闻获取成功")
        print(f"📊 新闻数量: {len(news_data)}条")
        print()
        print("📫 新闻预览（前3条）:")
        for i, news in enumerate(news_data[:3], 1):
            print(f"\n{i}. {news.get('title', '无标题')}")
            print(f"   来源: {news.get('source', '未知')}")
            print(f"   时间: {news.get('publish_time', '未知')}")
            if "sentiment" in news:
                print(f"   情绪: {news.get('sentiment', '未知')}")
            if "url" in news:
                print(f"   链接: {news.get('url', '')[:50]}...")
    else:
        print("❌ 新闻获取失败或无数据")


def test_market_news():
    """测试市场新闻获取"""
    print_section("测试市场新闻获取")

    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    manager = get_data_source_manager()

    hours_back = 6
    limit = 5

    print("📊 测试类型: 市场新闻（不指定股票代码）")
    print(f"⏰ 回溯时间: {hours_back}小时")
    print(f"📊 数量限制: {limit}条")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print()

    print("-" * 70)
    news_data = manager.get_news_data(symbol=None, hours_back=hours_back, limit=limit)
    print()

    print("-" * 70)
    print("📰 市场新闻获取结果")
    print("-" * 70)
    if news_data and len(news_data) > 0:
        print("✅ 新闻获取成功")
        print(f"📊 新闻数量: {len(news_data)}条")
        print()
        print("📫 新闻预览（前3条）:")
        for i, news in enumerate(news_data[:3], 1):
            print(f"\n{i}. {news.get('title', '无标题')}")
            print(f"   来源: {news.get('source', '未知')}")
            print(f"   时间: {news.get('publish_time', '未知')}")
            if "sentiment" in news:
                print(f"   情绪: {news.get('sentiment', '未知')}")
    else:
        print("⚠️ 市场新闻获取失败或无数据")


def test_fallback_mechanism():
    """测试新闻数据降级机制"""
    print_section("测试新闻数据降级机制")

    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    manager = get_data_source_manager()

    # 测试一个可能在 MongoDB 中不存在的股票
    test_symbol = "688999"
    hours_back = 24
    limit = 5

    print(f"📊 测试股票: {test_symbol}")
    print(f"⏰ 回溯时间: {hours_back}小时")
    print(f"📊 数量限制: {limit}条")
    print("📝 预期行为: MongoDB 无数据 → 自动降级到 Tushare/AKShare")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print()

    print("-" * 70)
    news_data = manager.get_news_data(symbol=test_symbol, hours_back=hours_back, limit=limit)
    print()

    print("-" * 70)
    print("📰 降级测试结果")
    print("-" * 70)
    if news_data and len(news_data) > 0:
        print("✅ 降级成功，从备用数据源获取到新闻")
        print(f"📊 新闻数量: {len(news_data)}条")
        print()
        print("📫 新闻预览（第1条）:")
        news = news_data[0]
        print(f"   标题: {news.get('title', '无标题')}")
        print(f"   来源: {news.get('source', '未知')}")
        print(f"   时间: {news.get('publish_time', '未知')}")
    else:
        print("⚠️ 所有数据源都无法获取该股票的新闻")


def test_different_time_ranges():
    """测试不同时间范围的新闻获取"""
    print_section("测试不同时间范围的新闻获取")

    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    manager = get_data_source_manager()

    test_symbol = "000001"
    time_ranges = [6, 24, 72]

    print(f"📊 测试股票: {test_symbol}")
    print(f"🔍 当前数据源: {manager.current_source.value}")
    print()

    for hours in time_ranges:
        print(f"⏰ 测试时间范围: {hours}小时")
        news_data = manager.get_news_data(symbol=test_symbol, hours_back=hours, limit=10)

        if news_data and len(news_data) > 0:
            print(f"   ✅ 获取成功: {len(news_data)}条新闻")
        else:
            print("   ⚠️ 无数据")
        print()


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("🚀 新闻数据统一功能测试")
    print("=" * 70)
    print()
    print("📝 测试说明:")
    print("   本测试验证DataSourceManager是否正确支持新闻数据获取")
    print("   包括个股新闻、市场新闻、降级机制等")
    print()
    print("💡 配置要求:")
    print("   - TA_USE_APP_CACHE=true  # 启用 MongoDB 缓存")
    print("   - MongoDB 服务正常运行")
    print("   - Tushare/AKShare API 可用")
    print()

    try:
        # 测试数据源优先级
        test_data_source_priority()

        # 测试个股新闻
        test_stock_news()

        # 测试市场新闻
        test_market_news()

        # 测试降级机制
        test_fallback_mechanism()

        # 测试不同时间范围
        test_different_time_ranges()

        print_section("✅ 所有测试完成")
        print()
        print("💡 提示：检查上面的日志，确认")
        print("   1. 个股新闻和市场新闻是否都能正确获取")
        print("   2. 数据获取日志中是否显示正确的数据来源")
        print("   3. 降级机制是否正常工作")
        print("   4. MongoDB优先级是否正确")
        print()

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
