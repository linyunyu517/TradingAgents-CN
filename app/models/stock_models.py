"""
股票数据模型 - 基于现有集合扩展
采用方案B: 在现有集合基础上扩展字段，保持向后兼容
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_str_id(v: Any) -> str:
    """ObjectId转字符串工具函数"""
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


class MarketType(str, Enum):
    """市场类型枚举"""

    CN = "CN"  # 中国A股
    HK = "HK"  # 港股
    US = "US"  # 美股


class StockStatus(str, Enum):
    """股票状态枚举"""

    LISTED = "L"  # 上市
    DELISTED = "D"  # 退市
    SUSPENDED = "P"  # 暂停上市


class ReportType(str, Enum):
    """报告类型枚举"""

    ANNUAL = "annual"  # 年报
    QUARTERLY = "quarterly"  # 季报


class NewsCategory(str, Enum):
    """新闻类别枚举"""

    COMPANY_ANNOUNCEMENT = "company_announcement"  # 公司公告
    INDUSTRY_NEWS = "industry_news"  # 行业新闻
    MARKET_NEWS = "market_news"  # 市场新闻
    RESEARCH_REPORT = "research_report"  # 研究报告


class SentimentType(str, Enum):
    """情绪类型枚举"""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ExchangeType(str, Enum):
    """交易所类型枚举"""

    SZSE = "SZSE"  # 深圳证券交易所
    SSE = "SSE"  # 上海证券交易所
    SEHK = "SEHK"  # 香港交易所
    NYSE = "NYSE"  # 纽约证券交易所
    NASDAQ = "NASDAQ"  # 纳斯达克


class CurrencyType(str, Enum):
    """货币类型枚举"""

    CNY = "CNY"  # 人民币
    HKD = "HKD"  # 港币
    USD = "USD"  # 美元


class BaseStockModel(BaseModel):
    """股票数据基础模型"""

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    data_source: str = Field(..., description="数据来源")
    version: int = Field(default=1, description="数据版本")

    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat(), date: lambda v: v.isoformat(), Decimal: float},
    )


class StockBasicInfo(BaseStockModel):
    """股票基础信息模型"""

    symbol: str = Field(..., description="标准化股票代码", pattern=r"^\d{6}$")
    exchange_symbol: str = Field(..., description="交易所完整代码")
    name: str = Field(..., description="股票名称")
    name_en: str | None = Field(None, description="英文名称")
    market: str = Field(..., description="交易所")
    board: str = Field(..., description="板块")
    industry: str = Field(..., description="行业")
    industry_code: str | None = Field(None, description="行业代码")
    sector: str = Field(..., description="所属板块")
    list_date: date = Field(..., description="上市日期")
    delist_date: date | None = Field(None, description="退市日期")
    area: str = Field(..., description="所在地区")
    market_cap: float | None = Field(None, description="总市值")
    float_cap: float | None = Field(None, description="流通市值")
    total_shares: float | None = Field(None, description="总股本")
    float_shares: float | None = Field(None, description="流通股本")
    currency: str = Field(default="CNY", description="交易货币")
    status: StockStatus = Field(default=StockStatus.LISTED, description="上市状态")
    is_hs: bool = Field(default=False, description="是否沪深港通标的")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError("股票代码必须是6位数字")
        return v


class StockDailyQuote(BaseStockModel):
    """股票日线行情模型"""

    symbol: str = Field(..., description="股票代码")
    trade_date: date = Field(..., description="交易日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    pre_close: float = Field(..., description="前收盘价")
    change: float = Field(..., description="涨跌额")
    pct_chg: float = Field(..., description="涨跌幅")
    vol: float = Field(..., description="成交量(手)")
    amount: float = Field(..., description="成交额")
    adj_factor: float | None = Field(None, description="复权因子")


class StockMinuteQuote(BaseStockModel):
    """股票分钟行情模型"""

    symbol: str = Field(..., description="股票代码")
    trade_time: datetime = Field(..., description="交易时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    vol: float = Field(..., description="成交量(手)")
    amount: float = Field(..., description="成交额")


class FinancialIndicator(BaseStockModel):
    """财务指标模型"""

    symbol: str = Field(..., description="股票代码")
    report_date: date = Field(..., description="报告日期")
    report_type: ReportType = Field(..., description="报告类型")
    eps: float | None = Field(None, description="基本每股收益")
    diluted_eps: float | None = Field(None, description="稀释每股收益")
    bvps: float | None = Field(None, description="每股净资产")
    operating_revenue: float | None = Field(None, description="营业收入")
    net_profit: float | None = Field(None, description="净利润")
    gross_profit_margin: float | None = Field(None, description="毛利率")
    net_profit_margin: float | None = Field(None, description="净利率")
    roe: float | None = Field(None, description="净资产收益率")
    roa: float | None = Field(None, description="总资产收益率")
    debt_ratio: float | None = Field(None, description="资产负债率")
    free_cash_flow: float | None = Field(None, description="自由现金流")


# ============================================================
# 嵌入结构（用于 API 响应中的嵌套对象）
# ============================================================


class MarketInfo(BaseModel):
    """市场信息结构 - 新增字段"""

    market: MarketType = Field(..., description="市场标识")
    exchange: ExchangeType = Field(..., description="交易所代码")
    exchange_name: str = Field(..., description="交易所名称")
    currency: CurrencyType = Field(..., description="交易货币")
    timezone: str = Field(..., description="时区")
    trading_hours: dict[str, Any] | None = Field(None, description="交易时间")


class TechnicalIndicators(BaseModel):
    """技术指标结构 - 分类扩展设计"""

    # 趋势指标
    trend: dict[str, float] | None = Field(None, description="趋势指标")
    # 震荡指标
    oscillator: dict[str, float] | None = Field(None, description="震荡指标")
    # 通道指标
    channel: dict[str, float] | None = Field(None, description="通道指标")
    # 成交量指标
    volume: dict[str, float] | None = Field(None, description="成交量指标")
    # 波动率指标
    volatility: dict[str, float] | None = Field(None, description="波动率指标")
    # 自定义指标
    custom: dict[str, Any] | None = Field(None, description="自定义指标")


# ============================================================
# API 响应模型（基于现有集合扩展）
# ============================================================


class StockBasicInfoExtended(BaseModel):
    """扩展股票基础信息 - 用于API响应（非ORM）"""

    # === 标准化字段 ===
    symbol: str = Field("", description="6位股票代码")
    full_symbol: str | None = Field(None, description="完整标准化代码")
    name: str = Field("", description="股票名称")
    name_en: str | None = Field(None, description="英文名称")
    market: str | None = Field(None, description="市场")

    # === 基础信息 ===
    area: str | None = Field(None, description="地区")
    industry: str | None = Field(None, description="行业")
    board: str | None = Field(None, description="板块")
    sector: str | None = Field(None, description="所属板块")
    list_date: str | None = Field(None, description="上市日期")
    delist_date: str | None = Field(None, description="退市日期")

    # === 市值 ===
    total_mv: float | None = Field(None, description="总市值")
    float_mv: float | None = Field(None, description="流通市值")
    total_share: float | None = Field(None, description="总股本")
    float_share: float | None = Field(None, description="流通股本")

    # === 估值 ===
    pe: float | None = Field(None, description="市盈率")
    pe_ttm: float | None = Field(None, description="市盈率(TTM)")
    pb: float | None = Field(None, description="市净率")
    ps: float | None = Field(None, description="市销率")
    pcf: float | None = Field(None, description="市现率")

    # === 扩展信息 ===
    market_info: dict[str, Any] | None = Field(None, description="市场信息")
    status: str | None = Field(None, description="状态(L-上市/D-退市)")
    currency: str | None = Field(None, description="货币")
    exchange: str | None = Field(None, description="交易所")
    is_hs: bool | None = Field(None, description="沪深港通")

    # 版本控制
    data_version: int | None = Field(None, description="数据版本")

    model_config = ConfigDict(
        # 允许额外字段，保持向后兼容
        extra="allow",
        # 示例数据
        json_schema_extra={
            "example": {
                # 标准化字段
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "name": "平安银行",
                # 基础信息
                "area": "深圳",
                "industry": "银行",
                "market": "深圳证券交易所",
                "sse": "主板",
                "total_mv": 2500.0,
                "pe": 5.2,
                "pb": 0.8,
                # 扩展字段
                "market_info": {
                    "market": "CN",
                    "exchange": "SZSE",
                    "exchange_name": "深圳证券交易所",
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai",
                },
                "status": "L",
                "data_version": 1,
            },
        },
    )


class MarketQuotesExtended(BaseModel):
    """
    实时行情扩展模型 - 基于现有 market_quotes 集合
    统一使用 symbol 作为主要股票代码字段
    """

    # === 标准化字段 (主要字段) ===
    symbol: str = Field(..., description="6位股票代码", pattern=r"^\d{6}$")
    full_symbol: str | None = Field(None, description="完整标准化代码")
    market: MarketType | None = Field(None, description="市场标识")

    # === 兼容字段 (保持向后兼容) ===
    code: str | None = Field(None, description="6位股票代码(已废弃,使用symbol)")

    # === 行情字段 ===
    close: float | None = Field(None, description="收盘价")
    pct_chg: float | None = Field(None, description="涨跌幅%")
    amount: float | None = Field(None, description="成交额")
    open: float | None = Field(None, description="开盘价")
    high: float | None = Field(None, description="最高价")
    low: float | None = Field(None, description="最低价")
    pre_close: float | None = Field(None, description="前收盘价")
    trade_date: str | None = Field(None, description="交易日期")
    updated_at: datetime | None = Field(None, description="更新时间")

    # 新增行情字段
    current_price: float | None = Field(None, description="当前价格(与close相同)")
    change: float | None = Field(None, description="涨跌额")
    volume: float | None = Field(None, description="成交量")
    turnover_rate: float | None = Field(None, description="换手率")
    volume_ratio: float | None = Field(None, description="量比")

    # 五档行情
    bid_prices: list[float] | None = Field(None, description="买1-5价")
    bid_volumes: list[float] | None = Field(None, description="买1-5量")
    ask_prices: list[float] | None = Field(None, description="卖1-5价")
    ask_volumes: list[float] | None = Field(None, description="卖1-5量")

    # 时间戳
    timestamp: datetime | None = Field(None, description="行情时间戳")

    # 数据源和版本
    data_source: str | None = Field(None, description="数据来源")
    data_version: int | None = Field(None, description="数据版本")

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                # 标准化字段
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "market": "CN",
                # 行情字段
                "close": 12.65,
                "pct_chg": 1.61,
                "amount": 1580000000,
                "open": 12.50,
                "high": 12.80,
                "low": 12.30,
                "trade_date": "2024-01-15",
                # 扩展字段
                "current_price": 12.65,
                "change": 0.20,
                "volume": 125000000,
            },
        },
    )


# 数据库操作相关的响应模型
class StockBasicInfoResponse(BaseModel):
    """股票基础信息API响应模型"""

    success: bool = True
    data: StockBasicInfoExtended | None = None
    message: str = ""


class MarketQuotesResponse(BaseModel):
    """实时行情API响应模型"""

    success: bool = True
    data: MarketQuotesExtended | None = None
    message: str = ""


class StockListResponse(BaseModel):
    """股票列表API响应模型"""

    success: bool = True
    data: list[StockBasicInfoExtended] | None = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    message: str = ""
