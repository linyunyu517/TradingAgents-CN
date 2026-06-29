"""
响应安全序列化中间件

对所有 Dict[str, Any] 返回类型的端点响应进行安全序列化，
防止 PydanticSerializationError 导致 HTTP 500。
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def safe_serialize(data: Any, depth: int = 0) -> Any:
    """递归安全序列化，处理不可 JSON 序列化的对象

    Args:
        data: 任意 Python 对象
        depth: 递归深度（防止无限递归）

    Returns:
        可被 JSON 安全序列化的 Python 原生类型
    """
    MAX_DEPTH = 50
    if depth > MAX_DEPTH:
        return repr(data)[:200]

    # 基础可 JSON 序列化类型
    if isinstance(data, (str, int, float, bool, type(None))):
        return data

    # type 对象 → 类名
    if isinstance(data, type):
        return f"<class '{data.__module__}.{data.__name__}'>"

    # dict
    if isinstance(data, dict):
        return {str(k): safe_serialize(v, depth + 1) for k, v in data.items()}

    # list / tuple
    if isinstance(data, (list, tuple)):
        return [safe_serialize(item, depth + 1) for item in data]

    # datetime → ISO 格式
    if isinstance(data, datetime):
        return data.isoformat()

    # ObjectId
    if hasattr(data, "__class__") and data.__class__.__name__ == "ObjectId":
        return str(data)

    # dict-like 对象（有 keys 方法）
    if hasattr(data, "keys") and callable(data.keys):
        try:
            return {str(k): safe_serialize(v, depth + 1) for k, v in data.items()}
        except Exception:
            logger.debug("dict 序列化失败 (key=%s)", str(data.__class__.__name__))

    # 枚举成员
    if hasattr(data, "__class__") and hasattr(data.__class__, "__members__"):
        try:
            return str(data.value) if hasattr(data, "value") else str(data)
        except Exception:
            return str(data)
    if hasattr(data, "value") and callable(getattr(data, "value", None)):
        try:
            return data.value
        except Exception:
            logger.debug("value 序列化失败: %s", str(type(data).__name__))

    # 有 __dict__ 的对象（dataclass、普通对象等）
    if hasattr(data, "__dict__"):
        try:
            return safe_serialize(data.__dict__, depth + 1)
        except Exception:
            return str(data)

    # 最终降级
    try:
        return str(data)
    except Exception:
        return repr(data)[:200]


class ResponseSanitizerMiddleware(BaseHTTPMiddleware):
    """响应安全序列化中间件

    拦截所有响应，尝试对 JSON body 进行安全序列化，
    防止不可序列化的对象（如 LangGraph state）导致的 500 错误。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 🐛 [BUG-024] 修复: StreamingResponse 没有 .body 属性，直接跳过
        # 流式响应(SSE/WebSocket)不应经过 JSON 序列化处理
        if hasattr(response, "body") is False:
            return response

        # 只对 JSON 响应进行处理
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        try:
            # 尝试读取并重新序列化 body
            import json

            body = response.body
            if body:
                parsed = json.loads(body)
                safe_parsed = safe_serialize(parsed)
                # 如果序列化后没有变化，直接返回原响应
                if safe_parsed == parsed:
                    return response
                new_body = json.dumps(safe_parsed, ensure_ascii=False, default=str).encode("utf-8")
                from starlette.responses import Response as StarletteResponse

                return StarletteResponse(
                    content=new_body.decode("utf-8"),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type="application/json",
                )
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            # body 不是合法 JSON 或无法处理，跳过
            pass
        except Exception as e:
            logger.warning(f"ResponseSanitizer 处理失败: {e}", exc_info=True)

        return response
