#!/usr/bin/env python3
"""
LLM技术面分析调试测试
专门诊断阿里百炼vs DeepSeek在技术面分析中的差异
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_dashscope_technical_analysis():
    """测试阿里百炼的技术面分析"""
    print("\n🔧 测试阿里百炼技术面分析")
    print("=" * 60)

    try:
        from langchain.schema import HumanMessage
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope

        # 创建阿里百炼模型
        llm = ChatDashScope(model="qwen-plus-latest", temperature=0.1, max_tokens=2000)

        print("✅ 阿里百炼模型创建成功")

        # 测试简单对话
        print("🔄 测试简单对话...")
        simple_messages = [HumanMessage(content="请简单介绍股票技术分析的概念，控制在100字以内。")]
        simple_response = llm.invoke(simple_messages)
        print(f"📊 简单对话响应长度: {len(simple_response.content)}字符")
        print(f"📋 简单对话内容: {simple_response.content[:200]}...")

        # 测试复杂技术分析prompt
        print("\n🔄 测试复杂技术分析prompt...")
        complex_prompt = """现在请基于以下股票数据，生成详细的技术分析报告。

要求：
1. 报告必须基于提供的数据进行分析
2. 包含具体的技术指标数值和专业分析
3. 提供明确的投资建议和风险提示
4. 报告长度不少于800字
5. 使用中文撰写

请分析股票600036的技术面情况，包括：
- 价格趋势分析
- 技术指标解读
- 支撑阻力位分析
- 成交量分析
- 投资建议

股票数据：
股票代码: 600036
股票名称: 招商银行
当前价格: ¥47.13
涨跌幅: -1.03%
成交量: 61.5万手
"""

        complex_messages = [HumanMessage(content=complex_prompt)]
        complex_response = llm.invoke(complex_messages)
        print(f"📊 复杂分析响应长度: {len(complex_response.content)}字符")
        print(f"📋 复杂分析内容: {complex_response.content[:300]}...")

        if len(complex_response.content) < 100:
            print("❌ 阿里百炼复杂分析响应过短")
            return False
        print("✅ 阿里百炼复杂分析响应正常")
        return True

    except Exception as e:
        print(f"❌ 阿里百炼测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_deepseek_technical_analysis():
    """测试DeepSeek的技术面分析"""
    print("\n🔧 测试DeepSeek技术面分析")
    print("=" * 60)

    try:
        from langchain.schema import HumanMessage

        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 创建DeepSeek模型
        llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=2000)

        print("✅ DeepSeek模型创建成功")

        # 测试简单对话
        print("🔄 测试简单对话...")
        simple_messages = [HumanMessage(content="请简单介绍股票技术分析的概念，控制在100字以内。")]
        simple_response = llm.invoke(simple_messages)
        print(f"📊 简单对话响应长度: {len(simple_response.content)}字符")
        print(f"📋 简单对话内容: {simple_response.content[:200]}...")

        # 测试复杂技术分析prompt
        print("\n🔄 测试复杂技术分析prompt...")
        complex_prompt = """现在请基于以下股票数据，生成详细的技术分析报告。

要求：
1. 报告必须基于提供的数据进行分析
2. 包含具体的技术指标数值和专业分析
3. 提供明确的投资建议和风险提示
4. 报告长度不少于800字
5. 使用中文撰写

请分析股票600036的技术面情况，包括：
- 价格趋势分析
- 技术指标解读
- 支撑阻力位分析
- 成交量分析
- 投资建议

股票数据：
股票代码: 600036
股票名称: 招商银行
当前价格: ¥47.13
涨跌幅: -1.03%
成交量: 61.5万手
"""

        complex_messages = [HumanMessage(content=complex_prompt)]
        complex_response = llm.invoke(complex_messages)
        print(f"📊 复杂分析响应长度: {len(complex_response.content)}字符")
        print(f"📋 复杂分析内容: {complex_response.content[:300]}...")

        if len(complex_response.content) < 100:
            print("❌ DeepSeek复杂分析响应过短")
            return False
        print("✅ DeepSeek复杂分析响应正常")
        return True

    except Exception as e:
        print(f"❌ DeepSeek测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_message_sequence_handling():
    """测试复杂消息序列处理"""
    print("\n🔧 测试复杂消息序列处理")
    print("=" * 60)

    try:
        from langchain.schema import AIMessage, HumanMessage, ToolMessage
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope

        # 创建阿里百炼模型
        llm = ChatDashScope(model="qwen-plus-latest", temperature=0.1, max_tokens=2000)

        print("✅ 阿里百炼模型创建成功")

        # 模拟复杂的消息序列（类似技术面分析中的情况）
        messages = [
            HumanMessage(content="请分析股票600036的技术面"),
            AIMessage(
                content="我需要获取股票数据来进行分析",
                tool_calls=[
                    {
                        "name": "get_china_stock_data",
                        "args": {"stock_code": "600036", "start_date": "2025-06-10", "end_date": "2025-07-10"},
                        "id": "call_1",
                    },
                ],
            ),
            ToolMessage(
                content="股票代码: 600036\n股票名称: 招商银行\n当前价格: ¥47.13\n涨跌幅: -1.03%\n成交量: 61.5万手",
                tool_call_id="call_1",
            ),
            HumanMessage(
                content="""现在请基于上述工具获取的数据，生成详细的技术分析报告。

要求：
1. 报告必须基于工具返回的真实数据进行分析
2. 包含具体的技术指标数值和专业分析
3. 提供明确的投资建议和风险提示
4. 报告长度不少于800字
5. 使用中文撰写

请分析股票600036的技术面情况，包括：
- 价格趋势分析
- 技术指标解读
- 支撑阻力位分析
- 成交量分析
- 投资建议""",
            ),
        ]

        print("🔄 测试复杂消息序列...")
        response = llm.invoke(messages)
        print(f"📊 复杂消息序列响应长度: {len(response.content)}字符")
        print(f"📋 复杂消息序列内容: {response.content[:300]}...")

        if len(response.content) < 100:
            print("❌ 阿里百炼复杂消息序列响应过短")
            return False
        print("✅ 阿里百炼复杂消息序列响应正常")
        return True

    except Exception as e:
        print(f"❌ 复杂消息序列测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_max_tokens_impact():
    """测试max_tokens参数的影响"""
    print("\n🔧 测试max_tokens参数影响")
    print("=" * 60)

    try:
        from langchain.schema import HumanMessage
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope

        prompt = """请生成一份详细的股票技术分析报告，要求不少于800字，包含：
1. 价格趋势分析
2. 技术指标解读
3. 支撑阻力位分析
4. 成交量分析
5. 投资建议

股票：招商银行(600036)
当前价格: ¥47.13
"""

        # 测试不同的max_tokens设置
        token_settings = [500, 1000, 2000, 4000]

        for max_tokens in token_settings:
            print(f"\n🔄 测试max_tokens={max_tokens}...")

            llm = ChatDashScope(model="qwen-plus-latest", temperature=0.1, max_tokens=max_tokens)

            messages = [HumanMessage(content=prompt)]
            response = llm.invoke(messages)

            print(f"📊 max_tokens={max_tokens}, 响应长度: {len(response.content)}字符")

            if len(response.content) < 100:
                print(f"❌ max_tokens={max_tokens}时响应过短")
            else:
                print(f"✅ max_tokens={max_tokens}时响应正常")

        return True

    except Exception as e:
        print(f"❌ max_tokens测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔍 LLM技术面分析调试测试")
    print("=" * 70)
    print("💡 调试目标:")
    print("   - 诊断阿里百炼技术面分析报告过短问题")
    print("   - 对比DeepSeek和阿里百炼的响应差异")
    print("   - 测试复杂消息序列处理")
    print("   - 分析max_tokens参数影响")
    print("=" * 70)

    # 运行所有测试
    tests = [
        ("阿里百炼技术面分析", test_dashscope_technical_analysis),
        ("DeepSeek技术面分析", test_deepseek_technical_analysis),
        ("复杂消息序列处理", test_message_sequence_handling),
        ("max_tokens参数影响", test_max_tokens_impact),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))

    # 总结
    print("\n📋 LLM技术面分析调试总结")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    total = len(results)
    print(f"\n📊 测试结果: {passed}/{total} 通过")

    print("\n💡 可能的解决方案:")
    print("   1. 调整阿里百炼的max_tokens参数")
    print("   2. 优化技术面分析的prompt设计")
    print("   3. 简化复杂消息序列")
    print("   4. 添加模型特定的处理逻辑")

    input("按回车键退出...")


if __name__ == "__main__":
    main()
