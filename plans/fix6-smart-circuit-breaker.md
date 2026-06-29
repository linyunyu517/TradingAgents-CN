# FIX-6：智能熔断器（错误分类重试）

## 分析流程

### 第1轮：信息收集 + 抽象
- 确认 TradingAgents-CN 运行在 **Windows Python**（非 WSL2）
- Windows 上的错误是 `RemoteDisconnected`（不是 `FileNotFoundError`）
- 服务器端（阿里云 ALB）间歇性拒绝连接，失败率 ~30-50%
- 免费账户限制：50次/分钟，8000次/天（我们的用量远低于此）
- 在线搜索确认：Tushare 社区报告同类间歇性连接问题（GitHub Issues #1877, #1878, #1685）

### 第2轮：方案比选 + 假设验证
- 方案A（智能重试不触发熔断器）：8.0/10
- 方案B（预连接预热）：6.7/10
- 方案C（双轨并行）：6.0/10
- 方案D（接受现状）：6.0/10
- **胜出：方案A** — 根本解决了"熔断器阻止重试"的矛盾

### 第3轮：深层验证 + 最终方案
- 验证 H-1：不触发熔断器→更多重试→大概率成功 ✅
- 验证 H-2：分流不会掩盖真实服务故障 ✅
- 修正关键词列表以匹配 Windows 实际错误类型

---

## 最终方案（唯一）

**文件**：`tradingagents/dataflows/providers/china/tushare.py`
**改动量**：~10行，`_api_call_with_retry` 方法

### 问题根因

Tushare API 部署在阿里云 ALB（负载均衡器）后面。ALB 间歇性拒绝新 TCP 连接（返回 RST 或直接关闭），导致：
- Windows：`RemoteDisconnected`（远程端关闭连接无响应）
- WSL2：`FileNotFoundError`（内核级套接字创建失败）

**关键矛盾**：当前 `_api_call_with_retry` 将所有异常（连接级和API级）都计入熔断器。连续3次连接错误→熔断器 OPEN 120秒→在此期间最多3次快速重试→放弃。但连接错误是**间歇性的**（可能在几秒内恢复），熔断器反而阻止了恢复后的重试。

### 修复内容

```python
# 在 _api_call_with_retry 中，第248行附近

if attempt < max_retries:
    # [NEW] 判断是否为连接级错误（网络/ALB层，非Tushare服务端错误）
    is_connection_error = any(
        kw in err_str for kw in [
            "RemoteDisconnected",    # Windows: 服务器关闭连接无响应
            "Connection aborted",    # 跨平台: TCP连接被中断
            "FileNotFoundError",     # WSL2: 内核套接字创建失败
            "Connection reset",      # 通用: TCP RST
        ]
    )
    
    if not is_connection_error:
        # 仅对 API 级别错误触发熔断器
        TushareProvider._cb_failure_count += 1
        TushareProvider._cb_last_failure_time = time.time()
        if (
            TushareProvider._cb_failure_count >= TushareProvider._CB_THRESHOLD
            and TushareProvider._cb_state == TushareProvider._CB_CLOSED
        ):
            TushareProvider._cb_state = TushareProvider._CB_OPEN
            self.logger.warning(
                "🔌 熔断器 → OPEN (连续 %d 次失败，冷却 %ds)",
                TushareProvider._cb_failure_count,
                TushareProvider._CB_COOLDOWN,
            )
        elif (
            TushareProvider._cb_state == TushareProvider._CB_HALF_OPEN
        ):
            TushareProvider._cb_state = TushareProvider._CB_OPEN
            TushareProvider._cb_last_failure_time = time.time()
            self.logger.warning(
                "🔌 熔断器 HALF_OPEN 探测失败 → OPEN (冷却 %ds)",
                TushareProvider._CB_COOLDOWN,
            )
    # 连接级错误：不触发熔断器，持续重试
```

### 预期效果

**之前**（3次连接错误后）：
```
🔄 Tushare 连接异常 (第 1 次)
🔄 Tushare 连接异常 (第 2 次)
🔄 Tushare 连接异常 (第 3 次)
🔌 熔断器 → OPEN (120s 冷却)
❌ Tushare API 调用 61 次全部失败
→ 系统降级到 AKShare
```

**之后**（同样3次连接错误）：
```
🔄 Tushare 连接异常 (第 1 次)
🔄 Tushare 连接异常 (第 2 次)
🔄 Tushare 连接异常 (第 3 次)
🔄 Tushare 连接异常 (第 4 次)
🔄 Tushare 连接异常 (第 5 次)
✅ Tushare连接成功  ← 在恢复后立即成功，因为熔断器没有阻止
```

### 与现有修复的关系

| FIX | 状态 | 作用 |
|-----|------|------|
| FIX-1 | ✅ 保持 | .pyc 缓存自动清理 |
| FIX-2 | ✅ 保持 | ts_type_name 旧URL参数移除 |
| FIX-3 | ✅ 保持 | config_service.py 绕过路径修复 |
| FIX-4 | ✅ 保持 | 双熔断器统一 |
| FIX-5 | ✅ 保持 | Session 连接池复用 |
| **FIX-6** | **🆕 新增** | **智能熔断器——连接错误不触发** |
