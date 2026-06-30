"""
恢复用户的分析师选择

将用户的分析师选择恢复为：['市场分析师', '基本面分析师', '新闻分析师']
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from app.core.database import get_mongo_db_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def restore_user_analysts():
    """恢复用户的分析师选择"""
    try:
        # 获取同步数据库连接
        db = get_mongo_db_sync()
        users_collection = db["users"]

        # 查找所有用户
        users = users_collection.find({})
        updated_count = 0

        for user in users:
            username = user.get("username", "unknown")
            preferences = user.get("preferences", {})

            # 恢复分析师选择为3位
            preferences["default_analysts"] = ["市场分析师", "基本面分析师", "新闻分析师"]

            # 更新用户
            users_collection.update_one({"_id": user["_id"]}, {"$set": {"preferences": preferences}})
            updated_count += 1
            logger.info(f"✅ 用户 {username} 分析师选择已恢复为: ['市场分析师', '基本面分析师', '新闻分析师']")

        logger.info(f"🎉 恢复完成！共更新 {updated_count} 个用户的分析师选择")

    except Exception as e:
        logger.error(f"❌ 恢复失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("🚀 开始恢复用户分析师选择...")
    restore_user_analysts()
    logger.info("✅ 恢复完成")
