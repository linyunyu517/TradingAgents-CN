#!/usr/bin/env python3
"""
测试数据一致性检查功能
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

import pandas as pd

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


def test_data_consistency_checker():
    """测试数据一致性检查器"""
    print("=" * 60)
    print("🧪 测试数据一致性检查功能")
    print("=" * 60)

    try:
        from app.services.data_source_adapters import DataSourceManager

        # 1. 测试数据源管理器初始化
        print("\n1. 初始化数据源管理器...")
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()

        print(f"✅ 可用数据源: {[adapter.name for adapter in available_adapters]}")
        print(f"✅ 一致性检查器: {'可用' if manager.consistency_checker else '不可用'}")

        if len(available_adapters) < 2:
            print("⚠️ 需要至少2个数据源才能进行一致性检查")
            return

        # 2. 测试获取数据
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"\n2. 获取{trade_date}的数据进行一致性检查...")

        # 使用一致性检查获取数据
        data, source, consistency_report = manager.get_daily_basic_with_consistency_check(trade_date)

        if data is not None and not data.empty:
            print(f"✅ 成功获取数据: {len(data)}条记录，来源: {source}")

            if consistency_report:
                print("\n📊 一致性检查报告:")
                print(f"   数据一致性: {'✅ 一致' if consistency_report['is_consistent'] else '❌ 不一致'}")
                print(f"   置信度分数: {consistency_report['confidence_score']:.2f}")
                print(f"   推荐行动: {consistency_report['recommended_action']}")
                print(f"   解决策略: {consistency_report['resolution_strategy']}")
                print(f"   主数据源: {consistency_report['primary_source']}")
                print(f"   次数据源: {consistency_report['secondary_source']}")

                # 显示具体差异
                if consistency_report["differences"]:
                    print("\n📈 指标差异详情:")
                    for metric, diff_info in consistency_report["differences"].items():
                        if isinstance(diff_info, dict) and "difference_pct" in diff_info:
                            print(f"   {metric}:")
                            print(f"     主数据源值: {diff_info.get('primary_value', 'N/A')}")
                            print(f"     次数据源值: {diff_info.get('secondary_value', 'N/A')}")
                            if diff_info.get("difference_pct") is not None:
                                print(f"     差异百分比: {diff_info['difference_pct']:.2%}")
                            print(f"     是否显著: {'是' if diff_info.get('is_significant') else '否'}")
                            print(f"     容忍度: {diff_info.get('tolerance', 0):.2%}")
            else:
                print("ℹ️ 未进行一致性检查（可能只有一个数据源可用）")
        else:
            print("❌ 未能获取数据")

        # 3. 测试单独的一致性检查器
        print("\n3. 测试独立的一致性检查器...")

        if manager.consistency_checker and len(available_adapters) >= 2:
            # 分别获取两个数据源的数据
            primary_adapter = available_adapters[0]
            secondary_adapter = available_adapters[1]

            primary_data = primary_adapter.get_daily_basic(trade_date)
            secondary_data = secondary_adapter.get_daily_basic(trade_date)

            if primary_data is not None and secondary_data is not None:
                consistency_result = manager.consistency_checker.check_daily_basic_consistency(
                    primary_data, secondary_data, primary_adapter.name, secondary_adapter.name,
                )

                print("✅ 独立一致性检查完成:")
                print(f"   一致性: {consistency_result.is_consistent}")
                print(f"   置信度: {consistency_result.confidence_score:.2f}")
                print(f"   推荐行动: {consistency_result.recommended_action}")

                # 测试冲突解决
                final_data, strategy = manager.consistency_checker.resolve_data_conflicts(
                    primary_data, secondary_data, consistency_result,
                )
                print(f"   解决策略: {strategy}")
                print(f"   最终数据条数: {len(final_data) if final_data is not None else 0}")
            else:
                print("⚠️ 无法获取足够的数据进行独立检查")

        print("\n✅ 数据一致性检查测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


def test_mock_data_consistency():
    """使用模拟数据测试一致性检查逻辑"""
    print("\n" + "=" * 60)
    print("🧪 使用模拟数据测试一致性检查逻辑")
    print("=" * 60)

    try:
        from app.services.data_consistency_checker import DataConsistencyChecker

        checker = DataConsistencyChecker()

        # 创建模拟数据
        # 主数据源数据
        primary_data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
                "pe": [10.5, 15.2, 8.9],
                "pb": [1.2, 2.1, 0.9],
                "total_mv": [100000, 50000, 80000],
                "trade_date": ["20241201", "20241201", "20241201"],
            },
        )

        # 次数据源数据（略有差异）
        secondary_data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
                "pe": [10.8, 15.0, 9.1],  # 轻微差异
                "pb": [1.25, 2.0, 0.95],  # 轻微差异
                "total_mv": [101000, 49500, 81000],  # 轻微差异
                "trade_date": ["20241201", "20241201", "20241201"],
            },
        )

        print("📊 模拟数据创建完成:")
        print(f"   主数据源: {len(primary_data)}条记录")
        print(f"   次数据源: {len(secondary_data)}条记录")

        # 进行一致性检查
        result = checker.check_daily_basic_consistency(primary_data, secondary_data, "Tushare", "AKShare")

        print("\n📈 一致性检查结果:")
        print(f"   数据一致性: {result.is_consistent}")
        print(f"   置信度分数: {result.confidence_score:.3f}")
        print(f"   推荐行动: {result.recommended_action}")

        print("\n📊 详细差异:")
        for metric, diff in result.differences.items():
            if isinstance(diff, dict):
                print(f"   {metric}:")
                print(f"     主数据源平均值: {diff.get('primary_value', 'N/A')}")
                print(f"     次数据源平均值: {diff.get('secondary_value', 'N/A')}")
                if diff.get("difference_pct") is not None:
                    print(f"     差异百分比: {diff['difference_pct']:.2%}")
                print(f"     是否显著: {diff.get('is_significant', False)}")

        # 测试冲突解决
        final_data, strategy = checker.resolve_data_conflicts(primary_data, secondary_data, result)

        print("\n🔧 冲突解决:")
        print(f"   策略: {strategy}")
        print(f"   最终数据条数: {len(final_data)}")

        print("\n✅ 模拟数据测试完成")

    except Exception as e:
        print(f"❌ 模拟数据测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_data_consistency_checker()
    test_mock_data_consistency()
