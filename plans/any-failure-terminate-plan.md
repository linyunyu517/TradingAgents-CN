# 方案：任意一个真实数据获取失败就终止

> 需求：只要有一个数据源（Market/Sentiment/News/Fundamentals）获取真实数据失败，立即终止分析
> 方案：ContextVar 共享标记 + 工具层打标 + Bull Researcher 检查
> 修改量：3个文件，约30行

---

## 1. 问题分析

当前系统即使数据源全失败，LLM 也会生成非空报告（"无法获取数据"这样的文本），导致 `are_all_reports_empty()` 永远返回 False，终止机制（C2+C3+C4）无法独立触发。

**根因：终止判断依赖 LLM 输出（报告文本是否为空），但 LLM 永远不输出空文本。**

**解决：将失败检测下沉到数据获取层（工具函数层），用 ContextVar 在工具和 Bull Researcher 间传递失败标记。**

---

## 2. 方案设计

### 核心机制

```
工具函数执行 → 检测到数据获取失败 → 设置 ContextVar = True
                                              ↓
Bull Researcher 运行 → 读取 ContextVar → 如果为 True → 设置 data_source_failure=True
                                              ↓
should_continue_debate() → 检测 data_source_failure → 返回 "__END__" → 终止
```

### 为什么选 ContextVar？

| 方案 | 原因 |
|------|------|
| 全局变量 | 多线程并发会互相覆盖 |
| threading.local | 线程池复用后状态残留 |
| **ContextVar** ✅ | 自动随上下文传播，与 LangGraph 的 StateGraph 线程模型匹配 |
| 修改 AgentState | 工具函数没有访问 State 的权限 |

---

## 3. 修改清单

### 文件 1（新建）：`tradingagents/graph/data_failure_tracker.py`

```python
"""数据获取失败追踪器

使用 ContextVar 在工具函数和 Bull Researcher 之间传递数据失败标记。
ContextVar 是线程/异步上下文安全的，适合 LangGraph 的多线程执行环境。
"""

from contextvars import ContextVar

# 数据获取失败标记（True = 至少一个数据源获取真实数据失败）
_data_fetch_failure_flag: ContextVar[bool] = ContextVar(
    "_data_fetch_failure_flag", default=False
)


def mark_data_fetch_failed() -> None:
    """标记数据获取失败（由工具函数在检测到失败时调用）"""
    _data_fetch_failure_flag.set(True)


def is_data_fetch_failed() -> bool:
    """检查是否有数据获取失败（由 Bull Researcher 调用）"""
    return _data_fetch_failure_flag.get()
```

**为什么这样设计：**
- `ContextVar` 默认 False，新线程自动初始化为 False
- 一旦设为 True，同一上下文内永久 True（符合"一个失败就终止"需求）
- `mark_data_fetch_failed()` 被每个工具函数调用，幂等安全

### 文件 2（修改）：`tradingagents/agents/utils/agent_utils.py`

在 4 个核心工具函数的**返回前**添加失败检测：

```python
# === 顶部新增导入 ===
from tradingagents.graph.data_failure_tracker import mark_data_fetch_failed

# === 工具函数 1: get_stock_market_data_unified (约第1843行) ===
# 在函数末尾 return result 之前添加：
def get_stock_market_data_unified(...):
    ...
    result = ...  # 已有逻辑
    
    # [数据失败终止] 检测：空字符串 或 含 ❌ 的返回 = 数据获取失败
    if not result or not result.strip() or "❌" in result:
        mark_data_fetch_failed()
    
    return result

# === 工具函数 2: get_stock_sentiment_unified (约第2094行) ===
def get_stock_sentiment_unified(...):
    ...
    result = ...
    
    # [数据失败终止] 检测：含失败关键词或无法获取数据的提示
    failure_markers = [
        "当前未获取到", "数据获取异常", "模块未安装",
        "数据获取受限", "total_posts: 0"
    ]
    if result and isinstance(result, str):
        if any(m in result for m in failure_markers):
            mark_data_fetch_failed()
    
    return result

# === 工具函数 3: get_stock_news_unified (约第1968行) ===
def get_stock_news_unified(...):
    ...
    result = ...
    
    # [数据失败终止] 检测
    if not result or not result.strip() or "❌ 无法获取" in result:
        mark_data_fetch_failed()
    
    return result

# === 工具函数 4: get_stock_fundamentals_unified (约第1482行) ===
def get_stock_fundamentals_unified(...):
    ...
    result = ...
    
    # [数据失败终止] 检测：含 ⚠️ 数据获取失败 或 fundamental_score: -1.0
    if result:
        if isinstance(result, str) and "⚠️ 数据获取失败" in result:
            mark_data_fetch_failed()
        elif isinstance(result, dict) and result.get("fundamental_score") == -1.0:
            mark_data_fetch_failed()
    
    return result
```

### 文件 3（修改）：`tradingagents/agents/researchers/bull_researcher.py`

在 `are_all_reports_empty()` 检查之前添加 ContextVar 检查：

```python
# === 顶部新增导入 ===
from tradingagents.graph.data_failure_tracker import is_data_fetch_failed

# === bull_node 函数内，在 are_all_reports_empty 之前添加（约第26行） ===
def bull_node(state) -> dict:
    ...
    
    # [数据失败终止] 优先检查 ContextVar —— 任意数据源失败立即标记
    if is_data_fetch_failed():
        logger.warning(
            "🔧 [数据失败终止] ContextVar 检测到至少一个数据源获取失败，"
            "立即终止分析流程"
        )
        return {
            "investment_debate_state": ...,
            "data_source_failure": True,
            "empty_research_count": state.get("empty_research_count", 0) + 1,
        }
    
    # 原有逻辑继续
    if are_all_reports_empty(state):
        ...
```

---

## 4. 实施顺序

| 步骤 | 文件 | 操作 | 验证 |
|------|------|------|------|
| 1 | `data_failure_tracker.py` | 新建文件 | `python -c "from tradingagents.graph.data_failure_tracker import *"` |
| 2 | `agent_utils.py` | 4处插入 | 语法检查通过 |
| 3 | `bull_researcher.py` | 1处插入 | 语法检查通过 |
| 4 | 全系统 | 运行测试 | `python -m tradingagents --symbol 605300` |

---

## 5. 风险与兜底

| 风险 | 应对 |
|------|------|
| ContextVar 在 LangGraph 中不传播 | 实测验证；ContextVar 继承自父线程，tool_node 和 bull_node 在同一线程执行 |
| 部分数据源失败误判 | failure_markers 可调优，失败检测仅在明确失败时才触发 |
| 与 C1 预检查冲突 | C1 是 graph.stream() 前的检查，ContextVar 是 graph 运行中的检查，互补不冲突 |

## 6. 与已有机制的协同

```
C1 (预检查) → graph.stream() 前检查 → 全失败 → 终止
C2 (假数据移除) → 工具返回空/错误 → ContextVar 捕获 → 终止
C3 (条件路由) → data_source_failure=True → __END__ → 终止
C4 (条件边映射) → __END__: END → 图终止
```

三个终止层互补：C1 最早、ContextVar 在工具层、C3/C4 在 LangGraph 层。
