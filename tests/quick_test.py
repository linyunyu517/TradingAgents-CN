#!/usr/bin/env python3
"""
快速集成测试 - 验证复制的文件是否正常工作
"""

import os
import traceback
from datetime import datetime

print("🚀 TradingAgents 集成测试")
print("=" * 40)

# 测试1：检查文件是否存在
print("\n📁 检查复制的文件...")
files_to_check = [
    "tradingagents/dataflows/cache_manager.py",
    "tradingagents/dataflows/optimized_us_data.py",
    "tradingagents/dataflows/config.py",
]

for file_path in files_to_check:
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        print(f"✅ {file_path} (大小: {size:,} 字节)")
    else:
        print(f"❌ {file_path} (文件不存在)")

# 测试2：检查Python语法
print("\n🐍 检查Python语法...")
for file_path in files_to_check:
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                compile(f.read(), file_path, "exec")
            print(f"✅ {file_path} 语法正确")
        except SyntaxError as e:
            print(f"❌ {file_path} 语法错误: {e}")
        except Exception as e:
            print(f"⚠️ {file_path} 检查失败: {e}")

# 测试3：尝试导入模块
print("\n📦 测试模块导入...")

# 测试缓存管理器
try:
    from tradingagents.dataflows.cache_manager import get_cache

    print("✅ cache_manager 导入成功")

    # 创建缓存实例
    cache = get_cache()
    print(f"✅ 缓存实例创建成功: {type(cache).__name__}")

    # 检查缓存目录
    if hasattr(cache, "cache_dir"):
        print(f"📁 缓存目录: {cache.cache_dir}")
        if cache.cache_dir.exists():
            print("✅ 缓存目录已创建")
        else:
            print("⚠️ 缓存目录不存在")

except Exception as e:
    print(f"❌ cache_manager 导入失败: {e}")
    traceback.print_exc()

# 测试优化美股数据
try:
    from tradingagents.dataflows.optimized_us_data import get_optimized_us_data_provider

    print("✅ optimized_us_data 导入成功")

    # 创建数据提供器
    provider = get_optimized_us_data_provider()
    print(f"✅ 数据提供器创建成功: {type(provider).__name__}")

except Exception as e:
    print(f"❌ optimized_us_data 导入失败: {e}")
    traceback.print_exc()

# 测试配置模块
try:
    from tradingagents.dataflows.config import get_config

    print("✅ config 导入成功")

    # 获取配置
    config = get_config()
    print(f"✅ 配置获取成功: {type(config).__name__}")

except Exception as e:
    print(f"❌ config 导入失败: {e}")
    traceback.print_exc()

# 测试4：基本功能测试
print("\n💾 测试缓存基本功能...")
try:
    cache = get_cache()

    # 测试数据保存
    test_data = f"测试数据 - {datetime.now()}"
    cache_key = cache.save_stock_data(
        symbol="TEST", data=test_data, start_date="2024-01-01", end_date="2024-12-31", data_source="integration_test",
    )
    print(f"✅ 数据保存成功: {cache_key}")

    # 测试数据加载
    loaded_data = cache.load_stock_data(cache_key)
    if loaded_data == test_data:
        print("✅ 数据加载成功，内容匹配")
    else:
        print("❌ 数据不匹配")
        print(f"  期望: {test_data}")
        print(f"  实际: {loaded_data}")

    # 测试缓存查找
    found_key = cache.find_cached_stock_data(
        symbol="TEST", start_date="2024-01-01", end_date="2024-12-31", data_source="integration_test",
    )

    if found_key:
        print(f"✅ 缓存查找成功: {found_key}")
    else:
        print("❌ 缓存查找失败")

except Exception as e:
    print(f"❌ 缓存功能测试失败: {e}")
    traceback.print_exc()

# 测试5：性能测试
print("\n⚡ 简单性能测试...")
try:
    import time

    cache = get_cache()

    # 保存测试
    start_time = time.time()
    cache_key = cache.save_stock_data(
        symbol="PERF", data="性能测试数据", start_date="2024-01-01", end_date="2024-12-31", data_source="perf_test",
    )
    save_time = time.time() - start_time

    # 加载测试
    start_time = time.time()
    data = cache.load_stock_data(cache_key)
    load_time = time.time() - start_time

    print(f"📊 保存时间: {save_time:.4f}秒")
    print(f"⚡ 加载时间: {load_time:.4f}秒")

    if load_time < 0.1:
        print("✅ 缓存性能良好 (<0.1秒)")
    else:
        print("⚠️ 缓存性能需要优化")

except Exception as e:
    print(f"❌ 性能测试失败: {e}")

# 测试6：缓存统计
print("\n📊 缓存统计信息...")
try:
    cache = get_cache()
    stats = cache.get_cache_stats()

    print("缓存统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

except Exception as e:
    print(f"❌ 缓存统计失败: {e}")

print("\n" + "=" * 40)
print("🎉 集成测试完成!")
print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 生成测试报告
print("\n📋 测试总结:")
print("1. 文件复制: 检查文件是否正确复制")
print("2. 语法检查: 验证Python语法正确性")
print("3. 模块导入: 测试模块是否可以正常导入")
print("4. 功能测试: 验证缓存基本功能")
print("5. 性能测试: 检查缓存性能")
print("6. 统计信息: 获取缓存使用统计")

print("\n🎯 下一步:")
print("1. 如果测试通过，可以开始清理中文内容")
print("2. 添加英文文档和注释")
print("3. 创建完整的测试用例")
print("4. 准备性能基准报告")
print("5. 联系上游项目维护者")
