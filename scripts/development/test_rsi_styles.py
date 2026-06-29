"""
测试不同风格的RSI计算

验证：
1. 国际标准 RSI14（EMA）
2. 中国风格 RSI6/12/24（中国式SMA）
3. 与 A 股数据源的 RSI 计算结果对比
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
import pandas as pd

from tradingagents.tools.analysis.indicators import add_all_indicators, rsi


def test_rsi_methods():
    """测试不同的RSI计算方法"""
    print("=" * 80)
    print("测试不同的RSI计算方法")
    print("=" * 80)

    # 创建测试数据
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close_prices = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame({"date": dates, "close": close_prices})

    print(f"\n📊 测试数据: {len(df)} 条记录")
    print(f"   价格范围: {df['close'].min():.2f} ~ {df['close'].max():.2f}")

    # 测试1: 国际标准 RSI14（EMA）
    print("\n" + "=" * 80)
    print("测试1: 国际标准 RSI14（EMA）")
    print("=" * 80)
    df["rsi_ema"] = rsi(df["close"], 14, method="ema")
    print(f"✅ RSI14 (EMA) 最新值: {df['rsi_ema'].iloc[-1]:.2f}")
    print(f"   前5个值: {df['rsi_ema'].tail(5).values}")

    # 测试2: 简单移动平均 RSI14（SMA）
    print("\n" + "=" * 80)
    print("测试2: 简单移动平均 RSI14（SMA）")
    print("=" * 80)
    df["rsi_sma"] = rsi(df["close"], 14, method="sma")
    print(f"✅ RSI14 (SMA) 最新值: {df['rsi_sma'].iloc[-1]:.2f}")
    print(f"   前5个值: {df['rsi_sma'].tail(5).values}")

    # 测试3: 中国式 RSI6/12/24
    print("\n" + "=" * 80)
    print("测试3: 中国式 RSI6/12/24（同花顺/通达信风格）")
    print("=" * 80)
    df["rsi6_china"] = rsi(df["close"], 6, method="china")
    df["rsi12_china"] = rsi(df["close"], 12, method="china")
    df["rsi24_china"] = rsi(df["close"], 24, method="china")
    print(f"✅ RSI6  (China) 最新值: {df['rsi6_china'].iloc[-1]:.2f}")
    print(f"✅ RSI12 (China) 最新值: {df['rsi12_china'].iloc[-1]:.2f}")
    print(f"✅ RSI24 (China) 最新值: {df['rsi24_china'].iloc[-1]:.2f}")

    # 测试4: 使用 add_all_indicators（国际标准）
    print("\n" + "=" * 80)
    print("测试4: add_all_indicators（国际标准）")
    print("=" * 80)
    df_int = df[["date", "close"]].copy()
    df_int = add_all_indicators(df_int, rsi_style="international")
    print(f"✅ 添加的指标列: {[col for col in df_int.columns if col not in ['date', 'close']]}")
    print(f"   RSI 最新值: {df_int['rsi'].iloc[-1]:.2f}")

    # 测试5: 使用 add_all_indicators（中国风格）
    print("\n" + "=" * 80)
    print("测试5: add_all_indicators（中国风格）")
    print("=" * 80)
    df_china = df[["date", "close"]].copy()
    df_china = add_all_indicators(df_china, rsi_style="china")
    print(f"✅ 添加的指标列: {[col for col in df_china.columns if col not in ['date', 'close']]}")
    print(f"   RSI6  最新值: {df_china['rsi6'].iloc[-1]:.2f}")
    print(f"   RSI12 最新值: {df_china['rsi12'].iloc[-1]:.2f}")
    print(f"   RSI24 最新值: {df_china['rsi24'].iloc[-1]:.2f}")
    print(f"   RSI14 最新值: {df_china['rsi14'].iloc[-1]:.2f}")
    print(f"   RSI (兼容) 最新值: {df_china['rsi'].iloc[-1]:.2f}")

    # 对比分析
    print("\n" + "=" * 80)
    print("对比分析")
    print("=" * 80)
    print(f"EMA vs SMA 差异: {abs(df['rsi_ema'].iloc[-1] - df['rsi_sma'].iloc[-1]):.2f}")
    print(f"China RSI6 vs RSI12 差异: {abs(df['rsi6_china'].iloc[-1] - df['rsi12_china'].iloc[-1]):.2f}")
    print(f"China RSI12 vs RSI24 差异: {abs(df['rsi12_china'].iloc[-1] - df['rsi24_china'].iloc[-1]):.2f}")

    return True


def test_a_stock_compatibility():
    """测试与 A 股数据源的兼容性"""
    print("\n" + "=" * 80)
    print("测试与 A 股数据源的兼容性")
    print("=" * 80)

    # 创建测试数据（模拟 A 股数据）
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close_prices = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame({"date": dates, "close": close_prices})

    # 方法1: 使用 add_all_indicators（中国风格）
    df1 = df.copy()
    df1 = add_all_indicators(df1, rsi_style="china")

    # 方法2: 手动计算（模拟 A 股数据源的计算方式）
    df2 = df.copy()
    delta = df2["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # RSI6
    avg_gain6 = gain.ewm(com=5, adjust=True).mean()
    avg_loss6 = loss.ewm(com=5, adjust=True).mean()
    rs6 = avg_gain6 / avg_loss6.replace(0, np.nan)
    df2["rsi6_manual"] = 100 - (100 / (1 + rs6))

    # RSI12
    avg_gain12 = gain.ewm(com=11, adjust=True).mean()
    avg_loss12 = loss.ewm(com=11, adjust=True).mean()
    rs12 = avg_gain12 / avg_loss12.replace(0, np.nan)
    df2["rsi12_manual"] = 100 - (100 / (1 + rs12))

    # RSI24
    avg_gain24 = gain.ewm(com=23, adjust=True).mean()
    avg_loss24 = loss.ewm(com=23, adjust=True).mean()
    rs24 = avg_gain24 / avg_loss24.replace(0, np.nan)
    df2["rsi24_manual"] = 100 - (100 / (1 + rs24))

    # 对比结果
    print("\n📊 RSI6 对比:")
    print(f"   add_all_indicators: {df1['rsi6'].iloc[-1]:.6f}")
    print(f"   手动计算:          {df2['rsi6_manual'].iloc[-1]:.6f}")
    print(f"   差异:              {abs(df1['rsi6'].iloc[-1] - df2['rsi6_manual'].iloc[-1]):.6f}")

    print("\n📊 RSI12 对比:")
    print(f"   add_all_indicators: {df1['rsi12'].iloc[-1]:.6f}")
    print(f"   手动计算:          {df2['rsi12_manual'].iloc[-1]:.6f}")
    print(f"   差异:              {abs(df1['rsi12'].iloc[-1] - df2['rsi12_manual'].iloc[-1]):.6f}")

    print("\n📊 RSI24 对比:")
    print(f"   add_all_indicators: {df1['rsi24'].iloc[-1]:.6f}")
    print(f"   手动计算:          {df2['rsi24_manual'].iloc[-1]:.6f}")
    print(f"   差异:              {abs(df1['rsi24'].iloc[-1] - df2['rsi24_manual'].iloc[-1]):.6f}")

    # 验证是否一致
    tolerance = 1e-6
    rsi6_match = abs(df1["rsi6"].iloc[-1] - df2["rsi6_manual"].iloc[-1]) < tolerance
    rsi12_match = abs(df1["rsi12"].iloc[-1] - df2["rsi12_manual"].iloc[-1]) < tolerance
    rsi24_match = abs(df1["rsi24"].iloc[-1] - df2["rsi24_manual"].iloc[-1]) < tolerance

    if rsi6_match and rsi12_match and rsi24_match:
        print(f"\n✅ 所有RSI计算结果一致！（误差 < {tolerance}）")
        return True
    print("\n❌ RSI计算结果不一致！")
    if not rsi6_match:
        print("   RSI6 不匹配")
    if not rsi12_match:
        print("   RSI12 不匹配")
    if not rsi24_match:
        print("   RSI24 不匹配")
    return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RSI 计算方法测试")
    print("=" * 80)

    try:
        # 测试1: 不同RSI计算方法
        test1_passed = test_rsi_methods()

        # 测试2: 与 A 股数据源的兼容性
        test2_passed = test_a_stock_compatibility()

        # 总结
        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)
        print(f"✅ 测试1（不同RSI方法）: {'通过' if test1_passed else '失败'}")
        print(f"✅ 测试2（A股兼容性）:   {'通过' if test2_passed else '失败'}")

        if test1_passed and test2_passed:
            print("\n🎉 所有测试通过！")
        else:
            print("\n❌ 部分测试失败！")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
