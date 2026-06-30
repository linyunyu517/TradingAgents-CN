#!/usr/bin/env python3
"""
实时新闻数据获取工具
解决新闻滞后性问题
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tradingagents.config.runtime_settings import get_timezone_name
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")


@dataclass
class NewsItem:
    """新闻项目数据结构"""

    title: str
    content: str
    source: str
    publish_time: datetime
    url: str
    urgency: str  # high, medium, low
    relevance_score: float


class RealtimeNewsAggregator:
    """实时新闻聚合器"""

    def __init__(self):
        self.headers = {"User-Agent": "TradingAgents-CN/1.0"}

    def get_realtime_stock_news(self, ticker: str, hours_back: int = 6, max_news: int = 10) -> list[NewsItem]:
        """
        获取实时股票新闻
        使用企业级反爬虫新闻系统（东方财富 + 新浪财经 + 雪球）

        Args:
            ticker: 股票代码
            hours_back: 回溯小时数
            max_news: 最大新闻数量，默认10条
        """
        logger.info(f"[新闻聚合器] 开始获取 {ticker} 的实时新闻，回溯时间: {hours_back}小时")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))
        all_news = []

        # 1. 中文财经新闻源（东方财富 > 新浪财经 > 雪球）
        logger.info(f"[新闻聚合器] 尝试获取 {ticker} 的中文财经新闻")
        chinese_start = datetime.now(ZoneInfo(get_timezone_name()))
        chinese_news = self._get_chinese_finance_news(ticker, hours_back)
        chinese_time = (datetime.now(ZoneInfo(get_timezone_name())) - chinese_start).total_seconds()

        if chinese_news:
            logger.info(f"[新闻聚合器] 成功获取 {len(chinese_news)} 条中文财经新闻，耗时: {chinese_time:.2f}秒")
        else:
            logger.info(f"[新闻聚合器] 未获取到中文财经新闻，耗时: {chinese_time:.2f}秒")

        all_news.extend(chinese_news)

        # 去重和排序
        logger.info(f"[新闻聚合器] 开始对 {len(all_news)} 条新闻进行去重和排序")
        dedup_start = datetime.now(ZoneInfo(get_timezone_name()))
        unique_news = self._deduplicate_news(all_news)
        sorted_news = sorted(unique_news, key=lambda x: x.publish_time, reverse=True)
        dedup_time = (datetime.now(ZoneInfo(get_timezone_name())) - dedup_start).total_seconds()

        # 记录去重结果
        removed_count = len(all_news) - len(unique_news)
        logger.info(
            f"[新闻聚合器] 新闻去重完成，移除了 {removed_count} 条重复新闻，剩余 {len(sorted_news)} 条，耗时: {dedup_time:.2f}秒",
        )

        # 记录总体情况
        total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
        logger.info(
            f"[新闻聚合器] {ticker} 的新闻聚合完成，总共获取 {len(sorted_news)} 条新闻，总耗时: {total_time:.2f}秒",
        )

        # 限制新闻数量为最新的max_news条
        if len(sorted_news) > max_news:
            original_count = len(sorted_news)
            sorted_news = sorted_news[:max_news]
            logger.info(f"[新闻聚合器] 📰 新闻数量限制: 从{original_count}条限制为{max_news}条最新新闻")

        # 记录一些新闻标题示例
        if sorted_news:
            sample_titles = [item.title for item in sorted_news[:3]]
            logger.info(f"[新闻聚合器] 新闻标题示例: {', '.join(sample_titles)}")

        return sorted_news

    def _get_chinese_finance_news(self, ticker: str, hours_back: int) -> list[NewsItem]:
        """获取中文财经新闻（东方财富 > 新浪财经 > 雪球）"""
        logger.info(f"[中文财经新闻] 开始获取 {ticker} 的中文财经新闻，回溯时间: {hours_back}小时")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        try:
            from .news_source_manager import get_news
            raw_news = get_news(ticker, max_news=10)
        except Exception as e:
            logger.error(f"[中文财经新闻] 企业级新闻系统获取失败: {e}")
            return []

        if not raw_news:
            logger.info("[中文财经新闻] 企业级新闻系统未返回数据")
            return []

        news_items = []
        for item in raw_news:
            title = item.get("title", "")
            content = item.get("content", "") or item.get("summary", "")
            source = item.get("source", "") or item.get("media_name", "")
            url = item.get("url", "")
            pub_time_str = item.get("publish_time", "")
            try:
                publish_time = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=ZoneInfo(get_timezone_name()),
                )
            except Exception:
                publish_time = datetime.now(ZoneInfo(get_timezone_name()))

            if publish_time < datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=hours_back + 24):
                pass

            urgency = self._assess_news_urgency(title, content)
            news_items.append(
                NewsItem(
                    title=title,
                    content=content[:500],
                    source=source,
                    publish_time=publish_time,
                    url=url,
                    urgency=urgency,
                    relevance_score=self._calculate_relevance(title, ticker),
                ),
            )

        total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
        logger.info(
            f"[中文财经新闻] {ticker} 的中文财经新闻获取完成，共 {len(news_items)} 条，耗时: {total_time:.2f}秒",
        )
        return news_items

    def _assess_news_urgency(self, title: str, content: str) -> str:
        """评估新闻紧急程度"""
        text = (title + " " + content).lower()

        # 高紧急度关键词
        high_urgency_keywords = [
            "breaking",
            "urgent",
            "alert",
            "emergency",
            "halt",
            "suspend",
            "突发",
            "紧急",
            "暂停",
            "停牌",
            "重大",
        ]

        # 中等紧急度关键词
        medium_urgency_keywords = [
            "earnings",
            "report",
            "announce",
            "launch",
            "merger",
            "acquisition",
            "财报",
            "发布",
            "宣布",
            "并购",
            "收购",
        ]

        # 检查高紧急度关键词
        for keyword in high_urgency_keywords:
            if keyword in text:
                logger.debug(f"[紧急度评估] 检测到高紧急度关键词 '{keyword}' 在新闻中: {title[:50]}...")
                return "high"

        # 检查中等紧急度关键词
        for keyword in medium_urgency_keywords:
            if keyword in text:
                logger.debug(f"[紧急度评估] 检测到中等紧急度关键词 '{keyword}' 在新闻中: {title[:50]}...")
                return "medium"

        logger.debug(f"[紧急度评估] 未检测到紧急关键词，评估为低紧急度: {title[:50]}...")
        return "low"

    def _calculate_relevance(self, title: str, ticker: str) -> float:
        """计算新闻相关性分数"""
        text = title.lower()
        ticker_lower = ticker.lower()

        # 基础相关性 - 股票代码直接出现在标题中
        if ticker_lower in text:
            logger.debug(f"[相关性计算] 股票代码 {ticker} 直接出现在标题中，相关性评分: 1.0，标题: {title[:50]}...")
            return 1.0

        # 公司名称匹配
        company_names = {
            "aapl": ["apple", "iphone", "ipad", "mac"],
            "tsla": ["tesla", "elon musk", "electric vehicle"],
            "nvda": ["nvidia", "gpu", "ai chip"],
            "msft": ["microsoft", "windows", "azure"],
            "googl": ["google", "alphabet", "search"],
        }

        # 检查公司相关关键词
        if ticker_lower in company_names:
            for name in company_names[ticker_lower]:
                if name in text:
                    logger.debug(
                        f"[相关性计算] 检测到公司相关关键词 '{name}' 在标题中，相关性评分: 0.8，标题: {title[:50]}...",
                    )
                    return 0.8

        # 提取股票代码的纯数字部分（适用于中国股票）
        pure_code = "".join(filter(str.isdigit, ticker))
        if pure_code and pure_code in text:
            logger.debug(
                f"[相关性计算] 股票代码数字部分 {pure_code} 出现在标题中，相关性评分: 0.9，标题: {title[:50]}...",
            )
            return 0.9

        logger.debug(f"[相关性计算] 未检测到明确相关性，使用默认评分: 0.3，标题: {title[:50]}...")
        return 0.3  # 默认相关性

    def _deduplicate_news(self, news_items: list[NewsItem]) -> list[NewsItem]:
        """去重新闻"""
        logger.info(f"[新闻去重] 开始对 {len(news_items)} 条新闻进行去重处理")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        seen_titles = set()
        unique_news = []
        duplicate_count = 0
        short_title_count = 0

        for item in news_items:
            # 简单的标题去重
            title_key = item.title.lower().strip()

            # 检查标题长度
            if len(title_key) <= 10:
                logger.debug(f"[新闻去重] 跳过标题过短的新闻: '{item.title}'，来源: {item.source}")
                short_title_count += 1
                continue

            # 检查是否重复
            if title_key in seen_titles:
                logger.debug(f"[新闻去重] 检测到重复新闻: '{item.title[:50]}...'，来源: {item.source}")
                duplicate_count += 1
                continue

            # 添加到结果集
            seen_titles.add(title_key)
            unique_news.append(item)

        # 记录去重结果
        time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
        logger.info(f"[新闻去重] 去重完成，原始新闻: {len(news_items)}条，去重后: {len(unique_news)}条，")
        logger.info(
            f"[新闻去重] 去除重复: {duplicate_count}条，标题过短: {short_title_count}条，耗时: {time_taken:.2f}秒",
        )

        return unique_news

    def format_news_report(self, news_items: list[NewsItem], ticker: str) -> str:
        """格式化新闻报告"""
        logger.info(f"[新闻报告] 开始为 {ticker} 生成新闻报告")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        if not news_items:
            logger.warning(f"[新闻报告] 未获取到 {ticker} 的实时新闻数据")
            return f"未获取到{ticker}的实时新闻数据。"

        # 按紧急程度分组
        high_urgency = [n for n in news_items if n.urgency == "high"]
        medium_urgency = [n for n in news_items if n.urgency == "medium"]
        low_urgency = [n for n in news_items if n.urgency == "low"]

        # 记录新闻分类情况
        logger.info(
            f"[新闻报告] {ticker} 新闻分类统计: 高紧急度 {len(high_urgency)}条, 中紧急度 {len(medium_urgency)}条, 低紧急度 {len(low_urgency)}条",
        )

        # 记录新闻来源分布
        news_sources = {}
        for item in news_items:
            source = item.source
            if source in news_sources:
                news_sources[source] += 1
            else:
                news_sources[source] = 1

        sources_info = ", ".join([f"{source}: {count}条" for source, count in news_sources.items()])
        logger.info(f"[新闻报告] {ticker} 新闻来源分布: {sources_info}")

        report = f"# {ticker} 实时新闻分析报告\n\n"
        report += f"📅 生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"📊 新闻总数: {len(news_items)}条\n\n"

        if high_urgency:
            report += "## 🚨 紧急新闻\n\n"
            for news in high_urgency[:3]:  # 最多显示3条
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"{news.content}\n\n"

        if medium_urgency:
            report += "## 📢 重要新闻\n\n"
            for news in medium_urgency[:5]:  # 最多显示5条
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"{news.content}\n\n"

        # 添加时效性说明
        latest_news = max(news_items, key=lambda x: x.publish_time)
        time_diff = datetime.now(ZoneInfo(get_timezone_name())) - latest_news.publish_time

        report += "\n## ⏰ 数据时效性\n"
        report += f"最新新闻发布于: {time_diff.total_seconds() / 60:.0f}分钟前\n"

        if time_diff.total_seconds() < 1800:  # 30分钟内
            report += "🟢 数据时效性: 优秀 (30分钟内)\n"
        elif time_diff.total_seconds() < 3600:  # 1小时内
            report += "🟡 数据时效性: 良好 (1小时内)\n"
        else:
            report += "🔴 数据时效性: 一般 (超过1小时)\n"

        # 记录报告生成完成信息
        end_time = datetime.now(ZoneInfo(get_timezone_name()))
        time_taken = (end_time - start_time).total_seconds()
        report_length = len(report)

        logger.info(f"[新闻报告] {ticker} 新闻报告生成完成，耗时: {time_taken:.2f}秒，报告长度: {report_length}字符")

        # 记录时效性信息
        time_diff_minutes = time_diff.total_seconds() / 60
        logger.info(f"[新闻报告] {ticker} 新闻时效性: 最新新闻发布于 {time_diff_minutes:.1f}分钟前")

        return report


def get_realtime_stock_news(ticker: str, curr_date: str, hours_back: int = 6) -> str:
    """
    获取实时股票新闻的主要接口函数
    """
    logger.info("[新闻分析] ========== 函数入口 ==========")
    logger.info("[新闻分析] 函数: get_realtime_stock_news")
    logger.info(f"[新闻分析] 参数: ticker={ticker}, curr_date={curr_date}, hours_back={hours_back}")
    logger.info(f"[新闻分析] 开始获取 {ticker} 的实时新闻，日期: {curr_date}, 回溯时间: {hours_back}小时")
    start_total_time = datetime.now(ZoneInfo(get_timezone_name()))
    logger.info(f"[新闻分析] 开始时间: {start_total_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

    # 判断股票类型
    logger.info("[新闻分析] ========== 步骤1: 股票类型判断 ==========")
    stock_type = "未知"
    is_china_stock = False
    logger.info(f"[新闻分析] 原始ticker: {ticker}")

    if "." in ticker:
        logger.info("[新闻分析] 检测到ticker包含点号，进行后缀匹配")
        if any(suffix in ticker for suffix in [".SH", ".SZ", ".SS", ".XSHE", ".XSHG"]):
            stock_type = "A股"
            is_china_stock = True
            logger.info(f"[新闻分析] 匹配到A股后缀，股票类型: {stock_type}")
        elif ".HK" in ticker:
            stock_type = "港股"
            logger.info(f"[新闻分析] 匹配到港股后缀，股票类型: {stock_type}")
        elif any(suffix in ticker for suffix in [".US", ".N", ".O", ".NYSE", ".NASDAQ"]):
            stock_type = "美股"
            logger.info(f"[新闻分析] 匹配到美股后缀，股票类型: {stock_type}")
        else:
            logger.info("[新闻分析] 未匹配到已知后缀")
    else:
        logger.info("[新闻分析] ticker不包含点号，尝试使用StockUtils判断")
        # 尝试使用StockUtils判断股票类型
        try:
            from tradingagents.utils.stock_utils import StockUtils

            logger.info("[新闻分析] 成功导入StockUtils，开始判断股票类型")
            market_info = StockUtils.get_market_info(ticker)
            logger.info(f"[新闻分析] StockUtils返回市场信息: {market_info}")
            if market_info["is_china"]:
                stock_type = "A股"
                is_china_stock = True
                logger.info("[新闻分析] StockUtils判断为A股")
            elif market_info["is_hk"]:
                stock_type = "港股"
                logger.info("[新闻分析] StockUtils判断为港股")
            elif market_info["is_us"]:
                stock_type = "美股"
                logger.info("[新闻分析] StockUtils判断为美股")
        except Exception as e:
            logger.warning(f"[新闻分析] 使用StockUtils判断股票类型失败: {e}")

    logger.info(f"[新闻分析] 最终判断结果 - 股票 {ticker} 类型: {stock_type}, 是否A股: {is_china_stock}")

    # 对于A股，优先使用企业级反爬虫新闻系统
    if is_china_stock:
        logger.info("[新闻分析] ========== 步骤2: 企业级反爬虫新闻系统 ==========")
        logger.info(f"[新闻分析] 检测到A股股票 {ticker}，使用反爬虫新闻系统获取")
        try:
            from .news_source_manager import get_news_report

            report = get_news_report(ticker, max_news=10)
            if report and len(report.strip()) > 100:
                total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
                logger.info(
                    f"[新闻分析] ✅ 反爬虫新闻系统成功获取 {ticker} 新闻，"
                    f"长度 {len(report)} 字符，耗时 {total_time:.2f} 秒"
                )
                return report
            logger.warning(f"[新闻分析] ⚠️ 反爬虫新闻系统未获取到数据，降级到实时新闻聚合器")
        except Exception as e:
            logger.warning(f"[新闻分析] ⚠️ 反爬虫新闻系统异常: {e}，降级到实时新闻聚合器")
    else:
        logger.info("[新闻分析] ========== 跳过A股东方财富新闻获取 ==========")
        logger.info(f"[新闻分析] 股票类型为 {stock_type}，不是A股，跳过东方财富新闻源")

    # 如果不是A股或A股新闻获取失败，使用实时新闻聚合器
    logger.info("[新闻分析] ========== 步骤3: 实时新闻聚合器 ==========")
    aggregator = RealtimeNewsAggregator()
    logger.info("[新闻分析] 成功创建实时新闻聚合器实例")
    try:
        logger.info(f"[新闻分析] 尝试使用实时新闻聚合器获取 {ticker} 的新闻")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))
        logger.info(f"[新闻分析] 聚合器调用开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

        # 获取实时新闻
        news_items = aggregator.get_realtime_stock_news(ticker, hours_back, max_news=10)

        end_time = datetime.now(ZoneInfo(get_timezone_name()))
        time_taken = (end_time - start_time).total_seconds()
        logger.info(f"[新闻分析] 聚合器调用结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logger.info(f"[新闻分析] 聚合器调用耗时: {time_taken:.2f}秒")
        logger.info(f"[新闻分析] 聚合器返回数据类型: {type(news_items)}")
        logger.info(f"[新闻分析] 聚合器返回数据: {news_items}")

        # 如果成功获取到新闻
        if news_items and len(news_items) > 0:
            news_count = len(news_items)
            logger.info(f"[新闻分析] 实时新闻聚合器成功获取 {news_count} 条 {ticker} 的新闻，耗时 {time_taken:.2f} 秒")

            # 记录一些新闻标题示例
            sample_titles = [item.title for item in news_items[:3]]
            logger.info(f"[新闻分析] 新闻标题示例: {', '.join(sample_titles)}")

            # 格式化报告
            logger.info("[新闻分析] 开始格式化新闻报告")
            report = aggregator.format_news_report(news_items, ticker)
            logger.info(f"[新闻分析] 报告格式化完成，长度: {len(report)} 字符")

            total_time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
            logger.info(
                f"[新闻分析] 成功生成 {ticker} 的新闻报告，总耗时 {total_time_taken:.2f} 秒，新闻来源: 实时新闻聚合器",
            )
            logger.info("[新闻分析] ========== 实时新闻聚合器获取成功，函数即将返回 ==========")
            return report
        logger.warning(
            f"[新闻分析] 实时新闻聚合器未获取到 {ticker} 的新闻，耗时 {time_taken:.2f} 秒，尝试使用备用新闻源",
        )
            # 如果没有获取到新闻，继续尝试备用方案
    except Exception as e:
        logger.error(f"[新闻分析] 实时新闻聚合器获取失败: {e}，将尝试备用新闻源")
        logger.error(f"[新闻分析] 异常详情: {type(e).__name__}: {e!s}")
        import traceback

        logger.error(f"[新闻分析] 异常堆栈: {traceback.format_exc()}")
        # 发生异常时，继续尝试备用方案

    # 备用方案1: 对于港股，使用反爬虫新闻系统获取
    if not is_china_stock and ".HK" in ticker:
        logger.info(f"[新闻分析] 检测到港股代码 {ticker}，使用反爬虫新闻系统获取")
        try:
            from .news_source_manager import get_news_report

            report = get_news_report(ticker, max_news=10)
            if report and len(report.strip()) > 100:
                total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
                logger.info(
                    f"[新闻分析] ✅ 反爬虫新闻系统成功获取港股 {ticker} 新闻，"
                    f"长度 {len(report)} 字符，耗时 {total_time:.2f} 秒"
                )
                return report
        except Exception as e:
            logger.warning(f"[新闻分析] ⚠️ 港股反爬虫新闻系统异常: {e}")

    # 备用方案2: 对于非A股，尝试使用反爬虫新闻系统
    try:
        from .news_source_manager import get_news_report

        report = get_news_report(ticker, max_news=10)
        if report and len(report.strip()) > 100:
            total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
            logger.info(
                f"[新闻分析] ✅ 反爬虫新闻系统成功获取 {ticker} 新闻，"
                f"长度 {len(report)} 字符，耗时 {total_time:.2f} 秒"
            )
            return report
    except Exception as e:
        logger.warning(f"[新闻分析] ⚠️ 反爬虫新闻系统异常: {e}")

    # 所有方法都失败，返回错误信息
    total_time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
    logger.error(f"[新闻分析] {ticker} 的所有新闻获取方法均已失败，总耗时 {total_time_taken:.2f} 秒")

    return f"""
实时新闻获取失败 - {ticker}
分析日期: {curr_date}

❌ 错误信息: 所有可用的新闻源都未能获取到相关新闻

💡 备用建议:
1. 检查网络连接
2. 使用基础新闻分析作为备选
3. 关注官方财经媒体的最新报道

注: 实时新闻获取依赖外部API服务的可用性。
"""
