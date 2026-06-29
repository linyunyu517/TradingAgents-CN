# FIX-7: 连接错误重试优化

## 3轮深度分析总结

### 第1轮：信息收集
- 阅读 analysis_worker.py → 分析在 ThreadPoolExecutor 中执行
- 阅读 event_loop_pool.py → 使用独立后台线程运行事件循环
- 阅读 tushare_adapter.py → TushareAdapter 懒加载，非启动时创建
- 阅读 data_source_manager.py → `_run_async_in_new_loop` 使用 EventLoopPool
- 阅读 _api_call_with_retry → 含_rate limiter + 三态熔断器 + 指数退避
- 日志分析：17:22 运行的每条失败记录时间戳
- 网上搜索：AKShare 也有完全相同的 RemoteDisconnected 错误

### 第2轮：假设验证
- **H1 (asyncio阻塞被推翻)**: 分析代码使用 `run_in_executor(ThreadPoolExecutor)`，不阻塞事件循环
- **从日志发现真正瓶颈**: 时间戳分析揭示每次重试间隔 7→14→15→19→22 秒，这是指数退避 sleep 造成的
- HTTP 调用本身只花 ~1 秒（ALB 毫秒级断连，urllib3 立即检测到）
- 真正的延迟来源：指数退避 `1.5^attempt`，第 7 次起就达到 15s 上限

### 第3轮：方案比选
| 方案 | 思路 | 效果 | 复杂度 |
|------|------|:----:|:------:|
| **FIX-7 (最优)** | 连接错误用固定间隔 | 61次~2分钟 | 1行 |
| 增加超时 | 10s→20s | 更糟 | 1行 |
| 减少重试次数 | 61→10 | 机会减少 | 1行 |
| 用 curl 代替 requests | 绕过 urllib3 | 大幅改动 | ~30行 |

**结论**: FIX-7 效果最好，改动最小。

---

## 最终修复方案

### 问题
`_api_call_with_retry` 中对连接错误的回退使用指数退避：
```python
sleep_time = min(1.5 ** attempt, 15) + random.uniform(0, 0.5)
```

第 7 次重试起 sleep = 15s，61 次重试共需约 **15 分钟**。

### 根因
Tushare 阿里云 ALB 间歇性断连。每次断连在毫秒级被 urllib3 检测到，但指数退避强行等了 15 秒才发起下一次重试。

### 修复
改为固定短间隔（~1.25s）：
```python
sleep_time = 1.0 + random.uniform(0, 0.5)
```

### 效果
- **修复前**: 61次重试 ≈ **15分钟**
- **修复后**: 61次重试 ≈ **2分钟**
- ALB 恢复后 2 分钟内可被检测到
- API 业务错误的熔断器行为不受影响
- 改动量：**1行代码，1个文件**

### 修改

**文件**: `tradingagents/dataflows/providers/china/tushare.py`
**位置**: `_api_call_with_retry` 方法，连接错误分支（~L267）

```python
# 当前（指数退避，15s上限）：
sleep_time = min(1.5 ** attempt, 15) + random.uniform(0, 0.5)

# 改为（固定~1.25s）：
sleep_time = 1.0 + random.uniform(0, 0.5)
```
