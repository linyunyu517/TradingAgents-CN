#!/usr/bin/env python3
"""
测试同步控制的三个功能：开始同步、刷新状态、清空缓存
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


async def test_sync_control_functions():
    """测试同步控制的三个核心功能"""
    print("=" * 60)
    print("🧪 测试同步控制功能")
    print("=" * 60)

    try:
        from app.core.database import get_mongo_db, init_db
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service

        # 初始化数据库
        await init_db()
        service = get_multi_source_sync_service()
        db = get_mongo_db()

        print("✅ 服务初始化成功")

        # 1. 测试获取同步状态
        print("\n1. 📊 测试获取同步状态...")
        try:
            status = await service.get_status()
            print(f"   ✅ 当前状态: {status.get('status', 'unknown')}")
            print(
                f"   📈 统计信息: 总数={status.get('total', 0)}, 新增={status.get('inserted', 0)}, 更新={status.get('updated', 0)}",
            )
            if status.get("data_sources_used"):
                print(f"   🔗 使用的数据源: {status.get('data_sources_used')}")
        except Exception as e:
            print(f"   ❌ 获取状态失败: {e}")

        # 2. 测试清空缓存
        print("\n2. 🗑️ 测试清空缓存...")
        try:
            # 先检查是否有缓存数据
            cache_count_before = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   📊 清空前缓存记录数: {cache_count_before}")

            # 清空缓存的逻辑（模拟API调用）
            result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
            service._running = False

            cache_count_after = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   ✅ 清空缓存成功: 删除了{result.deleted_count}条记录")
            print(f"   📊 清空后缓存记录数: {cache_count_after}")

        except Exception as e:
            print(f"   ❌ 清空缓存失败: {e}")

        # 3. 测试开始同步（小规模测试）
        print("\n3. 🚀 测试开始同步...")
        try:
            # 检查数据源可用性
            from app.services.data_source_adapters import DataSourceManager

            manager = DataSourceManager()
            available_adapters = manager.get_available_adapters()

            if not available_adapters:
                print("   ⚠️ 没有可用的数据源，跳过同步测试")
            else:
                print(f"   📡 可用数据源: {[adapter.name for adapter in available_adapters]}")

                # 启动同步（非阻塞）
                print("   🔄 启动同步任务...")

                # 创建一个简单的同步任务来测试
                sync_task = asyncio.create_task(service.run_full_sync(force=True))

                # 等待一小段时间让同步开始
                await asyncio.sleep(2)

                # 检查同步状态
                status = await service.get_status()
                print(f"   📊 同步状态: {status.get('status', 'unknown')}")

                if status.get("status") == "running":
                    print("   ✅ 同步任务已成功启动")
                    print("   ⏳ 等待同步完成...")

                    # 等待同步完成或超时
                    try:
                        await asyncio.wait_for(sync_task, timeout=30)
                        final_status = await service.get_status()
                        print(f"   🎯 同步完成: {final_status.get('status')}")
                        print(
                            f"   📈 最终统计: 总数={final_status.get('total', 0)}, 新增={final_status.get('inserted', 0)}, 更新={final_status.get('updated', 0)}",
                        )
                    except asyncio.TimeoutError:
                        print("   ⏰ 同步超时，但任务仍在后台运行")
                        sync_task.cancel()
                else:
                    print(f"   ⚠️ 同步状态异常: {status.get('status')}")
                    if status.get("message"):
                        print(f"   💬 消息: {status.get('message')}")

        except Exception as e:
            print(f"   ❌ 同步测试失败: {e}")
            import traceback

            traceback.print_exc()

        # 4. 最终状态检查
        print("\n4. 📋 最终状态检查...")
        try:
            final_status = await service.get_status()
            print(f"   📊 最终状态: {final_status.get('status', 'unknown')}")
            print(f"   🕐 开始时间: {final_status.get('started_at', 'N/A')}")
            print(f"   🕑 结束时间: {final_status.get('finished_at', 'N/A')}")

            if final_status.get("data_sources_used"):
                print(f"   🔗 使用的数据源: {', '.join(final_status.get('data_sources_used'))}")

        except Exception as e:
            print(f"   ❌ 最终状态检查失败: {e}")

        print("\n🎉 同步控制功能测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


async def test_api_endpoints():
    """测试API端点（模拟HTTP调用）"""
    print("\n" + "=" * 60)
    print("🌐 测试API端点")
    print("=" * 60)

    try:
        # 这里可以添加HTTP客户端测试
        # 但为了简化，我们直接调用路由函数
        from app.routers.multi_source_sync import clear_sync_cache, get_sync_status, run_stock_basics_sync

        print("1. 📊 测试获取同步状态API...")
        try:
            response = await get_sync_status()
            print(f"   ✅ API响应成功: {response.success}")
            print(f"   📊 状态: {response.data.get('status', 'unknown')}")
        except Exception as e:
            print(f"   ❌ API调用失败: {e}")

        print("\n2. 🗑️ 测试清空缓存API...")
        try:
            response = await clear_sync_cache()
            print(f"   ✅ API响应成功: {response.success}")
            print(f"   💬 消息: {response.message}")
            print(f"   📊 清空项目数: {response.data.get('items_cleared', 0)}")
        except Exception as e:
            print(f"   ❌ API调用失败: {e}")

        print("\n3. 🚀 测试开始同步API...")
        try:
            # 测试启动同步（不等待完成）
            response = await run_stock_basics_sync(force=True)
            print(f"   ✅ API响应成功: {response.success}")
            print(f"   💬 消息: {response.message}")
            print(f"   📊 同步状态: {response.data.get('status', 'unknown')}")
        except Exception as e:
            print(f"   ❌ API调用失败: {e}")

        print("\n🎉 API端点测试完成")

    except Exception as e:
        print(f"❌ API测试失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_sync_control_functions())
    asyncio.run(test_api_endpoints())
