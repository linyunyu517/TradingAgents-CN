#!/usr/bin/env python
"""测试修复后的财务数据获取"""

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

# 创建数据流实例
df = OptimizedChinaDataProvider()

# 测试获取 000002 的财务数据
print("🔍 测试获取 000002 的财务数据...")
result = df._get_cached_raw_financial_data("000002")

if result:
    print("✅ 成功获取财务数据")
    print(f"包含字段: {list(result.keys())}")

    if "balance_sheet" in result:
        print(f"  - 资产负债表记录数: {len(result['balance_sheet'])}")
    if "income_statement" in result:
        print(f"  - 利润表记录数: {len(result['income_statement'])}")
    if "cash_flow" in result:
        print(f"  - 现金流量表记录数: {len(result['cash_flow'])}")
    if "main_indicators" in result:
        print(f"  - 财务指标记录数: {len(result['main_indicators'])}")
else:
    print("❌ 未获取到财务数据")
