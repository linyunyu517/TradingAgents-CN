# -*- coding: utf-8 -*-
"""
新浪财经新闻提供者
备用数据源，使用 requests + BeautifulSoup 获取新浪财经个股新闻。
当东方财富主源失败时自动降级到此源。
"""

import random
import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

# 新浪财经个股新闻 API 端点
_SINA_STOCK_NEWS_URL = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{symbol}.phtml"

# 请求间隔
_MIN_INTERVAL = 1.5
_MAX_INTERVAL = 3.0
_last_request_time = 0.0
_consecutive_failures = 0

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


def _normalize_symbol(symbol: str) -> str:
    """将股票代码转换为新浪格式（如 600519 → sh600519, 000001 → sz000001）"""
    s = symbol.replace(".SH", "").replace(".SZ", "").replace(".SS", "").replace(".XSHE", "").replace(".XSHG", "")
    s = s.strip()
    if s.startswith("6") or s.startswith("9"):
        return f"sh{s}"
    elif s.startswith("0") or s.startswith("3") or s.startswith("2"):
        return f"sz{s}"
    return s


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


def fetch_news(symbol: str, page_size: int = 10) -> list[dict]:
    """
    从新浪财经获取个股新闻。

    Args:
        symbol: 股票代码
        page_size: 最大新闻数量

    Returns:
        list[dict]: 标准格式新闻列表
    """
    global _consecutive_failures

    normalized = _normalize_symbol(symbol)
    url = _SINA_STOCK_NEWS_URL.format(symbol=normalized)

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://finance.sina.com.cn/",
    }

    _rate_limit()

    try:
        logger.info(f"[SinaNews] 请求 {symbol} 新闻 (url={url})")
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[SinaNews] HTTP {resp.status_code}: {symbol}")
            _consecutive_failures += 1
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("ul.list li") or soup.select("div.datelist ul li")
        if not items:
            logger.info(f"[SinaNews] 未找到 {symbol} 的新闻条目")
            _consecutive_failures = 0
            return []

        news_list = []
        for item in items:
            link = item.find("a")
            if not link:
                continue
            title = link.get("title") or link.text or ""
            title = title.strip()
            if not title or len(title) < 8:
                continue
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = "https://finance.sina.com.cn" + href

            # 提取时间
            span = item.find("span")
            pub_time = ""
            if span:
                time_text = span.text.strip()
                try:
                    dt = datetime.strptime(time_text, "%Y-%m-%d %H:%M")
                    pub_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pub_time = time_text

            news_list.append({
                "title": title,
                "content": "",
                "publish_time": pub_time,
                "url": href,
                "source": "新浪财经",
                "media_name": "新浪财经",
            })

            if len(news_list) >= page_size:
                break

        logger.info(f"[SinaNews] ✅ 成功获取 {symbol} 的 {len(news_list)} 条新闻")
        _consecutive_failures = 0
        return news_list

    except Exception as e:
        logger.warning(f"[SinaNews] {symbol} 请求失败: {e}")
        _consecutive_failures += 1
        return []
