"""
测试聚合渠道支持功能

使用方法:
    python scripts/test_aggregator_support.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.constants.model_capabilities import AGGREGATOR_PROVIDERS, is_aggregator_model, parse_aggregator_model
from app.services.model_capability_service import ModelCapabilityService


def test_aggregator_model_parsing():
    """测试聚合渠道模型名称解析"""
    print("=" * 60)
    print("测试 1: 聚合渠道模型名称解析")
    print("=" * 60)

    test_cases = [
        ("openai/gpt-4", True, ("openai", "gpt-4")),
        ("anthropic/claude-3-sonnet", True, ("anthropic", "claude-3-sonnet")),
        ("google/gemini-pro", True, ("google", "gemini-pro")),
        ("gpt-4", False, ("", "gpt-4")),
        ("qwen-turbo", False, ("", "qwen-turbo")),
    ]

    for model_name, expected_is_aggregator, expected_parse in test_cases:
        is_agg = is_aggregator_model(model_name)
        parsed = parse_aggregator_model(model_name)

        status = "✅" if (is_agg == expected_is_aggregator and parsed == expected_parse) else "❌"
        print(f"{status} {model_name}")
        print(f"   是否聚合模型: {is_agg} (期望: {expected_is_aggregator})")
        print(f"   解析结果: {parsed} (期望: {expected_parse})")
        print()


def test_model_capability_mapping():
    """测试模型能力映射"""
    print("=" * 60)
    print("测试 2: 模型能力映射")
    print("=" * 60)

    service = ModelCapabilityService()

    test_models = [
        # 聚合渠道模型（应该映射到原模型）
        "openai/gpt-4",
        "anthropic/claude-3-sonnet",
        "google/gemini-pro",
        # 原厂模型（直接匹配）
        "gpt-4",
        "claude-3-sonnet",
        "gemini-pro",
        # 通义千问模型
        "qwen-turbo",
        "qwen-plus",
        "qwen-max",
    ]

    for model_name in test_models:
        capability = service.get_model_capability(model_name)
        config = service.get_model_config(model_name)

        print(f"📊 {model_name}")
        print(f"   能力等级: {capability}")
        print(f"   适用角色: {config.get('suitable_roles', [])}")
        print(f"   特性: {config.get('features', [])}")

        if "_mapped_from" in config:
            print(f"   🔄 映射自: {config['_mapped_from']}")

        print()


def test_aggregator_providers_config():
    """测试聚合渠道配置"""
    print("=" * 60)
    print("测试 3: 聚合渠道配置")
    print("=" * 60)

    for provider_name, config in AGGREGATOR_PROVIDERS.items():
        print(f"🌐 {config['display_name']} ({provider_name})")
        print(f"   官网: {config.get('website', 'N/A')}")
        print(f"   API 端点: {config['default_base_url']}")
        print(f"   模型格式: {config.get('model_name_format', 'N/A')}")
        print(f"   支持厂商: {', '.join(config.get('supported_providers', []))}")
        print()


def test_model_recommendation():
    """测试模型推荐（使用聚合渠道模型）"""
    print("=" * 60)
    print("测试 4: 模型推荐")
    print("=" * 60)

    service = ModelCapabilityService()

    # 模拟聚合渠道模型的验证
    test_pairs = [
        ("openai/gpt-3.5-turbo", "openai/gpt-4", "标准"),
        ("qwen-turbo", "anthropic/claude-3-sonnet", "深度"),
        ("google/gemini-1.5-flash", "google/gemini-1.5-pro", "全面"),
    ]

    for quick_model, deep_model, depth in test_pairs:
        print(f"🔍 验证模型对: {quick_model} + {deep_model} (深度: {depth})")

        result = service.validate_model_pair(quick_model, deep_model, depth)

        print(f"   有效: {'✅' if result['valid'] else '❌'}")

        if result["warnings"]:
            print("   警告:")
            for warning in result["warnings"]:
                print(f"     - {warning}")

        if result["recommendations"]:
            print("   建议:")
            for rec in result["recommendations"]:
                print(f"     - {rec}")

        print()


def main():
    """主函数"""
    print("\n")
    print("🚀 聚合渠道支持功能测试")
    print("=" * 60)
    print()

    try:
        # 测试 1: 模型名称解析
        test_aggregator_model_parsing()

        # 测试 2: 能力映射
        test_model_capability_mapping()

        # 测试 3: 聚合渠道配置
        test_aggregator_providers_config()

        # 测试 4: 模型推荐
        test_model_recommendation()

        print("=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
