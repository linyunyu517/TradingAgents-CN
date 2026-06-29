#!/usr/bin/env python3
"""
调试DeepSeek成本计算问题
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


def debug_config_manager():
    """调试配置管理器"""
    print("🔧 调试配置管理器")
    print("=" * 50)

    try:
        from tradingagents.config.config_manager import ConfigManager

        # 创建配置管理器
        config_manager = ConfigManager()

        print(f"📁 配置目录: {config_manager.config_dir}")
        print(f"📄 定价文件: {config_manager.pricing_file}")
        print(f"📄 定价文件存在: {config_manager.pricing_file.exists()}")

        # 加载定价配置
        pricing_configs = config_manager.load_pricing()
        print(f"📊 加载的定价配置数量: {len(pricing_configs)}")

        # 查找DeepSeek配置
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"📊 DeepSeek定价配置数量: {len(deepseek_configs)}")

        for config in deepseek_configs:
            print(f"   - 提供商: {config.provider}")
            print(f"   - 模型: {config.model_name}")
            print(f"   - 输入价格: {config.input_price_per_1k}")
            print(f"   - 输出价格: {config.output_price_per_1k}")
            print(f"   - 货币: {config.currency}")

        # 测试成本计算
        print("\n💰 测试成本计算:")
        cost = config_manager.calculate_cost(
            provider="deepseek", model_name="deepseek-chat", input_tokens=2272, output_tokens=1215,
        )
        print(f"   计算结果: ¥{cost:.6f}")

        if cost == 0.0:
            print("❌ 成本计算返回0，检查匹配逻辑...")

            # 详细检查匹配逻辑
            for pricing in pricing_configs:
                print(f"   检查配置: provider='{pricing.provider}', model='{pricing.model_name}'")
                if pricing.provider == "deepseek" and pricing.model_name == "deepseek-chat":
                    print("   ✅ 找到匹配配置!")
                    input_cost = (2272 / 1000) * pricing.input_price_per_1k
                    output_cost = (1215 / 1000) * pricing.output_price_per_1k
                    total_cost = input_cost + output_cost
                    print(f"   输入成本: {input_cost:.6f}")
                    print(f"   输出成本: {output_cost:.6f}")
                    print(f"   总成本: {total_cost:.6f}")
                    break
            else:
                print("   ❌ 未找到匹配的配置")

        return True

    except Exception as e:
        print(f"❌ 配置管理器调试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def debug_token_tracker():
    """调试Token跟踪器"""
    print("\n📊 调试Token跟踪器")
    print("=" * 50)

    try:
        from tradingagents.config.config_manager import ConfigManager, TokenTracker

        # 创建配置管理器和Token跟踪器
        config_manager = ConfigManager()
        token_tracker = TokenTracker(config_manager)

        print("🔧 Token跟踪器创建成功")

        # 检查设置
        settings = config_manager.load_settings()
        cost_tracking_enabled = settings.get("enable_cost_tracking", True)
        print(f"📊 成本跟踪启用: {cost_tracking_enabled}")

        # 测试跟踪使用
        print("💰 测试Token跟踪...")
        usage_record = token_tracker.track_usage(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=2272,
            output_tokens=1215,
            session_id="debug_session",
            analysis_type="debug_analysis",
        )

        if usage_record:
            print("✅ Token跟踪成功")
            print(f"   提供商: {usage_record.provider}")
            print(f"   模型: {usage_record.model_name}")
            print(f"   输入tokens: {usage_record.input_tokens}")
            print(f"   输出tokens: {usage_record.output_tokens}")
            print(f"   成本: ¥{usage_record.cost:.6f}")

            if usage_record.cost > 0:
                print("✅ 成本计算正确")
                return True
            print("❌ 成本计算仍为0")
            return False
        print("❌ Token跟踪失败")
        return False

    except Exception as e:
        print(f"❌ Token跟踪器调试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def debug_deepseek_adapter():
    """调试DeepSeek适配器"""
    print("\n🤖 调试DeepSeek适配器")
    print("=" * 50)

    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("⚠️ 未找到DEEPSEEK_API_KEY，跳过适配器调试")
        return True

    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        print("🔧 创建DeepSeek适配器...")

        # 创建DeepSeek实例
        deepseek_llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1, max_tokens=100)

        print(f"📊 模型名称: {deepseek_llm.model_name}")

        # 检查TOKEN_TRACKING_ENABLED
        from tradingagents.llm_adapters.deepseek_adapter import TOKEN_TRACKING_ENABLED

        print(f"📊 Token跟踪启用: {TOKEN_TRACKING_ENABLED}")

        # 测试调用
        print("📤 发送测试请求...")
        result = deepseek_llm.invoke("测试")

        print("📊 调用完成")
        print(f"   响应长度: {len(result.content)}")

        return True

    except Exception as e:
        print(f"❌ DeepSeek适配器调试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def debug_model_name_issue():
    """调试模型名称匹配问题"""
    print("\n🔍 调试模型名称匹配问题")
    print("=" * 50)

    try:
        from tradingagents.config.config_manager import ConfigManager
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

        # 创建配置管理器
        config_manager = ConfigManager()

        # 创建DeepSeek实例
        deepseek_llm = ChatDeepSeek(model="deepseek-chat")

        print(f"📊 适配器中的模型名称: '{deepseek_llm.model_name}'")

        # 加载定价配置
        pricing_configs = config_manager.load_pricing()

        print("📊 定价配置中的DeepSeek模型:")
        for config in pricing_configs:
            if config.provider == "deepseek":
                print(f"   - 模型名称: '{config.model_name}'")
                print(f"   - 匹配检查: {config.model_name == deepseek_llm.model_name}")

        # 手动测试匹配
        print("\n💰 手动测试成本计算:")
        cost = config_manager.calculate_cost(
            provider="deepseek", model_name=deepseek_llm.model_name, input_tokens=100, output_tokens=50,
        )
        print(f"   使用适配器模型名称: ¥{cost:.6f}")

        cost2 = config_manager.calculate_cost(
            provider="deepseek", model_name="deepseek-chat", input_tokens=100, output_tokens=50,
        )
        print(f"   使用硬编码模型名称: ¥{cost2:.6f}")

        return True

    except Exception as e:
        print(f"❌ 模型名称调试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🔬 DeepSeek成本计算问题深度调试")
    print("=" * 80)

    # 调试配置管理器
    config_success = debug_config_manager()

    # 调试Token跟踪器
    tracker_success = debug_token_tracker()

    # 调试模型名称匹配
    model_success = debug_model_name_issue()

    # 调试适配器
    adapter_success = debug_deepseek_adapter()

    # 总结
    print("\n📋 调试总结")
    print("=" * 60)

    print(f"配置管理器: {'✅ 正常' if config_success else '❌ 有问题'}")
    print(f"Token跟踪器: {'✅ 正常' if tracker_success else '❌ 有问题'}")
    print(f"模型名称匹配: {'✅ 正常' if model_success else '❌ 有问题'}")
    print(f"适配器调试: {'✅ 正常' if adapter_success else '❌ 有问题'}")

    overall_success = config_success and tracker_success and model_success and adapter_success

    if overall_success:
        print("\n🤔 所有组件都正常，但实际使用时成本为0...")
        print("   可能的原因:")
        print("   1. 在实际分析流程中使用了不同的配置目录")
        print("   2. 某个地方覆盖了配置")
        print("   3. 有缓存问题")
        print("   4. 模型名称在某个地方被修改了")
    else:
        print("\n❌ 发现问题，请检查上述失败的组件")

    print("\n🎯 调试完成！")
    return overall_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
