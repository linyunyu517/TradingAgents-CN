"""
测试脚本：验证模型特性转换修复

这个脚本会：
1. 测试从数据库读取模型配置
2. 验证字符串到枚举的转换
3. 测试模型验证逻辑
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_model_config():
    """测试模型配置读取"""

    print("=" * 80)
    print("测试：模型配置读取和特性转换")
    print("=" * 80)

    from app.constants.model_capabilities import ModelFeature, ModelRole
    from app.services.model_capability_service import ModelCapabilityService

    service = ModelCapabilityService()

    # 测试 gemini-2.5-flash
    print("\n🔍 测试模型：gemini-2.5-flash")
    config = service.get_model_config("gemini-2.5-flash")

    print("\n📊 模型配置：")
    print(f"  - model_name: {config['model_name']}")
    print(f"  - capability_level: {config['capability_level']}")
    print(f"  - suitable_roles: {config['suitable_roles']}")
    print(f"  - features: {config['features']}")
    print(f"  - recommended_depths: {config['recommended_depths']}")

    # 检查类型
    print("\n🔍 类型检查：")
    print(f"  - suitable_roles 类型: {type(config['suitable_roles'])}")
    if config["suitable_roles"]:
        print(f"  - suitable_roles[0] 类型: {type(config['suitable_roles'][0])}")
        print(f"  - suitable_roles[0] 值: {config['suitable_roles'][0]}")

    print(f"  - features 类型: {type(config['features'])}")
    if config["features"]:
        print(f"  - features[0] 类型: {type(config['features'][0])}")
        print(f"  - features[0] 值: {config['features'][0]}")

    # 测试枚举比较
    print("\n🔍 枚举比较测试：")
    if config["features"]:
        has_tool_calling = ModelFeature.TOOL_CALLING in config["features"]
        print(f"  - ModelFeature.TOOL_CALLING in features: {has_tool_calling}")
        print(f"  - ModelFeature.TOOL_CALLING 值: {ModelFeature.TOOL_CALLING}")
        print(f"  - ModelFeature.TOOL_CALLING 类型: {type(ModelFeature.TOOL_CALLING)}")

    if config["suitable_roles"]:
        has_both = ModelRole.BOTH in config["suitable_roles"]
        has_quick = ModelRole.QUICK_ANALYSIS in config["suitable_roles"]
        print(f"  - ModelRole.BOTH in suitable_roles: {has_both}")
        print(f"  - ModelRole.QUICK_ANALYSIS in suitable_roles: {has_quick}")

    print("\n" + "=" * 80)


def test_model_validation():
    """测试模型验证"""

    print("\n测试：模型对验证")
    print("=" * 80)

    from app.services.model_capability_service import ModelCapabilityService

    service = ModelCapabilityService()

    # 测试 gemini-2.5-flash + qwen-plus
    print("\n🔍 测试模型对：gemini-2.5-flash + qwen-plus")
    result = service.validate_model_pair(quick_model="gemini-2.5-flash", deep_model="qwen-plus", research_depth="标准")

    print("\n📊 验证结果：")
    print(f"  - valid: {result['valid']}")
    print(f"  - warnings: {len(result['warnings'])} 条")
    if result["warnings"]:
        for i, warning in enumerate(result["warnings"], 1):
            print(f"    {i}. {warning}")
    print(f"  - recommendations: {len(result['recommendations'])} 条")
    if result["recommendations"]:
        for i, rec in enumerate(result["recommendations"], 1):
            print(f"    {i}. {rec}")

    if result["valid"]:
        print("\n✅ 验证通过！模型对可以使用")
    else:
        print("\n❌ 验证失败！模型对不适合使用")

    print("\n" + "=" * 80)


def test_database_config():
    """测试数据库配置"""

    print("\n测试：数据库配置")
    print("=" * 80)

    from app.core.unified_config import unified_config

    llm_configs = unified_config.get_llm_configs()

    print("\n📊 数据库中的模型配置：")

    # 查找 gemini-2.5-flash
    for config in llm_configs:
        if config.model_name == "gemini-2.5-flash":
            print("\n🔍 找到 gemini-2.5-flash 配置：")
            print(f"  - model_name: {config.model_name}")
            print(f"  - capability_level: {config.capability_level}")
            print(f"  - suitable_roles: {config.suitable_roles} (类型: {type(config.suitable_roles)})")
            print(f"  - features: {config.features} (类型: {type(config.features)})")
            print(f"  - recommended_depths: {config.recommended_depths}")

            # 检查 features 的内容
            if config.features:
                print("\n  📋 features 详情：")
                for i, feature in enumerate(config.features, 1):
                    print(f"    {i}. {feature} (类型: {type(feature).__name__})")

            # 检查 suitable_roles 的内容
            if config.suitable_roles:
                print("\n  📋 suitable_roles 详情：")
                for i, role in enumerate(config.suitable_roles, 1):
                    print(f"    {i}. {role} (类型: {type(role).__name__})")

            break
    else:
        print("\n❌ 未找到 gemini-2.5-flash 配置")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    # 测试数据库配置
    test_database_config()

    # 测试模型配置读取
    test_model_config()

    # 测试模型验证
    test_model_validation()

    print("\n✅ 所有测试完成！")
