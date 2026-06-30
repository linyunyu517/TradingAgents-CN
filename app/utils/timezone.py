from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.utils._timezone_config import get_cached_settings

logger = logging.getLogger(__name__)


def get_tz_name() -> str:
    """Return configured timezone name, preferring DB system_settings.app_timezone if cached.
    Fallback order: DB (cached) > env (settings.TIMEZONE) > Asia/Shanghai.
    This function is sync and must not await; it relies on provider cache populated elsewhere.

    [B16] Circular import resolved: reads from _timezone_config module-level dict
    instead of lazy-importing app.services.config_provider.
    """
    try:
        cached = get_cached_settings()
        if isinstance(cached, dict):
            tz = cached.get("app_timezone") or cached.get("APP_TIMEZONE")
            if isinstance(tz, str) and tz.strip():
                return tz.strip()
    except Exception:
        logger.warning("缓存读取失败，使用 env 默认值", exc_info=True)
    return settings.TIMEZONE or "Asia/Shanghai"


def get_tz() -> ZoneInfo:
    return ZoneInfo(get_tz_name())


def now_tz() -> datetime:
    """Current time in configured timezone (tz-aware)."""
    return datetime.now(get_tz())


def to_config_tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive as UTC by default, then convert to configured tz
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(get_tz())
    return dt.astimezone(get_tz())


def ensure_timezone(dt: datetime | None) -> datetime | None:
    """
    确保 datetime 对象包含时区信息
    如果没有时区信息，假定为配置的时区（默认 Asia/Shanghai）
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # 如果没有时区信息，假定为配置的时区
        return dt.replace(tzinfo=get_tz())
    return dt
