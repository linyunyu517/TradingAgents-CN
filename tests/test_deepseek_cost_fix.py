#!/usr/bin/env python3
"""
验证DeepSeek成本计算修复
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()


def test_deepseek_cost_calculation():
    """测试DeepSeek成本计算"""
    print("🧪 测试DeepSeek成本计算修复")
    print("=" * 50)

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("⚠️ 未找到DEEPSEEK_API_KEY，跳过测试")
        return False

    try:
        from tradingagents.config.config_manager import config_manager
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 获取初始统计
        initial_stats = config_manager.get_usage_statistics(1)
        initial_cost = initial_stats.get("total_cost", 0)

        print(f"📊 初始成本: ¥{initial_cost:.6f}")

        # 创建DeepSeek实例
        llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=100)

        # 测试多次调用
        test_cases = ["什么是股票？", "请简单解释市盈率的含义。", "分析一下投资风险。"]

        for i, prompt in enumerate(test_cases, 1):
            print(f"\n🔍 测试 {i}: {prompt}")

            response = llm.invoke(prompt, session_id=f"test_cost_{i}", analysis_type="cost_test")

            print(f"   响应长度: {len(response.content)}")

        # 等待统计更新
        import time

        time.sleep(1)

        # 检查最终统计
        final_stats = config_manager.get_usage_statistics(1)
        final_cost = final_stats.get("total_cost", 0)

        cost_increase = final_cost - initial_cost

        print("\n📊 最终统计:")
        print(f"   初始成本: ¥{initial_cost:.6f}")
        print(f"   最终成本: ¥{final_cost:.6f}")
        print(f"   成本增加: ¥{cost_increase:.6f}")

        # 检查DeepSeek统计
        provider_stats = final_stats.get("provider_stats", {})
        deepseek_stats = provider_stats.get("deepseek", {})

        if deepseek_stats:
            print(f"   DeepSeek成本: ¥{deepseek_stats.get('cost', 0):.6f}")
            print(f"   DeepSeek请求: {deepseek_stats.get('requests', 0)}")
            print(f"   DeepSeek Token: {deepseek_stats.get('tokens', 0)}")

        # 验证成本是否合理
        if cost_increase > 0:
            print("\n✅ 成本计算修复成功！")
            print(f"   每次调用平均成本: ¥{cost_increase / len(test_cases):.6f}")
            return True
        print("\n❌ 成本计算仍有问题")
        return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cost_precision():
    """测试成本精度显示"""
    print("\n🔍 测试成本精度显示")
    print("-" * 30)

    from tradingagents.config.config_manager import ConfigManager

    config_manager = ConfigManager()

    # 测试小额成本计算
    test_cases = [
        (10, 5),  # 很小的token数
        (100, 50),  # 小的token数
        (1000, 500),  # 中等token数
        (2000, 1000),  # 较大token数
    ]

    for input_tokens, output_tokens in test_cases:
        cost = config_manager.calculate_cost("deepseek", "deepseek-chat", input_tokens, output_tokens)
        print(f"   {input_tokens:4d}+{output_tokens:4d} tokens = ¥{cost:.6f}")


def main():
    """主函数"""
    success1 = test_deepseek_cost_calculation()
    test_cost_precision()

    print("\n" + "=" * 50)
    if success1:
        print("🎉 DeepSeek成本计算修复验证成功！")
    else:
        print("❌ DeepSeek成本计算仍需修复")

    return success1


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
