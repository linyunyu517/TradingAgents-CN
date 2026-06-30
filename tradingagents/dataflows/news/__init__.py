"""
新闻数据获取模块
统一管理各种新闻数据源
"""

# 导入企业级反爬虫新闻系统
try:
    from .news_source_manager import get_news, get_news_report

    ANTI_CRAWLER_NEWS_AVAILABLE = True
except ImportError:
    get_news = None
    get_news_report = None
    ANTI_CRAWLER_NEWS_AVAILABLE = False

# 导入反爬虫新闻提供者
try:
    from .providers import (
        fetch_eastmoney_news,
        fetch_eastmoney_news_multi,
        fetch_sina_news,
        fetch_xueqiu_news,
    )

    PROVIDERS_AVAILABLE = True
except ImportError:
    fetch_eastmoney_news = None
    fetch_eastmoney_news_multi = None
    fetch_sina_news = None
    fetch_xueqiu_news = None
    PROVIDERS_AVAILABLE = False

__all__ = [
    "ANTI_CRAWLER_NEWS_AVAILABLE",
    "PROVIDERS_AVAILABLE",
    # Anti-Crawler News System
    "get_news",
    "get_news_report",
    # Anti-Crawler Providers
    "fetch_eastmoney_news",
    "fetch_eastmoney_news_multi",
    "fetch_sina_news",
    "fetch_xueqiu_news",
]
