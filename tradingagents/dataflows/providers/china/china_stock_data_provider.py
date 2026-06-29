"""A 股市场数据提供器的抽象基类 - 扩展通用数据接口的 A 股特色能力"""

from abc import ABC
from typing import Any

from ..base_provider import BaseStockDataProvider


class ChinaStockDataProvider(BaseStockDataProvider, ABC):
    """
    A 股市场数据提供器的中间抽象层。

    在 BaseStockDataProvider（通用数据接口）基础上扩展 A 股特色接口：
    - 涨停复盘 (Limit-Up Review)
    - 龙虎榜 (Dragon & Tiger Board)
    - 市场情绪 (Market Sentiment)
    - 板块分析 (Sector Analysis)
    - 资金流向 (Money Flow)
    - 实时快照 (Real-time Snapshot)

    所有方法默认返回 None（表示不支持），
    具体子类按需覆盖。
    """

    # ═══════════════════════════════════════════
    # 第一类：涨停复盘
    # ═══════════════════════════════════════════

    async def get_limit_up_review(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取涨停复盘数据"""
        return None

    async def get_limit_down_review(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取跌停复盘数据"""
        return None

    async def get_limit_up_statistics(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取涨停统计"""
        return None

    async def get_consecutive_limit_up(
        self, min_boards: int = 2, trade_date: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """获取连板股票列表"""
        return None

    # ═══════════════════════════════════════════
    # 第二类：龙虎榜
    # ═══════════════════════════════════════════

    async def get_dragon_tiger_daily(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取龙虎榜每日榜单"""
        return None

    async def get_dragon_tiger_detailed(self, symbol: str, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取个股龙虎榜详情"""
        return None

    async def get_dragon_tiger_continuous(self, days: int = 5) -> list[dict[str, Any]] | None:
        """获取多日龙虎榜累计排名"""
        return None

    # ═══════════════════════════════════════════
    # 第三类：市场情绪
    # ═══════════════════════════════════════════

    async def get_market_sentiment(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取市场情绪指标"""
        return None

    async def get_market_breadth(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取市场宽度指标"""
        return None

    async def get_a_share_sentiment_index(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取 A 股情绪指数"""
        return None

    # ═══════════════════════════════════════════
    # 第四类：板块分析
    # ═══════════════════════════════════════════

    async def get_sector_performance(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取板块/行业涨跌榜"""
        return None

    async def get_industry_rotation(self, days: int = 5) -> dict[str, Any] | None:
        """获取行业轮动数据"""
        return None

    async def get_concept_board_performance(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取概念板块表现"""
        return None

    async def get_sector_flow(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取板块资金流向"""
        return None

    # ═══════════════════════════════════════════
    # 第五类：资金流向
    # ═══════════════════════════════════════════

    async def get_individual_money_flow(self, symbol: str, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取个股资金流向"""
        return None

    async def get_market_money_flow(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取全市场资金流向汇总"""
        return None

    async def get_margin_and_short(self, trade_date: str | None = None) -> dict[str, Any] | None:
        """获取融资融券数据"""
        return None

    # ═══════════════════════════════════════════
    # 第六类：实时快照
    # ═══════════════════════════════════════════

    async def get_realtime_snapshot(self, symbol: str) -> dict[str, Any] | None:
        """获取个股实时快照"""
        return None

    async def get_market_realtime_snapshot(self, trade_date: str | None = None) -> list[dict[str, Any]] | None:
        """获取全市场实时快照"""
        return None

    async def get_minute_kline(
        self, symbol: str, trade_date: str | None = None, freq: str = "1min",
    ) -> list[dict[str, Any]] | None:
        """获取分钟 K 线数据"""
        return None
