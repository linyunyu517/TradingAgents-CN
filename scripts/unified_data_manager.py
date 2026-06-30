#!/usr/bin/env python3
"""
统一数据目录配置管理器
Unified Data Directory Configuration Manager

提供统一的数据目录配置管理功能
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class UnifiedDataDirectoryManager:
    """统一数据目录管理器"""

    def __init__(self, project_root: str | Path | None = None):
        """
        初始化数据目录管理器

        Args:
            project_root: 项目根目录，默认为当前文件的上级目录
        """
        if project_root is None:
            # 假设此文件在 scripts/ 目录下
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = Path(project_root)

        # 默认数据目录配置
        self._default_config = {
            "data_root": "data",
            "cache": "data/cache",
            "analysis_results": "data/analysis_results",
            "databases": "data/databases",
            "sessions": "data/sessions",
            "logs": "data/logs",
            "config": "data/config",
            "temp": "data/temp",
            # 子目录
            "cache_stock_data": "data/cache/stock_data",
            "cache_news_data": "data/cache/news_data",
            "cache_fundamentals": "data/cache/fundamentals",
            "cache_metadata": "data/cache/metadata",
            "results_summary": "data/analysis_results/summary",
            "results_detailed": "data/analysis_results/detailed",
            "results_exports": "data/analysis_results/exports",
            "db_mongodb": "data/databases/mongodb",
            "db_redis": "data/databases/redis",
            "sessions_web": "data/sessions/web_sessions",
            "sessions_cli": "data/sessions/cli_sessions",
            "logs_application": "data/logs/application",
            "logs_operations": "data/logs/operations",
            "logs_user_activities": "data/logs/user_activities",
            "config_user": "data/config/user_configs",
            "config_system": "data/config/system_configs",
            "temp_downloads": "data/temp/downloads",
            "temp_processing": "data/temp/processing",
        }

        # 环境变量映射
        self._env_mapping = {
            "data_root": "TRADINGAGENTS_DATA_DIR",
            "cache": "TRADINGAGENTS_CACHE_DIR",
            "analysis_results": "TRADINGAGENTS_RESULTS_DIR",
            "sessions": "TRADINGAGENTS_SESSIONS_DIR",
            "logs": "TRADINGAGENTS_LOGS_DIR",
            "config": "TRADINGAGENTS_CONFIG_DIR",
            "temp": "TRADINGAGENTS_TEMP_DIR",
        }

    def get_path(self, key: str, create: bool = True) -> Path:
        """
        获取指定数据目录的路径

        Args:
            key: 目录键名
            create: 是否自动创建目录

        Returns:
            Path: 目录路径对象
        """
        # 首先检查环境变量
        env_key = self._env_mapping.get(key)
        if env_key and os.getenv(env_key):
            path_str = os.getenv(env_key)
        else:
            # 使用默认配置
            path_str = self._default_config.get(key)
            if not path_str:
                raise ValueError(f"未知的目录键: {key}")

        # 处理路径
        path = Path(path_str) if os.path.isabs(path_str) else self.project_root / path_str

        # 创建目录
        if create:
            path.mkdir(parents=True, exist_ok=True)

        return path

    def get_all_paths(self, create: bool = True) -> dict[str, Path]:
        """
        获取所有数据目录路径

        Args:
            create: 是否自动创建目录

        Returns:
            Dict[str, Path]: 所有目录路径的字典
        """
        paths = {}
        for key in self._default_config:
            try:
                paths[key] = self.get_path(key, create=create)
            except Exception as e:
                logger.warning(f"获取路径失败 {key}: {e}")

        return paths

    def create_all_directories(self) -> bool:
        """
        创建所有数据目录

        Returns:
            bool: 是否成功创建所有目录
        """
        try:
            logger.info("🔄 创建统一数据目录结构...")

            paths = self.get_all_paths(create=True)

            for key, path in paths.items():
                logger.info(f"  ✅ {key}: {path}")

            logger.info("✅ 统一数据目录结构创建完成")
            return True

        except Exception as e:
            logger.error(f"❌ 创建目录结构失败: {e}")
            return False

    def get_config_summary(self) -> dict[str, str]:
        """
        获取配置摘要

        Returns:
            Dict[str, str]: 配置摘要
        """
        summary = {
            "project_root": str(self.project_root),
            "data_root": str(self.get_path("data_root", create=False)),
        }

        # 添加环境变量状态
        for key, env_key in self._env_mapping.items():
            env_value = os.getenv(env_key)
            summary[f"env_{key}"] = env_value or "未设置"

        return summary

    def validate_structure(self) -> dict[str, bool]:
        """
        验证目录结构

        Returns:
            Dict[str, bool]: 验证结果
        """
        results = {}

        for key in self._default_config:
            try:
                path = self.get_path(key, create=False)
                results[key] = path.exists()
            except Exception:
                results[key] = False

        return results

    def print_structure(self):
        """打印目录结构"""
        print("📁 统一数据目录结构:")
        print(f"📂 项目根目录: {self.project_root}")
        print()

        # 按层级组织显示
        structure = {
            "📊 数据根目录": ["data_root"],
            "💾 缓存目录": ["cache", "cache_stock_data", "cache_news_data", "cache_fundamentals", "cache_metadata"],
            "📈 分析结果": ["analysis_results", "results_summary", "results_detailed", "results_exports"],
            "🗄️ 数据库": ["databases", "db_mongodb", "db_redis"],
            "📝 会话数据": ["sessions", "sessions_web", "sessions_cli"],
            "📋 日志文件": ["logs", "logs_application", "logs_operations", "logs_user_activities"],
            "🔧 配置文件": ["config", "config_user", "config_system"],
            "📦 临时文件": ["temp", "temp_downloads", "temp_processing"],
        }

        for category, keys in structure.items():
            print(f"{category}:")
            for key in keys:
                try:
                    path = self.get_path(key, create=False)
                    exists = "✅" if path.exists() else "❌"
                    relative_path = path.relative_to(self.project_root)
                    print(f"  {exists} {key}: {relative_path}")
                except Exception as e:
                    print(f"  ❌ {key}: 错误 - {e}")
            print()


# 全局实例
_data_manager = None


def get_data_manager(project_root: str | Path | None = None) -> UnifiedDataDirectoryManager:
    """
    获取全局数据目录管理器实例

    Args:
        project_root: 项目根目录

    Returns:
        UnifiedDataDirectoryManager: 数据目录管理器实例
    """
    global _data_manager
    if _data_manager is None:
        _data_manager = UnifiedDataDirectoryManager(project_root)
    return _data_manager


def get_data_path(key: str, create: bool = True) -> Path:
    """
    便捷函数：获取数据目录路径

    Args:
        key: 目录键名
        create: 是否自动创建目录

    Returns:
        Path: 目录路径
    """
    return get_data_manager().get_path(key, create=create)


def main():
    """命令行工具主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="统一数据目录配置管理器")
    parser.add_argument("--project-root", help="项目根目录路径")
    parser.add_argument("--create", action="store_true", help="创建所有目录")
    parser.add_argument("--validate", action="store_true", help="验证目录结构")
    parser.add_argument("--show-config", action="store_true", help="显示配置摘要")
    parser.add_argument("--show-structure", action="store_true", help="显示目录结构")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    manager = UnifiedDataDirectoryManager(args.project_root)

    if args.create:
        manager.create_all_directories()

    if args.validate:
        print("🔍 验证目录结构:")
        results = manager.validate_structure()
        for key, exists in results.items():
            status = "✅" if exists else "❌"
            print(f"  {status} {key}")

        total = len(results)
        existing = sum(results.values())
        print(f"\n📊 统计: {existing}/{total} 个目录存在")

    if args.show_config:
        print("⚙️ 配置摘要:")
        config = manager.get_config_summary()
        for key, value in config.items():
            print(f"  {key}: {value}")

    if args.show_structure:
        manager.print_structure()

    # 如果没有指定任何操作，显示帮助
    if not any([args.create, args.validate, args.show_config, args.show_structure]):
        parser.print_help()


if __name__ == "__main__":
    main()
