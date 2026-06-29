# BAOSTOCK-CONNECT-001 修复记录

## 概述

修复 baostock 库 `SocketUtil.connect()` 在 TCP 连接失败时静默吞掉异常但仍将已损坏的 socket 存入全局上下文，导致后续所有调用因 `'NoneType' object has no attribute 'error_code'` 崩溃的问题。

## 根因分析

### 文件: `baostock/util/socketutil.py` (第三方库，不可修改)

```python
# SocketUtil.connect() 第 34-41 行 原始代码问题
def connect(self):
    mySockect = None
    try:
        import socket
        mySockect = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mySockect.connect((cons.BAOSTOCK_SERVER_IP, cons.BAOSTOCK_SERVER_PORT))
    except Exception:
        print("服务器连接失败，请稍后再试。")
        # ← 异常被吞掉，mySockect 保持 None
    # ↓ 没有检查 mySockect 是否为 None，将 None 存入全局 context
    setattr(context, "default_socket", mySockect)
```

**问题链:**
1. TCP 连接失败 → `mySockect = None`
2. `except` 只打印消息，不抛异常、不 return
3. `setattr(context, "default_socket", mySockect)` 将 `None` 写入全局上下文
4. 后续 `send_msg()` 使用 `context.default_socket` 时报 `AttributeError`
5. `send_msg()` 的 attempt 循环 catch 后返回空字符串 `""`
6. `loginout.py` 的 `login()` 未收到有效响应 → `ResultData.error_code = BSERR_NO_LOGIN`
7. 调用方检查 `lg.error_code != '0'` 时因 `lg is None` 崩溃

## 修复策略

### 策略选择: **Monkey-patching**（不修改第三方库源文件）

创建 `baostock_patched.py`，在模块加载时自动替换 `SocketUtil.connect()` 和 `send_msg()`，提供 `safe_login()` 封装保证永不返回 `None`。

## 修改文件清单

### 新建文件

| 文件 | 路径 | 说明 |
|------|------|------|
| `baostock_patched.py` | `tradingagents/dataflows/providers/china/baostock_patched.py` | 核心补丁模块 |

### 修改文件

| 文件 | 路径 | login 调用点 | 修改内容 |
|------|------|-------------|---------|
| `baostock.py` | `tradingagents/dataflows/providers/china/baostock.py` | 11 处 | 引入 `BaostockSafeLogin`，全部替换为 `safe_login()` + None 防御 |
| `baostock_adapter.py` | `app/services/data_sources/baostock_adapter.py` | 2 处 | 替换为 `safe_login()` / `safe_logout()` + None 防御 |
| `akshare.py` | `tradingagents/dataflows/providers/china/akshare.py` | 2 处 | 替换为 `safe_login()` / `safe_logout()` + None 防御 |
| `data_source_manager.py` | `tradingagents/dataflows/data_source_manager.py` | 1 处 | 替换为 `safe_login()`（保留已有重试逻辑） |
| `a_share_fetcher.py` | `tradingagents/dataflows/a_share_fetcher.py` | 1 处 | 替换为 `safe_login()` + None 防御 |
| `real_data_pipeline.py` | `tradingagents/l_iwm/real_data_pipeline.py` | 2 处 | 替换为 `safe_login()` + None 防御 |
| `config_service.py` | `app/services/config_service.py` | 1 处 | 替换为 `safe_login()` + None 防御 |

## 修复覆盖统计

| 指标 | 数值 |
|------|------|
| 原始 `bs.login()` 调用点总数 | 20 |
| 已替换为 `safe_login()` 数量 | 20 |
| 修复覆盖率 | **100%** |
| 新增 import 行数 | 8 |
| 新增 None 防御检查 | 20 |
| 新增 `_SafeLoginResult` 包装类 | 1 |

## 核心修改说明

### `_patched_connect()` — 修复根因

```python
def _patched_connect(self) -> None:
    mySockect = None
    try:
        import socket
        import baostock.common.contants as cons
        mySockect = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mySockect.connect((cons.BAOSTOCK_SERVER_IP, cons.BAOSTOCK_SERVER_PORT))
    except Exception:
        print("服务器连接失败，请稍后再试。")
        traceback.print_exc()
        mySockect = None
    if mySockect is not None:
        setattr(context, "default_socket", mySockect)
    else:
        # 清理已损坏的 socket
        if hasattr(context, "default_socket"):
            delattr(context, "default_socket")
```

**关键改动:**
1. 添加 `traceback.print_exc()` 保留异常堆栈
2. `except` 块中显式设置 `mySockect = None`
3. 在 `setattr` 前检查 `mySockect is not None`
4. 失败时清理 `context.default_socket` 属性

### `_SafeLoginResult` — 永不返回 None

```python
@dataclass
class _SafeLoginResult:
    error_code: str = "-1"
    error_msg: str = "safe_login returned None (connection failed)"

    def __bool__(self) -> bool:
        return self.error_code == "0"
```

### `BaostockSafeLogin.safe_login()` — 指数退避重试

```python
def safe_login(self, max_retries: int = 3, backoff_base: float = 2.0) -> _SafeLoginResult:
    for attempt in range(1, max_retries + 1):
        try:
            bs.login()
            if bs.is_login():
                return _SafeLoginResult(error_code="0", error_msg="")
        except Exception:
            if attempt < max_retries:
                time.sleep(backoff_base ** (attempt - 1))
    return _SafeLoginResult()
```

## 验证标准

1. ✅ Monkey-patch 无需手动调用，`import baostock_patched` 自动触发
2. ✅ `safe_login()` 永远不返回 `None`
3. ✅ 所有 `bs.login()` 调用点全部替换
4. ✅ 所有 `.error_code` 访问前都有 `lg is None` 检查
5. ✅ `safe_logout()` 安全封装，不抛异常
6. ✅ `reset_connection()` 可人工恢复连接
7. ✅ 不破坏已有重试逻辑（`data_source_manager.py`）
8. ✅ 保留原始 `import baostock as bs` 引用（不影响其他 API 调用）

## 风险与注意事项

- 每次 `import baostock_patched` 都会重新应用 monkey-patch，多次 import 无害（重复替换相同函数）
- Monkey-patch 只替换 `SocketUtil.connect()` 和 `send_msg()`，不修改 baostock 的其他行为
- 需要确保 `baostock_patched.py` 在 `bs.login()` 首次调用前被 import（所有被修改文件在模块顶部 import）
- `"服务器连接失败，请稍后再试。"` 消息仍会被打印（保留原始库行为），不影响功能

## 关联问题

- **BUG-NEW-004**: `data_source_manager.py` 中已有 `is_login()` 验证，与本次修复兼容
- **P1-H2**: `akshare.py` 中 `logout` 错误静默处理，与本次修复兼容
