#!/usr/bin/env python3
"""
调试BaoStock返回的字段结构
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

import pandas as pd

from tradingagents.dataflows.providers.china.baostock_patched import safe_login, safe_logout

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


def debug_baostock_fields():
    """调试BaoStock返回的字段结构"""
    print("=" * 60)
    print("🔍 调试BaoStock返回的字段结构")
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

        # 获取股票列表
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"📅 查询日期: {trade_date}")

        rs = bs.query_all_stock(day=trade_date)
        print(f"返回码: {rs.error_code}")
        print(f"返回消息: {rs.error_msg}")
        print(f"字段列表: {rs.fields}")

        if rs.error_code == "0":
            # 解析数据
            data_list = []
            count = 0
            while (rs.error_code == "0") & rs.next():
                row = rs.get_row_data()
                data_list.append(row)
                count += 1
                if count <= 10:  # 显示前10条
                    print(f"第{count}条: {row}")
                if count >= 100:  # 限制总数
                    break

            print(f"\n📊 总共获取到 {len(data_list)} 条记录")

            if data_list:
                # 转换为DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                print(f"DataFrame形状: {df.shape}")
                print(f"列名: {list(df.columns)}")
                print("前5行数据:")
                print(df.head())

                # 分析A股股票
                print("\n🔍 分析A股股票:")
                a_stock_pattern = r"^(sh|sz)\.[0-9]{6}$"
                a_stocks = df[df["code"].str.contains(a_stock_pattern, na=False)]
                print(f"匹配A股模式的股票数量: {len(a_stocks)}")

                if len(a_stocks) > 0:
                    print("A股样本:")
                    print(a_stocks.head())

                    # 检查字段映射
                    print("\n📋 字段映射分析:")
                    print(f"code -> symbol: {a_stocks['code'].head(3).tolist()}")
                    if "code_name" in a_stocks.columns:
                        print(f"code_name -> name: {a_stocks['code_name'].head(3).tolist()}")
                    if "tradeStatus" in a_stocks.columns:
                        print(f"tradeStatus: {a_stocks['tradeStatus'].head(3).tolist()}")

        safe_logout()
        print("\n✅ BaoStock登出成功")

    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_baostock_fields()
