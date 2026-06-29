#!/usr/bin/env python3
"""
调试基本面分析师的工具选择问题
"""

import sys


def test_fundamentals_analyst_directly():
    """直接测试基本面分析师函数"""
    print("🔧 直接测试基本面分析师...")

    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        # 创建工具包
        toolkit = Toolkit(config)

        # 创建LLM（模拟）
        class MockLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                class MockResult:
                    def __init__(self):
                        self.tool_calls = []
                        self.content = "模拟分析结果"

                return MockResult()

        llm = MockLLM()

        # 创建基本面分析师
        analyst = create_fundamentals_analyst(llm, toolkit)

        # 模拟状态
        state = {"trade_date": "2025-07-14", "company_of_interest": "0700.HK", "messages": []}

        print(f"  测试港股: {state['company_of_interest']}")
        print("  调用基本面分析师...")

        # 调用分析师（这会触发工具选择逻辑）
        result = analyst(state)

        print("  ✅ 基本面分析师调用完成")
        print(f"  结果类型: {type(result)}")

        return True

    except Exception as e:
        print(f"❌ 直接测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_stock_utils_import():
    """测试StockUtils导入和功能"""
    print("\n🔧 测试StockUtils导入...")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        # 测试港股识别
        ticker = "0700.HK"
        market_info = StockUtils.get_market_info(ticker)

        print(f"  股票: {ticker}")
        print(f"  市场信息: {market_info}")
        print(f"  是否港股: {market_info['is_hk']}")
        print(f"  是否A股: {market_info['is_china']}")
        print(f"  是否美股: {market_info['is_us']}")

        if market_info["is_hk"]:
            print("  ✅ StockUtils正确识别港股")
            return True
        print("  ❌ StockUtils未能识别港股")
        return False

    except Exception as e:
        print(f"❌ StockUtils测试失败: {e}")
        return False


def test_toolkit_hk_tools():
    """测试工具包中的港股工具"""
    print("\n🔧 测试工具包港股工具...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 检查港股工具是否存在
        hk_tools = ["get_hk_stock_data_unified", "get_china_stock_data", "get_fundamentals_openai"]

        for tool_name in hk_tools:
            has_tool = hasattr(toolkit, tool_name)
            print(f"  {tool_name}: {'✅' if has_tool else '❌'}")

            if has_tool:
                tool = getattr(toolkit, tool_name)
                print(f"    工具类型: {type(tool)}")
                print(f"    工具名称: {getattr(tool, 'name', 'N/A')}")

        return True

    except Exception as e:
        print(f"❌ 工具包测试失败: {e}")
        return False


def test_import_paths():
    """测试导入路径"""
    print("\n🔧 测试导入路径...")

    imports_to_test = [
        "tradingagents.agents.analysts.fundamentals_analyst",
        "tradingagents.utils.stock_utils",
        "tradingagents.agents.utils.agent_utils",
        "tradingagents.default_config",
    ]

    for import_path in imports_to_test:
        try:
            __import__(import_path)
            print(f"  {import_path}: ✅")
        except Exception as e:
            print(f"  {import_path}: ❌ - {e}")
            return False

    return True


def main():
    """主测试函数"""
    print("🔧 基本面分析师调试测试")
    print("=" * 60)

    tests = [
        test_import_paths,
        test_stock_utils_import,
        test_toolkit_hk_tools,
        test_fundamentals_analyst_directly,
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
        print("🎉 所有测试通过！")
        return True
    print("⚠️ 部分测试失败，需要进一步检查")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
