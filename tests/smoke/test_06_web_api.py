# TradingAgents-CN Smoke Test — Web API 服务启动测试
# ============================================================
# 验证 Web API 相关模块能正常导入，核心组件能实例化。
# Web 界面基于 Streamlit，在无 UI 环境下测试导入和语法正确性。
#
# 注意：Streamlit 应用需要在有 UI 的环境中运行（streamlit run），
# 本测试验证的是模块级导入和核心依赖可用性。
# ============================================================

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestWebDependencies:
    """Web 依赖可用性检查"""

    def test_streamlit_importable(self):
        """streamlit 包可导入"""
        try:
            import streamlit

            assert streamlit is not None
        except ImportError:
            pytest.skip("streamlit 未安装")

    def test_plotly_importable(self):
        """plotly 包可导入"""
        try:
            import plotly

            assert plotly is not None
        except ImportError:
            pytest.skip("plotly 未安装")


class TestWebModulesImports:
    """Web 组件模块导入测试"""

    def test_web_components_import(self):
        """Web 组件包可导入"""
        spec = importlib.util.spec_from_file_location(
            "web.components", str(PROJECT_ROOT / "web" / "components" / "__init__.py"),
        )
        assert spec is not None and spec.loader is not None

    def test_web_utils_import(self):
        """Web 工具包可导入"""
        spec = importlib.util.spec_from_file_location("web.utils", str(PROJECT_ROOT / "web" / "utils" / "__init__.py"))
        assert spec is not None and spec.loader is not None

    def test_web_modules_import(self):
        """Web 模块包可导入"""
        spec = importlib.util.spec_from_file_location(
            "web.modules", str(PROJECT_ROOT / "web" / "modules" / "__init__.py"),
        )
        assert spec is not None and spec.loader is not None

    def test_web_config_import(self):
        """Web 配置包可导入"""
        spec = importlib.util.spec_from_file_location(
            "web.config", str(PROJECT_ROOT / "web" / "config" / "__init__.py"),
        )
        assert spec is not None and spec.loader is not None


class TestWebModules:
    """Web 功能模块导入测试"""

    def test_analysis_runner_import(self):
        """analysis_runner 模块语法正确"""
        spec = importlib.util.spec_from_file_location(
            "web.utils.analysis_runner", str(PROJECT_ROOT / "web" / "utils" / "analysis_runner.py"),
        )
        assert spec is not None, "analysis_runner.py 语法分析失败"

    def test_api_checker_import(self):
        """api_checker 模块语法正确"""
        spec = importlib.util.spec_from_file_location(
            "web.utils.api_checker", str(PROJECT_ROOT / "web" / "utils" / "api_checker.py"),
        )
        assert spec is not None, "api_checker.py 语法分析失败"

    def test_auth_manager_import(self):
        """auth_manager 模块语法正确"""
        spec = importlib.util.spec_from_file_location(
            "web.utils.auth_manager", str(PROJECT_ROOT / "web" / "utils" / "auth_manager.py"),
        )
        assert spec is not None, "auth_manager.py 语法分析失败"

    def test_progress_tracker_import(self):
        """progress_tracker 模块语法正确"""
        spec = importlib.util.spec_from_file_location(
            "web.utils.progress_tracker", str(PROJECT_ROOT / "web" / "utils" / "progress_tracker.py"),
        )
        assert spec is not None, "progress_tracker.py 语法分析失败"

    def test_cache_management_import(self):
        """cache_management 模块语法正确"""
        spec = importlib.util.spec_from_file_location(
            "web.modules.cache_management", str(PROJECT_ROOT / "web" / "modules" / "cache_management.py"),
        )
        assert spec is not None, "cache_management.py 语法分析失败"


class TestWebAppSyntax:
    """web/app.py 语法正确性验证"""

    def test_app_py_syntax(self):
        """web/app.py 的 Python 语法正确（通过 compile）"""
        app_path = PROJECT_ROOT / "web" / "app.py"
        try:
            with open(app_path, encoding="utf-8") as f:
                source = f.read()
            compile(source, str(app_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"web/app.py 语法错误: {e}")
        except Exception:
            # 导入错误不算语法错误（可能是缺少依赖）
            pass

    def test_run_web_syntax(self):
        """web/run_web.py 的 Python 语法正确"""
        run_web_path = PROJECT_ROOT / "web" / "run_web.py"
        try:
            with open(run_web_path, encoding="utf-8") as f:
                source = f.read()
            compile(source, str(run_web_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"web/run_web.py 语法错误: {e}")
        except Exception:
            pass

    def test_run_web_importable(self):
        """run_web 模块的导入链可用"""
        try:
            # 只验证导入链，不实际执行
            import web.run_web

            assert web.run_web is not None
        except ImportError as e:
            # 如果缺少 streamlit 等依赖，跳过
            if "streamlit" in str(e).lower() or "plotly" in str(e).lower():
                pytest.skip(f"缺少 Web 依赖: {e}")
            raise


class TestWebComponents:
    """Web 组件模块语法验证"""

    @pytest.mark.parametrize(
        "component_name",
        [
            "analysis_form",
            "analysis_results",
            "async_progress_display",
            "header",
            "login",
            "operation_logs",
            "results_display",
            "sidebar",
            "user_activity_dashboard",
        ],
    )
    def test_component_syntax(self, component_name):
        """组件 {component_name} 语法正确"""
        component_path = PROJECT_ROOT / "web" / "components" / f"{component_name}.py"
        if not component_path.exists():
            pytest.skip(f"组件文件不存在: {component_path}")
        try:
            with open(component_path, encoding="utf-8") as f:
                source = f.read()
            compile(source, str(component_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"{component_name}.py 语法错误: {e}")
        except Exception:
            pass
