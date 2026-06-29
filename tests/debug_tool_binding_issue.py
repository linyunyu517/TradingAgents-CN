#!/usr/bin/env python3
"""
调试工具绑定问题
验证LLM是否能访问未绑定的工具
"""

import os
import sys


def test_tool_isolation():
    """测试工具隔离机制"""
    print("🔧 测试工具隔离机制...")

    try:
        from langchain_core.messages import HumanMessage

        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ 未找到DASHSCOPE_API_KEY，跳过测试")
            return True

        # 创建工具包
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 创建LLM
        llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=200)

        print("\n📋 工具包中的所有工具:")
        all_tools = []
        for attr_name in dir(toolkit):
            if not attr_name.startswith("_") and callable(getattr(toolkit, attr_name)):
                attr = getattr(toolkit, attr_name)
                if hasattr(attr, "name"):
                    all_tools.append(attr.name)
                    print(f"  - {attr.name}")

        print("\n🔧 测试1: 只绑定港股工具")
        hk_tools = [toolkit.get_hk_stock_data_unified]
        llm_hk = llm.bind_tools(hk_tools)

        print(f"  绑定的工具: {[tool.name for tool in hk_tools]}")

        # 测试是否能调用其他工具
        test_message = HumanMessage(content="请调用get_fundamentals_openai工具获取0700.HK的数据")

        try:
            response = llm_hk.invoke([test_message])
            print(f"  响应类型: {type(response)}")
            print(f"  工具调用数量: {len(getattr(response, 'tool_calls', []))}")

            if hasattr(response, "tool_calls") and response.tool_calls:
                called_tools = [call.get("name", "unknown") for call in response.tool_calls]
                print(f"  实际调用的工具: {called_tools}")

                # 检查是否调用了未绑定的工具
                unexpected_tools = [tool for tool in called_tools if tool not in [t.name for t in hk_tools]]
                if unexpected_tools:
                    print(f"  ❌ 调用了未绑定的工具: {unexpected_tools}")
                    return False
                print("  ✅ 只调用了绑定的工具")
            else:
                print("  ℹ️ 没有工具调用")

        except Exception as e:
            print(f"  ❌ 调用失败: {e}")
            return False

        print("\n🔧 测试2: 创建新的LLM实例")
        llm2 = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=200)

        china_tools = [toolkit.get_china_stock_data]
        llm2_china = llm2.bind_tools(china_tools)

        print(f"  绑定的工具: {[tool.name for tool in china_tools]}")

        test_message2 = HumanMessage(content="请调用get_hk_stock_data_unified工具获取0700.HK的数据")

        try:
            response2 = llm2_china.invoke([test_message2])
            print(f"  响应类型: {type(response2)}")
            print(f"  工具调用数量: {len(getattr(response2, 'tool_calls', []))}")

            if hasattr(response2, "tool_calls") and response2.tool_calls:
                called_tools2 = [call.get("name", "unknown") for call in response2.tool_calls]
                print(f"  实际调用的工具: {called_tools2}")

                # 检查是否调用了未绑定的工具
                unexpected_tools2 = [tool for tool in called_tools2 if tool not in [t.name for t in china_tools]]
                if unexpected_tools2:
                    print(f"  ❌ 调用了未绑定的工具: {unexpected_tools2}")
                    return False
                print("  ✅ 只调用了绑定的工具")
            else:
                print("  ℹ️ 没有工具调用")

        except Exception as e:
            print(f"  ❌ 调用失败: {e}")
            return False

        print("\n✅ 工具隔离测试完成")
        return True

    except Exception as e:
        print(f"❌ 工具隔离测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_llm_instance_reuse():
    """测试LLM实例复用问题"""
    print("\n🔧 测试LLM实例复用...")

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        # 创建工具包
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 检查是否存在全局LLM实例
        print("  检查LLM实例创建...")

        llm1 = ChatDashScopeOpenAI(model="qwen-turbo")
        llm2 = ChatDashScopeOpenAI(model="qwen-turbo")

        print(f"  LLM1 ID: {id(llm1)}")
        print(f"  LLM2 ID: {id(llm2)}")
        print(f"  是否为同一实例: {llm1 is llm2}")

        # 检查工具绑定状态
        tools1 = [toolkit.get_hk_stock_data_unified]
        tools2 = [toolkit.get_china_stock_data]

        llm1_with_tools = llm1.bind_tools(tools1)
        llm2_with_tools = llm2.bind_tools(tools2)

        print(f"  LLM1绑定工具: {[t.name for t in tools1]}")
        print(f"  LLM2绑定工具: {[t.name for t in tools2]}")

        # 检查绑定后的实例
        print(f"  LLM1绑定后ID: {id(llm1_with_tools)}")
        print(f"  LLM2绑定后ID: {id(llm2_with_tools)}")

        return True

    except Exception as e:
        print(f"❌ LLM实例复用测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔧 工具绑定问题调试")
    print("=" * 60)

    tests = [
        test_llm_instance_reuse,
        test_tool_isolation,
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
