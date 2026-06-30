#!/usr/bin/env python3
"""
启动前验证脚本：检查所有关键 import 是否可用。

在运行 `uvicorn app.main:app` 之前执行此脚本可提前发现
因删除模块导致的 ImportError，避免运行时 500 错误。

用法:
    python scripts/verify_imports.py
"""

import importlib
import logging
import sys
from pathlib import Path

# 确保项目在路径中
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 关键模块清单 — 启动前必须可导入
# ============================================================
CRITICAL_IMPORTS: dict[str, list[str]] = {
    "🐍 核心数据流": [
        "tradingagents.dataflows",
        "tradingagents.dataflows.data_source_manager",
        "tradingagents.dataflows.optimized_china_data",
        "tradingagents.dataflows.interface",
        "tradingagents.dataflows.providers",
        "tradingagents.dataflows.providers.provider_registry",
    ],
    "🔧 App 层": [
        "app.main",
        "app.services.data_sources",
        "app.services.data_sources.manager",
        "app.routers.health",
        "app.routers.multi_source_sync",
        "app.core.config",
        "app.core.rate_limiter",
    ],
    "📡 Tushare 数据源（唯一数据源）": [
        "tradingagents.dataflows.providers.china.tushare",
    ],
    "📰 新闻系统（仅反爬虫）": [
        "tradingagents.dataflows.news.news_source_manager",
        "tradingagents.dataflows.news.providers.eastmoney_provider",
    ],
    "📊 缓存系统": [
        "tradingagents.dataflows.cache",
    ],
}

# ============================================================
# 验证逻辑
# ============================================================


def verify_imports() -> bool:
    """验证所有关键 import 是否可正常导入。

    Returns:
        True 表示所有导入成功，False 表示存在失败项。
    """
    all_ok = True

    for category, modules in CRITICAL_IMPORTS.items():
        logger.info(f"\n{'=' * 60}")
        logger.info(f"  {category}")
        logger.info(f"{'=' * 60}")

        for module_name in modules:
            try:
                importlib.import_module(module_name)
                logger.info(f"  ✅  {module_name}")
            except ImportError as e:
                logger.error(f"  ❌  {module_name}  →  {e}")
                all_ok = False

    return all_ok


# ============================================================
# 已废弃模块清单 — 确保没有被意外重新导入
# ============================================================
FORBIDDEN_IMPORTS: dict[str, list[str]] = {
    "❌ 已移除的数据源（不应被导入）": [
        "tradingagents.dataflows.providers.china.baostock",
        "tradingagents.dataflows.providers.china.baostock_patched",
        "tradingagents.dataflows.providers.china.zzshare_provider",
        "tradingagents.dataflows.providers.china.zzshare_cache",
        "tradingagents.dataflows.providers.us.yfinance",
        "tradingagents.dataflows.providers.us.finnhub",
        "tradingagents.dataflows.providers.us.alpha_vantage_common",
        "tradingagents.dataflows.providers.hk.hk_stock",
        "tradingagents.dataflows.providers.hk.improved_hk",
        "tradingagents.dataflows.realtime_news_utils",
    ],
    "❌ 已移除的服务（不应被导入）": [
        "app.worker.akshare_sync_service",
        "app.worker.baostock_sync_service",
        "app.worker.baostock_init_service",
        "app.worker.financial_data_sync_service",
        "app.worker.multi_period_sync_service",
        "app.worker.us_sync_service",
        "app.worker.hk_sync_service",
        "app.services.data_sources.akshare_adapter",
        "app.services.data_sources.baostock_adapter",
    ],
}


def verify_forbidden_imports() -> bool:
    """验证已移除的模块没有被意外重新导入或创建。

    Returns:
        True 表示所有检查通过（模块均不存在）。
    """
    all_ok = True

    for category, modules in FORBIDDEN_IMPORTS.items():
        logger.info(f"\n{'=' * 60}")
        logger.info(f"  {category}")
        logger.info(f"{'=' * 60}")

        for module_name in modules:
            try:
                importlib.import_module(module_name)
                logger.error(f"  ❌  {module_name}  意外存在！请检查是否被重新创建")
                all_ok = False
            except ImportError:
                logger.info(f"  ✅  {module_name}  (已确认不存在)")

    return all_ok


# ============================================================
# 主入口
# ============================================================


def main():
    logger.info("=" * 60)
    logger.info("  TradingAgents-CN 启动预检脚本")
    logger.info("  验证关键模块导入可用性")
    logger.info("=" * 60)

    critical_ok = verify_imports()
    forbidden_ok = verify_forbidden_imports()

    logger.info(f"\n{'=' * 60}")
    if critical_ok and forbidden_ok:
        logger.info("  ✅ 最终结果：全部通过！可以安全启动。")
        logger.info(f"{'=' * 60}")
        return 0
    else:
        if not critical_ok:
            logger.error("  ❌ 部分关键模块导入失败，请先修复后再启动。")
        if not forbidden_ok:
            logger.error("  ❌ 部分已移除模块意外存在，请检查。")
        logger.info(f"{'=' * 60}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
