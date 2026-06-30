#!/usr/bin/env python3
"""
测试配置桥接功能
验证数据库配置是否正确桥接到环境变量
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_config_bridge():
    """测试配置桥接"""
    print("=" * 60)
    print("🧪 测试配置桥接功能")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n1️⃣ 初始化数据库连接...")
    from app.core.database import init_db

    await init_db()
    print("✅ 数据库连接成功")

    # 2. 读取数据库中的配置
    print("\n2️⃣ 读取数据库配置...")
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    config_doc = await db.system_configs.find_one({"is_active": True})

    if not config_doc:
        print("❌ 未找到激活的配置")
        return False

    system_settings = config_doc.get("system_settings", {})
    print(f"✅ 找到配置，包含 {len(system_settings)} 个设置项")

    # 显示 TradingAgents 相关配置
    ta_keys = [
        "ta_use_app_cache",
        "ta_hk_min_request_interval_seconds",
        "ta_hk_timeout_seconds",
        "ta_hk_max_retries",
        "ta_hk_rate_limit_wait_seconds",
        "ta_hk_cache_ttl_seconds",
    ]

    print("\n📋 数据库中的 TradingAgents 配置：")
    for key in ta_keys:
        value = system_settings.get(key, "未设置")
        print(f"  • {key}: {value}")

    # 3. 执行配置桥接
    print("\n3️⃣ 执行配置桥接...")
    from app.core.config_bridge import bridge_config_to_env

    success = bridge_config_to_env()

    if not success:
        print("❌ 配置桥接失败")
        return False

    print("✅ 配置桥接完成")

    # 4. 验证环境变量
    print("\n4️⃣ 验证环境变量...")
    env_mapping = {
        "ta_use_app_cache": "TA_USE_APP_CACHE",
        "ta_hk_min_request_interval_seconds": "TA_HK_MIN_REQUEST_INTERVAL_SECONDS",
        "ta_hk_timeout_seconds": "TA_HK_TIMEOUT_SECONDS",
        "ta_hk_max_retries": "TA_HK_MAX_RETRIES",
        "ta_hk_rate_limit_wait_seconds": "TA_HK_RATE_LIMIT_WAIT_SECONDS",
        "ta_hk_cache_ttl_seconds": "TA_HK_CACHE_TTL_SECONDS",
    }

    all_ok = True
    print("\n📋 环境变量验证结果：")
    for db_key, env_key in env_mapping.items():
        db_value = system_settings.get(db_key)
        env_value = os.getenv(env_key)

        if db_value is None:
            print(f"  ⚠️  {env_key}: 数据库中未设置")
            continue

        if env_value is None:
            print(f"  ❌ {env_key}: 未桥接到环境变量")
            all_ok = False
            continue

        # 比较值
        db_str = str(db_value).lower() if isinstance(db_value, bool) else str(db_value)
        if db_str == env_value:
            print(f"  ✅ {env_key}: {env_value}")
        else:
            print(f"  ⚠️  {env_key}: 值不匹配 (DB: {db_str}, ENV: {env_value})")
            all_ok = False

    # 5. 测试 tradingagents 读取配置
    print("\n5️⃣ 测试 tradingagents 读取配置...")
    try:
        from tradingagents.config.runtime_settings import get_float, get_int, use_app_cache_enabled

        print("\n📋 tradingagents 读取的配置值：")

        # 测试布尔值
        use_cache = use_app_cache_enabled(False)
        print(f"  • ta_use_app_cache: {use_cache}")

        # 测试浮点数
        min_interval = get_float("TA_HK_MIN_REQUEST_INTERVAL_SECONDS", "ta_hk_min_request_interval_seconds", 2.0)
        print(f"  • ta_hk_min_request_interval_seconds: {min_interval}")

        # 测试整数
        timeout = get_int("TA_HK_TIMEOUT_SECONDS", "ta_hk_timeout_seconds", 60)
        print(f"  • ta_hk_timeout_seconds: {timeout}")

        max_retries = get_int("TA_HK_MAX_RETRIES", "ta_hk_max_retries", 3)
        print(f"  • ta_hk_max_retries: {max_retries}")

        rate_limit_wait = get_int("TA_HK_RATE_LIMIT_WAIT_SECONDS", "ta_hk_rate_limit_wait_seconds", 60)
        print(f"  • ta_hk_rate_limit_wait_seconds: {rate_limit_wait}")

        cache_ttl = get_int("TA_HK_CACHE_TTL_SECONDS", "ta_hk_cache_ttl_seconds", 86400)
        print(f"  • ta_hk_cache_ttl_seconds: {cache_ttl}")

        print("\n✅ tradingagents 配置读取成功")

    except Exception as e:
        print(f"\n❌ tradingagents 配置读取失败: {e}")
        import traceback

        traceback.print_exc()
        all_ok = False

    # 总结
    print("\n" + "=" * 60)
    if all_ok:
        print("🎉 所有测试通过！配置桥接工作正常")
    else:
        print("⚠️  部分测试失败，请检查上述错误")
    print("=" * 60)

    return all_ok


if __name__ == "__main__":
    result = asyncio.run(test_config_bridge())
    sys.exit(0 if result else 1)
