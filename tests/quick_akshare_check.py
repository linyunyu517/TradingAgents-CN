#!/usr/bin/env python3
"""
快速AKShare功能检查
"""


def check_akshare_import():
    """检查AKShare导入"""
    try:
        import akshare as ak

        print(f"✅ AKShare导入成功，版本: {ak.__version__}")
        return True
    except ImportError as e:
        print(f"❌ AKShare导入失败: {e}")
        print("💡 请安装AKShare: pip install akshare")
        return False


def check_akshare_utils():
    """检查akshare_utils.py"""
    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider

        provider = get_akshare_provider()
        print(f"✅ AKShare工具模块正常，连接状态: {provider.connected}")
        return True, provider
    except Exception as e:
        print(f"❌ AKShare工具模块异常: {e}")
        return False, None


def check_data_source_manager():
    """检查数据源管理器"""
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager

        manager = DataSourceManager()

        available = [s.value for s in manager.available_sources]
        if "akshare" in available:
            print("✅ AKShare在可用数据源中")
        else:
            print("⚠️ AKShare不在可用数据源中")

        return True
    except Exception as e:
        print(f"❌ 数据源管理器检查失败: {e}")
        return False


def test_basic_akshare():
    """测试基本AKShare功能"""
    try:
        import akshare as ak

        # 测试获取股票列表
        print("📊 测试获取股票列表...")
        stock_list = ak.stock_info_a_code_name()
        print(f"✅ 获取到{len(stock_list)}只股票")

        # 测试获取股票数据
        print("📈 测试获取股票数据...")
        data = ak.stock_zh_a_hist(
            symbol="000001", period="daily", start_date="20241201", end_date="20241210", adjust="",
        )
        print(f"✅ 获取到{len(data)}条数据")

        return True
    except Exception as e:
        print(f"❌ AKShare基本功能测试失败: {e}")
        return False


def main():
    """主检查函数"""
    print("🔍 AKShare功能快速检查")
    print("=" * 40)

    results = []

    # 1. 检查导入
    results.append(check_akshare_import())

    # 2. 检查工具模块
    success, _provider = check_akshare_utils()
    results.append(success)

    # 3. 检查数据源管理器
    results.append(check_data_source_manager())

    # 4. 测试基本功能
    if results[0]:  # 如果导入成功
        results.append(test_basic_akshare())

    # 总结
    passed = sum(results)
    total = len(results)

    print(f"\n📊 检查结果: {passed}/{total} 项通过")

    if passed == total:
        print("🎉 AKShare功能完全可用！")
    else:
        print("⚠️ AKShare功能存在问题")

    return passed == total


if __name__ == "__main__":
    main()
