#!/usr/bin/env python3
"""测试新浪接口返回的列名"""

import akshare as ak

print("🔍 测试新浪接口返回的列名...")

# 获取数据
df = ak.stock_zh_a_spot()

print(f"\n✅ 获取到 {len(df)} 条记录")
print(f"\n📋 列名: {list(df.columns)}")

# 显示前10条数据，查看代码格式
print("\n📊 前10条数据（查看代码格式）:")
print(df[["代码", "名称", "最新价"]].head(10))

# 查找测试股票（尝试不同的代码格式）
test_codes = ["000001", "600000", "603175"]

for code in test_codes:
    print(f"\n🔍 查找 {code}:")

    # 尝试1: 直接匹配
    stock_data = df[df["代码"] == code]
    if not stock_data.empty:
        print("  ✅ 直接匹配找到:")
        print(f"     {stock_data.iloc[0][['代码', '名称', '最新价']].to_dict()}")
        continue

    # 尝试2: 匹配 sz/sh 前缀
    for prefix in ["sh", "sz", "bj"]:
        prefixed_code = f"{prefix}{code}"
        stock_data = df[df["代码"] == prefixed_code]
        if not stock_data.empty:
            print(f"  ✅ 带前缀 {prefix} 找到:")
            print(f"     {stock_data.iloc[0][['代码', '名称', '最新价']].to_dict()}")
            break
    else:
        # 尝试3: 包含匹配
        stock_data = df[df["代码"].str.contains(code, na=False)]
        if not stock_data.empty:
            print("  ✅ 包含匹配找到:")
            print(f"     {stock_data.iloc[0][['代码', '名称', '最新价']].to_dict()}")
        else:
            print("  ❌ 未找到")

# 统计不同市场的股票数量
print("\n📊 市场分布:")
for prefix in ["sh", "sz", "bj"]:
    count = len(df[df["代码"].str.startswith(prefix, na=False)])
    print(f"  {prefix.upper()}: {count} 只")

# 查看是否有不带前缀的代码
no_prefix = df[~df["代码"].str.match(r"^(sh|sz|bj)", na=False)]
print(f"  无前缀: {len(no_prefix)} 只")
if len(no_prefix) > 0:
    print(f"  示例: {no_prefix['代码'].head(5).tolist()}")
