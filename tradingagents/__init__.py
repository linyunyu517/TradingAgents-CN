#!/usr/bin/env python3
"""
TradingAgents-CN 核心模块

这是一个基于多智能体的股票分析系统，支持A股、港股和美股的综合分析。
"""

# === BUG-NEW-006 预防：自动清理 .pyc 缓存 ===
# 根因：Python 运行时可能加载陈旧 .pyc 字节码，导致代码修改不生效
# 策略：每次启动时检查关键模块的文件修改时间，若 .pyc 比 .py 旧则自动重建
import contextlib
import os
import pathlib


def _scan_pycache(py_file: pathlib.Path) -> int:
    """检查并清理单个 .py 文件的 __pycache__ 中的陈旧 .pyc。

    如果 .py 文件比 .pyc 文件更新，删除旧 .pyc 以强制 Python 重新编译。

    Returns:
        删除的 .pyc 文件数
    """
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


def _ensure_fresh_pyc():
    """自动发现并清理所有项目源文件中的陈旧 .pyc 字节码。

    Python 可能加载与当前 .py 源文件不一致的陈旧 .pyc 字节码，
    导致代码修改不生效（BUG-NEW-006 / BUG-037 回归的根本原因）。

    本函数递归扫描 tradingagents/ 和 app/ 目录下所有 .py 文件，
    对每个文件检查其 __pycache__/ 中的 .pyc 是否比 .py 源文件更旧，
    如果是则删除该 .pyc，强制 Python 下次重新编译。

    相比维护固定文件列表的方案，自动扫描的优势：
    - 覆盖所有源文件，不会遗漏新增文件
    - 不需要手动更新列表
    - 跨目录一致（同步覆盖 tradingagents/ 和 app/）
    """
    base_dir = pathlib.Path(__file__).resolve().parent.parent
    total_removed = 0
    total_scanned = 0

    scan_dirs = [
        base_dir / "tradingagents",
        base_dir / "app",
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if ".venv" in py_file.parts or ".mypy_cache" in py_file.parts or ".ruff_cache" in py_file.parts:
                continue
            total_scanned += 1
            total_removed += _scan_pycache(py_file)

    if total_removed > 0:
        import logging
        logging.getLogger(__name__).info(
            f"✅ 自动清理了 {total_removed} 个陈旧 .pyc 文件"
            f"（扫描 {total_scanned} 个 .py 源文件），"
            f"确保字节码与源代码一致",
        )


_ensure_fresh_pyc()
# === END BUG-NEW-006 预防 ===

__version__ = "1.0.0-preview"
__author__ = "TradingAgents-CN Team"
__description__ = "Multi-agent stock analysis system for Chinese markets"

# 导入核心模块
try:
    from .config import config_manager
    from .utils import logging_manager
except ImportError:
    # 如果导入失败，不影响模块的基本功能
    pass

__all__ = ["__author__", "__description__", "__version__"]
