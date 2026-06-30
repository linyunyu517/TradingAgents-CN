#!/usr/bin/env python3
"""
测试增强数据整合功能
验证 TA_USE_APP_CACHE 配置对数据访问的影响
"""

import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置环境变量
os.environ["TA_USE_APP_CACHE"] = "true"  # 启用MongoDB优先模式

from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter

from tradingagents.dataflows.optimized_china_data import get_optimized_china_data_provider


def test_enhanced_data_adapter():
    """测试增强数据适配器"""
    print("🔄 测试增强数据适配器...")

    adapter = get_enhanced_data_adapter()
    print(f"📊 MongoDB缓存模式: {'启用' if adapter.use_app_cache else '禁用'}")

    # 测试股票代码
    test_symbol = "000001"

    # 1. 测试基础信息获取
    print(f"\n1️⃣ 测试基础信息获取: {test_symbol}")
    basic_info = adapter.get_stock_basic_info(test_symbol)
    if basic_info:
        print(f"✅ 获取基础信息成功: {basic_info.get('name', 'N/A')}")
    else:
        print("❌ 未获取到基础信息")

    # 2. 测试历史数据获取
    print(f"\n2️⃣ 测试历史数据获取: {test_symbol}")
    end_date = datetime.now().strftime("%Y-%m-%d")  # 使用YYYY-MM-DD格式
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    historical_data = adapter.get_historical_data(test_symbol, start_date, end_date)
    if historical_data is not None and not historical_data.empty:
        print(f"✅ 获取历史数据成功: {len(historical_data)} 条记录")
        print(f"📅 数据范围: {historical_data['trade_date'].min()} - {historical_data['trade_date'].max()}")
    else:
        print("❌ 未获取到历史数据")

    # 3. 测试财务数据获取
    print(f"\n3️⃣ 测试财务数据获取: {test_symbol}")
    financial_data = adapter.get_financial_data(test_symbol)
    if financial_data:
        print(f"✅ 获取财务数据成功: 报告期 {financial_data.get('report_period', 'N/A')}")
    else:
        print("❌ 未获取到财务数据")

    # 4. 测试新闻数据获取
    print(f"\n4️⃣ 测试新闻数据获取: {test_symbol}")
    news_data = adapter.get_news_data(test_symbol, hours_back=24, limit=5)
    if news_data:
        print(f"✅ 获取新闻数据成功: {len(news_data)} 条记录")
    else:
        print("❌ 未获取到新闻数据")

    # 5. 测试社媒数据获取
    print(f"\n5️⃣ 测试社媒数据获取: {test_symbol}")
    social_data = adapter.get_social_media_data(test_symbol, hours_back=24, limit=5)
    if social_data:
        print(f"✅ 获取社媒数据成功: {len(social_data)} 条记录")
    else:
        print("❌ 未获取到社媒数据")


def test_optimized_china_data_provider():
    """测试优化的A股数据提供器"""
    print("\n🔄 测试优化的A股数据提供器...")

    provider = get_optimized_china_data_provider()
    test_symbol = "000001"

    # 测试股票数据获取
    print(f"\n📈 测试股票数据获取: {test_symbol}")
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        stock_data = provider.get_stock_data(test_symbol, start_date, end_date)
        if stock_data and len(stock_data) > 100:  # 简单检查数据长度
            print("✅ 股票数据获取成功")
            print(f"📊 数据长度: {len(stock_data)} 字符")
        else:
            print("❌ 股票数据获取失败或数据为空")
    except Exception as e:
        print(f"❌ 股票数据获取异常: {e}")

    # 测试基本面数据获取
    print(f"\n💰 测试基本面数据获取: {test_symbol}")
    try:
        fundamentals_data = provider.get_fundamentals_data(test_symbol)
        if fundamentals_data and len(fundamentals_data) > 100:
            print("✅ 基本面数据获取成功")
            print(f"📊 数据长度: {len(fundamentals_data)} 字符")
        else:
            print("❌ 基本面数据获取失败或数据为空")
    except Exception as e:
        print(f"❌ 基本面数据获取异常: {e}")


def test_cache_mode_comparison():
    """测试缓存模式对比"""
    print("\n🔄 测试缓存模式对比...")

    test_symbol = "000001"
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # 测试启用MongoDB模式
    print("\n📊 MongoDB优先模式:")
    os.environ["TA_USE_APP_CACHE"] = "true"
    provider1 = get_optimized_china_data_provider()

    start_time = datetime.now()
    try:
        data1 = provider1.get_stock_data(test_symbol, start_date, end_date)
        time1 = (datetime.now() - start_time).total_seconds()
        print(f"⏱️ 耗时: {time1:.2f}秒")
        print(f"📊 数据长度: {len(data1) if data1 else 0} 字符")
    except Exception as e:
        print(f"❌ 异常: {e}")

    # 测试禁用MongoDB模式
    print("\n📁 传统缓存模式:")
    os.environ["TA_USE_APP_CACHE"] = "false"
    # 注意：需要重新创建实例以应用新配置
    from importlib import reload

    import tradingagents.dataflows.enhanced_data_adapter

    reload(tradingagents.dataflows.enhanced_data_adapter)

    provider2 = get_optimized_china_data_provider()

    start_time = datetime.now()
    try:
        data2 = provider2.get_stock_data(test_symbol, start_date, end_date)
        time2 = (datetime.now() - start_time).total_seconds()
        print(f"⏱️ 耗时: {time2:.2f}秒")
        print(f"📊 数据长度: {len(data2) if data2 else 0} 字符")
    except Exception as e:
        print(f"❌ 异常: {e}")


def main():
    """主函数"""
    print("🚀 增强数据整合功能测试")
    print("=" * 50)

    # 测试1: 增强数据适配器
    test_enhanced_data_adapter()

    # 测试2: 优化的A股数据提供器
    test_optimized_china_data_provider()

    # 测试3: 缓存模式对比
    test_cache_mode_comparison()

    print("\n" + "=" * 50)
    print("✅ 测试完成")


if __name__ == "__main__":
    main()
