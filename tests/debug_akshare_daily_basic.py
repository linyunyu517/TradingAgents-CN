#!/usr/bin/env python3
"""
调试AKShare的daily_basic功能
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


def test_akshare_spot_data():
    """测试AKShare的实时行情数据"""
    print("=" * 60)
    print("🧪 测试AKShare的实时行情数据")
    print("=" * 60)

    try:
        import akshare as ak

        print("✅ AKShare导入成功")

        # 获取A股实时行情数据
        print("📊 调用ak.stock_zh_a_spot_em()...")
        spot_data = ak.stock_zh_a_spot_em()

        if spot_data is not None and not spot_data.empty:
            print(f"✅ 实时行情数据获取成功: {len(spot_data)}条记录")
            print(f"   列名: {list(spot_data.columns)}")

            # 检查需要的列是否存在
            required_cols = ["代码", "名称", "市盈率-动态", "市净率", "总市值"]
            print("\n🔍 检查需要的列:")
            for col in required_cols:
                exists = col in spot_data.columns
                print(f"   {col}: {'✅ 存在' if exists else '❌ 不存在'}")

            # 显示实际的列名（可能有变化）
            print("\n📋 实际列名（前20个）:")
            for i, col in enumerate(spot_data.columns[:20]):
                print(f"   {i + 1:2d}. {col}")

            # 显示前几条数据
            print("\n📊 前5条数据:")
            print(spot_data.head())

            # 查找可能的PE、PB相关列
            print("\n🔍 查找PE、PB相关列:")
            pe_cols = [col for col in spot_data.columns if "市盈率" in col or "PE" in col or "pe" in col]
            pb_cols = [col for col in spot_data.columns if "市净率" in col or "PB" in col or "pb" in col]
            mv_cols = [col for col in spot_data.columns if "市值" in col or "总市值" in col]

            print(f"   PE相关列: {pe_cols}")
            print(f"   PB相关列: {pb_cols}")
            print(f"   市值相关列: {mv_cols}")

        else:
            print("❌ 实时行情数据获取失败或为空")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_akshare_adapter():
    """测试AKShare适配器"""
    print("\n" + "=" * 60)
    print("🧪 测试AKShare适配器")
    print("=" * 60)

    try:
        from app.services.data_source_adapters import AKShareAdapter

        adapter = AKShareAdapter()

        if not adapter.is_available():
            print("❌ AKShare适配器不可用")
            return

        print("✅ AKShare适配器可用")

        # 测试daily_basic获取
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"\n📅 测试获取{trade_date}的daily_basic数据...")

        df = adapter.get_daily_basic(trade_date)

        if df is not None and not df.empty:
            print(f"✅ daily_basic数据获取成功: {len(df)}条记录")
            print(f"   列名: {list(df.columns)}")

            # 显示前几条记录
            print("   前5条记录:")
            for _i, row in df.head().iterrows():
                ts_code = row.get("ts_code", "N/A")
                name = row.get("name", "N/A")
                pe = row.get("pe", "N/A")
                pb = row.get("pb", "N/A")
                total_mv = row.get("total_mv", "N/A")
                print(f"     {ts_code} - {name}")
                print(f"       PE: {pe}, PB: {pb}, 总市值: {total_mv}")

            # 统计有效数据
            pe_count = df["pe"].notna().sum() if "pe" in df.columns else 0
            pb_count = df["pb"].notna().sum() if "pb" in df.columns else 0
            mv_count = df["total_mv"].notna().sum() if "total_mv" in df.columns else 0

            print("\n   📈 数据统计:")
            print(f"     有PE数据的股票: {pe_count}只")
            print(f"     有PB数据的股票: {pb_count}只")
            print(f"     有总市值数据的股票: {mv_count}只")

        else:
            print("❌ daily_basic数据获取失败")

    except Exception as e:
        print(f"❌ 适配器测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_akshare_alternative_apis():
    """测试AKShare的其他财务数据API"""
    print("\n" + "=" * 60)
    print("🧪 测试AKShare的其他财务数据API")
    print("=" * 60)

    try:
        import akshare as ak

        # 测试不同的API
        apis_to_test = [
            ("stock_zh_a_spot_em", "东方财富-沪深京A股-实时行情"),
            ("stock_zh_a_hist_min_em", "东方财富-沪深京A股-历史分钟行情"),
            ("stock_individual_info_em", "东方财富-个股信息"),
        ]

        for api_name, description in apis_to_test:
            print(f"\n📊 测试 {api_name} ({description}):")
            try:
                if api_name == "stock_zh_a_spot_em":
                    data = ak.stock_zh_a_spot_em()
                elif api_name == "stock_individual_info_em":
                    # 测试单个股票
                    data = ak.stock_individual_info_em(symbol="000001")
                else:
                    print("   ⏭️ 跳过复杂API测试")
                    continue

                if data is not None and not data.empty:
                    print(f"   ✅ 成功: {len(data)}条记录")
                    print(f"   列名: {list(data.columns)[:10]}...")  # 只显示前10个列名
                else:
                    print("   ❌ 无数据")

            except Exception as e:
                print(f"   ❌ 失败: {e}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    test_akshare_spot_data()
    test_akshare_adapter()
    test_akshare_alternative_apis()
