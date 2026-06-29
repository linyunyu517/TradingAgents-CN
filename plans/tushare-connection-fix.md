# Tushare 连接修复方案（第3轮最终版）

## 分析流程

### 第1轮：信息收集
- 阅读 Tushare 完整代码（tushare.py 621行，data_source_manager.py 相关段）
- 搜索 Tushare 官方文档：API 根地址 = `http://api.tushare.pro`（纯 HTTP），旧域名 `api.waditu.com` 已废弃
- 搜索 FileNotFoundError 标准根因：6个可能原因（SSLKEYLOGFILE、DNS、临时证书文件、Unix socket、连接池耗尽、ca_certs）

### 第2轮：实验验证 + 交叉确认
- **URL 路径验证**：`http://api.tushare.pro/dataapi` 和 `http://api.tushare.pro` 均返回 HTTP 200，/dataapi 路径有效
- **SDK 版本检查**：已安装 v1.4.29 代码硬编码 `__http_url = 'http://api.waditu.com/dataapi'`（旧域名）
- **手动复现**：`_patch_tushare_api` + `_api_call_with_retry` + `trade_cal` ⇒ 成功（10行，0.53s）
- **环境检查**：无 SSLKEYLOGFILE、无代理、无 Docker socket、certifi 正常、DNS 解析正常
- **绕过路径**：config_service.py 创建未补丁 `ts.pro_api()`，tushare_adapter.py 绕过 `_api_call_with_retry()`
- **排除假说**：URL 路径错误、代理问题、DNS 问题、SSL 证书问题均已排除

### 第3轮：最终根因锁定
- **最可能根因**：Python `.pyc` 字节码缓存使用旧代码（`.py` 和 `.pyc` 同为 14:52，WSL2 的 NTFS 挂载秒级精度可能让 Python 判断时间戳未变化）
- **证据**：手动测试（新鲜 import）成功，分析运行（`TradingAgentsGraph` 先加载再导入 tushare）失败
- **方案比选**：4方案评估，融合为最优方案

---

## 融合方案（最终版）

| Fix | 文件 | 行 | 描述 |
|-----|------|-----|------|
| **FIX-1** | `tradingagents/dataflows/providers/china/tushare.py` | 新增~8行 | 模块加载时强制清理自身 `.pyc` 字节码缓存 |
| **FIX-2** | `tradingagents/dataflows/providers/china/tushare.py` | L49 | 移除 `ts_type_name` 中的旧 SDK URL |
| **FIX-3** | `app/services/config_service.py` | L1294-1299 | 替换直接 `ts.pro_api()` 为使用 `get_tushare_provider()` |
| **FIX-4** | `tradingagents/dataflows/data_source_manager.py` | L1159-1166 | 移除重复的实例级 Tushare 熔断器 |

**总改动量**：~25 行，3 个文件

---

## FIX-1：强制清理 .pyc 缓存（最关键）

### 问题
Tushare SDK 的 `DataApi.__http_url` 默认写死 `http://api.waditu.com/dataapi`（旧域名，已废弃）。
我们的 `_patch_tushare_api()` 中 `HTTP_BASE` 已经改为 `http://api.tushare.pro/dataapi`（正确）。
但在分析运行时，Python 可能从缓存的 `.pyc` 字节码加载了**修改前**的代码，导致仍使用旧域名。

### 修复

**文件**：`tradingagents/dataflows/providers/china/tushare.py`

在模块导入后、TushareProvider 类定义前，添加缓存清理：

```python
# 在文件头部 import 之后添加：
import importlib
import pathlib

# 强制清理自身 __pycache__ 确保使用最新代码
# WSL2 NTFS 挂载时间戳精度为秒级，.py 和 .pyc 可能同秒，导致 Python 使用旧缓存
_module_dir = pathlib.Path(__file__).parent
_cache_dir = _module_dir / "__pycache__"
if _cache_dir.exists():
    for _pyc in _cache_dir.glob("tushare*.pyc"):
        _pyc.unlink(missing_ok=True)
    importlib.invalidate_caches()
```

---

## FIX-2：移除 `ts_type_name` 旧 URL 参数

### 问题
`_patch_tushare_api` 中 `patched_query` 的第 49 行：

```python
kwargs.setdefault("ts_type_name", api._DataApi__http_url)
```

将 SDK 写死的旧域名 `http://api.waditu.com/dataapi` 作为请求参数传给 Tushare 服务器。

### 修复

将第 49 行改为不传此参数：

```python
# 旧（有风险）：
kwargs.setdefault("ts_type_name", api._DataApi__http_url)

# 新（安全）：
# ts_type_name 参数对 API 结果无影响，移除对旧 URL 的依赖
```

删除此行。`ts_type_name` 是 Tushare 服务端的可选元数据字段，不影响 API 实际查询结果。

---

## FIX-3：修复 config_service.py 绕过路径

### 问题
`app/services/config_service.py` L1294-1299 创建未补丁的 `ts.pro_api()` 做连接测试，
若此路径失败会误导用户以为 Tushare 不可用（用户看到的诊断结果与实际分析路径不同）。

### 修复

替换为使用统一的 provider：

```python
# 旧代码 (L1294-1299)：
import tushare as ts
ts.set_token(api_key)
pro = ts.pro_api()
df = pro.trade_cal(exchange="SSE", start_date="20240101", end_date="20240101")

# 新代码：
from tradingagents.dataflows.providers.china.tushare import test_tushare_connection
result = test_tushare_connection(token=api_key)  # 已包含 monkey-patch + 重试
```

---

## FIX-4：移除 data_source_manager 重复熔断器

### 问题
`data_source_manager.py` L1159-1166 有独立的 `_tushare_error_count` 计数器，与 `tushare.py` 的类级别三态熔断器形成**双重计数**——同一错误被计两次，导致 data_source_manager 的熔断器先于 tushare.py 的熔断器触发，造成混淆。

### 修复

删除 L1159-1166 的实例级熔断器检查，完全依赖 `tushare.py` 的类级别熔断器。

---

## 验证方法

1. 删除 `__pycache__/tushare*.pyc`（FIX-1 自动完成）
2. 运行分析，检查 error.log 中 Tushare 日志：
   - ✅ 期望：`✅ Tushare连接成功` + 无 FileNotFoundError
   - ❌ 失败：仍出现 `FileNotFoundError(2, 'No such file or directory')`
3. 手动验证：`python3 -c "from tradingagents.dataflows.providers.china.tushare import test_tushare_connection; print(test_tushare_connection(token='xxx'))"`

---

## 预期效果

- FileNotFoundError 完全消失
- Tushare 在分析运行时成为主数据源（不再降级到 AKShare）
- config_service 中的"测试连接"功能与主分析路径使用相同代码
- 熔断器逻辑统一，不再有双重计数
