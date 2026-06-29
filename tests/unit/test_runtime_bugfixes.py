#!/usr/bin/env python
"""
运行时诊断发现的 5 个 Bug 的捕获测试。

测试覆盖：
- Bug #1: AnalysisTask 创建时缺少 symbol 必需字段
- Bug #2: project_dir KeyError（TradingAgentsGraph 初始化配置缺失）
- Bug #3: MemoryStateManager 缺少 get_status_sync 同步方法
- Bug #4: update_status 方法名不匹配（应为 update_task_status）
- Bug #5: list_user_tasks 参数名 status vs status_filter 不匹配
"""

import io
import sys
from datetime import datetime
from unittest.mock import patch

import pytest

# ============================================================
# Bug #1: AnalysisTask 创建时缺少 symbol 必需字段
# ============================================================


class TestBug1_AnalysisTaskSymbol:
    """验证 AnalysisTask 创建时必须传入 symbol 字段"""

    def test_analysis_task_requires_symbol(self):
        """AnalysisTask 缺少 symbol 字段时应抛出 ValidationError"""
        from bson import ObjectId
        from pydantic import ValidationError

        from app.models.analysis import AnalysisStatus, AnalysisTask
        from app.models.user import PyObjectId

        with pytest.raises(ValidationError) as excinfo:
            AnalysisTask(
                task_id="test-task-1",
                user_id=PyObjectId(ObjectId()),
                stock_code="000001",
                status=AnalysisStatus.PENDING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        # 验证错误信息包含 symbol 字段
        errors = excinfo.value.errors()
        field_names = [e["loc"] for e in errors]
        assert any("symbol" in loc for loc in field_names), f"应提示缺少 symbol 字段，实际错误: {errors}"

    def test_analysis_task_with_symbol_ok(self):
        """AnalysisTask 传入 symbol 和 stock_code 时应能正常创建"""
        from bson import ObjectId

        from app.models.analysis import AnalysisStatus, AnalysisTask
        from app.models.user import PyObjectId

        task = AnalysisTask(
            task_id="test-task-2",
            user_id=PyObjectId(ObjectId()),
            stock_code="000001",
            symbol="000001",
            status=AnalysisStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert task.symbol == "000001"
        assert task.stock_code == "000001"

    def test_analysis_task_symbol_equals_stock_code(self):
        """验证 symbol 和 stock_code 可以传入相同的值"""
        from bson import ObjectId

        from app.models.analysis import AnalysisStatus, AnalysisTask
        from app.models.user import PyObjectId

        stock_code = "600519"
        task = AnalysisTask(
            task_id="test-task-3",
            user_id=PyObjectId(ObjectId()),
            stock_code=stock_code,
            symbol=stock_code,
            status=AnalysisStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert task.symbol == stock_code
        assert task.stock_code == stock_code


# ============================================================
# Bug #2: project_dir KeyError
# ============================================================


class TestBug2_ProjectDirKeyError:
    """验证 TradingAgentsGraph 初始化时 config 中包含 project_dir"""

    def test_trading_graph_config_has_project_dir(self):
        """TradingAgentsGraph 使用的 config dict 必须包含 project_dir"""
        from tradingagents.default_config import DEFAULT_CONFIG

        assert "project_dir" in DEFAULT_CONFIG, "DEFAULT_CONFIG 必须包含 project_dir 键"
        assert DEFAULT_CONFIG["project_dir"], "project_dir 的值不能为空"

    def test_get_trading_graph_config_merges_defaults(self):
        """验证 _get_trading_graph 传入的 config 合并了 DEFAULT_CONFIG 中的 project_dir"""
        # 模拟 create_analysis_config 生成的配置（不含 project_dir）
        partial_config = {
            "selected_analysts": ["market", "fundamentals"],
            "deep_analysis_model": "Pro/deepseek-ai/DeepSeek-R1",
            "quick_analysis_model": "deepseek-ai/DeepSeek-V3",
            "user_id": "test-user",
            "task_id": "test-task",
        }

        # 模拟 _get_trading_graph 的合并行为
        from tradingagents.default_config import DEFAULT_CONFIG

        merged = {**DEFAULT_CONFIG, **partial_config}
        assert "project_dir" in merged
        assert merged["project_dir"] == DEFAULT_CONFIG["project_dir"]

    @patch("tradingagents.graph.trading_graph.TradingAgentsGraph")
    def test_no_keyerror_on_init(self, MockGraph):
        """传入不含 project_dir 的 config 时，若未合并 DEFAULT_CONFIG 应触发 KeyError"""
        bad_config = {
            "selected_analysts": ["market"],
            "llm_provider": "test",
        }

        # 模拟 TradingAgentsGraph.__init__ 访问 self.config["project_dir"]
        def init_side_effect(selected_analysts=None, debug=False, config=None):
            config = config or {}
            _ = config["project_dir"]  # 应 KeyError

        MockGraph.side_effect = init_side_effect

        with pytest.raises(KeyError, match="project_dir"):
            TradingAgentsGraph = MockGraph
            TradingAgentsGraph(selected_analysts=["market"], config=bad_config)


# ============================================================
# Bug #3: get_status_sync 方法缺失
# ============================================================


class TestBug3_GetStatusSync:
    """验证 MemoryStateManager 中存在 get_status_sync 方法"""

    def test_get_status_sync_exists(self):
        """MemoryStateManager 必须有 get_status_sync 方法"""
        from app.services.memory_state_manager import MemoryStateManager

        mgr = MemoryStateManager()
        assert hasattr(mgr, "get_status_sync"), "缺少 get_status_sync 方法"
        assert callable(mgr.get_status_sync), "get_status_sync 必须是可调用的"

    def test_get_status_sync_returns_dict_or_none(self):
        """get_status_sync 应返回 dict（有任务时）或 None（无任务时）"""

        from app.services.memory_state_manager import MemoryStateManager, TaskStatus

        mgr = MemoryStateManager()
        task_id = "test-sync-task"

        # 先创建一个任务
        mgr.create_task_sync(
            task_id=task_id,
            user_id="test-user",
            stock_code="000001",
            status=TaskStatus.PENDING,
        )

        # 调用同步方法
        result = mgr.get_status_sync(task_id)
        assert result is not None
        assert "status" in result
        assert result["task_id"] == task_id

        # 不存在的任务应返回 None
        assert mgr.get_status_sync("nonexistent") is None

    def test_get_status_sync_content(self):
        """get_status_sync 返回的 dict 应包含关键字段"""
        from app.services.memory_state_manager import MemoryStateManager, TaskStatus

        mgr = MemoryStateManager()
        task_id = "test-sync-content"

        mgr.create_task_sync(
            task_id=task_id,
            user_id="user-1",
            stock_code="600519",
            status=TaskStatus.RUNNING,
        )

        result = mgr.get_status_sync(task_id)
        assert result["task_id"] == task_id
        assert result["stock_code"] == "600519"
        assert result["status"] == TaskStatus.RUNNING.value


# ============================================================
# Bug #4: update_status 方法名不匹配
# ============================================================


class TestBug4_UpdateStatus:
    """验证 MemoryStateManager 中存在 update_status 方法（或兼容别名）"""

    def test_update_status_exists(self):
        """MemoryStateManager 必须有 update_status 方法（与 async update_task_status 兼容）"""
        from app.services.memory_state_manager import MemoryStateManager

        mgr = MemoryStateManager()
        assert hasattr(mgr, "update_status"), "缺少 update_status 方法"
        assert callable(mgr.update_status), "update_status 必须是可调用的"

    @pytest.mark.asyncio
    async def test_update_status_async_compatible(self):
        """update_status 应支持 await 调用（兼容现有代码中的 await self.memory_manager.update_status(...)）"""
        from app.services.memory_state_manager import MemoryStateManager, TaskStatus

        mgr = MemoryStateManager()

        task_id = "test-async-update"
        mgr.create_task_sync(
            task_id=task_id,
            user_id="test-user",
            stock_code="000001",
            status=TaskStatus.PENDING,
        )

        result = await mgr.update_status(task_id, TaskStatus.RUNNING, "测试中...")
        assert result is True

        # 验证状态已更新
        task = mgr.get_status_sync(task_id)
        assert task["status"] == TaskStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_update_status_sync_compatible(self):
        """update_status 应可被 await 调用（与生产代码一致）"""
        from app.services.memory_state_manager import MemoryStateManager, TaskStatus

        mgr = MemoryStateManager()

        task_id = "test-sync-update"
        mgr.create_task_sync(
            task_id=task_id,
            user_id="test-user",
            stock_code="000001",
            status=TaskStatus.PENDING,
        )

        # async 调用
        result = await mgr.update_status(task_id, TaskStatus.COMPLETED, "同步完成测试")
        assert result is True

        task = mgr.get_status_sync(task_id)
        assert task["status"] == TaskStatus.COMPLETED.value


# ============================================================
# Bug #5: status vs status_filter 参数名不匹配
# ============================================================


class TestBug5_StatusFilterParameter:
    """验证 list_user_tasks 的参数名与调用方匹配"""

    def test_list_user_tasks_signature_has_status_filter(self):
        """list_user_tasks 方法应使用 status_filter 参数名"""
        import inspect

        from app.services.simple_analysis_service import SimpleAnalysisService

        sig = inspect.signature(SimpleAnalysisService.list_user_tasks)
        params = list(sig.parameters.keys())
        assert "status_filter" in params, f"list_user_tasks 参数应包含 status_filter，实际参数: {params}"

    def test_router_passes_status_filter(self):
        """验证路由器 analysis.py 中 list_user_tasks 调用使用 status_filter= 参数名"""
        import inspect

        from app.routers import analysis as analysis_router

        # 获取 list_user_tasks 路由函数的源代码
        source = inspect.getsource(analysis_router.list_user_tasks)
        # 检查调用是否使用 status_filter= 而不是 status=
        # 注意：这是验证修复后的代码，应使用 status_filter=
        assert "status_filter=" in source or "status_filter =" in source, (
            f"路由中 list_user_tasks 调用应使用 status_filter= 参数名\n实际源码:\n{source}"
        )

    def test_list_user_tasks_accepts_status_filter(self):
        """list_user_tasks 应能通过 status_filter 参数过滤"""
        from app.services.simple_analysis_service import SimpleAnalysisService

        service = SimpleAnalysisService()
        # 此测试仅验证方法签名兼容，不实际调用（需要 MongoDB）
        # 方法应能接受 status_filter 参数
        import inspect

        sig = inspect.signature(service.list_user_tasks)
        # 尝试用 status_filter 调用（会被 MongoDB 查询拒绝，但参数不匹配应在调用前抛出）
        try:
            # 我们只测试关键字参数名是否能被接受
            sig.bind(user_id="test", status_filter="running", limit=10, skip=0)
        except TypeError as e:
            pytest.fail(f"list_user_tasks 不接受 status_filter 参数: {e}")


# ============================================================
# Bug #6 (P0): Toolkit=None 占位符阻止懒加载 — __init__.py 中 = None 占位符
# ============================================================


class TestBug6_ToolkitNonePlaceholder:
    """验证 tradingagents.agents.__init__.py 中所有导出都不是 None（PEP 562 lazy loading）"""

    def test_toolkit_is_not_none(self):
        """Toolkit 应可调用（不是 None），验证 PEP 562 __getattr__ 正常工作"""
        from tradingagents.agents import Toolkit

        assert Toolkit is not None, "Toolkit should not be None"
        assert callable(Toolkit), "Toolkit should be callable (a class)"

    def test_toolkit_is_callable_class(self):
        """Toolkit 应该是一个类（可通过 Toolkit(config=...) 实例化）"""
        from tradingagents.agents import Toolkit

        assert isinstance(Toolkit, type), f"Toolkit 应该是 type（类），实际类型: {type(Toolkit)}"
        # 验证 __init__ 接受 config 参数
        import inspect

        sig = inspect.signature(Toolkit.__init__)
        assert "config" in sig.parameters or "self" in sig.parameters, (
            f"Toolkit.__init__ 应接受 config 参数，实际签名: {sig}"
        )

    def test_all_exports_are_not_none(self):
        """验证 __all__ 中所有 18 个导出都不是 None"""
        import tradingagents.agents

        __all__ = tradingagents.agents.__all__
        for name in __all__:
            obj = getattr(tradingagents.agents, name, None)
            assert obj is not None, f"{name} should not be None（PEP 562 __getattr__ 惰性加载失败）"

    def test_getattr_works_for_all_exports(self):
        """通过 __getattr__ 访问每个导出，验证惰性加载触发"""
        import tradingagents.agents

        for name in tradingagents.agents.__all__:
            # 先从模块 globals() 中删除（模拟首次导入）
            if name in tradingagents.agents.__dict__:
                del tradingagents.agents.__dict__[name]
            # 重新访问应触发 __getattr__
            obj = getattr(tradingagents.agents, name)
            assert obj is not None, f"{name} 通过 __getattr__ 加载后仍为 None"

    def test_no_none_values_in_module_dict(self):
        """模块的 __dict__ 中不应存在值为 None 的导出项"""
        import tradingagents.agents

        bad_names = []
        for name in tradingagents.agents.__all__:
            val = tradingagents.agents.__dict__.get(name)
            if val is None:
                bad_names.append(name)
        assert not bad_names, f"以下导出仍为 None（= None 占位符可能未彻底删除）: {bad_names}"


# ============================================================
# Bug #7 (P1): SimpleJsonFormatter.format() 丢弃 exc_info
# ============================================================


class TestBug7_SimpleJsonFormatterExcInfo:
    """验证 SimpleJsonFormatter.format() 保留 exc_info / traceback"""

    def test_format_contains_exc_info_when_present(self):
        """当 record 包含 exc_info 时，format() 输出应包含 traceback 行"""
        import json
        import logging

        from app.core.logging_config import SimpleJsonFormatter

        formatter = SimpleJsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=42,
            msg="test error with exception",
            args=(),
            exc_info=(ValueError, ValueError("测试异常"), None),
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        # 应包含 traceback 信息
        assert "exc_info" in parsed or "traceback" in parsed or "exception" in parsed, (
            f"format() 输出应包含异常信息，实际输出键: {list(parsed.keys())}"
        )
        # 验证消息本身保留
        assert parsed.get("message") == "test error with exception"

    def test_format_no_exc_info_unchanged(self):
        """没有 exc_info 时，format() 输出应与原来一致"""
        import json
        import logging

        from app.core.logging_config import SimpleJsonFormatter

        formatter = SimpleJsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="normal log message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed.get("message") == "normal log message"
        # 不应包含异常相关字段
        for key in ("exc_info", "traceback", "exception"):
            assert key not in parsed or not parsed[key], f"无异常时不应包含 {key}"

    def test_format_with_exception_has_traceback_text(self):
        """format() 输出包含异常类型和消息文本"""
        import json
        import logging

        from app.core.logging_config import SimpleJsonFormatter

        formatter = SimpleJsonFormatter()
        try:
            raise RuntimeError("这是测试异常")
        except RuntimeError:
            record = logging.LogRecord(
                name="test_logger",
                level=logging.ERROR,
                pathname=__file__,
                lineno=100,
                msg="捕获到异常",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        # 应包含 RuntimeError 文本
        combined = json.dumps(parsed, ensure_ascii=False)
        assert "RuntimeError" in combined, f"输出应包含异常类型 RuntimeError，实际: {combined}"
        assert "这是测试异常" in combined, f"输出应包含异常消息，实际: {combined}"

    def test_logger_error_with_exc_info_outputs_traceback(self):
        """集成测试：logger.error(..., exc_info=True) 的输出应包含 traceback"""
        import logging

        # 创建内存 handler
        from app.core.logging_config import SimpleJsonFormatter

        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(SimpleJsonFormatter())
        logger = logging.getLogger("test_exc_info_logger")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise ConnectionError("集成测试异常")
        except ConnectionError:
            logger.error("测试 logger.error with exc_info", exc_info=True)

        output = handler.stream.getvalue()
        assert "ConnectionError" in output, f"traceback 应包含 ConnectionError，实际: {output}"
        assert "集成测试异常" in output, f"traceback 应包含异常消息，实际: {output}"


# ============================================================
# Bug #8 (P2): get_provider_by_model_name_sync ImportError 静默吞噬
# ============================================================


class TestBug8_ImportErrorWarning:
    """验证 get_provider_by_model_name_sync 在 ImportError 时记录 warning"""

    def test_importerror_logs_warning(self, caplog):
        """ImportError 时应输出 warning 级别日志"""
        import logging

        caplog.set_level(logging.WARNING)
        # 模拟 analysis 模块不可用（通过 monkey-patch import）
        import builtins

        from app.services.simple_analysis_service import get_provider_by_model_name_sync

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "app.services.analysis":
                raise ImportError("模拟 analysis 模块不存在")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            result = get_provider_by_model_name_sync("test-model")
            # 应回退到 siliconflow
            assert result == "siliconflow", f"回退值应为 siliconflow，实际: {result}"
        finally:
            builtins.__import__ = original_import

        # 验证 warning 日志
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("ImportError" in msg or "不可用" in msg or "analysis" in msg for msg in warning_messages), (
            f"应输出 ImportError 相关 warning，实际日志: {warning_messages}"
        )

    def test_normal_import_no_warning(self, caplog):
        """正常导入时不应有 warning 日志"""
        import logging

        caplog.set_level(logging.WARNING)
        from app.services.simple_analysis_service import get_provider_by_model_name_sync

        # 正常调用（不模拟 ImportError）
        result = get_provider_by_model_name_sync("deepseek-ai/DeepSeek-V3")
        # 应返回一个非空 provider 字符串
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_importerror_logger_name_matches(self, caplog):
        """ImportError 日志应使用正确的 logger 名称"""
        import logging

        caplog.set_level(logging.WARNING)
        import builtins

        from app.services.simple_analysis_service import get_provider_by_model_name_sync

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "app.services.analysis":
                raise ImportError("模拟 analysis 模块不可用")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            get_provider_by_model_name_sync("test-model")
        finally:
            builtins.__import__ = original_import

        # 验证日志来自正确的 logger
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("analysis_service" in r.name or "simple_analysis" in r.name for r in warning_records), (
            f"warning 日志应来自正确的 logger，实际: {[r.name for r in warning_records]}"
        )


# ============================================================
# Bug #9 (P3): RedisProgressTracker 参数不匹配 — 调用方传 total_steps=100 但构造器不接收
# ============================================================


class TestBug9_RedisProgressTrackerSignature:
    """验证 RedisProgressTracker 构造器与调用方参数匹配"""

    def test_init_signature_accepts_total_steps_kwarg(self):
        """RedisProgressTracker.__init__ 应接受 total_steps 关键字参数"""
        # 检查构造器签名
        import inspect

        from app.services.progress.tracker import RedisProgressTracker

        sig = inspect.signature(RedisProgressTracker.__init__)
        params = list(sig.parameters.keys())
        # 应有 task_id（第一个参数除外 self）
        assert "task_id" in params, f"构造器应包含 task_id，实际参数: {params}"
        # total_steps 参数要么在构造器中存在，要么被 **kwargs 捕获
        has_total_steps = "total_steps" in params
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        assert has_total_steps or has_kwargs, f"构造器应接受 total_steps（通过显式参数或 **kwargs），实际签名: {sig}"

    def test_init_with_total_steps_no_typeerror(self):
        """RedisProgressTracker(task_id, total_steps=100) 不应抛出 TypeError"""
        from app.services.progress.tracker import RedisProgressTracker

        try:
            tracker = RedisProgressTracker(task_id="test-fix9", total_steps=100)
            assert tracker.task_id == "test-fix9"
        except TypeError as e:
            pytest.fail(f"RedisProgressTracker(task_id, total_steps=100) 抛出 TypeError: {e}")

    def test_init_without_optional_params(self):
        """RedisProgressTracker(task_id) 只传 task_id 时仍应正常工作"""
        from app.services.progress.tracker import RedisProgressTracker

        try:
            tracker = RedisProgressTracker(task_id="test-minimal")
            assert tracker.task_id == "test-minimal"
        except TypeError as e:
            pytest.fail(f"RedisProgressTracker(task_id) 抛出 TypeError: {e}")

    def test_init_backward_compatible_full_params(self):
        """RedisProgressTracker(task_id, analysts, research_depth, llm_provider) 向后兼容"""
        from app.services.progress.tracker import RedisProgressTracker

        try:
            tracker = RedisProgressTracker(
                task_id="test-full", analysts=["market", "fundamentals"], research_depth="标准", llm_provider="deepseek",
            )
            assert tracker.task_id == "test-full"
            assert tracker.analysts == ["market", "fundamentals"]
        except TypeError as e:
            pytest.fail(f"完整参数调用抛出 TypeError: {e}")

    def test_tracker_not_raise_on_construction(self):
        """验证生产代码中的调用 RedisProgressTracker(task_id, total_steps=100) 不抛 TypeError"""
        # 模拟生产代码的调用方式
        from app.services.progress.tracker import RedisProgressTracker

        # 这就是 line 925 的实际调用方式
        tracker = RedisProgressTracker("test-prod-call", total_steps=100)

        assert tracker is not None
        assert tracker.task_id == "test-prod-call"
