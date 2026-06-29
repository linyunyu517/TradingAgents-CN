#!/usr/bin/env python3
"""
Finnhub数据下载脚本

这个脚本用于从Finnhub API下载新闻数据、内部人情绪数据和内部人交易数据。
支持批量下载和增量更新。

使用方法:
    python scripts/download_finnhub_data.py --data-type news --symbols AAPL,TSLA,MSFT
    python scripts/download_finnhub_data.py --all
    python scripts/download_finnhub_data.py --force-refresh
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入项目模块
try:
    from tradingagents.config.config_manager import config_manager
    from tradingagents.utils.logging_manager import get_logger

    logger = get_logger("finnhub_downloader")
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)


class FinnhubDataDownloader:
    """Finnhub数据下载器"""

    def __init__(self, api_key: str | None = None, data_dir: str | None = None):
        """
        初始化下载器

        Args:
            api_key: Finnhub API密钥
            data_dir: 数据存储目录
        """
        # 获取API密钥
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        if not self.api_key:
            raise ValueError("❌ 未找到Finnhub API密钥，请设置FINNHUB_API_KEY环境变量")

        # 获取数据目录
        if data_dir:
            self.data_dir = data_dir
        else:
            # 优先使用环境变量，然后是项目根目录
            env_data_dir = os.getenv("TRADINGAGENTS_DATA_DIR")
            if env_data_dir:
                self.data_dir = env_data_dir
            else:
                # 使用项目根目录下的data目录
                self.data_dir = str(project_root / "data")

            logger.info(f"🔍 数据目录来源: {'环境变量' if env_data_dir else '项目根目录'}")

        self.base_url = "https://finnhub.io/api/v1"
        self.session = requests.Session()

        logger.info(f"📁 数据目录: {self.data_dir}")
        logger.info(f"🔑 API密钥: {self.api_key[:8]}...")

    def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        发送API请求

        Args:
            endpoint: API端点
            params: 请求参数

        Returns:
            API响应数据
        """
        params["token"] = self.api_key
        url = f"{self.base_url}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            # 检查API限制
            if response.status_code == 429:
                logger.warning("⚠️ API调用频率限制，等待60秒...")
                time.sleep(60)
                return self._make_request(endpoint, params)

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API请求失败: {e}")
            return {}

    def download_news_data(self, symbols: list[str], days: int = 7, force_refresh: bool = False):
        """
        下载新闻数据

        Args:
            symbols: 股票代码列表
            days: 下载多少天的数据
            force_refresh: 是否强制刷新
        """
        logger.info(f"📰 开始下载新闻数据，股票: {symbols}, 天数: {days}")

        # 创建目录
        news_dir = Path(self.data_dir) / "finnhub_data" / "news_data"
        news_dir.mkdir(parents=True, exist_ok=True)

        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        for symbol in symbols:
            logger.info(f"📰 下载 {symbol} 的新闻数据...")

            # 检查文件是否存在且有效
            file_path = news_dir / f"{symbol}_data_formatted.json"
            if file_path.exists() and not force_refresh:
                # 检查文件是否有内容
                try:
                    file_size = file_path.stat().st_size
                    if file_size > 10:  # 文件大小大于10字节才认为有效
                        logger.info(f"📄 {symbol} 数据文件已存在且有效 (大小: {file_size} 字节)，跳过下载")
                        continue
                    logger.warning(f"⚠️ {symbol} 数据文件存在但为空 (大小: {file_size} 字节)，重新下载")
                except Exception as e:
                    logger.warning(f"⚠️ 检查 {symbol} 文件状态失败: {e}，重新下载")

            logger.info(f"📥 开始下载 {symbol} 的新闻数据...")

            # 下载新闻数据
            params = {"symbol": symbol, "from": start_date.strftime("%Y-%m-%d"), "to": end_date.strftime("%Y-%m-%d")}

            news_data = self._make_request("company-news", params)

            logger.info(
                f"🔍 API响应类型: {type(news_data)}, 长度: {len(news_data) if isinstance(news_data, list) else 'N/A'}",
            )

            if news_data and isinstance(news_data, list) and len(news_data) > 0:
                # 格式化数据
                formatted_data = []
                for item in news_data:
                    formatted_item = {
                        "datetime": item.get("datetime", 0),
                        "headline": item.get("headline", ""),
                        "summary": item.get("summary", ""),
                        "url": item.get("url", ""),
                        "source": item.get("source", ""),
                        "category": item.get("category", ""),
                        "sentiment": item.get("sentiment", {}),
                    }
                    formatted_data.append(formatted_item)

                # 保存数据
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(formatted_data, f, ensure_ascii=False, indent=2)

                    # 验证文件保存
                    if file_path.exists():
                        file_size = file_path.stat().st_size
                        logger.info(f"✅ {symbol} 新闻数据已保存: {len(formatted_data)} 条, 文件大小: {file_size} 字节")
                    else:
                        logger.error(f"❌ {symbol} 文件保存失败，文件不存在")

                except Exception as e:
                    logger.error(f"❌ {symbol} 文件保存异常: {e}")

            elif news_data and isinstance(news_data, dict):
                logger.warning(f"⚠️ {symbol} API返回字典而非列表: {news_data}")
            else:
                logger.warning(f"⚠️ {symbol} 新闻数据下载失败或为空")

            # 避免API限制
            time.sleep(1)

    def download_insider_sentiment(self, symbols: list[str], force_refresh: bool = False):
        """
        下载内部人情绪数据

        Args:
            symbols: 股票代码列表
            force_refresh: 是否强制刷新
        """
        logger.info(f"💭 开始下载内部人情绪数据，股票: {symbols}")

        # 创建目录
        sentiment_dir = Path(self.data_dir) / "finnhub_data" / "insider_senti"
        sentiment_dir.mkdir(parents=True, exist_ok=True)

        for symbol in symbols:
            logger.info(f"💭 下载 {symbol} 的内部人情绪数据...")

            # 检查文件是否存在
            file_path = sentiment_dir / f"{symbol}_data_formatted.json"
            if file_path.exists() and not force_refresh:
                logger.info(f"📄 {symbol} 情绪数据文件已存在，跳过下载")
                continue

            # 下载情绪数据
            params = {"symbol": symbol}
            sentiment_data = self._make_request("stock/insider-sentiment", params)

            if sentiment_data and "data" in sentiment_data:
                # 保存数据
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(sentiment_data, f, ensure_ascii=False, indent=2)

                logger.info(f"✅ {symbol} 内部人情绪数据已保存")
            else:
                logger.warning(f"⚠️ {symbol} 内部人情绪数据下载失败")

            # 避免API限制
            time.sleep(1)

    def download_insider_transactions(self, symbols: list[str], force_refresh: bool = False):
        """
        下载内部人交易数据

        Args:
            symbols: 股票代码列表
            force_refresh: 是否强制刷新
        """
        logger.info(f"💰 开始下载内部人交易数据，股票: {symbols}")

        # 创建目录
        trans_dir = Path(self.data_dir) / "finnhub_data" / "insider_trans"
        trans_dir.mkdir(parents=True, exist_ok=True)

        for symbol in symbols:
            logger.info(f"💰 下载 {symbol} 的内部人交易数据...")

            # 检查文件是否存在
            file_path = trans_dir / f"{symbol}_data_formatted.json"
            if file_path.exists() and not force_refresh:
                logger.info(f"📄 {symbol} 交易数据文件已存在，跳过下载")
                continue

            # 下载交易数据
            params = {"symbol": symbol}
            trans_data = self._make_request("stock/insider-transactions", params)

            if trans_data and "data" in trans_data:
                # 保存数据
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(trans_data, f, ensure_ascii=False, indent=2)

                logger.info(f"✅ {symbol} 内部人交易数据已保存")
            else:
                logger.warning(f"⚠️ {symbol} 内部人交易数据下载失败")

            # 避免API限制
            time.sleep(1)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Finnhub数据下载脚本")

    parser.add_argument(
        "--data-type", choices=["news", "sentiment", "transactions", "all"], default="all", help="要下载的数据类型",
    )

    parser.add_argument("--symbols", type=str, default="AAPL,TSLA,MSFT,GOOGL,AMZN", help="股票代码，用逗号分隔")

    parser.add_argument("--days", type=int, default=7, help="下载多少天的新闻数据")

    parser.add_argument("--force-refresh", action="store_true", help="强制刷新已存在的数据")

    parser.add_argument("--all", action="store_true", help="下载所有类型的数据")

    parser.add_argument("--api-key", type=str, help="Finnhub API密钥")

    parser.add_argument("--data-dir", type=str, help="数据存储目录")

    args = parser.parse_args()

    # 解析股票代码
    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    try:
        # 创建下载器
        downloader = FinnhubDataDownloader(api_key=args.api_key, data_dir=args.data_dir)

        # 确定要下载的数据类型
        if args.all:
            data_types = ["news", "sentiment", "transactions"]
        else:
            data_types = [args.data_type] if args.data_type != "all" else ["news", "sentiment", "transactions"]

        logger.info("🚀 开始下载Finnhub数据")
        logger.info(f"📊 股票代码: {symbols}")
        logger.info(f"📋 数据类型: {data_types}")
        logger.info(f"🔄 强制刷新: {args.force_refresh}")

        # 下载数据
        for data_type in data_types:
            if data_type == "news":
                downloader.download_news_data(symbols, args.days, args.force_refresh)
            elif data_type == "sentiment":
                downloader.download_insider_sentiment(symbols, args.force_refresh)
            elif data_type == "transactions":
                downloader.download_insider_transactions(symbols, args.force_refresh)

        logger.info("🎉 数据下载完成！")

    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
