#!/usr/bin/env python3
"""
测试筛选字段配置API
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_field_config_api():
    """测试筛选字段配置API"""
    print("🧪 测试筛选字段配置API...")

    try:
        # 导入必要的模块
        from app.core.database import init_db
        from app.models.screening import BASIC_FIELDS_INFO

        # 初始化数据库
        await init_db()
        print("✅ 数据库连接成功")

        # 测试字段配置
        print("\n📋 可用筛选字段:")

        # 字段分类
        categories = {
            "basic": ["code", "name", "industry", "area", "market"],
            "market_value": ["total_mv", "circ_mv"],
            "financial": ["pe", "pb", "pe_ttm", "pb_mrq"],
            "trading": ["turnover_rate", "volume_ratio"],
            "price": ["close", "pct_chg", "amount"],
            "technical": ["ma20", "rsi14", "kdj_k", "kdj_d", "kdj_j", "dif", "dea", "macd_hist"],
        }

        for category, fields in categories.items():
            print(f"\n🏷️ {category.upper()}:")
            for field in fields:
                if field in BASIC_FIELDS_INFO:
                    field_info = BASIC_FIELDS_INFO[field]
                    print(f"  ✅ {field}: {field_info.display_name} ({field_info.data_type})")
                    print(f"     描述: {field_info.description}")
                    print(f"     支持操作: {field_info.supported_operators}")
                else:
                    print(f"  ❌ {field}: 字段信息缺失")

        # 测试API响应格式
        response_data = {
            "fields": {
                name: {
                    "name": info.name,
                    "display_name": info.display_name,
                    "field_type": info.field_type.value,
                    "data_type": info.data_type,
                    "description": info.description,
                    "supported_operators": [op.value for op in info.supported_operators],
                }
                for name, info in BASIC_FIELDS_INFO.items()
            },
            "categories": categories,
        }

        print("\n📄 API响应示例:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False)[:500] + "...")

        print("\n🎉 字段配置API测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_field_config_api())
