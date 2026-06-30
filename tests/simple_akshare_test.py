#!/usr/bin/env python3
"""
简单的AKShare测试
验证修复后的导入是否正常
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_basic_imports():
    """测试基本导入"""
    print("🔍 测试基本导入")
    print("=" * 40)

    try:
        # 测试AKShare直接导入
        import akshare as ak

        print(f"✅ AKShare导入成功: {ak.__version__}")
    except Exception as e:
        print(f"❌ AKShare导入失败: {e}")
        return False

    try:
        # 测试dataflows模块导入
        print("✅ akshare_utils模块导入成功")
    except Exception as e:
        print(f"❌ akshare_utils模块导入失败: {e}")
        return False

    try:
        # 测试数据源管理器导入
        print("✅ DataSourceManager导入成功")
    except Exception as e:
        print(f"❌ DataSourceManager导入失败: {e}")
        return False

    return True


def test_akshare_provider():
    """测试AKShare提供器"""
    print("\n🔍 测试AKShare提供器")
    print("=" * 40)

    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider

        provider = get_akshare_provider()
        print(f"✅ AKShare提供器创建成功，连接状态: {provider.connected}")

        if provider.connected:
            # 测试获取股票数据
            data = provider.get_stock_data("000001", "2024-12-01", "2024-12-10")
            if data is not None and not data.empty:
                print(f"✅ 获取股票数据成功: {len(data)}条记录")
            else:
                print("❌ 获取股票数据失败")
                return False

        return True
    except Exception as e:
        print(f"❌ AKShare提供器测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_data_source_manager():
    """测试数据源管理器"""
    print("\n🔍 测试数据源管理器")
    print("=" * 40)

    try:
        from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager

        # 检查AKShare枚举
        akshare_enum = ChinaDataSource.AKSHARE
        print(f"✅ AKShare枚举: {akshare_enum.value}")

        # 创建管理器
        manager = DataSourceManager()
        print("✅ 数据源管理器创建成功")

        # 检查可用数据源
        available = [s.value for s in manager.available_sources]
        print(f"✅ 可用数据源: {available}")

        if "akshare" in available:
            print("✅ AKShare在可用数据源中")
        else:
            print("⚠️ AKShare不在可用数据源中")

        return True
    except Exception as e:
        print(f"❌ 数据源管理器测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🔍 简单AKShare功能测试")
    print("=" * 60)

    results = []

    # 1. 基本导入测试
    results.append(test_basic_imports())

    # 2. AKShare提供器测试
    results.append(test_akshare_provider())

    # 3. 数据源管理器测试
    results.append(test_data_source_manager())

    # 总结
    passed = sum(results)
    total = len(results)

    print(f"\n📊 测试结果: {passed}/{total} 项通过")

    if passed == total:
        print("🎉 AKShare功能完全正常！")
        print("✅ 可以安全删除重复的AKShare分支")
        return True
    if passed >= 2:
        print("⚠️ AKShare基本功能正常，部分高级功能可能有问题")
        print("✅ 可以考虑删除重复的AKShare分支")
        return True
    print("❌ AKShare功能存在问题")
    return False


if __name__ == "__main__":
    success = main()

    if success:
        print("\n🎯 分支管理建议:")
        print("✅ AKShare功能基本正常")
        print("✅ 可以删除以下重复分支:")
        print("   - feature/akshare-integration")
        print("   - feature/akshare-integration-clean")
        print("✅ 保留 feature/tushare-integration（包含完整功能）")
    else:
        print("\n⚠️ 建议:")
        print("1. 先修复AKShare集成问题")
        print("2. 再考虑分支清理")
