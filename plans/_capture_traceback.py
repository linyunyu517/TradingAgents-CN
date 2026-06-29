"""
TradingAgents-CN v1.0.1 — Traceback 捕获脚本
直接重现 TradingAgentsGraph.__init__ 错误，绕过被 SimpleJsonFormatter 破坏的日志系统
"""

import logging
import os
import sys
import traceback

# ── 确保项目路径 ──
PROJECT_ROOT = r"D:\AI-Projects\TradingAgents-CN_v1.0.1"
sys.path.insert(0, PROJECT_ROOT)

# ── 捕获现场：劫持所有 logger 的 error/exception 方法 ──
_original_error = logging.Logger.error


def _patched_error(self, msg, *args, **kwargs):
    if kwargs.get("exc_info"):
        tb = traceback.format_exc()
        print(f"[CAPTURED TRACEBACK] {msg}")
        print(tb)
        with open(os.path.join(PROJECT_ROOT, "plans", "_traceback_captured.txt"), "a", encoding="utf-8") as f:
            f.write(f"[CAPTURED TRACEBACK] {msg}\n{tb}\n")
    return _original_error(self, msg, *args, **kwargs)


logging.Logger.error = _patched_error

_original_exception = logging.Logger.exception


def _patched_exception(self, msg, *args, **kwargs):
    tb = traceback.format_exc()
    print(f"[CAPTURED EXCEPTION] {msg}")
    print(tb)
    with open(os.path.join(PROJECT_ROOT, "plans", "_traceback_captured.txt"), "a", encoding="utf-8") as f:
        f.write(f"[CAPTURED EXCEPTION] {msg}\n{tb}\n")
    return _original_exception(self, msg, *args, **kwargs)


logging.Logger.exception = _patched_exception

# ── 确保环境变量 ──
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-d6efb2f03c334db28bdb6dca77e5db91")

# ── 1. 模拟 create_analysis_config 的输出 ──
from app.models.analysis import SingleAnalysisRequest
from app.services.simple_analysis_service import create_analysis_config

request = SingleAnalysisRequest(symbol="000001")
try:
    config = create_analysis_config(request, "admin", "traceback-capture-001")
    print("create_analysis_config SUCCESS")
    print(f"  llm_provider={config.get('llm_provider')}")
    print(f"  deep_analysis_provider={config.get('deep_analysis_provider')}")
    print(f"  deep_analysis_model={config.get('deep_analysis_model')}")
except Exception as e:
    print(f"create_analysis_config FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── 2. 模拟 _get_trading_graph 的合并逻辑 ──
from tradingagents.default_config import DEFAULT_CONFIG

merged_config = {**DEFAULT_CONFIG, **config}

print("\nMerged config keys:")
print(f"  llm_provider = {merged_config.get('llm_provider')}")
print(f"  deep_think_llm = {merged_config.get('deep_think_llm')}")
print(f"  quick_think_llm = {merged_config.get('quick_think_llm')}")
print(f"  backend_url = {merged_config.get('backend_url')}")
print(f"  deep_analysis_model = {merged_config.get('deep_analysis_model')}")
print(f"  selected_analysts = {merged_config.get('selected_analysts')}")

# ── 3. 直接创建 TradingAgentsGraph ──
from tradingagents.graph.trading_graph import TradingAgentsGraph

print("\nCreating TradingAgentsGraph instance...")
try:
    trading_graph = TradingAgentsGraph(
        selected_analysts=merged_config.get("selected_analysts", ["market", "fundamentals"]),
        debug=merged_config.get("debug", False),
        config=merged_config,
    )
    print(f"TradingAgents instance created OK (ID: {id(trading_graph)})")
except Exception as e:
    print("\nERROR: TradingAgentsGraph.__init__ FAILED!")
    print(f"  Type: {type(e).__name__}")
    print(f"  Message: {e}")
    print(f"\n{'=' * 60}")
    print("FULL PYTHON TRACEBACK:")
    print(f"{'=' * 60}")
    traceback.print_exc()
    tb_path = os.path.join(PROJECT_ROOT, "plans", "_traceback_captured.txt")
    with open(tb_path, "w", encoding="utf-8") as f:
        f.write(f"Error: {type(e).__name__}: {e}\n")
        f.write(f"{'=' * 60}\n")
        traceback.print_exc(file=f)
    print(f"\nTraceback saved to: {tb_path}")
