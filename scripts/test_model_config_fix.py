#!/usr/bin/env python
"""测试模型配置修复"""

from app.core.unified_config import unified_config

print("=" * 80)
print("🧪 测试模型配置读取")
print("=" * 80)

# 1. 读取系统设置
settings = unified_config.get_system_settings()
print("\n📖 系统设置中的字段:")
print(f"  - quick_analysis_model: {settings.get('quick_analysis_model')}")
print(f"  - deep_analysis_model: {settings.get('deep_analysis_model')}")
print(f"  - quick_think_llm: {settings.get('quick_think_llm')}")
print(f"  - deep_think_llm: {settings.get('deep_think_llm')}")

# 2. 测试新的读取函数
quick_model = unified_config.get_quick_analysis_model()
deep_model = unified_config.get_deep_analysis_model()

print("\n✅ 通过 unified_config 读取的模型:")
print(f"  - quick_analysis_model: {quick_model}")
print(f"  - deep_analysis_model: {deep_model}")

# 3. 验证结果
expected_quick = "qwen-flash"
expected_deep = "qwen-plus"

if quick_model == expected_quick and deep_model == expected_deep:
    print("\n🎉 测试通过！模型配置正确:")
    print(f"  ✓ 快速分析模型: {quick_model}")
    print(f"  ✓ 深度分析模型: {deep_model}")
else:
    print("\n❌ 测试失败！")
    print(f"  期望: quick={expected_quick}, deep={expected_deep}")
    print(f"  实际: quick={quick_model}, deep={deep_model}")

print("\n" + "=" * 80)
