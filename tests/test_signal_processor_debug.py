#!/usr/bin/env python3
"""
测试信号处理器的调试脚本
"""

import os
import sys

sys.path.append("..")


def test_signal_processor():
    """测试信号处理器功能"""
    print("🔍 测试信号处理器...")

    try:
        from tradingagents.graph.signal_processing import SignalProcessor
        from tradingagents.llm_adapters import ChatDashScope

        # 创建LLM实例
        llm = ChatDashScope(model="qwen-plus-latest", temperature=0.1, max_tokens=1000)

        # 创建信号处理器
        processor = SignalProcessor(llm)
        print("✅ 信号处理器创建成功")

        # 测试信号
        test_signal = """
        基于全面分析，我建议对该股票采取持有策略。

        投资建议：持有
        置信度：75%
        目标价位：¥45.50
        风险评分：40%

        主要理由：
        1. 技术面显示上升趋势
        2. 基本面稳健
        3. 市场情绪积极
        """

        print("\n📊 测试信号内容:")
        print(test_signal)

        # 处理信号
        print("\n🔄 开始处理信号...")
        result = processor.process_signal(test_signal, "000001")

        print("\n✅ 处理结果:")
        print(f"类型: {type(result)}")
        print(f"内容: {result}")

        # 检查结果结构
        if isinstance(result, dict):
            print("\n📋 结果详情:")
            for key, value in result.items():
                print(f"  {key}: {value}")

        return result

    except Exception as e:
        print(f"❌ 测试失败: {e!s}")
        import traceback

        traceback.print_exc()
        return None


def test_trading_graph():
    """测试完整的交易图"""
    print("\n" + "=" * 50)
    print("🔍 测试完整交易图...")

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "阿里百炼"
        config["quick_think_llm"] = "qwen-plus-latest"
        config["deep_think_llm"] = "qwen-plus-latest"

        print("📊 配置信息:")
        print(f"  LLM提供商: {config['llm_provider']}")
        print(f"  快速模型: {config['quick_think_llm']}")
        print(f"  深度模型: {config['deep_think_llm']}")

        # 创建交易图
        print("\n🔄 创建交易图...")
        graph = TradingAgentsGraph(analysts=["market"], config=config, debug=False)
        print("✅ 交易图创建成功")

        # 测试信号处理器
        print("\n🔄 测试信号处理器...")
        test_signal = "推荐：买入\n目标价位：¥50.00\n置信度：80%\n风险评分：30%"
        result = graph.process_signal(test_signal, "000001")

        print("✅ 信号处理结果:")
        print(f"类型: {type(result)}")
        print(f"内容: {result}")

        return result

    except Exception as e:
        print(f"❌ 测试失败: {e!s}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("🚀 开始信号处理器调试测试")
    print("=" * 50)

    # 检查API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 请设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    print(f"✅ API密钥已配置: {api_key[:10]}...")

    # 测试信号处理器
    result1 = test_signal_processor()

    # 测试交易图
    result2 = test_trading_graph()

    print("\n" + "=" * 50)
    print("🎯 测试总结:")
    print(f"信号处理器测试: {'✅ 成功' if result1 else '❌ 失败'}")
    print(f"交易图测试: {'✅ 成功' if result2 else '❌ 失败'}")
