"""
测试使用统计记录功能
模拟一次分析并检查是否正确记录
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_usage_recording():
    print("=" * 80)
    print("🧪 测试使用统计记录功能")
    print("=" * 80)

    # 1. 初始化数据库
    print("\n1️⃣ 初始化数据库...")
    try:
        from app.core.database import get_mongo_db, init_db

        await init_db()
        db = get_mongo_db()
        print("✅ 数据库初始化成功")
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        return

    # 2. 创建测试使用记录
    print("\n2️⃣ 创建测试使用记录...")
    try:
        from app.models.config import UsageRecord
        from app.services.usage_statistics_service import UsageStatisticsService

        usage_service = UsageStatisticsService()

        # 创建一个完整的使用记录（包含 currency 字段）
        test_record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            provider="dashscope",
            model_name="qwen-plus",
            input_tokens=2000,
            output_tokens=1000,
            cost=0.015,
            currency="CNY",
            session_id="test_session_001",
            analysis_type="stock_analysis",
            stock_code="600519",
        )

        print("   记录内容:")
        print(f"     Provider: {test_record.provider}")
        print(f"     Model: {test_record.model_name}")
        print(f"     Tokens: {test_record.input_tokens} + {test_record.output_tokens}")
        print(f"     Cost: {test_record.currency} {test_record.cost:.4f}")
        print(f"     Session: {test_record.session_id}")

        # 保存记录
        success = await usage_service.add_usage_record(test_record)

        if success:
            print("✅ 记录保存成功")
        else:
            print("❌ 记录保存失败")
            return
    except Exception as e:
        print(f"❌ 创建记录失败: {e}")
        import traceback

        traceback.print_exc()
        return

    # 3. 验证记录是否保存
    print("\n3️⃣ 验证记录是否保存...")
    try:
        collection = db["token_usage"]

        # 查找刚才保存的记录
        saved_record = await collection.find_one({"session_id": "test_session_001"})

        if saved_record:
            print("✅ 记录已保存到数据库")
            print(f"   MongoDB _id: {saved_record['_id']}")
            print(f"   Provider: {saved_record.get('provider', 'N/A')}")
            print(f"   Model: {saved_record.get('model_name', 'N/A')}")
            print(f"   Cost: {saved_record.get('currency', 'N/A')} {saved_record.get('cost', 0):.4f}")
        else:
            print("❌ 数据库中找不到记录")
            return
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return

    # 4. 测试统计查询
    print("\n4️⃣ 测试统计查询...")
    try:
        stats = await usage_service.get_usage_statistics(days=1)

        print(f"   总请求数: {stats.total_requests}")
        print(f"   总输入 Token: {stats.total_input_tokens:,}")
        print(f"   总输出 Token: {stats.total_output_tokens:,}")
        print(f"   总成本: ¥{stats.total_cost:.4f}")

        if stats.total_requests > 0:
            print("✅ 统计查询成功")
        else:
            print("⚠️  统计查询返回空数据")
    except Exception as e:
        print(f"❌ 统计查询失败: {e}")
        import traceback

        traceback.print_exc()

    # 5. 清理测试数据
    print("\n5️⃣ 清理测试数据...")
    try:
        collection = db["token_usage"]
        result = await collection.delete_many({"session_id": "test_session_001"})
        print(f"✅ 已清理 {result.deleted_count} 条测试记录")
    except Exception as e:
        print(f"❌ 清理失败: {e}")

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


async def test_analysis_service_recording():
    """测试分析服务的记录功能"""
    print("\n" + "=" * 80)
    print("🧪 测试分析服务记录功能")
    print("=" * 80)

    try:
        from app.core.database import get_mongo_db, init_db

        await init_db()
        db = get_mongo_db()

        from bson import ObjectId

        from app.models.analysis import AnalysisResult, AnalysisTask
        from app.services.analysis_service import AnalysisService

        # 创建模拟任务
        task = AnalysisTask(
            task_id="test_task_001",
            user_id=ObjectId(),  # 添加必需的 user_id 字段
            symbol="600519",
            market="CN",
            start_date="2024-01-01",
            end_date="2024-12-31",
            llm_provider="dashscope",
            llm_model="qwen-plus",
        )

        # 创建模拟结果
        result = AnalysisResult(
            task_id="test_task_001",
            symbol="600519",
            market="CN",
            analysis_content="测试分析内容",
            tokens_used=3000,
            status="completed",
        )

        # 测试记录方法
        service = AnalysisService()
        await service._record_token_usage(task, result, "dashscope", "qwen-plus")

        # 验证记录
        collection = db["token_usage"]
        saved_record = await collection.find_one({"session_id": "test_task_001"})

        if saved_record:
            print("✅ 分析服务记录功能正常")
            print(f"   Provider: {saved_record.get('provider', 'N/A')}")
            print(f"   Model: {saved_record.get('model_name', 'N/A')}")
            print(f"   Tokens: {saved_record.get('input_tokens', 0)} + {saved_record.get('output_tokens', 0)}")
            print(f"   Cost: {saved_record.get('currency', 'N/A')} {saved_record.get('cost', 0):.4f}")

            # 清理测试数据
            await collection.delete_many({"session_id": "test_task_001"})
            print("✅ 测试数据已清理")
        else:
            print("❌ 分析服务记录功能失败 - 数据库中找不到记录")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


async def main():
    # 测试1: 基础记录功能
    await test_usage_recording()

    # 测试2: 分析服务记录功能
    await test_analysis_service_recording()


if __name__ == "__main__":
    asyncio.run(main())
