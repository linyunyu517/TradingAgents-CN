# FIX-9: Tushare 融合优化方案 (Fusion)

## 3 轮深度分析总结

### 发现的核心问题

Tushare API 服务器（阿里云 ALB）**间歇性挂断新 TCP 连接**：
- TCP 握手成功 → HTTP POST 发出后 ALB 无响应 → 挂起约 10s → ALB 关闭连接
- Windows 表现为 `FileNotFoundError(2, 'No such file or directory')`
- 这不是客户端代码 bug，是 ALB 级的行为
- "坏周期"时 100% 失败，正常时 <0.1s 响应

### 关键数据点

| 项目 | 之前 | 之后(方案D) |
|------|------|------------|
| 重试次数 | 60次 (connect_sync) / 61次 (_api_call_with_retry) | **3次 / 5次** |
| HTTP timeout | 10s | **5s** |
| HTTPS timeout | 45s | **5s (且跳过)** |
| 双协议降级 | HTTP失败→HTTPS | **跳过HTTPS** |
| Tushare官方建议 | 远偏离 | **遵循官方推荐** |

## 唯一最佳方案: 方案 D (Fusion)

只改 **1 个文件** `tushare.py`，约 **5 行代码**。

### 改动清单

| # | 位置 | 修改 | 说明 |
|---|------|------|------|
| 1 | `connect_sync()` - `_api_call_with_retry` 调用 | `max_retries=60` → **`max_retries=3`** | 连接验证用 3 次重试 |
| 2 | `_api_call_with_retry()` 函数签名 | `max_retries=60` → **`max_retries=5`** | 数据查询用 5 次重试 |
| 3 | `patched_query()` HTTP timeout | `effective_timeout = 10` → **`effective_timeout = 5`** | 匹配 ALB 内部超时 |
| 4 | `patched_query()` HTTPS timeout | `api._DataApi__timeout or 45` → **`5`** | 统一 5s |
| 5 | `patched_query()` for 循环 | 去掉 HTTPS 尝试 | HTTP 和 HTTPS 走同一个 ALB，失败原因相同，降级无意义 |

### 代码修改示意

```python
# === 1. connect_sync() - 连接验证 ===
# 改前:
df = self._api_call_with_retry(self.api.trade_cal, ..., max_retries=60)
# 改后:
df = self._api_call_with_retry(self.api.trade_cal, ..., max_retries=3)

# === 2. _api_call_with_retry() 函数签名 ===
# 改前:
def _api_call_with_retry(self, api_method, *args, max_retries=60, **kwargs):
# 改后:
def _api_call_with_retry(self, api_method, *args, max_retries=5, **kwargs):

# === 3. patched_query() 超时 ===
# 改前:
effective_timeout = 10 if base_url == HTTP_BASE else (api._DataApi__timeout or 45)
# 改后:
effective_timeout = 5  # 统一 5s

# === 4. patched_query() - 跳过 HTTPS 降级 ===
# 改前:
for base_url in (HTTP_BASE, HTTPS_BASE):
# 改后:
for base_url in (HTTP_BASE,):  # 只试 HTTP
```

### 效果预测

| 场景 | 之前 | 之后 | 改善 |
|------|------|------|------|
| Tushare 正常 | ~0.1s (1次 try) | ~0.1s (1次 try) | ⇔ 不变 |
| ALB 坏周期(即时断开) | 61次×2s=122s | 5次×1.2s=6s | **×20** |
| ALB 坏周期(挂10s) | 61次×12s=732s | 5次×6s=30s | **×24** |
| ALB 一直坏(最坏情况) | 61次×25s=1525s | 5次×6s=30s | **×50** |

### 参考来源

1. **Tushare 官方文档** "如何优雅撸数据" (doc_id=131)
   ```python
   for _ in range(3):  # 3 retries
       try: ...
       except: time.sleep(1)
       else: return df
   ```

2. **Fail Fast 设计模式** - 早期失败更快切换到降级路径

3. **AWS SDK / Google API Client 重试策略** - 通常 3-5 次 + 指数退避

### 与现有修复的兼容性

| 现有修复 | 与方案 D 关系 | 备注 |
|----------|-------------|------|
| FIX-6 (智能熔断器) | ✅ 互补 | 重试减少后熔断器触发概率降低 |
| FIX-7 (1s 固定间隔) | ✅ 保留 | 1s sleep 不变 |
| FIX-8 (删 Session) | ✅ 已实施 | 不需要 Session |
| C1-C6 (终止机制) | ✅ 无关 | 独立组件 |

### 文件

- **当前文件路径**: `/mnt/d/AI-Projects/TradingAgents-CN_v1.0.1/tradingagents/dataflows/providers/china/tushare.py`

---

*计划模式生成，待用户确认后执行*
