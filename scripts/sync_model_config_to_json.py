#!/usr/bin/env python
"""将数据库中的模型配置同步到 JSON 文件"""

import asyncio
import os

from pymongo import MongoClient


async def main():
    print("=" * 80)
    print("🔄 同步数据库配置到 JSON 文件")
    print("=" * 80)

    try:
        # 1. 从数据库读取配置
        mongo_password = os.getenv("MONGODB_PASSWORD", "")
        if not mongo_password:
            print("错误：请设置 MONGODB_PASSWORD 环境变量")
            return
        client = MongoClient(f"mongodb://admin:{mongo_password}@localhost:27017/?authSource=admin")
        db = client["tradingagents"]

        system_config = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])
        if not system_config:
            print("❌ 未找到激活的系统配置")
            return

        system_settings = system_config.get("system_settings", {})
        quick_model = system_settings.get("quick_analysis_model")
        deep_model = system_settings.get("deep_analysis_model")

        print("\n📖 从数据库读取配置:")
        print(f"  - quick_analysis_model: {quick_model}")
        print(f"  - deep_analysis_model: {deep_model}")

        # 2. 使用 unified_config 保存到 JSON
        from app.core.unified_config import unified_config

        # 读取现有配置
        current_settings = unified_config.get_system_settings()
        print("\n📖 当前 JSON 配置:")
        print(f"  - quick_analysis_model: {current_settings.get('quick_analysis_model')}")
        print(f"  - deep_analysis_model: {current_settings.get('deep_analysis_model')}")
        print(f"  - quick_think_llm: {current_settings.get('quick_think_llm')}")
        print(f"  - deep_think_llm: {current_settings.get('deep_think_llm')}")

        # 3. 更新配置
        if quick_model and deep_model:
            print("\n💾 更新 JSON 配置...")
            current_settings["quick_analysis_model"] = quick_model
            current_settings["deep_analysis_model"] = deep_model
            current_settings["quick_think_llm"] = quick_model  # 映射到旧字段名
            current_settings["deep_think_llm"] = deep_model  # 映射到旧字段名

            success = unified_config.save_system_settings(current_settings)

            if success:
                print("✅ 配置同步成功！")
                print("\n📋 最新配置:")
                print(f"  - quick_analysis_model: {quick_model}")
                print(f"  - deep_analysis_model: {deep_model}")
                print(f"  - quick_think_llm: {quick_model}")
                print(f"  - deep_think_llm: {deep_model}")
            else:
                print("❌ 配置同步失败")
        else:
            print("\n⚠️  数据库配置不完整，跳过同步")

        client.close()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
