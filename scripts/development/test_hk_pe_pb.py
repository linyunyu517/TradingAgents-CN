"""
测试 AKShare 港股数据接口能否获取 PE、PB 等估值指标

测试目标：
1. 查看 stock_hk_spot() 返回哪些字段
2. 查看是否包含 PE、PB、市盈率、市净率等估值指标
3. 测试其他可能的 AKShare 港股接口
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def test_akshare_hk_spot():
    """测试 AKShare 港股实时行情接口"""
    print("=" * 80)
    print("测试 1: AKShare stock_hk_spot() 接口")
    print("=" * 80)

    try:
        import akshare as ak

        # 获取港股实时行情
        df = ak.stock_hk_spot()

        print(f"\n✅ 成功获取数据，共 {len(df)} 条记录")
        print("\n📊 数据列名:")
        for i, col in enumerate(df.columns, 1):
            print(f"  {i}. {col}")

        # 查找汇丰控股 (00005)
        test_symbol = "00005"
        matched = df[df["代码"] == test_symbol]

        if not matched.empty:
            print(f"\n📈 {test_symbol} 的数据:")
            row = matched.iloc[0]
            for col in df.columns:
                print(f"  {col}: {row[col]}")
        else:
            print(f"\n⚠️ 未找到 {test_symbol} 的数据")
            print("\n前5条数据示例:")
            print(df.head())

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_akshare_hk_valuation():
    """测试 AKShare 港股估值相关接口"""
    print("\n" + "=" * 80)
    print("测试 2: 查找 AKShare 港股估值相关接口")
    print("=" * 80)

    try:
        import akshare as ak

        # 列出所有包含 'hk' 和 'valuation' 或 'pe' 或 'pb' 的接口
        all_functions = dir(ak)
        hk_functions = [f for f in all_functions if "hk" in f.lower()]

        print(f"\n📋 AKShare 中包含 'hk' 的接口 (共 {len(hk_functions)} 个):")
        for func in hk_functions:
            print(f"  - {func}")

        # 查找估值相关的接口
        valuation_keywords = ["valuation", "pe", "pb", "ratio", "indicator", "fundamental"]
        print(f"\n🔍 查找估值相关接口 (关键词: {valuation_keywords}):")

        for keyword in valuation_keywords:
            matching = [f for f in all_functions if keyword in f.lower()]
            if matching:
                print(f"\n  包含 '{keyword}' 的接口:")
                for func in matching:
                    print(f"    - {func}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_akshare_hk_individual_stock():
    """测试 AKShare 港股个股相关接口"""
    print("\n" + "=" * 80)
    print("测试 3: 测试 AKShare 港股个股接口")
    print("=" * 80)

    test_symbol = "00005"

    # 测试可能的接口
    test_functions = [
        ("stock_hk_daily", {"symbol": test_symbol, "adjust": ""}),
        (
            "stock_hk_hist",
            {"symbol": test_symbol, "period": "daily", "start_date": "20241101", "end_date": "20241109", "adjust": ""},
        ),
    ]

    try:
        import akshare as ak

        for func_name, kwargs in test_functions:
            print(f"\n📊 测试接口: {func_name}")
            print(f"   参数: {kwargs}")

            try:
                if hasattr(ak, func_name):
                    func = getattr(ak, func_name)
                    df = func(**kwargs)

                    if df is not None and not df.empty:
                        print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
                        print(f"   📋 列名: {list(df.columns)}")
                        print("   📈 最新数据:")
                        print(df.tail(1).to_string(index=False))
                    else:
                        print("   ⚠️ 返回空数据")
                else:
                    print("   ⚠️ 接口不存在")

            except Exception as e:
                print(f"   ❌ 调用失败: {e}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_tushare_hk():
    """测试 Tushare 港股接口"""
    print("\n" + "=" * 80)
    print("测试 4: 测试 Tushare 港股接口")
    print("=" * 80)

    try:
        import tushare as ts

        from tradingagents.config import get_config

        config = get_config()
        tushare_token = config.get("tushare_token")

        if not tushare_token:
            print("⚠️ 未配置 Tushare Token，跳过测试")
            return

        ts.set_token(tushare_token)
        pro = ts.pro_api()

        # 测试港股基本信息
        print("\n📊 测试 hk_basic 接口:")
        try:
            df = pro.hk_basic(ts_code="00005.HK")
            if df is not None and not df.empty:
                print("   ✅ 成功获取数据")
                print(f"   📋 列名: {list(df.columns)}")
                print("   📈 数据:")
                print(df.to_string(index=False))
            else:
                print("   ⚠️ 返回空数据")
        except Exception as e:
            print(f"   ❌ 调用失败: {e}")

        # 测试港股日线行情
        print("\n📊 测试 hk_daily 接口:")
        try:
            df = pro.hk_daily(ts_code="00005.HK", start_date="20241101", end_date="20241109")
            if df is not None and not df.empty:
                print(f"   ✅ 成功获取数据，共 {len(df)} 条记录")
                print(f"   📋 列名: {list(df.columns)}")
                print("   📈 最新数据:")
                print(df.head(1).to_string(index=False))
            else:
                print("   ⚠️ 返回空数据")
        except Exception as e:
            print(f"   ❌ 调用失败: {e}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("港股 PE、PB 等估值指标数据源测试")
    print("=" * 80)

    # 测试 1: AKShare 实时行情
    test_akshare_hk_spot()

    # 测试 2: 查找估值相关接口
    test_akshare_hk_valuation()

    # 测试 3: 个股接口
    test_akshare_hk_individual_stock()

    # 测试 4: Tushare 港股接口
    test_tushare_hk()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
