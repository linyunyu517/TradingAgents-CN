# tradingagents/diffusion/uniform_prior.py
"""
均匀先验退化模块 (Uniform Prior)

当扩散推理失败时，退化为均匀分布作为安全回退。

核心哲学:
    这不是降级机制——均匀先验本身就是最大熵分布，
    表示"无信息偏好"，是贝叶斯推理中的合法先验选择。
    当扩散模型无法产生有意义的输出时，系统自然地
    退化为"无信息"状态，而非使用低质量的默认值。

设计原则:
    - 扩散输出失败 → 自动退化为均匀先验，无需额外代码路径
    - 均匀先验的置信度为 0，下游的权重融合机制自动降低其影响
    - 符合"不设计降级机制"的核心原则
"""

from __future__ import annotations

import numpy as np


def uniform_prior(
    shape: tuple[int, ...],
    low: float = -1.0,
    high: float = 1.0,
    dtype: np.dtype | None = None,
) -> np.ndarray:
    """均匀先验分布采样

    当扩散推理失败时，返回均匀分布样本作为安全回退。
    输出范围默认为 [-1, 1]，与扩散模型的标准数据范围一致。

    Args:
        shape: 输出形状，与扩散模型输出格式一致
        low: 均匀分布下限 (默认 -1.0)
        high: 均匀分布上限 (默认 1.0)
        dtype: 输出数据类型 (默认 np.float64)

    Returns:
        np.ndarray: shape 与输入 shape 相同，服从 U(low, high) 分布

    Examples:
        >>> uniform_prior((3, 5))
        array([[-0.23,  0.45, ..., 0.12]])

        >>> uniform_prior((2, 4, 32))  # batch=2, seq=4, dim=32
        array([[[...]]])
    """
    if dtype is None:
        dtype = np.float64
    return np.random.uniform(low, high, size=shape).astype(dtype)


def get_uniform_prior_confidence() -> float:
    """返回均匀先验的置信度

    均匀先验的置信度为 0.0，表示"完全不确定"。
    下游的权重融合机制使用此置信度自动降低均匀先验的影响。

    Returns:
        float: 0.0 (零置信度)
    """
    return 0.0


def is_uniform_prior_applicable(
    output: np.ndarray,
    validity_threshold: float = 0.0,
) -> bool:
    """判断是否需要回退到均匀先验

    简单的有效性检查: 如果输出包含 NaN/Inf 或所有值相等，
    则认为扩散推理失败，需要回退到均匀先验。

    Args:
        output: 扩散模型输出
        validity_threshold: 有效性阈值 (保留用于未来扩展)

    Returns:
        bool: True 表示输出无效，应使用均匀先验
    """
    if output is None:
        return True
    if np.any(np.isnan(output)):
        return True
    if np.any(np.isinf(output)):
        return True
    # 检查是否所有值都相等 (去噪完全失败)
    return bool(output.size > 1 and np.allclose(output, output.flat[0]))


# 模块级便捷引用
__all__ = [
    "get_uniform_prior_confidence",
    "is_uniform_prior_applicable",
    "uniform_prior",
]
