# PR #2 实施计划：ContextVar 精确数据源故障终止

> 当前状态: `PR #1 (C1-C6)` 已完成，数据源故障终止粗略版已生效
> 问题：预检查太宽松(只检查股票基本信息未查实时价格)，完整分析仍跑842秒
> 目标：**只要有一个真实数据获取失败就立刻终止分析**
> 方案：H-B — Python `contextvars` + 4个工具函数设置标记 + Bull Researcher 检查
> 涉及文件：3个，约10-15行

---

## 目录

1. [方案选择说明](#1-方案选择说明)
2. [方案 H-B：ContextVar 精确终止](#2-方案-h-bcontextvar-精确终止)
3. [修改文件 1: agent_utils.py — ContextVar + 4个工具函数](#3-修改文件-1-agent_utilspy--contextvar--4个工具函数)
4. [修改文件 2: bull_researcher.py — 检查 ContextVar](#4-修改文件-2-bull_researcherpy--检查-contextvar)
5. [修改文件 3: bull_researcher.py (conditional_logic) — 保持 __END__](#5-修改文件-3-bull_researcherpy-conditional_logic--保持-__end__)
6. [运行验证](#6-运行验证)
7. [回滚方案](#7-回滚方案)

---

## 1. 方案选择说明

tracelattice 第1轮对3个候选方案进行了比选：

| 方案 | 描述 | 改动量 | 优点 | 缺点 | 效果 |
|------|------|--------|------|------|------|
| **H-A** | 扩展已有预检查(propagation.py) | ~20行 | 终止最早 | 需重复完整数据获取逻辑，与现有工具函数重复 | ⭐⭐ |
| **H-B ✅** | ContextVar + 工具函数标记 | ~10行 | 精确到每个数据源，工具函数内自然检测，改动最小 | 需导入contextvars | ⭐⭐⭐ |
| **H-C** | 新增LangGraph图节点检查 | ~30行 | 架构清晰 | 新增节点增加复杂度，CR审议周期长 | ⭐ |

**选择 H-B 的原因**：
1. 工具函数(`get_stock_market_data_unified`等)已经在内部判断数据是否成功(有`❌`检测逻辑)
2. 只要在工具函数结尾加 1-2 行代码设置 ContextVar 即可
3. bull_researcher 加一行检查即可
4. 改动量最小(3文件~10行)，效果最好(精确捕获每个数据源状态)

---

## 2. 方案 H-B：ContextVar 精确终止

### 2.1 原理

```
┌──────────────────────────────────────────────────────────────────────┐
│  LangGraph 执行流 (单线程单协程, ContextVar 自然继承)                │
│                                                                      │
│  START → Market Analyst                                              │
│              │─ get_stock_market_data_unified() → ContextVar=True/False│
│              └─ 存储 market_report                                    │
│          → Sentiment Analyst                                         │
│              │─ get_stock_sentiment_unified() → ContextVar=True/False│
│              └─ 存储 sentiment_report                                 │
│          → News Analyst                                              │
│              │─ get_stock_news_unified() → ContextVar=True/False     │
│              └─ 存储 news_report                                      │
│          → Fundamentals Analyst                                      │
│              │─ get_stock_fundamentals_unified() → ContextVar=True/F  │
│              └─ 存储 fundamentals_report                              │
│                                                                      │
│          → Bull Researcher                                           │
│              │─ 检查 ContextVar: 任一失败? → data_source_failure=True│
│              └─ → __END__ (终止)                                     │
│                                                                      │
│  ★ 精确到每个数据源：4个工具函数独立检测各自的数据获取状态            │
│  ★ 任一个返回失败(含❌/错误/空)立即设置 ContextVar                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流关系

```
工具函数(数据源头)              ContextVar(传播)          Bull Researcher(检查)
────────────────────          ──────────────          ─────────────────────
get_stock_market_data  ──→    _data_fetch_failed      if _data_fetch_failed.get():
  return "❌ ..."           ──→  .set(True)               data_source_failure=True
                                                          return {"data_source_failure": True}
get_stock_sentiment     ──→    _data_fetch_failed      ──→ __END__
  return "异常"             ──→  .set(True)
                                                        清理: _data_fetch_failed.set(False)
get_stock_news          ──→    _data_fetch_failed
  return "❌ ..."           ──→  .set(True)

get_stock_fundamentals  ──→    _data_fetch_failed
  return "⚠️ 失败"         ──→  .set(True)
```

### 2.3 为什么用 ContextVar

| 方案 | 问题 |
|------|------|
| 全局变量 (`global`) | 多线程/多分析并行时互相污染 |
| 函数参数传递 | 工具函数是LangGraph ToolNode无参数传递路径 |
| 类实例变量 | 同步问题，分析间隔离复杂 |
| **`contextvars.ContextVar`** | 每个协程/线程独立，自动隔离，零冲突 |

> LangGraph 默认在单线程中运行(除非显式并行)，但 ContextVar 提供了最安全的隔离保障。

---

## 3. 修改文件 1: agent_utils.py — ContextVar + 4个工具函数

**文件**: `tradingagents/agents/utils/agent_utils.py`

### 3.1 添加 ContextVar (约第10行附近)

```python
# ===== [PR #2] 数据源故障检测 ContextVar =====
import contextvars

# 用于在 LangGraph 执行流中传播数据源故障状态
# 每个协程/线程独立，不会跨分析污染
_data_fetch_failed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_data_fetch_failed", default=False
)
```

### 3.2 4个工具函数各加一行（返回前设置标记）

以下4个函数都需要在**返回失败结果之前**(但在记录日志之后)设置标记。

#### 3.2.1 `get_stock_market_data_unified` (约第1958行)

```python
def get_stock_market_data_unified(ticker: str, ...) -> str:
    # ... 现有逻辑 ...
    
    is_success = False  # 跟踪是否成功
    try:
        result = ...   # 调用数据源
        if result and "❌" not in result and "错误" not in result:
            is_success = True
    except Exception as e:
        logger.error(...)
    
    if not is_success:
        # ===== [PR #2] 设置数据源故障标记 =====
        _data_fetch_failed.set(True)
        logger.warning(f"🔴 [数据源故障] get_stock_market_data_unified 失败，标记终止")
    
    return result  # 或错误消息
```

但这种方式需要修改现有 try/except 逻辑结构。更好的方式是**在返回前添加一行**：

```python
def get_stock_market_data_unified(ticker: str, ...) -> str:
    try:
        result = ...
        # 原有成功/失败检测
        if result and "❌" not in result and "错误" not in result:
            return result
        return f"❌ 获取{ticker}股票数据失败: ..."
    except Exception as e:
        logger.error(...)
        result = f"统一市场数据工具执行失败: {e!s}"
    
    # ===== [PR #2] 设置数据源故障标记 =====
    _data_fetch_failed.set(True)
    return result
```

即在**最后返回前**（不管是正常返回错误还是在except返回错误）统一检测结果。

#### 3.2.2 `get_stock_fundamentals_unified` (约第1830行)

在函数末尾返回结果前添加：

```python
    # ===== [PR #2] 设置数据源故障标记 =====
    if result and ("❌" in result or "错误" in result or result.startswith("⚠️")):
        _data_fetch_failed.set(True)
    
    return result
```

#### 3.2.3 `get_stock_news_unified` (约第2085行)

在函数末尾返回结果前添加：

```python
    # ===== [PR #2] 设置数据源故障标记 =====
    if result and "❌" in result:
        _data_fetch_failed.set(True)
    
    return result
```

#### 3.2.4 `get_stock_sentiment_unified` (约第2215行)

在函数末尾返回结果前添加：

```python
    # ===== [PR #2] 设置数据源故障标记 =====
    if not result or "数据获取异常" in result or "未获取到" in result:
        _data_fetch_failed.set(True)
    
    return result
```

### 3.3 检测函数（给 bull_researcher 用）

在同一文件中添加：

```python
# ===== [PR #2] 数据源故障状态查询 =====
def is_data_fetch_failed() -> bool:
    """检查当前上下文中的数据源是否发生故障。

    Returns:
        bool: 任何数据源获取失败返回 True
    """
    return _data_fetch_failed.get()
```

### 3.4 清理函数（在graph运行结束后调用）

```python
def reset_data_fetch_failed():
    """重置数据源故障标记（在graph运行结束后调用）"""
    _data_fetch_failed.set(False)
```

---

## 4. 修改文件 2: bull_researcher.py — 检查 ContextVar

**文件**: `tradingagents/agents/researchers/bull_researcher.py`

### 当前代码 (第25-47行)

```python
        # 🔧 [H10 数据源全故障降级] 检测所有报告是否为空
        if are_all_reports_empty(state):
            empty_count = state.get("empty_research_count", 0) + 1
            ...
            return {
                "investment_debate_state": new_investment_debate_state,
                "data_source_failure": True,
                "empty_research_count": empty_count,
            }
```

### 修改后代码

```python
        # 🔧 [PR #2 ContextVar 精确检测] 检查任一数据源是否获取失败
        if is_data_fetch_failed() or are_all_reports_empty(state):
            empty_count = state.get("empty_research_count", 0) + 1
            logger.warning(
                f"🔴 [PR #2 ContextVar] 检测到数据源故障标记，跳过 LLM 调用"
                f"(data_fetch_failed={is_data_fetch_failed()})",
            )
            placeholder = (
                "⚠️ 数据源不可用：发现数据获取失败。"
                "分析已终止。"
            )
            new_count = investment_debate_state["count"] + 1
            new_investment_debate_state = {
                "history": history + "\n" + f"Bull Analyst: {placeholder}",
                "bull_history": bull_history + "\n" + f"Bull Analyst: {placeholder}",
                "bear_history": investment_debate_state.get("bear_history", ""),
                "current_response": placeholder,
                "count": new_count,
            }
            return {
                "investment_debate_state": new_investment_debate_state,
                "data_source_failure": True,
                "empty_research_count": empty_count,
            }
```

### 修改文件顶部导入

在现有导入（第6行）旁添加：

```python
from tradingagents.agents.utils.agent_utils import are_all_reports_empty, safe_extract_content, safe_llm_invoke
# ===== [PR #2] ContextVar 精确检测 =====
from tradingagents.agents.utils.agent_utils import is_data_fetch_failed
```

---

## 5. 修改文件 3: conditional_logic.py — 保持 __END__

**无需修改！** 因为 PR #1 C3 已经将 `should_continue_debate()` 的 `data_source_failure` 路径改为返回 `"__END__"`，Bull Researcher 返回 `{"data_source_failure": True}` 后会自动触发终止。

```
Bull Researcher 返回 {"data_source_failure": True}
    → LangGraph 调用 should_continue_debate(state)
    → state["data_source_failure"] == True
    → return "__END__"
    → 图终止
```

---

## 6. 运行验证

### 6.1 快速验证（预期终止）

```bash
# 应立刻检测到数据源失败并终止（< 10秒）
python -m tradingagents --symbol 002342
```

预期输出：
```
🔴 [数据源故障] get_stock_market_data_unified 失败，标记终止
🔴 [PR #2 ContextVar] 检测到数据源故障标记，跳过 LLM 调用
🔧 [数据源故障终止] 检测到 data_source_failure 标记，立即终止分析流程
✅ 分析已完成，总耗时: 7.5秒
```

### 6.2 验证成功后清除标记

```python
# 在 trading_graph.py 的 propagate() 返回前添加
from tradingagents.agents.utils.agent_utils import reset_data_fetch_failed
reset_data_fetch_failed()
```

---

## 7. 回滚方案

### 回滚指定文件

```bash
# 回滚 agent_utils.py (ContextVar + 4个工具函数修改)
git checkout -- tradingagents/agents/utils/agent_utils.py

# 回滚 bull_researcher.py (ContextVar 检查)
git checkout -- tradingagents/agents/researchers/bull_researcher.py
```

### 完整回滚

```bash
git revert HEAD  # 或 git reset --hard HEAD~1
```

---

## 附录：修改汇总表

| 文件 | 修改位置 | 添加行 | 修改类型 |
|------|---------|--------|---------|
| `tradingagents/agents/utils/agent_utils.py` | 顶部(约L10) | `import contextvars` + `_data_fetch_failed` | 新增 |
| `tradingagents/agents/utils/agent_utils.py` | `get_stock_market_data_unified` 结尾(L1960) | `if "❌" in result: _data_fetch_failed.set(True)` | 新增1行 |
| `tradingagents/agents/utils/agent_utils.py` | `get_stock_fundamentals_unified` 结尾(L1834) | `if "❌" in result or "⚠️" in result: _data_fetch_failed.set(True)` | 新增1行 |
| `tradingagents/agents/utils/agent_utils.py` | `get_stock_news_unified` 结尾(L2086) | `if "❌" in result: _data_fetch_failed.set(True)` | 新增1行 |
| `tradingagents/agents/utils/agent_utils.py` | `get_stock_sentiment_unified` 结尾(L2217) | `if "数据获取异常" in result: _data_fetch_failed.set(True)` | 新增1行 |
| `tradingagents/agents/utils/agent_utils.py` | 任意位置 | `is_data_fetch_failed()` + `reset_data_fetch_failed()` | 新增2函数 |
| `tradingagents/agents/researchers/bull_researcher.py` | 导入区(L6) | `from ... import is_data_fetch_failed` | 新增导入 |
| `tradingagents/agents/researchers/bull_researcher.py` | `bull_node()` (L26) | `if is_data_fetch_failed() or are_all_reports_empty(state):` | 修改条件 |

**总计**: 2文件(agent_utils.py + bull_researcher.py)，约15行新增

**不需要修改**: conditional_logic.py, setup.py, trading_graph.py, propagation.py (均已在PR #1中完成)
