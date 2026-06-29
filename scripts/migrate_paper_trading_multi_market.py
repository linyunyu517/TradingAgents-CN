"""
模拟交易数据库迁移脚本：支持多市场和多货币

运行方式：
    python scripts/migrate_paper_trading_multi_market.py
    python scripts/migrate_paper_trading_multi_market.py --dry-run  # 仅预览，不实际修改
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_mongo_db, init_database


async def migrate_accounts(dry_run=False):
    """迁移账户表：单一现金 -> 多货币"""
    print("\n" + "=" * 60)
    print("📊 迁移账户表 (paper_accounts)")
    print("=" * 60)

    db = get_mongo_db()
    collection = db["paper_accounts"]

    # 查找所有账户
    accounts = await collection.find({}).to_list(None)

    if not accounts:
        print("✅ 没有需要迁移的账户")
        return

    print(f"📋 找到 {len(accounts)} 个账户需要迁移\n")

    migrated_count = 0
    skipped_count = 0

    for acc in accounts:
        user_id = acc.get("user_id")

        # 检查是否已经是新格式
        if isinstance(acc.get("cash"), dict):
            print(f"⏭️  跳过账户 {user_id}（已是新格式）")
            skipped_count += 1
            continue

        # 获取旧的现金和盈亏
        old_cash = float(acc.get("cash", 0.0))
        old_pnl = float(acc.get("realized_pnl", 0.0))

        print(f"🔄 迁移账户: {user_id}")
        print(f"   旧格式 - 现金: ¥{old_cash:,.2f}, 盈亏: ¥{old_pnl:,.2f}")

        # 新的多货币格式
        # 每个市场的初始资金
        INITIAL_CASH_BY_MARKET = {
            "CNY": 1_000_000.0,  # A股：100万人民币
            "HKD": 1_000_000.0,  # 港股：100万港币
            "USD": 100_000.0,  # 美股：10万美元
        }

        new_cash = {"CNY": old_cash, "HKD": INITIAL_CASH_BY_MARKET["HKD"], "USD": INITIAL_CASH_BY_MARKET["USD"]}

        new_pnl = {"CNY": old_pnl, "HKD": 0.0, "USD": 0.0}

        # 账户设置
        settings = {"auto_currency_conversion": False, "default_market": "CN"}

        print(f"   新格式 - CNY: ¥{new_cash['CNY']:,.2f}, HKD: HK${new_cash['HKD']:,.2f}, USD: ${new_cash['USD']:,.2f}")

        if not dry_run:
            # 更新数据库
            await collection.update_one(
                {"_id": acc["_id"]},
                {
                    "$set": {
                        "cash": new_cash,
                        "realized_pnl": new_pnl,
                        "settings": settings,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                },
            )
            print("   ✅ 迁移成功")
        else:
            print("   🔍 [DRY RUN] 将会更新")

        migrated_count += 1
        print()

    print("📊 迁移统计:")
    print(f"   ✅ 迁移: {migrated_count}")
    print(f"   ⏭️  跳过: {skipped_count}")
    print(f"   📝 总计: {len(accounts)}")


async def migrate_positions(dry_run=False):
    """迁移持仓表：添加市场和货币字段"""
    print("\n" + "=" * 60)
    print("📊 迁移持仓表 (paper_positions)")
    print("=" * 60)

    db = get_mongo_db()
    collection = db["paper_positions"]

    # 查找所有持仓
    positions = await collection.find({}).to_list(None)

    if not positions:
        print("✅ 没有需要迁移的持仓")
        return

    print(f"📋 找到 {len(positions)} 个持仓需要迁移\n")

    migrated_count = 0
    skipped_count = 0

    for pos in positions:
        code = pos.get("code")
        user_id = pos.get("user_id")

        # 检查是否已经有市场字段
        if "market" in pos:
            print(f"⏭️  跳过持仓 {user_id}/{code}（已有市场字段）")
            skipped_count += 1
            continue

        quantity = pos.get("quantity", 0)
        avg_cost = pos.get("avg_cost", 0.0)

        print(f"🔄 迁移持仓: {user_id}/{code}")
        print(f"   数量: {quantity}, 成本: ¥{avg_cost:.2f}")

        # 假设旧数据都是A股
        market = "CN"
        currency = "CNY"

        print(f"   添加字段 - 市场: {market}, 货币: {currency}")

        if not dry_run:
            # 更新数据库
            await collection.update_one(
                {"_id": pos["_id"]},
                {
                    "$set": {
                        "market": market,
                        "currency": currency,
                        "available_qty": quantity,  # 初始可用数量等于总数量
                        "frozen_qty": 0,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                },
            )
            print("   ✅ 迁移成功")
        else:
            print("   🔍 [DRY RUN] 将会更新")

        migrated_count += 1
        print()

    print("📊 迁移统计:")
    print(f"   ✅ 迁移: {migrated_count}")
    print(f"   ⏭️  跳过: {skipped_count}")
    print(f"   📝 总计: {len(positions)}")


async def migrate_orders(dry_run=False):
    """迁移订单表：添加市场、货币和手续费字段"""
    print("\n" + "=" * 60)
    print("📊 迁移订单表 (paper_orders)")
    print("=" * 60)

    db = get_mongo_db()
    collection = db["paper_orders"]

    # 查找所有订单
    orders = await collection.find({}).to_list(None)

    if not orders:
        print("✅ 没有需要迁移的订单")
        return

    print(f"📋 找到 {len(orders)} 个订单需要迁移\n")

    migrated_count = 0
    skipped_count = 0

    for order in orders:
        str(order.get("_id"))
        order.get("code")

        # 检查是否已经有市场字段
        if "market" in order:
            skipped_count += 1
            continue

        side = order.get("side")
        amount = order.get("amount", 0.0)

        # 假设旧数据都是A股
        market = "CN"
        currency = "CNY"

        # 简单估算手续费（实际应该根据市场规则计算）
        commission = max(amount * 0.0003, 5.0)  # 佣金
        if side == "sell":
            commission += amount * 0.001  # 印花税
        commission = round(commission, 2)

        if not dry_run:
            # 更新数据库
            await collection.update_one(
                {"_id": order["_id"]}, {"$set": {"market": market, "currency": currency, "commission": commission}},
            )

        migrated_count += 1

    print("📊 迁移统计:")
    print(f"   ✅ 迁移: {migrated_count}")
    print(f"   ⏭️  跳过: {skipped_count}")
    print(f"   📝 总计: {len(orders)}")


async def migrate_trades(dry_run=False):
    """迁移成交记录表：添加市场、货币和手续费字段"""
    print("\n" + "=" * 60)
    print("📊 迁移成交记录表 (paper_trades)")
    print("=" * 60)

    db = get_mongo_db()
    collection = db["paper_trades"]

    # 查找所有成交记录
    trades = await collection.find({}).to_list(None)

    if not trades:
        print("✅ 没有需要迁移的成交记录")
        return

    print(f"📋 找到 {len(trades)} 个成交记录需要迁移\n")

    migrated_count = 0
    skipped_count = 0

    for trade in trades:
        # 检查是否已经有市场字段
        if "market" in trade:
            skipped_count += 1
            continue

        side = trade.get("side")
        amount = trade.get("amount", 0.0)

        # 假设旧数据都是A股
        market = "CN"
        currency = "CNY"

        # 简单估算手续费
        commission = max(amount * 0.0003, 5.0)
        if side == "sell":
            commission += amount * 0.001
        commission = round(commission, 2)

        if not dry_run:
            # 更新数据库
            await collection.update_one(
                {"_id": trade["_id"]}, {"$set": {"market": market, "currency": currency, "commission": commission}},
            )

        migrated_count += 1

    print("📊 迁移统计:")
    print(f"   ✅ 迁移: {migrated_count}")
    print(f"   ⏭️  跳过: {skipped_count}")
    print(f"   📝 总计: {len(trades)}")


async def main():
    """主函数"""
    # 初始化数据库连接
    await init_database()

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("\n" + "🔍 " + "=" * 58)
        print("🔍 DRY RUN 模式：仅预览，不会实际修改数据")
        print("🔍 " + "=" * 58)

    print("\n🚀 开始迁移模拟交易数据库...")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 迁移各个表
        await migrate_accounts(dry_run)
        await migrate_positions(dry_run)
        await migrate_orders(dry_run)
        await migrate_trades(dry_run)

        print("\n" + "=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)

        if dry_run:
            print("\n💡 提示: 这是 DRY RUN 模式，数据未实际修改")
            print("💡 要执行实际迁移，请运行: python scripts/migrate_paper_trading_multi_market.py")
        else:
            print("\n✅ 所有数据已成功迁移到新格式")
            print("✅ 现在可以使用多市场模拟交易功能了")

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
