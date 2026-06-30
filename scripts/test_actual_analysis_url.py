"""
测试脚本：模拟实际分析流程，查看使用的 backend_url
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.simple_analysis_service import create_analysis_config, get_provider_and_url_by_model_sync


def main():
    print("=" * 80)
    print("🧪 测试：模拟实际分析流程")
    print("=" * 80)

    # 测试参数
    quick_model = "qwen-turbo"
    deep_model = "qwen-plus"
    llm_provider = "dashscope"

    print("\n📋 测试参数：")
    print(f"  快速模型: {quick_model}")
    print(f"  深度模型: {deep_model}")
    print(f"  LLM 厂家: {llm_provider}")

    # 1. 测试 get_provider_and_url_by_model_sync
    print(f"\n\n🔍 1. 测试 get_provider_and_url_by_model_sync('{quick_model}')")
    print("-" * 80)

    try:
        provider_info = get_provider_and_url_by_model_sync(quick_model)
        print("\n✅ 查询成功：")
        print(f"   厂家: {provider_info['provider']}")
        print(f"   backend_url: {provider_info['backend_url']}")
    except Exception as e:
        print(f"\n❌ 查询失败: {e}")
        import traceback

        traceback.print_exc()

    # 2. 测试 create_analysis_config
    print("\n\n🔍 2. 测试 create_analysis_config()")
    print("-" * 80)

    try:
        config = create_analysis_config(
            research_depth="标准",
            selected_analysts=["market", "fundamentals"],
            quick_model=quick_model,
            deep_model=deep_model,
            llm_provider=llm_provider,
            market_type="A股",
        )

        print("\n✅ 配置创建成功：")
        print(f"   backend_url: {config.get('backend_url')}")
        print(f"   llm_provider: {config.get('llm_provider')}")
        print(f"   quick_think_llm: {config.get('quick_think_llm')}")
        print(f"   deep_think_llm: {config.get('deep_think_llm')}")

        # 检查是否使用了正确的 URL
        expected_url = "https://dashscope.aliyuncs.com/api/v2"
        actual_url = config.get("backend_url")

        print("\n🎯 URL 验证：")
        print(f"   期望的 URL: {expected_url}")
        print(f"   实际的 URL: {actual_url}")

        if actual_url == expected_url:
            print("   ✅ URL 正确！厂家的 default_base_url 已生效")
        else:
            print("   ❌ URL 不正确！")
            print("   可能的原因：")
            print("   1. 模型配置中有 api_base 字段")
            print("   2. 厂家配置中的 default_base_url 不正确")
            print("   3. 代码逻辑有问题")

    except Exception as e:
        print(f"\n❌ 配置创建失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
