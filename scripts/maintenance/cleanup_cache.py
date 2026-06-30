#!/usr/bin/env python3
"""
缓存清理工具
清理过期的缓存文件和数据库记录
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def cleanup_file_cache(max_age_days: int = 7):
    """清理文件缓存"""
    logger.info(f"🧹 清理 {max_age_days} 天前的文件缓存...")

    cache_dirs = [
        project_root / "cache",
        project_root / "data" / "cache",
        project_root / "tradingagents" / "dataflows" / "data_cache",
    ]

    total_cleaned = 0
    cutoff_time = datetime.now() - timedelta(days=max_age_days)

    for cache_dir in cache_dirs:
        if not cache_dir.exists():
            continue

        logger.info(f"📁 检查缓存目录: {cache_dir}")

        for cache_file in cache_dir.rglob("*"):
            if cache_file.is_file():
                try:
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_time < cutoff_time:
                        cache_file.unlink()
                        total_cleaned += 1
                        logger.info(f"  ✅ 删除: {cache_file.name}")
                except Exception as e:
                    logger.error(f"  ❌ 删除失败: {cache_file.name} - {e}")

    logger.info(f"✅ 文件缓存清理完成，删除了 {total_cleaned} 个文件")
    return total_cleaned


def cleanup_database_cache(max_age_days: int = 7):
    """清理数据库缓存"""
    logger.info(f"🗄️ 清理 {max_age_days} 天前的数据库缓存...")

    try:
        from tradingagents.dataflows.integrated_cache import get_cache

        cache = get_cache()

        if hasattr(cache, "clear_old_cache"):
            cleared_count = cache.clear_old_cache(max_age_days)
            logger.info(f"✅ 数据库缓存清理完成，删除了 {cleared_count} 条记录")
            return cleared_count
        logger.info("ℹ️ 当前缓存系统不支持自动清理")
        return 0

    except Exception as e:
        logger.error(f"❌ 数据库缓存清理失败: {e}")
        return 0


def cleanup_python_cache():
    """清理Python缓存文件"""
    logger.info("🐍 清理Python缓存文件...")

    cache_patterns = ["__pycache__", "*.pyc", "*.pyo"]
    total_cleaned = 0

    for pattern in cache_patterns:
        if pattern == "__pycache__":
            cache_dirs = list(project_root.rglob(pattern))
            for cache_dir in cache_dirs:
                try:
                    import shutil

                    shutil.rmtree(cache_dir)
                    total_cleaned += 1
                    logger.info(f"  ✅ 删除目录: {cache_dir.relative_to(project_root)}")
                except Exception as e:
                    logger.error(f"  ❌ 删除失败: {cache_dir.relative_to(project_root)} - {e}")
        else:
            cache_files = list(project_root.rglob(pattern))
            for cache_file in cache_files:
                try:
                    cache_file.unlink()
                    total_cleaned += 1
                    logger.info(f"  ✅ 删除文件: {cache_file.relative_to(project_root)}")
                except Exception as e:
                    logger.error(f"  ❌ 删除失败: {cache_file.relative_to(project_root)} - {e}")

    logger.info(f"✅ Python缓存清理完成，删除了 {total_cleaned} 个项目")
    return total_cleaned


def get_cache_statistics():
    """获取缓存统计信息"""
    logger.info("📊 获取缓存统计信息...")

    try:
        from tradingagents.dataflows.integrated_cache import get_cache

        cache = get_cache()

        logger.info(f"🎯 缓存模式: {cache.get_performance_mode()}")
        logger.info(f"🗄️ 数据库可用: {'是' if cache.is_database_available() else '否'}")

        # 统计文件缓存
        cache_dirs = [
            project_root / "cache",
            project_root / "data" / "cache",
            project_root / "tradingagents" / "dataflows" / "data_cache",
        ]

        total_files = 0
        total_size = 0

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                for cache_file in cache_dir.rglob("*"):
                    if cache_file.is_file():
                        total_files += 1
                        total_size += cache_file.stat().st_size

        logger.info(f"📁 文件缓存: {total_files} 个文件，{total_size / 1024 / 1024:.2f} MB")

    except Exception as e:
        logger.error(f"❌ 获取缓存统计失败: {e}")


def main():
    """主函数"""
    logger.info("🧹 TradingAgents 缓存清理工具")
    logger.info("=")

    import argparse

    parser = argparse.ArgumentParser(description="清理TradingAgents缓存")
    parser.add_argument("--days", type=int, default=7, help="清理多少天前的缓存 (默认: 7)")
    parser.add_argument(
        "--type", choices=["all", "file", "database", "python"], default="all", help="清理类型 (默认: all)",
    )
    parser.add_argument("--stats", action="store_true", help="只显示统计信息，不清理")

    args = parser.parse_args()

    if args.stats:
        get_cache_statistics()
        return

    total_cleaned = 0

    if args.type in ["all", "file"]:
        total_cleaned += cleanup_file_cache(args.days)

    if args.type in ["all", "database"]:
        total_cleaned += cleanup_database_cache(args.days)

    if args.type in ["all", "python"]:
        total_cleaned += cleanup_python_cache()

    logger.info("\n")
    logger.info(f"🎉 缓存清理完成！总共清理了 {total_cleaned} 个项目")
    logger.info("\n💡 使用提示:")
    logger.info("  --stats     查看缓存统计")
    logger.info("  --days 3    清理3天前的缓存")
    logger.info("  --type file 只清理文件缓存")


if __name__ == "__main__":
    main()
