# 修复 propagation.py 导入 Bug 计划

> 问题: `pre_check_data_sources()` 因导入错误类名和方法名，靠异常触发终止
> 修复量: 2-3行，单个文件
> 影响范围: 仅 `propagation.py`，不影响其他代码

---

## 问题描述

最新运行(605300 佳禾食品)中，数据源预检查虽然让分析在 7.48 秒终止了（之前 678 秒），但终止方式是靠**异常**而不是靠正常逻辑。

日志显示：
```
❌ [数据源预检查] 检查过程异常: 
cannot import name 'ChinaStockDataProvider' 
from 'tradingagents.dataflows.optimized_china_data'
```

因为 `except Exception` 捕获了导入异常，返回 `available=False`，`trading_graph.py` 才终止分析。

**修复后预期效果**：真正尝试获取数据来判断数据源可用性，而不是靠异常来终止。

---

## 修复方案（唯一方案，已验证通过）

经过 tracelattice 3个假设验证，唯一推荐方案为 **H-1（最小修复）**。

### 修改 1: 第35行 — 类名错误

```diff
- from tradingagents.dataflows.optimized_china_data import ChinaStockDataProvider
+ from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
```

**原因**: 实际类名是 `OptimizedChinaDataProvider`（第27行定义），`ChinaStockDataProvider` 不存在。

### 修改 2: 第49行 — 方法名错误

```diff
- fund_data = provider.get_fundamentals(symbol)
+ fund_data = provider.get_fundamentals_data(symbol)
```

**原因**: 实际方法名是 `get_fundamentals_data()`（第194行定义），`get_fundamentals` 不存在。

### 修改 3（可选）: 第42行 — 空日期合理化

```diff
- market_data = provider.get_stock_data(symbol, "", "")
+ market_data = provider.get_stock_data(symbol, "20200101", "20260101")
```

**原因**: `get_stock_data` 的 `start_date=""` 和 `end_date=""` 可能在某些情况下导致意外行为。传入合理日期范围可以获取到正常的历史数据来判断数据源是否可用。

---

## 实施步骤

| 步骤 | 操作 | 精确行号 |
|------|------|---------|
| 1 | `propagation.py` 第35行: `ChinaStockDataProvider` → `OptimizedChinaDataProvider` | L35 |
| 2 | `propagation.py` 第49行: `get_fundamentals` → `get_fundamentals_data` | L49 |
| 3 | `propagation.py` 第42行（可选）: `"", ""` → `"20200101", "20260101"` | L42 |

## 验证方法

修完后运行验证命令确认无导入错误：

```bash
python -c "
from tradingagents.graph.propagation import Propagator
p = Propagator()
result = p.pre_check_data_sources('605300')
print(f'可用: {result[\"available\"]}')
print(f'详情: {result[\"details\"]}')
print(f'原因: {result[\"reason\"]}')
"
```

预期输出（不含导入异常）：
```
可用: True/False
详情: {'market': ..., 'fundamentals': ...}
原因: ...
```

然后可通过完整运行验证实际效果：
```bash
python -m tradingagents --symbol 605300
```

---

## 回滚方案

如果修改后出现意外问题，最简单的回滚方式：

```bash
# 查看当前修改
git diff tradingagents/graph/propagation.py

# 还原单个文件
git checkout -- tradingagents/graph/propagation.py
```

## 风险分析

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| `OptimizedChinaDataProvider` 初始化失败 | 低 | pre_check 返回 available=False（同异常行为） | 已有 except 兜底 |
| `get_fundamentals_data(symbol)` 返回空 | 中 | fundamentals 被标记不可用 | 不影响 market 检查 |
| `get_stock_data(symbol, "20200101", "20260101")` 耗时 | 低 | 预检查延迟增加~0.5秒 | 仅在 graph stream 前执行一次 |
| 空日期 `""` 导致的后端解析问题 | 中 | 可能导致预检查失败 | 建议采用修改3修复此问题 |
