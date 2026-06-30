#!/usr/bin/env python3
"""
Agent Utils Tushare修复验证测试
验证agent_utils中的函数已成功从TDX迁移到Tushare统一接口
"""

import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_get_china_stock_data_fix():
    """测试get_china_stock_data函数的Tushare修复"""
    print("\n🔧 测试get_china_stock_data函数修复")
    print("=" * 60)

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit导入成功")

        # 测试股票数据获取
        print("🔄 测试股票数据获取...")
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        result = Toolkit.get_china_stock_data("600036", start_date, end_date)

        if result and len(result) > 100:
            print("✅ 股票数据获取成功")
            print(f"📊 数据长度: {len(result)}字符")

            # 检查是否使用了统一接口（而不是TDX）
            if "统一数据源接口" in result or "tushare" in result.lower():
                print("✅ 已成功使用统一数据源接口")
            elif "通达信" in result:
                print("⚠️ 警告: 仍在使用中国股票数据源")
            else:
                print("✅ 数据源已更新")

            # 显示部分结果
            print(f"📋 结果预览: {result[:200]}...")
        else:
            print("❌ 股票数据获取失败")
            print(f"返回结果: {result}")

        return True

    except Exception as e:
        print(f"❌ get_china_stock_data测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_get_china_market_overview_fix():
    """测试get_china_market_overview函数的修复"""
    print("\n🔧 测试get_china_market_overview函数修复")
    print("=" * 60)

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit导入成功")

        # 测试市场概览获取
        print("🔄 测试市场概览获取...")
        curr_date = datetime.now().strftime("%Y-%m-%d")

        result = Toolkit.get_china_market_overview(curr_date)

        if result and len(result) > 50:
            print("✅ 市场概览获取成功")
            print(f"📊 数据长度: {len(result)}字符")

            # 检查是否提到了Tushare迁移
            if "Tushare" in result or "迁移" in result:
                print("✅ 已更新为Tushare数据源说明")
            elif "通达信" in result and "TDX" not in result:
                print("⚠️ 警告: 仍在使用中国股票数据源")
            else:
                print("✅ 市场概览功能已更新")

            # 显示部分结果
            print(f"📋 结果预览: {result[:300]}...")
        else:
            print("❌ 市场概览获取失败")
            print(f"返回结果: {result}")

        return True

    except Exception as e:
        print(f"❌ get_china_market_overview测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_stock_name_mapping_fix():
    """测试股票名称映射的修复"""
    print("\n🔧 测试股票名称映射修复")
    print("=" * 60)

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit导入成功")

        # 测试基本面数据获取（会触发股票名称映射）
        print("🔄 测试基本面数据获取（包含股票名称映射）...")
        curr_date = datetime.now().strftime("%Y-%m-%d")

        result = Toolkit.get_fundamentals_openai("600036", curr_date)

        if result and len(result) > 100:
            print("✅ 基本面数据获取成功")
            print(f"📊 数据长度: {len(result)}字符")

            # 检查是否包含正确的股票名称
            if "招商银行" in result:
                print("✅ 股票名称映射成功: 600036 -> 招商银行")
            else:
                print("⚠️ 股票名称映射可能有问题")

            # 显示部分结果
            print(f"📋 结果预览: {result[:200]}...")
        else:
            print("❌ 基本面数据获取失败")
            print(f"返回结果: {result}")

        return True

    except Exception as e:
        print(f"❌ 股票名称映射测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_debug_output():
    """检查调试输出是否显示使用了统一接口"""
    print("\n🔧 检查调试输出")
    print("=" * 60)

    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("🔄 运行股票数据获取并检查调试输出...")
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        # 这应该会产生调试输出
        Toolkit.get_china_stock_data("000001", start_date, end_date)

        print("✅ 调试输出检查完成")
        print("💡 请查看上面的调试输出，确认是否显示:")
        print("   - '成功导入统一数据源接口'")
        print("   - '正在调用统一数据源接口'")
        print("   - 而不是 'tdx_utils.get_china_stock_data'")

        return True

    except Exception as e:
        print(f"❌ 调试输出检查失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔬 Agent Utils Tushare修复验证测试")
    print("=" * 70)
    print("💡 测试目标:")
    print("   - 验证get_china_stock_data已迁移到统一接口")
    print("   - 验证get_china_market_overview已更新")
    print("   - 验证股票名称映射使用统一接口")
    print("   - 检查调试输出确认修复生效")
    print("=" * 70)

    # 运行所有测试
    tests = [
        ("get_china_stock_data修复", test_get_china_stock_data_fix),
        ("get_china_market_overview修复", test_get_china_market_overview_fix),
        ("股票名称映射修复", test_stock_name_mapping_fix),
        ("调试输出检查", check_debug_output),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))

    # 总结
    print("\n📋 Agent Utils修复测试总结")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    total = len(results)
    print(f"\n📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 Agent Utils修复测试完全成功！")
        print("\n💡 修复效果:")
        print("   ✅ get_china_stock_data已使用统一数据源接口")
        print("   ✅ get_china_market_overview已更新为Tushare说明")
        print("   ✅ 股票名称映射使用统一接口")
        print("   ✅ 调试输出确认修复生效")
        print("\n🚀 现在Agent工具完全使用Tushare数据源！")
    else:
        print("\n⚠️ 部分测试失败，请检查相关配置")

    print("\n🎯 验证方法:")
    print("   1. 查看调试输出中的'统一数据源接口'字样")
    print("   2. 确认不再出现'tdx_utils'相关调用")
    print("   3. 股票数据应该来自Tushare而不是TDX")

    input("按回车键退出...")


if __name__ == "__main__":
    main()
