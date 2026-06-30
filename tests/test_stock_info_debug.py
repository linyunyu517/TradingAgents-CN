#!/usr/bin/env python3
"""
股票信息获取调试测试
专门诊断为什么某些股票显示"未知公司"
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_stock_code_normalization():
    """测试股票代码标准化"""
    print("\n🔧 测试股票代码标准化")
    print("=" * 60)

    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider

        provider = get_tushare_provider()

        test_codes = ["000858", "600036", "000001", "300001"]

        for code in test_codes:
            normalized = provider._normalize_symbol(code)
            print(f"📊 {code} -> {normalized}")

        return True

    except Exception as e:
        print(f"❌ 股票代码标准化测试失败: {e}")
        return False


def test_tushare_api_direct():
    """直接测试Tushare API"""
    print("\n🔧 直接测试Tushare API")
    print("=" * 60)

    try:
        import os

        import tushare as ts

        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            print("❌ TUSHARE_TOKEN未设置")
            return False

        ts.set_token(token)
        pro = ts.pro_api()

        # 测试获取000858的信息
        print("🔄 测试获取000858.SZ的基本信息...")

        try:
            basic_info = pro.stock_basic(
                ts_code="000858.SZ", fields="ts_code,symbol,name,area,industry,market,list_date",
            )

            if not basic_info.empty:
                info = basic_info.iloc[0]
                print("✅ 找到股票信息:")
                print(f"   代码: {info['ts_code']}")
                print(f"   名称: {info['name']}")
                print(f"   行业: {info.get('industry', 'N/A')}")
                print(f"   地区: {info.get('area', 'N/A')}")
                return True
            print("❌ 未找到000858.SZ的信息")

            # 尝试搜索所有包含858的股票
            print("🔄 搜索所有包含858的股票...")
            all_stocks = pro.stock_basic(
                exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,market,list_date",
            )

            matches = all_stocks[all_stocks["symbol"].str.contains("858", na=False)]
            if not matches.empty:
                print(f"✅ 找到{len(matches)}只包含858的股票:")
                for _idx, row in matches.iterrows():
                    print(f"   {row['ts_code']} - {row['name']}")
            else:
                print("❌ 未找到任何包含858的股票")

            return False

        except Exception as e:
            print(f"❌ API调用失败: {e}")
            return False

    except Exception as e:
        print(f"❌ Tushare API测试失败: {e}")
        return False


def test_stock_list_search():
    """测试股票列表搜索"""
    print("\n🔧 测试股票列表搜索")
    print("=" * 60)

    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider

        provider = get_tushare_provider()

        if not provider.connected:
            print("❌ Tushare未连接")
            return False

        # 获取股票列表
        print("🔄 获取完整股票列表...")
        stock_list = provider.get_stock_list()

        if stock_list.empty:
            print("❌ 股票列表为空")
            return False

        print(f"✅ 获取到{len(stock_list)}只股票")

        # 搜索000858
        print("🔄 搜索000858...")
        matches = stock_list[stock_list["symbol"] == "000858"]

        if not matches.empty:
            print("✅ 找到000858:")
            for _idx, row in matches.iterrows():
                print(f"   {row['ts_code']} - {row['name']} - {row.get('industry', 'N/A')}")
        else:
            print("❌ 在股票列表中未找到000858")

            # 搜索包含858的股票
            partial_matches = stock_list[stock_list["symbol"].str.contains("858", na=False)]
            if not partial_matches.empty:
                print(f"✅ 找到{len(partial_matches)}只包含858的股票:")
                for _idx, row in partial_matches.head(5).iterrows():
                    print(f"   {row['ts_code']} - {row['name']}")

        return True

    except Exception as e:
        print(f"❌ 股票列表搜索失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_alternative_stock_codes():
    """测试其他股票代码"""
    print("\n🔧 测试其他股票代码")
    print("=" * 60)

    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter

        adapter = get_tushare_adapter()

        # 测试几个已知的股票代码
        test_codes = [
            ("000001", "平安银行"),
            ("600036", "招商银行"),
            ("000002", "万科A"),
            ("600519", "贵州茅台"),
            ("000858", "五粮液"),  # 这个可能是问题代码
        ]

        for code, expected_name in test_codes:
            print(f"🔄 测试 {code} (期望: {expected_name})...")

            info = adapter.get_stock_info(code)

            if info and info.get("name") and info["name"] != f"股票{code}":
                print(f"✅ {code}: {info['name']}")
                if expected_name in info["name"]:
                    print("   ✅ 名称匹配")
                else:
                    print(f"   ⚠️ 名称不匹配，期望: {expected_name}")
            else:
                print(f"❌ {code}: 获取失败或返回未知")

        return True

    except Exception as e:
        print(f"❌ 其他股票代码测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔍 股票信息获取调试测试")
    print("=" * 70)
    print("💡 调试目标:")
    print("   - 诊断为什么000858显示'未知公司'")
    print("   - 检查股票代码标准化")
    print("   - 验证Tushare API响应")
    print("   - 测试股票列表搜索")
    print("=" * 70)

    # 运行所有测试
    tests = [
        ("股票代码标准化", test_stock_code_normalization),
        ("Tushare API直接测试", test_tushare_api_direct),
        ("股票列表搜索", test_stock_list_search),
        ("其他股票代码测试", test_alternative_stock_codes),
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
    print("\n📋 股票信息调试测试总结")
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
        print("\n🎉 所有测试通过！")
        print("💡 如果000858仍显示未知，可能是:")
        print("   1. 该股票代码在Tushare中不存在")
        print("   2. 股票已退市或暂停交易")
        print("   3. 需要使用不同的查询方式")
    else:
        print("\n⚠️ 部分测试失败，请检查具体问题")

    input("按回车键退出...")


if __name__ == "__main__":
    main()
