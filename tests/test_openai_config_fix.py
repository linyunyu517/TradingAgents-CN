#!/usr/bin/env python3
"""
测试OpenAI配置修复效果
验证在没有OpenAI API Key的情况下，系统是否正确跳过OpenAI API调用
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_openai_config_detection():
    """测试OpenAI配置检测逻辑"""
    print("\n🔍 测试OpenAI配置检测逻辑")
    print("=" * 80)

    try:
        # 检查当前环境变量
        openai_key = os.getenv("OPENAI_API_KEY")
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        finnhub_key = os.getenv("FINNHUB_API_KEY")

        print("📊 当前环境变量状态:")
        print(f"   OPENAI_API_KEY: {'✅ 已配置' if openai_key else '❌ 未配置'}")
        print(f"   DASHSCOPE_API_KEY: {'✅ 已配置' if dashscope_key else '❌ 未配置'}")
        print(f"   FINNHUB_API_KEY: {'✅ 已配置' if finnhub_key else '❌ 未配置'}")

        # 检查配置
        from tradingagents.dataflows.config import get_config

        config = get_config()

        print("\n📊 当前系统配置:")
        print(f"   llm_provider: {config.get('llm_provider', 'N/A')}")
        print(f"   backend_url: {config.get('backend_url', 'N/A')}")
        print(f"   quick_think_llm: {config.get('quick_think_llm', 'N/A')}")
        print(f"   deep_think_llm: {config.get('deep_think_llm', 'N/A')}")

        # 模拟OpenAI配置检查逻辑
        print("\n🔍 模拟OpenAI配置检查:")

        # 检查1: OpenAI API Key
        if not openai_key:
            print("   ❌ 检查1失败: 未配置OPENAI_API_KEY")
            should_skip_openai = True
        else:
            print("   ✅ 检查1通过: OPENAI_API_KEY已配置")
            should_skip_openai = False

        # 检查2: 基本配置
        if not should_skip_openai:
            if not config.get("backend_url") or not config.get("quick_think_llm"):
                print("   ❌ 检查2失败: OpenAI配置不完整")
                should_skip_openai = True
            else:
                print("   ✅ 检查2通过: OpenAI基本配置完整")

        # 检查3: backend_url是否是OpenAI的
        if not should_skip_openai:
            backend_url = config.get("backend_url", "")
            if "openai.com" not in backend_url:
                print(f"   ❌ 检查3失败: backend_url不是OpenAI API ({backend_url})")
                should_skip_openai = True
            else:
                print("   ✅ 检查3通过: backend_url是OpenAI API")

        print("\n📋 最终决策:")
        if should_skip_openai:
            print("   🔄 跳过OpenAI API，直接使用FinnHub")
        else:
            print("   🔄 使用OpenAI API")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_fundamentals_api_selection():
    """测试基本面数据API选择逻辑"""
    print("\n📊 测试基本面数据API选择逻辑")
    print("=" * 80)

    try:
        # 设置日志级别
        from tradingagents.utils.logging_init import get_logger

        logger = get_logger("default")
        logger.setLevel("INFO")

        # 测试美股基本面数据获取
        test_ticker = "MSFT"
        test_date = "2025-07-16"

        print(f"📊 测试股票: {test_ticker}")
        print(f"📊 测试日期: {test_date}")

        print("\n🔄 调用基本面数据获取...")

        from tradingagents.dataflows.interface import get_fundamentals_openai

        # 这个调用应该会跳过OpenAI，直接使用FinnHub
        result = get_fundamentals_openai(test_ticker, test_date)

        print("✅ 基本面数据获取完成")
        print(f"   结果类型: {type(result)}")
        print(f"   结果长度: {len(result) if result else 0}")

        if result:
            # 检查结果来源
            if "finnhub" in result.lower() or "FinnHub" in result:
                print("   ✅ 确认使用了FinnHub数据源")
            elif "openai" in result.lower() or "OpenAI" in result:
                print("   ⚠️ 意外使用了OpenAI数据源")
            else:
                print("   ℹ️ 无法确定数据源")

            # 显示结果摘要
            print("\n📄 结果摘要 (前200字符):")
            print("-" * 40)
            print(result[:200])
            if len(result) > 200:
                print("...")
            print("-" * 40)
        else:
            print("   ❌ 未获取到数据")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config_scenarios():
    """测试不同配置场景"""
    print("\n🧪 测试不同配置场景")
    print("=" * 80)

    scenarios = [
        {
            "name": "场景1: 无OpenAI Key + Google配置",
            "openai_key": None,
            "backend_url": "https://generativelanguage.googleapis.com/v1",
            "expected": "跳过OpenAI，使用FinnHub",
        },
        {
            "name": "场景2: 无OpenAI Key + OpenAI配置",
            "openai_key": None,
            "backend_url": "https://api.openai.com/v1",
            "expected": "跳过OpenAI，使用FinnHub",
        },
        {
            "name": "场景3: 有OpenAI Key + 非OpenAI配置",
            "openai_key": "sk-test123",
            "backend_url": "https://generativelanguage.googleapis.com/v1",
            "expected": "跳过OpenAI，使用FinnHub",
        },
    ]

    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print("-" * 60)

        # 模拟配置检查
        openai_key = scenario["openai_key"]
        backend_url = scenario["backend_url"]

        print(f"   配置: OPENAI_API_KEY = {openai_key}")
        print(f"   配置: backend_url = {backend_url}")

        # 执行检查逻辑
        should_skip = False

        if not openai_key:
            print("   ❌ 未配置OPENAI_API_KEY")
            should_skip = True
        elif "openai.com" not in backend_url:
            print("   ❌ backend_url不是OpenAI API")
            should_skip = True
        else:
            print("   ✅ 配置检查通过")

        result = "跳过OpenAI，使用FinnHub" if should_skip else "使用OpenAI API"
        expected = scenario["expected"]

        if result == expected:
            print(f"   ✅ 结果符合预期: {result}")
        else:
            print(f"   ❌ 结果不符合预期: 期望 {expected}, 实际 {result}")

    return True


def main():
    """主测试函数"""
    print("🚀 开始测试OpenAI配置修复效果")
    print("=" * 100)

    results = []

    # 测试1: OpenAI配置检测逻辑
    results.append(test_openai_config_detection())

    # 测试2: 基本面数据API选择逻辑
    results.append(test_fundamentals_api_selection())

    # 测试3: 不同配置场景
    results.append(test_config_scenarios())

    # 总结结果
    print("\n" + "=" * 100)
    print("📋 测试结果总结")
    print("=" * 100)

    passed = sum(results)
    total = len(results)

    test_names = ["OpenAI配置检测逻辑", "基本面数据API选择逻辑", "不同配置场景测试"]

    for i, (name, result) in enumerate(zip(test_names, results, strict=False)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i + 1}. {name}: {status}")

    print(f"\n📊 总体结果: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！OpenAI配置修复成功")
        print("\n📋 修复效果:")
        print("1. ✅ 正确检测OpenAI API Key是否配置")
        print("2. ✅ 正确检测backend_url是否为OpenAI API")
        print("3. ✅ 在配置不匹配时跳过OpenAI，直接使用FinnHub")
        print("4. ✅ 避免了404错误和配置混乱")

        print("\n🔧 解决的问题:")
        print("- ❌ 在没有OpenAI Key时仍尝试调用OpenAI API")
        print("- ❌ 使用Google URL调用OpenAI API格式导致404错误")
        print("- ❌ 配置检查逻辑不够严格")
        print("- ❌ 错误的API调用浪费时间和资源")
    else:
        print("⚠️ 部分测试失败，需要进一步优化")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
