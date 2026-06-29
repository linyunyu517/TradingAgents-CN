# BUG-035 诊断与修复报告

## 摘要

进度条卡在 20%（首次运行卡在 38%）的双重根本原因分析、修复及验证。

---

## ① 症状分析

| 运行 | 进度演进 | 卡住位置 |
|------|---------|---------|
| BUG-034 前（首次） | 20%→20%(HPC) → 20%→36%(AIF) → 36%→38%(AIF_LLMPrior) | **38%** |
| BUG-034 后（二次） | 20%→20%(count=1..6) 全部 20% | **20%** |

关键日志证据：
```
📊 [Graph进度] 进度已更新: 20% → 20% - 🔮 HPC 预测 (callback_count=1)
📊 [Graph进度] 进度已更新: 20% → 20% - 🔮 AIF 预测 (callback_count=2)
...
🔧 [创建LLM] provider=deepseek, model=o4-mini, url=https://api.openai.com/v1  ← 配置错配！
Retrying request to /chat/completions ...  ← 无限重试！
```

---

## ② 根因分析（H1 + H2）

### H1 — BUG-034 回归（置信度 0.95）

**因果链：**
```
_PROGRESS_TOTAL_STEPS = 30  →  每回调步长 = 3.33%
update_progress_sync(20, ..)  →  初始进度基线 = 20%
new_pct = max(count*100//30, 20)  →  count≤6 时公式值 ≤ 20%
                                             →  卡在 20%
```

**修复方案 B：** 将 `_PROGRESS_TOTAL_STEPS` 从 30 改为 **15**

修复后步长 = 6.67%/callback：
- count=1 → 6%
- count=2 → 13%
- count=3 → **20%** (与基线对齐)
- count=4 → **26%** ✅ 首次超出基线
- count=6 → 40%
- count=15 → 95% (上限)

### H2 — LLM 配置错配（置信度 0.99）

**因果链：**
```
MongoDB config: provider=deepseek, backend_url=https://api.openai.com/v1
          ↓
create_analysis_config() 未设置 backend_url 键
          ↓
TradingAgentsGraph.config 缺少 backend_url
          ↓
回退到 DEFAULT_CONFIG['backend_url'] = 'https://api.openai.com/v1'
          ↓
_create_provider_pair(provider="deepseek") → backend_url="https://api.openai.com/v1"
          ↓
OpenAIClient.get_llm(): self.base_url = "https://api.openai.com/v1" ≠ None
                          → 覆盖 _PROVIDER_CONFIG['deepseek'] = 'https://api.deepseek.com'
          ↓
DeepSeek API Key → OpenAI endpoint → 401 Unauthorized
          ↓
httpx 无限重试（max_retries 未设置）→ 任务永久阻塞
```

**修复方案 A+C：**
- **Fix A:** `create_analysis_config()` 根据解析后的 provider 设置正确的 `backend_url`
- **Fix C:** `_create_provider_pair()` 添加 `max_retries=2` 默认值

---

## ③ 修复方案

| 修复 | 文件 | 变更 |
|------|------|------|
| **Fix A** | `app/services/simple_analysis_service.py:524-538` | `create_analysis_config()` 根据 provider 解析 `backend_url` |
| **Fix B** | `app/services/simple_analysis_service.py:1289` | `_PROGRESS_TOTAL_STEPS = 30 → 15` |
| **Fix C** | `tradingagents/graph/trading_graph.py:169-182` | `_create_provider_pair()` 添加 `max_retries=2` 默认值 |

### Fix A 细节
```python
# 新增代码（create_analysis_config 内）
resolved_backend_url = (
    config.get('backend_url', '')
    or _get_default_backend_url(llm_provider)
    or DEFAULT_CONFIG.get('backend_url', 'https://api.openai.com/v1')
)
analysis_config = {
    ...
    "backend_url": resolved_backend_url,  # 新增键
    ...
}
```
当 `llm_provider="deepseek"` 时，`_get_default_backend_url("deepseek")` 返回 `"https://api.deepseek.com"`，确保创建 LLM 时使用正确的 API 端点。

### Fix B 细节
```python
_PROGRESS_TOTAL_STEPS = 15  # 之前是 30
```
步长从 3.33% → 6.67%/callback。

### Fix C 细节
```python
# _create_provider_pair 中
if "max_retries" not in quick_extra_kwargs:
    quick_extra_kwargs["max_retries"] = 2
if "max_retries" not in deep_extra_kwargs:
    deep_extra_kwargs["max_retries"] = 2
```
通过 `_PASSTHROUGH_KWARGS` → `OpenAIClient.get_llm()` → `NormalizedChatOpenAI` 传递。

---

## ④ 扩散检查

| 检查项 | 结果 |
|--------|------|
| `_PROGRESS_TOTAL_STEPS` 同类模式 | ✅ 仅 `simple_analysis_service.py` 一处 |
| `max_retries` 缺失的其他 LLM 创建入口 | ✅ 无其他 OpenAI-compatible 客户端缺失 |
| `backend_url` 覆盖的其他路径 | ✅ 仅 `create_analysis_config` 一处缺失 |

---

## ⑤ 闭环状态

- [x] H1 验证：日志证据匹配 BUG-034 公式回归
- [x] H2 验证：日志证据匹配 LLM 配置错配 + 无限重试
- [x] Fix A 已应用：`backend_url` 根据 provider 解析
- [x] Fix B 已应用：`_PROGRESS_TOTAL_STEPS = 15`
- [x] Fix C 已应用：`max_retries=2` 默认值
- [x] 扩散检查完成：无同类模式
- [ ] 集成验证：重启服务后观察进度推进和 LLM 调用

---

## 技术债务跟踪

| 项目 | 优先级 | 说明 |
|------|--------|------|
| MongoDB 配置可视化 | P3 | 建议在管理页面上添加 provider/backend_url 联动校验 |
| progress 公式通用化 | P4 | 考虑将 `_PROGRESS_TOTAL_STEPS` 改为动态计算 |
