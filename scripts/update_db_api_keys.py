#!/usr/bin/env python3
"""
更新数据库中的 API Key
从 .env 文件读取真实的 API Key，更新到 MongoDB 数据库中
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ 已加载 .env 文件: {env_file}")
else:
    print(f"❌ .env 文件不存在: {env_file}")
    sys.exit(1)


async def update_api_keys():
    """更新数据库中的 API Key"""
    from app.core.database import get_mongo_db, init_db

    # 初始化数据库
    await init_db()
    db = await get_mongo_db()

    print("\n" + "=" * 80)
    print("🔧 更新数据库中的 API Key")
    print("=" * 80)

    # 读取 .env 文件中的 API Key
    api_keys = {
        "dashscope": os.getenv("DASHSCOPE_API_KEY"),
        "deepseek": os.getenv("DEEPSEEK_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY"),
        "google": os.getenv("GOOGLE_API_KEY"),
        "baidu": os.getenv("BAIDU_API_KEY"),
        "openrouter": os.getenv("OPENROUTER_API_KEY"),
    }

    print("\n📋 从 .env 文件读取的 API Key:")
    for provider, key in api_keys.items():
        if key and not key.startswith("your_"):
            print(f"  ✅ {provider.upper()}_API_KEY: {key[:10]}... (长度: {len(key)})")
        else:
            print(f"  ⚠️  {provider.upper()}_API_KEY: 未设置或为占位符")

    # 获取当前激活的系统配置
    system_configs = db.system_configs
    config = await system_configs.find_one({"is_active": True}, sort=[("version", -1)])

    if not config:
        print("\n❌ 数据库中没有激活的系统配置")
        return

    print(f"\n📊 当前配置版本: {config.get('version', 0)}")

    # 更新 LLM 配置中的 API Key
    llm_configs = config.get("llm_configs", [])
    updated_count = 0

    print("\n🔄 更新 LLM 配置:")
    for llm_config in llm_configs:
        provider = llm_config.get("provider", "").lower()
        old_key = llm_config.get("api_key", "")

        # 如果 .env 中有对应的 API Key，且不是占位符
        if provider in api_keys and api_keys[provider] and not api_keys[provider].startswith("your_"):
            new_key = api_keys[provider]

            # 只有当 API Key 不同时才更新
            if old_key != new_key:
                llm_config["api_key"] = new_key
                llm_config["enabled"] = True  # 自动启用
                print(f"  ✅ 更新 {provider.upper()}: {old_key[:10]}... → {new_key[:10]}... (长度: {len(new_key)})")
                updated_count += 1
            else:
                print(f"  ⏭️  {provider.upper()}: API Key 已是最新")
        elif old_key.startswith("your_"):
            print(f"  ⚠️  {provider.upper()}: .env 中未设置有效的 API Key，跳过")
        else:
            print(f"  ⏭️  {provider.upper()}: 保持现有配置")

    # 更新数据源配置中的 API Key
    data_source_configs = config.get("data_source_configs", [])

    print("\n🔄 更新数据源配置:")

    # Tushare Token
    tushare_token = os.getenv("TUSHARE_TOKEN")
    if tushare_token and not tushare_token.startswith("your_"):
        for ds_config in data_source_configs:
            if ds_config.get("type") == "tushare":
                old_token = ds_config.get("api_key", "")
                if old_token != tushare_token:
                    ds_config["api_key"] = tushare_token
                    ds_config["enabled"] = True
                    print(
                        f"  ✅ 更新 TUSHARE_TOKEN: {old_token[:10]}... → {tushare_token[:10]}... (长度: {len(tushare_token)})",
                    )
                    updated_count += 1
                else:
                    print("  ⏭️  TUSHARE_TOKEN: 已是最新")
                break

    # FinnHub API Key
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key and not finnhub_key.startswith("your_"):
        for ds_config in data_source_configs:
            if ds_config.get("type") == "finnhub":
                old_key = ds_config.get("api_key", "")
                if old_key != finnhub_key:
                    ds_config["api_key"] = finnhub_key
                    ds_config["enabled"] = True
                    print(
                        f"  ✅ 更新 FINNHUB_API_KEY: {old_key[:10]}... → {finnhub_key[:10]}... (长度: {len(finnhub_key)})",
                    )
                    updated_count += 1
                else:
                    print("  ⏭️  FINNHUB_API_KEY: 已是最新")
                break

    if updated_count == 0:
        print("\n⏭️  没有需要更新的配置")
        return

    # 保存更新后的配置
    print(f"\n💾 保存更新后的配置 (共更新 {updated_count} 项)...")

    # 更新配置版本号
    config["version"] = config.get("version", 0) + 1
    config["updated_at"] = {"$currentDate": True}

    # 保存到数据库
    result = await system_configs.update_one(
        {"_id": config["_id"]},
        {
            "$set": {
                "llm_configs": llm_configs,
                "data_source_configs": data_source_configs,
                "version": config["version"],
            },
            "$currentDate": {"updated_at": True},
        },
    )

    if result.modified_count > 0:
        print(f"✅ 配置更新成功！新版本: {config['version']}")
        print("\n💡 提示: 请重启后端服务以应用新配置")
        print("   docker-compose -f docker-compose.hub.nginx.yml restart backend")
    else:
        print("❌ 配置更新失败")


async def main():
    """主函数"""
    try:
        await update_api_keys()
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
