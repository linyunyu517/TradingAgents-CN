#!/usr/bin/env python3
"""
智能配置系统 - 自动检测和配置数据库依赖
确保系统在有或没有MongoDB/Redis的情况下都能正常运行
"""

import json
import logging
import os
from typing import Any

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class SmartConfigManager:
    """智能配置管理器 - 自动检测可用服务并配置系统"""

    def __init__(self):
        self.config = {}
        self.mongodb_available = False
        self.redis_available = False
        self.detection_results = {}

        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # 执行检测
        self._detect_services()
        self._generate_config()

    def _detect_mongodb(self) -> tuple[bool, str]:
        """检测MongoDB是否可用"""
        try:
            import pymongo
            from pymongo import MongoClient

            # 尝试连接MongoDB
            client = MongoClient("localhost", 27017, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
            client.server_info()  # 触发连接测试
            client.close()

            return True, "MongoDB服务正在运行"

        except ImportError:
            return False, "pymongo未安装"
        except Exception as e:
            return False, f"MongoDB连接失败: {e!s}"

    def _detect_redis(self) -> tuple[bool, str]:
        """检测Redis是否可用"""
        try:
            import redis

            # 尝试连接Redis
            r = redis.Redis(host="localhost", port=6379, socket_timeout=2, socket_connect_timeout=2)
            r.ping()

            return True, "Redis服务正在运行"

        except ImportError:
            return False, "redis未安装"
        except Exception as e:
            return False, f"Redis连接失败: {e!s}"

    def _detect_services(self):
        """检测所有服务"""
        logger.debug("🔍 检测系统服务...")

        # 检测MongoDB
        self.mongodb_available, mongodb_msg = self._detect_mongodb()
        self.detection_results["mongodb"] = {"available": self.mongodb_available, "message": mongodb_msg}

        if self.mongodb_available:
            logger.info(f"✅ MongoDB: {mongodb_msg}")
        else:
            logger.error(f"❌ MongoDB: {mongodb_msg}")

        # 检测Redis
        self.redis_available, redis_msg = self._detect_redis()
        self.detection_results["redis"] = {"available": self.redis_available, "message": redis_msg}

        if self.redis_available:
            logger.info(f"✅ Redis: {redis_msg}")
        else:
            logger.error(f"❌ Redis: {redis_msg}")

    def _generate_config(self):
        """根据检测结果生成配置"""
        logger.info("\n⚙️ 生成智能配置...")

        # 基础配置
        self.config = {
            "cache": {
                "enabled": True,
                "primary_backend": "file",  # 默认使用文件缓存
                "fallback_enabled": True,
                "ttl_settings": {
                    "us_stock_data": 7200,  # 2小时
                    "china_stock_data": 3600,  # 1小时
                    "us_news": 21600,  # 6小时
                    "china_news": 14400,  # 4小时
                    "us_fundamentals": 86400,  # 24小时
                    "china_fundamentals": 43200,  # 12小时
                },
            },
            "database": {
                "mongodb": {
                    "enabled": self.mongodb_available,
                    "host": "localhost",
                    "port": 27017,
                    "database": "tradingagents",
                    "timeout": 2000,
                },
                "redis": {"enabled": self.redis_available, "host": "localhost", "port": 6379, "timeout": 2},
            },
            "detection_results": self.detection_results,
        }

        # 根据可用服务调整缓存策略
        if self.redis_available and self.mongodb_available:
            self.config["cache"]["primary_backend"] = "redis"
            self.config["cache"]["secondary_backend"] = "mongodb"
            self.config["cache"]["tertiary_backend"] = "file"
            logger.info("🚀 配置模式: Redis + MongoDB + 文件缓存")

        elif self.redis_available:
            self.config["cache"]["primary_backend"] = "redis"
            self.config["cache"]["secondary_backend"] = "file"
            logger.info("⚡ 配置模式: Redis + 文件缓存")

        elif self.mongodb_available:
            self.config["cache"]["primary_backend"] = "mongodb"
            self.config["cache"]["secondary_backend"] = "file"
            logger.info("💾 配置模式: MongoDB + 文件缓存")

        else:
            self.config["cache"]["primary_backend"] = "file"
            logger.info("📁 配置模式: 纯文件缓存")

    def get_config(self) -> dict[str, Any]:
        """获取配置"""
        return self.config.copy()

    def save_config(self, config_path: str = "smart_config.json"):
        """保存配置到文件"""
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ 配置已保存到: {config_path}")
        except Exception as e:
            logger.error(f"❌ 配置保存失败: {e}")

    def load_config(self, config_path: str = "smart_config.json") -> bool:
        """从文件加载配置"""
        try:
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info(f"✅ 配置已从文件加载: {config_path}")
                return True
        except Exception as e:
            logger.error(f"❌ 配置加载失败: {e}")
        return False

    def get_cache_backend_info(self) -> dict[str, Any]:
        """获取缓存后端信息"""
        return {
            "primary_backend": self.config["cache"]["primary_backend"],
            "mongodb_available": self.mongodb_available,
            "redis_available": self.redis_available,
            "fallback_enabled": self.config["cache"]["fallback_enabled"],
        }

    def print_status(self):
        """打印系统状态"""
        logger.info("\n📊 系统状态报告:")
        logger.info("=")

        # 服务状态
        logger.info("🔧 服务状态:")
        for service, info in self.detection_results.items():
            status = "✅ 可用" if info["available"] else "❌ 不可用"
            logger.info(f"  {service.upper()}: {status} - {info['message']}")

        # 缓存配置
        cache_info = self.get_cache_backend_info()
        logger.info("\n💾 缓存配置:")
        logger.info(f"  主要后端: {cache_info['primary_backend']}")
        logger.info(f"  降级支持: {'启用' if cache_info['fallback_enabled'] else '禁用'}")

        # 运行模式
        if self.mongodb_available and self.redis_available:
            mode = "🚀 高性能模式 (Redis + MongoDB + 文件)"
        elif self.redis_available:
            mode = "⚡ 快速模式 (Redis + 文件)"
        elif self.mongodb_available:
            mode = "💾 持久化模式 (MongoDB + 文件)"
        else:
            mode = "📁 基础模式 (纯文件缓存)"

        logger.info(f"  运行模式: {mode}")

        # 性能预期
        logger.info("\n📈 性能预期:")
        if self.redis_available:
            logger.info("  缓存性能: 极快 (<0.001秒)")
        else:
            logger.info("  缓存性能: 很快 (<0.01秒)")
        logger.info("  相比API调用: 99%+ 性能提升")


# 全局配置管理器实例
_config_manager = None


def get_smart_config() -> SmartConfigManager:
    """获取全局智能配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = SmartConfigManager()
    return _config_manager


def get_config() -> dict[str, Any]:
    """获取系统配置"""
    return get_smart_config().get_config()


def is_mongodb_available() -> bool:
    """检查MongoDB是否可用"""
    return get_smart_config().mongodb_available


def is_redis_available() -> bool:
    """检查Redis是否可用"""
    return get_smart_config().redis_available


def get_cache_backend() -> str:
    """获取当前缓存后端"""
    config = get_config()
    return config["cache"]["primary_backend"]


def main():
    """主函数 - 演示智能配置系统"""
    logger.info("🔧 TradingAgents 智能配置系统")
    logger.info("=")

    # 创建配置管理器
    config_manager = get_smart_config()

    # 显示状态
    config_manager.print_status()

    # 保存配置
    config_manager.save_config()

    # 生成环境变量设置脚本
    config = config_manager.get_config()

    env_script = f"""# 环境变量配置脚本
# 根据检测结果自动生成

# 缓存配置
export CACHE_BACKEND="{config["cache"]["primary_backend"]}"
export CACHE_ENABLED="true"
export FALLBACK_ENABLED="{str(config["cache"]["fallback_enabled"]).lower()}"

# 数据库配置
export MONGODB_ENABLED="{str(config["database"]["mongodb"]["enabled"]).lower()}"
export REDIS_ENABLED="{str(config["database"]["redis"]["enabled"]).lower()}"

# TTL设置
export US_STOCK_TTL="{config["cache"]["ttl_settings"]["us_stock_data"]}"
export CHINA_STOCK_TTL="{config["cache"]["ttl_settings"]["china_stock_data"]}"

echo "✅ 环境变量已设置"
echo "缓存后端: $CACHE_BACKEND"
echo "MongoDB: $MONGODB_ENABLED"
echo "Redis: $REDIS_ENABLED"
"""

    with open("set_env.sh", "w", encoding="utf-8") as f:
        f.write(env_script)

    logger.info("\n✅ 环境配置脚本已生成: set_env.sh")

    # 生成PowerShell版本
    ps_script = f"""# PowerShell环境变量配置脚本
# 根据检测结果自动生成

# 缓存配置
$env:CACHE_BACKEND = "{config["cache"]["primary_backend"]}"
$env:CACHE_ENABLED = "true"
$env:FALLBACK_ENABLED = "{str(config["cache"]["fallback_enabled"]).lower()}"

# 数据库配置
$env:MONGODB_ENABLED = "{str(config["database"]["mongodb"]["enabled"]).lower()}"
$env:REDIS_ENABLED = "{str(config["database"]["redis"]["enabled"]).lower()}"

# TTL设置
$env:US_STOCK_TTL = "{config["cache"]["ttl_settings"]["us_stock_data"]}"
$env:CHINA_STOCK_TTL = "{config["cache"]["ttl_settings"]["china_stock_data"]}"

Write-Host "✅ 环境变量已设置" -ForegroundColor Green
Write-Host "缓存后端: $env:CACHE_BACKEND" -ForegroundColor Cyan
Write-Host "MongoDB: $env:MONGODB_ENABLED" -ForegroundColor Cyan
Write-Host "Redis: $env:REDIS_ENABLED" -ForegroundColor Cyan
"""

    with open("set_env.ps1", "w", encoding="utf-8") as f:
        f.write(ps_script)

    logger.info("✅ PowerShell配置脚本已生成: set_env.ps1")

    logger.info("\n🎯 下一步:")
    logger.info("1. 运行: python test_with_smart_config.py")
    logger.info(r"2. 或者: .\set_env.ps1 (设置环境变量)")
    logger.info("3. 然后: python quick_test.py")


if __name__ == "__main__":
    main()
