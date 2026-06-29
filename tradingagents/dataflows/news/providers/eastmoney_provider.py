# -*- coding: utf-8 -*-
"""
东方财富新闻提供者
最高等级反爬虫方案：
  - curl_cffi TLS 指纹模拟（5种浏览器随机轮换）
  - JSONP 回调参数随机化
  - 自适应限速（失败时指数退避）
  - 多浏览器冗余（一次失败自动切换）
"""

import json
import random
import time
from datetime import datetime
from typing import Any

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

# 浏览器 TLS 指纹池 — 每次请求随机选择一个
# 仅包含当前 curl_cffi 版本中实际支持的浏览器
_BROWSER_FINGERPRINTS = [
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
    "chrome124",
    "chrome131",
    "chrome145",
    "chrome146",
    "safari17_0",
    "safari15_3",
    "safari180",
    "edge101",
    "firefox133",
    "firefox144",
]

# 东方财富搜索 API 端点
_EASTMONEY_SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"

# 请求间隔控制
_MIN_REQUEST_INTERVAL = 1.0  # 最小间隔（秒）
_MAX_REQUEST_INTERVAL = 3.0  # 最大间隔（秒）— 失败时退避到该值
_last_request_time = 0.0
_consecutive_failures = 0

# HTTP 参考来源 — 随机选择一个以模仿真实浏览器行为
_REFERERS = [
    "https://www.eastmoney.com/",
    "https://so.eastmoney.com/news/s?keyword=",
    "https://guba.eastmoney.com/",
    "https://quote.eastmoney.com/",
    "https://so.eastmoney.com/",
]


def _rate_limit():
    """自适应限速：失败次数越多，等待越久"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    base_interval = _MIN_REQUEST_INTERVAL + random.random() * 0.5
    # 失败退避：连续失败越多，间隔越大
    backoff = min(_consecutive_failures * 0.5, _MAX_REQUEST_INTERVAL)
    wait = max(0.0, base_interval + backoff - elapsed)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.time()


def _get_curl_requests():
    """
    延迟导入 curl_cffi，避免模块加载失败导致整个 provider 不可用。
    如果 curl_cffi 不可用，尝试回退到标准 requests。
    """
    try:
        from curl_cffi import requests as curl_requests
        return curl_requests, True
    except ImportError:
        import requests as std_requests
        logger.warning("[EastMoney] curl_cffi 不可用，回退到标准 requests（反爬保护降低）")
        return std_requests, False


def _build_search_params(keyword: str, page_size: int = 10) -> tuple[dict, dict]:
    """
    构建东方财富搜索 API 的请求参数。
    返回 (params_dict, json_body_dict)
    """
    uid = "".join(random.choices("0123456789abcdef", k=16))
    cb = f"jQuery{random.randint(1000000000, 9999999999)}_{int(time.time() * 1000)}"
    ts = str(int(time.time() * 1000))

    body = {
        "uid": uid,
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "<em>",
                "postTag": "</em>",
            },
        },
    }

    params = {
        "cb": cb,
        "param": json.dumps(body),
        "_": ts,
    }
    return params, body


def _parse_jsonp_response(text: str) -> dict | None:
    """解析 JSONP 响应：剔除 jQuery callback 包裹，提取纯 JSON"""
    try:
        if text.startswith("jQuery"):
            start = text.find("(")
            end = text.rfind(")")
            if start >= 0 and end > start:
                text = text[start + 1 : end]
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, IndexError) as e:
        logger.error(f"[EastMoney] JSONP 解析失败: {e}")
        return None


def _articles_to_standard(articles: list[dict]) -> list[dict]:
    """将东方财富 API 返回的文章列表转换为标准格式"""
    result = []
    for article in articles:
        if not article:
            continue
        title = article.get("title", "")
        if not title or len(title.strip()) < 5:
            continue
        # 去除 <em> 标签
        clean_title = title.replace("<em>", "").replace("</em>", "")
        content = article.get("content", "") or article.get("summary", "") or ""
        clean_content = content.replace("<em>", "").replace("</em>", "")
        pub_time_str = article.get("date", "") or article.get("showTime", "") or ""
        pub_time = None
        if pub_time_str:
            try:
                pub_time = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    pub_time = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    pub_time = datetime.now()

        result.append({
            "title": clean_title,
            "content": clean_content,
            "publish_time": pub_time.strftime("%Y-%m-%d %H:%M:%S") if pub_time else "",
            "url": article.get("url", ""),
            "source": "东方财富",
            "media_name": article.get("mediaName", article.get("source", "东方财富")),
        })
    return result


def fetch_news(keyword: str, page_size: int = 10) -> list[dict]:
    """
    使用 curl_cffi TLS 指纹模拟从东方财富获取新闻。

    这是最高等级的反爬虫实现：
      1. 随机浏览器 TLS 指纹（5种）
      2. JSONP 回调参数随机化
      3. 请求 Referer 随机化
      4. 自适应限速 + 失败退避
      5. 多浏览器冗余：一次失败自动切换浏览器重试
      6. 永不抛异常 — 失败返回空列表

    Args:
        keyword: 搜索关键词（股票代码、名称等）
        page_size: 返回的新闻数量

    Returns:
        list[dict]: 标准格式的新闻列表
    """
    global _consecutive_failures

    req_lib, has_curl = _get_curl_requests()
    params, _ = _build_search_params(keyword, page_size)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": random.choice(_REFERERS),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "script",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
    }

    # 自适应限速
    _rate_limit()

    # 浏览器指纹选择（仅 curl_cffi 支持）
    browser = random.choice(_BROWSER_FINGERPRINTS) if has_curl else None

    try:
        logger.info(
            f"[EastMoney] 请求 {keyword} 新闻 (browser={browser or 'requests'}, "
            f"page_size={page_size}, consecutive_failures={_consecutive_failures})"
        )

        if has_curl and browser:
            response = req_lib.get(
                _EASTMONEY_SEARCH_URL,
                params=params,
                headers=headers,
                impersonate=browser,
                timeout=15,
            )
        else:
            response = req_lib.get(
                _EASTMONEY_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=15,
            )

        if response.status_code != 200:
            logger.warning(f"[EastMoney] HTTP {response.status_code}: {keyword}")
            _consecutive_failures += 1
            return []

        data = _parse_jsonp_response(response.text)
        if not data:
            _consecutive_failures += 1
            return []

        articles = data.get("result", {}).get("cmsArticleWebOld", [])
        if not articles:
            logger.info(f"[EastMoney] 未找到 {keyword} 的相关新闻 (hitsTotal={data.get('hitsTotal', 0)})")
            _consecutive_failures = 0
            return []

        std_articles = _articles_to_standard(articles)
        logger.info(f"[EastMoney] ✅ 成功获取 {keyword} 的 {len(std_articles)} 条新闻")
        _consecutive_failures = 0
        return std_articles

    except Exception as e:
        logger.warning(f"[EastMoney] 请求失败 ({browser or 'requests'}): {type(e).__name__}: {e}")
        _consecutive_failures += 1

        # 如果有 curl_cffi 且不是 requests 回退模式，立即用不同浏览器重试一次
        if has_curl and browser:
            alt_browser = random.choice([b for b in _BROWSER_FINGERPRINTS if b != browser])
            logger.info(f"[EastMoney] 切换到 {alt_browser} 重试 {keyword}")
            try:
                time.sleep(0.5 + random.random() * 0.5)
                response = req_lib.get(
                    _EASTMONEY_SEARCH_URL,
                    params=params,
                    headers=headers,
                    impersonate=alt_browser,
                    timeout=15,
                )
                if response.status_code == 200:
                    data = _parse_jsonp_response(response.text)
                    if data:
                        articles = data.get("result", {}).get("cmsArticleWebOld", [])
                        if articles:
                            std_articles = _articles_to_standard(articles)
                            logger.info(f"[EastMoney] ✅ 重试成功 ({alt_browser}): {keyword}")
                            _consecutive_failures = 0
                            return std_articles
            except Exception as e2:
                logger.warning(f"[EastMoney] 重试也失败 ({alt_browser}): {e2}")
                _consecutive_failures += 1

        return []


def fetch_news_multi_keyword(keywords: list[str], page_size: int = 5) -> list[dict]:
    """
    用多个关键词搜索新闻，合并去重后返回。
    适用于公司名称 + 股票代码同时搜索。

    Args:
        keywords: 搜索关键词列表
        page_size: 每个关键词的新闻数量（总数量 = len(keywords) * page_size，但会去重）

    Returns:
        list[dict]: 去重合并后的新闻列表
    """
    seen_urls = set()
    all_news = []

    for kw in keywords:
        news = fetch_news(kw, page_size=page_size)
        for item in news:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_news.append(item)
        time.sleep(0.3 + random.random() * 0.3)  # 关键词之间也做限速

    # 按时间排序（最新在前）
    all_news.sort(key=lambda x: x.get("publish_time", ""), reverse=True)

    logger.info(f"[EastMoney] ✅ 多关键词搜索完成: {len(all_news)} 条去重新闻 (来自 {len(keywords)} 个关键词)")
    return all_news
