#!/usr/bin/env python3
"""
系统初始化脚本
初始化数据库配置，确保系统可以在有或没有数据库的情况下运行
"""

import json
import sys
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def initialize_system():
    """初始化系统"""
    logger.info("🚀 TradingAgents 系统初始化")
    logger.info("=")

    # 1. 创建配置目录
    logger.info("\n📁 创建配置目录...")
    config_dir = project_root / "config"
    config_dir.mkdir(exist_ok=True)
    logger.info(f"✅ 配置目录: {config_dir}")

    # 2. 创建数据缓存目录
    logger.info("\n📁 创建缓存目录...")
    cache_dir = project_root / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ 缓存目录: {cache_dir}")

    # 3. 检查并创建数据库配置文件
    logger.info("\n⚙️ 配置数据库设置...")
    config_file = config_dir / "database_config.json"

    if config_file.exists():
        logger.info(f"ℹ️ 配置文件已存在: {config_file}")

        # 读取现有配置
        try:
            with open(config_file, encoding="utf-8") as f:
                existing_config = json.load(f)
            logger.info("✅ 现有配置加载成功")
        except Exception as e:
            logger.error(f"⚠️ 现有配置读取失败: {e}")
            existing_config = None
    else:
        existing_config = None

    # 4. 检测数据库可用性
    logger.debug("\n🔍 检测数据库可用性...")

    # 检测MongoDB
    mongodb_available = False
    try:
        import pymongo
        from pymongo import MongoClient

        client = MongoClient("localhost", 27017, serverSelectionTimeoutMS=2000)
        client.server_info()
        client.close()
        mongodb_available = True
        logger.info("✅ MongoDB: 可用")
    except ImportError:
        logger.error("❌ MongoDB: pymongo未安装")
    except Exception as e:
        logger.error(f"❌ MongoDB: 连接失败 - {e}")

    # 检测Redis
    redis_available = False
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_timeout=2)
        r.ping()
        redis_available = True
        logger.info("✅ Redis: 可用")
    except ImportError:
        logger.error("❌ Redis: redis未安装")
    except Exception as e:
        logger.error(f"❌ Redis: 连接失败 - {e}")

    # 5. 生成配置
    logger.info("\n⚙️ 生成系统配置...")

    # 确定主要缓存后端
    if redis_available:
        primary_backend = "redis"
        logger.info("🚀 选择Redis作为主要缓存后端")
    elif mongodb_available:
        primary_backend = "mongodb"
        logger.info("💾 选择MongoDB作为主要缓存后端")
    else:
        primary_backend = "file"
        logger.info("📁 选择文件作为主要缓存后端")

    # 创建配置
    config = {
        "database": {
            "enabled": mongodb_available or redis_available,
            "auto_detect": True,
            "fallback_to_file": True,
            "mongodb": {
                "enabled": mongodb_available,
                "host": "localhost",
                "port": 27017,
                "database": "tradingagents",
                "timeout": 2000,
                "auto_detect": True,
            },
            "redis": {"enabled": redis_available, "host": "localhost", "port": 6379, "timeout": 2, "auto_detect": True},
        },
        "cache": {
            "enabled": True,
            "primary_backend": primary_backend,
            "fallback_enabled": True,
            "file_cache": {
                "enabled": True,
                "directory": "data/cache",
                "max_size_mb": 1000,
                "cleanup_interval_hours": 24,
            },
            "ttl_settings": {
                "us_stock_data": 7200,  # 2小时
                "china_stock_data": 3600,  # 1小时
                "us_news": 21600,  # 6小时
                "china_news": 14400,  # 4小时
                "us_fundamentals": 86400,  # 24小时
                "china_fundamentals": 43200,  # 12小时
            },
        },
        "performance": {"enable_compression": True, "enable_async_cache": False, "max_concurrent_requests": 10},
        "logging": {"level": "INFO", "log_database_operations": True, "log_cache_operations": False},
    }

    # 6. 保存配置
    logger.info("\n💾 保存配置文件...")
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 配置已保存: {config_file}")
    except Exception as e:
        logger.error(f"❌ 配置保存失败: {e}")
        return False

    # 7. 测试系统
    logger.info("\n🧪 测试系统初始化...")
    try:
        # 测试数据库管理器
        from tradingagents.config.database_manager import get_database_manager

        db_manager = get_database_manager()
        status = db_manager.get_status_report()

        logger.info("📊 系统状态:")
        logger.error(f"  数据库可用: {'✅ 是' if status['database_available'] else '❌ 否'}")
        logger.error(f"  MongoDB: {'✅ 可用' if status['mongodb']['available'] else '❌ 不可用'}")
        logger.error(f"  Redis: {'✅ 可用' if status['redis']['available'] else '❌ 不可用'}")
        logger.info(f"  缓存后端: {status['cache_backend']}")

        # 测试缓存系统
        from tradingagents.dataflows.integrated_cache import get_cache

        cache = get_cache()
        performance_mode = cache.get_performance_mode()
        logger.info(f"  性能模式: {performance_mode}")

        # 简单功能测试
        test_key = cache.save_stock_data("INIT_TEST", "初始化测试数据", data_source="init")
        test_data = cache.load_stock_data(test_key)

        if test_data == "初始化测试数据":
            logger.info("✅ 缓存功能测试通过")
        else:
            logger.error("❌ 缓存功能测试失败")
            return False

    except Exception as e:
        logger.error(f"❌ 系统测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 8. 生成使用指南
    logger.info("\n📋 生成使用指南...")

    usage_guide = f"""# TradingAgents 系统配置

## 当前配置

- **数据库可用**: {"是" if mongodb_available or redis_available else "否"}
- **MongoDB**: {"✅ 可用" if mongodb_available else "❌ 不可用"}
- **Redis**: {"✅ 可用" if redis_available else "❌ 不可用"}
- **主要缓存后端**: {primary_backend}
- **性能模式**: {cache.get_performance_mode() if "cache" in locals() else "未知"}

## 系统特性

### 自动降级支持
- 系统会自动检测可用的数据库服务
- 如果数据库不可用，自动使用文件缓存
- 保证系统在任何环境下都能正常运行

### 性能优化
- 智能缓存策略，减少API调用
- 支持多种数据类型的TTL管理
- 自动清理过期缓存

## 使用方法

### 基本使用
```python
from tradingagents.dataflows.integrated_cache import get_cache

# 获取缓存实例
cache = get_cache()

# 保存数据
cache_key = cache.save_stock_data("AAPL", stock_data)

# 加载数据
data = cache.load_stock_data(cache_key)
```

### 检查系统状态
```bash
python scripts/validation/check_system_status.py
```

## 性能提升建议

"""

    if not mongodb_available and not redis_available:
        usage_guide += """
### 安装数据库以获得更好性能

1. **安装Python依赖**:
   ```bash
   pip install pymongo redis
   ```

2. **启动MongoDB** (可选):
   ```bash
   docker run -d -p 27017:27017 --name mongodb mongo:4.4
   ```

3. **启动Redis** (可选):
   ```bash
   docker run -d -p 6379:6379 --name redis redis:alpine
   ```

4. **重新初始化系统**:
   ```bash
   python scripts/setup/initialize_system.py
   ```
"""
    else:
        usage_guide += """
### 系统已优化
✅ 数据库服务可用，系统运行在最佳性能模式
"""

    usage_file = project_root / "SYSTEM_SETUP_GUIDE.md"
    try:
        with open(usage_file, "w", encoding="utf-8") as f:
            f.write(usage_guide)
        logger.info(f"✅ 使用指南已生成: {usage_file}")
    except Exception as e:
        logger.error(f"⚠️ 使用指南生成失败: {e}")

    # 9. 总结
    logger.info("\n")
    logger.info("🎉 系统初始化完成!")
    logger.info("\n📊 初始化结果:")
    logger.info("  配置文件: ✅ 已创建")
    logger.info("  缓存目录: ✅ 已创建")
    logger.info("  数据库检测: ✅ 已完成")
    logger.info("  系统测试: ✅ 已通过")
    logger.info("  使用指南: ✅ 已生成")

    if mongodb_available or redis_available:
        logger.info("\n🚀 系统运行在高性能模式!")
    else:
        logger.info("\n📁 系统运行在文件缓存模式")
        logger.info("💡 安装MongoDB/Redis可获得更好性能")

    logger.info("\n🎯 下一步:")
    logger.info("1. 运行系统状态检查: python scripts/validation/check_system_status.py")
    logger.info(f"2. 查看使用指南: {usage_file}")
    logger.info("3. 开始使用TradingAgents!")

    return True


def main():
    """主函数"""
    try:
        success = initialize_system()
        return success
    except Exception as e:
        logger.error(f"❌ 系统初始化失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
