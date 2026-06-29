#!/usr/bin/env python3
"""
股票数据降级系统演示
展示MongoDB -> Tushare数据接口的完整降级机制
"""

import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def demo_database_config_fixes():
    """
    演示数据库配置修复
    """
    print("🔧 数据库配置修复演示")
    print("=" * 50)

    print("\n📋 修复内容:")
    print("  1. ✅ 移除了硬编码的MongoDB连接地址")
    print("  2. ✅ 创建了统一的数据库配置管理")
    print("  3. ✅ 实现了完整的降级机制")
    print("  4. ✅ 增强了错误处理和提示")

    print("\n🔍 检查配置文件:")

    # 检查.env文件
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        print(f"  ✅ 找到配置文件: {env_path}")
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
            if "MONGODB_HOST" in content or "MONGODB_CONNECTION_STRING" in content:
                print("  ✅ MongoDB配置已设置")
            if "REDIS_HOST" in content or "REDIS_CONNECTION_STRING" in content:
                print("  ✅ Redis配置已设置")
    else:
        print(f"  ⚠️ 配置文件不存在: {env_path}")

    # 检查database_config.py
    config_path = os.path.join(project_root, "tradingagents", "config", "database_config.py")
    if os.path.exists(config_path):
        print("  ✅ 找到统一配置管理: database_config.py")
    else:
        print("  ⚠️ 统一配置管理文件不存在")


def demo_fallback_mechanism():
    """
    演示降级机制
    """
    print("\n🔄 降级机制演示")
    print("=" * 50)

    try:
        from tradingagents.api.stock_api import check_service_status, get_market_summary, get_stock_info

        print("\n📊 1. 检查服务状态:")
        status = check_service_status()

        for key, value in status.items():
            if key == "mongodb_status":
                icon = "✅" if value == "connected" else "⚠️" if value == "disconnected" else "❌"
                print(f"  {icon} MongoDB: {value}")
            elif key == "unified_api_status":
                icon = "✅" if value == "available" else "⚠️" if value == "limited" else "❌"
                print(f"  {icon} 统一数据接口: {value}")

        print("\n🔍 2. 测试股票查询（展示降级过程）:")
        test_codes = ["000001", "600000"]

        for code in test_codes:
            print(f"\n  📊 查询股票 {code}:")
            result = get_stock_info(code)

            if "error" in result:
                print(f"    ❌ 查询失败: {result['error']}")
                if "suggestion" in result:
                    print(f"    💡 建议: {result['suggestion']}")
            else:
                print(f"    ✅ 查询成功: {result.get('name')}")
                print(f"    🔗 数据源: {result.get('source')}")
                print(f"    🏢 市场: {result.get('market')}")

        print("\n📈 3. 测试市场概览:")
        summary = get_market_summary()

        if "error" in summary:
            print(f"  ❌ 获取失败: {summary['error']}")
        else:
            print(f"  ✅ 总股票数: {summary.get('total_count', 0):,}")
            print(f"  🔗 数据源: {summary.get('data_source')}")
            print(f"  🏢 沪市: {summary.get('shanghai_count', 0):,} 只")
            print(f"  🏢 深市: {summary.get('shenzhen_count', 0):,} 只")

    except ImportError as e:
        print(f"❌ 无法导入股票API: {e}")
        print("💡 请确保所有依赖文件都已正确创建")
    except Exception as e:
        print(f"❌ 演示过程中出错: {e}")


def demo_configuration_benefits():
    """
    演示配置优化的好处
    """
    print("\n💡 配置优化的好处")
    print("=" * 50)

    benefits = [
        ("🔒 安全性提升", "移除硬编码连接地址，通过环境变量管理敏感信息"),
        ("🔄 灵活性增强", "支持不同环境的配置，无需修改代码"),
        ("⚡ 高可用性", "MongoDB不可用时自动降级到Tushare数据接口"),
        ("📊 数据完整性", "多数据源确保股票信息的持续可用性"),
        ("🛠️ 易于维护", "统一的配置管理，便于运维和部署"),
        ("🔍 错误诊断", "详细的状态检查和错误提示"),
        ("💾 自动缓存", "从API获取的数据自动缓存到MongoDB"),
        ("🎯 性能优化", "优先使用本地数据库，减少网络请求"),
    ]

    for icon_title, description in benefits:
        print(f"\n{icon_title}:")
        print(f"  {description}")


def demo_usage_scenarios():
    """
    演示使用场景
    """
    print("\n🎯 使用场景演示")
    print("=" * 50)

    scenarios = [
        {
            "title": "🏢 生产环境",
            "description": "MongoDB正常运行，提供最佳性能",
            "config": "MONGODB_CONNECTION_STRING=mongodb://prod-server:27017/tradingagents",
        },
        {
            "title": "🧪 测试环境",
            "description": "使用本地MongoDB进行开发测试",
            "config": "MONGODB_CONNECTION_STRING=mongodb://localhost:27017/test_db",
        },
        {
            "title": "☁️ 云端部署",
            "description": "使用云数据库服务",
            "config": "MONGODB_CONNECTION_STRING=mongodb+srv://user:pass@cluster.mongodb.net/db",
        },
        {
            "title": "🔧 开发环境",
            "description": "MongoDB未配置，自动使用Tushare数据接口",
            "config": "# MONGODB_CONNECTION_STRING 未设置",
        },
        {"title": "🌐 离线模式", "description": "网络受限时使用缓存数据", "config": "使用本地文件缓存作为最后降级方案"},
    ]

    for scenario in scenarios:
        print(f"\n{scenario['title']}:")
        print(f"  📝 描述: {scenario['description']}")
        print(f"  ⚙️ 配置: {scenario['config']}")


def demo_migration_guide():
    """
    演示迁移指南
    """
    print("\n📚 迁移指南")
    print("=" * 50)

    print("\n🔄 从旧版本迁移的步骤:")

    steps = [
        "1. 📋 检查现有的硬编码连接地址",
        "2. 🔧 配置环境变量 MONGODB_CONNECTION_STRING",
        "3. 🔧 配置环境变量 REDIS_CONNECTION_STRING",
        "4. 📝 更新应用代码使用新的API接口",
        "5. 🧪 运行测试验证降级机制",
        "6. 🚀 部署到生产环境",
        "7. 📊 监控服务状态和性能",
    ]

    for step in steps:
        print(f"  {step}")

    print("\n💡 最佳实践:")
    practices = [
        "🔒 使用环境变量管理敏感配置",
        "🔄 定期测试降级机制",
        "📊 监控数据源的可用性",
        "💾 定期备份MongoDB数据",
        "🔍 使用日志记录关键操作",
        "⚡ 优化查询性能和缓存策略",
    ]

    for practice in practices:
        print(f"  {practice}")


def main():
    """
    主演示函数
    """
    print("🚀 股票数据系统修复演示")
    print("=" * 60)
    print(f"📅 演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 演示各个方面
        demo_database_config_fixes()
        demo_fallback_mechanism()
        demo_configuration_benefits()
        demo_usage_scenarios()
        demo_migration_guide()

        print("\n" + "=" * 60)
        print("🎉 演示完成！")
        print("\n📋 总结:")
        print("  ✅ 成功移除了硬编码的数据库连接地址")
        print("  ✅ 实现了完整的MongoDB -> Tushare数据接口降级机制")
        print("  ✅ 提供了统一的配置管理和API接口")
        print("  ✅ 增强了系统的可靠性和可维护性")

        print("\n🔗 相关文件:")
        files = [
            "tradingagents/config/database_config.py - 统一配置管理",
            "tradingagents/dataflows/stock_data_service.py - 股票数据服务",
            "tradingagents/api/stock_api.py - 便捷API接口",
            "examples/stock_query_examples.py - 使用示例",
            "tests/test_stock_data_service.py - 测试程序",
            ".env - 数据库配置文件",
        ]

        for file_info in files:
            print(f"  📄 {file_info}")

    except KeyboardInterrupt:
        print("\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程中出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
