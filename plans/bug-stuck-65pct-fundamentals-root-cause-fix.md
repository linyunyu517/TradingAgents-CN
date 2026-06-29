# 系统卡在 65%「基本面分析师」阶段 — 根因分析与修复方案

## 一、问题概述

系统在执行 TradingAgents 分析流程时，进度卡在 **65%** 不再推进，对应的 LangGraph 阶段为 **「💼 基本面分析师」**节点。经全面代码审计，发现该问题由**多层超时空隙 + 未保护的阻塞调用**共同导致，且**市场分析师**节点存在相同的风险模式。

---

## 二、文件定位

| 组件 | 文件位置 | 关键行号 |
|------|----------|----------|
| 基本面分析师节点函数 | [`fundamentals_analyst.py:29`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\fundamentals_analyst.py:29) | `fundamentals_analyst_node(state)` |
| 进度映射表 | [`simple_analysis_service.py:1303`](D:\AI-Projects\TradingAgents-CN_v1.0.1\app\services\simple_analysis_service.py:1303) | `"💼 基本面分析师": 65` |
| 节点名称映射 | [`trading_graph.py:1211`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\graph\trading_graph.py:1211) | `'Fundamentals Analyst': "💼 基本面分析师"` |
| 进度回调 | [`trading_graph.py:1136`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\graph\trading_graph.py:1136) | `_send_progress_update()` |
| 回调处理 | [`simple_analysis_service.py:1336`](D:\AI-Projects\TradingAgents-CN_v1.0.1\app\services\simple_analysis_service.py:1336) | `graph_progress_callback(message)` |
| 统一基本面工具 | [`agent_utils.py:1028`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\utils\agent_utils.py:1028) | `get_stock_fundamentals_unified()` |
| Graph 超时配置 | [`trading_graph.py:885-889`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\graph\trading_graph.py:885-889) | `_graph_timeout = config.get("timeout", 900)` |
| 强制工具调用路径 | [`fundamentals_analyst.py:570`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\fundamentals_analyst.py:570) | `unified_tool.invoke({...})` — **无超时** |
| 市场分析师工具调用 | [`market_analyst.py:294`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\market_analyst.py:294) | `tool.invoke(tool_args)` — **无超时** |

---

## 三、根因分析

### 3.1 调用链全景（问题路径）

```
graph.stream() ── LangGraph config timeout=900s (15分钟)
  │
  ├─ fundamentals_analyst_node(state)
  │    │
  │    ├─ [Step 1] safe_chain_invoke(chain, {messages}) ── LLM 调用
  │    │     └─ ChatOpenAI 内置 timeout=quick_timeout(180s)/deep_timeout(900s)
  │    │
  │    ├─ [判断] LLM 未返回 tool_calls + 未返回有效内容
  │    │     → 进入「强制工具调用」路径
  │    │
  │    ├─ [Step 2] unified_tool.invoke({...})               ← ⚠️ 无超时！
  │    │     └─ get_stock_fundamentals_unified()
  │    │          ├─ A股: get_china_stock_data_unified()
  │    │          │     └─ DataSourceManager.get_stock_data()
  │    │          │           ├─ _get_tushare_data() ── _run_async_in_new_loop() timeout=60s
  │    │          │           ├─ _get_efinance_data() ── _run_async_in_new_loop() timeout=60s
  │    │          │           ├─ _get_akshare_data() ── _run_async_in_new_loop() timeout=60s
  │    │          │           └─ _try_fallback_sources() ── 串行尝试剩余数据源
  │    │          │
  │    │          ├─ A股: OptimizedChinaDataProvider._generate_fundamentals_report()
  │    │          │     ├─ get_china_stock_info_unified() ── MongoDB 查询（MongoDB timeout=30s connect/60s socket）
  │    │          │     ├─ _get_industry_info() ── MongoDB 查询
  │    │          │     └─ _estimate_financial_metrics()
  │    │          │           └─ _get_real_financial_metrics() ── 多次 MongoDB 查询
  │    │          │
  │    │          └─ [港股] get_hk_stock_data_unified()
  │    │                ├─ AKShare: get_hk_stock_data_akshare() ── 锁超时 60s
  │    │                └─ Yahoo Finance: get_hk_stock_data() ── timeout=60s
  │    │
  │    └─ [Step 3] safe_chain_invoke(analysis_chain, ...) ── 第二次 LLM 调用
  │
  └─ Graph 整体超时: _graph_timeout=900s（deep_model timeout）
       → 整个 graph 在 900s 后被 LangGraph 强制终止
```

### 3.2 四层超时空隙

| 层级 | 位置 | 当前超时 | 问题 |
|------|------|----------|------|
| 🟢 L1: LLM 调用 | `safe_chain_invoke()` line 299 | `quick_timeout=180s` / `deep_timeout=900s` | ✅ 正常，由 ChatOpenAI 参数传递 |
| 🔴 **L2: 强制工具调用** | `unified_tool.invoke()` **line 570** | **无超时** | **关键问题！** |
| 🔴 **L3: 市场分析师工具** | `tool.invoke(tool_args)` **line 294** | **无超时** | **同类型风险** |
| 🟡 L4: 数据源内部 | `_run_async_in_new_loop()` | `future.result(timeout=60)` | 部分保护，但 HTTP 层超时不一致 |
| 🟡 L5: Graph 整体 | `_graph_timeout = 900s` | 900s（15分钟） | 兜底，但粒度太粗 |

### 3.3 具体阻塞场景

**场景 A — 数据源过慢/超时**：
```
get_china_stock_data_unified(30天数据)
  ├─ _get_tushare_data() 失败 (60s)
  ├─ _try_fallback_sources()
  │    ├─ _get_efinance_data() 失败 (60s)
  │    ├─ _get_akshare_data() 失败 (60s)
  │    └─ _get_baostock_data() 失败 (60s)
  └─ 总耗时: 4×60s = 240s+（仅价格数据）
```
然后 `_generate_fundamentals_report()` 又做多次 MongoDB 查询 + API 调用。

**场景 B — MongoDB 连接阻塞**：
`_get_real_financial_metrics()` 中的 MongoDB 查询使用默认的 `serverSelectionTimeoutMS=5000` + `socketTimeoutMS=60000`，如果 MongoDB 响应慢，单个查询可阻塞 60s。

**场景 C — LLM 流式调用卡住**：
虽然 `ChatOpenAI` 有 `timeout` 参数，但某些模型（特别是 DeepSeek）在流式输出时可能因网络抖动停留在中间状态，`timeout` 仅保护连接阶段而非流式读取阶段。

### 3.4 BUG-NEW-042 已修复（不影响根因）

检查发现 [`simple_analysis_service.py:1355-1367`](D:\AI-Projects\TradingAgents-CN_v1.0.1\app\services\simple_analysis_service.py:1355) 的 `dict` vs `str` 类型兼容修复已实施：
- `_node_key = message.get('message', '')` 处理 dict 消息
- Dict 消息跳过 `_seen_progress_messages` set 去重
- 回退计数器 +1% 最小推进保障

这意味着**进度显示不会卡在 65%**，但**进度更新不卡不代表节点执行不卡**。如果基本面分析师节点本身的 `unified_tool.invoke()` 阻塞数分钟，进度显示会正确停留在 65%（因为节点尚未返回），直到整个 graph 超时（900s）或节点最终完成。

---

## 四、修复方案

### 方案 A（推荐 🏆）：为强制工具调用添加同步超时

**修改文件**：[`fundamentals_analyst.py:570`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\fundamentals_analyst.py:570)

**方案**：使用 `concurrent.futures` 包装 `unified_tool.invoke()` 调用，添加 120 秒超时。

```python
import concurrent.futures

# 替换 line 570-575:
def _invoke_with_timeout(tool, kwargs, timeout=120):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(tool.invoke, kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(f"⏰ [基本面分析师] 工具调用超时 ({timeout}s): {kwargs.get('ticker')}")
            return f"数据获取超时（超过{timeout}秒），请稍后重试"

combined_data = _invoke_with_timeout(unified_tool, {
    'ticker': ticker,
    'start_date': start_date,
    'end_date': current_date,
    'curr_date': current_date
})
```

**优点**：
- 精确保护关键阻塞点
- 120s 足够大部分数据源完成
- 不影响 LLM 调用的现有超时机制
- 侵入性最小

**缺点**：
- 需要硬编码超时值
- 不解决数据源内部超时不一致的问题

---

### 方案 B（推荐 🥈）：为市场分析师添加相同保护

**修改文件**：[`market_analyst.py:294`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\market_analyst.py:294)

**方案**：同样使用 `concurrent.futures` 包装 `tool.invoke(tool_args)` 调用。

```python
# 替换 line 293-294:
import concurrent.futures

def _invoke_tool_with_timeout(tool, tool_args, timeout=120):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(tool.invoke, tool_args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(f"⏰ [市场分析师] 工具调用超时 ({timeout}s): {tool_args}")
            return f"工具执行超时（超过{timeout}秒）"

tool_result = _invoke_tool_with_timeout(tool, tool_args)
```

**优点**：
- 覆盖市场分析师的相同风险模式
- 统一超时策略，代码可复用

---

### 方案 C（补充 🥉）：LangGraph 节点级超时

**修改文件**：[`setup.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\graph\setup.py)（节点注册处）

**方案**：在 GraphSetup 中为每个分析师节点添加超时包装器。

```python
def _with_node_timeout(node_func, node_name, timeout=300):
    """为 LangGraph 节点函数添加超时保护"""
    from functools import wraps
    import concurrent.futures
    
    @wraps(node_func)
    def wrapper(state):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(node_func, state)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"⏰ [节点超时] {node_name} 执行超过 {timeout}s")
                return {
                    f"{node_name.lower()}_report": f"分析超时（超过{timeout}秒）",
                    "messages": []
                }
    return wrapper
```

**优点**：
- 全局保护，覆盖所有分析师节点
- 统一超时策略
- 可配置每个节点的超时时间

**缺点**：
- 修改范围较大，需要改动节点注册逻辑
- 返回兜底报告可能影响下游分析质量

---

## 五、扩散检查（其他分析师节点）

| 分析师 | 文件 | LLM 调用 | 直接 tool.invoke() | 有超时风险？ |
|--------|------|----------|-------------------|-------------|
| 💼 基本面分析师 | [`fundamentals_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\fundamentals_analyst.py) | `safe_chain_invoke` (line 299, 414, 634) | **`unified_tool.invoke()` (line 570)** | **✅ 是** |
| 📊 市场分析师 | [`market_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\market_analyst.py) | `safe_chain_invoke` (line 209) | **`tool.invoke(tool_args)` (line 294)** | **✅ 是** |
| 📰 新闻分析师 | [`news_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\news_analyst.py) | `safe_chain_invoke` (line 258) | 无（通过 ToolNode） | ❌ 否 |
| 💬 社交媒体分析师 | [`social_media_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\social_media_analyst.py) | `safe_chain_invoke` (line 119) | 无（通过 ToolNode） | ❌ 否 |
| 🇨🇳 A股市场分析师 | [`china_market_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\china_market_analyst.py) | `safe_chain_invoke` (line 92, 196) | 无 | ❌ 否 |
| 🐂 看涨研究员 | researchers 目录 | — | 无直接调用 | ❌ 否 |
| 🐻 看跌研究员 | researchers 目录 | — | 无直接调用 | ❌ 否 |

**结论**：**市场分析师**（[`market_analyst.py:294`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\market_analyst.py:294)）存在**完全相同**的阻塞风险模式，应一并修复。

---

## 六、实施步骤

### Step 1: 添加共享超时工具函数

**文件**：[`agent_utils.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\utils\agent_utils.py)

添加一个可复用的同步超时包装器：

```python
import concurrent.futures
from typing import Callable, Any

def invoke_with_timeout(func: Callable, *args, timeout: int = 120, 
                        timeout_msg: str = "操作超时") -> Any:
    """同步调用函数并添加超时保护
    
    Args:
        func: 要调用的函数
        args: 传递给函数的参数
        timeout: 超时秒数（默认 120s）
        timeout_msg: 超时时的返回消息
    
    Returns:
        函数返回值，超时时返回错误字符串
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(f"⏰ [超时保护] {timeout_msg} (超过{timeout}s)")
            return f"❌ {timeout_msg}（超过{timeout}秒），请稍后重试"
```

### Step 2: 修复基本面分析师

**文件**：[`fundamentals_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\fundamentals_analyst.py:570)

修改强制工具调用路径，添加 120s 超时。

### Step 3: 修复市场分析师

**文件**：[`market_analyst.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\analysts\market_analyst.py:294)

修改直接工具调用路径，添加 120s 超时。

### Step 4（可选）：降低 graph 超时阈值

**文件**：[`trading_graph.py:886`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\graph\trading_graph.py:886)

从默认 900s 降低到 600s（10分钟），让用户更早收到超时反馈而非无限等待。

---

## 七、修复前后对比

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| `unified_tool.invoke()` 超时 | ❌ 无，可阻塞数分钟 | ✅ 120s 超时 + 错误返回 |
| `tool.invoke()`（市场分析师） | ❌ 无，可阻塞数分钟 | ✅ 120s 超时 + 错误返回 |
| Graph 整体超时 | 900s 后 LangGraph 强制终止 | 600s（缩短） |
| 进度 65% 卡住 | 节点阻塞 → 进度正确显示 65% 但用户以为卡死 | 工具 120s 超时 → 错误返回 → 节点继续 → 进度推进 |
| MongoDB 查询超时 | 依赖 Mongo 驱动默认值（60s socket） | 依赖 Mongo 驱动默认值 + `_run_async_safely(timeout=60)` |

---

## 八、补充建议（非必须）

1. **添加更细粒度的日志**：在 `unified_tool.invoke()` 调用前后添加明确的时间戳日志，方便定位具体阻塞位置。
2. **统一数据源超时策略**：将所有数据源调用的 `_run_async_in_new_loop()` 超时从 60s 降低到 30s，加快失败速度。
3. **考虑异步重构**：将同步的 `get_stock_fundamentals_unified` 改为异步实现，利用 LangGraph 的异步执行能力。
