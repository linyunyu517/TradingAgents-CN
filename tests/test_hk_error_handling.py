#!/usr/bin/env python3
"""
测试港股数据获取错误处理
验证在部分数据获取失败时的优雅降级处理
"""

import sys


def test_hk_data_error_handling():
    """测试港股数据获取错误处理"""
    print("🔧 测试港股数据获取错误处理...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建工具包
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 测试港股统一基本面工具
        test_cases = [
            "0700.HK",  # 腾讯
            "9988.HK",  # 阿里巴巴
            "3690.HK",  # 美团
        ]

        for ticker in test_cases:
            print(f"\n📊 测试 {ticker}:")

            try:
                result = toolkit.get_stock_fundamentals_unified.invoke(
                    {"ticker": ticker, "start_date": "2025-06-14", "end_date": "2025-07-14", "curr_date": "2025-07-14"},
                )

                print("  ✅ 工具调用成功")
                print(f"  结果长度: {len(result)}")

                # 检查结果质量
                if len(result) > 200:
                    print("  ✅ 结果长度合格（>200字符）")
                else:
                    print(f"  ⚠️ 结果长度偏短（{len(result)}字符）")

                # 检查是否包含港股相关内容
                if any(keyword in result for keyword in ["港股", "HK$", "港币", "香港交易所"]):
                    print("  ✅ 结果包含港股相关信息")
                else:
                    print("  ⚠️ 结果未包含港股相关信息")

                # 检查错误处理
                if "❌" in result:
                    if "备用" in result or "建议" in result:
                        print("  ✅ 包含优雅的错误处理和建议")
                    else:
                        print("  ⚠️ 错误处理可能不够完善")
                else:
                    print("  ✅ 数据获取成功，无错误")

                print(f"  结果前300字符: {result[:300]}...")

            except Exception as e:
                print(f"  ❌ 工具调用失败: {e}")
                return False

        print("✅ 港股数据获取错误处理测试通过")
        return True

    except Exception as e:
        print(f"❌ 港股数据获取错误处理测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_akshare_error_recovery():
    """测试AKShare错误恢复机制"""
    print("\n🔧 测试AKShare错误恢复机制...")

    try:
        # 创建模拟数据（使用正确的日期格式）
        import datetime

        import pandas as pd
        from tradingagents.dataflows.akshare_utils import format_hk_stock_data_akshare

        test_data = pd.DataFrame(
            {
                "Date": [
                    datetime.datetime(2025, 7, 10),
                    datetime.datetime(2025, 7, 11),
                    datetime.datetime(2025, 7, 12),
                ],
                "Open": [100.0, 101.0, 102.0],
                "High": [105.0, 106.0, 107.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [104.0, 105.0, 106.0],
                "Volume": [1000000, 1100000, 1200000],
            },
        )

        # 测试格式化函数的错误处理
        symbol = "0700.HK"
        start_date = "2025-07-10"
        end_date = "2025-07-12"

        print(f"  测试格式化港股数据: {symbol}")

        result = format_hk_stock_data_akshare(symbol, test_data, start_date, end_date)

        if result and len(result) > 100:
            print(f"  ✅ 格式化成功，长度: {len(result)}")

            # 检查是否包含必要信息
            required_info = ["港股", "HK$", "代码", "价格"]
            missing_info = [info for info in required_info if info not in result]

            if not missing_info:
                print("  ✅ 包含所有必要信息")
            else:
                print(f"  ⚠️ 缺少信息: {missing_info}")

            # 检查错误处理
            if "获取失败" in result or "❌" in result:
                if "默认" in result or "备用" in result:
                    print("  ✅ 包含优雅的错误处理")
                else:
                    print("  ⚠️ 错误处理可能不够完善")
            else:
                print("  ✅ 数据处理成功，无错误")

            return True
        print("  ❌ 格式化失败或结果太短")
        return False

    except Exception as e:
        print(f"❌ AKShare错误恢复机制测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_hk_fallback_mechanisms():
    """测试港股备用机制"""
    print("\n🔧 测试港股备用机制...")

    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified, get_hk_stock_info_unified

        symbol = "0700.HK"
        start_date = "2025-06-14"
        end_date = "2025-07-14"

        print(f"  测试港股数据统一接口: {symbol}")

        # 测试数据获取
        data_result = get_hk_stock_data_unified(symbol, start_date, end_date)

        if data_result:
            print(f"  ✅ 数据接口调用成功，长度: {len(data_result)}")

            # 检查数据源标识
            if "AKShare" in data_result:
                print("  ✅ 使用AKShare作为主要数据源")
            elif "Yahoo Finance" in data_result:
                print("  ✅ 使用Yahoo Finance作为备用数据源")
            elif "FINNHUB" in data_result:
                print("  ✅ 使用FINNHUB作为备用数据源")
            else:
                print("  ⚠️ 未明确标识数据源")
        else:
            print("  ❌ 数据接口调用失败")
            return False

        # 测试信息获取
        print(f"  测试港股信息统一接口: {symbol}")

        info_result = get_hk_stock_info_unified(symbol)

        if info_result and isinstance(info_result, dict):
            print("  ✅ 信息接口调用成功")
            print(f"    股票名称: {info_result.get('name', 'N/A')}")
            print(f"    货币: {info_result.get('currency', 'N/A')}")
            print(f"    交易所: {info_result.get('exchange', 'N/A')}")
            print(f"    数据源: {info_result.get('source', 'N/A')}")

            # 验证港股特有信息
            if info_result.get("currency") == "HKD" and info_result.get("exchange") == "HKG":
                print("  ✅ 港股信息正确")
            else:
                print("  ⚠️ 港股信息可能不完整")
        else:
            print("  ❌ 信息接口调用失败")
            return False

        print("✅ 港股备用机制测试通过")
        return True

    except Exception as e:
        print(f"❌ 港股备用机制测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🔧 港股数据获取错误处理测试")
    print("=" * 60)

    tests = [
        test_hk_data_error_handling,
        test_akshare_error_recovery,
        test_hk_fallback_mechanisms,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ 测试失败: {test.__name__}")
        except Exception as e:
            print(f"❌ 测试异常: {test.__name__} - {e}")

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！港股错误处理改进成功")
        print("\n📋 改进内容:")
        print("✅ 改进了AKShare港股信息获取的错误处理")
        print("✅ 添加了统一基本面工具的多重备用方案")
        print("✅ 实现了优雅降级机制")
        print("✅ 提供了有用的错误信息和建议")
        print("✅ 确保在部分数据失败时仍能提供基础信息")

        print("\n🚀 处理流程:")
        print("1️⃣ 尝试AKShare获取完整港股数据")
        print("2️⃣ 如果部分失败，使用默认信息继续处理")
        print("3️⃣ 如果完全失败，尝试Yahoo Finance备用")
        print("4️⃣ 最终备用：提供基础信息和建议")

        return True
    print("⚠️ 部分测试失败，需要进一步检查")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
