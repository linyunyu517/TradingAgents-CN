"""
Shared timezone configuration state — extracted to break the circular import chain.

This module must NOT import from ``app.services.config_provider`` or
``app.services.config_service`` (directly or transitively).  It provides a
simple module-level dict that ``config_provider`` populates after fetching
DB settings and that ``timezone.py`` reads when resolving the effective
timezone name.

Circular chain before this extraction::

    app.utils.timezone
        → app.services.config_provider
            → app.services.config_service
                → app.utils.timezone  (lazy import inside now_tz())

After extraction::

    app.utils.timezone
        → app.utils._timezone_config     ✓ (no service imports)
    app.services.config_provider
        → app.utils._timezone_config     ✓ (no circularity)
        → app.services.config_service    (unchanged)
"""

from typing import Any

# ---------------------------------------------------------------------------
# Shared cache — populated by ConfigProvider.get_effective_system_settings(),
# read by timezone.get_tz_name().
# Using a module-level dict avoids any import of config_provider inside
# timezone.py, thereby breaking the cycle.
# ---------------------------------------------------------------------------
_cached_settings: dict[str, Any] | None = None


def set_cached_settings(settings: dict[str, Any]) -> None:
    """Store a snapshot of the DB timezone-relevant settings.

    Called from :meth:`ConfigProvider.get_effective_system_settings`
    after a successful DB fetch.
    """
    global _cached_settings
    _cached_settings = dict(settings)


def get_cached_settings() -> dict[str, Any] | None:
    """Return the most recently cached settings dict (or *None*)."""
    return _cached_settings


def invalidate_cache() -> None:
    """Clear the cached settings (called on provider invalidation)."""
    global _cached_settings
    _cached_settings = None
