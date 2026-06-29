#!/usr/bin/env python3
"""
消息数据爬虫调度器
统一调度社媒消息和内部消息的爬取任务
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import init_db
from app.services.internal_message_service import get_internal_message_service
from app.services.social_media_service import get_social_media_service

# 导入爬虫模块
try:
    from internal_message_crawler import crawl_and_save_internal_messages
    from social_media_crawler import crawl_and_save_social_media
except ImportError:
    # 如果从其他目录运行，尝试绝对导入
    from examples.crawlers.internal_message_crawler import crawl_and_save_internal_messages
    from examples.crawlers.social_media_crawler import crawl_and_save_social_media

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MessageCrawlerScheduler:
    """消息数据爬虫调度器"""

    def __init__(self, config_file: str | None = None):
        self.config_file = config_file or "crawler_config.json"
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """加载爬虫配置"""
        default_config = {
            "symbols": ["000001", "000002", "600000", "600036", "000858"],
            "social_media": {
                "enabled": True,
                "platforms": ["weibo", "douyin"],
                "limits": {"weibo": 50, "douyin": 30},
                "schedule": {"interval_hours": 4, "max_daily_runs": 6},
            },
            "internal_messages": {
                "enabled": True,
                "types": ["research_report", "analyst_note"],
                "limits": {"research_report": 10, "analyst_note": 20},
                "schedule": {"interval_hours": 8, "max_daily_runs": 3},
            },
            "database": {"batch_size": 100, "retry_attempts": 3, "retry_delay": 5},
            "logging": {"level": "INFO", "save_logs": True, "log_file": "crawler_logs.txt"},
        }

        config_path = Path(self.config_file)
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    user_config = json.load(f)
                    # 合并配置
                    default_config.update(user_config)
                    self.logger.info(f"✅ 加载配置文件: {config_path}")
            except Exception as e:
                self.logger.warning(f"⚠️ 配置文件加载失败，使用默认配置: {e}")
        else:
            # 创建默认配置文件
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                self.logger.info(f"✅ 创建默认配置文件: {config_path}")
            except Exception as e:
                self.logger.warning(f"⚠️ 配置文件创建失败: {e}")

        return default_config

    async def run_social_media_crawl(self) -> dict[str, Any]:
        """运行社媒消息爬取"""
        if not self.config["social_media"]["enabled"]:
            self.logger.info("⏸️ 社媒消息爬取已禁用")
            return {"status": "disabled", "saved": 0}

        self.logger.info("🕷️ 开始社媒消息爬取任务")

        try:
            symbols = self.config["symbols"]
            platforms = self.config["social_media"]["platforms"]

            # 执行爬取
            saved_count = await crawl_and_save_social_media(symbols, platforms)

            result = {
                "status": "success",
                "saved": saved_count,
                "symbols": len(symbols),
                "platforms": len(platforms),
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info(f"✅ 社媒消息爬取完成: {saved_count} 条")
            return result

        except Exception as e:
            self.logger.error(f"❌ 社媒消息爬取失败: {e}")
            return {"status": "error", "error": str(e), "saved": 0, "timestamp": datetime.now().isoformat()}

    async def run_internal_message_crawl(self) -> dict[str, Any]:
        """运行内部消息爬取"""
        if not self.config["internal_messages"]["enabled"]:
            self.logger.info("⏸️ 内部消息爬取已禁用")
            return {"status": "disabled", "saved": 0}

        self.logger.info("📊 开始内部消息爬取任务")

        try:
            symbols = self.config["symbols"]
            message_types = self.config["internal_messages"]["types"]

            # 执行爬取
            saved_count = await crawl_and_save_internal_messages(symbols, message_types)

            result = {
                "status": "success",
                "saved": saved_count,
                "symbols": len(symbols),
                "types": len(message_types),
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info(f"✅ 内部消息爬取完成: {saved_count} 条")
            return result

        except Exception as e:
            self.logger.error(f"❌ 内部消息爬取失败: {e}")
            return {"status": "error", "error": str(e), "saved": 0, "timestamp": datetime.now().isoformat()}

    async def run_full_crawl(self) -> dict[str, Any]:
        """运行完整爬取任务"""
        self.logger.info("🚀 开始完整消息数据爬取任务")

        start_time = datetime.now()

        # 初始化数据库
        await init_db()

        # 并行执行社媒和内部消息爬取
        social_task = asyncio.create_task(self.run_social_media_crawl())
        internal_task = asyncio.create_task(self.run_internal_message_crawl())

        # 等待任务完成
        social_result, internal_result = await asyncio.gather(social_task, internal_task, return_exceptions=True)

        # 处理异常结果
        if isinstance(social_result, Exception):
            social_result = {"status": "error", "error": str(social_result), "saved": 0}

        if isinstance(internal_result, Exception):
            internal_result = {"status": "error", "error": str(internal_result), "saved": 0}

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 汇总结果
        total_saved = social_result.get("saved", 0) + internal_result.get("saved", 0)

        summary = {
            "status": "completed",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "total_saved": total_saved,
            "social_media": social_result,
            "internal_messages": internal_result,
            "symbols_processed": len(self.config["symbols"]),
        }

        self.logger.info(f"🎉 完整爬取任务完成: {total_saved} 条消息, 耗时 {duration:.1f} 秒")

        # 保存运行日志
        await self._save_run_log(summary)

        return summary

    async def _save_run_log(self, summary: dict[str, Any]):
        """保存运行日志"""
        if not self.config["logging"]["save_logs"]:
            return

        try:
            log_file = Path(self.config["logging"]["log_file"])

            # 读取现有日志
            logs = []
            if log_file.exists():
                with open(log_file, encoding="utf-8") as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        logs = []

            # 添加新日志
            logs.append(summary)

            # 保持最近100条记录
            if len(logs) > 100:
                logs = logs[-100:]

            # 保存日志
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"📝 运行日志已保存: {log_file}")

        except Exception as e:
            self.logger.warning(f"⚠️ 运行日志保存失败: {e}")

    async def get_crawl_statistics(self) -> dict[str, Any]:
        """获取爬取统计信息"""
        try:
            # 获取服务
            social_service = await get_social_media_service()
            internal_service = await get_internal_message_service()

            # 计算时间范围（最近24小时）
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)

            # 获取统计信息
            social_stats = await social_service.get_social_media_statistics(start_time=start_time, end_time=end_time)

            internal_stats = await internal_service.get_internal_statistics(start_time=start_time, end_time=end_time)

            return {
                "time_range": {"start_time": start_time.isoformat(), "end_time": end_time.isoformat(), "hours": 24},
                "social_media": {
                    "total_messages": social_stats.total_count,
                    "positive_messages": social_stats.positive_count,
                    "negative_messages": social_stats.negative_count,
                    "neutral_messages": social_stats.neutral_count,
                    "platforms": social_stats.platforms,
                    "avg_engagement_rate": social_stats.avg_engagement_rate,
                },
                "internal_messages": {
                    "total_messages": internal_stats.total_count,
                    "message_types": internal_stats.message_types,
                    "departments": internal_stats.departments,
                    "avg_confidence": internal_stats.avg_confidence,
                },
                "total_messages": social_stats.total_count + internal_stats.total_count,
            }

        except Exception as e:
            self.logger.error(f"❌ 获取统计信息失败: {e}")
            return {"error": str(e)}

    def print_config(self):
        """打印当前配置"""
        self.logger.info("📋 当前爬虫配置:")
        self.logger.info(f"   - 股票数量: {len(self.config['symbols'])}")
        self.logger.info(f"   - 社媒平台: {self.config['social_media']['platforms']}")
        self.logger.info(f"   - 内部消息类型: {self.config['internal_messages']['types']}")
        self.logger.info(f"   - 社媒爬取: {'启用' if self.config['social_media']['enabled'] else '禁用'}")
        self.logger.info(f"   - 内部消息爬取: {'启用' if self.config['internal_messages']['enabled'] else '禁用'}")


async def main():
    """主函数"""
    logger.info("🤖 消息数据爬虫调度器启动")

    # 创建调度器
    scheduler = MessageCrawlerScheduler()

    # 打印配置
    scheduler.print_config()

    # 运行完整爬取
    result = await scheduler.run_full_crawl()

    # 打印结果
    logger.info("\n" + "=" * 60)
    logger.info("📊 爬取任务执行结果")
    logger.info("=" * 60)
    logger.info(f"总耗时: {result['duration_seconds']:.1f} 秒")
    logger.info(f"总保存: {result['total_saved']} 条消息")
    logger.info(f"社媒消息: {result['social_media']['saved']} 条")
    logger.info(f"内部消息: {result['internal_messages']['saved']} 条")
    logger.info(f"处理股票: {result['symbols_processed']} 只")

    # 获取统计信息
    stats = await scheduler.get_crawl_statistics()
    if "error" not in stats:
        logger.info("\n📈 最近24小时统计:")
        logger.info(f"社媒消息总数: {stats['social_media']['total_messages']}")
        logger.info(f"内部消息总数: {stats['internal_messages']['total_messages']}")
        logger.info(f"消息总数: {stats['total_messages']}")

    logger.info("=" * 60)

    if result["total_saved"] > 0:
        logger.info("✅ 消息数据爬虫调度器运行成功!")
    else:
        logger.warning("⚠️ 未保存任何消息，请检查配置和网络连接")


if __name__ == "__main__":
    asyncio.run(main())
