#!/usr/bin/env python3
"""
将 .env 文件中的配置迁移到新的JSON配置系统
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.config.config_manager import config_manager


def load_env_config():
    """加载 .env 文件配置"""
    env_file = project_root / ".env"
    if not env_file.exists():
        logger.error("❌ .env 文件不存在")
        return None

    load_dotenv(env_file)
    return {
        "dashscope_api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "finnhub_api_key": os.getenv("FINNHUB_API_KEY", ""),
        "reddit_client_id": os.getenv("REDDIT_CLIENT_ID", ""),
        "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "reddit_user_agent": os.getenv("REDDIT_USER_AGENT", ""),
        "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "log_level": os.getenv("TRADINGAGENTS_LOG_LEVEL", "INFO"),
    }


def migrate_model_configs(env_config):
    """迁移模型配置"""
    logger.info("🔄 迁移模型配置...")

    # 加载现有配置
    models = config_manager.load_models()

    # 更新API密钥
    updated = False
    for model in models:
        if model.provider == "dashscope" and env_config["dashscope_api_key"]:
            if model.api_key != env_config["dashscope_api_key"]:
                model.api_key = env_config["dashscope_api_key"]
                model.enabled = True  # 有API密钥的模型自动启用
                updated = True
                logger.info(f"✅ 更新 {model.provider} - {model.model_name} API密钥")

        elif model.provider == "openai" and env_config["openai_api_key"]:
            if model.api_key != env_config["openai_api_key"]:
                model.api_key = env_config["openai_api_key"]
                model.enabled = True
                updated = True
                logger.info(f"✅ 更新 {model.provider} - {model.model_name} API密钥")

        elif model.provider == "google" and env_config["google_api_key"]:
            if model.api_key != env_config["google_api_key"]:
                model.api_key = env_config["google_api_key"]
                model.enabled = True
                updated = True
                logger.info(f"✅ 更新 {model.provider} - {model.model_name} API密钥")

        elif model.provider == "anthropic" and env_config["anthropic_api_key"]:
            if model.api_key != env_config["anthropic_api_key"]:
                model.api_key = env_config["anthropic_api_key"]
                model.enabled = True
                updated = True
                logger.info(f"✅ 更新 {model.provider} - {model.model_name} API密钥")

    if updated:
        config_manager.save_models(models)
        logger.info("💾 模型配置已保存")
    else:
        logger.info("ℹ️ 模型配置无需更新")


def migrate_system_settings(env_config):
    """迁移系统设置"""
    logger.info("\n🔄 迁移系统设置...")

    settings = config_manager.load_settings()

    # 更新设置
    updated = False
    if env_config["results_dir"] and settings.get("results_dir") != env_config["results_dir"]:
        settings["results_dir"] = env_config["results_dir"]
        updated = True
        logger.info(f"✅ 更新结果目录: {env_config['results_dir']}")

    if env_config["log_level"] and settings.get("log_level") != env_config["log_level"]:
        settings["log_level"] = env_config["log_level"]
        updated = True
        logger.info(f"✅ 更新日志级别: {env_config['log_level']}")

    # 添加其他配置
    if env_config["finnhub_api_key"]:
        settings["finnhub_api_key"] = env_config["finnhub_api_key"]
        updated = True
        logger.info("✅ 添加 FinnHub API密钥")

    if env_config["reddit_client_id"]:
        settings["reddit_client_id"] = env_config["reddit_client_id"]
        updated = True
        logger.info("✅ 添加 Reddit 客户端ID")

    if env_config["reddit_client_secret"]:
        settings["reddit_client_secret"] = env_config["reddit_client_secret"]
        updated = True
        logger.info("✅ 添加 Reddit 客户端密钥")

    if env_config["reddit_user_agent"]:
        settings["reddit_user_agent"] = env_config["reddit_user_agent"]
        updated = True
        logger.info("✅ 添加 Reddit 用户代理")

    if updated:
        config_manager.save_settings(settings)
        logger.info("💾 系统设置已保存")
    else:
        logger.info("ℹ️ 系统设置无需更新")


def main():
    """主函数"""
    logger.info("🔄 .env 配置迁移工具")
    logger.info("=")

    # 加载 .env 配置
    env_config = load_env_config()
    if not env_config:
        return False

    logger.info("📋 检测到的 .env 配置:")
    for key, value in env_config.items():
        if "api_key" in key or "secret" in key:
            # 隐藏敏感信息
            display_value = f"***{value[-4:]}" if value else "未设置"
        else:
            display_value = value or "未设置"
        logger.info(f"  {key}: {display_value}")

    logger.info("\n🎯 开始迁移配置...")

    try:
        # 迁移模型配置
        migrate_model_configs(env_config)

        # 迁移系统设置
        migrate_system_settings(env_config)

        logger.info("\n🎉 配置迁移完成！")
        logger.info("\n💡 下一步:")
        logger.info("1. 启动Web界面: python -m streamlit run web/app.py")
        logger.info("2. 访问 '⚙️ 配置管理' 页面查看迁移结果")
        logger.info("3. 根据需要调整模型参数和定价配置")
        logger.info("4. 可以继续使用 .env 文件，也可以完全使用Web配置")

        return True

    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback

        logger.error(f"错误详情: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
