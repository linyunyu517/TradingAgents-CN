"""
检查MongoDB中现有的分析报告数据
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient


async def check_reports():
    """检查MongoDB中的分析报告"""

    print("=" * 80)
    print("📊 检查MongoDB中的分析报告")
    print("=" * 80)

    # 连接MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["tradingagents"]

    # 1. 检查analysis_reports集合
    print("\n[1] 检查analysis_reports集合...")
    reports_count = await db.analysis_reports.count_documents({})
    print(f"   总记录数: {reports_count}")

    if reports_count > 0:
        # 获取最新的一条记录
        latest_report = await db.analysis_reports.find_one({}, sort=[("created_at", -1)])

        if latest_report:
            print("\n📋 最新报告信息:")
            print(f"   _id: {latest_report.get('_id')}")
            print(f"   analysis_id: {latest_report.get('analysis_id')}")
            print(f"   stock_symbol: {latest_report.get('stock_symbol')}")
            print(f"   analysis_date: {latest_report.get('analysis_date')}")
            print(f"   status: {latest_report.get('status')}")
            print(f"   created_at: {latest_report.get('created_at')}")

            # 检查reports字段
            print("\n📊 reports字段分析:")
            reports = latest_report.get("reports", {})
            print(f"   类型: {type(reports)}")

            if isinstance(reports, dict):
                print(f"   包含 {len(reports)} 个报告:")
                for key, value in reports.items():
                    print(f"      - {key}:")
                    print(f"        类型: {type(value)}")
                    if isinstance(value, str):
                        print(f"        长度: {len(value)} 字符")
                        print(f"        前100字符: {value[:100]}...")
                    else:
                        print(f"        值: {value}")
            else:
                print("   ⚠️ reports不是字典类型")

            # 检查其他关键字段
            print("\n🔍 其他关键字段:")
            print(f"   有 summary: {bool(latest_report.get('summary'))}")
            print(f"   有 recommendation: {bool(latest_report.get('recommendation'))}")
            print(f"   有 decision: {bool(latest_report.get('decision'))}")
            print(f"   有 state: {bool(latest_report.get('state'))}")

    # 2. 检查analysis_tasks集合
    print("\n[2] 检查analysis_tasks集合...")
    tasks_count = await db.analysis_tasks.count_documents({})
    print(f"   总记录数: {tasks_count}")

    if tasks_count > 0:
        # 获取最新的已完成任务
        latest_task = await db.analysis_tasks.find_one({"status": "completed"}, sort=[("created_at", -1)])

        if latest_task:
            print("\n📋 最新已完成任务:")
            print(f"   task_id: {latest_task.get('task_id')}")
            print(f"   stock_code: {latest_task.get('stock_code')}")
            print(f"   status: {latest_task.get('status')}")
            print(f"   created_at: {latest_task.get('created_at')}")

            # 检查result字段
            result = latest_task.get("result", {})
            if result:
                print("\n📊 result字段分析:")
                print(f"   类型: {type(result)}")
                print(f"   键: {list(result.keys())}")

                # 检查reports
                if "reports" in result:
                    reports = result["reports"]
                    print("\n   reports字段:")
                    print(f"      类型: {type(reports)}")
                    if isinstance(reports, dict):
                        print(f"      包含 {len(reports)} 个报告:")
                        for key in reports:
                            print(f"         - {key}")

                # 检查其他字段
                print("\n   其他关键字段:")
                print(f"      有 summary: {bool(result.get('summary'))}")
                print(f"      有 recommendation: {bool(result.get('recommendation'))}")
                print(f"      有 decision: {bool(result.get('decision'))}")
                print(f"      有 state: {bool(result.get('state'))}")

    # 3. 按股票代码查询
    print("\n[3] 按股票代码查询...")
    test_codes = ["000001", "000002", "600519"]

    for code in test_codes:
        count = await db.analysis_reports.count_documents({"stock_symbol": code})
        if count > 0:
            print(f"   {code}: {count} 条记录")

            # 获取该股票的最新报告
            latest = await db.analysis_reports.find_one({"stock_symbol": code}, sort=[("created_at", -1)])

            if latest:
                print(f"      最新报告日期: {latest.get('analysis_date')}")
                print(f"      有reports: {bool(latest.get('reports'))}")
                if latest.get("reports"):
                    print(f"      reports数量: {len(latest.get('reports', {}))}")

    print("\n" + "=" * 80)
    print("✅ 检查完成")
    print("=" * 80)

    client.close()


if __name__ == "__main__":
    asyncio.run(check_reports())
