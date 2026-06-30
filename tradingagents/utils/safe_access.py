#!/usr/bin/env python3
"""
安全嵌套访问工具（参考 toolz.get_in / Clojure get-in）

提供 safe_get / safe_set 函数，安全访问和设置嵌套字典，
中间节点类型不匹配（如遇到 str 而不是 dict）时返回 default 而非抛异常。

使用场景:
  - state.get("final_trade_decision", {}).get("action")  # type: ignore
  + safe_get(state, ["final_trade_decision", "action"], "")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_get(
    data: Any,
    keys: list[str],
    default: Any = None,
    *,
    warn: bool = True,
) -> Any:
    """安全访问嵌套字典，中间节点类型不匹配时返回 default

    参考 toolz.dicttoolz.get_in，但增强了对非 dict 中间节点的处理：
      - 如果某步遇到 str/int/None 而非 dict → 返回 default 而不是抛 TypeError
      - 如果 warn=True 会在 debug 级别记录命中 default 的情况

    Args:
        data: 任意嵌套的字典（或其他对象）
        keys: 键路径，如 ["final_trade_decision", "action"]
        default: 任何一步失败时返回的值
        warn: 是否在返回 default 时打 debug 日志

    Returns:
        键路径对应的值，或 default
    """
    current = data
    for i, key in enumerate(keys):
        try:
            if isinstance(current, dict):
                if key not in current:
                    if warn:
                        logger.debug(
                            "[safe_get] key=%s 不存在于第 %d 层, 可用 keys=%s, default=%s",
                            key, i, list(current.keys())[:10], default,
                        )
                    return default
                current = current.get(key, default)
            elif isinstance(current, str):
                if warn:
                    logger.debug(
                        "[safe_get] 第 %d 层是 str 而非 dict, key=%s, value=%s, default=%s",
                        i, key, current[:100], default,
                    )
                return default
            else:
                if warn:
                    logger.debug(
                        "[safe_get] 第 %d 层类型异常: %s, key=%s, default=%s",
                        i, type(current).__name__, key, default,
                    )
                return default
        except (AttributeError, TypeError, KeyError) as e:
            if warn:
                logger.debug("[safe_get] 异常 keys=%s, step=%d: %s, default=%s", keys, i, e, default)
            return default

        if current is None:
            if warn:
                logger.debug("[safe_get] 第 %d 层为 None, key=%s, default=%s", i, key, default)
            return default

    return current


def safe_set(data: dict, keys: list[str], value: Any) -> dict:
    """安全设置嵌套值，自动创建中间字典

    参考 Clojure 的 assoc-in 模式。
    就地修改 data 并返回 data。

    Args:
        data: 要修改的字典（就地修改）
        keys: 键路径，如 ["final_trade_decision_obj", "action"]
        value: 要设置的值

    Returns:
        修改后的 data（与输入相同对象）
    """
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return data
