#!/usr/bin/env python
"""检查分析任务的报告"""

from pymongo import MongoClient

# 连接数据库
client = MongoClient("mongodb://localhost:27017/")
db = client["tradingagents"]

# 查询任务 ID
task_id = "5f26efbf-3cb5-4542-979d-401c522d2cd3"

# 从 analysis_results 集合查询
result = db.analysis_results.find_one({"analysis_id": task_id})

if result:
    print(f"✅ 找到分析结果: {task_id}")
    print(f"\n📋 股票代码: {result.get('stock_code')}")
    print(f"📅 分析日期: {result.get('analysis_date')}")
    print(f"📊 分析师: {result.get('analysts', [])}")

    # 检查 reports 字段
    reports = result.get("reports", {})
    print(f"\n📄 报告数量: {len(reports)}")
    print("📄 报告类型:")
    for key in reports:
        report = reports[key]
        if isinstance(report, dict):
            print(f"  - {key}: {type(report).__name__}")
            # 显示报告的前100字符
            if "content" in report:
                content = report["content"]
                print(f"      内容长度: {len(content)} 字符")
                print(f"      前100字符: {content[:100]}...")
            elif isinstance(report, str):
                print(f"      内容长度: {len(report)} 字符")
                print(f"      前100字符: {report[:100]}...")
        else:
            print(f"  - {key}: {type(report).__name__}")
else:
    print(f"❌ 未找到分析结果: {task_id}")
