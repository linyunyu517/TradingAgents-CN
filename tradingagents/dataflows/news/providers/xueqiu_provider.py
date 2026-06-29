# -*- coding: utf-8 -*-
"""
雪球新闻/社区情绪提供者
从雪球社区获取个股相关讨论和新闻，作为辅助数据源。
主要用于社区情绪分析，补充正式新闻。
"""

import random
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

# 雪球 API
_XUEQIU_STATUS_URL = "https://stock.xueqiu.com/v5/stock/trade/stock_info.json"
_XUEQIU_SEARCH_URL = "https://xueqiu.com/query/v1/search/web/search.json"

_MIN_INTERVAL = 2.0
_MAX_INTERVAL = 4.0
_last_request_time = 0.0
_consecutive_failures = 0

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


def _get_session() -> requests.Session:
    """创建带 cookie 的 session 以绕过雪球的反爬"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    # 先访问首页获取 cookie
    try:
        session.get("https://xueqiu.com/", timeout=10)
    except Exception:
        pass
    return session


def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    base = _MIN_INTERVAL + random.random() * 0.5
    backoff = min(_consecutive_failures * 1.0, _MAX_INTERVAL)
    wait = max(0.0, base + backoff - elapsed)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.time()


def fetch_news(symbol: str, page_size: int = 5) -> list[dict]:
    """
    从雪球获取个股相关讨论。

    Args:
        symbol: 股票代码
        page_size: 最大讨论数量

    Returns:
        list[dict]: 标准格式新闻列表
    """
    global _consecutive_failures
    _rate_limit()

    session = _get_session()
    headers = {
        "Origin": "https://xueqiu.com",
        "Referer": f"https://xueqiu.com/S/{symbol}",
    }

    try:
        logger.info(f"[XueQiu] 请求 {symbol} 讨论")
        params = {
            "q": symbol,
            "count": page_size,
            "page": 1,
            "scope": "all",
            "source": "all",
        }
        resp = session.get(
            _XUEQIU_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=15,
        )

        if resp.status_code != 200:
            logger.warning(f"[XueQiu] HTTP {resp.status_code}: {symbol}")
            _consecutive_failures += 1
            return []

        data = resp.json()
        items = data.get("data", [])
        if not items:
            logger.info(f"[XueQiu] 未找到 {symbol} 的讨论")
            _consecutive_failures = 0
            return []

        news_list = []
        for item in items[:page_size]:
            title = item.get("title", "") or item.get("text", "") or ""
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            if not clean_title or len(clean_title) < 5:
                continue

            content = item.get("text", "") or item.get("description", "") or ""
            clean_content = re.sub(r"<[^>]+>", "", content).strip()

            timestamp = item.get("created_at", 0)
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                try:
                    dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    pub_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pub_time = ""
            else:
                pub_time = ""

            news_list.append({
                "title": clean_title[:200],
                "content": clean_content[:500],
                "publish_time": pub_time,
                "url": item.get("url", f"https://xueqiu.com/{item.get('user_id', '')}/{item.get('id', '')}"),
                "source": "雪球",
                "media_name": item.get("user_name", "雪球用户"),
            })

        logger.info(f"[XueQiu] ✅ 成功获取 {symbol} 的 {len(news_list)} 条讨论")
        _consecutive_failures = 0
        return news_list

    except Exception as e:
        logger.warning(f"[XueQiu] {symbol} 请求失败: {e}")
        _consecutive_failures += 1
        return []
