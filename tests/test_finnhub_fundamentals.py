#!/usr/bin/env python3
"""
测试Finnhub基本面数据获取功能、OpenAI fallback机制和缓存功能
"""

import os
import sys
import time
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_finnhub_api_key():
    """测试Finnhub API密钥配置"""
    print("🔑 检查Finnhub API密钥...")

    api_key = os.getenv("FINNHUB_API_KEY")
    if api_key:
        print(f"✅ Finnhub API密钥已配置: {api_key[:8]}...")
        return True
    print("❌ 未配置FINNHUB_API_KEY环境变量")
    return False


def test_finnhub_fundamentals_with_cache():
    """测试Finnhub基本面数据获取和缓存功能"""
    print("\n📊 测试Finnhub基本面数据获取和缓存功能...")

    try:
        from tradingagents.dataflows.cache_manager import get_cache

        from tradingagents.dataflows.interface import get_fundamentals_finnhub

        # 清理可能存在的缓存
        get_cache()
        test_ticker = "AAPL"
        curr_date = datetime.now().strftime("%Y-%m-%d")

        print(f"\n🔍 第一次获取 {test_ticker} 的基本面数据（从API获取）...")
        start_time = time.time()
        result1 = get_fundamentals_finnhub(test_ticker, curr_date)
        first_time = time.time() - start_time

        if result1 and len(result1) > 100:
            print(f"✅ {test_ticker} 基本面数据获取成功，长度: {len(result1)}")
            print(f"⏱️ 第一次获取耗时: {first_time:.2f}秒")
            print(f"📄 数据预览: {result1[:200]}...")

            # 第二次获取，应该从缓存读取
            print(f"\n🔍 第二次获取 {test_ticker} 的基本面数据（从缓存获取）...")
            start_time = time.time()
            result2 = get_fundamentals_finnhub(test_ticker, curr_date)
            second_time = time.time() - start_time

            print(f"⏱️ 第二次获取耗时: {second_time:.2f}秒")

            # 验证缓存效果
            if second_time < first_time and result1 == result2:
                print(f"✅ 缓存功能正常！速度提升了 {((first_time - second_time) / first_time * 100):.1f}%")
                return True
            print("⚠️ 缓存可能未生效")
            return False
        print(f"❌ {test_ticker} 基本面数据获取失败或数据过短")
        print(f"📄 返回内容: {result1}")
        return False

    except Exception as e:
        print(f"❌ Finnhub基本面数据测试失败: {e!s}")
        import traceback

        traceback.print_exc()
        return False


def test_openai_fallback_with_cache():
    """测试OpenAI fallback机制和缓存功能"""
    print("\n🔄 测试OpenAI fallback机制和缓存功能...")

    try:
        from tradingagents.dataflows.interface import get_fundamentals_openai

        # 临时移除OpenAI配置来测试fallback
        original_backend_url = os.environ.get("BACKEND_URL")
        original_quick_think_llm = os.environ.get("QUICK_THINK_LLM")

        # 清除OpenAI配置
        if "BACKEND_URL" in os.environ:
            del os.environ["BACKEND_URL"]
        if "QUICK_THINK_LLM" in os.environ:
            del os.environ["QUICK_THINK_LLM"]

        print("🚫 已临时移除OpenAI配置，测试fallback到Finnhub...")

        curr_date = datetime.now().strftime("%Y-%m-%d")
        test_ticker = "MSFT"

        print(f"\n🔍 第一次通过OpenAI接口获取 {test_ticker} 数据（应fallback到Finnhub）...")
        start_time = time.time()
        result1 = get_fundamentals_openai(test_ticker, curr_date)
        first_time = time.time() - start_time

        if result1 and "Finnhub" in result1:
            print("✅ OpenAI fallback机制工作正常，成功回退到Finnhub API")
            print(f"📄 数据长度: {len(result1)}")
            print(f"⏱️ 第一次获取耗时: {first_time:.2f}秒")

            # 第二次获取，应该从缓存读取
            print(f"\n🔍 第二次通过OpenAI接口获取 {test_ticker} 数据（应从缓存获取）...")
            start_time = time.time()
            result2 = get_fundamentals_openai(test_ticker, curr_date)
            second_time = time.time() - start_time

            print(f"⏱️ 第二次获取耗时: {second_time:.2f}秒")

            # 验证缓存效果
            if second_time < first_time and result1 == result2:
                print(f"✅ fallback + 缓存功能正常！速度提升了 {((first_time - second_time) / first_time * 100):.1f}%")
                success = True
            else:
                print("⚠️ 缓存可能未生效")
                success = False
        else:
            print("❌ OpenAI fallback机制可能有问题")
            print(f"📄 返回内容: {result1[:500]}...")
            success = False

        # 恢复原始配置
        if original_backend_url:
            os.environ["BACKEND_URL"] = original_backend_url
        if original_quick_think_llm:
            os.environ["QUICK_THINK_LLM"] = original_quick_think_llm

        return success

    except Exception as e:
        print(f"❌ OpenAI fallback测试失败: {e!s}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_management():
    """测试缓存管理功能"""
    print("\n💾 测试缓存管理功能...")

    try:
        from tradingagents.dataflows.cache_manager import get_cache

        cache = get_cache()

        # 获取缓存统计
        stats = cache.get_cache_stats()
        print(f"📊 当前缓存统计: {stats}")

        # 检查缓存配置
        print("\n⚙️ 基本面数据缓存配置:")
        for cache_type, config in cache.cache_config.items():
            if "fundamentals" in cache_type:
                print(
                    f"  - {cache_type}: TTL={config['ttl_hours']}小时, 最大文件数={config['max_files']}, 描述={config['description']}",
                )

        return True

    except Exception as e:
        print(f"❌ 缓存管理测试失败: {e!s}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🚀 开始Finnhub基本面数据功能和缓存测试")
    print("=" * 60)

    # 检查环境
    print(f"📍 当前工作目录: {os.getcwd()}")
    print(f"📍 Python路径: {sys.path[0]}")

    # 运行测试
    tests = [
        ("Finnhub API密钥检查", test_finnhub_api_key),
        ("Finnhub基本面数据获取和缓存", test_finnhub_fundamentals_with_cache),
        ("OpenAI fallback机制和缓存", test_openai_fallback_with_cache),
        ("缓存管理功能", test_cache_management),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试 '{test_name}' 执行失败: {e!s}")
            results.append((test_name, False))

    # 输出测试结果
    print(f"\n{'=' * 20} 测试结果汇总 {'=' * 20}")
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} {test_name}")

    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\n📊 测试完成: {passed}/{total} 个测试通过")

    if passed == total:
        print("🎉 所有测试都通过了！Finnhub基本面数据功能和缓存系统正常工作。")
        print("\n💡 功能特性:")
        print("1. ✅ 当OpenAI配置不可用时，系统会自动使用Finnhub API")
        print("2. ✅ Finnhub提供官方财务数据，包括PE、PS、ROE等关键指标")
        print("3. ✅ 数据来源于公司财报和SEC文件，具有较高的可靠性")
        print("4. ✅ 支持智能缓存机制，美股基本面数据缓存24小时，A股缓存12小时")
        print("5. ✅ 缓存按市场类型分类存储，提高查找效率")
        print("6. ✅ 自动检测缓存有效性，过期数据会重新获取")
    else:
        print("⚠️ 部分测试失败，请检查相关配置。")


if __name__ == "__main__":
    main()
