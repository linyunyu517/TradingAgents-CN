#!/usr/bin/env python3
"""检查美股缓存状态和MongoDB数据"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_mongo_db_sync

print("=" * 80)
print("📊 美股缓存状态检查")
print("=" * 80)

# 1. 检查环境变量
print("\n1️⃣ 环境变量配置")
print("-" * 80)
cache_strategy = os.getenv("TA_CACHE_STRATEGY", "file")
print(f"TA_CACHE_STRATEGY: {cache_strategy}")
print(
    f"说明: {'使用集成缓存（MongoDB/Redis/File）' if cache_strategy in ['integrated', 'adaptive'] else '使用文件缓存'}",
)

# 2. 检查MongoDB中的美股数据
print("\n2️⃣ MongoDB 数据库中的美股数据")
print("-" * 80)

db = get_mongo_db_sync()

# 检查各个集合
collections_to_check = {
    "stock_data": "历史行情数据（缓存）",
    "fundamentals_data": "基本面数据（缓存）",
    "news_data": "新闻数据（缓存）",
    "historical_data_us": "历史行情数据（持久化）",
    "stock_basic_info_us": "股票基础信息（持久化）",
    "market_quotes_us": "实时行情数据（持久化）",
}

print("\n集合名称                    | 说明                     | 数据量")
print("-" * 80)

for collection_name, description in collections_to_check.items():
    try:
        collection = db[collection_name]

        # 统计美股数据（根据不同集合的特征）
        if collection_name in ["stock_data", "fundamentals_data", "news_data"]:
            # 缓存集合：通过 _id 或 symbol 字段判断
            # 美股代码通常是字母，A股是6位数字
            us_count = collection.count_documents(
                {
                    "symbol": {"$regex": "^[A-Z]"},  # 美股代码通常是大写字母
                },
            )
        elif collection_name == "historical_data_us":
            # 历史数据集合
            us_count = collection.count_documents({})
        elif collection_name == "stock_basic_info_us":
            # 基础信息集合
            us_count = collection.count_documents({})
        elif collection_name == "market_quotes_us":
            # 实时行情集合
            us_count = collection.count_documents({})
        else:
            us_count = 0

        status = "✅" if us_count > 0 else "❌"
        print(f"{status} {collection_name:25} | {description:25} | {us_count:,}")

    except Exception as e:
        print(f"❌ {collection_name:25} | {description:25} | 错误: {e}")

# 3. 检查具体的美股缓存数据
print("\n3️⃣ 美股缓存数据详情（stock_data 集合）")
print("-" * 80)

try:
    stock_data_collection = db.stock_data

    # 查找美股数据（通过 _id 或 symbol 判断）
    us_cache_docs = list(stock_data_collection.find({"symbol": {"$regex": "^[A-Z]"}}).limit(10))

    if us_cache_docs:
        print(f"\n找到 {len(us_cache_docs)} 条美股缓存数据（显示前10条）:\n")
        for doc in us_cache_docs:
            symbol = doc.get("symbol", "N/A")
            data_source = doc.get("data_source", "N/A")
            created_at = doc.get("created_at", "N/A")
            cache_key = doc.get("_id", "N/A")

            print(f"股票: {symbol}")
            print(f"  数据源: {data_source}")
            print(f"  缓存键: {cache_key}")
            print(f"  创建时间: {created_at}")
            print()
    else:
        print("❌ 未找到美股缓存数据")

except Exception as e:
    print(f"❌ 查询失败: {e}")

# 4. 检查基本面数据缓存
print("\n4️⃣ 美股基本面数据缓存（fundamentals_data 集合）")
print("-" * 80)

try:
    fundamentals_collection = db.fundamentals_data

    # 查找美股基本面数据
    us_fundamentals = list(fundamentals_collection.find({"symbol": {"$regex": "^[A-Z]"}}).limit(10))

    if us_fundamentals:
        print(f"\n找到 {len(us_fundamentals)} 条美股基本面缓存数据（显示前10条）:\n")
        for doc in us_fundamentals:
            symbol = doc.get("symbol", "N/A")
            data_source = doc.get("data_source", "N/A")
            created_at = doc.get("created_at", "N/A")
            cache_key = doc.get("_id", "N/A")

            print(f"股票: {symbol}")
            print(f"  数据源: {data_source}")
            print(f"  缓存键: {cache_key}")
            print(f"  创建时间: {created_at}")
            print()
    else:
        print("❌ 未找到美股基本面缓存数据")

except Exception as e:
    print(f"❌ 查询失败: {e}")

# 5. 检查文件缓存
print("\n5️⃣ 文件缓存目录")
print("-" * 80)

cache_dir = project_root / "tradingagents" / "dataflows" / "cache" / "data_cache"
us_stocks_dir = cache_dir / "us_stocks"
us_fundamentals_dir = cache_dir / "us_fundamentals"

print(f"\n缓存目录: {cache_dir}")
print(f"美股历史数据: {us_stocks_dir}")
print(f"美股基本面数据: {us_fundamentals_dir}")

if us_stocks_dir.exists():
    us_stock_files = list(us_stocks_dir.glob("*.json"))
    print(f"\n✅ 美股历史数据文件: {len(us_stock_files)} 个")
    if us_stock_files:
        print("\n最近的5个文件:")
        for f in sorted(us_stock_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")
else:
    print(f"❌ 目录不存在: {us_stocks_dir}")

if us_fundamentals_dir.exists():
    us_fundamentals_files = list(us_fundamentals_dir.glob("*.txt"))
    print(f"\n✅ 美股基本面数据文件: {len(us_fundamentals_files)} 个")
    if us_fundamentals_files:
        print("\n最近的5个文件:")
        for f in sorted(us_fundamentals_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")
else:
    print(f"❌ 目录不存在: {us_fundamentals_dir}")

print("\n" + "=" * 80)
print("📋 总结")
print("=" * 80)
print(f"""
当前配置:
  - 缓存策略: {cache_strategy}
  - 文件缓存: {"✅ 有数据" if (us_stocks_dir.exists() and list(us_stocks_dir.glob("*.json"))) else "❌ 无数据"}
  - MongoDB缓存: {"需要检查上面的统计结果"}

建议:
  1. 如果要使用MongoDB缓存，设置环境变量: TA_CACHE_STRATEGY=integrated
  2. 如果MongoDB中没有数据，可能是因为:
     - 使用的是文件缓存策略（默认）
     - MongoDB连接失败，自动降级到文件缓存
     - 数据还没有被保存到MongoDB
""")
