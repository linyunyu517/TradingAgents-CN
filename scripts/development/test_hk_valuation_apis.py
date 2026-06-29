"""
测试 AKShare 港股估值相关接口

重点测试：
1. stock_hk_valuation_baidu - 百度港股估值
2. stock_hk_indicator_eniu - 亿牛港股指标
3. stock_financial_hk_analysis_indicator_em - 东方财富港股财务分析指标
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def test_stock_hk_valuation_baidu():
    """测试百度港股估值接口"""
    print("=" * 80)
    print("测试 1: stock_hk_valuation_baidu (百度港股估值)")
    print("=" * 80)

    test_symbols = ["00005", "00700", "09988"]  # 汇丰控股、腾讯、阿里巴巴

    try:
        import akshare as ak

        for symbol in test_symbols:
            print(f"\n📊 测试股票: {symbol}")

            try:
                df = ak.stock_hk_valuation_baidu(symbol=symbol)

                if df is not None and not df.empty:
                    print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
                    print(f"   📋 列名: {list(df.columns)}")
                    print("   📈 最新数据:")
                    print(df.tail(3).to_string(index=False))
                else:
                    print("   ⚠️ 返回空数据")

            except Exception as e:
                print(f"   ❌ 调用失败: {e}")
                import traceback

                traceback.print_exc()

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_stock_hk_indicator_eniu():
    """测试亿牛港股指标接口"""
    print("\n" + "=" * 80)
    print("测试 2: stock_hk_indicator_eniu (亿牛港股指标)")
    print("=" * 80)

    test_symbols = ["00005", "00700", "09988"]

    try:
        import akshare as ak

        for symbol in test_symbols:
            print(f"\n📊 测试股票: {symbol}")

            try:
                df = ak.stock_hk_indicator_eniu(symbol=symbol)

                if df is not None and not df.empty:
                    print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
                    print(f"   📋 列名: {list(df.columns)}")
                    print("   📈 最新数据:")
                    print(df.tail(3).to_string(index=False))
                else:
                    print("   ⚠️ 返回空数据")

            except Exception as e:
                print(f"   ❌ 调用失败: {e}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_stock_financial_hk_analysis_indicator_em():
    """测试东方财富港股财务分析指标接口"""
    print("\n" + "=" * 80)
    print("测试 3: stock_financial_hk_analysis_indicator_em (东方财富港股财务分析指标)")
    print("=" * 80)

    test_symbols = ["01810", "00700", "09988"]  # 小米、腾讯、阿里巴巴

    try:
        import akshare as ak

        for symbol in test_symbols:
            print(f"\n📊 测试股票: {symbol}")

            try:
                df = ak.stock_financial_hk_analysis_indicator_em(symbol=symbol)

                if df is not None and not df.empty:
                    print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
                    print(f"   📋 列名: {list(df.columns)}")
                    print("   📈 最新数据:")
                    print(df.tail(1).to_string(index=False))

                    # 查找 PE、PB 相关字段
                    pe_pb_cols = [
                        col
                        for col in df.columns
                        if any(keyword in col.lower() for keyword in ["pe", "pb", "市盈", "市净", "ratio"])
                    ]
                    if pe_pb_cols:
                        print(f"\n   🔍 找到 PE/PB 相关字段: {pe_pb_cols}")
                        print("   📊 PE/PB 数据:")
                        print(df[pe_pb_cols].tail(1).to_string(index=False))
                else:
                    print("   ⚠️ 返回空数据")

            except Exception as e:
                print(f"   ❌ 调用失败: {e}")
                import traceback

                traceback.print_exc()

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_stock_hk_spot_em():
    """测试东方财富港股实时行情接口"""
    print("\n" + "=" * 80)
    print("测试 4: stock_hk_spot_em (东方财富港股实时行情)")
    print("=" * 80)

    try:
        import akshare as ak

        df = ak.stock_hk_spot_em()

        if df is not None and not df.empty:
            print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
            print(f"   📋 列名: {list(df.columns)}")

            # 查找汇丰控股
            test_symbol = "01810"  # 小米
            matched = df[df["代码"] == test_symbol]

            if not matched.empty:
                print(f"\n   📈 {test_symbol} 的数据:")
                row = matched.iloc[0]
                for col in df.columns:
                    print(f"     {col}: {row[col]}")

                # 查找 PE、PB 相关字段
                pe_pb_cols = [
                    col for col in df.columns if any(keyword in col for keyword in ["PE", "PB", "市盈", "市净", "估值"])
                ]
                if pe_pb_cols:
                    print(f"\n   🔍 找到 PE/PB 相关字段: {pe_pb_cols}")
            else:
                print(f"\n   ⚠️ 未找到 {test_symbol} 的数据")
        else:
            print("   ⚠️ 返回空数据")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("港股估值指标接口测试")
    print("=" * 80)

    # 测试 1: 百度港股估值
    test_stock_hk_valuation_baidu()

    # 测试 2: 亿牛港股指标
    test_stock_hk_indicator_eniu()

    # 测试 3: 东方财富港股财务分析指标
    test_stock_financial_hk_analysis_indicator_em()

    # 测试 4: 东方财富港股实时行情
    test_stock_hk_spot_em()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
