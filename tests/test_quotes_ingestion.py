"""
测试行情入库服务的股票代码标准化和历史数据导入功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from app.core.database import close_db, get_mongo_db, init_db
from app.services.quotes_ingestion_service import QuotesIngestionService


async def test_normalize_stock_code():
    """测试股票代码标准化功能"""
    print("\n" + "=" * 60)
    print("测试 1: 股票代码标准化功能")
    print("=" * 60)

    test_cases = [
        ("sz000001", "000001", "深圳平安银行"),
        ("sh600036", "600036", "上海招商银行"),
        ("000001", "000001", "标准6位代码"),
        ("1", "000001", "单个数字"),
        ("600036", "600036", "已经是6位"),
        ("sz002594", "002594", "深圳比亚迪"),
        ("", "", "空字符串"),
        ("abc123", "000123", "包含字母"),
        ("sz000000", "000000", "全0代码"),
    ]

    service = QuotesIngestionService()

    passed = 0
    failed = 0

    for input_code, expected, description in test_cases:
        result = service._normalize_stock_code(input_code)
        status = "✅" if result == expected else "❌"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} {description:20s} | 输入: {input_code:12s} | 期望: {expected:8s} | 实际: {result:8s}")

    print(f"\n总计: {len(test_cases)} 个测试用例, 通过: {passed}, 失败: {failed}")

    return failed == 0


async def test_market_quotes_status():
    """测试 market_quotes 集合状态"""
    print("\n" + "=" * 60)
    print("测试 2: market_quotes 集合状态检查")
    print("=" * 60)

    await init_db()
    db = get_mongo_db()
    service = QuotesIngestionService()

    # 检查集合是否为空
    is_empty = await service._collection_empty()
    count = await db.market_quotes.estimated_document_count()

    print("📊 market_quotes 集合状态:")
    print(f"   - 是否为空: {is_empty}")
    print(f"   - 文档数量: {count}")

    if count > 0:
        # 获取一些样本数据
        sample_docs = await db.market_quotes.find().limit(5).to_list(length=5)
        print("\n📋 样本数据 (前5条):")
        for i, doc in enumerate(sample_docs, 1):
            code = doc.get("code") or doc.get("symbol")
            close = doc.get("close")
            trade_date = doc.get("trade_date")
            updated_at = doc.get("updated_at")
            print(f"   {i}. 代码: {code}, 收盘价: {close}, 交易日: {trade_date}, 更新时间: {updated_at}")

        # 检查是否有带前缀的代码
        print("\n🔍 检查是否有异常代码（长度不是6位）:")
        pipeline = [
            {"$project": {"code": 1, "code_length": {"$strLenCP": {"$toString": "$code"}}}},
            {"$match": {"code_length": {"$ne": 6}}},
            {"$limit": 10},
        ]

        abnormal_docs = await db.market_quotes.aggregate(pipeline).to_list(length=10)

        if abnormal_docs:
            print(f"   ⚠️ 发现 {len(abnormal_docs)} 条异常代码:")
            for doc in abnormal_docs:
                print(f"      - 代码: {doc.get('code')}, 长度: {doc.get('code_length')}")
        else:
            print("   ✅ 所有代码都是标准的6位格式")

    await close_db()
    return True


async def test_historical_data_import():
    """测试从历史数据导入功能"""
    print("\n" + "=" * 60)
    print("测试 3: 从历史数据导入到 market_quotes")
    print("=" * 60)

    await init_db()
    db = get_mongo_db()
    service = QuotesIngestionService()

    # 检查 stock_daily_quotes 集合状态
    daily_count = await db.stock_daily_quotes.estimated_document_count()
    print("📊 stock_daily_quotes 集合状态:")
    print(f"   - 文档数量: {daily_count}")

    if daily_count == 0:
        print("   ⚠️ 历史数据集合为空，无法测试导入功能")
        await close_db()
        return False

    # 获取最新交易日
    latest_doc = await db.stock_daily_quotes.find({"period": "daily"}).sort("trade_date", -1).limit(1).to_list(length=1)

    if latest_doc:
        latest_trade_date = latest_doc[0].get("trade_date")
        print(f"   - 最新交易日: {latest_trade_date}")

        # 统计该交易日的数据量
        date_count = await db.stock_daily_quotes.count_documents({"trade_date": latest_trade_date, "period": "daily"})
        print(f"   - 该日数据量: {date_count}")
    else:
        print("   ⚠️ 无法获取最新交易日")
        await close_db()
        return False

    # 检查 market_quotes 当前状态
    market_count_before = await db.market_quotes.estimated_document_count()
    print("\n📊 market_quotes 导入前状态:")
    print(f"   - 文档数量: {market_count_before}")

    # 询问用户是否要清空 market_quotes 进行测试
    print("\n⚠️  是否要清空 market_quotes 集合来测试导入功能？")
    print("   输入 'yes' 清空并测试，输入其他跳过测试")

    # 由于是自动化测试，我们不清空，只是模拟检查
    print("   [自动跳过清空操作，仅检查导入逻辑]")

    # 测试 backfill_from_historical_data 方法
    print("\n🔄 测试历史数据导入逻辑...")

    try:
        # 如果集合不为空，方法会自动跳过
        await service.backfill_from_historical_data()

        market_count_after = await db.market_quotes.estimated_document_count()
        print("\n📊 market_quotes 导入后状态:")
        print(f"   - 文档数量: {market_count_after}")

        if market_count_after > market_count_before:
            print(f"   ✅ 成功导入 {market_count_after - market_count_before} 条数据")
        elif market_count_before > 0:
            print("   ℹ️  集合不为空，跳过导入（符合预期）")
        else:
            print("   ⚠️ 集合为空但未导入数据，可能历史数据不足")

    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        import traceback

        traceback.print_exc()
        await close_db()
        return False

    await close_db()
    return True


async def test_akshare_realtime_quotes():
    """测试 AKShare 实时行情获取（检查代码标准化）"""
    print("\n" + "=" * 60)
    print("测试 4: AKShare 实时行情代码标准化")
    print("=" * 60)

    try:
        from app.services.data_sources.akshare_adapter import AKShareAdapter

        adapter = AKShareAdapter()

        if not adapter.is_available():
            print("   ⚠️ AKShare 不可用，跳过测试")
            return True

        print("   📡 正在获取实时行情（新浪接口）...")
        quotes_map = adapter.get_realtime_quotes(source="sina")

        if not quotes_map:
            print("   ⚠️ 未获取到实时行情数据")
            return False

        print(f"   ✅ 获取到 {len(quotes_map)} 只股票的实时行情")

        # 检查代码格式
        print("\n🔍 检查代码格式（前10个）:")
        abnormal_codes = []

        for i, (code, data) in enumerate(list(quotes_map.items())[:10], 1):
            code_len = len(code)
            is_digit = code.isdigit()
            status = "✅" if code_len == 6 and is_digit else "❌"

            if code_len != 6 or not is_digit:
                abnormal_codes.append(code)

            print(
                f"   {status} {i:2d}. 代码: {code:8s} | 长度: {code_len} | 纯数字: {is_digit} | 收盘价: {data.get('close')}",
            )

        if abnormal_codes:
            print(f"\n   ⚠️ 发现 {len(abnormal_codes)} 个异常代码")
            return False
        print("\n   ✅ 所有代码都是标准的6位数字格式")
        return True

    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🧪 行情入库服务测试程序")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # 测试 1: 股票代码标准化
    result1 = await test_normalize_stock_code()
    results.append(("股票代码标准化", result1))

    # 测试 2: market_quotes 集合状态
    result2 = await test_market_quotes_status()
    results.append(("market_quotes 状态检查", result2))

    # 测试 3: 历史数据导入
    result3 = await test_historical_data_import()
    results.append(("历史数据导入", result3))

    # 测试 4: AKShare 实时行情
    result4 = await test_akshare_realtime_quotes()
    results.append(("AKShare 实时行情", result4))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status:8s} | {test_name}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\n总计: {total} 个测试, 通过: {passed}, 失败: {total - passed}")

    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查日志")


if __name__ == "__main__":
    asyncio.run(main())
