"""
数据目录配置工具
Data Directory Configuration Utilities

为项目中的其他模块提供统一的数据目录访问接口
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from scripts.unified_data_manager import get_data_manager, get_data_path
except ImportError:
    # 如果无法导入，提供基本的实现
    def get_data_path(key: str, create: bool = True) -> Path:
        """基本的数据路径获取函数"""
        project_root = Path(__file__).parent.parent

        # 基本路径映射
        path_mapping = {
            "data_root": "data",
            "cache": "data/cache",
            "analysis_results": "data/analysis_results",
            "sessions": "data/sessions",
            "logs": "data/logs",
            "config": "data/config",
            "temp": "data/temp",
        }

        path_str = path_mapping.get(key, f"data/{key}")
        path = project_root / path_str

        if create:
            path.mkdir(parents=True, exist_ok=True)

        return path


# 便捷函数
def get_cache_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取缓存目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 缓存目录路径
    """
    if subdir:
        cache_path = get_data_path("cache", create=create) / subdir
        if create:
            cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path
    return get_data_path("cache", create=create)


def get_results_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取分析结果目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 结果目录路径
    """
    if subdir:
        results_path = get_data_path("analysis_results", create=create) / subdir
        if create:
            results_path.mkdir(parents=True, exist_ok=True)
        return results_path
    return get_data_path("analysis_results", create=create)


def get_sessions_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取会话数据目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 会话目录路径
    """
    if subdir:
        sessions_path = get_data_path("sessions", create=create) / subdir
        if create:
            sessions_path.mkdir(parents=True, exist_ok=True)
        return sessions_path
    return get_data_path("sessions", create=create)


def get_logs_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取日志目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 日志目录路径
    """
    if subdir:
        logs_path = get_data_path("logs", create=create) / subdir
        if create:
            logs_path.mkdir(parents=True, exist_ok=True)
        return logs_path
    return get_data_path("logs", create=create)


def get_config_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取配置目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 配置目录路径
    """
    if subdir:
        config_path = get_data_path("config", create=create) / subdir
        if create:
            config_path.mkdir(parents=True, exist_ok=True)
        return config_path
    return get_data_path("config", create=create)


def get_temp_dir(subdir: str | None = None, create: bool = True) -> Path:
    """
    获取临时文件目录

    Args:
        subdir: 子目录名称
        create: 是否自动创建目录

    Returns:
        Path: 临时目录路径
    """
    if subdir:
        temp_path = get_data_path("temp", create=create) / subdir
        if create:
            temp_path.mkdir(parents=True, exist_ok=True)
        return temp_path
    return get_data_path("temp", create=create)


# 兼容性函数 - 为现有代码提供向后兼容
def get_analysis_results_dir() -> Path:
    """获取分析结果目录 (兼容性函数)"""
    return get_results_dir()


def get_stock_data_cache_dir() -> Path:
    """获取股票数据缓存目录"""
    return get_cache_dir("stock_data")


def get_news_data_cache_dir() -> Path:
    """获取新闻数据缓存目录"""
    return get_cache_dir("news_data")


def get_fundamentals_cache_dir() -> Path:
    """获取基本面数据缓存目录"""
    return get_cache_dir("fundamentals")


def get_metadata_cache_dir() -> Path:
    """获取元数据缓存目录"""
    return get_cache_dir("metadata")


def get_web_sessions_dir() -> Path:
    """获取Web会话目录"""
    return get_sessions_dir("web_sessions")


def get_cli_sessions_dir() -> Path:
    """获取CLI会话目录"""
    return get_sessions_dir("cli_sessions")


def get_application_logs_dir() -> Path:
    """获取应用程序日志目录"""
    return get_logs_dir("application")


def get_operations_logs_dir() -> Path:
    """获取操作日志目录"""
    return get_logs_dir("operations")


def get_user_activities_logs_dir() -> Path:
    """获取用户活动日志目录"""
    return get_logs_dir("user_activities")


# 环境变量检查函数
def check_data_directory_config() -> dict:
    """
    检查数据目录配置状态

    Returns:
        dict: 配置状态信息
    """
    env_vars = [
        "TRADINGAGENTS_DATA_DIR",
        "TRADINGAGENTS_CACHE_DIR",
        "TRADINGAGENTS_RESULTS_DIR",
        "TRADINGAGENTS_SESSIONS_DIR",
        "TRADINGAGENTS_LOGS_DIR",
        "TRADINGAGENTS_CONFIG_DIR",
        "TRADINGAGENTS_TEMP_DIR",
    ]

    config_status = {}
    for var in env_vars:
        value = os.getenv(var)
        config_status[var] = {
            "set": value is not None,
            "value": value,
            "exists": Path(value).exists() if value else False,
        }

    return config_status


def print_data_directory_status():
    """打印数据目录配置状态"""
    print("📁 数据目录配置状态:")
    print("=" * 50)

    status = check_data_directory_config()

    for var, info in status.items():
        status_icon = "✅" if info["set"] else "❌"
        exists_icon = "📁" if info["exists"] else "❓"

        print(f"{status_icon} {var}")
        if info["set"]:
            print(f"   值: {info['value']}")
            print(f"   {exists_icon} 目录存在: {'是' if info['exists'] else '否'}")
        else:
            print("   未设置")
        print()


if __name__ == "__main__":
    print_data_directory_status()
