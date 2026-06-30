#!/usr/bin/env python3
"""
阿里百炼工具调用测试 - Agent友好版本
专门为agent执行优化，避免闪退问题
"""

import os
import sys
import time
import traceback


# 强制刷新输出
def flush_print(msg):
    """强制刷新输出"""
    print(msg)
    sys.stdout.flush()
    time.sleep(0.1)  # 给agent时间捕获输出


def main():
    """主测试函数"""
    flush_print("🔬 阿里百炼工具调用测试 - Agent友好版本")
    flush_print("=" * 60)

    try:
        # 添加项目根目录到Python路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        flush_print("✅ 项目路径配置完成")

        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            flush_print("❌ 未找到DASHSCOPE_API_KEY环境变量")
            return False

        flush_print(f"✅ API密钥已配置: {api_key[:10]}...")

        # 测试1: 基本导入
        flush_print("\n🔧 测试1: 基本导入")
        flush_print("-" * 40)

        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        flush_print("✅ 所有模块导入成功")

        # 测试2: LLM创建
        flush_print("\n🔧 测试2: LLM创建")
        flush_print("-" * 40)

        llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=200)

        flush_print("✅ LLM实例创建成功")

        # 测试3: 工具定义和绑定
        flush_print("\n🔧 测试3: 工具定义和绑定")
        flush_print("-" * 40)

        @tool
        def get_stock_info(symbol: str) -> str:
            """获取股票信息"""
            return f"股票{symbol}的信息: 价格100元，涨幅+2.5%"

        llm_with_tools = llm.bind_tools([get_stock_info])
        flush_print("✅ 工具绑定成功")

        # 测试4: 简单调用（不要求工具调用）
        flush_print("\n🔧 测试4: 简单调用")
        flush_print("-" * 40)

        simple_response = llm.invoke([HumanMessage(content="请简单回复：你好")])

        flush_print("✅ 简单调用成功")
        flush_print(f"   响应长度: {len(simple_response.content)}字符")
        flush_print(f"   响应内容: {simple_response.content}")

        # 测试5: 工具调用测试
        flush_print("\n🔧 测试5: 工具调用测试")
        flush_print("-" * 40)

        # 尝试多种prompt策略
        prompts = [
            "请调用get_stock_info工具查询AAPL股票信息",
            "我需要AAPL的股票信息，请使用可用的工具",
            "必须调用get_stock_info工具，参数symbol='AAPL'",
        ]

        tool_call_success = False

        for i, prompt in enumerate(prompts, 1):
            flush_print(f"\n   策略{i}: {prompt[:30]}...")

            try:
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])

                tool_calls = getattr(response, "tool_calls", [])
                flush_print(f"   工具调用数量: {len(tool_calls)}")
                flush_print(f"   响应长度: {len(response.content)}字符")

                if len(tool_calls) > 0:
                    flush_print(f"   ✅ 策略{i}成功: 触发了工具调用")
                    for j, tool_call in enumerate(tool_calls):
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                        flush_print(f"      工具{j + 1}: {tool_name}({tool_args})")
                    tool_call_success = True
                    break
                flush_print(f"   ❌ 策略{i}失败: 未触发工具调用")
                flush_print(f"   直接响应: {response.content[:100]}...")

            except Exception as e:
                flush_print(f"   ❌ 策略{i}异常: {e}")

        # 测试6: 不同模型测试
        flush_print("\n🔧 测试6: 不同模型测试")
        flush_print("-" * 40)

        models = ["qwen-turbo", "qwen-plus-latest"]

        for model in models:
            flush_print(f"\n   测试模型: {model}")

            try:
                test_llm = ChatDashScopeOpenAI(
                    model=model,
                    temperature=0.0,  # 降低温度
                    max_tokens=100,
                )

                test_llm_with_tools = test_llm.bind_tools([get_stock_info])

                response = test_llm_with_tools.invoke([HumanMessage(content="请调用get_stock_info工具查询TSLA")])

                tool_calls = getattr(response, "tool_calls", [])
                flush_print(f"   {model}: 工具调用数量 = {len(tool_calls)}")

                if len(tool_calls) > 0:
                    flush_print(f"   ✅ {model}: 支持工具调用")
                else:
                    flush_print(f"   ❌ {model}: 不支持工具调用")

            except Exception as e:
                flush_print(f"   ❌ {model}: 测试异常 - {str(e)[:100]}")

        # 总结
        flush_print("\n📋 测试总结")
        flush_print("=" * 50)

        if tool_call_success:
            flush_print("🎉 阿里百炼工具调用测试成功！")
            flush_print("   ✅ 模型能够理解并执行工具调用")
            flush_print("   ✅ OpenAI兼容适配器工作正常")
        else:
            flush_print("⚠️ 阿里百炼工具调用存在问题")
            flush_print("   ❌ 模型不主动调用工具")
            flush_print("   💡 建议: 使用手动工具调用作为备用方案")

        flush_print("\n🔍 问题分析:")
        flush_print("   1. 适配器创建: ✅ 正常")
        flush_print("   2. 工具绑定: ✅ 正常")
        flush_print("   3. API调用: ✅ 正常")
        flush_print(f"   4. 工具调用: {'✅ 正常' if tool_call_success else '❌ 异常'}")

        if not tool_call_success:
            flush_print("\n💡 解决方案:")
            flush_print("   1. 使用更明确的工具调用指令")
            flush_print("   2. 调整模型参数(temperature=0.0)")
            flush_print("   3. 使用手动工具调用模式")
            flush_print("   4. 考虑使用DeepSeek作为替代")

        return tool_call_success

    except Exception as e:
        flush_print(f"\n💥 测试异常: {e}")
        flush_print("异常详情:")
        traceback.print_exc()
        return False

    finally:
        flush_print("\n" + "=" * 60)
        flush_print("测试完成！")
        # 不使用input()避免挂起


if __name__ == "__main__":
    try:
        success = main()
        exit_code = 0 if success else 1
        flush_print(f"退出码: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        flush_print(f"主函数异常: {e}")
        sys.exit(1)
