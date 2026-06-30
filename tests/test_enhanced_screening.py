#!/usr/bin/env python3
"""
测试增强的股票筛选功能
"""

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_enhanced_screening():
    """测试增强筛选功能"""
    print("🧪 测试增强的股票筛选功能...")

    try:
        # 导入服务
        from app.core.database import init_db
        from app.models.screening import OperatorType, ScreeningCondition
        from app.services.enhanced_screening_service import get_enhanced_screening_service

        # 初始化数据库
        await init_db()
        print("✅ 数据库连接成功")

        # 获取服务实例
        service = get_enhanced_screening_service()

        # 测试1: 获取支持的字段信息
        print("\n📋 测试1: 获取支持的字段信息")
        fields = await service.get_all_supported_fields()
        print(f"✅ 支持的字段数量: {len(fields)}")
        for field in fields[:5]:  # 显示前5个字段
            print(f"  - {field['name']}: {field['display_name']} ({field['field_type']})")

        # 测试2: 基础信息筛选（数据库优化）
        print("\n🔍 测试2: 基础信息筛选（数据库优化）")
        conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.GTE,
                value=100,  # 总市值 >= 100亿
            ),
            ScreeningCondition(
                field="pe",
                operator=OperatorType.BETWEEN,
                value=[5, 30],  # 市盈率在5-30之间
            ),
            ScreeningCondition(
                field="industry",
                operator=OperatorType.CONTAINS,
                value="银行",  # 行业包含"银行"
            ),
        ]

        start_time = time.time()
        result = await service.screen_stocks(conditions=conditions, limit=10, use_database_optimization=True)
        time.time()

        print("✅ 筛选完成:")
        print(f"  - 总数量: {result['total']}")
        print(f"  - 返回数量: {len(result['items'])}")
        print(f"  - 耗时: {result.get('took_ms', 0)}ms")
        print(f"  - 优化方式: {result.get('optimization_used')}")
        print(f"  - 数据源: {result.get('source')}")

        # 显示前3个结果
        if result["items"]:
            print("  - 前3个结果:")
            for i, item in enumerate(result["items"][:3], 1):
                print(
                    f"    {i}. {item.get('code')} {item.get('name')} "
                    f"市值:{item.get('total_mv')}亿 PE:{item.get('pe')} "
                    f"行业:{item.get('industry')}",
                )

        # 测试3: 验证筛选条件
        print("\n✅ 测试3: 验证筛选条件")
        validation = await service.validate_conditions(conditions)
        print(f"  - 验证结果: {'通过' if validation['valid'] else '失败'}")
        if validation["errors"]:
            print(f"  - 错误: {validation['errors']}")
        if validation["warnings"]:
            print(f"  - 警告: {validation['warnings']}")

        # 测试4: 字段统计信息
        print("\n📊 测试4: 字段统计信息")
        field_info = await service.get_field_info("total_mv")
        if field_info:
            stats = field_info.get("statistics", {})
            print("  - 总市值统计:")
            print(f"    最小值: {stats.get('min')}亿")
            print(f"    最大值: {stats.get('max')}亿")
            print(f"    平均值: {stats.get('avg')}亿")
            print(f"    数据量: {stats.get('count')}条")

        # 测试5: 性能对比（数据库 vs 传统）
        print("\n⚡ 测试5: 性能对比")

        # 简单条件（适合数据库优化）
        simple_conditions = [ScreeningCondition(field="total_mv", operator=OperatorType.GTE, value=50)]

        # 数据库优化方式
        start_time = time.time()
        db_result = await service.screen_stocks(conditions=simple_conditions, limit=20, use_database_optimization=True)
        db_time = time.time() - start_time

        # 传统方式
        start_time = time.time()
        traditional_result = await service.screen_stocks(
            conditions=simple_conditions, limit=20, use_database_optimization=False,
        )
        traditional_time = time.time() - start_time

        print(f"  - 数据库优化: {db_result.get('took_ms', 0)}ms, 结果数: {len(db_result['items'])}")
        print(f"  - 传统方式: {traditional_result.get('took_ms', 0)}ms, 结果数: {len(traditional_result['items'])}")
        print(f"  - 性能提升: {traditional_time / db_time:.1f}x" if db_time > 0 else "  - 无法计算性能提升")

        # 测试6: 复杂筛选条件
        print("\n🔧 测试6: 复杂筛选条件")
        complex_conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.BETWEEN,
                value=[100, 1000],  # 市值100-1000亿
            ),
            ScreeningCondition(
                field="pe",
                operator=OperatorType.LTE,
                value=20,  # PE <= 20
            ),
            ScreeningCondition(
                field="pb",
                operator=OperatorType.LTE,
                value=3,  # PB <= 3
            ),
            ScreeningCondition(
                field="area",
                operator=OperatorType.IN,
                value=["北京", "上海", "深圳"],  # 地区在一线城市
            ),
        ]

        complex_result = await service.screen_stocks(
            conditions=complex_conditions, limit=15, order_by=[{"field": "total_mv", "direction": "desc"}],
        )

        print("✅ 复杂筛选完成:")
        print(f"  - 总数量: {complex_result['total']}")
        print(f"  - 返回数量: {len(complex_result['items'])}")
        print(f"  - 耗时: {complex_result.get('took_ms', 0)}ms")
        print(f"  - 优化方式: {complex_result.get('optimization_used')}")

        if complex_result["items"]:
            print("  - 前5个结果:")
            for i, item in enumerate(complex_result["items"][:5], 1):
                print(
                    f"    {i}. {item.get('code')} {item.get('name')} "
                    f"市值:{item.get('total_mv')}亿 PE:{item.get('pe')} "
                    f"PB:{item.get('pb')} 地区:{item.get('area')}",
                )

        print("\n🎉 所有测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_enhanced_screening())
