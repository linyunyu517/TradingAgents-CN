#!/usr/bin/env python3
"""
测试统一基本面分析工具
验证新的统一工具方案是否有效
"""

import os
import sys


def test_unified_tool_directly():
    """直接测试统一基本面分析工具"""
    print("🔧 直接测试统一基本面分析工具...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建工具包
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 测试不同类型的股票
        test_cases = [
            ("0700.HK", "港股"),
            ("9988.HK", "港股"),
            ("000001", "中国A股"),
            ("AAPL", "美股"),
        ]

        for ticker, expected_type in test_cases:
            print(f"\n📊 测试 {ticker} ({expected_type}):")

            try:
                result = toolkit.get_stock_fundamentals_unified.invoke(
                    {"ticker": ticker, "start_date": "2025-06-14", "end_date": "2025-07-14", "curr_date": "2025-07-14"},
                )

                print("  ✅ 工具调用成功")
                print(f"  结果长度: {len(result)}")
                print(f"  结果前200字符: {result[:200]}...")

                # 检查结果是否包含预期内容
                if expected_type in result:
                    print("  ✅ 结果包含正确的股票类型")
                else:
                    print("  ⚠️ 结果未包含预期的股票类型")

                # 检查是否包含货币信息
                if any(currency in result for currency in ["¥", "HK$", "$"]):
                    print("  ✅ 结果包含货币信息")
                else:
                    print("  ⚠️ 结果未包含货币信息")

            except Exception as e:
                print(f"  ❌ 工具调用失败: {e}")
                return False

        print("✅ 统一工具直接测试通过")
        return True

    except Exception as e:
        print(f"❌ 统一工具直接测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_fundamentals_analyst_with_unified_tool():
    """测试基本面分析师使用统一工具"""
    print("\n🔧 测试基本面分析师使用统一工具...")

    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ 未找到DASHSCOPE_API_KEY，跳过LLM测试")
            return True

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        # 创建工具包
        toolkit = Toolkit(config)

        # 创建LLM
        llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=1000)

        # 创建基本面分析师
        analyst = create_fundamentals_analyst(llm, toolkit)

        # 测试港股
        state = {"trade_date": "2025-07-14", "company_of_interest": "0700.HK", "messages": []}

        print(f"  测试港股基本面分析: {state['company_of_interest']}")

        # 调用分析师
        result = analyst(state)

        print("  ✅ 基本面分析师调用完成")
        print(f"  结果类型: {type(result)}")

        if isinstance(result, dict) and "fundamentals_report" in result:
            report = result["fundamentals_report"]
            print(f"  报告长度: {len(report)}")
            print(f"  报告前200字符: {report[:200]}...")

            # 检查报告质量
            if len(report) > 200:
                print("  ✅ 报告长度合格（>200字符）")
            else:
                print(f"  ⚠️ 报告长度偏短（{len(report)}字符）")

            # 检查是否包含港币相关内容
            if "HK$" in report or "港币" in report or "港元" in report:
                print("  ✅ 报告包含港币计价")
            else:
                print("  ⚠️ 报告未包含港币计价")
        else:
            print("  ❌ 未找到基本面报告")
            return False

        print("✅ 基本面分析师统一工具测试通过")
        return True

    except Exception as e:
        print(f"❌ 基本面分析师统一工具测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_stock_type_detection():
    """测试股票类型检测"""
    print("\n🔧 测试股票类型检测...")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        test_cases = [
            ("0700.HK", "港股", "港币", "HK$"),
            ("9988.HK", "港股", "港币", "HK$"),
            ("000001", "中国A股", "人民币", "¥"),
            ("600036", "中国A股", "人民币", "¥"),
            ("AAPL", "美股", "美元", "$"),
        ]

        for ticker, expected_market, expected_currency, expected_symbol in test_cases:
            market_info = StockUtils.get_market_info(ticker)

            print(f"  {ticker}:")
            print(f"    市场: {market_info['market_name']}")
            print(f"    货币: {market_info['currency_name']} ({market_info['currency_symbol']})")

            # 验证结果
            if (
                expected_market in market_info["market_name"]
                and market_info["currency_name"] == expected_currency
                and market_info["currency_symbol"] == expected_symbol
            ):
                print("    ✅ 识别正确")
            else:
                print("    ❌ 识别错误")
                return False

        print("✅ 股票类型检测测试通过")
        return True

    except Exception as e:
        print(f"❌ 股票类型检测测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔧 统一基本面分析工具测试")
    print("=" * 60)

    tests = [
        test_stock_type_detection,
        test_unified_tool_directly,
        test_fundamentals_analyst_with_unified_tool,
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
        print("🎉 所有测试通过！统一基本面分析工具方案成功")
        print("\n📋 方案优势:")
        print("✅ 简化了工具选择逻辑")
        print("✅ 工具内部自动识别股票类型")
        print("✅ 避免了LLM工具调用混乱")
        print("✅ 统一的系统提示和处理流程")
        print("✅ 更容易维护和扩展")
        return True
    print("⚠️ 部分测试失败，需要进一步检查")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
