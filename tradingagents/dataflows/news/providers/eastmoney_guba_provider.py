# -*- coding: utf-8 -*-
"""
东方财富股吧（Guba）舆情提供者
最高等级反爬虫方案：
  - curl_cffi TLS 指纹模拟（15种浏览器随机轮换）
  - 自适应限速（失败时指数退避）
  - 多浏览器冗余（一次失败自动切换）
  - Referer 随机化
  - article_list JSON 数据提取

数据来源：东方财富股吧论坛帖子
API：https://guba.eastmoney.com/list,{code},f_{page}.html
页面内嵌 article_list JavaScript 变量包含帖子结构化 JSON 数据。
"""

import json
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

# =============================================================================
# 浏览器 TLS 指纹池 — 每次请求随机选择一个
# 仅包含当前 curl_cffi 版本中实际支持的浏览器
# =============================================================================
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

# =============================================================================
# 股吧基础 URL
# =============================================================================
_GUBA_LIST_URL = "https://guba.eastmoney.com/list,{code},f_{page}.html"

# =============================================================================
# 请求间隔控制
# =============================================================================
_MIN_REQUEST_INTERVAL = 1.5  # 最小间隔（秒）
_MAX_REQUEST_INTERVAL = 4.0  # 最大间隔（秒）— 失败时退避到该值
_last_request_time = 0.0
_consecutive_failures = 0

# =============================================================================
# HTTP 参考来源 — 随机选择一个以模仿真实浏览器行为
# =============================================================================
_REFERERS = [
    "https://www.eastmoney.com/",
    "https://guba.eastmoney.com/",
    "https://quote.eastmoney.com/",
    "https://so.eastmoney.com/",
    "https://data.eastmoney.com/",
]

# =============================================================================
# 情绪关键词分析
# =============================================================================
_BULLISH_KEYWORDS = [
    "买入", "加仓", "满仓", "涨停", "看多", "抄底", "牛市", "上涨",
    "突破", "新高", "暴拉", "主升", "反弹", "护盘", "看好", "做多",
    "趋势", "金叉", "低吸", "布局", "低估", "机会", "必涨", "翻倍",
    "吃肉", "上车", "稳了", "爆发", "大牛", "超级", "绝对收益",
    "值得拥有", "明天涨停", "继续涨", "冲", "干", "满仓干", "梭哈",
    "重仓", "坚定持有", "坚定看多", "中长期", "价值洼地", "黄金坑",
    "强烈推荐", "重点关注", "潜力股", "龙头", "强者恒强", "回调到位",
]

_BEARISH_KEYWORDS = [
    "卖出", "清仓", "止损", "跌停", "看空", "割肉", "熊市", "下跌",
    "破位", "新低", "崩盘", "主力出货", "出货", "跑路", "利空",
    "减持", "套牢", "回撤", "死叉", "逃顶", "风险", "远离", "快跑",
    "血亏", "亏损", "小心", "警告", "危险", "撤退", "清仓跑路",
    "别买", "别进", "不要进", "赶紧跑", "快跑", "小心为上",
    "谨慎", "观望", "不建议", "回避", "减仓", "轻仓", "空仓",
    "大跌", "暴跌", "完蛋", "没救了", "垃圾", "废物", "骗局",
]

# =============================================================================
# 辅助函数
# =============================================================================


def _rate_limit():
    """自适应限速：失败次数越多，等待越久"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    base_interval = _MIN_REQUEST_INTERVAL + random.random() * 0.5
    # 失败退避：连续失败越多，间隔越大
    backoff = min(_consecutive_failures * 1.0, _MAX_REQUEST_INTERVAL)
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

        logger.warning("[Guba] curl_cffi 不可用，回退到标准 requests（反爬保护降低）")
        return std_requests, False


def _clean_stock_code(ticker: str) -> str:
    """清理股票代码，移除后缀"""
    return (
        ticker.replace(".SH", "")
        .replace(".SZ", "")
        .replace(".SS", "")
        .replace(".XSHE", "")
        .replace(".XSHG", "")
        .replace(".HK", "")
        .replace(".US", "")
        .strip()
    )


def _extract_article_list(html: str | bytes) -> list[dict] | None:
    """
    从股吧 HTML 页面中提取 article_list JSON 数据。
    
    页面内嵌的 JavaScript 变量格式：
    var article_list = {"re": [...], "rc": 0, "page": {...}};
    
    注意：article_list 中的 JSON 数据使用 UTF-8 编码（独立于页面 GBK 编码），
    因此推荐传入原始 bytes 以避免 GBK 解码导致的字符损坏。
    
    Args:
        html: HTML 页面内容（str 或 bytes）。传入 bytes 可以获得最准确的 JSON 提取。
        
    Returns:
        list[dict] | None: 帖子列表，提取失败返回 None
    """
    # 统一为 bytes 处理（覆盖 bytes / bytearray / str）
    if isinstance(html, (bytes, bytearray)):
        raw_bytes = bytes(html) if isinstance(html, bytearray) else html
    elif isinstance(html, str):
        raw_bytes = html.encode("utf-8", errors="replace")
    else:
        logger.warning(f"[Guba] 意外输入类型 {type(html).__name__}，尝试 str() 转换")
        raw_bytes = str(html).encode("utf-8", errors="replace")

    # 从原始 bytes 中匹配 article_list
    pattern = rb"var\s+article_list\s*=\s*(\{)"
    match = re.search(pattern, raw_bytes, re.DOTALL)

    if not match:
        logger.warning("[Guba] 未找到 article_list 数据（页面结构可能已变更）")
        return None

    # 定位到第一个 { 开始 brace counting
    brace_start = match.start(1)

    depth = 1
    i = brace_start
    in_str = False
    esc = False

    while depth > 0 and i < len(raw_bytes) - 1:
        i += 1
        b = raw_bytes[i]
        if esc:
            esc = False
            continue
        if b == 0x5C:  # backslash
            esc = True
            continue
        if b == 0x22:  # double quote
            in_str = not in_str
            continue
        if not in_str:
            if b == 0x7B:  # {
                depth += 1
            elif b == 0x7D:  # }
                depth -= 1

    json_bytes = raw_bytes[brace_start : i + 1]

    # Decode as UTF-8 (article_list JSON is always UTF-8)
    json_str = json_bytes.decode("utf-8", errors="replace")

    try:
        data = json.loads(json_str)
        posts = data.get("re", [])
        if not posts:
            logger.info("[Guba] article_list 中无帖子数据")
            return []
        return posts
    except json.JSONDecodeError as e:
        logger.warning(f"[Guba] article_list JSON 解析失败: {e}")
        return None


def _extract_article_list_from_old_format(html: str) -> list[dict] | None:
    """
    备用提取方法：尝试从旧版股吧页面结构提取帖子数据。
    某些 Guba 页面使用不同的 JavaScript 变量名或结构。
    """
    # 尝试替代变量名
    patterns = [
        r"var\s+data_list\s*=\s*(\[.*?\]);",
        r"var\s+post_list\s*=\s*(\[.*?\]);",
        r"var\s+gbData\s*=\s*(\{.*?\});",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    posts = data.get("re") or data.get("list") or data.get("data") or data.get("posts")
                    if posts:
                        return posts
            except json.JSONDecodeError:
                continue
    return None


def _parse_post_time(time_str: str) -> str:
    """
    解析股吧帖子时间，统一为标准格式。
    
    股吧时间格式多样：
    - "06-28"（当天，月-日）
    - "06-28 15:30"（月-日 时:分）
    - "2024-06-28 15:30:00"（完整格式）
    - "刚刚"、"5分钟前"、"1小时前"（相对时间）
    """
    if not time_str:
        return ""

    time_str = time_str.strip()

    # 相对时间处理
    now = datetime.now()
    if "刚刚" in time_str:
        return now.strftime("%Y-%m-%d %H:%M:%S")
    if "分钟" in time_str:
        try:
            minutes = int(re.search(r"(\d+)", time_str).group(1))
            return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        except (AttributeError, ValueError):
            pass
    if "小时" in time_str:
        try:
            hours = int(re.search(r"(\d+)", time_str).group(1))
            return (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        except (AttributeError, ValueError):
            pass
    if "昨天" in time_str:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d") + time_str.replace("昨天", " 00:00:00")

    # 完整格式：YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # 完整格式变体
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # 月-日 时:分（跨年情况）
    try:
        dt = datetime.strptime(time_str, "%m-%d %H:%M")
        # 如果月份在当前月之后，可能是去年的数据
        if dt.month > now.month:
            dt = dt.replace(year=now.year - 1)
        else:
            dt = dt.replace(year=now.year)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # 纯月-日
    try:
        dt = datetime.strptime(time_str, "%m-%d")
        dt = dt.replace(year=now.year)
        if dt > now:
            dt = dt.replace(year=now.year - 1)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # 无法解析，返回原始字符串
    return time_str


def _analyze_sentiment_keywords(title: str, content: str = "") -> dict:
    """
    基于关键词的帖子情绪分析。
    
    Args:
        title: 帖子标题
        content: 帖子内容摘要
        
    Returns:
        dict: {sentiment, score, bullish_matches, bearish_matches}
    """
    text = f"{title} {content}".lower()
    bullish_matches = [kw for kw in _BULLISH_KEYWORDS if kw in text]
    bearish_matches = [kw for kw in _BEARISH_KEYWORDS if kw in text]

    bullish_count = len(bullish_matches)
    bearish_count = len(bearish_matches)

    if bullish_count > bearish_count:
        sentiment = "positive"
        # 强度：基于关键词比例
        score = min(0.9, 0.5 + (bullish_count - bearish_count) * 0.1)
    elif bearish_count > bullish_count:
        sentiment = "negative"
        score = max(-0.9, -0.5 - (bearish_count - bullish_count) * 0.1)
    else:
        sentiment = "neutral"
        score = 0.0

    return {
        "sentiment": sentiment,
        "score": round(score, 4),
        "bullish_matches": bullish_matches[:5],
        "bearish_matches": bearish_matches[:5],
    }


def _posts_to_standard(posts: list[dict], ticker: str) -> list[dict]:
    """
    将股吧 API 返回的帖子列表转换为标准格式。
    
    Args:
        posts: 原始帖子列表（来自 article_list JSON）
        ticker: 股票代码
        
    Returns:
        list[dict]: 标准化后的帖子列表
    """
    result = []
    for post in posts:
        if not post:
            continue

        # 提取标题
        title = (
            post.get("post_title", "")
            or post.get("title", "")
            or post.get("art_title", "")
        )
        if not title or len(title.strip()) < 2:
            continue
        clean_title = title.strip()

        # 提取内容摘要
        content = (
            post.get("post_content", "")
            or post.get("content", "")
            or post.get("post_abstract", "")
            or post.get("abstract", "")
            or ""
        )
        # 去除 HTML 标签
        clean_content = re.sub(r"<[^>]+>", "", content).strip()
        # 截取前 500 字符
        if len(clean_content) > 500:
            clean_content = clean_content[:500] + "..."

        # 提取发布时间（article_list JSON 中的时间已经是标准格式）
        pub_time_str = (
            post.get("post_publish_time", "")
            or post.get("post_display_time", "")
            or post.get("publish_time", "")
            or post.get("post_date", "")
            or post.get("date", "")
        )
        pub_time = _parse_post_time(pub_time_str)

        # 提取作者（post_user 是嵌套字典）
        post_user = post.get("post_user", {})
        if isinstance(post_user, dict):
            author = (
                post_user.get("user_nickname", "")
                or post_user.get("user_name", "")
                or ""
            )
            user_id = str(post_user.get("user_id", "") or "")
        else:
            author = (
                post.get("user_nickname", "")
                or post.get("user_name", "")
                or post.get("nickname", "")
                or ""
            )
            user_id = (
                str(post.get("user_id", ""))
                or str(post.get("UserId", ""))
                or ""
            )

        # 提取互动数据
        read_count = int(
            post.get("post_click_count", 0)
            or post.get("click_count", 0)
            or post.get("click", 0)
            or post.get("read_count", 0)
            or 0
        )
        reply_count = int(
            post.get("post_comment_count", 0)
            or post.get("comment_count", 0)
            or post.get("reply_count", 0)
            or 0
        )
        like_count = int(
            post.get("post_like_count", 0)
            or post.get("like_count", 0)
            or post.get("like", 0)
            or 0
        )

        # 帖子ID
        post_id = (
            str(post.get("post_id", ""))
            or str(post.get("art_code", ""))
            or str(post.get("id", ""))
            or str(post.get("Id", ""))
        )

        # 情绪分析
        sentiment_result = _analyze_sentiment_keywords(clean_title, clean_content)

        result.append({
            "post_id": post_id,
            "title": clean_title,
            "content": clean_content,
            "author": author,
            "user_id": user_id,
            "publish_time": pub_time,
            "read_count": read_count,
            "reply_count": reply_count,
            "like_count": like_count,
            "source": "东方财富股吧",
            "platform": "guba",
            "ticker": ticker,
            "sentiment": sentiment_result["sentiment"],
            "sentiment_score": sentiment_result["score"],
            "bullish_keywords": sentiment_result["bullish_matches"],
            "bearish_keywords": sentiment_result["bearish_matches"],
        })

    return result


def _gbk_decode_or_fallback(content: bytes) -> str:
    """
    尝试解码 GBK 编码的 HTML 页面。
    股吧页面使用 GBK/GB2312 编码，但有时也返回 UTF-8。
    """
    for encoding in ["gbk", "gb2312", "gb18030", "utf-8", "latin-1"]:
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="ignore")


# =============================================================================
# 主接口函数
# =============================================================================


def fetch_guba_posts(ticker: str, page: int = 1, max_posts: int = 20) -> list[dict]:
    """
    从东方财富股吧获取指定股票的论坛帖子。
    
    最高等级反爬虫实现：
      1. 随机浏览器 TLS 指纹（15种）
      2. 请求 Referer 随机化
      3. 自适应限速 + 失败退避
      4. 多浏览器冗余：一次失败自动切换浏览器重试
      5. 永不抛异常 — 失败返回空列表

    Args:
        ticker: 股票代码（如 600519, 000001, 300750）
        page: 页码（从1开始）
        max_posts: 最大返回帖子数

    Returns:
        list[dict]: 标准化帖子列表
    """
    global _consecutive_failures

    code = _clean_stock_code(ticker)
    req_lib, has_curl = _get_curl_requests()

    url = _GUBA_LIST_URL.format(code=code, page=page)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": random.choice(_REFERERS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    # 自适应限速
    _rate_limit()

    # 浏览器指纹选择（仅 curl_cffi 支持）
    browser = random.choice(_BROWSER_FINGERPRINTS) if has_curl else None

    try:
        logger.info(
            f"[Guba] 请求 {code} 股吧第{page}页 (browser={browser or 'requests'}, "
            f"consecutive_failures={_consecutive_failures})"
        )

        if has_curl and browser:
            response = req_lib.get(
                url,
                headers=headers,
                impersonate=browser,
                timeout=20,
            )
        else:
            response = req_lib.get(
                url,
                headers=headers,
                timeout=20,
            )

        if response.status_code != 200:
            logger.warning(f"[Guba] HTTP {response.status_code}: {code} 第{page}页")
            _consecutive_failures += 1
            return []

        # 获取原始响应内容
        # 注意：article_list 中的 JSON 数据使用 UTF-8 编码（独立于页面 GBK 编码）
        # 因此必须从原始 bytes 中提取 JSON，避免 GBK 解码导致的字符损坏
        raw_bytes = response.content if hasattr(response, "content") else response.text.encode("utf-8")
        # GBK 解码仅用于 HTML 层面的正则备选方案
        html_text = _gbk_decode_or_fallback(raw_bytes) if isinstance(raw_bytes, bytes) else raw_bytes

        # 提取 article_list JSON 数据（使用原始 bytes 中的 UTF-8 JSON）
        posts = _extract_article_list(raw_bytes)
        if posts is None:
            # 尝试从解码后的 HTML 中提取（备选）
            posts = _extract_article_list(html_text)
        if posts is None:
            # 尝试旧格式
            posts = _extract_article_list_from_old_format(html_text)

        if not posts:
            logger.info(f"[Guba] 未找到 {code} 的股吧帖子（第{page}页无数据）")
            _consecutive_failures = 0
            return []

        # 标准化
        std_posts = _posts_to_standard(posts, code)

        # 截断到 max_posts
        if len(std_posts) > max_posts:
            std_posts = std_posts[:max_posts]

        logger.info(f"[Guba] ✅ 成功获取 {code} 股吧第{page}页: {len(std_posts)} 条帖子")
        _consecutive_failures = 0
        return std_posts

    except Exception as e:
        logger.warning(f"[Guba] 请求失败 ({browser or 'requests'}): {type(e).__name__}: {e}")
        _consecutive_failures += 1

        # 有 curl_cffi 且不是 requests 回退模式，立即用不同浏览器重试一次
        if has_curl and browser:
            alt_browser = random.choice([b for b in _BROWSER_FINGERPRINTS if b != browser])
            logger.info(f"[Guba] 切换到 {alt_browser} 重试 {code}")
            try:
                time.sleep(0.5 + random.random() * 0.5)
                if has_curl and alt_browser:
                    response = req_lib.get(
                        url,
                        headers=headers,
                        impersonate=alt_browser,
                        timeout=20,
                    )
                else:
                    response = req_lib.get(url, headers=headers, timeout=20)

                if response.status_code == 200:
                    raw_bytes = response.content if hasattr(response, "content") else response.text.encode("utf-8")
                    html_text = _gbk_decode_or_fallback(raw_bytes) if isinstance(raw_bytes, bytes) else raw_bytes

                    posts = _extract_article_list(raw_bytes)
                    if posts is None:
                        posts = _extract_article_list(html_text)
                    if posts is None:
                        posts = _extract_article_list_from_old_format(html_text)

                    if posts:
                        std_posts = _posts_to_standard(posts, code)
                        if len(std_posts) > max_posts:
                            std_posts = std_posts[:max_posts]
                        logger.info(f"[Guba] ✅ 重试成功 ({alt_browser}): {code} 第{page}页, {len(std_posts)} 条")
                        _consecutive_failures = 0
                        return std_posts
            except Exception as e2:
                logger.warning(f"[Guba] 重试也失败 ({alt_browser}): {e2}")
                _consecutive_failures += 1

        return []


def fetch_guba_sentiment(ticker: str, pages: int = 2, max_posts: int = 40) -> dict:
    """
    获取指定股票的股吧情绪分析报告。
    
    聚合多页帖子数据，计算整体情绪指标。

    Args:
        ticker: 股票代码
        pages: 获取的页数（每页约20条帖子）
        max_posts: 最大帖子数量

    Returns:
        dict: {
            "ticker": str,
            "total_posts": int,
            "sentiment_distribution": {"positive": int, "neutral": int, "negative": int},
            "sentiment_score": float,  # 综合情绪得分 (-1~1)
            "avg_read_count": float,
            "avg_reply_count": float,
            "hot_posts": list[dict],  # 最热帖子（按阅读量排序）
            "bullish_keywords": list[str],  # 看多关键词汇总
            "bearish_keywords": list[str],  # 看空关键词汇总
            "recent_posts": list[dict],  # 最新帖子
        }
    """
    code = _clean_stock_code(ticker)
    all_posts = []

    for page in range(1, pages + 1):
        posts = fetch_guba_posts(code, page=page, max_posts=max_posts)
        if posts:
            all_posts.extend(posts)
        # 页间延迟
        time.sleep(0.5 + random.random() * 0.5)
        if len(all_posts) >= max_posts:
            break

    if not all_posts:
        return {
            "ticker": code,
            "total_posts": 0,
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "sentiment_score": 0.0,
            "avg_read_count": 0.0,
            "avg_reply_count": 0.0,
            "hot_posts": [],
            "bullish_keywords": [],
            "bearish_keywords": [],
            "recent_posts": [],
            "note": "数据获取受限，请稍后重试",
        }

    # 统计情绪分布
    positive_count = sum(1 for p in all_posts if p.get("sentiment") == "positive")
    negative_count = sum(1 for p in all_posts if p.get("sentiment") == "negative")
    neutral_count = sum(1 for p in all_posts if p.get("sentiment") == "neutral")

    # 综合情绪得分 (简单平均)
    sentiment_scores = [p.get("sentiment_score", 0) for p in all_posts]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

    # 平均阅读/回复数
    read_counts = [p.get("read_count", 0) for p in all_posts if p.get("read_count", 0) > 0]
    reply_counts = [p.get("reply_count", 0) for p in all_posts if p.get("reply_count", 0) > 0]
    avg_read = sum(read_counts) / len(read_counts) if read_counts else 0.0
    avg_reply = sum(reply_counts) / len(reply_counts) if reply_counts else 0.0

    # 热门帖子（按阅读量排序）
    hot_posts = sorted(all_posts, key=lambda x: x.get("read_count", 0), reverse=True)[:5]

    # 关键词汇总
    all_bullish = set()
    all_bearish = set()
    for p in all_posts:
        all_bullish.update(p.get("bullish_keywords", []))
        all_bearish.update(p.get("bearish_keywords", []))

    # 最新帖子（按发布时间排序）
    sorted_by_time = sorted(
        [p for p in all_posts if p.get("publish_time")],
        key=lambda x: x.get("publish_time", ""),
        reverse=True,
    )
    recent_posts = sorted_by_time[:5]

    # 移除详细关键词以节省空间（保留汇总结果即可）
    for p in all_posts:
        p.pop("bullish_keywords", None)
        p.pop("bearish_keywords", None)

    return {
        "ticker": code,
        "total_posts": len(all_posts),
        "sentiment_distribution": {
            "positive": positive_count,
            "neutral": neutral_count,
            "negative": negative_count,
        },
        "sentiment_score": round(avg_sentiment, 4),
        "positive_ratio": round(positive_count / len(all_posts), 4) if all_posts else 0.0,
        "negative_ratio": round(negative_count / len(all_posts), 4) if all_posts else 0.0,
        "neutral_ratio": round(neutral_count / len(all_posts), 4) if all_posts else 0.0,
        "avg_read_count": round(avg_read, 1),
        "avg_reply_count": round(avg_reply, 1),
        "hot_posts": [
            {
                "title": p.get("title", ""),
                "author": p.get("author", ""),
                "read_count": p.get("read_count", 0),
                "reply_count": p.get("reply_count", 0),
                "sentiment": p.get("sentiment", "neutral"),
                "publish_time": p.get("publish_time", ""),
            }
            for p in hot_posts
        ],
        "recent_posts": [
            {
                "title": p.get("title", ""),
                "author": p.get("author", ""),
                "sentiment": p.get("sentiment", "neutral"),
                "publish_time": p.get("publish_time", ""),
            }
            for p in recent_posts
        ],
        "bullish_keywords": list(all_bullish)[:10],
        "bearish_keywords": list(all_bearish)[:10],
    }


def fetch_guba_multi_stock(tickers: list[str], pages: int = 1, posts_per_stock: int = 10) -> dict[str, dict]:
    """
    批量获取多只股票的股吧情绪数据。
    
    Args:
        tickers: 股票代码列表
        pages: 每只股票获取的页数
        posts_per_stock: 每只股票最大帖子数
        
    Returns:
        dict: {ticker: sentiment_dict, ...}
    """
    results = {}
    for ticker in tickers:
        code = _clean_stock_code(ticker)
        sentiment = fetch_guba_sentiment(code, pages=pages, max_posts=posts_per_stock)
        results[code] = sentiment
        # 股票间延迟
        time.sleep(1.0 + random.random() * 1.0)
    return results


def format_sentiment_report(sentiment: dict) -> str:
    """
    将股吧情绪分析结果格式化为报告字符串。
    
    Args:
        sentiment: fetch_guba_sentiment 返回的结果
        
    Returns:
        str: 格式化的报告
    """
    if not sentiment or sentiment.get("total_posts", 0) == 0:
        ticker = sentiment.get("ticker", "未知")
        return f"📊 **{ticker} 东方财富股吧情绪分析**\n\n暂无股吧讨论数据。当前数据获取受限，建议稍后重试。\n"

    ticker = sentiment.get("ticker", "未知")
    total = sentiment["total_posts"]
    dist = sentiment["sentiment_distribution"]
    score = sentiment["sentiment_score"]

    # 情绪等级
    if score > 0.3:
        level = "🟢 积极"
        signal = "市场情绪偏乐观，投资者看多情绪浓厚"
    elif score > 0.1:
        level = "🟡 偏积极"
        signal = "市场情绪略偏乐观"
    elif score > -0.1:
        level = "⚪ 中性"
        signal = "市场情绪中性，多空分歧不大"
    elif score > -0.3:
        level = "🟠 偏消极"
        signal = "市场情绪略偏悲观"
    else:
        level = "🔴 消极"
        signal = "市场情绪偏悲观，投资者看空情绪浓厚"

    report = f"📊 **{ticker} 东方财富股吧情绪分析**\n"
    report += f"分析样本: {total} 条帖子\n\n"
    report += f"**综合情绪得分**: {score:.4f} ({level})\n"
    report += f"**情绪信号**: {signal}\n\n"
    report += f"**情绪分布**:\n"
    report += f"  - 😊 看多: {dist.get('positive', 0)} 条 ({sentiment.get('positive_ratio', 0) * 100:.1f}%)\n"
    report += f"  - 😐 中性: {dist.get('neutral', 0)} 条 ({sentiment.get('neutral_ratio', 0) * 100:.1f}%)\n"
    report += f"  - 😟 看空: {dist.get('negative', 0)} 条 ({sentiment.get('negative_ratio', 0) * 100:.1f}%)\n\n"

    # 互动数据
    report += f"**互动数据**:\n"
    report += f"  - 平均阅读: {sentiment.get('avg_read_count', 0):.0f}\n"
    report += f"  - 平均回复: {sentiment.get('avg_reply_count', 0):.1f}\n\n"

    # 看多/看空关键词
    bullish_kw = sentiment.get("bullish_keywords", [])
    bearish_kw = sentiment.get("bearish_keywords", [])
    if bullish_kw:
        report += f"**看多关键词**: {'、'.join(bullish_kw)}\n"
    if bearish_kw:
        report += f"**看空关键词**: {'、'.join(bearish_kw)}\n"

    report += "\n"

    # 热门帖子
    hot_posts = sentiment.get("hot_posts", [])
    if hot_posts:
        report += "**🔥 热门帖子**:\n"
        for i, post in enumerate(hot_posts, 1):
            sentiment_emoji = {"positive": "😊", "negative": "😟", "neutral": "😐"}.get(
                post.get("sentiment", "neutral"), "😐"
            )
            report += (
                f"  {i}. {sentiment_emoji} {post.get('title', '无标题')[:60]}\n"
                f"     👤 {post.get('author', '匿名')} | "
                f"👁️ {post.get('read_count', 0)} | "
                f"💬 {post.get('reply_count', 0)} | "
                f"🕐 {post.get('publish_time', '')}\n"
            )
        report += "\n"

    # 最新帖子
    recent_posts = sentiment.get("recent_posts", [])
    if recent_posts:
        report += "**📰 最新帖子**:\n"
        for i, post in enumerate(recent_posts, 1):
            sentiment_emoji = {"positive": "😊", "negative": "😟", "neutral": "😐"}.get(
                post.get("sentiment", "neutral"), "😐"
            )
            report += (
                f"  {i}. {sentiment_emoji} {post.get('title', '无标题')[:60]}\n"
                f"     👤 {post.get('author', '匿名')} | 🕐 {post.get('publish_time', '')}\n"
            )

    report += f"\n---\n*数据来源: 东方财富股吧 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"

    return report
