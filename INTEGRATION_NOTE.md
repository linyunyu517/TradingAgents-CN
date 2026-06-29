# INTEGRATION_NOTE — 三轮改造集成说明

> 本文件记录 `TradingAgents-CN v1.0.1` 项目在完成三轮模块改造（HPC-Loop、L-IWM、HSR-MC）后的架构现状与集成说明。

---

## 1. 当前状态

### 已完成的三轮模块移植

三轮改造的所有模块均已成功集成到 [`tradingagents/`](tradingagents) 核心引擎中，具体位置如下：

| 模块 | 路径 | 文件数 | 状态 |
|------|------|--------|------|
| HPC-Loop (主动推理) | [`tradingagents/hpc_loop/`](tradingagents/hpc_loop) | 10 .py | ✅ 导入正常，已挂钩 |
| L-IWM (可学习世界模型) | [`tradingagents/l_iwm/`](tradingagents/l_iwm) | 9 .py | ✅ 导入正常 |
| HSR-MC (元认知优化) | [`tradingagents/hsrc_mc/`](tradingagents/hsrc_mc) | 6 .py | ✅ 导入正常 |

### 引擎钩子注入点

三轮改造通过以下方式注入到核心交易图 (`TradingAgentsGraph`) 中：

- **配置项**：[`tradingagents/default_config.py`](tradingagents/default_config.py) 新增 `hpc_loop_enabled`、`l_iwm_enabled`、`hsrc_mc_enabled` 开关
- **引擎入口**：[`tradingagents/graph/trading_graph.py`](tradingagents/graph/trading_graph.py) 中：
  - `HPCLoopManager` 在 `__init__` 中实例化
  - `propagate()` 流程中通过 `self.hpc_loop.enabled` 条件注入 HPC 状态初始化与后处理
  - 桥接了 `l_iwm` 和 `hsrc_mc` 的配置通道

---

## 2. FastAPI Web 前端的当前架构

项目的 Web 前端基于 FastAPI，位于 [`app/`](app) 目录：

```
app/
├── main.py              # FastAPI 应用入口
├── routers/
│   └── analysis.py      # 分析 API 路由
├── services/
│   └── analysis/
│       ├── __init__.py
│       └── status_update_utils.py
└── ... (models, core, middleware, worker 等)
```

**关键观察**：`app/services/analysis/` 目前使用 **独立的轻量分析实现**，没有对接 `TradingAgentsGraph`。这意味着 Web 前端的分析功能和三轮改造模块是分离的。

---

## 3. 在 Web 前端使用三轮改造功能的方案

如果需要在 FastAPI Web 前端中利用三轮改造模块的分析能力，需要执行以下步骤：

### 步骤 A：创建 Graph Bridge

在 [`app/services/analysis/`](app/services/analysis) 中新建 `graph_bridge.py`：

```python
# app/services/analysis/graph_bridge.py
"""
桥接 TradingAgentsGraph 到 FastAPI 服务层。
允许 Web 前端触发完整的多轮推理流程并获取结果。
"""
import asyncio
from typing import Any, Dict, Optional, AsyncGenerator
from tradingagents.graph.trading_graph import TradingAgentsGraph

class GraphBridge:
    """将 TradingAgentsGraph 包装为 FastAPI 可调用的异步服务"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.graph = TradingAgentsGraph(config=config)

    async def analyze(
        self,
        query: str,
        max_rounds: int = 3,
        progress_callback=None
    ) -> Dict[str, Any]:
        """执行完整的多轮分析并返回结果"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.graph.propagate(query, max_rounds, progress_callback)
        )
        return result

    async def analyze_stream(
        self,
        query: str,
        max_rounds: int = 3
    ) -> AsyncGenerator[str, None]:
        """流式版本，逐步返回分析进度"""
        def callback(msg: str):
            # 通过队列传递给异步生成器
            ...
        result = await ...
        yield result
```

### 步骤 B：添加 API 路由

在 [`app/routers/analysis.py`](app/routers/analysis.py) 中添加新的端点：

```python
@router.post("/analysis/deep")
async def deep_analysis(
    request: DeepAnalysisRequest,
    background_tasks: BackgroundTasks
):
    """使用 TradingAgentsGraph 执行深度分析"""
    bridge = GraphBridge()
    result = await bridge.analyze(request.query, request.max_rounds)
    return {"status": "ok", "data": result}
```

### 步骤 C：响应格式转换

将 `TradingAgentsGraph.propagate()` 的输出（包含 agent 状态、消息历史、HPC 状态等）转换为 FastAPI 标准响应格式：

```python
def convert_graph_output_to_api_response(graph_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    转换 TradingAgentsGraph.propagate() 的输出为 FastAPI 响应格式。
    
    输入结构:
    {
        "agent_states": [...],
        "messages": [...],
        "hpc_state": {...},        # 如启用
        "l_iwm_state": {...},      # 如启用
        "hsrc_mc_state": {...},    # 如启用
        "final_answer": str,
        "performance": {...}
    }
    
    输出结构:
    {
        "answer": str,
        "reasoning_steps": [...],
        "metadata": {
            "rounds_completed": int,
            "modules_used": ["hpc", "l_iwm", "hsrc_mc"],
            "performance": {...}
        }
    }
    """
    return {
        "answer": graph_output.get("final_answer", ""),
        "reasoning_steps": [
            {"agent": s.get("agent_name"), "message": s.get("content")}
            for s in graph_output.get("agent_states", [])
        ],
        "metadata": {
            "rounds_completed": len(graph_output.get("agent_states", [])),
            "modules_used": [
                mod for mod, key in [
                    ("hpc", "hpc_state"),
                    ("l_iwm", "l_iwm_state"),
                    ("hsrc_mc", "hsrc_mc_state"),
                ] if graph_output.get(key)
            ],
        }
    }
```

---

## 4. 架构说明

### 这是 v1.0.1 的架构遗留问题

Web 前端（FastAPI `app/`）与核心分析引擎（`tradingagents/`）之间的分离，**不是本次三轮模块迁移引入的**，而是 v1.0.1 项目**原有的架构设计**：

- `tradingagents/` 定位为**核心分析引擎库**，不与 Web 框架耦合
- `app/` 是独立的 **FastAPI Web 服务**，通过轻量实现提供 REST API
- 两者共享配置（通过 `default_config.py`），但运行时相互独立

这种分离的优点是**关注点隔离**（引擎可独立于 Web 服务进行测试和演进），代价是需要显式编写桥接代码才能在 Web API 中使用引擎能力。

### 后续建议

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 🔴 高 | 创建 `graph_bridge.py` | 实现上述桥接模式 |
| 🔴 高 | 添加深度分析 API 端点 | 在 `app/routers/analysis.py` 中 |
| 🟡 中 | 实现流式响应支持 | 基于 SSE 推送 HPC 推理进度 |
| 🟢 低 | 性能监控集成 | 将 `_build_performance_data` 输出到 Prometheus |

---

*本文档由综合验证阶段自动生成，最后更新: 2026-06-06*

---

## 5. 架构遗留问题解决记录（2026-06-09）

### 现状核实

经代码调研确认，`INTEGRATION_NOTE.md` v1 中给出的 `GraphBridge` 伪代码（第 57-99 行）**已过时**。实际架构如下：

- `SimpleAnalysisService`（`app/services/simple_analysis_service.py`）已直接包装 `TradingAgentsGraph.propagate()`，无需新建 GraphBridge 类
- `propagate()` 的实际签名为 `(company_name, trade_date, progress_callback, task_id, stock_code)`，而非伪代码中的 `(query, max_rounds, progress_callback)`
- `_extract_hpc_reports()` 函数已提取 HPC-Loop 的 7 类报告到 API 响应

### 已修复的问题

1. **`_extract_hpc_reports()` 增强**：新增 L-IWM 状态、HSR-MC 状态、AIF 引擎状态、融合模式、扩散模型状态的提取
2. **API 端点增强**：`/tasks/{task_id}/result` 新增 `modules_enabled` 标记，明确告知前端三轮改造各组件的启用状态
3. **性能指标暴露**：`performance_metrics` 节点级耗时数据已加入 API 响应

### 桥接完成状态

| 组件 | API 暴露状态 |
|------|-------------|
| HPC-Loop (12节点) | ✅ 7类报告 + enabled标记 |
| L-IWM (6子模块) | ✅ report + enabled标记 |
| HSR-MC (4节点) | ✅ report + enabled标记 |
| AIF Engine (8节点) | ✅ report + enabled标记 |
| Diffusion Model | ✅ report(如有) + enabled标记 |
| Fusion Mode | ✅ 布尔标记 |
