#!/usr/bin/env python3
"""
修复美股数据源的 enabled 状态

问题：
- 前端显示数据源为"启用"状态
- 但数据库中 datasource_groupings 集合的 enabled 字段为 false
- 导致系统无法使用配置的数据源

解决方案：
- 读取数据库中的 datasource_groupings 配置
- 将美股数据源的 enabled 字段设置为 true
- 确保优先级配置正确
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from app.core.database import get_mongo_db_sync


def fix_us_datasource_enabled():
    """修复美股数据源的 enabled 状态"""

    print("=" * 60)
    print("修复美股数据源 enabled 状态")
    print("=" * 60)

    try:
        # 获取数据库连接
        db = get_mongo_db_sync()
        groupings_collection = db.datasource_groupings

        # 查询美股数据源分组
        us_groupings = list(groupings_collection.find({"market_category_id": "us_stocks"}))

        if not us_groupings:
            print("❌ 未找到美股数据源分组配置")
            return

        print(f"\n📊 找到 {len(us_groupings)} 个美股数据源分组：\n")

        # 显示当前状态
        for grouping in us_groupings:
            ds_name = grouping.get("data_source_name", "Unknown")
            enabled = grouping.get("enabled", False)
            priority = grouping.get("priority", 0)
            status = "✅ 启用" if enabled else "❌ 禁用"
            print(f"  {ds_name:20s} - {status} - 优先级: {priority}")

        print("\n" + "=" * 60)
        print("开始修复...")
        print("=" * 60 + "\n")

        # 修复配置
        updates = [
            {"name": "Alpha Vantage", "enabled": True, "priority": 3, "reason": "设置为最高优先级，启用"},
            {"name": "Yahoo Finance", "enabled": True, "priority": 2, "reason": "设置为中等优先级，启用"},
            {"name": "Finnhub", "enabled": True, "priority": 1, "reason": "设置为最低优先级，启用（作为备用）"},
        ]

        updated_count = 0
        for update in updates:
            result = groupings_collection.update_one(
                {"data_source_name": update["name"], "market_category_id": "us_stocks"},
                {
                    "$set": {
                        "enabled": update["enabled"],
                        "priority": update["priority"],
                        "updated_at": datetime.utcnow(),
                    },
                },
            )

            if result.matched_count > 0:
                if result.modified_count > 0:
                    print(f"✅ {update['name']:20s} - 已更新 - {update['reason']}")
                    updated_count += 1
                else:
                    print(f"ℹ️  {update['name']:20s} - 无需更新（已是目标状态）")
            else:
                print(f"⚠️  {update['name']:20s} - 未找到配置")

        print("\n" + "=" * 60)
        print("修复完成")
        print("=" * 60 + "\n")

        # 显示修复后的状态
        us_groupings_after = list(groupings_collection.find({"market_category_id": "us_stocks"}).sort("priority", -1))

        print("📊 修复后的配置：\n")
        for grouping in us_groupings_after:
            ds_name = grouping.get("data_source_name", "Unknown")
            enabled = grouping.get("enabled", False)
            priority = grouping.get("priority", 0)
            status = "✅ 启用" if enabled else "❌ 禁用"
            print(f"  {ds_name:20s} - {status} - 优先级: {priority}")

        print(f"\n✅ 成功更新 {updated_count} 个数据源配置")
        print("\n💡 提示：")
        print("   1. 请重启 Web 服务以使配置生效")
        print("   2. 数据源优先级：Alpha Vantage (3) > Yahoo Finance (2) > Finnhub (1)")
        print("   3. 系统会按优先级依次尝试数据源，失败后自动降级")

    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    fix_us_datasource_enabled()
