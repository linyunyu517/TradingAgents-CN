#!/usr/bin/env python3
"""
测试 AKShare 港股历史数据接口返回的字段
检查字段映射是否正确
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta

import akshare as ak


def test_hk_stock_data_fields():
    """测试港股历史数据字段"""

    print("=" * 80)
    print("🔍 测试 AKShare 港股历史数据接口")
    print("=" * 80)

    # 测试腾讯控股 00700
    symbol = "00700"

    print(f"\n📊 测试股票: {symbol} (腾讯控股)")
    print("-" * 80)

    try:
        # 获取最近 5 天的数据
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

        print(f"📅 日期范围: {start_date} - {end_date}")
        print(f"🔄 调用 ak.stock_hk_daily(symbol='{symbol}', adjust='qfq')")
        print()

        # 调用 AKShare 接口
        df = ak.stock_hk_daily(symbol=symbol, adjust="qfq")

        if df is None or df.empty:
            print("❌ 未获取到数据")
            return

        # 只显示最近 5 条
        df_recent = df.tail(5)

        print("✅ 成功获取数据")
        print(f"📊 总记录数: {len(df)}")
        print(f"📋 字段列表: {list(df.columns)}")
        print()

        print("=" * 80)
        print("📋 最近 5 天的原始数据")
        print("=" * 80)
        print(df_recent.to_string())
        print()

        # 显示字段类型
        print("=" * 80)
        print("📋 字段类型")
        print("=" * 80)
        print(df.dtypes)
        print()

        # 显示最新一天的详细数据
        print("=" * 80)
        print("📋 最新一天的详细数据")
        print("=" * 80)
        latest = df_recent.iloc[-1]
        for col in df_recent.columns:
            print(f"{col:15s} = {latest[col]}")
        print()

        # 检查字段映射
        print("=" * 80)
        print("🔍 检查字段映射")
        print("=" * 80)

        # 根据百度财经的数据，检查字段是否正确
        print("\n根据百度财经数据:")
        print("  今开: 638.000")
        print("  昨收: 644.000")
        print("  最高: 643.000")
        print("  最低: 628.500")
        print()

        # 检查 AKShare 返回的字段
        if "开盘" in df_recent.columns:
            print("✅ '开盘' 字段存在")
        if "收盘" in df_recent.columns:
            print("✅ '收盘' 字段存在")
        if "最高" in df_recent.columns:
            print("✅ '最高' 字段存在")
        if "最低" in df_recent.columns:
            print("✅ '最低' 字段存在")
        if "成交量" in df_recent.columns:
            print("✅ '成交量' 字段存在")
        if "成交额" in df_recent.columns:
            print("✅ '成交额' 字段存在")

        print()

        # 分析字段映射
        print("=" * 80)
        print("🔍 字段映射分析")
        print("=" * 80)

        # 获取最新两天的数据
        if len(df_recent) >= 2:
            today = df_recent.iloc[-1]
            yesterday = df_recent.iloc[-2]

            print("\n最新交易日:")
            print(f"  日期: {today.get('date', 'N/A')}")
            print(f"  开盘: {today.get('open', 'N/A')}")
            print(f"  收盘: {today.get('close', 'N/A')}")
            print(f"  最高: {today.get('high', 'N/A')}")
            print(f"  最低: {today.get('low', 'N/A')}")

            print("\n前一交易日:")
            print(f"  日期: {yesterday.get('date', 'N/A')}")
            print(f"  收盘: {yesterday.get('close', 'N/A')}")

            print("\n⚠️  注意:")
            print(f"  今日开盘 ({today.get('open', 'N/A')}) 应该接近昨日收盘 ({yesterday.get('close', 'N/A')})")
            print("  如果今日开盘 = 638.000，昨日收盘应该 ≈ 644.000")

            # 检查是否有 "昨收" 字段
            if "pre_close" in df_recent.columns:
                print(f"\n✅ 发现 'pre_close' 字段: {today.get('pre_close', 'N/A')}")
            else:
                print("\n⚠️  没有 'pre_close' 字段，需要从前一天的 'close' 获取")
                print(f"   昨收 (计算) = {yesterday.get('close', 'N/A')}")

        print()

        # 测试字段映射代码
        print("=" * 80)
        print("🔍 测试当前代码的字段映射")
        print("=" * 80)

        # 模拟当前代码的映射逻辑（AKShare 返回的是英文字段）
        latest = df_recent.iloc[-1]

        mapped_data = {
            "date": latest.get("date"),
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "close": latest.get("close"),
            "volume": latest.get("volume"),
            "amount": latest.get("amount"),  # AKShare 不返回 amount
            "pre_close": latest.get("pre_close"),  # AKShare 不返回 pre_close
        }

        print("\n当前映射结果:")
        for key, value in mapped_data.items():
            print(f"  {key:10s} = {value}")

        # 检查是否有问题
        print("\n⚠️  问题检查:")
        if mapped_data["open"] and mapped_data["low"]:
            if abs(float(mapped_data["open"]) - 638.0) < 1.0:
                print(f"  ✅ 开盘价 ({mapped_data['open']}) 接近 638.000")
            else:
                print(f"  ❌ 开盘价 ({mapped_data['open']}) 不接近 638.000")

            if abs(float(mapped_data["low"]) - 628.5) < 1.0:
                print(f"  ✅ 最低价 ({mapped_data['low']}) 接近 628.500")
            else:
                print(f"  ❌ 最低价 ({mapped_data['low']}) 不接近 628.500")

        # 检查昨收字段
        if mapped_data["pre_close"] is None:
            print("  ⚠️  pre_close 字段为 None，需要从前一天的 close 获取")
            if len(df_recent) >= 2:
                yesterday_close = df_recent.iloc[-2].get("close")
                print(f"  💡 解决方案: pre_close = 前一天的 close = {yesterday_close}")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback

        traceback.print_exc()


def test_multiple_stocks():
    """测试多个港股的数据"""

    print("\n" + "=" * 80)
    print("🔍 测试多个港股的数据")
    print("=" * 80)

    test_stocks = [
        ("00700", "腾讯控股"),
        ("00941", "中国移动"),
        ("01299", "友邦保险"),
    ]

    for symbol, name in test_stocks:
        print(f"\n📊 {symbol} - {name}")
        print("-" * 80)

        try:
            df = ak.stock_hk_daily(symbol=symbol, adjust="qfq")

            if df is None or df.empty:
                print("  ❌ 未获取到数据")
                continue

            latest = df.iloc[-1]

            print(f"  日期: {latest.get('date', 'N/A')}")
            print(f"  开盘: {latest.get('open', 'N/A')}")
            print(f"  收盘: {latest.get('close', 'N/A')}")
            print(f"  最高: {latest.get('high', 'N/A')}")
            print(f"  最低: {latest.get('low', 'N/A')}")
            print(f"  成交量: {latest.get('volume', 'N/A')}")

            # 检查是否有昨收字段
            if "pre_close" in df.columns:
                print(f"  昨收: {latest.get('pre_close', 'N/A')}")
            elif len(df) >= 2:
                yesterday_close = df.iloc[-2].get("close", "N/A")
                print(f"  昨收 (计算): {yesterday_close}")

        except Exception as e:
            print(f"  ❌ 错误: {e}")


if __name__ == "__main__":
    test_hk_stock_data_fields()
    test_multiple_stocks()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)
