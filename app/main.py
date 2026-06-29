"""
TradingAgents-CN v1.0.0-preview FastAPI Backend
主应用程序入口

Copyright (c) 2025 hsliuping. All rights reserved.
版权所有 (c) 2025 hsliuping。保留所有权利。

This software is proprietary and confidential. Unauthorized copying, distribution,
or use of this software, via any medium, is strictly prohibited.
本软件为专有和机密软件。严禁通过任何媒介未经授权复制、分发或使用本软件。

For commercial licensing, please contact: hsliup@163.com
商业许可咨询，请联系：hsliup@163.com
"""

import contextlib
import os
import pathlib
import sys

# ============================================================
# 🔥 [Bug #2 修复] 强制 stdout/stderr 使用 UTF-8 编码
# 避免 Windows GBK 控制台无法输出 emoji 导致的 UnicodeEncodeError
# ============================================================
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass  # 某些环境（如管道重定向）可能不支持 reconfigure
with contextlib.suppress(Exception):
    sys.stderr.reconfigure(encoding="utf-8")

# 设置环境变量确保子进程也使用 UTF-8
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# [R2 Fix M4] Docker 容器内跳过 PYTHONUTF8，避免 locale 不完整导致子进程静默崩溃
if os.environ.get("DOCKER_CONTAINER") != "true" and not os.path.exists("/.dockerenv"):
    os.environ.setdefault("PYTHONUTF8", "1")

# ============================================================
# Clean Slate R1: 泛化 .pyc 扫描 — 在导入任何业务模块前清理陈旧字节码
# ============================================================
def _scan_pycache(py_file: pathlib.Path) -> int:
    if not py_file.exists():
        return 0
    py_mtime = py_file.stat().st_mtime
    pyc_dir = py_file.parent / "__pycache__"
    removed = 0
    if pyc_dir.exists():
        stem = py_file.stem
        for pyc_file in pyc_dir.glob(f"{stem}.*.pyc"):
            if pyc_file.stat().st_mtime < py_mtime:
                with contextlib.suppress(OSError):
                    pyc_file.unlink()
                    removed += 1
    return removed


def _pre_import_pyc_cleanup():
    total_removed = 0
    total_scanned = 0
    project_root = pathlib.Path(__file__).resolve().parent.parent
    for scan_dir in [project_root / "tradingagents", project_root / "app"]:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if any(p in py_file.parts for p in [".venv", ".mypy_cache", ".ruff_cache", ".git"]):
                continue
            total_scanned += 1
            total_removed += _scan_pycache(py_file)
    if total_removed > 0:
        print(
            f"[pre-import] ✅ 清理 {total_removed} 个陈旧 .pyc "
            f"（扫描 {total_scanned} 个源文件）",
        )
    return total_removed


_pre_import_pyc_cleanup()
# ============================================================

import asyncio
import logging
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging_config import setup_logging

# 港股和美股改为按需获取+缓存模式，不再需要定时同步任务
# from app.worker.hk_sync_service import ...
# from app.worker.us_sync_service import ...
from app.middleware.operation_log_middleware import OperationLogMiddleware
from app.middleware.response_sanitizer import ResponseSanitizerMiddleware

# RUNTIME-020: 使用延迟导入函数替代批量导入，避免单模块失败导致整体启动崩溃
# 路由注册在 app.include_router 处改为导入单个模块
# 保留静态导入中不会失败的稳定模块
from app.routers import health, multi_source_sync
from app.routers import multi_market_stocks as multi_market_stocks_router
from app.routers import notifications as notifications_router
from app.routers import paper as paper_router
from app.routers import scheduler as scheduler_router
from app.routers import stock_data as stock_data_router
from app.routers import stock_sync as stock_sync_router
from app.routers import stocks as stocks_router
from app.routers import sync as sync_router
from app.routers import websocket_notifications as websocket_notifications_router
from app.services.scheduler_service import set_scheduler_instance
from app.services.simple_analysis_service import (
    get_simple_analysis_service,  # CYCLE2-001: 用于 lifespan 关闭时释放线程池
)

# 模块级日志记录器
logger = logging.getLogger(__name__)


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        logger.debug("读取 VERSION 文件失败", exc_info=True)
    return "1.0.0"  # 默认版本号


async def _print_config_summary(logger):
    """显示配置摘要"""
    try:
        logger.info("=" * 70)
        logger.info("📋 TradingAgents-CN Configuration Summary")
        logger.info("=" * 70)

        # .env 文件路径信息
        import os
        from pathlib import Path

        current_dir = Path.cwd()
        logger.info(f"📁 Current working directory: {current_dir}")

        # 检查可能的 .env 文件位置
        env_files_to_check = [
            current_dir / ".env",
            current_dir / "app" / ".env",
            Path(__file__).parent.parent / ".env",  # 项目根目录
        ]

        logger.info("🔍 Checking .env file locations:")
        env_file_found = False
        for env_file in env_files_to_check:
            if env_file.exists():
                logger.info(f"  ✅ Found: {env_file} (size: {env_file.stat().st_size} bytes)")
                env_file_found = True
                # 显示文件的前几行（隐藏敏感信息）
                try:
                    with open(env_file, encoding="utf-8") as f:
                        lines = f.readlines()[:5]  # 只读前5行
                        logger.info("     Preview (first 5 lines):")
                        for i, line in enumerate(lines, 1):
                            # 隐藏包含密码、密钥等敏感信息的行
                            if any(keyword in line.upper() for keyword in ["PASSWORD", "SECRET", "KEY", "TOKEN"]):
                                logger.info(f"       {i}: {line.split('=')[0]}=***")
                            else:
                                logger.info(f"       {i}: {line.strip()}")
                except Exception as e:
                    logger.warning(f"     Could not preview file: {e}")
            else:
                logger.info(f"  ❌ Not found: {env_file}")

        if not env_file_found:
            logger.warning("⚠️  No .env file found in checked locations")

        # Pydantic Settings 配置加载状态
        logger.info("⚙️  Pydantic Settings Configuration:")
        logger.info(f"  • Settings class: {settings.__class__.__name__}")
        logger.info(f"  • Config source: {getattr(settings.model_config, 'env_file', 'Not specified')}")
        logger.info(f"  • Encoding: {getattr(settings.model_config, 'env_file_encoding', 'Not specified')}")

        # 显示一些关键配置值的来源（环境变量 vs 默认值）
        key_settings = ["HOST", "PORT", "DEBUG", "MONGODB_HOST", "REDIS_HOST"]
        logger.info("  • Key settings sources:")
        for setting_name in key_settings:
            env_var_name = setting_name
            env_value = os.getenv(env_var_name)
            config_value = getattr(settings, setting_name, None)
            if env_value is not None:
                logger.info(f"    - {setting_name}: from environment variable ({config_value})")
            else:
                logger.info(f"    - {setting_name}: using default value ({config_value})")

        # 环境信息
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # 数据库连接
        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # 代理配置
        import os

        if settings.HTTP_PROXY or settings.HTTPS_PROXY:
            logger.info("Proxy Configuration:")
            if settings.HTTP_PROXY:
                logger.info(f"  HTTP_PROXY: {settings.HTTP_PROXY}")
            if settings.HTTPS_PROXY:
                logger.info(f"  HTTPS_PROXY: {settings.HTTPS_PROXY}")
            if settings.NO_PROXY:
                # 只显示前3个域名
                no_proxy_list = settings.NO_PROXY.split(",")
                if len(no_proxy_list) <= 3:
                    logger.info(f"  NO_PROXY: {settings.NO_PROXY}")
                else:
                    logger.info(f"  NO_PROXY: {','.join(no_proxy_list[:3])}... ({len(no_proxy_list)} domains)")
            logger.info("  ✅ Proxy environment variables set successfully")
        else:
            logger.info("Proxy: Not configured (direct connection)")

        # 检查大模型配置
        try:
            from app.services.config_service import config_service

            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # 只显示前3个
                        logger.info(f"  • {llm.provider}: {llm.model_name}")
                    if len(enabled_llms) > 3:
                        logger.info(f"  • ... and {len(enabled_llms) - 3} more")
                else:
                    logger.warning("⚠️  No LLM enabled. Please configure at least one LLM in Web UI.")
            else:
                logger.warning("⚠️  No LLM configured. Please configure at least one LLM in Web UI.")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check LLM configs: {e}")

        # 检查数据源配置
        try:
            if config and config.data_source_configs:
                enabled_sources = [ds for ds in config.data_source_configs if ds.enabled]
                logger.info(f"Enabled Data Sources: {len(enabled_sources)}")
                if enabled_sources:
                    for ds in enabled_sources[:3]:  # 只显示前3个
                        logger.info(f"  • {ds.type.value}: {ds.name}")
                    if len(enabled_sources) > 3:
                        logger.info(f"  • ... and {len(enabled_sources) - 3} more")
            else:
                logger.info("Data Sources: Using default (AKShare)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check data source configs: {e}")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Failed to print config summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    setup_logging()
    logger = logging.getLogger("app.main")

    # ========== BUG-008 修复: 添加启动超时保护 ==========
    _shutdown_timeout = 10  # 关闭超时（秒）

    # 验证启动配置
    try:
        from app.core.startup_validator import validate_startup_config

        validate_startup_config()
    except Exception as e:
        # 安全地通过类型名判断，避免模块导入失败时 ConfigurationError 未定义导致 UnboundLocalError
        _err_type_name = type(e).__name__
        if _err_type_name == "ConfigurationError":
            logger.error(f"❌ 配置验证失败: {e}")
            logger.error("💡 请复制 .env.example 为 .env 并填写必需的配置项")
            logger.error("💡 或通过 Web 后台配置向导进行初始化设置")
        else:
            logger.error(f"配置验证失败: {e}")
        raise

    # ========== Clean Slate R4: 部署验证 ==========
    try:
        import importlib
        import sys as _sys
        # 1. Python 版本检查
        py_version = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
        logger.info(f"🔍 Python 版本: {py_version} (需要 >=3.10)")
        if _sys.version_info < (3, 10):
            logger.error("❌ Python 版本过低，需要 >=3.10")
            raise RuntimeError(f"Python {py_version} 不满足最低要求 3.10")

        # 2. 关键模块可导入性检查
        _critical_modules = [
            ("tradingagents/agents/utils/agent_utils", "create_msg_delete"),
            ("tradingagents/graph/setup", "GraphSetup"),
        ]
        for mod_path, sym in _critical_modules:
            try:
                mod = importlib.import_module(mod_path.replace("/", "."))
                if not hasattr(mod, sym):
                    logger.warning(f"  ⚠️ 模块 {mod_path} 缺少符号 {sym}")
            except ImportError as e:
                logger.warning(f"  ⚠️ 模块 {mod_path} 导入失败: {e}")
        logger.info("✅ 部署验证通过")
    except Exception as e:
        logger.warning(f"⚠️ 部署验证异常: {e}")

    # 初始化数据库连接（MongoDB + Redis）
    # RUNTIME-021: 添加重试机制，应对数据库临时不可用
    _max_db_retries = 3
    _db_retry_delay = 2  # 初始延迟（秒），每次翻倍
    _db_connected = False
    for _retry_attempt in range(1, _max_db_retries + 1):
        try:
            await asyncio.wait_for(init_db(), timeout=30)
            logger.info(f"✅ 数据库连接初始化完成（第{_retry_attempt}次尝试）")
            _db_connected = True
            break
        except asyncio.TimeoutError:
            if _retry_attempt < _max_db_retries:
                _delay = _db_retry_delay * (2 ** (_retry_attempt - 1))
                logger.warning(f"⚠️ 数据库连接超时，{_delay}秒后重试（第{_retry_attempt}/{_max_db_retries}次）")
                await asyncio.sleep(_delay)
            else:
                logger.error(
                    f"❌ 数据库连接初始化超时（已重试{_max_db_retries}次），后端继续运行，数据库功能可能不可用",
                )
        except Exception as e:
            if _retry_attempt < _max_db_retries:
                _delay = _db_retry_delay * (2 ** (_retry_attempt - 1))
                logger.warning(f"⚠️ 数据库初始化失败: {e}，{_delay}秒后重试（第{_retry_attempt}/{_max_db_retries}次）")
                await asyncio.sleep(_delay)
            else:
                logger.warning(
                    f"⚠️ 数据库初始化失败（已重试{_max_db_retries}次），后端继续运行，数据库相关功能不可用）: {e}",
                )

    # ========== Phase 5d-1 修复: 初始化调度器实例（解决 scheduler 16 个路由 500 错误）==========
    scheduler = AsyncIOScheduler()
    try:
        set_scheduler_instance(scheduler)
        scheduler.start()
        logger.info("✅ 调度器实例已创建并启动")
    except Exception as e:
        logger.warning(f"⚠️ 调度器初始化失败: {e}")

    # ========== BUG-026-FIX: 启动时主动初始化 SimpleAnalysisService，触发僵尸任务清理 ==========
    try:
        _analysis_svc_startup = get_simple_analysis_service()
        logger.info(f"✅ SimpleAnalysisService 已初始化（实例ID: {id(_analysis_svc_startup)}）")
    except Exception as e:
        logger.warning(f"⚠️ SimpleAnalysisService 初始化失败（服务将在首次请求时懒加载）: {e}")

    # ========== P0-3 Fix: 启动数据源健康检查 ==========
    try:
        pass
    except Exception as e:
        logger.warning(f"⚠️ 数据源健康检查出错: {e}")

    # 启动完成，让应用开始服务
    yield

    # ========== Phase 5d-1 修复: 关闭调度器 ==========
    try:
        scheduler.shutdown(wait=False)
        logger.info("✅ 调度器已关闭")
    except Exception as e:
        logger.warning(f"⚠️ 关闭调度器时出错: {e}")

    # ========== BUG-008 修复: 关闭时添加超时保护，避免 shutdown 挂死 ==========
    try:
        await asyncio.wait_for(close_db(), timeout=_shutdown_timeout)
        logger.info("✅ 数据库连接已关闭")
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ 数据库连接关闭超时（{_shutdown_timeout}秒），强制退出")
    except Exception as e:
        logger.warning(f"⚠️ 关闭数据库连接时出错: {e}")

    # ========== CYCLE2-001: 关闭 SimpleAnalysisService 线程池 ==========
    # atexit.register 在 FastAPI lifespan 的 shutdown 阶段不保证触发
    # 此处显式调用 shutdown() 确保 _thread_pool 和 _async_progress_executor 被释放
    try:
        _analysis_svc = get_simple_analysis_service()
        _analysis_svc.shutdown()
        logger.info("✅ SimpleAnalysisService 线程池已关闭")
    except Exception as e:
        logger.warning(f"⚠️ 关闭 SimpleAnalysisService 时出错: {e}")


# 创建FastAPI应用
app = FastAPI(
    title="TradingAgents-CN API",
    description="股票分析与批量队列系统 API",
    version=get_version(),
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# 安全中间件
if not settings.DEBUG:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 操作日志中间件
app.add_middleware(OperationLogMiddleware)

# 响应安全序列化中间件（防止 PydanticSerializationError）
app.add_middleware(ResponseSanitizerMiddleware)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # 跳过健康检查和静态文件请求的日志
    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # 使用webapi logger记录请求
    logger = logging.getLogger("webapi")
    logger.info(f"[REQ] {request.method} {request.url.path} - 开始处理")

    response = await call_next(request)
    process_time = time.time() - start_time

    # 记录请求完成
    status_tag = "OK" if response.status_code < 400 else "FAIL"
    logger.info(
        f"[{status_tag}] {request.method} {request.url.path} - 状态: {response.status_code} - 耗时: {process_time:.3f}s",
    )

    return response


# 全局异常处理
# 请求ID/Trace-ID 中间件（需作为最外层，放在函数式中间件之后）
from app.middleware.request_id import RequestIDMiddleware

app.add_middleware(RequestIDMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 🐛 [Fix D] 增强诊断日志：记录请求路径、异常类型、异常详情和堆栈
    logger = logging.getLogger("app.main")
    exc_type = type(exc).__name__
    logger.error(
        f"❌ [Fix D] 未处理异常 - 路径: {request.method} {request.url.path} | 异常类型: {exc_type} | 异常详情: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None),
                # 🐛 [Fix D] 附带异常类型，帮助前端/运维快速识别问题类别
                "exception_type": exc_type,
            },
        },
    )


# 测试端点 - 验证中间件是否工作
@app.get("/api/test-log")
async def test_log():
    """测试日志中间件是否工作"""
    logger.info("🧪 测试端点被调用 - 这条消息应该出现在控制台")
    return {"message": "测试成功", "timestamp": time.time()}


# ============================================================
# RUNTIME-020: 路由模块延迟导入 + 守卫，避免单模块失败导致整体启动崩溃
# 原批量导入（约 24 行写在 from xxx import a,b,c,d,...）一旦某模块抛异常
# 整个 app 启动失败。改为逐个延迟导入，失败仅影响该路由。
# ============================================================
import importlib as _importlib

_ROUTER_CACHE = {}


def _lazy_router(mod_name: str):
    """延迟导入路由模块，失败时记录日志并返回 None"""
    if mod_name in _ROUTER_CACHE:
        return _ROUTER_CACHE[mod_name]
    try:
        mod = _importlib.import_module(mod_name)
        _ROUTER_CACHE[mod_name] = mod
        return mod
    except Exception as e:
        # [Fix: HTTP 405 Level-2] 增强日志：输出完整异常链路 + 导入路径分析
        tb_lines = traceback.format_exc().splitlines()
        # 只保留关键 traceback 帧（从 import_module 调用帧开始过滤）
        import_frames = [
            line
            for line in tb_lines
            if "import_module" in line or "importlib" in line or "ModuleNotFoundError" in line or "ImportError" in line
        ]
        detail = "; ".join(import_frames[-4:]) if import_frames else "（无 import 链路信息）"
        logger.warning(
            f"⚠️ [RUNTIME-020] 路由模块 {mod_name} 导入失败（仅该路由不可用）\n"
            f"   ├─ 错误类型: {type(e).__name__}\n"
            f"   ├─ 错误信息: {e}\n"
            f"   └─ import 链路: {detail}",
        )
        _ROUTER_CACHE[mod_name] = None
        return None


# 逐个延迟导入（替代原单行批量 from app.routers import auth_db as auth, analysis, ...）
auth = _lazy_router("app.routers.auth_db")
analysis = _lazy_router("app.routers.analysis")
reports = _lazy_router("app.routers.reports")
screening = _lazy_router("app.routers.screening")
queue = _lazy_router("app.routers.queue")
favorites = _lazy_router("app.routers.favorites")
tags = _lazy_router("app.routers.tags")
config = _lazy_router("app.routers.config")
model_capabilities = _lazy_router("app.routers.model_capabilities")
usage_statistics = _lazy_router("app.routers.usage_statistics")
database = _lazy_router("app.routers.database")
cache = _lazy_router("app.routers.cache")
operation_logs = _lazy_router("app.routers.operation_logs")
logs = _lazy_router("app.routers.logs")
sse = _lazy_router("app.routers.sse")
tushare_init = _lazy_router("app.routers.tushare_init")
historical_data = _lazy_router("app.routers.historical_data")
multi_period_sync = _lazy_router("app.routers.multi_period_sync")
financial_data = _lazy_router("app.routers.financial_data")
news_data = _lazy_router("app.routers.news_data")
social_media = _lazy_router("app.routers.social_media")
internal_messages = _lazy_router("app.routers.internal_messages")
# 系统配置只读摘要（也用延迟导入统一 pattern）
system_config_router = _lazy_router("app.routers.system_config")

# 注册路由
app.include_router(health.router, prefix="/api", tags=["health"])
if auth:
    app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
if analysis:
    app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
if reports:
    app.include_router(reports.router, tags=["reports"])
if screening:
    app.include_router(screening.router, prefix="/api/screening", tags=["screening"])
if queue:
    app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
if favorites:
    app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(stocks_router.router, prefix="/api", tags=["stocks"])
app.include_router(multi_market_stocks_router.router, prefix="/api", tags=["multi-market"])
app.include_router(stock_data_router.router, tags=["stock-data"])
app.include_router(stock_sync_router.router, tags=["stock-sync"])
if tags:
    app.include_router(tags.router, prefix="/api", tags=["tags"])
if config:
    app.include_router(config.router, prefix="/api", tags=["config"])
if model_capabilities:
    app.include_router(model_capabilities.router, tags=["model-capabilities"])
if usage_statistics:
    app.include_router(usage_statistics.router, tags=["usage-statistics"])
if database:
    app.include_router(database.router, prefix="/api/system", tags=["database"])
if cache:
    app.include_router(cache.router, tags=["cache"])
if operation_logs:
    app.include_router(operation_logs.router, prefix="/api/system", tags=["operation_logs"])
if logs:
    app.include_router(logs.router, prefix="/api/system", tags=["logs"])
if system_config_router:
    app.include_router(system_config_router.router, prefix="/api/system", tags=["system"])

# 通知模块（REST + SSE）
app.include_router(notifications_router.router, prefix="/api", tags=["notifications"])

# 🔥 WebSocket 通知模块（替代 SSE + Redis PubSub）
app.include_router(websocket_notifications_router.router, prefix="/api", tags=["websocket"])

# 定时任务管理
app.include_router(scheduler_router.router, tags=["scheduler"])

if sse:
    app.include_router(sse.router, prefix="/api/stream", tags=["streaming"])
app.include_router(sync_router.router)
app.include_router(multi_source_sync.router)
app.include_router(paper_router.router, prefix="/api", tags=["paper"])
if tushare_init:
    app.include_router(tushare_init.router, prefix="/api", tags=["tushare-init"])

if historical_data:
    app.include_router(historical_data.router, tags=["historical-data"])
if multi_period_sync:
    app.include_router(multi_period_sync.router, tags=["multi-period-sync"])
if financial_data:
    app.include_router(financial_data.router, tags=["financial-data"])
if news_data:
    app.include_router(news_data.router, tags=["news-data"])
if social_media:
    app.include_router(social_media.router, tags=["social-media"])
if internal_messages:
    app.include_router(internal_messages.router, tags=["internal-messages"])


@app.get("/")
async def root():
    """根路径 — 优先返回前端 SPA，否则返回 API 信息"""
    FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
    index_path = FRONTEND_DIST / "index.html"
    if index_path.is_file():
        return FileResponse(str(index_path))
    return {
        "name": "TradingAgents-CN API",
        "version": get_version(),
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None,
        "note": "前端未构建。请执行: cd frontend && npm run build",
    }


# ============================================================
# SPA 静态文件服务（必须放在所有 API 路由之后）
# ============================================================
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    logger.info(f"✅ 检测到前端构建产物: {FRONTEND_DIST}")
    # 挂载子目录静态资源（Vite 构建产物结构: js/, css/, assets/）
    for subdir in ["js", "css", "assets"]:
        sub_path = FRONTEND_DIST / subdir
        if sub_path.is_dir():
            app.mount(f"/{subdir}", StaticFiles(directory=str(sub_path)), name=f"spa-{subdir}")
            logger.info(f"  📁 挂载 /{subdir}/ -> {sub_path}")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA fallback 路由：处理根级静态文件和 Vue Router 路径"""
        # [Fix: HTTP 405 Level-3] 对 /api/ 前缀路径直接返回 404，避免返回 405
        if full_path.startswith("api/") or full_path.startswith("api\\"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # 🛡️ 路径遍历防护：确保解析后路径仍在 FRONTEND_DIST 内
        resolved = (FRONTEND_DIST / full_path).resolve()
        if not str(resolved).startswith(str(FRONTEND_DIST.resolve())):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        # 优先返回真实文件（favicon.ico, manifest.json, logo.svg 等）
        if resolved.is_file():
            return FileResponse(str(resolved))
        # SPA fallback: 返回 index.html，由 Vue Router 处理前端路由
        index_path = FRONTEND_DIST / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path), media_type="text/html")
        return JSONResponse({"detail": "前端未构建。请执行: cd frontend && npm run build"})
else:
    logger.warning("⚠️ 未检测到前端构建产物（frontend/dist/），SPA 静态文件服务已禁用")


def _check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用，如果端口被占用则尝试自动释放

    🔥 [Bug K 修复] 在 uvicorn 启动前检查端口可用性，
    避免启动时抛出 [Errno 10048] 错误

    🔥 [BUG-045 增强] 检测到端口被占用时自动尝试释放，
    免去手动查找PID和杀进程的步骤

    Args:
        host: 主机地址
        port: 端口号

    Returns:
        bool: 端口是否可用
    """
    import re
    import socket
    import subprocess

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            logger.error(f"❌ 端口 {port} 已被占用！尝试自动释放...")
            # 尝试通过 netstat + taskkill 自动释放端口
            try:
                # 查找占用端口的PID
                netstat_out = subprocess.check_output(
                    f"netstat -ano | findstr :{port}", shell=True, text=True, timeout=5,
                )
                pid_match = re.search(r"LISTENING\s+(\d+)", netstat_out)
                if pid_match:
                    pid = pid_match.group(1)
                    logger.warning(f"  发现占用进程 PID={pid}，正在终止...")
                    taskkill_out = subprocess.check_output(f"taskkill /F /PID {pid}", shell=True, text=True, timeout=5)
                    logger.warning(f"  {taskkill_out.strip()}")
                    # 等待端口释放
                    import time

                    time.sleep(1)
                    # 再次检查
                    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock2.settimeout(1)
                    result2 = sock2.connect_ex((host, port))
                    sock2.close()
                    if result2 != 0:
                        logger.warning(f"✅ 端口 {port} 已成功释放")
                        return True
                    logger.error(f"❌ 端口 {port} 释放失败，请手动处理")
            except subprocess.TimeoutExpired:
                logger.error("  自动释放超时")
            except Exception as e2:
                logger.error(f"  自动释放异常: {e2}")

            logger.error("💡 手动释放命令：")
            logger.error(f"   netstat -ano | findstr :{port}")
            logger.error("   taskkill /PID <进程ID> /F")
            return False
        return True
    except Exception as e:
        logger.warning(f"⚠️ 端口检查失败: {e}，将继续尝试启动")
        return True


if __name__ == "__main__":
    # 🔥 [Bug K 修复] 启动前检查端口可用性，避免 [Errno 10048]
    if not _check_port_available(settings.HOST, settings.PORT):
        sys.exit(1)
    # RUNTIME-022: PORT 一致性检查 — uvicorn 端口与 settings.PORT 保持一致
    _uvicorn_port = int(getattr(settings, "PORT", 8000))
    if _uvicorn_port != settings.PORT:
        logger.warning(
            f"⚠️ [RUNTIME-022] PORT 不一致: settings.PORT={settings.PORT}, uvicorn port={_uvicorn_port}，使用 settings.PORT",
        )
        _uvicorn_port = settings.PORT
    # BUG-NEW-003 修复: 禁止 WatchFiles 热重载
    # Windows + multiprocessing + reload=True 会导致 KeyboardInterrupt 异常
    # 进程重启使正在进行的分析任务丢失，改为 False 确保稳定性
    _reload_enabled = False
    if _reload_enabled:
        logger.warning("⚠️ [BUG-NEW-003] reload=True 在 Windows 多进程环境下会导致 KeyboardInterrupt 异常，已强制禁用")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=_uvicorn_port,
        reload=_reload_enabled,
        log_level="info",
    )
