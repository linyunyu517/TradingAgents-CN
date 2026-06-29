"""数据源标准化错误码和异常类"""

from enum import Enum


class DataSourceErrorCode(str, Enum):
    """统一数据源错误码"""

    # 连接相关
    CONNECTION_FAILED = "CONNECTION_FAILED"  # 连接失败
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"  # 连接超时
    CONNECTION_CLOSED = "CONNECTION_CLOSED"  # 连接已关闭
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"  # 认证失败

    # 请求相关
    RATE_LIMITED = "RATE_LIMITED"  # 触发限流
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"  # 请求超时
    INVALID_PARAMS = "INVALID_PARAMS"  # 参数错误
    REQUEST_FAILED = "REQUEST_FAILED"  # 请求失败

    # 数据相关
    DATA_NOT_FOUND = "DATA_NOT_FOUND"  # 数据不存在
    DATA_EMPTY = "DATA_EMPTY"  # 数据为空
    DATA_FORMAT_ERROR = "DATA_FORMAT_ERROR"  # 数据格式错误
    DATA_TOO_OLD = "DATA_TOO_OLD"  # 数据太旧

    # 限流相关
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"  # 超过限流上限
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # Token 过期
    TOKEN_REQUIRED = "TOKEN_REQUIRED"  # 需要 Token 但未提供

    # 通用
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"  # 不支持的操作
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 内部错误
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"  # 未实现


class DataSourceError(Exception):
    """数据源异常基类"""

    def __init__(
        self,
        code: DataSourceErrorCode,
        message: str,
        provider: str | None = None,
        original_error: Exception | None = None,
    ):
        self.code = code
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(self.__str__())

    def __str__(self) -> str:
        parts = [f"[{self.code.value}] {self.message}"]
        if self.provider:
            parts.insert(0, f"[{self.provider}]")
        if self.original_error:
            parts.append(f"(原始错误: {self.original_error})")
        return " ".join(parts)

    def should_fallback(self) -> bool:
        """是否应触发降级"""
        return self.code in (
            DataSourceErrorCode.CONNECTION_FAILED,
            DataSourceErrorCode.CONNECTION_TIMEOUT,
            DataSourceErrorCode.REQUEST_TIMEOUT,
            DataSourceErrorCode.RATE_LIMIT_EXCEEDED,
            DataSourceErrorCode.DATA_NOT_FOUND,
            DataSourceErrorCode.DATA_EMPTY,
        )


class ConnectionError(DataSourceError):
    """连接异常"""

    def __init__(self, message: str, provider: str | None = None, original: Exception | None = None):
        super().__init__(DataSourceErrorCode.CONNECTION_FAILED, message, provider, original)


class RateLimitError(DataSourceError):
    """限流异常"""

    def __init__(self, message: str, provider: str | None = None, retry_after: float | None = None):
        super().__init__(DataSourceErrorCode.RATE_LIMIT_EXCEEDED, message, provider)
        self.retry_after = retry_after


class DataNotFoundError(DataSourceError):
    """数据不存在异常"""

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(DataSourceErrorCode.DATA_NOT_FOUND, message, provider)


class TokenRequiredError(DataSourceError):
    """需要 Token 但未提供"""

    def __init__(self, provider: str | None = None):
        super().__init__(DataSourceErrorCode.TOKEN_REQUIRED, f"{provider} 需要配置 Token，请在配置文件中设置", provider)
