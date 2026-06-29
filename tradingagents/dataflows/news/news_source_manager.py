# -*- coding: utf-8 -*-
"""
统一新闻源管理器
企业级反爬虫新闻系统中枢：
  - 按市场类型路由到不同的提供者组合
  - A股：东方财富(主) → 新浪财经(备1) → 雪球(备2) → 空结果
  - 港股/美股：股票代码搜索 → 公司名称搜索 → 空结果
  - 自动去重、排序、格式化
  - 优雅降级：即使所有源都失败，也不会抛出异常
"""

import random
import re
import time
from datetime import datetime, timezone
from typing import Any

from tradingagents.utils.logging_manager import get_logger

from .providers import (
    fetch_eastmoney_news,
    fetch_eastmoney_news_multi,
    fetch_sina_news,
    fetch_xueqiu_news,
)

logger = get_logger("agents")


def _clean_stock_code(ticker: str) -> str:
    """移除股票代码后缀，返回纯数字代码"""
    return (
        ticker.replace(".SH", "").replace(".SZ", "").replace(".SS", "")
        .replace(".XSHE", "").replace(".XSHG", "").replace(".HK", "")
        .replace(".US", "").strip()
    )


def _is_a_stock(ticker: str) -> bool:
    """判断是否为 A 股"""
    code = _clean_stock_code(ticker)
    # A 股规则
    if code.startswith("6") or code.startswith("9") or code.startswith("0") or code.startswith("3") or code.startswith("2"):
        return True
    if ".SH" in ticker or ".SZ" in ticker or ".SS" in ticker or ".XSHE" in ticker or ".XSHG" in ticker:
        return True
    return False


def _is_hk_stock(ticker: str) -> bool:
    """判断是否为港股"""
    if ".HK" in ticker:
        return True
    code = _clean_stock_code(ticker)
    return code.startswith("0") and len(code) == 5


def _is_us_stock(ticker: str) -> bool:
    """判断是否为美股"""
    if ".US" in ticker:
        return True
    return False


def _deduplicate(news_list: list[dict]) -> list[dict]:
    """根据 URL 去重，保留时间最新的"""
    seen_urls = set()
    result = []
    for item in news_list:
        url = item.get("url", "")
        # 如果 URL 为空，用标题作为去重键
        key = url or item.get("title", "")
        if key and key not in seen_urls:
            seen_urls.add(key)
            result.append(item)
    return result


def _sort_by_time(news_list: list[dict], reverse: bool = True) -> list[dict]:
    """按发布时间排序"""
    def _parse_time(item):
        t = item.get("publish_time", "")
        if t:
            try:
                return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return datetime.min.replace(tzinfo=None)
    return sorted(news_list, key=_parse_time, reverse=reverse)


def _format_news_report(news_list: list[dict], ticker: str, source_label: str = "") -> str:
    """
    将新闻列表格式化为人类可读的报告字符串。

    Args:
        news_list: 标准格式新闻列表
        ticker: 股票代码
        source_label: 来源标签（如"东方财富+新浪财经+雪球"）

    Returns:
        str: 格式化的报告
    """
    if not news_list:
        return ""

    source_str = f"（来源: {source_label}）" if source_label else ""
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"📰 **{ticker} 实时新闻分析报告**\n"
    report += f"生成时间: {current_date} {source_str}\n\n"
    report += f"共获取 {len(news_list)} 条相关新闻:\n\n"
    report += "---\n\n"

    for i, item in enumerate(news_list, 1):
        title = item.get("title", "无标题")
        pub_time = item.get("publish_time", "未知时间")
        source = item.get("media_name", item.get("source", "未知来源"))
        url = item.get("url", "")

        report += f"**{i}. {title}**\n"
        report += f"   📅 {pub_time} | 🏷️ {source}\n"

        content = item.get("content", "")
        if content and len(content) > 10:
            # 取前 200 个字符作为摘要
            summary = content.replace("\n", " ").strip()[:200]
            report += f"   📝 {summary}...\n"

        if url:
            report += f"   🔗 {url}\n"

        report += "\n"

    report += "---\n"
    report += f"*报告由 TradingAgents-CN 新闻系统自动生成*\n"

    return report


def fetch_a_stock_news(ticker: str, max_news: int = 10) -> list[dict]:
    """
    获取 A 股新闻 — 三源故障转移。
    东方财富(主) → 新浪财经(备1) → 雪球(备2)

    Args:
        ticker: 股票代码
        max_news: 最大新闻数量

    Returns:
        list[dict]: 标准格式新闻列表（失败时返回空列表）
    """
    code = _clean_stock_code(ticker)
    combined: list[dict] = []

    # 源1: 东方财富（主源）
    try:
        logger.info(f"[新闻管理] 🔵 主源: 东方财富 {code}")
        news = fetch_eastmoney_news(code, page_size=max_news)
        if news:
            logger.info(f"[新闻管理] ✅ 东方财富 {len(news)} 条")
            combined.extend(news)
        else:
            logger.warning(f"[新闻管理] ⚠️ 东方财富无数据，切换备用源")
    except Exception as e:
        logger.warning(f"[新闻管理] ⚠️ 东方财富失败: {e}")

    # 源2: 新浪财经（备1）
    if len(combined) < max_news:
        try:
            logger.info(f"[新闻管理] 🟡 备用源1: 新浪财经 {code}")
            news = fetch_sina_news(code, page_size=max_news)
            if news:
                logger.info(f"[新闻管理] ✅ 新浪财经 {len(news)} 条")
                combined.extend(news)
            else:
                logger.warning(f"[新闻管理] ⚠️ 新浪财经无数据")
        except Exception as e:
            logger.warning(f"[新闻管理] ⚠️ 新浪财经失败: {e}")

    # 源3: 雪球（备2）— 仅当前两个源都结果较少时
    if len(combined) < max_news // 2:
        try:
            logger.info(f"[新闻管理] 🟠 备用源2: 雪球 {code}")
            news = fetch_xueqiu_news(code, page_size=max(3, max_news // 2))
            if news:
                logger.info(f"[新闻管理] ✅ 雪球 {len(news)} 条")
                combined.extend(news)
        except Exception as e:
            logger.warning(f"[新闻管理] ⚠️ 雪球失败: {e}")

    # 去重 + 排序 + 截断
    combined = _deduplicate(combined)
    combined = _sort_by_time(combined)

    source_labels = []
    has_em = any(n.get("source") == "东方财富" for n in combined)
    has_sina = any(n.get("source") == "新浪财经" for n in combined)
    has_xq = any(n.get("source") == "雪球" for n in combined)
    if has_em:
        source_labels.append("东方财富")
    if has_sina:
        source_labels.append("新浪财经")
    if has_xq:
        source_labels.append("雪球")

    logger.info(
        f"[新闻管理] 🎯 A股 {ticker} 汇总: {len(combined)} 条 "
        f"(来源: {'+'.join(source_labels) or '无'})"
    )
    return combined[:max_news]


def fetch_hk_stock_news(ticker: str, max_news: int = 10) -> list[dict]:
    """
    获取港股新闻 — 先东方财富搜索港股代码，再通用搜索。

    Args:
        ticker: 股票代码
        max_news: 最大新闻数量

    Returns:
        list[dict]: 标准格式新闻列表
    """
    code = _clean_stock_code(ticker)
    combined: list[dict] = []

    # 东方财富也支持港股新闻搜索
    try:
        logger.info(f"[新闻管理] 🔵 港股主源: 东方财富 {code}")
        news = fetch_eastmoney_news(code, page_size=max_news)
        if news:
            logger.info(f"[新闻管理] ✅ 东方财富(港股) {len(news)} 条")
            combined.extend(news)
    except Exception as e:
        logger.warning(f"[新闻管理] ⚠️ 东方财富(港股)失败: {e}")

    # 去重 + 排序 + 截断
    combined = _deduplicate(combined)
    combined = _sort_by_time(combined)

    return combined[:max_news]


def fetch_us_stock_news(ticker: str, max_news: int = 10) -> list[dict]:
    """
    获取美股新闻 — 通过东方财富英文搜索。
    注意：东方财富主要覆盖 A 股和港股，美股的覆盖有限。

    Args:
        ticker: 股票代码
        max_news: 最大新闻数量

    Returns:
        list[dict]: 标准格式新闻列表
    """
    code = _clean_stock_code(ticker)
    combined: list[dict] = []

    # 直接用代码名搜索
    try:
        logger.info(f"[新闻管理] 🔵 美股: 东方财富搜索 {code}")
        news = fetch_eastmoney_news(code, page_size=max_news)
        if news:
            logger.info(f"[新闻管理] ✅ 东方财富(美股) {len(news)} 条")
            combined.extend(news)
    except Exception as e:
        logger.warning(f"[新闻管理] ⚠️ 东方财富(美股)失败: {e}")

    combined = _deduplicate(combined)
    combined = _sort_by_time(combined)
    return combined[:max_news]


def get_news(ticker: str, company_name: str = "", max_news: int = 10) -> list[dict]:
    """
    根据股票类型自动选择新闻获取策略。

    这是系统唯一的新闻入口点：
      - A 股: 东方财富(主) → 新浪财经(备1) → 雪球(备2) → 空
      - 港股: 东方财富搜索 → 空
      - 美股: 东方财富搜索 → 空
      - 所有路径都优雅降级，永不抛异常

    Args:
        ticker: 股票代码
        company_name: 公司名称（用于辅助搜索）
        max_news: 最大新闻数量

    Returns:
        list[dict]: 标准格式新闻列表
    """
    stock_type = ""
    result: list[dict] = []

    if _is_a_stock(ticker):
        stock_type = "A股"
        result = fetch_a_stock_news(ticker, max_news)
        # 如果代码搜索结果较少，再用公司名称补搜
        if company_name and len(result) < max_news // 2:
            try:
                logger.info(f"[新闻管理] 公司名补搜: {company_name}")
                extra = fetch_eastmoney_news(company_name, page_size=max(3, max_news // 2))
                if extra:
                    combined = result + extra
                    combined = _deduplicate(combined)
                    combined = _sort_by_time(combined)
                    result = combined[:max_news]
                    logger.info(f"[新闻管理] ✅ 补搜后共 {len(result)} 条")
            except Exception as e:
                logger.warning(f"[新闻管理] ⚠️ 公司名补搜失败: {e}")

    elif _is_hk_stock(ticker):
        stock_type = "港股"
        result = fetch_hk_stock_news(ticker, max_news)
    elif _is_us_stock(ticker):
        stock_type = "美股"
        result = fetch_us_stock_news(ticker, max_news)
    else:
        # 未知类型，尝试通用搜索
        stock_type = "未知"
        try:
            result = fetch_eastmoney_news(_clean_stock_code(ticker), page_size=max_news)
            result = _deduplicate(result)
            result = _sort_by_time(result)
        except Exception:
            result = []

    logger.info(
        f"[新闻管理] 📊 {ticker} ({stock_type}) 最终获取 {len(result)} 条新闻"
    )
    return result


def get_news_report(ticker: str, company_name: str = "", max_news: int = 10) -> str:
    """
    获取新闻并格式化为报告字符串。
    这是给外部调用者的最上层接口。

    Args:
        ticker: 股票代码
        company_name: 公司名称
        max_news: 最大新闻数量

    Returns:
        str: 格式化报告，空字符串表示无新闻
    """
    news_list = get_news(ticker, company_name, max_news)
    if not news_list:
        return ""

    # 确定来源标签
    sources = set(n.get("source", "") for n in news_list if n.get("source"))
    source_label = "+".join(sorted(sources)) if sources else ""

    return _format_news_report(news_list, ticker, source_label)
