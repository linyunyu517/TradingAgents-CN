#!/usr/bin/env python3
"""
集成验证测试脚本
测试Web和CLI界面中的股票数据预获取功能是否正常工作
"""

import os
import sys
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_web_integration():
    """测试Web界面集成"""
    print("🌐 测试Web界面集成")
    print("=" * 60)

    try:
        # 导入Web分析运行器
        from web.utils.analysis_runner import run_stock_analysis

        # 模拟Web界面的进度更新函数
        progress_messages = []

        def mock_update_progress(message, current=None, total=None):
            progress_messages.append(message)
            if current and total:
                print(f"📊 进度 {current}/{total}: {message}")
            else:
                print(f"📊 {message}")

        # 测试有效股票代码
        print("\n🧪 测试有效股票代码: 000001 (A股)")
        start_time = time.time()

        try:
            result = run_stock_analysis(
                stock_symbol="000001",
                market_type="A股",
                analysts=["fundamentals"],
                research_depth="快速",
                llm_provider="dashscope",
                llm_model="qwen-plus-latest",
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                progress_callback=mock_update_progress,
            )

            elapsed = time.time() - start_time

            if result and result.get("success"):
                print(f"✅ Web集成测试成功 (耗时: {elapsed:.2f}秒)")
                print(f"📋 分析结果: {result.get('stock_symbol')} - {result.get('session_id')}")
                return True
            print(f"❌ Web集成测试失败: {result.get('error', '未知错误')}")
            return False

        except Exception as e:
            print(f"❌ Web集成测试异常: {e}")
            return False

    except ImportError as e:
        print(f"❌ 无法导入Web模块: {e}")
        return False


def test_cli_integration():
    """测试CLI界面集成"""
    print("\n💻 测试CLI界面集成")
    print("=" * 60)

    try:
        # 导入CLI相关模块

        # 模拟A股市场配置
        a_stock_market = {
            "name": "A股",
            "name_en": "A-Share",
            "default": "000001",
            "examples": ["000001 (平安银行)", "600519 (贵州茅台)", "000858 (五粮液)"],
            "format": "6位数字 (如: 000001)",
            "pattern": r"^\d{6}$",
            "data_source": "china_stock",
        }

        # 测试股票代码格式验证
        print("\n🧪 测试股票代码格式验证")
        import re

        test_codes = [
            ("000001", True, "平安银行"),
            ("600519", True, "贵州茅台"),
            ("999999", True, "格式正确但不存在"),
            ("00001", False, "位数不足"),
            ("AAPL", False, "美股代码"),
            ("", False, "空代码"),
        ]

        validation_success = 0
        for code, should_pass, description in test_codes:
            matches = bool(re.match(a_stock_market["pattern"], code))
            status = "✅" if matches == should_pass else "❌"
            print(f"  {code}: {status} ({description})")
            if matches == should_pass:
                validation_success += 1

        print(
            f"\n📊 格式验证成功率: {validation_success}/{len(test_codes)} ({validation_success / len(test_codes) * 100:.1f}%)",
        )

        # 测试数据预获取功能
        print("\n🧪 测试CLI数据预获取功能")
        from tradingagents.utils.stock_validator import prepare_stock_data

        result = prepare_stock_data("000001", "A股", 7)  # 测试7天数据

        if result.is_valid:
            print(f"✅ CLI数据预获取成功: {result.stock_name}")
            print(f"📊 缓存状态: {result.cache_status}")
            return True
        print(f"❌ CLI数据预获取失败: {result.error_message}")
        return False

    except Exception as e:
        print(f"❌ CLI集成测试异常: {e}")
        return False


def test_error_handling():
    """测试错误处理"""
    print("\n🚨 测试错误处理")
    print("=" * 60)

    try:
        from tradingagents.utils.stock_validator import prepare_stock_data

        # 测试不存在的股票代码
        error_tests = [
            ("999999", "A股", "不存在的A股"),
            ("9999.HK", "港股", "不存在的港股"),
            ("ZZZZ", "美股", "不存在的美股"),
            ("", "A股", "空代码"),
            ("ABC123", "A股", "格式错误"),
        ]

        error_handling_success = 0

        for code, market, description in error_tests:
            print(f"\n🧪 测试: {description} ({code})")

            result = prepare_stock_data(code, market, 7)

            if not result.is_valid:
                print(f"✅ 正确识别错误: {result.error_message}")
                if result.suggestion:
                    print(f"💡 建议: {result.suggestion}")
                error_handling_success += 1
            else:
                print("❌ 未能识别错误，错误地认为股票存在")

        print(
            f"\n📊 错误处理成功率: {error_handling_success}/{len(error_tests)} ({error_handling_success / len(error_tests) * 100:.1f}%)",
        )
        return error_handling_success == len(error_tests)

    except Exception as e:
        print(f"❌ 错误处理测试异常: {e}")
        return False


def test_performance():
    """测试性能表现"""
    print("\n⚡ 测试性能表现")
    print("=" * 60)

    try:
        from tradingagents.utils.stock_validator import prepare_stock_data

        # 测试多个股票的性能
        performance_tests = [("000001", "A股", "平安银行"), ("600519", "A股", "贵州茅台"), ("AAPL", "美股", "苹果公司")]

        total_time = 0
        success_count = 0

        for code, market, name in performance_tests:
            print(f"\n🚀 性能测试: {name} ({code})")

            start_time = time.time()
            result = prepare_stock_data(code, market, 7)
            elapsed = time.time() - start_time

            total_time += elapsed

            if result.is_valid:
                print(f"✅ 成功 (耗时: {elapsed:.2f}秒)")
                success_count += 1

                if elapsed < 5:
                    print("🚀 性能优秀")
                elif elapsed < 15:
                    print("⚡ 性能良好")
                else:
                    print("⚠️ 性能较慢")
            else:
                print(f"❌ 失败: {result.error_message}")

        avg_time = total_time / len(performance_tests)
        print("\n📊 性能总结:")
        print(
            f"   成功率: {success_count}/{len(performance_tests)} ({success_count / len(performance_tests) * 100:.1f}%)",
        )
        print(f"   平均耗时: {avg_time:.2f}秒")
        print(f"   总耗时: {total_time:.2f}秒")

        return success_count >= len(performance_tests) * 0.8  # 80%成功率

    except Exception as e:
        print(f"❌ 性能测试异常: {e}")
        return False


if __name__ == "__main__":
    print("🧪 股票数据预获取集成测试")
    print("=" * 80)
    print("📝 此测试验证Web和CLI界面中的股票验证功能是否正常工作")
    print("=" * 80)

    all_passed = True

    # 1. Web界面集成测试
    if not test_web_integration():
        all_passed = False

    # 2. CLI界面集成测试
    if not test_cli_integration():
        all_passed = False

    # 3. 错误处理测试
    if not test_error_handling():
        all_passed = False

    # 4. 性能测试
    if not test_performance():
        all_passed = False

    # 最终结果
    print("\n🏁 集成测试结果")
    print("=" * 80)
    if all_passed:
        print("🎉 所有集成测试通过！股票数据预获取功能已成功集成到Web和CLI界面")
        print("✨ 功能特点:")
        print("   - ✅ 在分析开始前验证股票是否存在")
        print("   - ✅ 预先获取和缓存历史数据和基本信息")
        print("   - ✅ 避免对假股票代码执行完整分析流程")
        print("   - ✅ 提供友好的错误提示和建议")
        print("   - ✅ 良好的性能表现")
    else:
        print("❌ 部分集成测试失败，建议检查和优化")
        print("🔍 请检查:")
        print("   - Web和CLI界面的导入路径是否正确")
        print("   - 数据源连接是否正常")
        print("   - 网络连接是否稳定")
        print("   - 相关依赖是否正确安装")
