"""
调试增强数据适配器
检查MongoDB中的数据格式和查询问题
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

from tradingagents.config.database_manager import get_mongodb_client


def check_mongodb_data():
    """检查MongoDB中的数据"""
    print("🔍 检查MongoDB中的数据")
    print("=" * 60)

    client = get_mongodb_client()
    db = client.get_database("tradingagents")

    # 1. 检查基础信息
    print("\n1️⃣ 检查基础信息集合")
    basic_info = db.stock_basic_info
    count = basic_info.count_documents({})
    print(f"   总记录数: {count:,}")

    sample = basic_info.find_one({"code": "000001"})
    if sample:
        print(f"   000001示例: {sample.get('name', 'N/A')}")
        print(f"   字段: {list(sample.keys())}")

    # 2. 检查历史数据
    print("\n2️⃣ 检查历史数据集合")
    quotes = db.stock_daily_quotes
    count = quotes.count_documents({})
    print(f"   总记录数: {count:,}")

    # 检查000001的数据
    count_000001 = quotes.count_documents({"symbol": "000001"})
    print(f"   000001记录数: {count_000001:,}")

    # 获取一条示例数据
    sample = quotes.find_one({"symbol": "000001"}, sort=[("trade_date", -1)])
    if sample:
        print("   最新记录:")
        print(f"     trade_date: {sample.get('trade_date')} (类型: {type(sample.get('trade_date'))})")
        print(f"     close: {sample.get('close')}")
        print(f"     period: {sample.get('period', 'N/A')}")
        print(f"     data_source: {sample.get('data_source', 'N/A')}")
        print(f"   字段: {list(sample.keys())}")

    # 检查不同周期的数据
    for period in ["daily", "weekly", "monthly"]:
        count_period = quotes.count_documents({"symbol": "000001", "period": period})
        print(f"   000001 {period}数据: {count_period:,}条")

    # 3. 检查财务数据
    print("\n3️⃣ 检查财务数据集合")
    financial = db.stock_financial_data
    count = financial.count_documents({})
    print(f"   总记录数: {count:,}")

    count_000001 = financial.count_documents({"symbol": "000001"})
    print(f"   000001记录数: {count_000001:,}")

    sample = financial.find_one({"symbol": "000001"}, sort=[("report_period", -1)])
    if sample:
        print("   最新记录:")
        print(f"     report_period: {sample.get('report_period')}")
        print(f"     字段: {list(sample.keys())[:10]}...")

    # 4. 检查新闻数据
    print("\n4️⃣ 检查新闻数据集合")
    news = db.stock_news
    count = news.count_documents({})
    print(f"   总记录数: {count:,}")

    count_000001 = news.count_documents({"symbol": "000001"})
    print(f"   000001记录数: {count_000001:,}")

    # 5. 检查社媒数据
    print("\n5️⃣ 检查社媒数据集合")
    social = db.social_media_data
    count = social.count_documents({})
    print(f"   总记录数: {count:,}")

    count_000001 = social.count_documents({"symbol": "000001"})
    print(f"   000001记录数: {count_000001:,}")


def test_date_format_query():
    """测试不同日期格式的查询"""
    print("\n🔍 测试日期格式查询")
    print("=" * 60)

    client = get_mongodb_client()
    db = client.get_database("tradingagents")
    quotes = db.stock_daily_quotes

    # 获取一条示例数据看日期格式
    sample = quotes.find_one({"symbol": "000001"}, sort=[("trade_date", -1)])
    if not sample:
        print("❌ 未找到000001的数据")
        return

    stored_date = sample.get("trade_date")
    print("\n📅 MongoDB中存储的日期格式:")
    print(f"   值: {stored_date}")
    print(f"   类型: {type(stored_date)}")

    # 测试不同格式的查询
    test_formats = [
        ("YYYY-MM-DD", "2024-01-01"),
        ("YYYYMMDD", "20240101"),
        ("YYYY/MM/DD", "2024/01/01"),
    ]

    print("\n🔍 测试不同日期格式的查询:")
    for format_name, date_str in test_formats:
        count = quotes.count_documents({"symbol": "000001", "trade_date": {"$gte": date_str}})
        print(f"   {format_name} ({date_str}): {count:,}条")

    # 测试最近30天的查询
    print("\n🔍 测试最近30天的查询:")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    # 格式1: YYYY-MM-DD
    start_str1 = start_date.strftime("%Y-%m-%d")
    end_str1 = end_date.strftime("%Y-%m-%d")
    count1 = quotes.count_documents({"symbol": "000001", "trade_date": {"$gte": start_str1, "$lte": end_str1}})
    print(f"   YYYY-MM-DD ({start_str1} ~ {end_str1}): {count1:,}条")

    # 格式2: YYYYMMDD
    start_str2 = start_date.strftime("%Y%m%d")
    end_str2 = end_date.strftime("%Y%m%d")
    count2 = quotes.count_documents({"symbol": "000001", "trade_date": {"$gte": start_str2, "$lte": end_str2}})
    print(f"   YYYYMMDD ({start_str2} ~ {end_str2}): {count2:,}条")


def test_enhanced_adapter_with_correct_format():
    """使用正确的日期格式测试增强适配器"""
    print("\n🔍 测试增强适配器（使用正确日期格式）")
    print("=" * 60)

    from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter

    adapter = get_enhanced_data_adapter()

    if not adapter.use_app_cache:
        print("❌ MongoDB模式未启用")
        return

    # 测试不同日期格式
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    # 格式1: YYYY-MM-DD
    print("\n1️⃣ 测试 YYYY-MM-DD 格式:")
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"   查询范围: {start_str} ~ {end_str}")

    df = adapter.get_historical_data("000001", start_str, end_str)
    if df is not None and not df.empty:
        print(f"   ✅ 成功: {len(df)}条记录")
        print(f"   日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    else:
        print("   ❌ 失败: 未获取到数据")

    # 格式2: YYYYMMDD
    print("\n2️⃣ 测试 YYYYMMDD 格式:")
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    print(f"   查询范围: {start_str} ~ {end_str}")

    df = adapter.get_historical_data("000001", start_str, end_str)
    if df is not None and not df.empty:
        print(f"   ✅ 成功: {len(df)}条记录")
        print(f"   日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    else:
        print("   ❌ 失败: 未获取到数据")


if __name__ == "__main__":
    check_mongodb_data()
    test_date_format_query()
    test_enhanced_adapter_with_correct_format()

    print("\n" + "=" * 60)
    print("✅ 调试完成")
