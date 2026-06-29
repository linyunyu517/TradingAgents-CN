# PR #1 实施计划：数据源故障终止 + Bug 修复

> 目标分支: `fix/data-source-termination`
> 涉及文件: 6个
> 预估修改量: ~52行
> 前置依赖: 无（可独立于 PR #2 实施）

---

## 目录

1. [修改清单全景](#1-修改清单全景)
2. [Change 1: 数据源预检查-快速失败](#2-change-1-数据源预检查-快速失败)
3. [Change 2: 移除假数据生成](#3-change-2-移除假数据生成)
4. [Change 3: 终止路由条件逻辑](#4-change-3-终止路由条件逻辑)
5. [Change 4: LangGraph 条件边映射](#5-change-4-langgraph-条件边映射)
6. [Change 5: memory_state_manager 类型修复](#6-change-5-memory_state_manager-类型修复)
7. [Change 6: 股吧爬虫 bytes/bytearray 防护](#7-change-6-股吧爬虫-bytesbytearray-防护)
8. [验证步骤](#8-验证步骤)
9. [回滚方案](#9-回滚方案)

---

## 1. 修改清单全景

| # | 文件 | 修改类型 | 精确行号 | 行数 | 功能 |
|---|------|---------|---------|------|------|
| **C1** | `tradingagents/graph/propagation.py` | **新增函数** | ~第22行后 | ~30行 | 数据源预检查，在graph.stream()前快速失败 |
| **C2a** | `tradingagents/dataflows/optimized_china_data.py` | 修改 | 第1675-1694行 | ~3行 | `_generate_fallback_data()` 返回空值 |
| **C2b** | 同上 | 修改 | 第1696-1709行 | ~3行 | `_generate_fallback_fundamentals()` 返回错误字典 |
| **C2c** | 同上 | 修改 | 第908-929行 | ~3行 | `_estimate_financial_metrics()` 返回错误标记 |
| **C3a** | `tradingagents/graph/conditional_logic.py` | 修改 | 第274-279行 | ~2行 | `data_source_failure` 路径返回 `__END__` |
| **C3b** | 同上 | 修改 | 第281-288行 | ~2行 | 兜底空报告路径也返回 `__END__` |
| **C4a** | `tradingagents/graph/setup.py` | 修改 | 第1935-1942行 | ~2行 | Bull Researcher 条件边加 `__END__: END` |
| **C4b** | 同上 | 修改 | 第1943-1950行 | ~2行 | Bear Researcher 条件边加 `__END__: END` |
| **C5** | `app/services/analysis_service.py` | 修改 | 第551行 | ~1行 | `params.model_dump()` 转 dict |
| **C6** | `tradingagents/dataflows/news/providers/eastmoney_guba_provider.py` | 修改 | 第161/164行 | ~4行 | 扩展类型检查 + 防御性编码 |

---

## 2. Change 1: 数据源预检查-快速失败

**这是最关键的修改。** 在 graph 运行之前就检测数据源状态，避免浪费 LLM Token。

### 方案说明

在 `Propagator` 类中添加 `pre_check_data_sources()` 静态方法。在 `TradingAgentsGraph.propagate()` 调用 `graph.stream()` **之前** 执行此检查。如果所有数据源都失败，直接返回降级结果，不执行 graph。

### 精确代码

**文件**: `tradingagents/graph/propagation.py`
**位置**: 在 `create_initial_state()` 方法之前（第22行前），添加新方法

```python
# 新增: 导入数据源检查
from tradingagents.dataflows.data_source_manager import DataSourceManager
from tradingagents.dataflows.optimized_china_data import ChinaStockDataProvider
import logging

logger = logging.getLogger(__name__)

class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        self.max_recur_limit = max_recur_limit

    # ===== 新增: 数据源预检查 =====
    def pre_check_data_sources(self, symbol: str) -> bool:
        """在graph执行前快速检查数据源是否可用。
        
        Args:
            symbol: 股票代码
            
        Returns:
            bool: True=数据源可用(继续执行), False=全部失败(应该终止)
        """
        logger.info(f"🔍 [数据源预检查] 开始检查 {symbol} 的数据源可用性...")
        
        try:
            provider = ChinaStockDataProvider()
            
            # 尝试获取不同类型的数据
            checks = {
                "market": ("get_stock_data", [symbol]),
                "fundamentals": ("get_fundamentals", [symbol]),
            }
            
            results = {}
            for name, (method, args) in checks.items():
                try:
                    func = getattr(provider, method, None)
                    if func:
                        result = func(*args)
                        results[name] = bool(result and result.strip())
                    else:
                        results[name] = False
                except Exception as e:
                    logger.warning(f"⚠️ [数据源预检查] {name} 数据获取失败: {e}")
                    results[name] = False
            
            success_count = sum(1 for v in results.values() if v)
            logger.info(
                f"📊 [数据源预检查] {symbol}: {success_count}/{len(results)} 数据源可用"
                f" (market={results.get('market')}, fundamentals={results.get('fundamentals')})"
            )
            
            if success_count == 0:
                logger.error(f"❌ [数据源预检查] {symbol} 所有数据源均不可用，建议终止分析")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [数据源预检查] 检查过程本身异常: {e}")
            return False  # 保守策略：检查失败时也终止
```

### 在 `TradingAgentsGraph.propagate()` 中的调用点

**文件**: `tradingagents/graph/trading_graph.py`
**位置**: 在 `graph.stream()` 调用之前（约第1000行附近）

```python
# 在 propagate() 方法中，添加预检查
def propagate(self, ...):
    ...
    init_agent_state = self.propagator.create_initial_state(...)
    
    # ===== 新增: 数据源预检查 =====
    symbol = ...  # 从 init_agent_state 或参数中获取
    if not self.propagator.pre_check_data_sources(symbol):
        logger.warning(f"⏹️ [数据源预检查] {symbol} 数据源全部不可用，终止分析")
        # 返回降级结果
        return init_agent_state, {
            "decision": "分析终止",
            "confidence": 0.0,
            "reasoning": "所有数据源均不可用，无法获取实时数据。请检查网络连接和数据源配置（Tushare Token、AKShare 可用性等）。",
            "data_source_failure": True,
        }
    
    # 原有逻辑继续
    for chunk in self.graph.stream(init_agent_state, ...):
        ...
```

### 为什么选择这个方案？

| 优势 | 说明 |
|------|------|
| **最早期终止** | 在 graph.stream() 之前就终止，0个LLM Token浪费 |
| **不依赖 LLM 输出** | 不依赖"报告是否为空"的检测，直接检查底层数据 |
| **与现有架构一致** | `propagation.py` 本身就是做预处理的 |
| **可独立测试** | 静态方法，可以单独单元测试 |
| **不影响任何现有逻辑** | 新增代码只在check失败时提前返回 |

---

## 3. Change 2: 移除假数据生成

### C2a: `_generate_fallback_data()`

**文件**: `tradingagents/dataflows/optimized_china_data.py`
**当前行号**: 第1675-1694行
**操作**: 替换函数体

**当前代码** (第1675-1694行):
```python
def _generate_fallback_data(self, symbol: str, start_date: str, end_date: str, error_msg: str) -> str:
    """生成备用数据"""
    return f"""# {symbol} A股数据获取失败

## ❌ 错误信息
{error_msg}

## 📊 模拟数据（仅供演示）
- 股票代码: {symbol}
- 股票名称: 模拟公司
- 数据期间: {start_date} 至 {end_date}
- 模拟价格: ¥{random.uniform(10, 50):.2f}
- 模拟涨跌: {random.uniform(-5, 5):+.2f}%

## ⚠️ 重要提示
由于数据接口限制或网络问题，无法获取实时数据。
建议稍后重试或检查网络连接。

生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime("%Y-%m-%d %H:%M:%S")}
"""
```

**修改后代码**:
```python
def _generate_fallback_data(self, symbol: str, start_date: str, end_date: str, error_msg: str) -> str:
    """数据源不可用：返回空值以触发上游终止机制"""
    return ""
```

### C2b: `_generate_fallback_fundamentals()`

**文件**: `tradingagents/dataflows/optimized_china_data.py`
**当前行号**: 第1696-1709行

**当前代码**:
```python
def _generate_fallback_fundamentals(self, symbol: str, error_msg: str) -> str:
    """生成备用基本面数据"""
    return f"""# {symbol} A股基本面分析失败

## ❌ 错误信息
{error_msg}

## 📊 基本信息
- 股票代码: {symbol}
- 分析状态: 数据获取失败
- 建议: 稍后重试或检查网络连接

生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime("%Y-%m-%d %H:%M:%S")}
"""
```

**修改后代码**:
```python
def _generate_fallback_fundamentals(self, symbol: str, error_msg: str) -> str:
    """数据源不可用：返回纯错误消息"""
    return f"⚠️ 数据获取失败：{error_msg}"
```

### C2c: `_estimate_financial_metrics()`

**文件**: `tradingagents/dataflows/optimized_china_data.py`
**当前行号**: 第908-929行

**当前代码**:
```python
# 如果无法获取真实数据，抛出异常
error_msg = f"无法获取股票 {symbol} 的财务数据。MongoDB 获取失败，返回估算值。"
logger.error(f"❌ {error_msg}")
# 返回兜底财务指标，避免上游崩溃
return {
    "total_revenue": 0,
    "net_profit": 0,
    "total_assets": 0,
    "total_liab": 0,
    "total_equity": 0,
    "pe": 0,
    "pb": 0,
    "roe": 0,
    "roa": 0,
    "gross_margin": 0,
    "net_margin": 0,
    "eps": 0,
    "fundamental_score": 0,
    "valuation_score": 0,
    "growth_score": 0,
    "risk_level": "high",
    "error": error_msg,
}
```

**修改后代码**:
```python
# 如果无法获取真实数据，返回错误标记
error_msg = f"无法获取股票 {symbol} 的财务数据。MongoDB 获取失败，返回估算值。"
logger.error(f"❌ {error_msg}")
# 返回显式错误标记（不再使用全零值误导下游）
return {
    "fundamental_score": -1.0,   # -1.0 表示"未知/失败"
    "valuation_score": -1.0,
    "growth_score": -1.0,
    "risk_level": "unknown",      # 明确的"未知"标记
    "error": error_msg,
    # 移除所有全零财务字段
}
```

---

## 4. Change 3: 终止路由条件逻辑

### C3a: `data_source_failure` 检测路径

**文件**: `tradingagents/graph/conditional_logic.py`
**当前行号**: 第274-279行

**当前代码**:
```python
        # 🔧 [H10 数据源全故障降级] 优先级1: 检查 data_source_failure 标记
        if state.get("data_source_failure", False):
            logger.warning(
                "🔧 [H10 数据源全故障降级] 检测到 data_source_failure 标记，跳过辩论阶段直接进入 Research Manager",
            )
            return "Research Manager"
```

**修改后代码**:
```python
        # 🔧 [H10 数据源全故障降级] 优先级1: 检查 data_source_failure 标记 → 立即终止
        if state.get("data_source_failure", False):
            logger.warning(
                "🔧 [数据源故障终止] 检测到 data_source_failure 标记，立即终止分析流程",
            )
            return "__END__"
```

### C3b: 兜底空报告检测路径

**文件**: `tradingagents/graph/conditional_logic.py`
**当前行号**: 第281-288行

**当前代码**:
```python
        # 🔧 [H10 数据源全故障降级] 优先级2: 兜底检测所有报告是否为空
        if state.get("empty_research_count", 0) >= 1 and self._are_all_reports_empty(state):
            logger.warning(
                f"🔧 [H10 数据源全故障降级] 兜底检测：所有分析师报告为空 "
                f"(empty_research_count={state.get('empty_research_count', 0)})，"
                f"跳过辩论阶段直接进入 Research Manager",
            )
            return "Research Manager"
```

**修改后代码**:
```python
        # 🔧 [数据源故障终止] 优先级2: 兜底检测所有报告是否为空 → 立即终止
        if state.get("empty_research_count", 0) >= 1 and self._are_all_reports_empty(state):
            logger.warning(
                f"🔧 [数据源故障终止] 兜底检测：所有分析师报告为空 "
                f"(empty_research_count={state.get('empty_research_count', 0)})，"
                f"立即终止分析流程",
            )
            return "__END__"
```

---

## 5. Change 4: LangGraph 条件边映射

### C4a: Bull Researcher 条件边

**文件**: `tradingagents/graph/setup.py`
**当前行号**: 第1935-1942行

**当前代码**:
```python
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
```

**修改后代码**:
```python
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                "__END__": END,   # ← 新增: 数据源故障时立即终止
            },
        )
```

### C4b: Bear Researcher 条件边

**文件**: `tradingagents/graph/setup.py`
**当前行号**: 第1943-1950行

**当前代码**:
```python
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
```

**修改后代码**:
```python
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
                "__END__": END,   # ← 新增: 安全兜底
            },
        )
```

> **注意**: `END` 已在 `setup.py` 第11行导入：`from langgraph.graph import END, START, StateGraph`
>
> 虽然 Bull Researcher 确认 `data_source_failure=True` 后 Bear Researcher 不会被到达（`__END__` 会跳过所有后续节点），但添加 Bear 的 `__END__` 映射是安全做法。

---

## 6. Change 5: memory_state_manager 类型修复

**文件**: `app/services/analysis_service.py`
**当前行号**: 第551行

**当前代码**:
```python
                memory_manager.create_task_sync(
                    task_id=task_id,
                    user_id=str(converted_user_id),
                    stock_code=stock_symbol,
                    status=TaskStatus.PENDING,
                    parameters=params,       # ← params 是 AnalysisParameters(BaseModel)
                )
```

**修改后代码**:
```python
                memory_manager.create_task_sync(
                    task_id=task_id,
                    user_id=str(converted_user_id),
                    stock_code=stock_symbol,
                    status=TaskStatus.PENDING,
                    parameters=params.model_dump() if hasattr(params, 'model_dump') else params,
                )
```

### 为什么这样修复？

`_calculate_estimated_duration()` 在第326行调用 `parameters.get("research_depth", "标准")`：
```python
research_depth = parameters.get("research_depth", "标准")
```

Pydantic v2 的 `BaseModel` 没有 `.get()` 方法。`model_dump()` 将其转为普通 dict，从而可以调用 `.get()`。

兼容性处理：
- Pydantic v2: `BaseModel.model_dump()` → dict
- Pydantic v1: `BaseModel.dict()` → dict
- 如果既没有 `model_dump` 也没有 `dict`（不是 BaseModel），直接传入原值

---

## 7. Change 6: 股吧爬虫 bytes/bytearray 防护

**文件**: `tradingagents/dataflows/news/providers/eastmoney_guba_provider.py`
**当前行号**: 第161-164行

**当前代码**:
```python
    # 统一为 bytes 处理
    if isinstance(html, bytes):
        raw_bytes = html
    else:
        raw_bytes = html.encode("utf-8", errors="replace")
```

**修改后代码**:
```python
    # 统一为 bytes 处理（覆盖 bytes 和 bytearray）
    if isinstance(html, (bytes, bytearray)):
        raw_bytes = bytes(html) if isinstance(html, bytearray) else html
    elif isinstance(html, str):
        raw_bytes = html.encode("utf-8", errors="replace")
    else:
        # 兜底：尝试 str() 转换
        logger.warning(f"[Guba] 意外输入类型 {type(html).__name__}，尝试 str() 转换")
        raw_bytes = str(html).encode("utf-8", errors="replace")
```

### 错误的触发场景

| 触发条件 | 概率 | 说明 |
|---------|------|------|
| curl_cffi 未安装→回退到 requests | 高 | `response.text` 在某些编码检测失败时返回 bytearray |
| 代理环境下响应编码异常 | 中 | 代理修改 Content-Type 头导致编码检测异常 |
| 服务器返回非标 Content-Type | 低 | 如 `text/html; charset=binary` |

---

## 8. 验证步骤

### 8.1 单元测试

```bash
# 1. 验证 conditional_logic 返回 __END__
pytest tests/ -k "should_continue_debate" -v

# 2. 验证 data_source_failure 标记传播
pytest tests/ -k "data_source_failure" -v

# 3. 验证 are_all_reports_empty
pytest tests/ -k "are_all_reports_empty" -v
```

### 8.2 集成测试

```bash
# 1. 无数据源环境下运行（预期立刻终止）
python -m tradingagents --symbol 002342 --no-env-file

# 2. 正常数据源环境下运行（预期正常执行）
python -m tradingagents --symbol 600519

# 3. 部分数据源失败（预期继续执行但跳过对应分析）
python -m tradingagents --symbol 000001 --mock-failure market
```

### 8.3 手动验证

```python
# 验证 conditional_logic 返回值
from tradingagents.graph.conditional_logic import ConditionalLogic
logic = ConditionalLogic(...)
result = logic.should_continue_debate({"data_source_failure": True})
assert result == "__END__"
```

### 8.4 回归测试

```bash
# 验证不破坏已有的 fusion/aif 模式
python -m pytest tests/ -x -v

# 验证所有 graph 边缘情况
python -m pytest tests/test_graph/ -v
```

---

## 9. 回滚方案

### 9.1 逐文件回滚

如果某个修改导致问题，可以用文件级回滚：

```bash
# 恢复特定文件
git checkout -- tradingagents/graph/conditional_logic.py
git checkout -- tradingagents/graph/setup.py
git checkout -- tradingagents/dataflows/optimized_china_data.py
git checkout -- app/services/analysis_service.py
git checkout -- tradingagents/dataflows/news/providers/eastmoney_guba_provider.py
```

### 9.2 分支级回滚

```bash
# 撤销整个 PR
git revert HEAD
# 或删除分支
git branch -D fix/data-source-termination
```

### 9.3 风险矩阵

| 修改 | 风险等级 | 回滚复杂度 | 影响范围 |
|------|---------|-----------|---------|
| C1 预检查（新增） | 🟢 低 | 1行删除 | 仅失败时影响 |
| C2 假数据移除 | 🟡 中 | 3个函数还原 | 无数据时分析结果为空 |
| C3 路由指向 __END__ | 🟡 中 | 还原 return 值 | 仅 data_source_failure 时 |
| C4 条件边映射 | 🟢 低 | 删除2行 | LangGraph 不识别的键=忽略 |
| C5 model_dump | 🟢 低 | 1行还原 | 仅该参数传递 |
| C6 类型检查 | 🟢 低 | 还原类型检查 | 仅异常输入时 |

---

## 附录：实施顺序与检查点

### 建议实施顺序

```
Step 1: C2 (假数据移除) ──── 最先做，安全且独立
    ↓ 验证: 运行单股分析确认不再有模拟价格
Step 2: C3 (终止路由) + C4 (条件边) ──── 核心修改
    ↓ 验证: 注入 data_source_failure=True 确认 graph 终止
Step 3: C1 (预检查) ──── 新增功能，最后做最安全
    ↓ 验证: 无数据环境下运行确认提前终止
Step 4: C5 (memory fix) + C6 (guba fix) ──── 独立Bug修复
    ↓ 验证: 分别确认修复生效
```

### 每个修改的自检清单

- [ ] C1: `pre_check_data_sources()` 在全部失败时返回 False
- [ ] C1: `propagate()` 在预检查失败时返回降级结果而非执行 graph
- [ ] C2a: `_generate_fallback_data()` 返回空字符串
- [ ] C2b: `_generate_fallback_fundamentals()` 返回纯错误消息
- [ ] C2c: `_estimate_financial_metrics()` 返回 `-1.0` score 和 `"unknown"` risk_level
- [ ] C3a: `data_source_failure=True` 时返回 `__END__` 而不是 `Research Manager`
- [ ] C3b: 兜底空报告检测也返回 `__END__`
- [ ] C4a: Bull Researcher 条件边包含 `"__END__": END`
- [ ] C4b: Bear Researcher 条件边包含 `"__END__": END`
- [ ] C5: `params.model_dump()` 兼容 Pydantic v1/v2
- [ ] C6: `isinstance(html, (bytes, bytearray))` 覆盖所有字节类型
- [ ] 所有 `import END` 语句都已存在（不需要新增）
- [ ] 所有 `logger` 变量都已存在（不需要新增）
- [ ] 没有引入新的 `except:` 裸异常捕获
