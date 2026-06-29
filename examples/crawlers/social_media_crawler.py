#!/usr/bin/env python3
"""
社媒消息爬虫示例程序
演示如何爬取社交媒体数据并入库到消息数据系统
"""

import asyncio
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import aiohttp

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import init_db
from app.services.social_media_service import get_social_media_service

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SocialMediaCrawler:
    """社媒消息爬虫基类"""

    def __init__(self, platform: str):
        self.platform = platform
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{platform}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()

    def clean_content(self, text: str) -> str:
        """清洗文本内容"""
        if not text:
            return ""

        # 移除HTML标签
        text = re.sub(r"<[^>]+>", "", text)
        # 移除多余空白字符
        text = re.sub(r"\s+", " ", text).strip()
        # 移除特殊字符
        text = re.sub(r"[^\w\s\u4e00-\u9fff#@.,!?()（）。，！？]", "", text)

        return text

    def extract_hashtags(self, text: str) -> list[str]:
        """提取话题标签"""
        hashtags = re.findall(r"#([^#\s]+)#?", text)
        return list(set(hashtags))[:10]  # 最多10个标签

    def extract_mentions(self, text: str) -> list[str]:
        """提取@用户"""
        mentions = re.findall(r"@([^\s@]+)", text)
        return list(set(mentions))[:5]  # 最多5个提及

    def analyze_sentiment(self, text: str) -> tuple:
        """简单情绪分析"""
        positive_keywords = ["利好", "上涨", "增长", "盈利", "突破", "创新高", "买入", "推荐", "看好", "牛市"]
        negative_keywords = ["利空", "下跌", "亏损", "风险", "暴跌", "卖出", "警告", "下调", "看空", "熊市"]

        text_lower = text.lower()
        positive_count = sum(1 for keyword in positive_keywords if keyword in text_lower)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text_lower)

        if positive_count > negative_count:
            sentiment = "positive"
            score = min(0.9, 0.5 + (positive_count - negative_count) * 0.1)
        elif negative_count > positive_count:
            sentiment = "negative"
            score = max(-0.9, -0.5 - (negative_count - positive_count) * 0.1)
        else:
            sentiment = "neutral"
            score = 0.0

        return sentiment, score

    def extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        # 简单的关键词提取（实际应用中可使用jieba等工具）
        common_keywords = [
            "股票",
            "股价",
            "涨停",
            "跌停",
            "买入",
            "卖出",
            "持有",
            "业绩",
            "财报",
            "分红",
            "重组",
            "并购",
            "IPO",
            "牛市",
            "熊市",
            "反弹",
            "调整",
            "突破",
            "支撑",
            "压力",
            "基本面",
            "技术面",
            "消息面",
            "政策",
            "监管",
        ]

        keywords = []
        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)

        return keywords[:8]  # 最多8个关键词

    def assess_importance(self, engagement: dict[str, Any], author_influence: float) -> str:
        """评估消息重要性"""
        engagement_rate = engagement.get("engagement_rate", 0)
        views = engagement.get("views", 0)

        # 综合评分
        score = engagement_rate * 0.4 + author_influence * 0.4 + min(views / 10000, 1) * 0.2

        if score >= 0.7:
            return "high"
        if score >= 0.4:
            return "medium"
        return "low"

    def assess_credibility(self, author: dict[str, Any], content: str) -> str:
        """评估消息可信度"""
        verified = author.get("verified", False)
        follower_count = author.get("follower_count", 0)

        # 基础可信度
        if verified and follower_count > 100000:
            base_credibility = "high"
        elif verified or follower_count > 10000:
            base_credibility = "medium"
        else:
            base_credibility = "low"

        # 内容质量调整
        if len(content) > 100 and not re.search(r"[!]{3,}|[?]{3,}", content):
            return base_credibility
        # 降低一级
        if base_credibility == "high":
            return "medium"
        if base_credibility == "medium":
            return "low"
        return "low"


class WeiboCrawler(SocialMediaCrawler):
    """微博爬虫"""

    def __init__(self):
        super().__init__("weibo")
        self.base_url = "https://m.weibo.cn/api"

    async def crawl_stock_messages(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """爬取股票相关微博消息"""
        self.logger.info(f"🕷️ 开始爬取微博消息: {symbol}")

        try:
            # 模拟API调用（实际需要根据微博API文档实现）
            messages = await self._simulate_weibo_api(symbol, limit)

            # 数据标准化
            standardized_messages = []
            for msg in messages:
                standardized_msg = await self._standardize_weibo_message(msg, symbol)
                if standardized_msg:
                    standardized_messages.append(standardized_msg)

            self.logger.info(f"✅ 微博消息爬取完成: {len(standardized_messages)} 条")
            return standardized_messages

        except Exception as e:
            self.logger.error(f"❌ 微博消息爬取失败: {e}")
            return []

    async def _simulate_weibo_api(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        """模拟微博API响应（实际应用中替换为真实API调用）"""
        # 模拟数据
        mock_messages = []

        for i in range(min(limit, 20)):  # 模拟最多20条
            mock_msg = {
                "id": f"weibo_{symbol}_{int(time.time())}_{i}",
                "text": self._generate_mock_weibo_text(symbol, i),
                "created_at": (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(),
                "user": {
                    "id": f"user_{random.randint(1000, 9999)}",
                    "screen_name": f"股民{random.randint(100, 999)}",
                    "verified": random.choice([True, False]),
                    "followers_count": random.randint(100, 100000),
                    "location": random.choice(["北京", "上海", "深圳", "广州", "杭州"]),
                },
                "reposts_count": random.randint(0, 100),
                "comments_count": random.randint(0, 200),
                "attitudes_count": random.randint(10, 500),
            }
            mock_messages.append(mock_msg)

            # 模拟API限流
            await asyncio.sleep(0.1)

        return mock_messages

    def _generate_mock_weibo_text(self, symbol: str, index: int) -> str:
        """生成模拟微博文本"""
        templates = [
            f"{symbol}今天表现不错，看好后续走势！#股票# #投资#",
            f"关注{symbol}的基本面变化，业绩预期良好 #价值投资#",
            f"{symbol}技术面突破，成交量放大，值得关注 #技术分析#",
            f"持有{symbol}一段时间了，分红不错，长期看好 #长线投资#",
            f"{symbol}最新消息：公司发布重要公告，利好消息 #利好#",
        ]

        return random.choice(templates)

    async def _standardize_weibo_message(self, raw_msg: dict[str, Any], symbol: str) -> dict[str, Any] | None:
        """标准化微博消息数据"""
        try:
            content = self.clean_content(raw_msg.get("text", ""))
            if not content:
                return None

            # 解析用户信息
            user = raw_msg.get("user", {})
            author = {
                "user_id": str(user.get("id", "")),
                "username": user.get("screen_name", ""),
                "display_name": user.get("screen_name", ""),
                "verified": user.get("verified", False),
                "follower_count": user.get("followers_count", 0),
                "influence_score": min(1.0, user.get("followers_count", 0) / 100000),
            }

            # 计算互动数据
            reposts = raw_msg.get("reposts_count", 0)
            comments = raw_msg.get("comments_count", 0)
            likes = raw_msg.get("attitudes_count", 0)
            views = likes * 10  # 估算浏览量

            engagement = {
                "likes": likes,
                "shares": reposts,
                "comments": comments,
                "views": views,
                "engagement_rate": (likes + reposts + comments) / max(views, 1),
            }

            # 情绪分析
            sentiment, sentiment_score = self.analyze_sentiment(content)

            # 提取标签和关键词
            hashtags = self.extract_hashtags(content)
            keywords = self.extract_keywords(content)

            # 评估重要性和可信度
            importance = self.assess_importance(engagement, author["influence_score"])
            credibility = self.assess_credibility(author, content)

            # 解析发布时间
            publish_time = datetime.fromisoformat(raw_msg.get("created_at", "").replace("Z", "+00:00"))

            return {
                "message_id": raw_msg.get("id"),
                "platform": "weibo",
                "message_type": "post",
                "content": content,
                "media_urls": [],
                "hashtags": hashtags,
                "author": author,
                "engagement": engagement,
                "publish_time": publish_time,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "confidence": 0.8,  # 分析置信度
                "keywords": keywords,
                "topics": ["股票讨论", "投资观点"],
                "importance": importance,
                "credibility": credibility,
                "location": {"country": "CN", "province": "", "city": user.get("location", "")},
                "data_source": "crawler_weibo",
                "crawler_version": "1.0",
                "symbol": symbol,
            }

        except Exception as e:
            self.logger.error(f"❌ 微博消息标准化失败: {e}")
            return None


class DouyinCrawler(SocialMediaCrawler):
    """抖音爬虫"""

    def __init__(self):
        super().__init__("douyin")

    async def crawl_stock_messages(self, symbol: str, limit: int = 30) -> list[dict[str, Any]]:
        """爬取股票相关抖音消息"""
        self.logger.info(f"🕷️ 开始爬取抖音消息: {symbol}")

        try:
            # 模拟抖音数据
            messages = await self._simulate_douyin_api(symbol, limit)

            # 数据标准化
            standardized_messages = []
            for msg in messages:
                standardized_msg = await self._standardize_douyin_message(msg, symbol)
                if standardized_msg:
                    standardized_messages.append(standardized_msg)

            self.logger.info(f"✅ 抖音消息爬取完成: {len(standardized_messages)} 条")
            return standardized_messages

        except Exception as e:
            self.logger.error(f"❌ 抖音消息爬取失败: {e}")
            return []

    async def _simulate_douyin_api(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        """模拟抖音API响应"""
        mock_messages = []

        for i in range(min(limit, 15)):
            mock_msg = {
                "aweme_id": f"douyin_{symbol}_{int(time.time())}_{i}",
                "desc": self._generate_mock_douyin_text(symbol, i),
                "create_time": int((datetime.now() - timedelta(hours=random.randint(1, 72))).timestamp()),
                "author": {
                    "uid": f"dy_user_{random.randint(1000, 9999)}",
                    "nickname": f"财经达人{random.randint(100, 999)}",
                    "verification_type": random.choice([0, 1]),
                    "follower_count": random.randint(1000, 500000),
                    "city": random.choice(["北京", "上海", "深圳", "广州"]),
                },
                "statistics": {
                    "digg_count": random.randint(50, 2000),
                    "share_count": random.randint(10, 300),
                    "comment_count": random.randint(20, 500),
                    "play_count": random.randint(1000, 50000),
                },
                "video": {"play_addr": {"url_list": [f"https://example.com/video_{i}.mp4"]}},
            }
            mock_messages.append(mock_msg)
            await asyncio.sleep(0.1)

        return mock_messages

    def _generate_mock_douyin_text(self, symbol: str, index: int) -> str:
        """生成模拟抖音文本"""
        templates = [
            f"分析{symbol}的投资价值，这支股票值得关注！#股票分析 #投资理财",
            f"{symbol}最新财报解读，业绩超预期！#财报分析 #价值投资",
            f"技术分析{symbol}，突破关键阻力位 #技术分析 #股票",
            f"{symbol}行业前景分析，长期看好这个赛道 #行业分析",
            f"今日{symbol}涨停复盘，主力资金大幅流入 #涨停复盘",
        ]

        return random.choice(templates)

    async def _standardize_douyin_message(self, raw_msg: dict[str, Any], symbol: str) -> dict[str, Any] | None:
        """标准化抖音消息数据"""
        try:
            content = self.clean_content(raw_msg.get("desc", ""))
            if not content:
                return None

            # 解析用户信息
            author_info = raw_msg.get("author", {})
            author = {
                "user_id": str(author_info.get("uid", "")),
                "username": author_info.get("nickname", ""),
                "display_name": author_info.get("nickname", ""),
                "verified": author_info.get("verification_type", 0) > 0,
                "follower_count": author_info.get("follower_count", 0),
                "influence_score": min(1.0, author_info.get("follower_count", 0) / 500000),
            }

            # 解析互动数据
            stats = raw_msg.get("statistics", {})
            engagement = {
                "likes": stats.get("digg_count", 0),
                "shares": stats.get("share_count", 0),
                "comments": stats.get("comment_count", 0),
                "views": stats.get("play_count", 0),
                "engagement_rate": (
                    stats.get("digg_count", 0) + stats.get("share_count", 0) + stats.get("comment_count", 0)
                )
                / max(stats.get("play_count", 1), 1),
            }

            # 提取媒体URL
            video_info = raw_msg.get("video", {})
            media_urls = []
            if video_info and "play_addr" in video_info:
                url_list = video_info["play_addr"].get("url_list", [])
                if url_list:
                    media_urls = [url_list[0]]

            # 情绪分析和其他处理
            sentiment, sentiment_score = self.analyze_sentiment(content)
            hashtags = self.extract_hashtags(content)
            keywords = self.extract_keywords(content)
            importance = self.assess_importance(engagement, author["influence_score"])
            credibility = self.assess_credibility(author, content)

            # 时间转换
            publish_time = datetime.fromtimestamp(raw_msg.get("create_time", time.time()))

            return {
                "message_id": raw_msg.get("aweme_id"),
                "platform": "douyin",
                "message_type": "post",
                "content": content,
                "media_urls": media_urls,
                "hashtags": hashtags,
                "author": author,
                "engagement": engagement,
                "publish_time": publish_time,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "confidence": 0.75,
                "keywords": keywords,
                "topics": ["财经视频", "投资教育"],
                "importance": importance,
                "credibility": credibility,
                "location": {"country": "CN", "province": "", "city": author_info.get("city", "")},
                "data_source": "crawler_douyin",
                "crawler_version": "1.0",
                "symbol": symbol,
            }

        except Exception as e:
            self.logger.error(f"❌ 抖音消息标准化失败: {e}")
            return None


async def crawl_and_save_social_media(symbols: list[str], platforms: list[str] | None = None):
    """爬取并保存社媒消息"""
    if platforms is None:
        platforms = ["weibo", "douyin"]

    logger.info(f"🚀 开始爬取社媒消息: {symbols}, 平台: {platforms}")

    try:
        # 初始化数据库
        await init_db()

        # 获取服务
        service = await get_social_media_service()

        total_saved = 0

        for symbol in symbols:
            logger.info(f"📊 处理股票: {symbol}")

            for platform in platforms:
                try:
                    # 创建对应平台的爬虫
                    if platform == "weibo":
                        async with WeiboCrawler() as crawler:
                            messages = await crawler.crawl_stock_messages(symbol, limit=50)
                    elif platform == "douyin":
                        async with DouyinCrawler() as crawler:
                            messages = await crawler.crawl_stock_messages(symbol, limit=30)
                    else:
                        logger.warning(f"⚠️ 不支持的平台: {platform}")
                        continue

                    if messages:
                        # 保存到数据库
                        result = await service.save_social_media_messages(messages)
                        saved_count = result.get("saved", 0)
                        total_saved += saved_count

                        logger.info(f"✅ {platform} - {symbol}: 保存 {saved_count} 条消息")
                    else:
                        logger.warning(f"⚠️ {platform} - {symbol}: 未获取到消息")

                    # 平台间延迟
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"❌ {platform} - {symbol} 处理失败: {e}")
                    continue

            # 股票间延迟
            await asyncio.sleep(2)

        logger.info(f"🎉 社媒消息爬取完成! 总计保存: {total_saved} 条")
        return total_saved

    except Exception as e:
        logger.error(f"❌ 社媒消息爬取过程异常: {e}")
        return 0


async def main():
    """主函数"""
    # 测试股票列表
    test_symbols = ["000001", "000002", "600000"]

    # 测试平台列表
    test_platforms = ["weibo", "douyin"]

    logger.info("🕷️ 社媒消息爬虫示例程序启动")

    # 执行爬取
    saved_count = await crawl_and_save_social_media(test_symbols, test_platforms)

    logger.info("📊 爬取结果统计:")
    logger.info(f"   - 处理股票: {len(test_symbols)} 只")
    logger.info(f"   - 处理平台: {len(test_platforms)} 个")
    logger.info(f"   - 保存消息: {saved_count} 条")

    if saved_count > 0:
        logger.info("✅ 社媒消息爬虫运行成功!")
    else:
        logger.warning("⚠️ 未保存任何消息，请检查配置")


if __name__ == "__main__":
    asyncio.run(main())
