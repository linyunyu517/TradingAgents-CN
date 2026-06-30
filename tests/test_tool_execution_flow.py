#!/usr/bin/env python3
"""
测试工具调用执行流程
验证ToolNode如何处理工具调用并返回结果
"""

import sys

sys.path.append(".")


from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_utils import Toolkit


def test_tool_execution_flow():
    """测试工具执行流程"""
    print("📊 测试工具调用执行流程")
    print("=" * 50)

    try:
        # 创建工具包
        print("1. 创建工具包...")
        toolkit = Toolkit()
        print("   ✅ 工具包创建成功")

        # 创建ToolNode
        print("2. 创建ToolNode...")
        tool_node = ToolNode([toolkit.get_stock_fundamentals_unified])
        print("   ✅ ToolNode创建成功")

        # 模拟一个带有tool_calls的AIMessage
        print("3. 创建模拟AIMessage...")
        ai_message = AIMessage(
            content="我需要调用工具获取基本面数据",
            tool_calls=[
                {
                    "name": "get_stock_fundamentals_unified",
                    "args": {"ticker": "000858", "start_date": "2024-01-01", "end_date": "2024-12-31"},
                    "id": "call_123",
                },
            ],
        )

        print(f"   - AIMessage内容: {ai_message.content}")
        print(f"   - 工具调用: {ai_message.tool_calls}")

        # 模拟状态
        state = {"messages": [ai_message]}

        print("\n4. 执行ToolNode...")
        result = tool_node.invoke(state)

        print(f"   - ToolNode返回类型: {type(result)}")
        print(f"   - 返回结构: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")

        if "messages" in result:
            print(f"   - 返回消息数量: {len(result['messages'])}")

            for i, msg in enumerate(result["messages"]):
                print(f"\n   消息{i + 1}:")
                print(f"     - 类型: {type(msg).__name__}")

                if hasattr(msg, "tool_call_id"):
                    print(f"     - tool_call_id: {msg.tool_call_id}")

                if hasattr(msg, "content"):
                    content = str(msg.content)
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    print(f"     - content长度: {len(content)} 字符")
                    print(f"     - content预览: {content_preview}")

                    # 检查是否包含实际数据
                    has_data = any(keyword in content for keyword in ["股票", "财务", "营收", "利润", "资产"])
                    print(f"     - 包含财务数据: {'✅' if has_data else '❌'}")

        print("\n5. 分析工具执行结果...")

        # 检查是否正常执行
        if "messages" in result and len(result["messages"]) > 0:
            tool_message = result["messages"][0]
            if isinstance(tool_message, ToolMessage):
                print("   ✅ 工具正常执行，返回了ToolMessage")
                print(f"   ✅ ToolMessage的tool_call_id: {tool_message.tool_call_id}")
                print("   ✅ 这个ToolMessage会被添加到消息历史中")
                print("   ✅ 然后系统会返回到分析师节点处理数据")
            else:
                print(f"   ❌ 返回的不是ToolMessage，而是: {type(tool_message)}")
        else:
            print("   ❌ 没有返回消息")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_tool_execution_flow()
