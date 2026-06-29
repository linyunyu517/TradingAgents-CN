#!/usr/bin/env python3
"""
简单的.env配置测试
"""

import os


def test_env_reading():
    """测试.env文件读取"""
    print("🔧 测试.env配置读取")
    print("=" * 30)

    # 检查.env文件
    if os.path.exists(".env"):
        print("✅ .env文件存在")
    else:
        print("❌ .env文件不存在")
        return False

    # 读取环境变量
    print("\n📊 数据库配置:")

    # MongoDB配置
    mongodb_host = os.getenv("MONGODB_HOST", "localhost")
    mongodb_port = os.getenv("MONGODB_PORT", "27017")
    mongodb_username = os.getenv("MONGODB_USERNAME")
    mongodb_password = os.getenv("MONGODB_PASSWORD")
    mongodb_database = os.getenv("MONGODB_DATABASE", "tradingagents")

    print("MongoDB:")
    print(f"  Host: {mongodb_host}")
    print(f"  Port: {mongodb_port}")
    print(f"  Username: {mongodb_username or '未设置'}")
    print(f"  Password: {'***' if mongodb_password else '未设置'}")
    print(f"  Database: {mongodb_database}")

    # Redis配置
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_db = os.getenv("REDIS_DB", "0")

    print("\nRedis:")
    print(f"  Host: {redis_host}")
    print(f"  Port: {redis_port}")
    print(f"  Password: {'***' if redis_password else '未设置'}")
    print(f"  DB: {redis_db}")

    # 测试数据库连接
    print("\n🧪 测试数据库连接...")

    # 测试MongoDB
    mongodb_available = False
    try:
        import pymongo

        client = pymongo.MongoClient(
            host=mongodb_host,
            port=int(mongodb_port),
            username=mongodb_username,
            password=mongodb_password,
            authSource="admin",
            serverSelectionTimeoutMS=2000,
        )
        client.server_info()
        client.close()
        mongodb_available = True
        print("✅ MongoDB 连接成功")
    except ImportError:
        print("❌ pymongo 未安装")
    except Exception as e:
        print(f"❌ MongoDB 连接失败: {e}")

    # 测试Redis
    redis_available = False
    try:
        import redis

        r = redis.Redis(
            host=redis_host, port=int(redis_port), password=redis_password, db=int(redis_db), socket_timeout=2,
        )
        r.ping()
        redis_available = True
        print("✅ Redis 连接成功")
    except ImportError:
        print("❌ redis 未安装")
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")

    # 总结
    print("\n📊 总结:")
    print(f"MongoDB: {'✅ 可用' if mongodb_available else '❌ 不可用'}")
    print(f"Redis: {'✅ 可用' if redis_available else '❌ 不可用'}")

    if mongodb_available or redis_available:
        print("🚀 数据库可用，系统将使用高性能模式")
    else:
        print("📁 数据库不可用，系统将使用文件缓存模式")
        print("💡 这是正常的，系统可以正常工作")

    return True


if __name__ == "__main__":
    test_env_reading()
