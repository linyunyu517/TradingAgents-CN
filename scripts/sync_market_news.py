#!/usr/bin/env python3
"""
同步市场新闻数据脚本

用法：
    python scripts/sync_market_news.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.worker.news_data_sync_service import get_news_data_sync_service


async def main():
    """主函数"""
    print("=" * 60)
    print("📰 开始同步市场新闻数据")
    print("=" * 60)

    try:
        # 获取同步服务
        sync_service = await get_news_data_sync_service()

        # 同步市场新闻（最近24小时）
        print("\n🔄 正在同步市场新闻...")
        print("⏰ 回溯时间：24小时")
        print("📊 每个数据源最大新闻数：50条")

        stats = await sync_service.sync_market_news(
            data_sources=None,  # 使用所有可用数据源
            hours_back=24,
            max_news_per_source=50,
        )

        # 显示同步结果
        print("\n" + "=" * 60)
        print("✅ 市场新闻同步完成！")
        print("=" * 60)
        print(f"📊 总处理数：{stats.total_processed}")
        print(f"✅ 成功保存：{stats.successful_saves}")
        print(f"❌ 保存失败：{stats.failed_saves}")
        print(f"⏭️  重复跳过：{stats.duplicate_skipped}")
        print(f"🔧 使用数据源：{', '.join(stats.sources_used)}")
        print(f"⏱️  耗时：{stats.duration_seconds:.2f}秒")
        print(f"📈 成功率：{stats.success_rate:.1f}%")
        print("=" * 60)

        if stats.successful_saves > 0:
            print(f"\n🎉 成功同步 {stats.successful_saves} 条市场新闻！")
        else:
            print("\n⚠️  没有同步到新的新闻数据")
            print("💡 可能的原因：")
            print("   1. 数据源没有配置（需要配置 Tushare Token）")
            print("   2. 数据库中已有最新数据")
            print("   3. 数据源暂时无法访问")

    except Exception as e:
        print(f"\n❌ 同步失败：{e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
