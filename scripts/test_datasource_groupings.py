#!/usr/bin/env python3
"""
测试脚本：检查数据库中 datasource_groupings 集合的实际数据
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_mongo_db_sync


def test_datasource_groupings():
    """测试数据源分组配置"""
    print("=" * 80)
    print("📊 测试数据源分组配置")
    print("=" * 80)

    try:
        # 获取数据库连接
        db = get_mongo_db_sync()
        groupings_collection = db.datasource_groupings

        # 查询所有美股数据源分组
        print("\n🔍 查询美股数据源分组 (market_category_id='us_stocks'):")
        print("-" * 80)

        us_groupings = list(
            groupings_collection.find({"market_category_id": "us_stocks"}).sort("priority", -1),
        )  # 按优先级降序排序

        if not us_groupings:
            print("❌ 未找到任何美股数据源分组！")
            return

        print(f"✅ 找到 {len(us_groupings)} 个美股数据源分组\n")

        # 显示每个分组的详细信息
        for i, grouping in enumerate(us_groupings, 1):
            print(f"【分组 {i}】")
            print(f"  数据源名称: {grouping.get('data_source_name')}")
            print(f"  市场分类: {grouping.get('market_category_id')}")
            print(f"  优先级: {grouping.get('priority')}")
            print(f"  启用状态: {grouping.get('enabled')}")
            print(f"  创建时间: {grouping.get('created_at')}")
            print(f"  更新时间: {grouping.get('updated_at')}")
            print(f"  _id: {grouping.get('_id')}")
            print()

        # 统计启用和禁用的数据源
        enabled_count = sum(1 for g in us_groupings if g.get("enabled"))
        disabled_count = len(us_groupings) - enabled_count

        print("-" * 80)
        print("📊 统计信息:")
        print(f"  总数: {len(us_groupings)}")
        print(f"  启用: {enabled_count}")
        print(f"  禁用: {disabled_count}")
        print()

        # 显示启用的数据源优先级顺序
        enabled_sources = [g for g in us_groupings if g.get("enabled")]
        if enabled_sources:
            print("✅ 启用的数据源（按优先级排序）:")
            for i, g in enumerate(enabled_sources, 1):
                print(f"  {i}. {g.get('data_source_name')} (优先级: {g.get('priority')})")
        else:
            print("❌ 没有启用的数据源！")
        print()

        # 显示禁用的数据源
        disabled_sources = [g for g in us_groupings if not g.get("enabled")]
        if disabled_sources:
            print("⚠️ 禁用的数据源:")
            for i, g in enumerate(disabled_sources, 1):
                print(f"  {i}. {g.get('data_source_name')} (优先级: {g.get('priority')})")
        print()

        # 检查是否有重复的数据源
        source_names = [g.get("data_source_name") for g in us_groupings]
        duplicates = [name for name in source_names if source_names.count(name) > 1]
        if duplicates:
            print(f"⚠️ 发现重复的数据源: {set(duplicates)}")
        else:
            print("✅ 没有重复的数据源")
        print()

        print("=" * 80)
        print("✅ 测试完成")
        print("=" * 80)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_all_groupings():
    """测试所有市场的数据源分组"""
    print("\n" + "=" * 80)
    print("📊 测试所有市场的数据源分组")
    print("=" * 80)

    try:
        db = get_mongo_db_sync()
        groupings_collection = db.datasource_groupings

        # 查询所有分组
        all_groupings = list(groupings_collection.find({}))

        print(f"\n✅ 总共找到 {len(all_groupings)} 个数据源分组\n")

        # 按市场分类分组
        markets = {}
        for grouping in all_groupings:
            market = grouping.get("market_category_id", "unknown")
            if market not in markets:
                markets[market] = []
            markets[market].append(grouping)

        # 显示每个市场的分组
        for market, groupings in markets.items():
            print(f"【{market}】")
            print(f"  数据源数量: {len(groupings)}")

            enabled = [g for g in groupings if g.get("enabled")]
            disabled = [g for g in groupings if not g.get("enabled")]

            if enabled:
                print("  启用的数据源:")
                for g in sorted(enabled, key=lambda x: x.get("priority", 0), reverse=True):
                    print(f"    - {g.get('data_source_name')} (优先级: {g.get('priority')})")

            if disabled:
                print("  禁用的数据源:")
                for g in sorted(disabled, key=lambda x: x.get("priority", 0), reverse=True):
                    print(f"    - {g.get('data_source_name')} (优先级: {g.get('priority')})")

            print()

        print("=" * 80)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # 测试美股数据源分组
    test_datasource_groupings()

    # 测试所有市场的数据源分组
    test_all_groupings()
