"""
更新模型目录 - 添加价格信息

这个脚本会：
1. 删除现有的模型目录数据
2. 重新初始化包含价格信息的模型目录
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import db_manager
from app.services.config_service import ConfigService


async def main():
    """主函数"""
    print("=" * 60)
    print("更新模型目录 - 添加价格信息")
    print("=" * 60)
    print()

    try:
        # 初始化数据库连接
        print("🔄 正在初始化数据库连接...")
        await db_manager.init_mongodb()
        print("✅ 数据库连接成功")
        print()

        # 获取配置服务
        config_service = ConfigService(db_manager=db_manager)

        # 删除现有的模型目录
        print("🗑️  正在删除现有的模型目录...")
        db = db_manager.mongo_db
        catalog_collection = db["model_catalog"]
        result = await catalog_collection.delete_many({})
        print(f"✅ 已删除 {result.deleted_count} 条记录")
        print()

        # 重新初始化模型目录
        print("📦 正在初始化包含价格信息的模型目录...")
        success = await config_service.init_default_model_catalog()

        if success:
            print()
            print("=" * 60)
            print("✅ 模型目录更新成功！")
            print("=" * 60)
            print()
            print("现在模型目录包含以下信息：")
            print("  • 模型名称和显示名称")
            print("  • 输入/输出价格（每1K tokens）")
            print("  • 上下文长度")
            print("  • 货币单位（CNY/USD）")
            print()
            print("您可以在前端界面查看和编辑这些信息：")
            print("  设置 → 系统配置 → 配置管理 → 模型目录")
            print()
        else:
            print()
            print("=" * 60)
            print("❌ 模型目录更新失败")
            print("=" * 60)
            return 1

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ 更新失败: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
