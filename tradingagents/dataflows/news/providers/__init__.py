"""
反爬虫新闻提供者模块

最高等级反爬虫方案：
  1. EastMoneyProvider — curl_cffi TLS 指纹模拟（主源，15种浏览器随机轮换）
  2. SinaFinanceProvider — requests + BeautifulSoup（备用源）
  3. XueQiuProvider — 雪球社区讨论（情绪辅助源）
  4. EastMoneyGubaProvider — 东方财富股吧论坛情绪数据（curl_cffi TLS 指纹模拟）
"""

from .eastmoney_provider import fetch_news as fetch_eastmoney_news
from .eastmoney_provider import fetch_news_multi_keyword as fetch_eastmoney_news_multi
from .sina_provider import fetch_news as fetch_sina_news
from .xueqiu_provider import fetch_news as fetch_xueqiu_news
from .eastmoney_guba_provider import fetch_guba_posts
from .eastmoney_guba_provider import fetch_guba_sentiment
from .eastmoney_guba_provider import fetch_guba_multi_stock
from .eastmoney_guba_provider import format_sentiment_report

__all__ = [
    "fetch_eastmoney_news",
    "fetch_eastmoney_news_multi",
    "fetch_sina_news",
    "fetch_xueqiu_news",
    "fetch_guba_posts",
    "fetch_guba_sentiment",
    "fetch_guba_multi_stock",
    "format_sentiment_report",
]
