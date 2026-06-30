#!/usr/bin/env python3
"""
简单检查数据源优先级配置（使用pymongo）
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient

# 连接MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["trading_agents"]

print("=" * 80)
print("📊 数据源优先级配置检查")
print("=" * 80)

# 检查港股数据源配置
print("\n🇭🇰 港股数据源配置 (market_category_id='hk_stocks'):")
print("-" * 80)
hk_groupings = list(db.datasource_groupings.find({"market_category_id": "hk_stocks"}).sort("priority", -1))

if hk_groupings:
    for g in hk_groupings:
        print(f"  数据源: {g.get('data_source_name')}")
        print(f"    优先级: {g.get('priority')}")
        print(f"    启用: {g.get('enabled')}")
        print()
else:
    print("  ❌ 未找到港股数据源配置")

# 检查美股数据源配置
print("\n🇺🇸 美股数据源配置 (market_category_id='us_stocks'):")
print("-" * 80)
us_groupings = list(db.datasource_groupings.find({"market_category_id": "us_stocks"}).sort("priority", -1))

if us_groupings:
    for g in us_groupings:
        print(f"  数据源: {g.get('data_source_name')}")
        print(f"    优先级: {g.get('priority')}")
        print(f"    启用: {g.get('enabled')}")
        print()
else:
    print("  ❌ 未找到美股数据源配置")

# 检查A股数据源配置（参考）
print("\n🇨🇳 A股数据源配置 (market_category_id='a_shares'):")
print("-" * 80)
cn_groupings = list(db.datasource_groupings.find({"market_category_id": "a_shares"}).sort("priority", -1))

if cn_groupings:
    for g in cn_groupings:
        print(f"  数据源: {g.get('data_source_name')}")
        print(f"    优先级: {g.get('priority')}")
        print(f"    启用: {g.get('enabled')}")
        print()
else:
    print("  ❌ 未找到A股数据源配置")

print("=" * 80)
print("✅ 检查完成")
print("=" * 80)

client.close()
