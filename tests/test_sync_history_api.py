#!/usr/bin/env python3
"""
测试同步历史API功能
验证历史记录的获取和显示
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


async def test_sync_history_api():
    """测试同步历史API"""
    print("=" * 60)
    print("📚 测试同步历史API")
    print("=" * 60)

    try:
        from app.core.database import get_mongo_db, init_db
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service

        # 初始化数据库
        await init_db()
        db = get_mongo_db()
        service = get_multi_source_sync_service()

        print("✅ 服务初始化成功")

        # 1. 检查现有历史记录
        print("\n1. 📊 检查现有历史记录...")
        existing_count = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
        print(f"   📈 现有历史记录数: {existing_count}")

        # 2. 如果没有历史记录，创建一些测试数据
        if existing_count == 0:
            print("\n2. 🏗️ 创建测试历史数据...")

            test_records = [
                {
                    "job": "stock_basics_multi_source",
                    "status": "success",
                    "started_at": datetime.utcnow().isoformat(),
                    "finished_at": datetime.utcnow().isoformat(),
                    "total": 5427,
                    "inserted": 0,
                    "updated": 5427,
                    "errors": 0,
                    "data_sources_used": ["stock_list:tushare", "daily_data:tushare"],
                    "last_trade_date": "20250903",
                },
                {
                    "job": "stock_basics_multi_source",
                    "status": "success_with_errors",
                    "started_at": (datetime.utcnow()).isoformat(),
                    "finished_at": (datetime.utcnow()).isoformat(),
                    "total": 5420,
                    "inserted": 15,
                    "updated": 5400,
                    "errors": 5,
                    "data_sources_used": ["stock_list:akshare", "daily_data:tushare"],
                    "last_trade_date": "20250902",
                },
            ]

            result = await db.sync_status.insert_many(test_records)
            print(f"   ✅ 创建了 {len(result.inserted_ids)} 条测试记录")

        # 3. 测试历史记录API（模拟HTTP调用）
        print("\n3. 🌐 测试历史记录API...")

        # 模拟API调用
        from app.routers.multi_source_sync import get_sync_history

        # 测试第一页
        print("   📄 测试第一页...")
        try:
            response = await get_sync_history(page=1, page_size=10)
            print(f"   ✅ API响应成功: {response.success}")
            print(f"   📊 记录数: {len(response.data['records'])}")
            print(f"   📈 总数: {response.data['total']}")
            print(f"   📄 页码: {response.data['page']}")
            print(f"   🔄 是否有更多: {response.data['has_more']}")

            # 显示第一条记录的详细信息
            if response.data["records"]:
                first_record = response.data["records"][0]
                print("   📋 第一条记录:")
                print(f"      状态: {first_record.get('status')}")
                print(f"      总数: {first_record.get('total')}")
                print(f"      开始时间: {first_record.get('started_at')}")
                print(f"      完成时间: {first_record.get('finished_at')}")
                print(f"      数据源: {first_record.get('data_sources_used', [])}")

        except Exception as e:
            print(f"   ❌ API调用失败: {e}")

        # 4. 测试状态筛选
        print("\n4. 🔍 测试状态筛选...")
        try:
            response = await get_sync_history(page=1, page_size=10, status="success")
            print(f"   ✅ 成功状态筛选: {len(response.data['records'])} 条记录")
        except Exception as e:
            print(f"   ❌ 状态筛选失败: {e}")

        # 5. 运行一次新的同步，创建新的历史记录
        print("\n5. 🚀 运行新同步创建历史记录...")
        try:
            sync_result = await service.run_full_sync(force=True)
            print(f"   ✅ 同步完成: {sync_result.get('status')}")

            # 等待一下确保记录已保存
            await asyncio.sleep(1)

            # 再次检查历史记录数量
            new_count = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   📈 新的历史记录数: {new_count}")

        except Exception as e:
            print(f"   ❌ 同步失败: {e}")

        # 6. 最终验证
        print("\n6. ✅ 最终验证...")
        final_response = await get_sync_history(page=1, page_size=5)
        print(f"   📊 最新历史记录数: {len(final_response.data['records'])}")

        if final_response.data["records"]:
            latest = final_response.data["records"][0]
            print(f"   🕐 最新记录时间: {latest.get('started_at')}")
            print(f"   📊 最新记录状态: {latest.get('status')}")

        print("\n🎉 同步历史API测试完成")

        return {
            "total_records": final_response.data["total"],
            "latest_status": final_response.data["records"][0].get("status")
            if final_response.data["records"]
            else None,
            "api_working": True,
        }

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


async def test_frontend_integration():
    """测试前端集成"""
    print("\n" + "=" * 60)
    print("🌐 前端集成测试指南")
    print("=" * 60)

    print("现在你可以在前端测试以下功能：")
    print()
    print("1. 🔄 **刷新同步历史**:")
    print("   - 在同步历史卡片中点击 '刷新' 按钮")
    print("   - 应该能看到真实的历史记录")
    print()
    print("2. 🚀 **运行同步并观察历史更新**:")
    print("   - 点击 '强制重新同步' 按钮")
    print("   - 同步完成后，历史记录应该自动更新")
    print()
    print("3. 🕐 **检查完成时间**:")
    print("   - 完成时间应该显示真实的时间戳")
    print("   - 不再是固定的 '2025/09/04 00:53:38'")
    print()
    print("4. 📊 **验证统计数据**:")
    print("   - 总数、新增、更新、错误数应该是真实数据")
    print("   - 数据源信息应该显示实际使用的数据源")
    print()
    print("5. 🔔 **测试通知功能**:")
    print("   - 同步完成后应该显示成功通知")
    print("   - 包含详细的统计信息")
    print()
    print("如果以上功能都正常工作，说明修复成功！")


if __name__ == "__main__":
    result = asyncio.run(test_sync_history_api())
    if result:
        print("\n📊 测试结果摘要:")
        print(f"   历史记录总数: {result['total_records']}")
        print(f"   最新状态: {result['latest_status']}")
        print(f"   API正常: {result['api_working']}")

    asyncio.run(test_frontend_integration())
