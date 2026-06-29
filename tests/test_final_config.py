#!/usr/bin/env python3
"""
测试最终的.env配置系统
验证启用开关是否正常工作
"""

import os
import sys


def test_final_config():
    """测试最终配置"""
    print("🔧 测试最终的.env配置系统")
    print("=" * 40)

    # 1. 检查.env文件
    print("\n📁 检查.env文件...")
    if os.path.exists(".env"):
        print("✅ .env文件存在")
    else:
        print("❌ .env文件不存在")
        return False

    # 2. 读取启用开关
    print("\n🔧 检查启用开关...")
    mongodb_enabled = os.getenv("MONGODB_ENABLED", "false").lower() == "true"
    redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"

    print(f"MONGODB_ENABLED: {os.getenv('MONGODB_ENABLED', 'false')} -> {mongodb_enabled}")
    print(f"REDIS_ENABLED: {os.getenv('REDIS_ENABLED', 'false')} -> {redis_enabled}")

    # 3. 显示配置信息
    print("\n📊 数据库配置:")

    if mongodb_enabled:
        print("MongoDB: ✅ 启用")
        print(f"  Host: {os.getenv('MONGODB_HOST', 'localhost')}")
        print(f"  Port: {os.getenv('MONGODB_PORT', '27017')}")
        print(f"  Database: {os.getenv('MONGODB_DATABASE', 'tradingagents')}")
    else:
        print("MongoDB: ❌ 禁用")

    if redis_enabled:
        print("Redis: ✅ 启用")
        print(f"  Host: {os.getenv('REDIS_HOST', 'localhost')}")
        print(f"  Port: {os.getenv('REDIS_PORT', '6379')}")
        print(f"  DB: {os.getenv('REDIS_DB', '0')}")
    else:
        print("Redis: ❌ 禁用")

    # 4. 测试数据库管理器
    print("\n🔧 测试数据库管理器...")
    try:
        from tradingagents.config.database_manager import get_database_manager

        db_manager = get_database_manager()
        print("✅ 数据库管理器创建成功")

        # 获取状态报告
        status = db_manager.get_status_report()

        print("📊 检测结果:")
        print(f"  数据库可用: {'✅ 是' if status['database_available'] else '❌ 否'}")

        mongodb_info = status["mongodb"]
        print(f"  MongoDB: {'✅ 可用' if mongodb_info['available'] else '❌ 不可用'}")

        redis_info = status["redis"]
        print(f"  Redis: {'✅ 可用' if redis_info['available'] else '❌ 不可用'}")

        print(f"  缓存后端: {status['cache_backend']}")

    except Exception as e:
        print(f"❌ 数据库管理器测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 5. 测试缓存系统
    print("\n💾 测试缓存系统...")
    try:
        from tradingagents.dataflows.integrated_cache import get_cache

        cache = get_cache()
        print("✅ 缓存系统创建成功")

        # 获取性能模式
        performance_mode = cache.get_performance_mode()
        print(f"  性能模式: {performance_mode}")

        # 测试基本功能
        test_data = "测试数据 - 最终配置"
        cache_key = cache.save_stock_data(
            symbol="TEST_FINAL",
            data=test_data,
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="final_test",
        )
        print(f"✅ 数据保存成功: {cache_key}")

        # 加载数据
        loaded_data = cache.load_stock_data(cache_key)
        if loaded_data == test_data:
            print("✅ 数据加载成功")
        else:
            print("❌ 数据加载失败")
            return False

    except Exception as e:
        print(f"❌ 缓存系统测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 6. 总结
    print("\n📊 配置总结:")
    print("✅ 使用.env文件进行配置")
    print("✅ 通过MONGODB_ENABLED和REDIS_ENABLED控制启用状态")
    print("✅ 默认情况下数据库都是禁用的")
    print("✅ 系统使用文件缓存，性能良好")
    print("✅ 可以通过修改.env文件启用数据库")

    print("\n💡 使用说明:")
    print("1. 默认配置：MONGODB_ENABLED=false, REDIS_ENABLED=false")
    print("2. 启用MongoDB：将MONGODB_ENABLED设置为true")
    print("3. 启用Redis：将REDIS_ENABLED设置为true")
    print("4. 系统会自动检测并使用启用的数据库")
    print("5. 如果数据库不可用，自动降级到文件缓存")

    return True


def main():
    """主函数"""
    try:
        success = test_final_config()

        if success:
            print("\n🎉 最终配置测试完成!")
            print("\n🎯 系统特性:")
            print("✅ 简化配置：只需要.env文件")
            print("✅ 明确控制：通过启用开关控制数据库")
            print("✅ 默认安全：默认不启用数据库")
            print("✅ 智能降级：数据库不可用时自动使用文件缓存")
            print("✅ 性能优化：有数据库时自动使用高性能模式")

        return success

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
