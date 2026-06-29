#!/usr/bin/env python3
"""
调试DeepSeek成本计算问题
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


def test_pricing_config():
    """测试定价配置"""
    print("🔍 测试定价配置...")

    from tradingagents.config.config_manager import ConfigManager

    config_manager = ConfigManager()
    pricing_configs = config_manager.load_pricing()

    print(f"📊 加载了 {len(pricing_configs)} 个定价配置:")
    for pricing in pricing_configs:
        if pricing.provider == "deepseek":
            print(
                f"   ✅ {pricing.provider}/{pricing.model_name}: 输入¥{pricing.input_price_per_1k}/1K, 输出¥{pricing.output_price_per_1k}/1K",
            )


def test_cost_calculation():
    """测试成本计算"""
    print("\n🧮 测试成本计算...")

    from tradingagents.config.config_manager import ConfigManager

    config_manager = ConfigManager()

    # 测试DeepSeek成本计算
    test_cases = [
        ("deepseek", "deepseek-chat", 2000, 1000),
        ("deepseek", "deepseek-coder", 1500, 800),
        ("dashscope", "qwen-turbo", 2000, 1000),  # 对比测试
    ]

    for provider, model, input_tokens, output_tokens in test_cases:
        cost = config_manager.calculate_cost(provider, model, input_tokens, output_tokens)
        print(f"   {provider}/{model}: {input_tokens}+{output_tokens} tokens = ¥{cost:.6f}")


def test_token_tracking():
    """测试Token跟踪"""
    print("\n📝 测试Token跟踪...")

    from tradingagents.config.config_manager import token_tracker

    # 测试DeepSeek使用记录
    record = token_tracker.track_usage(
        provider="deepseek",
        model_name="deepseek-chat",
        input_tokens=2000,
        output_tokens=1000,
        session_id="debug_test_001",
        analysis_type="debug_test",
    )

    if record:
        print("   ✅ 记录创建成功:")
        print(f"      Provider: {record.provider}")
        print(f"      Model: {record.model_name}")
        print(f"      Tokens: {record.input_tokens}+{record.output_tokens}")
        print(f"      Cost: ¥{record.cost:.6f}")
    else:
        print("   ❌ 记录创建失败")


def test_deepseek_adapter():
    """测试DeepSeek适配器"""
    print("\n🤖 测试DeepSeek适配器...")

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("   ⚠️ 未找到DEEPSEEK_API_KEY，跳过适配器测试")
        return

    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 创建DeepSeek实例
        llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=100)

        print("   ✅ DeepSeek适配器创建成功")
        print(f"      Model: {llm.model_name}")
        print(f"      Base URL: {llm.openai_api_base}")

        # 测试简单调用
        response = llm.invoke(
            "请简单说明什么是股票，不超过30字。", session_id="debug_adapter_test", analysis_type="debug_test",
        )

        print(f"   ✅ API调用成功，响应长度: {len(response.content)}")

    except Exception as e:
        print(f"   ❌ DeepSeek适配器测试失败: {e}")


def check_usage_statistics():
    """检查使用统计"""
    print("\n📊 检查使用统计...")

    from tradingagents.config.config_manager import config_manager

    stats = config_manager.get_usage_statistics(1)

    print(f"   总成本: ¥{stats.get('total_cost', 0):.6f}")
    print(f"   总请求: {stats.get('total_requests', 0)}")
    print(f"   总Token: {stats.get('total_tokens', 0)}")

    provider_stats = stats.get("provider_stats", {})
    deepseek_stats = provider_stats.get("deepseek", {})

    if deepseek_stats:
        print("   DeepSeek统计:")
        print(f"      成本: ¥{deepseek_stats.get('cost', 0):.6f}")
        print(f"      请求: {deepseek_stats.get('requests', 0)}")
        print(f"      Token: {deepseek_stats.get('tokens', 0)}")
    else:
        print("   ❌ 未找到DeepSeek统计")


def main():
    """主函数"""
    print("🔧 DeepSeek成本计算调试")
    print("=" * 50)

    try:
        test_pricing_config()
        test_cost_calculation()
        test_token_tracking()
        test_deepseek_adapter()
        check_usage_statistics()

        print("\n" + "=" * 50)
        print("✅ 调试完成")

    except Exception as e:
        print(f"\n❌ 调试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
