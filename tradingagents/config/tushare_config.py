#!/usr/bin/env python3
"""
Tushare配置管理（主数据源）
"""
import logging
import os

logger = logging.getLogger(__name__)


class TushareConfig:
    """Tushare配置"""

    def __init__(self):
        self.token = os.getenv("TUSHARE_TOKEN", "")
        self.enabled = os.getenv("TUSHARE_ENABLED", "true").lower() in ("true", "1", "yes")
        logger.debug("TushareConfig: Token=%s..., Enabled=%s", self.token[:8] if self.token else "NONE", self.enabled)

    def is_available(self) -> bool:
        return bool(self.token) and self.enabled

    def print_config(self) -> None:
        print(f"Tushare Token: {'已配置' if self.token else '未配置'}")
        print(f"Tushare Enabled: {self.enabled}")
