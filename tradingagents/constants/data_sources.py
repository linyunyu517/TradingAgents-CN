"""
数据源编码统一定义
所有数据源的编码、名称、描述等信息都在这里定义

添加新数据源的步骤：
1. 在 DataSourceCode 枚举中添加新的数据源编码
2. 在 DATA_SOURCE_REGISTRY 中注册数据源信息
3. 在对应的 provider 中实现数据源接口
4. 更新前端的数据源类型选项（如果需要）
"""

from dataclasses import dataclass
from enum import Enum


class DataSourceCode(str, Enum):
    """
    数据源编码枚举

    命名规范：
    - 使用大写字母和下划线
    - 值使用小写字母和下划线
    - 保持简洁明了
    """

    # ==================== 缓存数据源 ====================
    MONGODB = "mongodb"  # MongoDB 数据库缓存（最高优先级）

    # ==================== 中国市场数据源 ====================
    TUSHARE = "tushare"  # Tushare Pro - 专业A股数据（主数据源）
    AKSHARE = "akshare"  # AKShare - 开源A股数据
    BAOSTOCK = "baostock"  # BaoStock - 免费A股数据

    # ==================== 其他数据源 ====================
    LOCAL_FILE = "local_file"  # 本地文件数据源
    CUSTOM = "custom"  # 自定义数据源


@dataclass
class DataSourceInfo:
    """数据源信息"""

    code: str  # 数据源编码
    name: str  # 数据源名称
    display_name: str  # 显示名称
    provider: str  # 提供商
    description: str  # 描述
    supported_markets: list[str]  # 支持的市场（a_shares, us_stocks, hk_stocks, etc.）
    requires_api_key: bool  # 是否需要 API 密钥
    is_free: bool  # 是否免费
    official_website: str | None = None  # 官方网站
    documentation_url: str | None = None  # 文档地址
    features: list[str] | None = None  # 特性列表

    def __post_init__(self):
        if self.features is None:
            self.features = []


# ==================== 数据源注册表 ====================
DATA_SOURCE_REGISTRY: dict[str, DataSourceInfo] = {
    # MongoDB 缓存
    DataSourceCode.MONGODB: DataSourceInfo(
        code=DataSourceCode.MONGODB,
        name="MongoDB",
        display_name="MongoDB 缓存",
        provider="MongoDB Inc.",
        description="本地 MongoDB 数据库缓存，最高优先级数据源",
        supported_markets=["a_shares", "us_stocks", "hk_stocks", "crypto", "futures"],
        requires_api_key=False,
        is_free=True,
        features=["本地缓存", "最快速度", "离线可用"],
    ),
    # Tushare
    DataSourceCode.TUSHARE: DataSourceInfo(
        code=DataSourceCode.TUSHARE,
        name="Tushare",
        display_name="Tushare Pro",
        provider="Tushare Pro",
        description="专业的A股数据接口，提供行情、财务、参考数据等全面数据",
        supported_markets=["a_shares"],
        requires_api_key=True,
        is_free=False,
        official_website="https://tushare.pro",
        documentation_url="https://tushare.pro/document/2",
        features=["历史行情", "实时行情", "财务数据", "估值指标", "技术指标", "数据稳定"],
    ),
    # Local File
    DataSourceCode.LOCAL_FILE: DataSourceInfo(
        code=DataSourceCode.LOCAL_FILE,
        name="Local File",
        display_name="本地文件",
        provider="本地",
        description="从本地文件读取数据",
        supported_markets=["a_shares", "us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        features=["离线可用", "自定义数据", "完全免费"],
    ),
    # Custom
    DataSourceCode.CUSTOM: DataSourceInfo(
        code=DataSourceCode.CUSTOM,
        name="Custom",
        display_name="自定义数据源",
        provider="自定义",
        description="自定义数据源接口",
        supported_markets=["a_shares", "us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        features=["自定义接口", "灵活配置"],
    ),
}


# ==================== 辅助函数 ====================


def get_data_source_info(code: str) -> DataSourceInfo | None:
    """
    获取数据源信息

    Args:
        code: 数据源编码

    Returns:
        数据源信息，如果不存在则返回 None
    """
    return DATA_SOURCE_REGISTRY.get(code)


def list_all_data_sources() -> list[DataSourceInfo]:
    """
    列出所有数据源

    Returns:
        所有数据源信息列表
    """
    return list(DATA_SOURCE_REGISTRY.values())


def list_data_sources_by_market(market: str) -> list[DataSourceInfo]:
    """
    列出支持指定市场的数据源

    Args:
        market: 市场类型（a_shares, us_stocks, hk_stocks, etc.）

    Returns:
        支持该市场的数据源列表
    """
    return [info for info in DATA_SOURCE_REGISTRY.values() if market in info.supported_markets]


def list_free_data_sources() -> list[DataSourceInfo]:
    """
    列出所有免费数据源

    Returns:
        免费数据源列表
    """
    return [info for info in DATA_SOURCE_REGISTRY.values() if info.is_free]


def is_data_source_supported(code: str) -> bool:
    """
    检查数据源是否支持

    Args:
        code: 数据源编码

    Returns:
        是否支持
    """
    return code in DATA_SOURCE_REGISTRY
