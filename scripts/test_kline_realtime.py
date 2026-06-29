"""
测试K线数据获取功能（包括当天实时数据）

测试场景：
1. 获取历史K线数据
2. 检查是否包含当天的实时数据
3. 验证数据来源标识
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import get_mongo_db, init_database


async def test_kline_realtime():
    """测试K线数据获取（包括当天实时数据）"""

    # 初始化数据库连接
    await init_database()
    """测试K线数据获取（包括当天实时数据）"""

    # 测试股票代码
    test_code = "000001"  # 平安银行

    print("=" * 80)
    print("🧪 测试K线数据获取功能（包括当天实时数据）")
    print("=" * 80)

    # 1. 检查 market_quotes 中是否有当天数据
    print("\n📊 步骤1：检查 market_quotes 集合中的当天数据")
    db = get_mongo_db()
    market_quotes_coll = db["market_quotes"]

    realtime_quote = await market_quotes_coll.find_one({"code": test_code})

    if realtime_quote:
        print("✅ 找到当天实时数据:")
        print(f"   - 代码: {realtime_quote.get('code')}")
        print(f"   - 开盘: {realtime_quote.get('open')}")
        print(f"   - 最高: {realtime_quote.get('high')}")
        print(f"   - 最低: {realtime_quote.get('low')}")
        print(f"   - 收盘: {realtime_quote.get('close')}")
        print(f"   - 成交量: {realtime_quote.get('volume')}")
        print(f"   - 成交额: {realtime_quote.get('amount')}")
        print(f"   - 更新时间: {realtime_quote.get('updated_at')}")
    else:
        print(f"⚠️ market_quotes 中未找到 {test_code} 的数据")

    # 2. 检查历史K线数据中是否有当天数据
    print("\n📊 步骤2：检查 stock_daily_quotes 集合中的历史数据")
    stock_daily_quotes_coll = db["stock_daily_quotes"]

    tz = ZoneInfo(settings.TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%Y%m%d")

    historical_today = await stock_daily_quotes_coll.find_one(
        {"symbol": test_code, "period": "daily", "trade_date": today_str},
    )

    if historical_today:
        print("✅ 历史数据中已有当天数据:")
        print(f"   - 交易日期: {historical_today.get('trade_date')}")
        print(f"   - 开盘: {historical_today.get('open')}")
        print(f"   - 收盘: {historical_today.get('close')}")
    else:
        print(f"⚠️ 历史数据中没有当天数据 ({today_str})")

    # 3. 模拟调用 K线接口
    print("\n📊 步骤3：模拟调用 K线接口")
    print(f"   - 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   - 是否交易时间: {_is_trading_time(now)}")

    # 获取最近的K线数据
    cursor = (
        stock_daily_quotes_coll.find({"symbol": test_code, "period": "daily"}, {"_id": 0})
        .sort("trade_date", -1)
        .limit(5)
    )

    recent_klines = await cursor.to_list(length=5)

    if recent_klines:
        print("\n✅ 最近5条K线数据:")
        for kline in recent_klines:
            print(f"   - {kline.get('trade_date')}: 开盘={kline.get('open')}, 收盘={kline.get('close')}")
    else:
        print("⚠️ 未找到历史K线数据")

    # 4. 判断是否需要添加当天实时数据
    print("\n📊 步骤4：判断是否需要添加当天实时数据")

    has_today_data = any(kline.get("trade_date") == today_str for kline in recent_klines)
    is_trading_time = _is_trading_time(now)
    should_fetch_realtime = is_trading_time or not has_today_data

    print(f"   - 历史数据中有当天数据: {has_today_data}")
    print(f"   - 当前是交易时间: {is_trading_time}")
    print(f"   - 是否需要获取实时数据: {should_fetch_realtime}")

    if should_fetch_realtime and realtime_quote:
        print("\n✅ 将添加/替换当天实时数据:")
        print(f"   - 时间: {today_str}")
        print(f"   - 开盘: {realtime_quote.get('open')}")
        print(f"   - 收盘: {realtime_quote.get('close')}")

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


def _is_trading_time(now: datetime) -> bool:
    """判断是否在交易时间内"""
    from datetime import time as dtime

    current_time = now.time()
    return (
        dtime(9, 30) <= current_time <= dtime(15, 0) and now.weekday() < 5  # 周一到周五
    )


if __name__ == "__main__":
    asyncio.run(test_kline_realtime())
