#!/usr/bin/env python3
"""
脚本凭据辅助模块 — 所有 scripts/ 和 tests/ 下的脚本统一通过此模块获取凭据。
零降级：不改变任何脚本的功能逻辑，仅统一凭据获取方式。

使用方式：
    from _credential_helper import get_mongodb_uri, get_redis_password

    # MongoDB 连接
    client = MongoClient(get_mongodb_uri())

    # Redis 连接
    r = redis.Redis(host='localhost', password=get_redis_password())

如果环境变量未设置，会打印明确指引并 sys.exit(1) — 拒绝回退到弱密码。
"""

import os
import sys


def get_mongodb_uri(database: str = "tradingagents") -> str:
    """
    从环境变量构建 MongoDB URI。
    优先使用 MONGODB_PASSWORD，其次使用 MONGO_ROOT_PASSWORD。
    未设置凭据时打印指引并退出。

    Args:
        database: 数据库名称，默认 "tradingagents"

    Returns:
        MongoDB URI 字符串，如: mongodb://admin:password@localhost:27017/tradingagents?authSource=admin
    """
    user = os.getenv("MONGODB_USERNAME", "admin")
    password = os.getenv("MONGODB_PASSWORD") or os.getenv("MONGO_ROOT_PASSWORD")

    if not password:
        print("=" * 60)
        print("  ❌ 未设置 MongoDB 密码")
        print("=" * 60)
        print()
        print("  请在环境变量中设置以下之一：")
        print("    - MONGODB_PASSWORD")
        print("    - MONGO_ROOT_PASSWORD")
        print()
        print("  或者运行凭据生成器自动生成：")
        print("    python scripts/generate_credentials.py")
        print()
        print("  启动前验证凭据：")
        print("    python scripts/validate_credentials.py")
        sys.exit(1)

    host = os.getenv("MONGODB_HOST", "localhost")
    port = os.getenv("MONGODB_PORT", "27017")
    auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
    return f"mongodb://{user}:{password}@{host}:{port}/{database}?authSource={auth_source}"


def get_redis_password() -> str:
    """
    从环境变量获取 Redis 密码。
    优先使用 REDIS_PASSWORD，其次使用 MONGO_ROOT_PASSWORD（兼容性）。
    未设置凭据时打印指引并退出。

    Returns:
        Redis 密码字符串
    """
    password = os.getenv("REDIS_PASSWORD") or os.getenv("MONGO_ROOT_PASSWORD")

    if not password:
        print("=" * 60)
        print("  ❌ 未设置 Redis 密码")
        print("=" * 60)
        print()
        print("  请在环境变量中设置以下之一：")
        print("    - REDIS_PASSWORD")
        print("    - MONGO_ROOT_PASSWORD")
        print()
        print("  或者运行凭据生成器自动生成：")
        print("    python scripts/generate_credentials.py")
        sys.exit(1)

    return password


def get_mongodb_password() -> str:
    """
    获取 MongoDB 密码（兼容旧的 MONGODB_PASSWORD 变量）
    """
    password = os.getenv("MONGODB_PASSWORD") or os.getenv("MONGO_ROOT_PASSWORD")
    if not password:
        print("=" * 60)
        print("  ❌ 未设置 MONGODB_PASSWORD")
        print("=" * 60)
        print()
        print("  请在环境变量中设置以下之一：")
        print("    - MONGODB_PASSWORD")
        print("    - MONGO_ROOT_PASSWORD")
        print()
        print("  或者运行凭据生成器自动生成：")
        print("    python scripts/generate_credentials.py")
        sys.exit(1)
    return password


def get_mongodb_uri_without_auth(database: str = "tradingagents") -> str:
    """
    构建不带认证信息的 MongoDB URI（适用于已配置 MongoDB 连接池的场景）
    """
    host = os.getenv("MONGODB_HOST", "localhost")
    port = os.getenv("MONGODB_PORT", "27017")
    return f"mongodb://{host}:{port}/{database}"


def get_admin_password() -> str:
    """
    获取管理员密码 ADMIN_PASSWORD
    """
    password = os.getenv("ADMIN_PASSWORD") or os.getenv("INITIAL_ADMIN_PASSWORD")
    if not password:
        print("=" * 60)
        print("  ❌ 未设置管理员密码")
        print("=" * 60)
        print()
        print("  请在环境变量中设置 ADMIN_PASSWORD 或 INITIAL_ADMIN_PASSWORD")
        print()
        print("  或者运行凭据生成器自动生成：")
        print("    python scripts/generate_credentials.py")
        sys.exit(1)
    return password


# 全局提示常量（在脚本输出中统一使用）
HELP_TEXT = """
💡 首次部署请按以下步骤操作：

  1. 生成凭据:
     python scripts/generate_credentials.py

  2. 设置环境变量（Windows PowerShell）:
     $env:MONGO_ROOT_PASSWORD = "your-generated-password"
     $env:REDIS_PASSWORD = "your-generated-password"

     或 Linux/macOS:
     export MONGO_ROOT_PASSWORD="your-generated-password"
     export REDIS_PASSWORD="your-generated-password"

  3. 验证凭据:
     python scripts/validate_credentials.py

  4. 启动服务:
     python main.py
"""
