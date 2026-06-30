"""
测试 API Key 验证逻辑

验证占位符检测是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.startup_validator import StartupValidator


def test_api_key_validation():
    """测试 API Key 验证逻辑"""
    validator = StartupValidator()

    # 测试用例
    test_cases = [
        # (api_key, expected_result, description)
        ("", False, "空字符串"),
        ("   ", False, "空白字符串"),
        ("sk-123", False, "长度不足"),
        ("your_openai_api_key_here", False, "占位符 - your_ 前缀 + _here 后缀"),
        ("your_dashscope_api_key_here", False, "占位符 - your_ 前缀 + _here 后缀"),
        ("your_anthropic_api_key_here", False, "占位符 - your_ 前缀 + _here 后缀"),
        ("your-api-key-here", False, "占位符 - your- 前缀 + -here 后缀"),
        ("your_test_key", False, "占位符 - your_ 前缀"),
        ("your-test-key", False, "占位符 - your- 前缀"),
        ("some_key_here", False, "占位符 - _here 后缀"),
        ("some-key-here", False, "占位符 - -here 后缀"),
        ("sk-990547695d6046cf9be4e8d095235d91", True, "有效的 API Key"),
        ("sk-c64f9c504be1496f943843f553e3d6ee", True, "有效的 API Key"),
        ("AIzaSyC3JdZVjblI0rfT_SNXXL5a4kvZ13_12CE", True, "有效的 Google API Key"),
        ("bce-v3/ALTAK-ZV1T8VLLSFYvSPAzVthhY/d364f2499819c1e08dd2e84c7cc5a9ab6bac895f", True, "有效的千帆 API Key"),
        (
            "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",
            True,
            "有效的 OpenRouter API Key",
        ),
        ('"sk-990547695d6046cf9be4e8d095235d91"', True, "带引号的有效 API Key"),
        ("'sk-990547695d6046cf9be4e8d095235d91'", True, "带单引号的有效 API Key"),
    ]

    print("\n" + "=" * 80)
    print("🧪 API Key 验证测试")
    print("=" * 80)

    passed = 0
    failed = 0

    for api_key, expected, description in test_cases:
        result = validator._is_valid_api_key(api_key)
        status = "✅ PASS" if result == expected else "❌ FAIL"

        if result == expected:
            passed += 1
        else:
            failed += 1

        # 显示 API Key 的前 20 个字符（如果太长）
        display_key = api_key if len(api_key) <= 40 else api_key[:40] + "..."

        print(f"{status} | {description:40s} | Key: {display_key:45s} | Expected: {expected:5} | Got: {result:5}")

    print("=" * 80)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_api_key_validation()
    sys.exit(0 if success else 1)
