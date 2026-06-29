"""
初始化模拟交易市场规则配置

运行方式：
    python scripts/init_paper_trading_market_rules.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_mongo_db, init_database

# 市场规则配置
MARKET_RULES = [
    {
        "market": "CN",
        "market_name": "A股市场",
        "currency": "CNY",
        "rules": {
            "t_plus": 1,  # T+1交易
            "price_limit": {
                "enabled": True,
                "up_limit": 10.0,  # 涨停 10%
                "down_limit": -10.0,  # 跌停 -10%
                "st_up_limit": 5.0,  # ST股涨停 5%
                "st_down_limit": -5.0,  # ST股跌停 -5%
                "kcb_up_limit": 20.0,  # 科创板涨停 20%
                "kcb_down_limit": -20.0,  # 科创板跌停 -20%
            },
            "lot_size": 100,  # 最小交易单位（手）
            "min_price_tick": 0.01,  # 最小报价单位
            "commission": {
                "rate": 0.0003,  # 佣金费率 0.03%
                "min": 5.0,  # 最低佣金 5元
                "stamp_duty_rate": 0.001,  # 印花税 0.1%（仅卖出）
                "transfer_fee_rate": 0.00002,  # 过户费 0.002%
            },
            "trading_hours": {
                "timezone": "Asia/Shanghai",
                "sessions": [{"open": "09:30", "close": "11:30"}, {"open": "13:00", "close": "15:00"}],
                "call_auction": [
                    {"open": "09:15", "close": "09:25"},  # 开盘集合竞价
                    {"open": "14:57", "close": "15:00"},  # 收盘集合竞价
                ],
            },
            "short_selling": {
                "enabled": False,  # 不支持做空（融券需要特殊权限）
            },
        },
    },
    {
        "market": "HK",
        "market_name": "港股市场",
        "currency": "HKD",
        "rules": {
            "t_plus": 0,  # T+0交易
            "price_limit": {
                "enabled": False,  # 无涨跌停限制
            },
            "lot_size": None,  # 每只股票不同，需查询
            "min_price_tick": 0.01,  # 最小报价单位（根据价格区间不同）
            "commission": {
                "rate": 0.0003,  # 佣金费率 0.03%
                "min": 3.0,  # 最低佣金 3港币
                "stamp_duty_rate": 0.0013,  # 印花税 0.13%
                "transaction_levy_rate": 0.00005,  # 交易征费 0.005%
                "trading_fee_rate": 0.00005,  # 交易费 0.005%
                "settlement_fee_rate": 0.00002,  # 结算费 0.002%
            },
            "trading_hours": {
                "timezone": "Asia/Hong_Kong",
                "sessions": [{"open": "09:30", "close": "12:00"}, {"open": "13:00", "close": "16:00"}],
                "call_auction": [
                    {"open": "09:00", "close": "09:30"},  # 开市前时段
                    {"open": "16:00", "close": "16:10"},  # 收市竞价时段
                ],
            },
            "short_selling": {
                "enabled": True,
                "margin_requirement": 1.4,  # 保证金要求 140%
            },
        },
    },
    {
        "market": "US",
        "market_name": "美股市场",
        "currency": "USD",
        "rules": {
            "t_plus": 0,  # T+0交易
            "price_limit": {
                "enabled": False,  # 无涨跌停限制
            },
            "lot_size": 1,  # 1股起
            "min_price_tick": 0.01,  # 最小报价单位
            "commission": {
                "rate": 0.0,  # 零佣金
                "min": 0.0,
                "sec_fee_rate": 0.0000278,  # SEC费用（仅卖出）
            },
            "trading_hours": {
                "timezone": "America/New_York",
                "sessions": [{"open": "09:30", "close": "16:00"}],
                "extended_hours": {
                    "pre_market": {"open": "04:00", "close": "09:30"},
                    "after_hours": {"open": "16:00", "close": "20:00"},
                },
            },
            "short_selling": {
                "enabled": True,
                "pdt_rule": True,  # Pattern Day Trader规则
                "min_account_equity": 25000,  # PDT最低账户净值（美元）
            },
        },
    },
]


async def init_market_rules():
    """初始化市场规则配置"""
    print("🚀 开始初始化模拟交易市场规则...")

    db = get_mongo_db()
    collection = db["paper_market_rules"]

    # 检查是否已存在配置
    existing_count = await collection.count_documents({})
    if existing_count > 0:
        print(f"⚠️  已存在 {existing_count} 条市场规则配置")
        response = input("是否覆盖现有配置？(y/n): ")
        if response.lower() != "y":
            print("❌ 取消初始化")
            return

        # 删除现有配置
        result = await collection.delete_many({})
        print(f"🗑️  已删除 {result.deleted_count} 条旧配置")

    # 插入新配置
    result = await collection.insert_many(MARKET_RULES)
    print(f"✅ 成功插入 {len(result.inserted_ids)} 条市场规则配置")

    # 显示配置详情
    print("\n📋 市场规则配置详情：")
    for rule in MARKET_RULES:
        market = rule["market"]
        market_name = rule["market_name"]
        currency = rule["currency"]
        t_plus = rule["rules"]["t_plus"]
        lot_size = rule["rules"]["lot_size"]

        print(f"\n  {market} - {market_name}")
        print(f"    货币: {currency}")
        print(f"    交易制度: T+{t_plus}")
        print(f"    最小交易单位: {lot_size or '每股不同'}")
        print(f"    涨跌停: {'是' if rule['rules']['price_limit']['enabled'] else '否'}")
        print(f"    做空: {'支持' if rule['rules']['short_selling']['enabled'] else '不支持'}")

    print("\n✅ 市场规则初始化完成！")


async def show_market_rules():
    """显示当前市场规则配置"""
    print("📋 当前市场规则配置：\n")

    db = get_mongo_db()
    collection = db["paper_market_rules"]

    rules = await collection.find({}).to_list(None)

    if not rules:
        print("❌ 未找到市场规则配置，请先运行初始化")
        return

    for rule in rules:
        market = rule["market"]
        market_name = rule["market_name"]
        currency = rule["currency"]

        print(f"{'=' * 60}")
        print(f"市场: {market} - {market_name}")
        print(f"货币: {currency}")
        print(f"{'=' * 60}")

        rules_data = rule["rules"]

        # 交易制度
        print("\n📅 交易制度:")
        print(f"  T+{rules_data['t_plus']}")

        # 涨跌停
        print("\n📊 涨跌停限制:")
        if rules_data["price_limit"]["enabled"]:
            print("  启用")
            print(f"  普通股票: {rules_data['price_limit']['up_limit']}% / {rules_data['price_limit']['down_limit']}%")
            if "st_up_limit" in rules_data["price_limit"]:
                print(
                    f"  ST股票: {rules_data['price_limit']['st_up_limit']}% / {rules_data['price_limit']['st_down_limit']}%",
                )
        else:
            print("  无限制")

        # 交易单位
        print("\n📦 交易单位:")
        lot_size = rules_data["lot_size"]
        print(f"  最小交易单位: {lot_size or '每股不同'}")
        print(f"  最小报价单位: {rules_data['min_price_tick']}")

        # 手续费
        print("\n💰 手续费:")
        commission = rules_data["commission"]
        print(f"  佣金费率: {commission['rate'] * 100:.3f}%")
        print(f"  最低佣金: {commission['min']} {currency}")
        if "stamp_duty_rate" in commission:
            print(f"  印花税: {commission['stamp_duty_rate'] * 100:.3f}% (仅卖出)")
        if "sec_fee_rate" in commission:
            print(f"  SEC费用: {commission['sec_fee_rate'] * 100:.5f}% (仅卖出)")

        # 交易时间
        print(f"\n🕐 交易时间 ({rules_data['trading_hours']['timezone']}):")
        for session in rules_data["trading_hours"]["sessions"]:
            print(f"  {session['open']} - {session['close']}")

        # 做空
        print("\n📉 做空:")
        if rules_data["short_selling"]["enabled"]:
            print("  支持")
            if "margin_requirement" in rules_data["short_selling"]:
                print(f"  保证金要求: {rules_data['short_selling']['margin_requirement'] * 100:.0f}%")
        else:
            print("  不支持")

        print()


async def main():
    """主函数"""
    # 初始化数据库连接
    await init_database()

    if len(sys.argv) > 1 and sys.argv[1] == "show":
        await show_market_rules()
    else:
        await init_market_rules()


if __name__ == "__main__":
    asyncio.run(main())
