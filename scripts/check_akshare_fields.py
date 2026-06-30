#!/usr/bin/env python3
"""检查 AKShare 返回的财务数据字段"""

import asyncio

import akshare as ak


async def check_akshare_fields():
    print("=" * 80)
    print("检查 AKShare 返回的财务数据字段（平安银行 000001）")
    print("=" * 80)

    # 获取财务指标数据
    print("\n📊 调用 stock_financial_analysis_indicator...")
    try:
        df = await asyncio.to_thread(ak.stock_financial_analysis_indicator, symbol="000001")

        if df is not None and not df.empty:
            print(f"✅ 获取到 {len(df)} 期数据")

            # 获取最新一期
            latest = df.iloc[-1].to_dict()
            print(f"\n最新期数据（报告期: {latest.get('报告期')}）:")
            print(f"   所有字段: {list(latest.keys())}")

            # 检查关键字段
            print("\n🔍 关键字段值:")
            for key in ["报告期", "净资产收益率", "资产负债率", "营业收入", "净利润", "股东权益合计"]:
                value = latest.get(key)
                print(f"   {key}: {value} (类型: {type(value).__name__})")
        else:
            print("❌ 未获取到数据")
    except Exception as e:
        print(f"❌ 获取失败: {e}")
        import traceback

        traceback.print_exc()


asyncio.run(check_akshare_fields())
