"""
Data sources subpackage.
Expose adapters and manager for backward-compatible imports.
"""

from .base import DataSourceAdapter
from .manager import DataSourceManager
from .tushare_adapter import TushareAdapter
