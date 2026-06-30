"""
修复模拟交易账户的港股和美股初始资金

运行方式：
    python scripts/fix_paper_trading_initial_cash.py
    python scripts/fix_paper_trading_initial_cash.py --dry-run  # 仅预览，不实际修改
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_mongo_db, init_database

# 每个市场的初始资金
INITIAL_CASH_BY_MARKET = {
    "CNY": 1_000_000.0,  # A股：100万人民币
    "HKD": 1_000_000.0,  # 港股：100万港币
    "USD": 100_000.0,  # 美股：10万美元
}


async def fix_accounts(dry_run=False):
    """修复账户的港股和美股初始资金"""
    print("\n" + "=" * 60)
    print("💰 修复账户初始资金")
    print("=" * 60)

    db = get_mongo_db()
    collection = db["paper_accounts"]

    # 查找所有账户
    accounts = await collection.find({}).to_list(None)

    if not accounts:
        print("✅ 没有账户")
        return

    print(f"📋 找到 {len(accounts)} 个账户\n")

    fixed_count = 0
    skipped_count = 0

    for acc in accounts:
        user_id = acc.get("user_id")
        cash = acc.get("cash", {})

        # 检查是否需要修复
        needs_fix = False
        if isinstance(cash, dict):
            hkd = cash.get("HKD", 0.0)
            usd = cash.get("USD", 0.0)

            # 如果港股或美股资金为0，且没有持仓，则需要修复
            if hkd == 0.0 or usd == 0.0:
                # 检查是否有港股/美股持仓
                positions = (
                    await db["paper_positions"]
                    .find({"user_id": user_id, "market": {"$in": ["HK", "US"]}})
                    .to_list(None)
                )

                if not positions:
                    needs_fix = True

        if not needs_fix:
            print(f"⏭️  跳过账户 {user_id}（无需修复）")
            skipped_count += 1
            continue

        print(f"🔧 修复账户: {user_id}")
        print(
            f"   当前 - CNY: ¥{cash.get('CNY', 0):,.2f}, HKD: HK${cash.get('HKD', 0):,.2f}, USD: ${cash.get('USD', 0):,.2f}",
        )

        # 更新港股和美股资金（保留A股资金不变）
        new_cash = {
            "CNY": cash.get("CNY", INITIAL_CASH_BY_MARKET["CNY"]),
            "HKD": INITIAL_CASH_BY_MARKET["HKD"],
            "USD": INITIAL_CASH_BY_MARKET["USD"],
        }

        print(f"   修复后 - CNY: ¥{new_cash['CNY']:,.2f}, HKD: HK${new_cash['HKD']:,.2f}, USD: ${new_cash['USD']:,.2f}")

        if not dry_run:
            # 更新数据库
            await collection.update_one(
                {"user_id": user_id}, {"$set": {"cash": new_cash, "updated_at": datetime.utcnow().isoformat()}},
            )
            print("   ✅ 修复成功")
        else:
            print("   🔍 [DRY RUN] 将会更新")

        fixed_count += 1
        print()

    print("📊 修复统计:")
    print(f"   ✅ 修复: {fixed_count}")
    print(f"   ⏭️  跳过: {skipped_count}")
    print(f"   📝 总计: {len(accounts)}")


async def main():
    """主函数"""
    # 检查是否为 dry-run 模式
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("\n🔍 DRY RUN 模式：仅预览，不会实际修改数据库\n")

    print("\n🚀 开始修复模拟交易账户...")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 初始化数据库
    await init_database()

    # 修复账户
    await fix_accounts(dry_run)

    print("\n" + "=" * 60)
    print("✅ 修复完成！")
    print("=" * 60)

    if dry_run:
        print("\n💡 这是 DRY RUN 模式，没有实际修改数据")
        print("💡 要真正执行修复，请运行: python scripts/fix_paper_trading_initial_cash.py")
    else:
        print("\n✅ 账户初始资金已修复")
        print("✅ 现在港股和美股账户都有初始资金了")

    print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
