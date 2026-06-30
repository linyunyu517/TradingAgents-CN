#!/usr/bin/env python3
"""检查导出文件内容"""

import json


def check_export_file(filepath: str):
    """检查导出文件内容"""
    print(f"📂 检查文件: {filepath}\n")

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        print("=== 文件结构 ===")
        print(f"顶层键: {list(data.keys())}")

        if "export_info" in data:
            print("\n=== 导出信息 ===")
            export_info = data["export_info"]
            print(f"创建时间: {export_info.get('created_at')}")
            print(f"格式: {export_info.get('format')}")
            print(f"集合列表: {export_info.get('collections')}")

        if "data" in data:
            print("\n=== 数据内容 ===")
            collections_data = data["data"]
            print(f"包含 {len(collections_data)} 个集合:\n")

            for coll_name, docs in collections_data.items():
                if isinstance(docs, list):
                    print(f"  ✅ {coll_name}: {len(docs)} 条文档")
                else:
                    print(f"  ⚠️  {coll_name}: 不是列表 (类型: {type(docs)})")

            # 检查分析报告相关集合
            print("\n=== 分析报告相关集合 ===")
            report_collections = ["config_reports", "analysis_results", "analysis_tasks", "debate_records"]

            for coll in report_collections:
                if coll in collections_data:
                    count = len(collections_data[coll]) if isinstance(collections_data[coll], list) else 1
                    print(f"  ✅ {coll}: {count} 条")

                    # 显示第一条数据的键
                    if isinstance(collections_data[coll], list) and len(collections_data[coll]) > 0:
                        first_doc = collections_data[coll][0]
                        if isinstance(first_doc, dict):
                            print(f"     字段: {list(first_doc.keys())[:10]}")
                else:
                    print(f"  ❌ {coll}: 不存在")

        print("\n✅ 文件检查完成")

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    filepath = r"C:\Users\hsliu\Downloads\database_export_config_reports_2025-11-11.json"
    check_export_file(filepath)
