"""手动触发定价配置同步"""

import asyncio

from app.core.config_bridge import _sync_pricing_config_from_db
from app.core.database import init_database


async def main():
    """主函数"""
    print("🔄 初始化数据库连接...")
    await init_database()

    print("🔄 从数据库同步定价配置...")
    await _sync_pricing_config_from_db()

    print("✅ 同步完成！")


if __name__ == "__main__":
    asyncio.run(main())
