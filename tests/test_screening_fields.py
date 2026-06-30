#!/usr/bin/env python3
"""
测试筛选字段映射
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_screening_fields():
    """测试筛选字段映射"""
    print("🧪 测试筛选字段映射...")

    try:
        # 导入服务
        from app.core.database import init_db
        from app.models.screening import OperatorType, ScreeningCondition
        from app.services.database_screening_service import get_database_screening_service

        # 初始化数据库
        await init_db()
        print("✅ 数据库连接成功")

        # 获取服务实例
        service = get_database_screening_service()

        # 测试筛选条件
        conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.GTE,
                value=100,  # 总市值 >= 100亿
            ),
        ]

        # 执行筛选
        results, total = await service.screen_stocks(
            conditions=conditions, limit=3, order_by=[{"field": "total_mv", "direction": "desc"}],
        )

        print(f"✅ 筛选完成: 总数={total}, 返回={len(results)}")

        # 检查字段映射
        if results:
            print("\n📋 字段映射检查:")
            first_result = results[0]

            # 检查前端期望的字段
            expected_fields = [
                "code",
                "name",
                "industry",
                "market_cap",
                "pe_ratio",
                "pb_ratio",
                "price",
                "change_percent",
            ]

            print("前端期望的字段:")
            for field in expected_fields:
                value = first_result.get(field)
                status = "✅" if field in first_result else "❌"
                print(f"  {status} {field}: {value}")

            print("\n📄 完整结果示例:")
            print(f"  股票代码: {first_result.get('code')}")
            print(f"  股票名称: {first_result.get('name')}")
            print(f"  所属行业: {first_result.get('industry')}")
            print(f"  市值: {first_result.get('market_cap')}亿")
            print(f"  市盈率: {first_result.get('pe_ratio')}")
            print(f"  市净率: {first_result.get('pb_ratio')}")
            print(f"  当前价格: {first_result.get('price')} (基础筛选为None)")
            print(f"  涨跌幅: {first_result.get('change_percent')} (基础筛选为None)")

        print("\n🎉 字段映射测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_screening_fields())
