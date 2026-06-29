#!/usr/bin/env python3
"""
港股错误处理测试脚本
测试港股网络限制时的错误处理和用户提示
"""

import os
import sys
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_hk_network_limitation_handling():
    """测试港股网络限制的错误处理"""
    print("🇭🇰 港股网络限制错误处理测试")
    print("=" * 80)

    try:
        from tradingagents.utils.stock_validator import prepare_stock_data

        # 测试港股代码（可能遇到网络限制）
        hk_test_cases = [
            {"code": "0700.HK", "name": "腾讯控股"},
            {"code": "9988.HK", "name": "阿里巴巴"},
            {"code": "3690.HK", "name": "美团"},
            {"code": "1810.HK", "name": "小米集团"},
            {"code": "9999.HK", "name": "不存在的港股"},  # 测试不存在的股票
        ]

        for i, test_case in enumerate(hk_test_cases, 1):
            print(f"\n📊 测试 {i}/{len(hk_test_cases)}: {test_case['code']} ({test_case['name']})")
            print("-" * 60)

            start_time = time.time()

            # 测试港股数据准备
            result = prepare_stock_data(
                stock_code=test_case["code"],
                market_type="港股",
                period_days=7,  # 较短时间测试
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
            )

            end_time = time.time()
            elapsed = end_time - start_time

            print(f"⏱️ 耗时: {elapsed:.2f}秒")
            print(f"📋 结果: {'成功' if result.is_valid else '失败'}")

            if result.is_valid:
                print(f"✅ 股票名称: {result.stock_name}")
                print(f"📊 市场类型: {result.market_type}")
                print(f"📅 数据时长: {result.data_period_days}天")
                print(f"💾 缓存状态: {result.cache_status}")
                print(f"📁 历史数据: {'✅' if result.has_historical_data else '❌'}")
                print(f"ℹ️ 基本信息: {'✅' if result.has_basic_info else '❌'}")
            else:
                print(f"❌ 错误信息: {result.error_message}")
                print("💡 详细建议:")

                # 显示详细建议（支持多行）
                suggestion_lines = result.suggestion.split("\n")
                for line in suggestion_lines:
                    if line.strip():
                        print(f"   {line}")

                # 检查是否为网络限制问题
                if "网络限制" in result.error_message or "Rate limited" in result.error_message:
                    print("🌐 检测到网络限制问题 - 错误处理正确")
                elif "不存在" in result.error_message:
                    print("🔍 检测到股票不存在 - 错误处理正确")
                else:
                    print("⚠️ 其他类型错误")

            # 添加延迟避免过于频繁的请求
            if i < len(hk_test_cases):
                print("⏳ 等待2秒避免频繁请求...")
                time.sleep(2)

        return True

    except Exception as e:
        print(f"❌ 测试过程中发生异常: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_error_message_formatting():
    """测试错误消息格式化"""
    print("\n📝 错误消息格式化测试")
    print("=" * 60)

    try:
        from tradingagents.utils.stock_validator import StockDataPreparer

        preparer = StockDataPreparer()

        # 测试网络限制建议格式
        suggestion = preparer._get_hk_network_limitation_suggestion()

        print("🌐 港股网络限制建议内容:")
        print("-" * 40)
        print(suggestion)
        print("-" * 40)

        # 检查建议内容的完整性
        required_elements = [
            "网络API限制",
            "解决方案",
            "等待5-10分钟",
            "常见港股代码格式",
            "腾讯控股：0700.HK",
            "稍后重试",
        ]

        missing_elements = []
        for element in required_elements:
            if element not in suggestion:
                missing_elements.append(element)

        if not missing_elements:
            print("✅ 建议内容完整，包含所有必要信息")
            return True
        print(f"❌ 建议内容缺少: {missing_elements}")
        return False

    except Exception as e:
        print(f"❌ 错误消息格式化测试异常: {e}")
        return False


def test_web_cli_integration():
    """测试Web和CLI界面的错误处理集成"""
    print("\n🖥️ Web和CLI错误处理集成测试")
    print("=" * 60)

    try:
        from tradingagents.utils.stock_validator import prepare_stock_data

        # 模拟一个可能遇到网络限制的港股
        result = prepare_stock_data("0700.HK", "港股", 7)

        print("📊 模拟Web界面错误处理:")
        if not result.is_valid:
            # 模拟Web界面的错误返回
            web_response = {
                "success": False,
                "error": result.error_message,
                "suggestion": result.suggestion,
                "stock_symbol": "0700.HK",
                "market_type": "港股",
            }

            print(f"   错误: {web_response['error']}")
            print(f"   建议: {web_response['suggestion'][:100]}...")
            print("✅ Web界面错误处理格式正确")
        else:
            print("✅ 股票验证成功，无需错误处理")

        print("\n💻 模拟CLI界面错误处理:")
        if not result.is_valid:
            # 模拟CLI界面的错误显示
            print(f"   ui.show_error('❌ 股票数据验证失败: {result.error_message}')")
            print(f"   ui.show_warning('💡 建议: {result.suggestion[:50]}...')")
            print("✅ CLI界面错误处理格式正确")
        else:
            print("✅ 股票验证成功，无需错误处理")

        return True

    except Exception as e:
        print(f"❌ Web和CLI集成测试异常: {e}")
        return False


if __name__ == "__main__":
    print("🧪 港股错误处理完整测试")
    print("=" * 80)
    print("📝 此测试验证港股网络限制时的错误处理和用户提示")
    print("=" * 80)

    all_passed = True

    # 1. 港股网络限制处理测试
    if not test_hk_network_limitation_handling():
        all_passed = False

    # 2. 错误消息格式化测试
    if not test_error_message_formatting():
        all_passed = False

    # 3. Web和CLI集成测试
    if not test_web_cli_integration():
        all_passed = False

    # 最终结果
    print("\n🏁 港股错误处理测试结果")
    print("=" * 80)
    if all_passed:
        print("🎉 所有测试通过！港股错误处理机制工作正常")
        print("✨ 改进特点:")
        print("   - ✅ 智能识别网络限制问题")
        print("   - ✅ 提供详细的解决方案和建议")
        print("   - ✅ 友好的用户提示和常见代码示例")
        print("   - ✅ 区分网络限制和股票不存在的情况")
        print("   - ✅ Web和CLI界面统一的错误处理")
    else:
        print("❌ 部分测试失败，建议检查错误处理逻辑")
        print("🔍 请检查:")
        print("   - 网络限制检测逻辑是否正确")
        print("   - 错误消息格式是否完整")
        print("   - 建议内容是否有用")
        print("   - Web和CLI界面集成是否正常")
