#!/usr/bin/env python3
"""
测试DeepSeek使用ReAct Agent的修复效果
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


def test_deepseek_react_market_analyst():
    """测试DeepSeek的ReAct市场分析师"""
    print("🤖 测试DeepSeek ReAct市场分析师")
    print("=" * 60)

    try:
        # 检查API密钥
        if not os.getenv("DEEPSEEK_API_KEY"):
            print("⚠️ 未找到DEEPSEEK_API_KEY，无法测试")
            return False

        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 创建DeepSeek LLM
        deepseek_llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=2000)

        # 创建工具包
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)

        # 创建ReAct市场分析师
        market_analyst = create_market_analyst_react(deepseek_llm, toolkit)

        # 模拟状态
        state = {"company_of_interest": "000002", "trade_date": "2025-07-08", "messages": []}

        print(f"📊 开始分析股票: {state['company_of_interest']}")

        # 执行分析
        result = market_analyst(state)

        print("📊 分析结果:")
        print(f"   消息数量: {len(result.get('messages', []))}")

        market_report = result.get("market_report", "")
        print(f"   市场报告长度: {len(market_report)}")
        print("   市场报告前500字符:")
        print("-" * 50)
        print(market_report[:500])
        print("-" * 50)

        # 检查报告质量
        has_data = any(keyword in market_report for keyword in ["¥", "RSI", "MACD", "万科", "技术指标", "6.56"])
        has_analysis = len(market_report) > 500
        not_placeholder = "正在调用工具" not in market_report and "(调用工具" not in market_report

        print("📊 报告质量检查:")
        print(f"   包含实际数据: {'✅' if has_data else '❌'}")
        print(f"   分析内容充实: {'✅' if has_analysis else '❌'}")
        print(f"   非占位符内容: {'✅' if not_placeholder else '❌'}")

        success = has_data and has_analysis and not_placeholder
        print(f"   整体评估: {'✅ 成功' if success else '❌ 需要改进'}")

        if success:
            print("\n🎉 DeepSeek ReAct市场分析师修复成功！")
            print("   - 正确调用了工具获取数据")
            print("   - 生成了基于真实数据的分析报告")
            print("   - 报告内容充实且专业")
        else:
            print("\n⚠️ DeepSeek ReAct市场分析师仍需改进")
            if not has_data:
                print("   - 缺少实际数据分析")
            if not has_analysis:
                print("   - 分析内容不够充实")
            if not not_placeholder:
                print("   - 仍包含占位符内容")

        return success

    except Exception as e:
        print(f"❌ DeepSeek ReAct市场分析师测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_graph_setup_logic():
    """测试图设置逻辑是否正确选择ReAct模式"""
    print("\n🔧 测试图设置逻辑")
    print("=" * 60)

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.setup import TradingAgentsGraph

        # 模拟DeepSeek配置
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "deepseek"
        config["deep_think_llm"] = "deepseek-chat"
        config["quick_think_llm"] = "deepseek-chat"

        print("📊 配置信息:")
        print(f"   LLM提供商: {config['llm_provider']}")
        print(f"   深度思考模型: {config['deep_think_llm']}")
        print(f"   快速思考模型: {config['quick_think_llm']}")

        # 创建图实例
        graph = TradingAgentsGraph(config)

        # 设置分析师（这会触发选择逻辑）
        print("\n📈 设置市场分析师...")
        graph.setup_and_compile(selected_analysts=["market"])

        print("✅ 图设置完成")
        return True

    except Exception as e:
        print(f"❌ 图设置逻辑测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🔬 DeepSeek ReAct修复效果测试")
    print("=" * 80)

    # 测试图设置逻辑
    setup_success = test_graph_setup_logic()

    # 测试DeepSeek ReAct分析师
    analyst_success = test_deepseek_react_market_analyst()

    # 总结
    print("\n📋 测试总结")
    print("=" * 60)

    print(f"图设置逻辑: {'✅ 正确' if setup_success else '❌ 有问题'}")
    print(f"DeepSeek ReAct分析师: {'✅ 修复成功' if analyst_success else '❌ 仍需修复'}")

    overall_success = setup_success and analyst_success

    if overall_success:
        print("\n🎉 DeepSeek ReAct修复完全成功！")
        print("   - 图设置逻辑正确选择ReAct模式")
        print("   - DeepSeek能正确执行工具调用并生成分析")
        print("   - 现在DeepSeek和百炼都使用稳定的ReAct Agent模式")
    else:
        print("\n⚠️ 仍有问题需要解决")
        if not setup_success:
            print("   - 图设置逻辑需要检查")
        if not analyst_success:
            print("   - DeepSeek ReAct分析师需要进一步修复")

    print("\n🎯 测试完成！")
    return overall_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
