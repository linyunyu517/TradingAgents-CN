#!/usr/bin/env python3
"""
测试美股分析功能
"""

import os
import sys

sys.path.append("..")


def test_us_stock_market_analysis():
    """测试美股市场分析"""
    print("🔍 测试美股市场分析...")

    try:
        from langchain_community.llms import Tongyi

        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        # 创建工具包
        toolkit = Toolkit()
        toolkit.update_config(config)

        # 检查工具包是否有正确的方法
        print("✅ 工具包方法检查:")
        print(f"  - get_YFin_data_online: {hasattr(toolkit, 'get_YFin_data_online')}")
        print(f"  - get_china_stock_data: {hasattr(toolkit, 'get_china_stock_data')}")

        # 创建Tongyi LLM
        llm = Tongyi()
        llm.model_name = "qwen-turbo"

        # 创建ReAct市场分析师
        analyst = create_market_analyst_react(llm, toolkit)

        # 测试美股
        test_state = {
            "trade_date": "2025-06-29",
            "company_of_interest": "AAPL",
            "messages": [("human", "分析AAPL")],
            "market_report": "",
        }

        print("\n🔄 开始美股市场分析...")
        result = analyst(test_state)

        print("✅ 美股市场分析完成")
        print(f"市场报告长度: {len(result['market_report'])}")

        if len(result["market_report"]) > 100:
            print("✅ 报告内容正常")
            print("报告前300字符:")
            print(result["market_report"][:300])
        else:
            print("❌ 报告内容异常:")
            print(result["market_report"])

        return result

    except Exception as e:
        print(f"❌ 美股市场分析失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_us_stock_fundamentals_analysis():
    """测试美股基本面分析"""
    print("\n" + "=" * 50)
    print("🔍 测试美股基本面分析...")

    try:
        from langchain_community.llms import Tongyi

        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst_react
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建配置
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        # 创建工具包
        toolkit = Toolkit()
        toolkit.update_config(config)

        # 检查工具包是否有正确的方法
        print("✅ 工具包方法检查:")
        print(f"  - get_YFin_data_online: {hasattr(toolkit, 'get_YFin_data_online')}")
        print(f"  - get_fundamentals_openai: {hasattr(toolkit, 'get_fundamentals_openai')}")

        # 创建Tongyi LLM
        llm = Tongyi()
        llm.model_name = "qwen-turbo"

        # 创建ReAct基本面分析师
        analyst = create_fundamentals_analyst_react(llm, toolkit)

        # 测试美股
        test_state = {
            "trade_date": "2025-06-29",
            "company_of_interest": "AAPL",
            "messages": [("human", "分析AAPL")],
            "fundamentals_report": "",
        }

        print("\n🔄 开始美股基本面分析...")
        result = analyst(test_state)

        print("✅ 美股基本面分析完成")
        print(f"基本面报告长度: {len(result['fundamentals_report'])}")

        if len(result["fundamentals_report"]) > 100:
            print("✅ 报告内容正常")
            print("报告前300字符:")
            print(result["fundamentals_report"][:300])
        else:
            print("❌ 报告内容异常:")
            print(result["fundamentals_report"])

        return result

    except Exception as e:
        print(f"❌ 美股基本面分析失败: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("🚀 开始美股分析测试")
    print("=" * 50)

    # 检查API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 请设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    print(f"✅ API密钥已配置: {api_key[:10]}...")

    # 测试市场分析
    result1 = test_us_stock_market_analysis()

    # 测试基本面分析
    result2 = test_us_stock_fundamentals_analysis()

    print("\n" + "=" * 50)
    print("🎯 测试总结:")
    print(f"市场分析测试: {'✅ 成功' if result1 else '❌ 失败'}")
    print(f"基本面分析测试: {'✅ 成功' if result2 else '❌ 失败'}")
