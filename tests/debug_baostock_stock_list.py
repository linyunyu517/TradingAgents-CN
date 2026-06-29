#!/usr/bin/env python3
"""
调试BaoStock股票列表获取问题
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

import pandas as pd

from tradingagents.dataflows.providers.china.baostock_patched import safe_login, safe_logout

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


def debug_baostock_query_all_stock():
    """调试BaoStock的query_all_stock接口"""
    print("=" * 60)
    print("🔍 调试BaoStock的query_all_stock接口")
    print("=" * 60)

    try:
        import baostock as bs

        # 登录BaoStock
        lg = safe_login()
        if lg is None:
            print("❌ BaoStock登录失败: safe_login 返回 None")
            return
        if lg.error_code != "0":
            print(f"❌ BaoStock登录失败: {lg.error_msg}")
            return

        print("✅ BaoStock登录成功")

        try:
            # 获取股票基本信息
            print("📊 调用bs.query_all_stock()...")
            rs = bs.query_all_stock()

            print(f"   返回码: {rs.error_code}")
            print(f"   返回消息: {rs.error_msg}")
            print(f"   字段列表: {rs.fields}")

            if rs.error_code != "0":
                print(f"❌ 查询失败: {rs.error_msg}")
                return

            # 解析数据
            data_list = []
            count = 0
            while (rs.error_code == "0") & rs.next():
                row = rs.get_row_data()
                data_list.append(row)
                count += 1
                if count <= 10:  # 只显示前10条
                    print(f"   第{count}条: {row}")
                if count >= 100:  # 限制总数以避免过多输出
                    break

            print(f"\n📈 总共获取到 {len(data_list)} 条记录")

            if data_list:
                # 转换为DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                print(f"   DataFrame形状: {df.shape}")
                print(f"   列名: {list(df.columns)}")

                # 检查A股股票
                if "code" in df.columns:
                    print("\n🔍 分析股票代码格式:")
                    code_samples = df["code"].head(20).tolist()
                    print(f"   前20个代码: {code_samples}")

                    # 检查A股过滤条件
                    a_stock_pattern = r"^(sh|sz)\.[0-9]{6}$"
                    a_stocks = df[df["code"].str.contains(a_stock_pattern, na=False)]
                    print(f"   匹配A股模式的股票数量: {len(a_stocks)}")

                    if len(a_stocks) > 0:
                        print("   A股样本:")
                        for _i, row in a_stocks.head(5).iterrows():
                            print(f"     {row['code']} - {row.get('code_name', 'N/A')}")
                    else:
                        print("   ❌ 没有找到匹配A股模式的股票!")
                        print("   所有代码格式样本:")
                        unique_patterns = df["code"].str.extract(r"^([a-z]+)\.").iloc[:, 0].value_counts()
                        print(f"     {unique_patterns}")
                else:
                    print("   ❌ 没有找到'code'列")
            else:
                print("   ❌ 没有获取到任何数据")

        finally:
            safe_logout()
            print("✅ BaoStock登出成功")

    except ImportError:
        print("❌ BaoStock未安装")
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback

        traceback.print_exc()


def debug_baostock_stock_basic():
    """调试BaoStock的query_stock_basic接口"""
    print("\n" + "=" * 60)
    print("🔍 调试BaoStock的query_stock_basic接口")
    print("=" * 60)

    try:
        import baostock as bs

        # 登录BaoStock
        lg = safe_login()
        if lg is None:
            print("❌ BaoStock登录失败: safe_login 返回 None")
            return
        if lg.error_code != "0":
            print(f"❌ BaoStock登录失败: {lg.error_msg}")
            return

        print("✅ BaoStock登录成功")

        # 测试几个已知的股票代码
        test_codes = ["sh.600000", "sz.000001", "sh.600519"]

        for code in test_codes:
            print(f"\n📊 测试股票: {code}")
            try:
                rs = bs.query_stock_basic(code=code)
                print(f"   返回码: {rs.error_code}")
                print(f"   返回消息: {rs.error_msg}")

                if rs.error_code == "0":
                    data_list = []
                    while (rs.error_code == "0") & rs.next():
                        data_list.append(rs.get_row_data())

                    if data_list:
                        print(f"   ✅ 获取成功: {data_list[0]}")
                    else:
                        print("   ⚠️ 无数据返回")
                else:
                    print(f"   ❌ 查询失败: {rs.error_msg}")

            except Exception as e:
                print(f"   ❌ 异常: {e}")

        safe_logout()
        print("\n✅ BaoStock登出成功")

    except Exception as e:
        print(f"❌ 调试失败: {e}")


def test_baostock_adapter_stock_list():
    """测试BaoStock适配器的股票列表获取"""
    print("\n" + "=" * 60)
    print("🔍 测试BaoStock适配器的股票列表获取")
    print("=" * 60)

    try:
        from app.services.data_source_adapters import BaoStockAdapter

        adapter = BaoStockAdapter()

        if not adapter.is_available():
            print("❌ BaoStock适配器不可用")
            return

        print("✅ BaoStock适配器可用")

        # 获取股票列表
        print("📊 调用adapter.get_stock_list()...")
        df = adapter.get_stock_list()

        if df is not None and not df.empty:
            print(f"✅ 股票列表获取成功: {len(df)}条记录")
            print(f"   列名: {list(df.columns)}")
            print("   前5条记录:")
            for _i, row in df.head().iterrows():
                print(f"     {row.get('symbol', 'N/A')} - {row.get('name', 'N/A')} - {row.get('ts_code', 'N/A')}")
        else:
            print("❌ 股票列表获取失败")

    except Exception as e:
        print(f"❌ 适配器测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_baostock_query_all_stock()
    debug_baostock_stock_basic()
    test_baostock_adapter_stock_list()
