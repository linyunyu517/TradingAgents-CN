#!/usr/bin/env python3
"""
统一新闻分析工具
整合A股、港股、美股等不同市场的新闻获取逻辑到一个工具函数中
让大模型只需要调用一个工具就能获取所有类型股票的新闻数据
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class UnifiedNewsAnalyzer:
    """统一新闻分析器，整合所有新闻获取逻辑"""

    def __init__(self, toolkit):
        """初始化统一新闻分析器
        
        Args:
            toolkit: 包含各种新闻获取工具的工具包
        """
        self.toolkit = toolkit

    def get_stock_news_unified(self, stock_code: str, max_news: int = 10, model_info: str = "") -> str:
        """
        统一新闻获取接口
        根据股票代码自动识别股票类型并获取相应新闻
        
        Args:
            stock_code: 股票代码
            max_news: 最大新闻数量
            model_info: 当前使用的模型信息，用于特殊处理
            
        Returns:
            str: 格式化的新闻内容
        """
        logger.info(f"[统一新闻工具] 开始获取 {stock_code} 的新闻，模型: {model_info}")
        logger.info(f"[统一新闻工具] 🤖 当前模型信息: {model_info}")

        # 识别股票类型
        stock_type = self._identify_stock_type(stock_code)
        logger.info(f"[统一新闻工具] 股票类型: {stock_type}")

        # 根据股票类型调用相应的获取方法
        if stock_type == "A股":
            result = self._get_a_share_news(stock_code, max_news, model_info)
        elif stock_type == "港股":
            result = self._get_hk_share_news(stock_code, max_news, model_info)
        elif stock_type == "美股":
            result = self._get_us_share_news(stock_code, max_news, model_info)
        else:
            # 默认使用A股逻辑
            result = self._get_a_share_news(stock_code, max_news, model_info)

        # 🔍 添加详细的结果调试日志
        logger.info(f"[统一新闻工具] 📊 新闻获取完成，结果长度: {len(result)} 字符")
        logger.info(f"[统一新闻工具] 📋 返回结果预览 (前1000字符): {result[:1000]}")

        # 如果结果为空或过短，记录警告
        if not result or len(result.strip()) < 50:
            logger.warning("[统一新闻工具] ⚠️ 返回结果异常短或为空！")
            logger.warning(f"[统一新闻工具] 📝 完整结果内容: '{result}'")

        return result

    def _identify_stock_type(self, stock_code: str) -> str:
        """识别股票类型"""
        stock_code = stock_code.upper().strip()

        # A股判断
        if re.match(r"^(00|30|60|68)\d{4}$", stock_code) or re.match(r"^(SZ|SH)\d{6}$", stock_code):
            return "A股"

        # 港股判断
        if re.match(r"^\d{4,5}\.HK$", stock_code) or (re.match(r"^\d{4,5}$", stock_code) and len(stock_code) <= 5):
            return "港股"

        # 美股判断
        if re.match(r"^[A-Z]{1,5}$", stock_code) or ("." in stock_code and not stock_code.endswith(".HK")):
            return "美股"

        # 默认按A股处理
        return "A股"

    def _get_news_from_database(self, stock_code: str, max_news: int = 10) -> str:
        """
        从数据库获取新闻

        Args:
            stock_code: 股票代码
            max_news: 最大新闻数量

        Returns:
            str: 格式化的新闻内容，如果没有新闻则返回空字符串
        """
        try:
            from datetime import timedelta

            from tradingagents.dataflows.cache.app_adapter import get_mongodb_client

            # 🔧 确保 max_news 是整数（防止传入浮点数）
            max_news = int(max_news)

            client = get_mongodb_client()
            if not client:
                logger.warning("[统一新闻工具] 无法连接到MongoDB")
                return ""

            db = client.get_database("tradingagents")
            collection = db.stock_news

            # 标准化股票代码（去除后缀）
            clean_code = stock_code.replace(".SH", "").replace(".SZ", "").replace(".SS", "")\
                                   .replace(".XSHE", "").replace(".XSHG", "").replace(".HK", "")

            # 查询最近30天的新闻（扩大时间范围）
            thirty_days_ago = datetime.now() - timedelta(days=30)

            # 尝试多种查询方式（使用 symbol 字段）
            query_list = [
                {"symbol": clean_code, "publish_time": {"$gte": thirty_days_ago}},
                {"symbol": stock_code, "publish_time": {"$gte": thirty_days_ago}},
                {"symbols": clean_code, "publish_time": {"$gte": thirty_days_ago}},
                # 如果最近30天没有新闻，则查询所有新闻（不限时间）
                {"symbol": clean_code},
                {"symbols": clean_code},
            ]

            news_items = []
            for query in query_list:
                cursor = collection.find(query).sort("publish_time", -1).limit(max_news)
                news_items = list(cursor)
                if news_items:
                    logger.info(f"[统一新闻工具] 📊 使用查询 {query} 找到 {len(news_items)} 条新闻")
                    break

            if not news_items:
                logger.info(f"[统一新闻工具] 数据库中没有找到 {stock_code} 的新闻")
                return ""

            # 格式化新闻
            report = f"# {stock_code} 最新新闻 (数据库缓存)\n\n"
            report += f"📅 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report += f"📊 新闻数量: {len(news_items)} 条\n\n"

            for i, news in enumerate(news_items, 1):
                title = news.get("title", "无标题")
                content = news.get("content", "") or news.get("summary", "")
                source = news.get("source", "未知来源")
                publish_time = news.get("publish_time", datetime.now())
                sentiment = news.get("sentiment", "neutral")

                # 情绪图标
                sentiment_icon = {
                    "positive": "📈",
                    "negative": "📉",
                    "neutral": "➖",
                }.get(sentiment, "➖")

                report += f"## {i}. {sentiment_icon} {title}\n\n"
                report += f"**来源**: {source} | **时间**: {publish_time.strftime('%Y-%m-%d %H:%M') if isinstance(publish_time, datetime) else publish_time}\n"
                report += f"**情绪**: {sentiment}\n\n"

                if content:
                    # 限制内容长度
                    content_preview = content[:500] + "..." if len(content) > 500 else content
                    report += f"{content_preview}\n\n"

                report += "---\n\n"

            logger.info(f"[统一新闻工具] ✅ 成功从数据库获取并格式化 {len(news_items)} 条新闻")
            return report

        except Exception as e:
            logger.error(f"[统一新闻工具] 从数据库获取新闻失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

    def _sync_news_from_eastmoney(self, stock_code: str, max_news: int = 10) -> bool:
        """
        从东方财富同步新闻到数据库（同步方法）
        使用 curl_cffi TLS 指纹模拟的反爬虫方案

        Args:
            stock_code: 股票代码
            max_news: 最大新闻数量

        Returns:
            bool: 是否同步成功
        """
        try:
            # 标准化股票代码（去除后缀）
            clean_code = stock_code.replace(".SH", "").replace(".SZ", "").replace(".SS", "")\
                                   .replace(".XSHE", "").replace(".XSHG", "").replace(".HK", "")

            logger.info(f"[统一新闻工具] 🔄 开始同步 {clean_code} 的新闻（东方财富反爬虫方案）...")

            # 使用新的东方财富新闻提供者
            from tradingagents.dataflows.news.providers.eastmoney_provider import fetch_news

            news_data = fetch_news(clean_code, page_size=max_news)

            if not news_data:
                logger.warning("[统一新闻工具] ⚠️ 未获取到新闻数据")
                return False

            logger.info(f"[统一新闻工具] 📥 获取到 {len(news_data)} 条新闻")

            # 🔥 使用同步方法保存到数据库
            try:
                from app.services.news_data_service import NewsDataService

                news_service = NewsDataService()
                saved_count = news_service.save_news_data_sync(
                    news_data=news_data,
                    data_source="eastmoney",
                    market="CN",
                )
                logger.info(f"[统一新闻工具] ✅ 同步成功: {saved_count} 条新闻")
                return saved_count > 0
            except ImportError:
                logger.warning("[统一新闻工具] ⚠️ NewsDataService 不可用，跳过数据库保存")
                return len(news_data) > 0

        except Exception as e:
            logger.error(f"[统一新闻工具] ❌ 同步新闻失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_a_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取A股新闻"""
        logger.info(f"[统一新闻工具] 获取A股 {stock_code} 新闻")

        # 获取当前日期
        curr_date = datetime.now().strftime("%Y-%m-%d")

        # 优先级0: 从数据库获取新闻（最高优先级）
        try:
            logger.info(f"[统一新闻工具] 🔍 优先从数据库获取 {stock_code} 的新闻...")
            db_news = self._get_news_from_database(stock_code, max_news)
            if db_news:
                logger.info(f"[统一新闻工具] ✅ 数据库新闻获取成功: {len(db_news)} 字符")
                return self._format_news_result(db_news, "数据库缓存", model_info)
            logger.info(f"[统一新闻工具] ⚠️ 数据库中没有 {stock_code} 的新闻，尝试同步...")

            # 🔥 数据库没有数据时，调用同步服务同步新闻
            try:
                logger.info(f"[统一新闻工具] 📡 调用同步服务同步 {stock_code} 的新闻...")
                synced_news = self._sync_news_from_eastmoney(stock_code, max_news)

                if synced_news:
                    logger.info("[统一新闻工具] ✅ 同步成功，重新从数据库获取...")
                    # 重新从数据库获取
                    db_news = self._get_news_from_database(stock_code, max_news)
                    if db_news:
                        logger.info(f"[统一新闻工具] ✅ 同步后数据库新闻获取成功: {len(db_news)} 字符")
                        return self._format_news_result(db_news, "数据库缓存(新同步)", model_info)
                else:
                    logger.warning("[统一新闻工具] ⚠️ 同步服务未返回新闻数据")

            except Exception as sync_error:
                logger.warning(f"[统一新闻工具] ⚠️ 同步服务调用失败: {sync_error}")

            logger.info("[统一新闻工具] ⚠️ 同步后仍无数据，尝试其他数据源...")
        except Exception as e:
            logger.warning(f"[统一新闻工具] 数据库新闻获取失败: {e}")

        # 优先级1: 东方财富实时新闻
        try:
            if hasattr(self.toolkit, "get_realtime_stock_news"):
                logger.info("[统一新闻工具] 尝试东方财富实时新闻...")
                # 使用LangChain工具的正确调用方式：.invoke()方法和字典参数
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})

                # 🔍 详细记录东方财富返回的内容
                logger.info(f"[统一新闻工具] 📊 东方财富返回内容长度: {len(result) if result else 0} 字符")
                logger.info(f"[统一新闻工具] 📋 东方财富返回内容预览 (前500字符): {result[:500] if result else 'None'}")

                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 东方财富新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "东方财富实时新闻", model_info)
                logger.warning("[统一新闻工具] ⚠️ 东方财富新闻内容过短或为空")
        except Exception as e:
            logger.warning(f"[统一新闻工具] 东方财富新闻获取失败: {e}")

        return "❌ 无法获取A股新闻数据，所有新闻源均不可用"

    def _get_hk_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取港股新闻"""
        logger.info(f"[统一新闻工具] 获取港股 {stock_code} 新闻")

        # 获取当前日期
        curr_date = datetime.now().strftime("%Y-%m-%d")

        # 优先级1: 实时新闻（如果支持港股）
        try:
            if hasattr(self.toolkit, "get_realtime_stock_news"):
                logger.info("[统一新闻工具] 尝试实时港股新闻...")
                # 使用LangChain工具的正确调用方式：.invoke()方法和字典参数
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 实时港股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "实时港股新闻", model_info)
        except Exception as e:
            logger.warning(f"[统一新闻工具] 实时港股新闻获取失败: {e}")

        return "❌ 无法获取港股新闻数据，所有新闻源均不可用"

    def _get_us_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取美股新闻"""
        logger.info(f"[统一新闻工具] 获取美股 {stock_code} 新闻")

        # 获取当前日期
        curr_date = datetime.now().strftime("%Y-%m-%d")

        # 优先级1: 实时新闻（东方财富美股支持）
        try:
            if hasattr(self.toolkit, "get_realtime_stock_news"):
                logger.info("[统一新闻工具] 尝试实时美股新闻...")
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 实时美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "实时美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[统一新闻工具] 实时美股新闻获取失败: {e}")

        return "❌ 无法获取美股新闻数据，所有新闻源均不可用"

    def _format_news_result(self, news_content: str, source: str, model_info: str = "") -> str:
        """格式化新闻结果"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 🔍 添加调试日志：打印原始新闻内容
        logger.info(f"[统一新闻工具] 📋 原始新闻内容预览 (前500字符): {news_content[:500]}")
        logger.info(f"[统一新闻工具] 📊 原始内容长度: {len(news_content)} 字符")

        # 检测是否为Google/Gemini模型
        is_google_model = any(keyword in model_info.lower() for keyword in ["google", "gemini", "gemma"])
        original_length = len(news_content)
        google_control_applied = False

        # 🔍 添加Google模型检测日志
        if is_google_model:
            logger.info("[统一新闻工具] 🤖 检测到Google模型，启用特殊处理")

        # 对Google模型进行特殊的长度控制
        if is_google_model and len(news_content) > 5000:  # 降低阈值到5000字符
            logger.warning(f"[统一新闻工具] 🔧 检测到Google模型，新闻内容过长({len(news_content)}字符)，进行长度控制...")

            # 更严格的长度控制策略
            lines = news_content.split("\n")
            important_lines = []
            char_count = 0
            target_length = 3000  # 目标长度设为3000字符

            # 第一轮：优先保留包含关键词的重要行
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 检查是否包含重要关键词
                important_keywords = ["股票", "公司", "财报", "业绩", "涨跌", "价格", "市值", "营收", "利润",
                                    "增长", "下跌", "上涨", "盈利", "亏损", "投资", "分析", "预期", "公告"]

                is_important = any(keyword in line for keyword in important_keywords)

                if (is_important and char_count + len(line) < target_length) or (not is_important and char_count + len(line) < target_length * 0.7):
                    important_lines.append(line)
                    char_count += len(line)

                # 如果已达到目标长度，停止添加
                if char_count >= target_length:
                    break

            # 如果提取的重要内容仍然过长，进行进一步截断
            if important_lines:
                processed_content = "\n".join(important_lines)
                if len(processed_content) > target_length:
                    processed_content = processed_content[:target_length] + "...(内容已智能截断)"

                news_content = processed_content
                google_control_applied = True
                logger.info(f"[统一新闻工具] ✅ Google模型智能长度控制完成，从{original_length}字符压缩至{len(news_content)}字符")
            else:
                # 如果没有重要行，直接截断到目标长度
                news_content = news_content[:target_length] + "...(内容已强制截断)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] ⚠️ Google模型强制截断至{target_length}字符")

        # 计算最终的格式化结果长度，确保总长度合理
        base_format_length = 300  # 格式化模板的大概长度
        if is_google_model and (len(news_content) + base_format_length) > 4000:
            # 如果加上格式化后仍然过长，进一步压缩新闻内容
            max_content_length = 3500
            if len(news_content) > max_content_length:
                news_content = news_content[:max_content_length] + "...(已优化长度)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] 🔧 Google模型最终长度优化，内容长度: {len(news_content)}字符")

        formatted_result = f"""
=== 📰 新闻数据来源: {source} ===
获取时间: {timestamp}
数据长度: {len(news_content)} 字符
{f"模型类型: {model_info}" if model_info else ""}
{f"🔧 Google模型长度控制已应用 (原长度: {original_length} 字符)" if google_control_applied else ""}

=== 📋 新闻内容 ===
{news_content}

=== ✅ 数据状态 ===
状态: 成功获取
来源: {source}
时间戳: {timestamp}
"""
        return formatted_result.strip()


def create_unified_news_tool(toolkit):
    """创建统一新闻工具函数"""
    analyzer = UnifiedNewsAnalyzer(toolkit)

    def get_stock_news_unified(stock_code: str, max_news: int = 100, model_info: str = ""):
        """
        统一新闻获取工具
        
        Args:
            stock_code (str): 股票代码 (支持A股如000001、港股如0700.HK、美股如AAPL)
            max_news (int): 最大新闻数量，默认100
            model_info (str): 当前使用的模型信息，用于特殊处理
        
        Returns:
            str: 格式化的新闻内容
        """
        if not stock_code:
            return "❌ 错误: 未提供股票代码"

        return analyzer.get_stock_news_unified(stock_code, max_news, model_info)

    # 设置工具属性
    get_stock_news_unified.name = "get_stock_news_unified"
    get_stock_news_unified.description = """
统一新闻获取工具 - 根据股票代码自动获取相应市场的新闻

功能:
- 自动识别股票类型（A股/港股/美股）
- 根据股票类型选择最佳新闻源
- 所有市场: 优先东方财富实时新闻（通过反爬虫系统）
- 返回格式化的新闻内容
"""

    return get_stock_news_unified
