"""
测试 default_base_url 是否被正确使用

测试场景：
1. 修改厂家的 default_base_url
2. 创建分析配置
3. 验证 backend_url 是否使用了 default_base_url
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient

from app.core.config import settings
from app.services.simple_analysis_service import create_analysis_config, get_provider_and_url_by_model_sync


def test_default_base_url():
    """测试 default_base_url 是否被正确使用"""

    print("\n" + "=" * 60)
    print("🧪 测试 default_base_url 是否被正确使用")
    print("=" * 60)

    # 连接数据库
    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    providers_collection = db.llm_providers

    # 测试厂家
    test_provider = "google"
    test_model = "gemini-2.0-flash"

    try:
        # 1️⃣ 获取原始配置
        print(f"\n1️⃣ 获取厂家 {test_provider} 的原始配置...")
        original_provider = providers_collection.find_one({"name": test_provider})

        if not original_provider:
            print(f"❌ 厂家 {test_provider} 不存在，跳过测试")
            return

        original_url = original_provider.get("default_base_url")
        print(f"   原始 default_base_url: {original_url}")

        # 2️⃣ 修改 default_base_url
        test_url = "https://test-api.google.com/v1"
        print(f"\n2️⃣ 修改 default_base_url 为: {test_url}")

        providers_collection.update_one({"name": test_provider}, {"$set": {"default_base_url": test_url}})
        print("✅ 修改成功")

        # 3️⃣ 测试 get_provider_and_url_by_model_sync
        print(f"\n3️⃣ 测试 get_provider_and_url_by_model_sync('{test_model}')...")
        provider_info = get_provider_and_url_by_model_sync(test_model)
        print(f"   返回结果: {provider_info}")

        if provider_info["backend_url"] == test_url:
            print(f"✅ backend_url 正确: {provider_info['backend_url']}")
        else:
            print("❌ backend_url 错误!")
            print(f"   期望: {test_url}")
            print(f"   实际: {provider_info['backend_url']}")

        # 4️⃣ 测试 create_analysis_config
        print("\n4️⃣ 测试 create_analysis_config...")
        config = create_analysis_config(
            research_depth=3,
            selected_analysts=["market", "fundamentals"],
            quick_model=test_model,
            deep_model=test_model,
            llm_provider=test_provider,
            market_type="A股",
        )

        print(f"   配置中的 backend_url: {config.get('backend_url')}")

        if config.get("backend_url") == test_url:
            print(f"✅ 配置中的 backend_url 正确: {config['backend_url']}")
        else:
            print("❌ 配置中的 backend_url 错误!")
            print(f"   期望: {test_url}")
            print(f"   实际: {config.get('backend_url')}")

        # 5️⃣ 恢复原始配置
        print("\n5️⃣ 恢复原始配置...")
        if original_url:
            providers_collection.update_one({"name": test_provider}, {"$set": {"default_base_url": original_url}})
            print(f"✅ 已恢复为: {original_url}")
        else:
            providers_collection.update_one({"name": test_provider}, {"$unset": {"default_base_url": ""}})
            print("✅ 已删除 default_base_url 字段")

        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()

        # 尝试恢复原始配置
        try:
            if original_url:
                providers_collection.update_one({"name": test_provider}, {"$set": {"default_base_url": original_url}})
                print("✅ 已恢复原始配置")
        except Exception:
            pass

    finally:
        client.close()


if __name__ == "__main__":
    test_default_base_url()
