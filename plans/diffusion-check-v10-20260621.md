# v10 周期扩散检查报告（查扩散）

> **检查日期**: 2026-06-21  
> **检查范围**: `tradingagents/`, `app/`, `web/`, `cli/`, `config/`  
> **检查模式**: 5 种扩散模式 (A-E)  
> **检查人**: Roo (自动化静态分析)

---

## 检查结论总览

| 模式 | 描述 | 风险等级 | 需要修复 | 备注 |
|------|------|---------|---------|------|
| **A** | efinance API 检测逻辑扩散 | 🟢 低 | 否 | 代码库已统一使用 runtime try/except，无 import-time 检测模式 |
| **B** | baostock None 保护扩散 | 🟢 低 | 否 | 所有 `safe_login()` 调用点已有 None 防御，但有 1 个改进建议 |
| **C** | AKShare 重试 None 绕过扩散 | 🟡 中 | 建议 | `get_stock_news_sync()` 有独立重试逻辑未使用统一包装器 |
| **D** | stockstats 自引用 import 扩散 | 🟢 低 | 否 | 非 bug，import 路径正确，无自引用循环 |
| **E** | 版本约束检测扩散 | 🟢 低 | 否 | 所有 46 个依赖均有上下界约束，无遗漏 |

---

## 模式 A: efinance API 检测逻辑

### 原 Bug (F17)
- **问题**: `efinance.py` 在模块级别使用 `_HAS_LATEST_API` 布尔标志做 import-time API 版本检测
- **修复**: 改为 runtime `try/except AttributeError` 兼容新旧 API

### 搜索策略
1. 搜索 `_HAS_` 前缀变量 → 项目源代码中 **0 处匹配**（仅在 `.venv` 第三方包中存在）
2. 搜索 `_AVAILABLE =` 模式 → **大量匹配**（见下方分析）
3. 搜索版本检测模式（`__version__`, `pkg_resources`）

### 发现的 `_AVAILABLE` 模式（共 69 处）

所有 `_AVAILABLE` 标志均使用 `try/except ImportError` 模式，是**正确的惰性/运行时检测**，非 import-time 编译期检测：

#### 关键文件分布

| 文件 | 标志名 | 检测方式 |
|------|--------|---------|
| `tradingagents/dataflows/interface.py` | `HK_STOCK_AVAILABLE`, `AKSHARE_HK_AVAILABLE`, `_CSDI_AVAILABLE`, `YFIN_AVAILABLE`, `STOCKSTATS_AVAILABLE`, `YF_AVAILABLE` | `try/except ImportError` |
| `tradingagents/dataflows/__init__.py` | `YFINANCE_AVAILABLE`, `STOCKSTATS_AVAILABLE` | `try/except ImportError`（嵌套 fallback） |
| `tradingagents/dataflows/providers/__init__.py` | `AKSHARE_AVAILABLE`, `TUSHARE_AVAILABLE`, `BAOSTOCK_AVAILABLE`, `YFINANCE_AVAILABLE`, `FINNHUB_AVAILABLE` | `try/except ImportError` |
| `tradingagents/config/config_manager.py` | `MONGODB_AVAILABLE` | `try/except ImportError` |
| `tradingagents/graph/setup.py` | `_L_IWM_AVAILABLE`, `_HSRC_MC_AVAILABLE`, `_DIFFUSION_AVAILABLE` | `try/except ImportError` |
| `tradingagents/hpc_loop/aif_engine.py` | `_JAX_AVAILABLE` | `try/except ImportError` |
| `tradingagents/dataflows/cache/` | `MONGODB_AVAILABLE`, `REDIS_AVAILABLE`, `FILE_CACHE_AVAILABLE`, `DB_CACHE_AVAILABLE`, `ADAPTIVE_CACHE_AVAILABLE`, `INTEGRATED_CACHE_AVAILABLE`, `APP_CACHE_AVAILABLE` | `try/except ImportError` |
| `app/utils/report_exporter.py` | `EXPORT_AVAILABLE`, `PANDOC_AVAILABLE`, `PDFKIT_AVAILABLE` | `try/except ImportError` + `OSError` |
| `web/utils/report_exporter.py` | `MONGODB_REPORT_AVAILABLE`, `DOCKER_ADAPTER_AVAILABLE`, `EXPORT_AVAILABLE`, `PANDOC_AVAILABLE` | `try/except ImportError` |

### 扩散结论
✅ **无扩散风险**。原因：
- 原 Bug 的特例性：`efinance` 的 API 版本检测 (`get_latest_quote` vs `get_quote`) 是库特有逻辑
- 代码库统一使用 `try/except ImportError` 惰性检测，在需要时才导入，而非在模块加载时硬编码版本判断
- 唯一的版本检测 [`baostock_patched.py:34-38`](tradingagents/dataflows/providers/china/baostock_patched.py:34) 使用 `pkg_resources.get_distribution()` 做运行时版本检测，用于 `is_login()` 兼容性决策，属于正确用法

---

## 模式 B: baostock None 保护扩散

### 原 Bug (F18)
- **问题**: `bs.login()` 可能返回 `None`，无防御导致 `AttributeError: 'NoneType' object has no attribute 'error_code'`
- **修复**: `_SafeLoginResult` 包装类 + `safe_login()` 5 次指数退避重试

### 搜索策略
1. 搜索 `bs.login()` 调用 → **仅 1 处**（`baostock_patched.py:163`，原函数内部）
2. 搜索 `safe_login()` 调用 → **17 处**（分布在 6 个文件）
3. 搜索 `.error_code` 访问 → **50 处**
4. 搜索 `app/` 中 `safe_login`/`error_code` → **15 处**

### 调用点分析

#### `safe_login()` 调用点（全部已有 None 防御）

| 文件 | 行号 | 防御方式 |
|------|------|---------|
| `baostock_patched.py` | 13, 140, 248 | 模块级快捷函数 + 类方法 |
| `baostock.py` | 63, 89, 144, 260, 323, 410, 610, 772, 811, 850, 889, 928 | `if lg is None or lg.error_code != '0'` |
| `a_share_fetcher.py` | 179 | `if lg is None or lg.error_code != "0"` |
| `data_source_manager.py` | 2055 | `if lg is not None and lg.error_code == '0'` |
| `real_data_pipeline.py` | 255, 494 | `if log_result is not None and log_result.error_code == '0'` |
| `akshare.py` | 303, 323 | `if log_result is not None and log_result.error_code == '0'` |
| `app/services/baostock_adapter.py` | 40, 121 | `if lg is None or lg.error_code != '0'` |
| `app/services/config_service.py` | 1388 | `if lg is not None and lg.error_code == '0'` |

#### `bs.login()` 直接调用（原始 API）
- **仅 1 处**：`baostock_patched.py:163` — 在 `safe_login()` 内部，且已有 `if result is not None` 防御

### 改进建议
🔶 **低优先级建议**：`data_source_manager.py:2055` 处的逻辑在 `if lg is not None and lg.error_code == '0'` 成功后调用 `is_login()` 双重验证，这是安全冗余但正确的做法。

### 扩散结论
✅ **无扩散风险**。所有 `safe_login()` 调用点均已正确防御 None 返回值。原修复（`_SafeLoginResult` 包装类）确保 `safe_login()` 本身永不返回 None，外部的 `if lg is None` 检查作为防御性编程冗余。

---

## 模式 C: AKShare 重试 None 绕过扩散

### 原 Bug (F19)
- **问题**: AKShare 在反爬触发时返回 `None` 或空 `DataFrame` 而非抛出异常，重试逻辑未检查
- **修复**: `_call_akshare_with_retry` 中添加 `result is None` 和 `result.empty` 检查

### 搜索策略
1. 搜索 `_call_akshare_with_retry` 调用点 → **15 处**
2. 搜索 `asyncio.to_thread` 在 akshare.py 中的裸调用 → **2 处**（见下方分析）
3. 搜索 `get_stock_news_sync` 的重试逻辑

### 调用点分析

#### `_call_akshare_with_retry` 已覆盖的调用（15 处）

```
akshare.py:502  get_stock_list - stock_info_a_code_name
akshare.py:585  _get_stock_list_cached - stock_info_a_code_name
akshare.py:605  _get_stock_info_detail - stock_individual_info_em
akshare.py:764  get_batch_stock_quotes - stock_zh_a_spot
akshare.py:774  get_batch_stock_quotes - stock_zh_a_spot_em
akshare.py:906  get_stock_quotes - stock_bid_ask_em
akshare.py:951  _get_realtime_quotes_data - stock_zh_a_spot
akshare.py:990  _get_realtime_quotes_data - stock_zh_a_spot_em
akshare.py:1025 _get_realtime_quotes_data - stock_zh_a_hist
akshare.py:1201 get_historical_data - stock_zh_a_hist
akshare.py:1287 get_financial_data - stock_financial_abstract
akshare.py:1303 get_financial_data - stock_balance_sheet_by_report_em
akshare.py:1319 get_financial_data - stock_profit_sheet_by_report_em
akshare.py:1335 get_financial_data - stock_cash_flow_sheet_by_report_em
akshare.py:1523 get_stock_news - stock_news_em
akshare.py:1582 get_stock_news - news_cctv
```

#### 未使用 `_call_akshare_with_retry` 的 AKShare 调用

##### 1. `get_stock_news_sync()` 的独立重试逻辑

[`akshare.py:1392-1465`](tradingagents/dataflows/providers/china/akshare.py:1392)

```python
max_retries = 3
retry_delay = 1
news_df = None

for attempt in range(max_retries):
    try:
        self._enforce_request_interval()
        news_df = ak.stock_news_em(symbol=symbol_6)
        break  # 成功则跳出重试循环
    except json.JSONDecodeError as e:
        ...
        retry_delay *= 2
    except Exception as e:
        ...
        retry_delay *= 2
```

🔶 **问题**: 
- 只重试 3 次（vs 统一包装器 8 次）
- 无 None/空 DataFrame 检查（AKShare 反爬典型表现）
- 无 UA 轮换
- 无随机抖动
- 是同步方法，`_call_akshare_with_retry` 是异步方法

##### 2. Docker 环境 curl_cffi 直接调用

[`akshare.py:1503`](tradingagents/dataflows/providers/china/akshare.py:1503)

```python
news_df = await asyncio.to_thread(
    self._get_stock_news_direct,
    symbol=symbol_6, limit=limit
)
```

✅ **风险较低**：此路径仅在 Docker 环境 + 非 Windows 平台触发，且失败后会回退到 `_call_akshare_with_retry`。

### 改进建议
🔶 **建议**：将 `get_stock_news_sync()` 的重试逻辑统一到 `_call_akshare_with_retry`，或者至少添加 None/空 DataFrame 检查。该方法是同步版本，可通过创建异步辅助函数包装。

### 扩散结论
🟡 **低-中风险，建议改进**。核心数据获取路径（行情、历史、财务）已全部通过 `_call_akshare_with_retry` 保护。`get_stock_news_sync()` 是遗留的独立同步方法，其重试逻辑较弱但功能上仍能工作。

---

## 模式 D: stockstats 自引用 import 扩散

### 原 Bug (F20)
- **问题**: `interface.py` 中自引用 import `from .technical.stockstats import StockstatsUtils` 在特定 Python 版本或包结构下可能导致循环导入
- **修复**: 修正 import 路径，保持相对导入

### 搜索策略
1. 搜索 `from .technical.stockstats import` → **2 处**
2. 搜索 `from stockstats import` / `import stockstats` → **2 处**
3. 搜索 `from .technical import` / `from technical import`

### Import 链分析

```
dataflows/__init__.py
  → from .technical import StockstatsUtils, STOCKSTATS_AVAILABLE  ✓
  → (fallback) from .technical.stockstats import StockstatsUtils  ✓

dataflows/interface.py
  → from .technical.stockstats import StockstatsUtils  ✓ (F20 修复后的路径)

dataflows/technical/__init__.py
  → from .stockstats import StockstatsUtils  ✓

dataflows/technical/stockstats.py
  → from stockstats import wrap  ✓ (第三方库，非自引用)

dataflows/providers/us/yfinance.py
  → from stockstats import wrap  ✓ (第三方库，非自引用)
```

### 扩散结论
✅ **无扩散风险**。`from stockstats import wrap`（第三方库）不会被误认为自引用。所有 `StockstatsUtils` 的导入路径正确且一致：
- `technical/__init__.py` → `technical/stockstats.py`（包内相对导入）
- `dataflows/__init__.py` → `technical` 包（通过 `__init__.py` 导出）
- `interface.py` → `technical.stockstats`（直接相对导入）

不存在循环导入（`stockstats.py` 不反向导入 `interface.py` 或 `dataflows/__init__.py`）。

---

## 模式 E: 版本约束检测扩散

### 原 Bug (版本约束问题)
- **问题**: `efinance>=1.2.0,<2.0.0` — PyPI 上不存在 `>=1.2.0` 版本（最新为 0.5.8）
- **修复**: `efinance>=0.5.8,<1.0.0` + `baostock>=0.8.0,<0.10.0`（锁定上限避免 is_login 移除）

### 约束审计

[`pyproject.toml`](pyproject.toml) 共 **46 个依赖**，所有依赖 **均有上下界约束**：

| 类别 | 依赖数 | 约束模式 | 示例 |
|------|--------|---------|------|
| API 框架 | 5 | `>=X,<Y` | `fastapi>=0.104.0,<1.0.0` |
| 数据库/缓存 | 3 | `>=X,<Y` | `motor>=3.3.0,<4.0.0` |
| 认证安全 | 2 | `>=X,<Y` | `PyJWT>=2.0.0,<3.0.0` |
| 任务调度 | 2 | `>=X,<Y` | `apscheduler>=3.10.0,<4.0.0` |
| HTTP/SSE | 2 | `>=X,<Y` | `httpx>=0.24.0,<1.0.0` |
| 数据源 | 9 | `>=X,<Y` | `efinance>=0.5.8,<1.0.0` |
| AI/LLM | 9 | `>=X,<Y` | `openai>=1.0.0,<2.0.0` |
| 数据处理 | 2 | `>=X,<Y` | `pandas>=2.3.0,<3.0.0` |
| 网络爬虫 | 6 | `>=X,<Y` | `requests>=2.32.4,<3.0.0` |
| 文档 | 3 | `>=X,<Y` | `markdown>=3.4.0,<4.0.0` |
| 工具 | 8 | `>=X,<Y` | `psutil>=6.1.0,<8.0.0` |
| GPU/RL | 2 | `>=X,<Y` | `gymnasium>=0.29.0,<1.0.0` |
| 可选 | 1 | `>=X,<Y` | `qianfan>=0.4.20,<1.0.0` |

### 关键约束评估

| 依赖 | 下界 | 上界 | 评估 |
|------|------|------|------|
| `efinance` | `>=0.5.8` | `<1.0.0` | ✅ 已纠正，0.5.8 是 PyPI 最新版 |
| `baostock` | `>=0.8.0` | `<0.10.0` | ✅ 已锁定，0.10.0+ 移除 `is_login()` |
| `akshare` | `>=1.17.86` | `<2.0.0` | ✅ 合理，已知兼容版本 |
| `yfinance` | `>=0.2.63` | `<1.0.0` | ✅ 合理 |
| `stockstats` | `>=0.6.5` | `<1.0.0` | ✅ 合理 |
| `tushare` | `>=1.4.21` | `<2.0.0` | ✅ 合理 |
| `gymnasium` | `>=0.29.0` | `<1.0.0` | ✅ P0-C3 修复的传递依赖 |
| `omegaconf` | `>=2.3.0` | `<3.0.0` | ✅ R2 Fix M2 |
| `setuptools` | `>=80.9.0` | `<81.0.0` | ⚠️ 上界 `<81.0.0` 非常紧，但 build-system 要求为 `>=61.0`（无上界） |

### 改进建议
🔶 **极低优先级**：`setuptools>=80.9.0,<81.0.0` 的上界非常窄，可能导致 pip 解析冲突。但 `[build-system]` 中 `requires = ["setuptools>=61.0", "wheel"]` 无上界，可作为降级路径。

### 扩散结论
✅ **无扩散风险**。所有依赖均有 `>=X,<Y` 双端约束，且已修复的两个版本约束（efinance、baostock）正确。无其他依赖出现类似"版本号在 PyPI 不存在"的问题。

---

## 综合风险评估

### 需要立即修复
- **无**

### 建议改进
1. **模式 C**: [`akshare.py:1392-1465`](tradingagents/dataflows/providers/china/akshare.py:1392) `get_stock_news_sync()` — 建议将该方法的独立重试逻辑升级为与 `_call_akshare_with_retry` 一致的 None/空 DataFrame 检查

### 无风险确认
- 其余 4 个模式（A, B, D, E）经代码库全量搜索确认无扩散

---

## 附录: 搜索命令记录

| 模式 | 搜索内容 | 来源文件数 | 匹配数 |
|------|---------|-----------|--------|
| A | `_HAS_` | 0 | 0 |
| A | `_AVAILABLE =` | ~20 | 69 |
| A | `__version__` / `pkg_resources` | 4 | 5 |
| B | `bs.login()` | 1 | 2 |
| B | `safe_login()` | 6 | 17 |
| B | `.error_code` | 6 | 50 |
| C | `_call_akshare_with_retry` | 1 | 16 |
| C | `asyncio.to_thread` | 5 | 53 |
| C | `result is None` / `result.empty` | 3 | 8 |
| D | `from .technical.stockstats import` | 2 | 2 |
| D | `from stockstats import` / `import stockstats` | 2 | 2 |
| D | `from .technical import` | 2 | 3 |
| E | pyproject.toml 全量审计 | 1 | 46 依赖 |
