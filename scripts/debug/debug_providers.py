#!/usr/bin/env python3
"""
调试厂家配置脚本
查看数据库中的厂家配置和环境变量
"""

import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, ".")

# 加载.env文件
try:
    from dotenv import load_dotenv

    load_dotenv()
    print("✅ .env文件已加载")
except ImportError:
    print("❌ python-dotenv未安装，尝试手动加载.env")
    # 手动加载.env文件
    if os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
        print("✅ 手动加载.env文件完成")

from app.core.database import get_mongo_db, init_db


async def debug_providers():
    """调试厂家配置"""
    print("🔍 开始调试厂家配置...")

    # 初始化数据库连接
    await init_db()
    db = get_mongo_db()
    providers_collection = db.llm_providers

    print("\n📊 数据库中的厂家配置:")
    print("-" * 60)

    providers_data = await providers_collection.find().to_list(length=None)

    if not providers_data:
        print("❌ 数据库中没有厂家配置")
        return

    for i, provider in enumerate(providers_data, 1):
        print(f"\n{i}. 厂家: {provider.get('display_name', 'N/A')}")
        print(f"   ID: {provider.get('name', 'N/A')}")
        print(f"   API密钥: {'✅ 已配置' if provider.get('api_key') else '❌ 未配置'}")
        if provider.get("api_key"):
            api_key = provider["api_key"]
            print(f"   密钥前缀: {api_key[:10]}...")
        print(f"   状态: {'✅ 启用' if provider.get('is_active') else '❌ 禁用'}")
        print(f"   来源: {provider.get('extra_config', {}).get('source', '数据库')}")

    print("\n🔑 环境变量中的API密钥:")
    print("-" * 60)

    # 先检查.env文件是否存在
    env_file_path = ".env"
    if os.path.exists(env_file_path):
        print(f"✅ .env文件存在: {env_file_path}")
    else:
        print(f"❌ .env文件不存在: {env_file_path}")

    # 检查一些关键的环境变量
    test_vars = [
        "DASHSCOPE_API_KEY",
        "DEEPSEEK_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ]

    print("\n直接检查环境变量:")
    for var in test_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} = {value[:10]}...")
        else:
            print(f"❌ {var} = None")

    env_keys = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "baidu": "QIANFAN_ACCESS_KEY",
        "qianfan": "QIANFAN_ACCESS_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    print("\n映射检查:")
    for provider_name, env_var in env_keys.items():
        env_value = os.getenv(env_var)
        if env_value and env_value not in ["your_openai_api_key_here", "your_anthropic_api_key_here"]:
            print(f"✅ {provider_name}: {env_var} = {env_value[:10]}...")
        else:
            print(f"❌ {provider_name}: {env_var} = 未配置")

    print("\n🔄 迁移分析:")
    print("-" * 60)

    for provider in providers_data:
        provider_name = provider.get("name")
        has_db_key = bool(provider.get("api_key"))

        env_var = env_keys.get(provider_name)
        env_value = os.getenv(env_var) if env_var else None
        has_env_key = bool(env_value and env_value not in ["your_openai_api_key_here", "your_anthropic_api_key_here"])

        print(f"\n厂家: {provider.get('display_name')}")
        print(f"  数据库密钥: {'✅' if has_db_key else '❌'}")
        print(f"  环境变量密钥: {'✅' if has_env_key else '❌'}")

        if not has_db_key and has_env_key:
            print(f"  🔄 可以迁移: {env_var}")
        elif has_db_key:
            print("  ⏭️ 跳过: 已有数据库密钥")
        else:
            print("  ❌ 无法迁移: 环境变量中无密钥")


if __name__ == "__main__":
    asyncio.run(debug_providers())
