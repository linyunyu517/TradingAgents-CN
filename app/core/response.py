"""
统一API响应格式工具
"""

from typing import Any

from app.utils.timezone import now_tz


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """标准成功响应
    返回结构：{"success": True, "data": data, "message": message, "timestamp": ...}
    """
    return {"success": True, "data": data, "message": message, "timestamp": now_tz().isoformat()}


def fail(message: str = "error", code: int = 500, data: Any = None) -> dict[str, Any]:
    """标准失败响应（一般错误仍建议用 HTTPException 抛出，此函数用于业务失败场景）"""
    return {"success": False, "data": data, "message": message, "code": code, "timestamp": now_tz().isoformat()}
