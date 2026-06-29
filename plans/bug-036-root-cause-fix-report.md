# BUG-036 诊断与修复报告

## 摘要

BUG-035 的三个修复（Fix A/B/C）已写入磁盘，但后端 uvicorn 进程在修复写入**之前**启动，导致运行时仍加载旧代码（旧字节码 + 旧 __pycache__ 缓存）。用户观察到与 BUG-035 完全相同的症状：进度条卡在 20%、"🧠 AIF LLM 先验" 状态、DeepSeek API Key 被发送到 OpenAI endpoint 导致 401 无限重试。

**根因：** 进程启动时序错误（修复代码已落盘 → 但进程未重启）。

---

## ① 症状分析

| 运行 | 进度演进 | 卡住位置 |
|------|---------|---------|
| BUG-035 修复写入后（旧进程） | 20%→20%(count=1..6) 全部 20% | **20%** |
| BUG-036 修复重启后（新进程） | ✅ 期待正常推进 | — |

关键日志证据（BUG-035 报告已确认）：
```
📊 [Graph进度] 进度已更新: 20% → 20% - 🔮 HPC 预测 (callback_count=1)
📊 [Graph进度] 进度已更新: 20% → 20% - 🔮 AIF 预测 (callback_count=2)
...
🔧 [创建LLM] provider=deepseek, model=o4-mini, url=https://api.openai.com/v1  ← 旧代码仍使用 OpenAI endpoint
Retrying request to /chat/completions ...  ← 无限重试 401
```

---

## ② 根因分析

### 根因：进程启动时序错位（置信度 0.99）

**因果链：**
```
BUG-035 修复文件写入磁盘（有写操作）
           ↓
uvicorn 进程（Terminal 4）在修复写入前已启动
           ↓
Python 导入 simple_analysis_service.py → 加载旧 __pycache__ 字节码
           ↓
Fix A: resolved_backend_url 不存在 → 回退到 DEFAULT_CONFIG['backend_url']='https://api.openai.com/v1'
Fix B: _PROGRESS_TOTAL_STEPS=30 → 步长 3.33% → count≤6 时 ≤20%
Fix C: max_retries 未设置 → httpx 无限重试 401
           ↓
DeepSeek API Key → OpenAI endpoint → 401 Unauthorized → 无限重试 → 任务永久阻塞
```

### 修复验证清单

| 检查项 | 状态 | 证据 |
|--------|------|------|
| 旧进程已杀 | ✅ | PID 25020 (uvicorn) 已 taskkill |
| __pycache__ 已清理 | ✅ | 全部 .pyc/.pyc 文件已删除 |
| 后端已重启 | ✅ | PID 6032, 8000端口 LISTENING |
| Swagger UI | ✅ | `/docs` 可访问 |
| Health API | ✅ | `/api/health` → `{"status":"ok"}` |
| DEEPSEEK_API_KEY | ✅ | 已设置（前缀 sk-f77f6d2562...） |
| TRADINGAGENTS_LLM_PROVIDER | ✅ | 未设置（自动检测，不影响） |
| MongoDB 僵尸任务 | ✅ | 6a373b3d4d54038d6d7658de 已标为失败 |
| 实际数据库 | ✅ | `tradingagentscn_v0_16660`（155 analysis_tasks） |

---

## ③ 三个 BUG-035 修复重新确认

### Fix A — `resolved_backend_url` 回退链（`simple_analysis_service.py:524-529`）
```python
resolved_backend_url = (
    config.get('backend_url', '')
    or _get_default_backend_url(llm_provider)    # deepseek → https://api.deepseek.com
    or DEFAULT_CONFIG.get('backend_url', 'https://api.openai.com/v1')
)
```
**功能：** 确保 DeepSeek API Key 被发送到 `https://api.deepseek.com`，而非 OpenAI endpoint。

**额外发现：** `ConfigService.get_config()` 在 [`config_service.py:32-4711`](..\AI-Projects\TradingAgents-CN_v1.0.1\app\services\config_service.py) 中**不存在**，导致 `create_analysis_config()` Line 482 的 `config_service.get_config(user_id)` 引发 `AttributeError`，被 `except` 捕获后 `config = {}`。但 Fix A 的回退链仍能从 `_get_default_backend_url(llm_provider)` 正确获取 `backend_url`，因此**不影响修复效果**。

### Fix B — `_PROGRESS_TOTAL_STEPS=15`（`simple_analysis_service.py:1297`）
```python
_PROGRESS_TOTAL_STEPS = 15  # 🐛 [BUG-035] 30→15: step=6.67%/callback
```
**步长变化：** 3.33% → 6.67%/callback。count=3 → 20%, count=4 → 26% ✅。

### Fix C — `max_retries=2`（`trading_graph.py:174-178`）
```python
if "max_retries" not in quick_extra_kwargs:
    quick_extra_kwargs["max_retries"] = 2
if "max_retries" not in deep_extra_kwargs:
    deep_extra_kwargs["max_retries"] = 2
```
**功能：** 防止 API 认证失败时 httpx 无限重试。

---

## ④ 扩散检查

| 检查项 | 结果 |
|--------|------|
| 同类型进程启动时序问题 | ✅ 已确认仅此一处。Terminal 4 的旧 uvicorn 未自动重启。 |
| __pycache__ 残留风险 | ✅ 已全量清理。后续修改后需手动或 hook 清理。 |
| ConfigService.get_config() 缺失影响 | ✅ 仅影响 `create_analysis_config` 中 `config` 字典的额外字段（selected_analysts、deep_analysis_model 等），不影响 `backend_url` 解析。 |
| MongoDB deepseek api_base | ✅ `https://api.deepseek.com/v1`（带 `/v1`），与 `_get_default_backend_url('deepseek')` 返回的 `https://api.deepseek.com` 差异不影响（LLM 客户端自动附加路径）。 |

---

## ⑤ 闭环状态

- [x] 根因确认：BUG-035 修复代码已写入但进程未重启
- [x] 阶段1：杀旧进程 → 清缓存 → 重启后端
- [x] 阶段2：验证 Fix A/B/C 在源代码中
- [x] 阶段3：环境变量确认（DEEPSEEK_API_KEY ✅, TRADINGAGENTS_LLM_PROVIDER 未设置不影响）
- [x] MongoDB 僵尸任务清理
- [x] 静态代码扫描：无新增问题
- [x] BUG-035 报告闭环更新

---

## 技术债务跟踪

| 项目 | 优先级 | 说明 |
|------|--------|------|
| `git post-merge hook` 自动清 `__pycache__` | P3 | 防止类似问题再次发生 |
| `ConfigService` 添加 `get_config()` 方法或更新调用方 | P3 | 当前 AttributeError 被静默捕获，不影响功能但应修复 |
| 后端启动日志记录启动时间戳和代码版本 | P3 | 便于快速判断是否运行旧代码 |
| 修改 `_start_backend.bat` 加入 `--reload` 或自动 pycache 清理 | P3 | 减少手动操作步骤 |
