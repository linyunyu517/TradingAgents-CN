"""
测试港股验证修复
"""

import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_hk_validation():
    """测试港股验证"""
    print("🧪 测试港股验证修复...")

    try:
        from web.utils.analysis_runner import validate_analysis_params

        # 测试用例
        test_cases = [
            # (股票代码, 市场类型, 应该通过验证)
            ("0700.HK", "港股", True),
            ("9988.HK", "港股", True),
            ("3690.HK", "港股", True),
            ("0700", "港股", True),
            ("9988", "港股", True),
            ("3690", "港股", True),
            ("AAPL", "港股", False),  # 美股代码
            ("000001", "港股", False),  # A股代码
            ("00", "港股", False),  # 太短
            ("12345", "港股", False),  # 太长
            ("ABC.HK", "港股", False),  # 非数字
        ]

        passed = 0
        total = len(test_cases)

        for symbol, market_type, should_pass in test_cases:
            is_valid, errors = validate_analysis_params(
                stock_symbol=symbol,
                analysis_date="2025-07-14",
                analysts=["market"],
                research_depth=3,
                market_type=market_type,
            )

            validation_passed = is_valid

            if validation_passed == should_pass:
                print(f"  ✅ {symbol} ({market_type}): {'通过' if validation_passed else '失败'}")
                passed += 1
            else:
                print(
                    f"  ❌ {symbol} ({market_type}): 期望{'通过' if should_pass else '失败'}, 实际{'通过' if validation_passed else '失败'}",
                )
                if errors:
                    print(f"      错误: {errors}")

        print(f"\n验证测试结果: {passed}/{total} 通过")

        if passed == total:
            print("🎉 所有验证测试通过！")
            return True
        print("⚠️ 部分验证测试失败")
        return False

    except Exception as e:
        print(f"❌ 验证测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_specific_case():
    """测试具体的0700.HK案例"""
    print("\n🧪 测试具体的0700.HK案例...")

    try:
        from web.utils.analysis_runner import validate_analysis_params

        # 测试0700.HK
        is_valid, errors = validate_analysis_params(
            stock_symbol="0700.HK",
            analysis_date="2025-07-14",
            analysts=["market", "fundamentals"],
            research_depth=3,
            market_type="港股",
        )

        print("  股票代码: 0700.HK")
        print("  市场类型: 港股")
        print(f"  验证结果: {'通过' if is_valid else '失败'}")

        if not is_valid:
            print(f"  错误信息: {errors}")
            return False
        print("  ✅ 0700.HK验证通过！")
        return True

    except Exception as e:
        print(f"❌ 具体案例测试失败: {e}")
        return False


def test_regex_patterns():
    """测试正则表达式模式"""
    print("\n🧪 测试正则表达式模式...")

    try:
        import re

        # 测试港股正则模式（支持4-5位数字）
        hk_pattern = r"^\d{4,5}\.HK$"
        digit_pattern = r"^\d{4}$"

        test_symbols = ["0700.HK", "9988.HK", "3690.HK", "0700", "9988", "3690", "AAPL", "000001", "ABC.HK"]

        for symbol in test_symbols:
            symbol_upper = symbol.upper()
            hk_match = re.match(hk_pattern, symbol_upper)
            digit_match = re.match(digit_pattern, symbol)

            matches = bool(hk_match or digit_match)

            print(f"  {symbol}: HK格式={bool(hk_match)}, 数字格式={bool(digit_match)}, 总体匹配={matches}")

        return True

    except Exception as e:
        print(f"❌ 正则表达式测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("🔧 港股验证修复测试")
    print("=" * 40)

    tests = [test_regex_patterns, test_specific_case, test_hk_validation]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ 测试 {test_func.__name__} 异常: {e}")

    print("\n" + "=" * 40)
    print(f"🔧 修复测试完成: {passed}/{total} 通过")

    if passed == total:
        print("🎉 港股验证修复成功！")
        print("\n现在可以正常使用0700.HK进行分析了")
    else:
        print("⚠️ 修复可能不完整，请检查失败的测试")


if __name__ == "__main__":
    main()
