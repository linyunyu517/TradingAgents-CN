"""
通知数据模型（MongoDB + Pydantic）
"""

from datetime import datetime
from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, Field, field_serializer, field_validator

from app.utils.timezone import now_tz

# 简单工具：ObjectId -> str


def to_str_id(v: Any) -> str:
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


NotificationType = Literal["analysis", "alert", "system"]
NotificationStatus = Literal["unread", "read"]


class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    content: str | None = None
    link: str | None = None
    source: str | None = None
    severity: Literal["info", "success", "warning", "error"] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v):
        mapping = {
            "analysis_complete": "analysis",
            "analysis_error": "alert",
            "task_complete": "system",
        }
        return mapping.get(v, v)


class NotificationDB(BaseModel):
    id: str | None = Field(default=None)
    user_id: str
    type: NotificationType
    title: str
    content: str | None = None
    link: str | None = None
    source: str | None = None
    severity: Literal["info", "success", "warning", "error"] | None = "info"
    status: NotificationStatus = "unread"
    created_at: datetime = Field(default_factory=now_tz)
    metadata: dict[str, Any] | None = None


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    title: str
    content: str | None = None
    link: str | None = None
    source: str | None = None
    status: NotificationStatus
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime | None, _info) -> str | None:
        """序列化 datetime 为 ISO 8601 格式，保留时区信息"""
        if dt:
            return dt.isoformat()
        return None


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int = 0
    page: int = 1
    page_size: int = 20
