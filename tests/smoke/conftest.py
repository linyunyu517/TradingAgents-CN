# TradingAgents-CN Smoke Test Configuration
# 冒烟测试共享 fixture 与配置

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 环境检测标记
# ============================================================


def _check_jax() -> bool:
    """检测 JAX 是否可用（包括 numpyro）"""
    try:
        import jax.numpy as jnp

        jnp.array([1.0])  # 实际测试 JAX 是否能正常工作
        return True
    except Exception:
        return False


def _check_cuda() -> bool:
    """检测 CUDA 是否可用"""
    try:
        import jax

        return jax.devices("gpu") != []
    except Exception:
        return False


HAS_JAX = _check_jax()
HAS_CUDA = _check_cuda()

# ============================================================
# 标记：需要 JAX 或 CUDA 的测试自动跳过
# ============================================================

requires_jax = pytest.mark.skipif(not HAS_JAX, reason="JAX 不可用 — 跳过需要 JAX 的测试（当前环境无 JAX/numpyro）")

requires_cuda = pytest.mark.skipif(not HAS_CUDA, reason="CUDA 不可用 — 跳过需要 CUDA 的测试（当前环境无 GPU）")


@pytest.fixture
def mock_llm():
    """创建一个模拟的 LLM 对象，避免真实 API 调用"""
    llm = MagicMock()
    # 模拟 invoke 返回值
    llm.invoke.return_value = MagicMock(content="这是模拟的分析报告，用于测试。")
    return llm


@pytest.fixture
def mock_toolkit():
    """创建一个模拟的 Toolkit 对象"""
    toolkit = MagicMock()
    toolkit.get_tools.return_value = []
    return toolkit


@pytest.fixture
def mock_memory():
    """创建一个模拟的 Memory 对象"""
    memory = MagicMock()
    return memory


@pytest.fixture
def mock_tool_nodes():
    """创建模拟的 tool_nodes 字典"""
    from langgraph.prebuilt import ToolNode

    return {
        "market": MagicMock(spec=ToolNode),
        "social": MagicMock(spec=ToolNode),
        "news": MagicMock(spec=ToolNode),
        "fundamentals": MagicMock(spec=ToolNode),
    }
