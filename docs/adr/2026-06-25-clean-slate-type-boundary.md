# ADR: Clean Slate — 类型安全边界层 + 系统性异常处理加固

## 状态
已开始执行（Phase 1-4 完成）

## 上下文
经过全代码库 3 轮抽象分析，确认系统存在 5 个根本原因，以 RC1（无类型安全接口契约）和 RC2（防御性异常处理）最为关键。

## 决策
选择 Clean Slate（根治）方案，按以下顺序推进：
1. 创建 `tradingagents/types/` 类型安全层
2. propagate() 三重拷贝合并
3. 修复全部 `except Exception: pass` 为 logger.debug
4. 扩散检查确保无同类模式遗留

## 影响
- ✅ propagate() 从 ~200 行减为 ~60 行
- ✅ 26 处 `except Exception: pass` 全部修复
- ✅ ruff + py_compile 全部通过
- 🔄 剩余阶段待执行（type:ignore 消除、测试基础设施、配置合并）

## 已修复文件清单
- `tradingagents/types/__init__.py` (新建)
- `tradingagents/types/state.py` (新建)
- `tradingagents/graph/trading_graph.py`
- `tradingagents/dataflows/optimized_china_data.py`
- `tradingagents/dataflows/providers/china/baostock_patched.py`
- `tradingagents/dataflows/providers/china/zzshare_provider.py`
- `tradingagents/dataflows/providers/us/optimized.py`
- `app/main.py`
- `app/__main__.py`
- `app/middleware/response_sanitizer.py`
- `app/services/simple_analysis_service.py`
- `app/services/user_service.py`
- `app/services/basics_sync/utils.py`
- `app/services/progress/tracker.py`
- `app/services/data_sources/akshare_adapter.py`
- `app/services/data_sources/tushare_adapter.py`
- `app/utils/report_exporter.py`
- `web/utils/docker_pdf_adapter.py`
- `web/utils/file_session_manager.py`
- `web/utils/smart_session_manager.py`
- `web/utils/report_exporter.py`
- `plans/v1.0.1-root-cause-and-fix-archive.md`
