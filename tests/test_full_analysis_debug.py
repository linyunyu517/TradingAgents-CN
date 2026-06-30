#!/usr/bin/env python3
"""
运行完整的股票分析，观察DeepSeek成本计算的详细日志
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


def test_full_stock_analysis():
    """运行完整的股票分析"""
    print("🔬 完整股票分析 - DeepSeek成本计算调试")
    print("=" * 80)

    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 未找到DEEPSEEK_API_KEY，无法测试")
        return False

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.setup import TradingAgentsGraph

        print("🔧 初始化交易分析图...")

        # 配置DeepSeek
        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "llm_provider": "deepseek",
                "deep_think_llm": "deepseek-chat",
                "quick_think_llm": "deepseek-chat",
                "max_debate_rounds": 1,  # 减少轮次，节省时间
                "max_risk_discuss_rounds": 1,
                "online_tools": True,
                "memory_enabled": False,
            },
        )

        print("📊 配置信息:")
        print(f"   LLM提供商: {config['llm_provider']}")
        print(f"   深度思考模型: {config['deep_think_llm']}")
        print(f"   快速思考模型: {config['quick_think_llm']}")

        # 创建图实例
        graph = TradingAgentsGraph(config)

        # 设置分析师（只选择市场分析师，减少复杂度）
        print("📈 设置分析师...")
        graph.setup_and_compile(selected_analysts=["market"])

        print("✅ 图设置完成")

        # 准备输入
        input_data = {
            "company_of_interest": "300059",  # 东方财富
            "trade_date": "2025-07-08",
        }

        print(f"\n📊 开始分析股票: {input_data['company_of_interest']}")
        print(f"📅 交易日期: {input_data['trade_date']}")
        print("\n" + "=" * 100)
        print("开始完整分析流程，请观察DeepSeek成本计算的详细日志：")
        print("=" * 100)

        # 运行分析
        result = graph.run(input_data)

        print("=" * 100)
        print("分析完成！")
        print("=" * 100)

        # 输出结果摘要
        if result and "decision" in result:
            decision = result["decision"]
            print("\n📋 分析结果摘要:")
            print(f"   投资建议: {decision.get('action', 'N/A')}")
            print(f"   置信度: {decision.get('confidence', 'N/A')}")
            print(f"   目标价格: {decision.get('target_price', 'N/A')}")

            if "market_report" in result:
                market_report = result["market_report"]
                print(f"   市场报告长度: {len(market_report)}")

        return True

    except Exception as e:
        print(f"❌ 完整分析测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🔬 完整股票分析 - DeepSeek成本计算调试测试")
    print("=" * 80)
    print("📝 这个测试将运行完整的股票分析流程")
    print("📝 请仔细观察所有的成本计算日志")
    print("📝 特别注意是否有成本为¥0.000000的情况")
    print("=" * 80)

    success = test_full_stock_analysis()

    if success:
        print("\n🎉 完整分析测试完成！")
        print("请查看上面的详细日志，分析成本计算的完整流程。")
    else:
        print("\n❌ 完整分析测试失败")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
