#!/usr/bin/env python3
"""
测试中文输出功能
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env", override=True)


def test_dashscope_chinese():
    """测试阿里百炼模型的中文输出"""
    try:
        from tradingagents.llm_adapters import ChatDashScope

        print("🧪 测试阿里百炼模型中文输出")
        print("=" * 50)

        # 创建模型实例
        llm = ChatDashScope(model="qwen-plus", temperature=0.1, max_tokens=500)

        # 测试中文提示词
        test_prompt = """你是一位专业的股票分析师。请用中文分析苹果公司(AAPL)的投资前景。

请重点关注：
1. 公司的竞争优势
2. 市场前景
3. 投资建议

请确保回答使用中文。"""

        print("发送测试提示词...")
        response = llm.invoke(test_prompt)

        print("✅ 模型响应成功")
        print(f"响应内容: {response.content[:200]}...")

        # 检查是否包含中文
        chinese_chars = sum(1 for char in response.content if "\u4e00" <= char <= "\u9fff")
        total_chars = len(response.content)
        chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0

        print(f"中文字符比例: {chinese_ratio:.2%}")

        if chinese_ratio > 0.3:
            print("✅ 模型正确输出中文内容")
            return True
        print("❌ 模型输出中文比例较低")
        return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        print(traceback.format_exc())
        return False


def test_signal_processor_chinese():
    """测试信号处理器的中文输出"""
    try:
        from tradingagents.graph.signal_processing import SignalProcessor
        from tradingagents.llm_adapters import ChatDashScope

        print("\n🧪 测试信号处理器中文输出")
        print("=" * 50)

        # 创建模型实例
        llm = ChatDashScope(model="qwen-plus", temperature=0.1, max_tokens=100)

        # 创建信号处理器
        processor = SignalProcessor(llm)

        # 测试信号
        test_signal = """基于技术分析和基本面分析，苹果公司显示出强劲的增长潜力。
        建议买入该股票，目标价位200美元。"""

        print("处理测试信号...")
        decision = processor.process_signal(test_signal, "AAPL")

        print("✅ 信号处理成功")
        print(f"决策结果: {decision}")

        # 检查决策是否为中文
        if any(word in decision for word in ["买入", "卖出", "持有"]):
            print("✅ 信号处理器输出中文决策")
            return True
        if any(word in decision.upper() for word in ["BUY", "SELL", "HOLD"]):
            print("⚠️ 信号处理器输出英文决策")
            return False
        print(f"❓ 未识别的决策格式: {decision}")
        return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        print(traceback.format_exc())
        return False


def main():
    """主测试函数"""
    print("🧪 中文输出功能测试")
    print("=" * 60)

    # 检查环境变量
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ DASHSCOPE_API_KEY 环境变量未设置")
        return

    # 测试基本中文输出
    success1 = test_dashscope_chinese()

    # 测试信号处理器
    success2 = test_signal_processor_chinese()

    print("\n📊 测试结果:")
    print(f"  基本中文输出: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"  信号处理器: {'✅ 通过' if success2 else '❌ 失败'}")

    if success1 and success2:
        print("\n🎉 所有测试通过！中文输出功能正常")
    else:
        print("\n⚠️ 部分测试失败，可能需要进一步调整")


if __name__ == "__main__":
    main()
