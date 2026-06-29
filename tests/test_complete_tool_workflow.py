#!/usr/bin/env python3
"""
测试完整的工具调用工作流程
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()


def test_deepseek_complete_workflow():
    """测试DeepSeek的完整工具调用工作流程"""
    print("🤖 测试DeepSeek完整工作流程")
    print("=" * 60)

    try:
        from langchain_core.messages import HumanMessage, ToolMessage
        from langchain_core.tools import BaseTool

        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 创建DeepSeek实例
        deepseek_llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=2000)

        # 创建模拟工具
        class MockChinaStockDataTool(BaseTool):
            name: str = "get_china_stock_data"
            description: str = "获取中国A股股票000002的市场数据和技术指标"

            def _run(self, query: str = "") -> str:
                return """# 000002 万科A 股票数据分析

## 📊 实时行情
- 股票名称: 万科A
- 当前价格: ¥6.56
- 涨跌幅: 0.61%
- 成交量: 934,783手

## 📈 技术指标
- 10日EMA: ¥6.45
- 50日SMA: ¥6.78
- 200日SMA: ¥7.12
- RSI: 42.5
- MACD: -0.08
- MACD信号线: -0.12
- 布林带上轨: ¥7.20
- 布林带中轨: ¥6.80
- 布林带下轨: ¥6.40
- ATR: 0.25"""

        tools = [MockChinaStockDataTool()]

        # 第一步：发送初始请求
        prompt = """请对中国A股股票000002进行详细的技术分析。

要求：
1. 首先调用get_china_stock_data工具获取数据
2. 然后基于获取的数据进行分析
3. 输出完整的技术分析报告"""

        print("📤 发送初始请求...")
        chain = deepseek_llm.bind_tools(tools)
        result1 = chain.invoke([HumanMessage(content=prompt)])

        print("📊 第一次响应:")
        print(f"   工具调用数量: {len(result1.tool_calls) if hasattr(result1, 'tool_calls') else 0}")
        print(f"   响应内容长度: {len(result1.content)}")
        print(f"   响应内容: {result1.content[:200]}...")

        if hasattr(result1, "tool_calls") and result1.tool_calls:
            print("\n🔧 执行工具调用...")

            # 模拟工具执行
            tool_messages = []
            for tool_call in result1.tool_calls:
                tool_name = tool_call.get("name")
                tool_id = tool_call.get("id")

                print(f"   执行工具: {tool_name}")

                # 执行工具
                tool = tools[0]  # 我们只有一个工具
                tool_result = tool._run("")

                # 创建工具消息
                tool_message = ToolMessage(content=tool_result, tool_call_id=tool_id)
                tool_messages.append(tool_message)

            # 第二步：发送工具结果，要求生成分析
            print("\n📤 发送工具结果，要求生成分析...")
            messages = [
                HumanMessage(content=prompt),
                result1,
                *tool_messages,
                HumanMessage(
                    content="现在请基于上述工具获取的数据，生成详细的技术分析报告。报告应该包含具体的数据分析和投资建议。",
                ),
            ]

            result2 = deepseek_llm.invoke(messages)

            print("📊 第二次响应:")
            print(f"   响应内容长度: {len(result2.content)}")
            print("   响应内容前500字符:")
            print("-" * 50)
            print(result2.content[:500])
            print("-" * 50)

            # 检查是否包含实际数据分析
            has_data = any(keyword in result2.content for keyword in ["¥6.56", "RSI", "MACD", "万科A", "42.5"])
            print(f"   包含实际数据: {'✅' if has_data else '❌'}")

            return result2
        print("❌ 没有工具调用")
        return result1

    except Exception as e:
        print(f"❌ DeepSeek测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_dashscope_react_agent():
    """测试百炼的ReAct Agent模式"""
    print("\n🌟 测试百炼ReAct Agent模式")
    print("=" * 60)

    try:
        from langchain.agents import AgentExecutor, create_react_agent
        from langchain_core.prompts import PromptTemplate
        from langchain_core.tools import BaseTool

        # 检查是否有百炼API密钥
        if not os.getenv("DASHSCOPE_API_KEY"):
            print("⚠️ 未找到DASHSCOPE_API_KEY，跳过百炼测试")
            return None

        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope

        # 创建百炼实例
        dashscope_llm = ChatDashScope(model="qwen-plus", temperature=0.1, max_tokens=2000)

        # 创建工具
        class MockChinaStockDataTool(BaseTool):
            name: str = "get_china_stock_data"
            description: str = "获取中国A股股票000002的市场数据和技术指标。直接调用，无需参数。"

            def _run(self, query: str = "") -> str:
                print("🔧 [工具执行] get_china_stock_data被调用")
                return """# 000002 万科A 股票数据分析

## 📊 实时行情
- 股票名称: 万科A
- 当前价格: ¥6.56
- 涨跌幅: 0.61%
- 成交量: 934,783手

## 📈 技术指标
- 10日EMA: ¥6.45
- 50日SMA: ¥6.78
- 200日SMA: ¥7.12
- RSI: 42.5
- MACD: -0.08
- MACD信号线: -0.12
- 布林带上轨: ¥7.20
- 布林带中轨: ¥6.80
- 布林带下轨: ¥6.40
- ATR: 0.25"""

        tools = [MockChinaStockDataTool()]

        # 创建ReAct Agent
        prompt_template = """请对中国A股股票000002进行详细的技术分析。

执行步骤：
1. 使用get_china_stock_data工具获取股票市场数据
2. 基于获取的真实数据进行深入的技术指标分析
3. 输出完整的技术分析报告内容

重要要求：
- 必须调用工具获取数据
- 必须输出完整的技术分析报告内容，不要只是描述报告已完成
- 报告必须基于工具获取的真实数据进行分析

你有以下工具可用:
{tools}

使用以下格式:

Question: 输入的问题
Thought: 你应该思考要做什么
Action: 要采取的行动，应该是[{tool_names}]之一
Action Input: 行动的输入
Observation: 行动的结果
... (这个Thought/Action/Action Input/Observation可以重复N次)
Thought: 我现在知道最终答案了
Final Answer: 对原始输入问题的最终答案

Question: {input}
{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(prompt_template)

        # 创建agent
        agent = create_react_agent(dashscope_llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=3)

        print("📤 执行ReAct Agent...")
        result = agent_executor.invoke({"input": "请对中国A股股票000002进行详细的技术分析"})

        print("📊 ReAct Agent结果:")
        print(f"   输出长度: {len(result['output'])}")
        print("   输出内容前500字符:")
        print("-" * 50)
        print(result["output"][:500])
        print("-" * 50)

        # 检查是否包含实际数据分析
        has_data = any(keyword in result["output"] for keyword in ["¥6.56", "RSI", "MACD", "万科A", "42.5"])
        print(f"   包含实际数据: {'✅' if has_data else '❌'}")

        return result

    except Exception as e:
        print(f"❌ 百炼ReAct Agent测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """主函数"""
    print("🔬 完整工具调用工作流程测试")
    print("=" * 80)

    # 测试DeepSeek
    deepseek_result = test_deepseek_complete_workflow()

    # 测试百炼ReAct Agent
    dashscope_result = test_dashscope_react_agent()

    # 总结
    print("\n📋 测试总结")
    print("=" * 60)

    if deepseek_result:
        has_data = any(keyword in deepseek_result.content for keyword in ["¥6.56", "RSI", "MACD", "万科A"])
        print(f"✅ DeepSeek: {'成功生成基于数据的分析' if has_data else '调用工具但分析不完整'}")
    else:
        print("❌ DeepSeek: 测试失败")

    if dashscope_result:
        has_data = any(keyword in dashscope_result["output"] for keyword in ["¥6.56", "RSI", "MACD", "万科A"])
        print(f"✅ 百炼ReAct: {'成功生成基于数据的分析' if has_data else '执行但分析不完整'}")
    else:
        print("❌ 百炼ReAct: 测试失败")

    print("\n🎯 测试完成！")


if __name__ == "__main__":
    main()
