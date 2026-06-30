"""
测试脚本：验证 default_base_url 修复是否生效
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main():
    print("=" * 80)
    print("🧪 测试：验证 default_base_url 修复")
    print("=" * 80)

    # 1. 测试 create_llm_by_provider 函数
    print("\n📊 1. 测试 create_llm_by_provider 函数")
    print("-" * 80)

    from tradingagents.graph.trading_graph import create_llm_by_provider

    # 测试参数
    provider = "dashscope"
    model = "qwen-turbo"
    backend_url = "https://dashscope.aliyuncs.com/api/v2"  # 自定义 URL
    temperature = 0.1
    max_tokens = 2000
    timeout = 60

    print("\n测试参数：")
    print(f"  provider: {provider}")
    print(f"  model: {model}")
    print(f"  backend_url: {backend_url}")

    try:
        llm = create_llm_by_provider(
            provider=provider,
            model=model,
            backend_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        print("\n✅ LLM 实例创建成功")
        print(f"   类型: {type(llm).__name__}")

        # 检查 base_url
        if hasattr(llm, "openai_api_base"):
            actual_url = llm.openai_api_base
            print(f"   base_url: {actual_url}")

            if actual_url == backend_url:
                print("\n🎯 ✅ base_url 正确！自定义 URL 已生效")
            else:
                print("\n❌ base_url 不正确！")
                print(f"   期望: {backend_url}")
                print(f"   实际: {actual_url}")
        else:
            print("   ⚠️ LLM 实例没有 openai_api_base 属性")

    except Exception as e:
        print(f"\n❌ LLM 实例创建失败: {e}")
        import traceback

        traceback.print_exc()

    # 2. 测试完整的分析流程
    print("\n\n📊 2. 测试完整的分析配置流程")
    print("-" * 80)

    from app.services.simple_analysis_service import create_analysis_config

    try:
        config = create_analysis_config(
            research_depth="标准",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A股",
        )

        print("\n✅ 配置创建成功")
        print(f"   backend_url: {config.get('backend_url')}")

        expected_url = "https://dashscope.aliyuncs.com/api/v2"
        actual_url = config.get("backend_url")

        if actual_url == expected_url:
            print("\n🎯 ✅ backend_url 正确！厂家的 default_base_url 已生效")
        else:
            print("\n⚠️ backend_url 与期望不符")
            print(f"   期望: {expected_url}")
            print(f"   实际: {actual_url}")

    except Exception as e:
        print(f"\n❌ 配置创建失败: {e}")
        import traceback

        traceback.print_exc()

    # 3. 测试 TradingAgentsGraph 初始化
    print("\n\n📊 3. 测试 TradingAgentsGraph 初始化")
    print("-" * 80)

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "llm_provider": "dashscope",
                "deep_think_llm": "qwen-plus",
                "quick_think_llm": "qwen-turbo",
                "backend_url": "https://dashscope.aliyuncs.com/api/v2",  # 自定义 URL
                "max_debate_rounds": 1,
                "max_risk_discuss_rounds": 1,
                "online_tools": False,  # 关闭在线工具以加快测试
                "memory_enabled": False,  # 关闭记忆以加快测试
            },
        )

        print("\n创建 TradingAgentsGraph...")
        print(f"  backend_url: {config['backend_url']}")

        graph = TradingAgentsGraph(selected_analysts=["market", "fundamentals"], debug=True, config=config)

        print("\n✅ TradingAgentsGraph 创建成功")
        print(f"   quick_thinking_llm 类型: {type(graph.quick_thinking_llm).__name__}")
        print(f"   deep_thinking_llm 类型: {type(graph.deep_thinking_llm).__name__}")

        # 检查 LLM 的 base_url
        if hasattr(graph.quick_thinking_llm, "openai_api_base"):
            quick_url = graph.quick_thinking_llm.openai_api_base
            print(f"   quick_thinking_llm base_url: {quick_url}")

            if quick_url == config["backend_url"]:
                print("\n🎯 ✅ quick_thinking_llm 的 base_url 正确！")
            else:
                print("\n❌ quick_thinking_llm 的 base_url 不正确！")
                print(f"   期望: {config['backend_url']}")
                print(f"   实际: {quick_url}")

        if hasattr(graph.deep_thinking_llm, "openai_api_base"):
            deep_url = graph.deep_thinking_llm.openai_api_base
            print(f"   deep_thinking_llm base_url: {deep_url}")

            if deep_url == config["backend_url"]:
                print("\n🎯 ✅ deep_thinking_llm 的 base_url 正确！")
            else:
                print("\n❌ deep_thinking_llm 的 base_url 不正确！")
                print(f"   期望: {config['backend_url']}")
                print(f"   实际: {deep_url}")

    except Exception as e:
        print(f"\n❌ TradingAgentsGraph 创建失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)

    print("\n💡 总结：")
    print("如果所有测试都通过，说明修复已生效。")
    print("现在在 Web 界面修改厂家的 default_base_url 后，分析时会使用新的 URL。")


if __name__ == "__main__":
    main()
