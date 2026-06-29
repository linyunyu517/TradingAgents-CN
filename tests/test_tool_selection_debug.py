#!/usr/bin/env python3
"""
调试工具选择问题 - 检查LLM实际看到的工具列表
"""

import sys


def test_llm_tool_binding():
    """测试LLM工具绑定时的实际工具列表"""
    print("🔧 测试LLM工具绑定...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        # 创建工具包
        toolkit = Toolkit(config)

        # 检查工具包中的所有工具
        print("\n📋 工具包中的所有工具:")
        all_tools = []
        for attr_name in dir(toolkit):
            if not attr_name.startswith("_") and callable(getattr(toolkit, attr_name)):
                attr = getattr(toolkit, attr_name)
                if hasattr(attr, "name"):
                    all_tools.append((attr_name, attr.name))
                    print(f"  {attr_name}: {attr.name}")

        # 检查港股相关工具
        hk_related_tools = [tool for tool in all_tools if "hk" in tool[0].lower() or "hk" in tool[1].lower()]
        print("\n🇭🇰 港股相关工具:")
        for attr_name, tool_name in hk_related_tools:
            print(f"  {attr_name}: {tool_name}")

        # 检查基本面相关工具
        fundamentals_tools = [
            tool for tool in all_tools if "fundamental" in tool[0].lower() or "fundamental" in tool[1].lower()
        ]
        print("\n📊 基本面相关工具:")
        for attr_name, tool_name in fundamentals_tools:
            print(f"  {attr_name}: {tool_name}")

        return True

    except Exception as e:
        print(f"❌ 工具绑定测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_tool_descriptions():
    """测试工具描述内容"""
    print("\n🔧 测试工具描述...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 检查关键工具的描述
        key_tools = ["get_hk_stock_data_unified", "get_fundamentals_openai", "get_china_stock_data"]

        for tool_name in key_tools:
            if hasattr(toolkit, tool_name):
                tool = getattr(toolkit, tool_name)
                print(f"\n📋 {tool_name}:")
                print(f"  名称: {getattr(tool, 'name', 'N/A')}")
                print(f"  描述: {getattr(tool, 'description', 'N/A')}")

                # 检查描述中是否提到港股
                desc = getattr(tool, "description", "")
                if "港股" in desc or "HK" in desc or "Hong Kong" in desc:
                    print("  ✅ 描述中包含港股相关内容")
                else:
                    print("  ⚠️ 描述中不包含港股相关内容")

        return True

    except Exception as e:
        print(f"❌ 工具描述测试失败: {e}")
        return False


def test_fundamentals_analyst_tool_selection():
    """测试基本面分析师的实际工具选择"""
    print("\n🔧 测试基本面分析师工具选择...")

    try:
        # 模拟基本面分析师的工具选择逻辑
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.utils.stock_utils import StockUtils

        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 测试港股
        ticker = "0700.HK"
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info["is_china"]
        is_hk = market_info["is_hk"]
        is_us = market_info["is_us"]

        print(f"\n📊 股票: {ticker}")
        print(f"  市场信息: {market_info['market_name']}")
        print(f"  is_china: {is_china}")
        print(f"  is_hk: {is_hk}")
        print(f"  is_us: {is_us}")

        # 模拟工具选择逻辑
        if toolkit.config["online_tools"]:
            if is_china:
                tools = [toolkit.get_china_stock_data, toolkit.get_china_fundamentals]
                print(f"  选择的工具（A股）: {[tool.name for tool in tools]}")
            elif is_hk:
                tools = [toolkit.get_hk_stock_data_unified]
                print(f"  选择的工具（港股）: {[tool.name for tool in tools]}")
            else:
                tools = [toolkit.get_fundamentals_openai]
                print(f"  选择的工具（美股）: {[tool.name for tool in tools]}")

        # 检查是否有工具名称冲突
        tool_names = [tool.name for tool in tools]
        print(f"  工具名称列表: {tool_names}")

        # 检查工具描述
        for tool in tools:
            print(f"  工具 {tool.name} 描述: {tool.description[:100]}...")

        return True

    except Exception as e:
        print(f"❌ 基本面分析师工具选择测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🔧 工具选择调试测试")
    print("=" * 60)

    tests = [
        test_llm_tool_binding,
        test_tool_descriptions,
        test_fundamentals_analyst_tool_selection,
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
