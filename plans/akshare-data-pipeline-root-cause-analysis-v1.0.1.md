# TradingAgents-CN v1.0.1 — AKShare 数据管道根因分析报告

> **生成时间**: 2026-06-18  
> **项目路径**: `D:\AI-Projects\TradingAgents-CN_v1.0.1`  
> **分析范围**: 数据源架构、AKShare 失败根因、降级链路、修复策略

---

## 目录

1. [完整数据管道架构图（文本）](#1-完整数据管道架构图)
2. [AKShare 失败根因诊断](#2-akshare-失败根因诊断)
3. [降级/回退链路映射](#3-降级回退链路映射)
4. [最优修复策略](#4-最优修复策略)
5. [附录: 关键文件与行号索引](#5-附录关键文件与行号索引)

---

## 1. 完整数据管道架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              TradingAgents-CN 数据管道架构                            │
│                        ┌──────────────────────────────────────┐                      │
│                        │         Agent 层请求入口              │                      │
│                        │  get_china_stock_data_unified()      │                      │
│                        │  get_china_stock_info_unified()      │                      │
│                        │  get_stock_data_by_market()          │                      │
│                        │  get_fundamentals_data()             │                      │
│                        └──────────────┬───────────────────────┘                      │
│                                       │                                              │
│                                       ▼                                              │
│              ┌────────────────────────────────────────────────┐                      │
│              │          interface.py 统一接口层                │                      │
│              │  ┌────────────────────────────────────────┐    │                      │
│              │  │  get_china_stock_data_unified()         │    │                      │
│              │  │  → 调用 DataSourceManager               │    │                      │
│              │  │  → 失败时 _maybe_csdi_impute() 插补     │    │                      │
│              │  └────────────────────────────────────────┘    │                      │
│              │  ┌────────────────────────────────────────┐    │                      │
│              │  │  get_china_stock_info_unified()         │    │                      │
│              │  │  → MongoDB 缓存优先 → DataSourceManager  │    │                      │
│              │  └────────────────────────────────────────┘    │                      │
│              │  ┌────────────────────────────────────────┐    │                      │
│              │  │  get_stock_data_by_market()             │    │                      │
│              │  │  → 自动按市场类型(CN/HK/US)路由          │    │                      │
│              │  └────────────────────────────────────────┘    │                      │
│              └──────────────────────┬─────────────────────────┘                      │
│                                     │                                                │
│                                     ▼                                                │
│    ┌──────────────────────────────────────────────────────────────────────────┐      │
│    │                      DataSourceManager 核心路由器                          │      │
│    │                      data_source_manager.py                               │      │
│    │                                                                            │      │
│    │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │      │
│    │  │ 优先级读取    │   │ 可用性检查   │   │ 智能路由     │   │ 降级引擎     │   │      │
│    │  │ _get_data_   │   │ _check_     │   │ get_stock_   │   │ _try_fallback│   │      │
│    │  │ source_     │──▶│ available_  │──▶│ data()       │──▶│ _sources()   │   │      │
│    │  │ priority_   │   │ sources()   │   │              │   │              │   │      │
│    │  │ order()     │   │             │   │              │   │              │   │      │
│    │  └─────────────┘   └─────────────┘   └──────────────┘   └──────────────┘   │      │
│    │                                                                            │      │
│    │  ╔══════════════════════════════════════════════════════════════════════╗   │      │
│    │  ║           数据源提供器层 (按优先级)                                   ║   │      │
│    │  ║  1. MongoDB 缓存 (_get_mongodb_data)                                ║   │      │
│    │  ║  2. efinance (_get_efinance_data)  ← 当前代码默认                    ║   │      │
│    │  ║  3. AKShare (_get_akshare_data)    ← .env 强制覆盖                  ║   │      │
│    │  ║  4. BaoStock (_get_baostock_data)  ← 30分钟降级窗口                  ║   │      │
│    │  ╚══════════════════════════════════════════════════════════════════════╝   │      │
│    └──────────────────────────────────────────────────────────────────────────┘      │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐       │
│  │  MONGODB 缓存层       │  │  CHINA 数据源         │  │  US 数据源            │       │
│  │  (MongoDB 适配器)     │  │  efinance / AKShare  │  │  yfinance            │       │
│  │  ────────────────    │  │  / BaoStock          │  │  Alpha Vantage       │       │
│  │  ❌ 本地未运行         │  │  / Tushare           │  │  Finnhub             │       │
│  │  WinError 10061      │  │  ────────────────    │  │  ────────────────    │       │
│  │  连接被拒             │  │  AKShare ❌ RemoteDis │  │  yfinance ✅ 基本正常  │       │
│  └──────────────────────┘  │  efinance ⚠️ 新加    │  └──────────────────────┘       │
│                            │  BaoStock ❌ Win失败  │                                │
│                            └──────────────────────┘                                │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                      最终兜底: 模拟/合成数据                                   │   │
│  │  "所有数据源不可用，使用模拟数据，分析结果仅供参考"                                 │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐      │
│  │                      Agent 状态降级链路                                   │      │
│  │                                                                            │      │
│  │  data_source_manager.py                        agent_states.py            │      │
│  │                                              ┌──────────────────┐         │      │
│  │  get_stock_data() 失败 ──────────────────▶  │ data_source_     │         │      │
│  │  设置 failure 标志                          │ failure: bool    │         │      │
│  │  (行 1114-1122)                           │ _bool_or_reducer │         │      │
│  │                                              │ (行 193)          │         │      │
│  │                                              └──────────────────┘         │      │
│  │                                                    │                      │      │
│  │                                                    ▼                      │      │
│  │                                              Bull/Bear Researcher        │      │
│  │                                              Fusion 模式下并发写入         │      │
│  │                                              OR语义合并 (不丢失告警)        │      │
│  └──────────────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 数据源优先级决定流程

```mermaid
flowchart TD
    A[get_stock_data 入口] --> B{current_source 已设置?}
    B -->|否| C[_get_data_source_priority_order]
    B -->|是| D[使用 current_source]
    
    C --> E{MongoDB 可访问?}
    E -->|是| F[从 MongoDB system_configs 读取优先级]
    E -->|否| G[硬编码默认 [EFINANCE, AKSHARE, BAOSTOCK]]
    
    F --> H[返回按市场分类的优先级]
    G --> H
    
    D --> I[调用对应 _get_xxx_data 方法]
    I --> J{成功?}
    J -->|是| K[格式化响应]
    J -->|否| L[_try_fallback_sources]
    L --> M[遍历 fallback_order 剩余源]
    M --> N{任一成功?}
    N -->|是| K
    N -->|否| O[返回空 → 调用者使用模拟数据]
    
    K --> P[保存到 MongoDB 缓存]
```

### 数据处理流程

```
Agent 请求
    │
    ▼
interface.py 统一入口
    │  get_china_stock_data_unified()
    │  get_stock_data_by_market()
    ▼
DataSourceManager 路由
    │
    ├──▶ _get_data_source_priority_order()
    │      → MongoDB config / 硬编码默认值
    │
    ├──▶ current_source 使用 get_stock_data()
    │
    ├──▶ _get_mongodb_data()         [层级 1: 缓存]
    │      → MongoDB 不可用 → 跳过
    │
    ├──▶ _get_efinance_data()        [层级 2: efinance]
    │      → 新增默认源
    │
    ├──▶ _get_akshare_data()         [层级 3: AKShare]
    │      → .env 强制覆盖为此源 → ❌ RemoteDisconnected
    │
    ├──▶ _get_baostock_data()        [层级 4: BaoStock]
    │      → Windows 登录失败 / 降级中 → ❌
    │
    ├──▶ _try_fallback_sources()     [降级引擎]
    │      → 遍历剩余源 → 全部失败
    │
    ▼
AgentState.data_source_failure = True
    │
    ▼
分析师生成 "所有数据源不可用，使用模拟数据"
```

---

## 2. AKShare 失败根因诊断

### 2.1 核心症状

| 症状 | 详情 | 证据 |
|------|------|------|
| **错误类型** | `RemoteDisconnected` — 远程连接被强制断开 | 日志文件数百次重复出现 |
| **影响范围** | 全部 A 股查询, 包括 601636, 600519, 600418, 300047, 000001 等 | 4 个日志文件均确认 |
| **时间跨度** | 持续失败至少 10 天 (2026-06-09 ~ 2026-06-19) | `logs/hpc_out.log`, `logs/backend_launcher.log` |
| **错误频率** | 每次数据请求均失败, 非偶发性 | `backend_launcher.log` 连续 100+ 行同一错误 |
| **BaoStock 状态** | Windows 下 `bs.login()` 失败 → 完全不可用 | `error.log` 含 BaoStock 跳过记录 |
| **MongoDB 状态** | `WinError 10061` 连接被拒 → 缓存层不可用 | `backend_stdout_new.log` |

### 2.2 根本原因链 (5-Why 分析)

```
Why 1: 为什么 AKShare 报 RemoteDisconnected?
    → 东方财富(东财)网站检测到非浏览器 HTTP 请求特征, 主动断开 TCP 连接。
       AKShare 本质是网页爬虫, 不是 API 服务。

Why 2: 为什么 AKShare 无法伪装成浏览器?
    → AKShare 需要 curl_cffi 库提供 TLS 指纹模拟+HTTP/2 支持,
       但 curl_cffi 的 libcurl 在 Windows 上有已知的运行时崩溃问题。

Why 3: 为什么 curl_cffi 在 Windows 上不可用?
    → 代码中明确跳过了 Windows 平台的 curl_cffi 加载。
       akshare.py 第 116-121 行:
       ```python
       if sys.platform == "win32":
           logger.warning("⚠️ 当前为 Windows 平台，curl_cffi 的 libcurl 兼容性已知存在问题，已跳过")
           # 不加载 curl_cffi
       ```

Why 4: 为什么跳过 curl_cffi 后就会失败?
    → 没有 curl_cffi → 使用标准 requests 库 → 无 TLS 指纹模拟
       → 东财反爬虫识别出非浏览器流量 → 发送 RST 包断开连接。
       增强重试(5次退避)也无用, 因为问题不是网络波动, 而是被主动拦截。

Why 5: 为什么 efinance 被新增为默认源后, 系统仍在使用 AKShare?
    → .env 文件第 14 行: `DEFAULT_CHINA_DATA_SOURCE=akshare`
      代码默认已改为 EFINANCE, 但 .env 覆盖优先级更高。
      这是配置残留问题——新增 efinance 提供器后未更新 .env。
```

### 2.3 代码级根因

#### 根因 A: curl_cffi Windows 跳过 (主要)

[`tradingagents/dataflows/providers/china/akshare.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\providers\china\akshare.py)

| 行号 | 代码 | 说明 |
|------|------|------|
| 116-121 | `if sys.platform == "win32": logger.warning(...)` | Windows 显式跳过 `curl_cffi`, 因为 libcurl 兼容性问题 |
| 122-130 | `truststore.inject_openssl()` / 注入 `truststore` SSL context | 尝试用 `truststore` 替代 SSL 验证, 但 TLS 指纹模拟才是根本问题 |
| 132-139 | `else: import curl_cffi; ...` | 非 Windows 正常使用 `curl_cffi` |
| 143 | `self.session = requests.Session()` | 使用标准 `requests.Session`, 无浏览器指纹伪装 |
| 86-97 | 增强重试策略: 5 次退避, `status_forcelist=[429,500,502,503,504]` | 重试对 `RemoteDisconnected` 无效, 因为底层连接已被服务端拒绝 |

#### 根因 B: .env 配置残留

[`.env`](D:\AI-Projects\TradingAgents-CN_v1.0.1\.env) 第 14 行:
```ini
DEFAULT_CHINA_DATA_SOURCE=akshare
```

[`data_source_manager.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\data_source_manager.py) 第 227-245 行:
```python
def _get_default_source(self) -> ChinaDataSource:
    """返回当前代码默认数据源"""
    return ChinaDataSource.EFINANCE  # 代码已改为 efinance
```

但 [`data_source_manager.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\data_source_manager.py) 第 109-192 行 `_get_data_source_priority_order()` 从 MongoDB 读取配置, 而 MongoDB 不可用时使用 `[EFINANCE, AKSHARE, BAOSTOCK]` 未读取 .env。

然而, [`interface.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\interface.py) 第 1518-1631 行的 `get_china_stock_data_unified()` 以及其它入口函数中, 如果 `os.getenv("DEFAULT_CHINA_DATA_SOURCE")` 存在, 会优先使用 .env 值覆盖代码默认。

#### 根因 C: stock_validator 回退链缺失 efinance

[`stock_validator.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\utils\stock_validator.py) 第 919-942 行:
```python
def _get_data_source_priority_for_sync(self, stock_code: str) -> list:
    """返回数据同步时的数据源优先级"""
    return ["tushare", "akshare", "baostock"]  # ❌ 没有 efinance!
```

这意味着数据预取/同步流程中完全不使用 efinance, 即使它是主流程的默认源。

### 2.4 日志证据

| 日志文件 | 关键内容 | 行数/频率 |
|----------|---------|-----------|
| `logs/backend_launcher.log` | `requests.exceptions.ConnectionError: RemoteDisconnected without any response` | 100+ 行连续 |
| `logs/backend_stdout_new.log` | 同上 + MongoDB `WinError 10061` | 50+ 行 |
| `logs/error.log` | `BaoStock ... 跳过` + `所有数据源不可用，使用模拟数据` | 行 4108, 4109 |
| `logs/hpc_out.log` | `RemoteDisconnected` 自 2026-06-09 起持续出现 | 贯穿全文 |

典型错误日志:
```
ERROR    | provider.china.akshare:get_stock_quotes:766 | 股票 600519 行情获取失败
→ requests.exceptions.ConnectionError: RemoteDisconnected without any response
```

---

## 3. 降级/回退链路映射

### 3.1 主数据获取降级链 (`get_stock_data`)

```
层级 1: MongoDB 缓存
    _get_mongodb_data() [data_source_manager.py:1164-1202]
    → 条件: MongoDB 启用且缓存命中且未过期
    → 当前状态: ❌ WinError 10061 连接被拒
    → 动作: 跳过

层级 2: efinance (代码默认源)
    _get_efinance_data() [data_source_manager.py:1336-1372]
    → 条件: efinance 包已安装
    → 当前状态: ⚠️ 新增源, 尚未充分测试
    → 问题: .env 强制使用 AKShare, 此层被完全跳过

层级 3: AKShare (.env 强制覆盖)
    _get_akshare_data() [data_source_manager.py:1298-1333]
    → 条件: akshare 包已安装
    → 当前状态: ❌ RemoteDisconnected (Windows 无 curl_cffi)
    → 动作: 抛出异常 → 进入降级

层级 4: BaoStock
    _get_baostock_data() [data_source_manager.py:1374-1426]
    → 条件: baostock 包已安装 + 未处于降级状态
    → 降级机制: 3 次连续空结果 → degraded=True, 30 分钟窗口后重置
    → 当前状态: ❌ Windows 登录失败或返回 None
    → 动作: 抛出异常

层级 5: 全部失败 → 调用者处理
    _try_fallback_sources() [data_source_manager.py:1453-1501]
    → 遍历 fallback_order 中剩余源
    → 全部失败 → 返回空数据
    → 调用者生成 "所有数据源不可用，使用模拟数据" 警告
```

### 3.2 股票基本信息降级链 (`get_stock_info`)

```
层级 1: MongoDB 缓存
    get_stock_info() 中先查 MongoDB [data_source_manager.py:1503-1611]
    → ❌ MongoDB 不可用

层级 2: efinance
    _get_efinance_stock_info() [data_source_manager.py:1731-1763]
    → ⚠️ 新增源, 但被 .env AKShare 覆盖

层级 3: AKShare (3 级子回退)
    _get_akshare_stock_info() [data_source_manager.py:1765-1909]
    ├── 子回退 1: stock_individual_info_em (行 1791-1826)
    ├── 子回退 2: stock_info_a_code_name (行 1829-1865)
    └── 子回退 3: yfinance (行 1868-1904)
    → ❌ 全部失败 (RemoteDisconnected)

层级 4: BaoStock
    _get_baostock_stock_info() [data_source_manager.py:1911-2043]
    → 包含 3 次登录重试 + 降级检查
    → ❌ Windows 登录失败
```

### 3.3 基本面数据降级链 (`get_fundamentals_data`)

```
层级 1: MongoDB
    _get_mongodb_fundamentals() [data_source_manager.py:2076-2122]
    → ❌ MongoDB 不可用

层级 2: AKShare
    _get_akshare_fundamentals() [data_source_manager.py:2129-2140]
    → ❌ RemoteDisconnected

层级 3: 本地分析生成
    _generate_fundamentals_analysis() [data_source_manager.py:2285-2305]
    → 生成基本的文字分析 (非真实财务数据)

层级 4: Fallback 遍历
    _try_fallback_fundamentals() [data_source_manager.py:2307-2342]
    → 遍历 EFINANCE → AKSHARE → 全部失败
```

### 3.4 新闻数据降级链 (`get_news_data`)

```
层级 1: MongoDB
    _get_mongodb_news() [data_source_manager.py:2344-2367]
    → ❌ MongoDB 不可用

层级 2: AKShare
    _get_akshare_news() [data_source_manager.py:2374-2377] → 存根返回 []
    _get_efinance_news() [data_source_manager.py:2380-2383] → 存根返回 []

层级 3: Fallback
    _try_fallback_news() [data_source_manager.py:2385-2420]
    → 全部返回 [] (暂未实现)
```

### 3.5 股票同步降级链 (`stock_validator.py`)

```
_prepare_china_stock_data() [stock_validator.py:322-482]
    → _check_database_data() [行 608-699] → 检查数据库是否有数据
    → 无数据 → _trigger_data_sync_sync() [行 701-751]
        → _trigger_data_sync_async() [行 753-917]
            → 遍历 _get_data_source_priority_for_sync() 返回的源:
                ["tushare", "akshare", "baostock"]  ← ❌ 没有 efinance
            → 每个源依次尝试获取数据
            → 全部失败 → 返回空
```

### 3.6 Agent 状态降级

```
DataSourceManager.get_stock_data() 失败
    → 设置 data_source_failure = True [data_source_manager.py:1114-1122]
    → 在 AgentState [agent_states.py:193] 中:
        data_source_failure: Annotated[bool, _bool_or_reducer]
    → _bool_or_reducer [agent_states.py:98-107]:
        OR 语义合并, 确保 Fusion 模式下 Bull/Bear 双路分析中
        任一检测到失败都不会丢失告警信号
```

---

## 4. 最优修复策略

### 策略 A: 切换默认数据源为 efinance (最高优先级, 低工作量)

**影响**: ⭐⭐⭐⭐⭐ (完全解决)  
**工作量**: ⭐ (5 分钟)  
**风险**: 低  

**操作**: 修改 `.env` 第 14 行:
```diff
- DEFAULT_CHINA_DATA_SOURCE=akshare
+ # DEFAULT_CHINA_DATA_SOURCE=akshare   ← 注释掉此行
+ # 使用代码默认值: efinance
```

或者更彻底的删除/注释:
```diff
- DEFAULT_CHINA_DATA_SOURCE=akshare
+ # 默认使用 efinance (代码默认), 如需切换请取消注释并修改:
+ # DEFAULT_CHINA_DATA_SOURCE=efinance
```

**理由**: 代码 [`_get_default_source()`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\data_source_manager.py:227-245) 已返回 `ChinaDataSource.EFINANCE` 作为默认值, `.env` 覆盖是唯一阻止它生效的因素。efinance 是零配置、Windows 原生兼容的东财数据源, 不需要 `curl_cffi`。

### 策略 B: stock_validator 同步链加入 efinance (高优先级, 低工作量)

**影响**: ⭐⭐⭐⭐⭐ (补齐同步盲区)  
**工作量**: ⭐ (5 分钟)  
**风险**: 低  

**操作**: 修改 [`stock_validator.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\utils\stock_validator.py:919-942) 第 926-942 行:
```diff
def _get_data_source_priority_for_sync(self, stock_code: str) -> list:
    """返回数据同步时的数据源优先级"""
-    return ["tushare", "akshare", "baostock"]
+    return ["efinance", "tushare", "akshare", "baostock"]
```

**理由**: 主流程默认源已是 efinance, 但同步流程未同步更新, 导致两个路径使用不同的数据源优先级。

### 策略 C: AKShare curl_cffi Windows 兼容性修复 (中优先级, 高工作量)

**影响**: ⭐⭐⭐ (使 AKShare 恢复)  
**工作量**: ⭐⭐⭐⭐ (4-8 小时, 含测试)  
**风险**: 高 (可能引入运行时崩溃)  

**操作步骤**:
1. 调查 `curl_cffi` Windows 兼容性问题版本 (尝试 0.7.x 或 0.9.x)
2. 测试 `curl_cffi` 在 Windows Python 3.11+ 上的稳定性
3. 若可行, 修改 [`akshare.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\providers\china\akshare.py:116-121):
```diff
- if sys.platform == "win32":
-     logger.warning("⚠️ 当前为 Windows 平台，curl_cffi 的 libcurl 兼容性已知存在问题，已跳过")
+ # curl_cffi >= 0.7.0 在 Windows 上已修复 libcurl 兼容性
+ # if sys.platform == "win32":
+ #     logger.warning(...)
```

4. 或在 Windows 上使用 `pip install curl_cffi --upgrade` 后做完整回归测试

**当前 `curl_cffi` 跳过代码** ([`akshare.py:116-121`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\dataflows\providers\china\akshare.py:116-121)):
```python
if sys.platform == "win32":
    logger.warning("⚠️ 当前为 Windows 平台，curl_cffi 的 libcurl 兼容性已知存在问题，已跳过")
    # 不加载 curl_cffi
else:
    try:
        import curl_cffi  # noqa: F401
        logger.info("✅ curl_cffi 可用，AKShare 使用增强模式")
    except ImportError:
        logger.warning("⚠️ curl_cffi 未安装，使用 requests 模式")
```

### 策略 D: 启动 MongoDB 或使用 SQLite 替代缓存 (中优先级, 中工作量)

**影响**: ⭐⭐⭐ (恢复缓存层)  
**工作量**: ⭐⭐⭐ (1-2 小时)  
**风险**: 中  

- 修复 MongoDB 服务启动失败的原因
- 或修改 `_get_mongodb_adapter()` 回退到本地 SQLite 缓存, 避免完全丢失缓存层
- MongoDB 连接失败影响范围: `_check_mongodb_enabled()`, `_get_cached_data()`, `_save_to_cache()`, `_get_data_source_priority_order()`

### 策略 E: 为 AShare 实施纯 requests 版反爬虫方案 (低优先级, 极高工作量)

**影响**: ⭐⭐  
**工作量**: ⭐⭐⭐⭐⭐ (数天)  
**风险**: 极高  

完全不依赖 `curl_cffi`, 用 `requests` + 手动头伪造 + 慢速重试 + 代理轮换。维护成本高, 不推荐。

### 策略优先级总结

| 优先级 | 策略 | 影响 | 工作量 | 推荐 |
|--------|------|------|--------|------|
| **P0** | A: .env 切换为 efinance | 完全解决数据获取失败 | 5 分钟 | ✅ **立即执行** |
| **P0** | B: stock_validator 加入 efinance | 补齐同步链盲区 | 5 分钟 | ✅ **立即执行** |
| **P1** | C: 修复 curl_cffi Windows 兼容性 | 使 AKShare 恢复 | 4-8 小时 | 条件性推荐 |
| **P2** | D: 修复/替代 MongoDB 缓存 | 恢复缓存层 | 1-2 小时 | 建议执行 |
| **P3** | E: 纯 requests 反爬虫方案 | 兜底方案 | 数天 | 不推荐 |

---

## 5. 附录: 关键文件与行号索引

### 5.1 核心配置文件

| 文件 | 行号 | 内容 |
|------|------|------|
| [`.env`](D:\AI-Projects\TradingAgents-CN_v1.0.1\.env:14) | 14 | `DEFAULT_CHINA_DATA_SOURCE=akshare` — 🔴 关键配置残留 |

### 5.2 DataSourceManager (data_source_manager.py)

| 方法 | 行号 | 功能 |
|------|------|------|
| `ChinaDataSource` 枚举 | 26-38 | `MONGODB=1, EFINANCE=2, TUSHARE=3, AKSHARE=4, BAOSTOCK=5` |
| `__init__` | 60-96 | 初始化缓存、默认源、可用源 |
| `_get_default_source` | 227-245 | 返回 `EFINANCE` (代码默认) |
| `_check_available_sources` | 425-525 | 检查各数据源包是否安装 |
| `_get_data_source_priority_order` | 109-192 | 从 MongoDB 读取优先级, 回退 `[EFINANCE, AKSHARE, BAOSTOCK]` |
| `get_stock_data` | 1051-1162 | 统一数据获取 + 降级路由 + failure 标志设置 |
| `_try_fallback_sources` | 1453-1501 | 遍历 fallback_order 进行降级 |
| `_get_mongodb_data` | 1164-1202 | MongoDB 缓存读取 |
| `_get_tushare_data` | 1204-1273 | Tushare 数据获取 |
| `_get_akshare_data` | 1298-1333 | AKShare 数据获取 + 技术指标 |
| `_get_efinance_data` | 1336-1372 | efinance 数据获取 (2026-06-18 新增) |
| `_get_baostock_data` | 1374-1426 | BaoStock + 3 次空数据降级 + 30 分钟窗口 |
| `get_stock_info` | 1503-1611 | 股票基本信息 + MongoDB 缓存优先 |
| `_get_efinance_stock_info` | 1731-1763 | efinance 股票信息 |
| `_get_akshare_stock_info` | 1765-1909 | AKShare 股票信息 (3 级子回退) |
| `_get_baostock_stock_info` | 1911-2043 | BaoStock 股票信息 (3 次登录重试) |
| `get_fundamentals_data` | 272-337 | 基本面数据路由 |
| `_try_fallback_fundamentals` | 2307-2342 | 基本面降级: EFINANCE→AKSHARE→生成分析 |
| `get_news_data` | 352-423 | 新闻数据路由 |
| `_try_fallback_news` | 2385-2420 | 新闻降级: 全部返回 [] |
| `_run_async_in_new_loop` | 1275-1296 | 在已有事件循环中安全运行异步协程 |

### 5.3 AKShare Provider (akshare.py)

| 方法 | 行号 | 功能 |
|------|------|------|
| `_suppress_tqdm` | 24-41 | BUG-NEW-007: 抑制 AKShare tqdm 进度条 (GC 压力修复) |
| `_create_http_session` | 67-97 | 创建 requests.Session + 增强重试策略 |
| `_initialize_akshare` | 99-193 | 🔴 **Windows 跳过 curl_cffi (行 116-121)** + truststore 注入 (行 122-130) |
| `_get_stock_news_direct` | 195-297 | 直接调用东财 API (curl_cffi 版, Windows 跳过行 208-210) |
| `get_stock_quotes` | 736-796 | 3 级回退: `stock_bid_ask_em` → `stock_zh_a_spot` → `stock_zh_a_hist` |
| `get_batch_stock_quotes` | 587-734 | 批量行情: sina → eastmoney 回退, 含重试 |
| `get_historical_data` | 1015-1077 | 历史数据 `stock_zh_a_hist` + qfq 前复权 |
| `get_financial_data` | 1120-1195 | 财务数据: 利润表→资产负债表→现金流量表→... |
| `get_stock_news` | 1303-1480 | 新闻: Docker curl_cffi 路径 + 标准路径 + 重试 |

### 5.4 efinance Provider (efinance.py)

| 方法 | 行号 | 功能 |
|------|------|------|
| `EfinanceProvider.__init__` | 33-37 | 初始化 |
| `_init_efinance` | 39-51 | 导入 efinance |
| `test_connection` | 57-77 | 连接测试 |
| `get_historical_data` | 79-164 | 历史行情 + 列名标准化 |
| `get_stock_basic_info` | 166-219 | 股票基本信息 |
| `get_realtime_quotes` | 221-261 | 批量实时行情 |

### 5.5 BaoStock Provider (baostock.py)

| 方法 | 行号 | 功能 |
|------|------|------|
| `_init_baostock` | 27-39 | 导入 baostock (无登录) |
| `test_connection` | 45-67 | 登录/登出测试 🔴 Windows 可能失败 |
| `get_historical_data` | 558-657 | 历史 K 线数据 |
| `get_financial_data` | 659-741 | 财务数据 (5 个子维度) |
| `get_valuation_data` | 217-298 | 估值数据 (PE/PB/PS/PCF) |
| `_to_baostock_code` | 444-455 | 代码格式转换 (sz/sh 前缀处理) |

### 5.6 Agent 状态与降级

| 文件 | 行号 | 内容 |
|------|------|------|
| [`agent_states.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\utils\agent_states.py:193) | 193 | `data_source_failure: Annotated[bool, _bool_or_reducer]` |
| [`agent_states.py`](D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\agents\utils\agent_states.py:98-107) | 98-107 | `_bool_or_reducer`: OR 语义合并并发写入 |

### 5.7 Stock Validator 数据同步

| 方法 | 行号 | 功能 |
|------|------|------|
| `_prepare_china_stock_data` | 322-482 | A 股数据预获取 |
| `_trigger_data_sync_async` | 753-917 | 异步数据同步 🔴 遍历 `[tushare, akshare, baostock]` |
| `_get_data_source_priority_for_sync` | 919-942 | 🔴 **返回 `["tushare", "akshare", "baostock"]` — 缺少 efinance** |

### 5.8 Interface 统一入口

| 方法 | 行号 | 功能 |
|------|------|------|
| `get_china_stock_data_unified` | 1518-1631 | A 股数据统一入口 |
| `get_china_stock_info_unified` | 1634-1683 | A 股信息统一入口 |
| `switch_china_data_source` | 1686-1722 | 运行时切换数据源 |
| `get_hk_stock_data_unified` | 1752-1848 | 港股数据 |
| `get_stock_data_by_market` | 2017-2056 | 按市场自动路由 |
| `_maybe_csdi_impute` | 1917-2014 | CSDI 扩散插补 NaN |

---

## 总结

**当前系统正处于"全面数据源失效"状态**。AKShare 因缺少 `curl_cffi` 而无法通过反爬虫检测, BaoStock 在 Windows 上登录失败, MongoDB 缓存层未运行。唯一可能工作的 efinance 被 `.env` 配置覆盖而未被使用。

**最快修复方案 (P0)**: 两处改动, 共约 10 分钟:
1. 注释 `.env` 第 14 行的 `DEFAULT_CHINA_DATA_SOURCE=akshare`
2. `stock_validator.py` 第 926 行的 `_get_data_source_priority_for_sync()` 返回值加上 `"efinance"`

**短期建议 (P1)**: 如果仍需要 AKShare 作为备用, 调查并升级 `curl_cffi` 到 Windows 兼容版本 (≥0.7.0)。

**中期建议 (P2)**: 修复 MongoDB 或实现本地 SQLite 缓存替代, 防止重复获取历史数据, 降低对实时数据源的依赖。
