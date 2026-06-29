#!/usr/bin/env python3
"""
002027 股票代码专项测试
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_002027_specifically():
    """专门测试002027股票代码"""
    print("🔍 002027 专项测试")
    print("=" * 60)

    test_ticker = "002027"

    try:
        from tradingagents.utils.logging_init import get_logger

        logger = get_logger("default")
        logger.setLevel("INFO")

        # 测试1: 数据获取
        print("\n📊 测试1: 数据获取")
        from tradingagents.dataflows.interface import get_china_stock_data_tushare

        data = get_china_stock_data_tushare(test_ticker, "2025-07-01", "2025-07-15")

        if "002021" in data:
            print("❌ 数据获取阶段发现错误代码 002021")
            return False
        print("✅ 数据获取阶段正确")

        # 测试2: 基本面分析
        print("\n💰 测试2: 基本面分析")
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        analyzer = OptimizedChinaDataProvider()
        report = analyzer._generate_fundamentals_report(test_ticker, data)

        if "002021" in report:
            print("❌ 基本面分析阶段发现错误代码 002021")
            return False
        print("✅ 基本面分析阶段正确")

        # 测试3: LLM处理
        print("\n🤖 测试3: LLM处理")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            from langchain_core.messages import HumanMessage

            from tradingagents.llm_adapters import ChatDashScopeOpenAI

            llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=500)

            prompt = f"请分析股票{test_ticker}的基本面，股票名称是分众传媒。要求：1.必须使用正确的股票代码{test_ticker} 2.不要使用任何其他股票代码"

            response = llm.invoke([HumanMessage(content=prompt)])

            if "002021" in response.content:
                print("❌ LLM处理阶段发现错误代码 002021")
                print(f"错误内容: {response.content[:200]}...")
                return False
            print("✅ LLM处理阶段正确")
        else:
            print("⚠️ 跳过LLM测试（未配置API密钥）")

        print("\n🎉 所有测试通过！002027股票代码处理正确")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


if __name__ == "__main__":
    test_002027_specifically()
