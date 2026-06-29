# LLM Provider 路由诊断报告

> **诊断目标**：追踪 TradingAgents-CN v1.0.1 "OpenAI API Key 无效"错误的完整根因
> **用户配置**：`.env` 中配置了 `DEEPSEEK_API_KEY`，但未配置 `OPENAI_API_KEY` 和 `TRADINGAGENTS_LLM_PROVIDER`
> **搜索路径**：`d:\AI-Projects\TradingAgents-CN_v1.0.1`
> **诊断日期**：2026-06-19

---

## 步骤 1：调用入口分析 — `POST /api/analysis/single`

### 1.1 API 路由定义

[`app/routers/analysis.py:40-99`](app/routers/analysis.py:40)

```python
@router.post("/single", response_model=Dict[str, Any])
async def submit_single_analysis(
    request: SingleAnalysisRequest, ...
):
    analysis_service = get_simple_analysis_service()          # ← 使用 SimpleAnalysisService
    result = await analysis_service.create_analysis_task(user["id"], request)
    ...
    await asyncio.wait_for(
        service.execute_analysis_background(task_id, user_id, request),  # ← 后台执行
        timeout=3600
    )
```

**关键发现**：`POST /api/analysis/single` 路由到 `SimpleAnalysisService`，而非 `AnalysisService`。

### 1.2 SimpleAnalysisService 执行流

[`simple_analysis_service.py:892-960`](app/services/simple_analysis_service.py:892)

```
execute_analysis_background(task_id, user_id, request)
    → _execute_analysis_sync(task_id, user_id, request, progress_tracker)
        → _run_analysis_sync(task_id, user_id, request, progress_tracker)
```

[`simple_analysis_service.py:1101`](app/services/simple_analysis_service.py:1101):
```python
def _run_analysis_sync(self, task_id, user_id, request, progress_tracker=None):
    config = create_analysis_config(request, user_id, task_id)   # ← 步骤 2
    ...
    trading_graph = self._get_trading_graph(config)               # ← 步骤 3
```

---

## 步骤 2：配置构建 — `create_analysis_config()` 缺失 `llm_provider`

### 2.1 函数签名与返回值

[`simple_analysis_service.py:467-529`](app/services/simple_analysis_service.py:467)

```python
def create_analysis_config(
    request: SingleAnalysisRequest,
    user_id: str,
    task_id: str
) -> Dict[str, Any]:
```

**返回的字典键**：
```python
{
    "selected_analysts": ...,
    "deep_analysis_model": "Pro/deepseek-ai/DeepSeek-R1",
    "quick_analysis_model": "deepseek-ai/DeepSeek-V3",
    "deep_analysis_provider": ...,      # 例如 "siliconflow"
    "quick_analysis_provider": ...,     # 例如 "siliconflow"
    "deep_analysis_backend_url": ...,
    "quick_analysis_backend_url": ...,
    "deep_analysis_api_key": ...,
    "quick_analysis_api_key": ...,
    "analysis_config": ...,
    "user_id": ...,
    "task_id": ...,
}
```

**⚠️ CRITICAL：返回值中不存在 `"llm_provider"` 键！**

### 2.2 Provider 推断逻辑

[`simple_analysis_service.py:446-464`](app/services/simple_analysis_service.py:446):

```python
def _get_default_provider_by_model(model_name: str) -> str:
    if not model_name:
        return 'siliconflow'             # ← 默认 fallback
    if 'deepseek' in model_lower:
        return 'deepseek'
    elif 'gpt' in model_lower or 'o1' in model_lower or 'o3' in model_lower:
        return 'openai'
    else:
        return 'siliconflow'             # ← 默认 fallback（例如 "DeepSeek-V3" 不匹配任何规则 → siliconflow）
```

**⚠️ `'siliconflow'` 在 `factory.py` 中被别名为 `'openai'`！**

[`tradingagents/llm_clients/factory.py:11`](tradingagents/llm_clients/factory.py:11):
```python
_PROVIDER_ALIASES = {
    "dashscope": "qwen",
    "alibaba": "qwen",
    "zhipu": "glm",
    "siliconflow": "openai",       # ← siliconflow → openai 别名！
}
```

---

## 步骤 3：Config 合并与 DEFAULT_CONFIG 填充

### 3.1 `_get_trading_graph()` 合并逻辑

[`simple_analysis_service.py:798-827`](app/services/simple_analysis_service.py:798):

```python
def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
    from tradingagents.default_config import DEFAULT_CONFIG
    merged_config = {**DEFAULT_CONFIG, **config}     # ← DEFAULT_CONFIG 填充缺失键
    trading_graph = TradingAgentsGraph(..., config=merged_config)
    return trading_graph
```

### 3.2 DEFAULT_CONFIG 默认值

[`tradingagents/default_config.py:106-126`](tradingagents/default_config.py:106):

```python
DEFAULT_CONFIG = _apply_env_overrides({
    "llm_provider": "openai",              # ← 默认值 "openai"！
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    ...
})
```

**⚠️ 由于 `create_analysis_config()` 返回的字典没有 `llm_provider` 键，合并后 `merged_config["llm_provider"] == "openai"`！**

### 3.3 `_ENV_OVERRIDES` 机制

[`tradingagents/default_config.py:10-11`](tradingagents/default_config.py:10):

```python
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",  # 可通过环境变量覆盖
    ...
}
```

[`tradingagents/default_config.py:93-100`](tradingagents/default_config.py:93):

```python
def _apply_env_overrides(config: dict) -> dict:
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue          # ← 如果环境变量未设置，跳过！
        config[key] = _coerce(raw, config.get(key))
    return config
```

**⚠️ 用户的 `.env` 文件没有设置 `TRADINGAGENTS_LLM_PROVIDER`，因此 `_apply_env_overrides` 不会覆盖默认值 "openai"！**

---

## 步骤 4：Provider 路由与 API Key 读取

### 4.1 `TradingAgentsGraph.__init__()` 路由决策

[`tradingagents/graph/trading_graph.py:247`](tradingagents/graph/trading_graph.py:247):

```python
normalized_provider = normalize_provider_key(self.config["llm_provider"])  # → "openai"
```

**当 `llm_provider == "openai"` 时**，走以下分支：

[`tradingagents/graph/trading_graph.py:278-308`](tradingagents/graph/trading_graph.py:278):

```python
elif normalized_provider in {"openai", "siliconflow", "openrouter", "aihubmix", "ollama"}:
    api_key = None
    if provider == "siliconflow":
        api_key = os.getenv('SILICONFLOW_API_KEY')
        ...
    elif provider == "openrouter":
        api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')
        ...
    # "openai" 分支：api_key 保持为 None！
    
    self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
        provider=provider,              # "openai"
        config=self.config,
        api_key=api_key,                # None！
        ...
    )
```

### 4.2 `_create_provider_pair()` 传递逻辑

[`tradingagents/graph/trading_graph.py:155-194`](tradingagents/graph/trading_graph.py:155):

```python
def _create_provider_pair(..., api_key=None, ...):
    shared_api_key = api_key or config.get("quick_api_key") or config.get("deep_api_key")
    # → None (因为 api_key=None 且 config 中没有 quick/deep_api_key)
    
    deep_llm = create_llm_by_provider(provider=provider, api_key=shared_api_key, ...)
    quick_llm = create_llm_by_provider(provider=provider, api_key=shared_api_key, ...)
```

### 4.3 `create_llm_by_provider()` API Key 解析

[`tradingagents/graph/trading_graph.py:45-90`](tradingagents/graph/trading_graph.py:45):

```python
def create_llm_by_provider(provider, model, backend_url, ..., api_key=None):
    normalized_provider = normalize_provider_key(provider)  # → "openai"
    
    if normalized_provider in {"openai", "siliconflow", ...}:
        if not api_key:                        # ← True
            if normalized_provider == "siliconflow":
                api_key = os.getenv('SILICONFLOW_API_KEY')
            elif normalized_provider == "openrouter":
                api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')
            elif normalized_provider == "openai":
                api_key = os.getenv('OPENAI_API_KEY')       # ← None！（用户.env没有设置）
            else:
                env_key = env_key_for_provider(normalized_provider)
                ...
```

### 4.4 OpenAIClient.get_llm() 最终验证

[`tradingagents/llm_clients/openai_client.py:190-215`](tradingagents/llm_clients/openai_client.py:190):

```python
def get_llm(self) -> Any:
    if self.provider in _PROVIDER_CONFIG:        # "openai" 不在 _PROVIDER_CONFIG 中！
        ...
    elif self.base_url:                          # 走这个分支
        llm_kwargs["base_url"] = self.base_url
        api_key = self.kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
        # → self.kwargs["api_key"] == None, os.environ.get("OPENAI_API_KEY") == None
        # → api_key == None，不走 llm_kwargs["api_key"] = api_key
        # → NormalizedChatOpenAI 被创建时没有 api_key
        
    return NormalizedChatOpenAI(_provider=self.provider, **llm_kwargs)
    # → 没有 api_key 参数，ChatOpenAI 使用空 key 调用 OpenAI API
    # → OpenAI 返回 "API Key 无效" 错误
```

**关键发现**：`_PROVIDER_CONFIG` 包含 `deepseek`, `qwen`, `glm`, `qianfan`, `openrouter`, `aihubmix`, `ollama`, `custom_openai`，但**不包含 `"openai"`**。对于 "openai" provider，代码降级到 `os.environ.get("OPENAI_API_KEY")`，而用户没有设置此环境变量。

---

## 步骤 5：完整调用链与修复方案

### 5.1 完整调用链（API 后端路径）

```
POST /api/analysis/single
  → app/routers/analysis.py:53: get_simple_analysis_service()
  → app/routers/analysis.py:77: service.execute_analysis_background(task_id, user_id, request)
  → simple_analysis_service.py:958: _execute_analysis_sync(task_id, user_id, request, progress_tracker)
  → simple_analysis_service.py:1062: _run_analysis_sync(task_id, user_id, request, progress_tracker)
  → simple_analysis_service.py:1101: config = create_analysis_config(request, user_id, task_id)
      → 返回 config 不包含 "llm_provider" 键
  → simple_analysis_service.py:1153: trading_graph = self._get_trading_graph(config)
      → merged_config = {**DEFAULT_CONFIG, **config}
      → DEFAULT_CONFIG["llm_provider"] = "openai" 填充缺失值
      → merged_config["llm_provider"] = "openai"
  → trading_graph.py:247: normalized_provider = normalize_provider_key(self.config["llm_provider"])
      → normalized_provider = "openai"
  → trading_graph.py:278: normalized_provider in {"openai", "siliconflow", ...}
      → 进入 "openai" 分支
  → trading_graph.py:283-307: api_key = None（"openai" 分支未设置 api_key）
  → trading_graph.py:297: _create_provider_pair(provider="openai", api_key=None, ...)
  → trading_graph.py:170: shared_api_key = None（config中也没有quick/deep_api_key）
  → trading_graph.py:66-73: create_llm_by_provider(provider="openai", api_key=None)
      → api_key = os.getenv('OPENAI_API_KEY') → None
  → openai_client.py:190-215: OpenAIClient.get_llm()
      → os.environ.get("OPENAI_API_KEY") → None
  → NormalizedChatOpenAI(api_key=None) → OpenAI API 返回 "无效" 错误
```

### 5.2 根因总结

| # | 根本原因 | 文件:行号 | 影响 |
|---|---------|-----------|------|
| 1 | `create_analysis_config()` 返回字典缺少 `llm_provider` 键 | [`simple_analysis_service.py:513-526`](app/services/simple_analysis_service.py:513) | 导致合并时被 DEFAULT_CONFIG 默认值覆盖 |
| 2 | `DEFAULT_CONFIG["llm_provider"] = "openai"` | [`default_config.py:121`](tradingagents/default_config.py:121) | 默认选中的是 OpenAI 而非 DeepSeek |
| 3 | `.env` 未设置 `TRADINGAGENTS_LLM_PROVIDER` | `.env` 文件 | `_apply_env_overrides` 无法覆盖默认值 |
| 4 | `siliconflow` 被别名为 `openai` | [`factory.py:11`](tradingagents/llm_clients/factory.py:11) | 模型推断 fallback 也指向 OpenAI |
| 5 | `_get_default_provider_by_model()` 对未知模型返回 `siliconflow` | [`simple_analysis_service.py:464`](app/services/simple_analysis_service.py:464) | 模型名推断 fallback 链也指向 OpenAI |
| 6 | `OpenAIClient._PROVIDER_CONFIG` 不含 `"openai"` | [`openai_client.py:165-174`](tradingagents/llm_clients/openai_client.py:165) | "openai" provider 只能从环境变量读取 key |

### 5.3 修复方案

#### 方案 A（推荐）：在 `create_analysis_config()` 中添加 `llm_provider`

修改 [`simple_analysis_service.py:513-526`](app/services/simple_analysis_service.py:513)：

```python
# 在 analysis_config 中添加 llm_provider 键
llm_provider = config.get('llm_provider', '') or deep_provider or quick_provider or 'deepseek'
analysis_config = {
    ...
    "llm_provider": llm_provider,          # ← 新增
    "deep_analysis_provider": deep_provider,
    "quick_analysis_provider": quick_provider,
    ...
}
```

**理由**：从 `config_service.get_config()` 或 model name inference 获取用户配置的 provider，同时提供 `deepseek` 作为最终 fallback。

#### 方案 B（快速修复）：在 `.env` 中添加 `TRADINGAGENTS_LLM_PROVIDER=deepseek`

```
TRADINGAGENTS_LLM_PROVIDER=deepseek
```

**理由**：`_apply_env_overrides()` 在 `DEFAULT_CONFIG` 创建时读取此环境变量，覆盖默认的 `"openai"`。但这是治标不治本。

#### 方案 C（二次修复）：修改 `_get_default_provider_by_model()` 对 DeepSeek 模型的识别

[`simple_analysis_service.py:451`](app/services/simple_analysis_service.py:451)：

```python
# 当前：只匹配 'deepseek'（小写）
if 'deepseek' in model_lower:
    return 'deepseek'
    
# 问题：用户模型名 "Pro/deepseek-ai/DeepSeek-R1" 包含 "deepseek" 路径
# 但 "deepseek-ai/DeepSeek-V3" 同样包含 "deepseek"，应该能正确匹配
# 需要验证实际传入的 model_name 是什么
```

---

## 验证假设的日志注入点

如需在运行时验证诊断结论，建议在以下位置添加日志：

1. [`simple_analysis_service.py:1101`](app/services/simple_analysis_service.py:1101)：`config = create_analysis_config(...)` 之后打印 `config.get('llm_provider', 'MISSING')`
2. [`simple_analysis_service.py:817`](app/services/simple_analysis_service.py:817)：合并后打印 `merged_config.get('llm_provider')`
3. [`trading_graph.py:247`](tradingagents/graph/trading_graph.py:247)：打印 `f"normalized_provider = {normalized_provider}"`
4. [`trading_graph.py:283`](tradingagents/graph/trading_graph.py:283)：打印 `f"api_key = {'<set>' if api_key else 'None'}"`
5. [`openai_client.py:205`](tradingagents/llm_clients/openai_client.py:205)：打印 `f"OPENAI_API_KEY from env: {'<set>' if os.environ.get('OPENAI_API_KEY') else 'None'}"`

---

## 诊断结论

**最终诊断**（置信度：95%）：

系统报告 "OpenAI API Key 无效" 的根本原因是 **`create_analysis_config()` 配置构建函数没有将 `llm_provider` 字段包含在返回的配置字典中**，导致在 `_get_trading_graph()` 执行 `{**DEFAULT_CONFIG, **config}` 合并时，`DEFAULT_CONFIG` 中的默认值 `"llm_provider": "openai"` 填充了缺失键。这导致 `TradingAgentsGraph` 使用 OpenAI provider 初始化 LLM，进而尝试读取未在 `.env` 中设置的 `OPENAI_API_KEY` 环境变量，最终引发 "OpenAI API Key 无效" 错误。

**修复优先级**：
1. **立即**：方案 B（.env 加 `TRADINGAGENTS_LLM_PROVIDER=deepseek`）— 无需代码修改
2. **建议**：方案 A（代码修改 `create_analysis_config()`）— 根治问题
3. **可选**：确认 `_get_default_provider_by_model()` 对用户实际使用的模型名是否正确推断

---

*报告由 Roo Debug 模式自动生成*
