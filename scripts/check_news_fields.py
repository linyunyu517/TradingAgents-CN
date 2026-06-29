#!/usr/bin/env python
"""检查数据库中新闻数据的字段"""

import os
import sys

from pymongo import MongoClient

# 连接数据库
mongo_password = os.getenv("MONGODB_PASSWORD", "")
if not mongo_password:
    print("错误：请设置 MONGODB_PASSWORD 环境变量")
    sys.exit(1)
client = MongoClient(f"mongodb://admin:{mongo_password}@localhost:27017/?authSource=admin")
db = client["tradingagents"]

print("=" * 80)
print("📰 检查数据库中新闻数据的字段")
print("=" * 80)

# 查看一条新闻的完整字段
news = db.stock_news.find_one()

if news:
    print("\n📋 新闻字段列表:")
    for key in sorted(news.keys()):
        value = news.get(key)
        value_type = type(value).__name__

        # 显示值的预览
        if isinstance(value, str):
            value_preview = value[:50] + "..." if len(value) > 50 else value
        elif isinstance(value, list):
            value_preview = f"[{len(value)} items]"
        elif isinstance(value, dict):
            value_preview = "{...}"
        else:
            value_preview = str(value)

        print(f"  - {key:20s} ({value_type:15s}): {value_preview}")

    # 检查是否有 symbol 或 stock_code 字段
    print("\n🔍 关键字段检查:")
    print(f"  - symbol: {news.get('symbol')}")
    print(f"  - stock_code: {news.get('stock_code')}")
    print(f"  - symbols: {news.get('symbols')}")
    print(f"  - full_symbol: {news.get('full_symbol')}")

else:
    print("❌ 数据库中没有新闻数据")

print("\n" + "=" * 80)
client.close()
