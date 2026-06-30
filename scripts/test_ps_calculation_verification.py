#!/usr/bin/env python3
"""
PS（市销率）计算验证程序

用途：
1. 从数据库获取实际财务数据
2. 手动计算 PS 并与系统计算结果对比
3. 验证三个数据源的 PS 计算是否正确

使用方法：
    python scripts/test_ps_calculation_verification.py 600036
    python scripts/test_ps_calculation_verification.py 000001
    python scripts/test_ps_calculation_verification.py 600036 000001 000002
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# 加载环境变量
load_dotenv()


class PSCalculationVerifier:
    """PS 计算验证器"""

    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        """连接数据库"""
        # 优先使用 MONGODB_CONNECTION_STRING
        mongo_uri = os.getenv("MONGODB_CONNECTION_STRING")
        db_name = os.getenv("MONGODB_DATABASE_NAME") or os.getenv("MONGODB_DATABASE", "tradingagents")

        if not mongo_uri:
            # 从环境变量构建连接 URI
            mongo_host = os.getenv("MONGODB_HOST", "localhost")
            mongo_port = int(os.getenv("MONGODB_PORT", "27017"))
            mongo_user = os.getenv("MONGODB_USERNAME", "")
            mongo_password = os.getenv("MONGODB_PASSWORD", "")
            mongo_auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")

            # 构建连接 URI
            if mongo_user and mongo_password:
                mongo_uri = (
                    f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/?authSource={mongo_auth_source}"
                )
            else:
                mongo_uri = f"mongodb://{mongo_host}:{mongo_port}"

        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        print(f"✅ 已连接到数据库: {db_name}")

    async def close(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
            print("✅ 已关闭数据库连接")

    async def get_stock_info(self, code: str) -> dict[str, Any] | None:
        """获取股票基本信息"""
        stock_info = await self.db.stock_basic_info.find_one({"code": code})
        return stock_info

    async def get_financial_data(self, code: str) -> dict[str, Any] | None:
        """获取财务数据"""
        financial_data = await self.db.stock_financial_data.find_one({"code": code})
        return financial_data

    async def get_market_quote(self, code: str) -> dict[str, Any] | None:
        """获取最新行情"""
        quote = await self.db.market_quotes.find_one({"code": code})
        return quote

    def calculate_ps_manually(
        self, price: float, total_share: float, revenue: float, revenue_ttm: float | None = None,
    ) -> dict[str, Any]:
        """
        手动计算 PS

        Args:
            price: 股价（元）
            total_share: 总股本（万股）
            revenue: 营业收入（万元，单期）
            revenue_ttm: TTM 营业收入（万元，最近12个月）

        Returns:
            计算结果字典
        """
        # 计算市值（万元）
        market_cap = price * total_share
        market_cap_yi = market_cap / 10000  # 转换为亿元

        result = {
            "price": price,
            "total_share": total_share,
            "market_cap_wan": market_cap,
            "market_cap_yi": market_cap_yi,
            "revenue": revenue,
            "revenue_ttm": revenue_ttm,
        }

        # 使用单期营业收入计算 PS（错误方法）
        if revenue and revenue > 0:
            ps_single = market_cap / revenue
            result["ps_single"] = ps_single
            result["ps_single_str"] = f"{ps_single:.2f}倍"
        else:
            result["ps_single"] = None
            result["ps_single_str"] = "N/A"

        # 使用 TTM 营业收入计算 PS（正确方法）
        if revenue_ttm and revenue_ttm > 0:
            ps_ttm = market_cap / revenue_ttm
            result["ps_ttm"] = ps_ttm
            result["ps_ttm_str"] = f"{ps_ttm:.2f}倍"
        else:
            result["ps_ttm"] = None
            result["ps_ttm_str"] = "N/A"

        return result

    async def verify_stock(self, code: str):
        """验证单只股票的 PS 计算"""
        print("\n" + "=" * 100)
        print(f"📊 验证股票: {code}")
        print("=" * 100)

        # 1. 获取股票基本信息
        stock_info = await self.get_stock_info(code)
        if not stock_info:
            print(f"❌ 未找到股票基本信息: {code}")
            return

        print("\n【股票信息】")
        print(f"   代码: {stock_info.get('code')}")
        print(f"   名称: {stock_info.get('name')}")
        print(f"   总市值: {stock_info.get('total_mv')} 亿元")

        # 2. 获取财务数据
        financial_data = await self.get_financial_data(code)
        if not financial_data:
            print(f"❌ 未找到财务数据: {code}")
            return

        # 从 raw_data.balance_sheet 中获取总股本
        total_share_yuan = None
        raw_data = financial_data.get("raw_data", {})
        balance_sheets = raw_data.get("balance_sheet", [])
        if balance_sheets and len(balance_sheets) > 0:
            total_share_yuan = balance_sheets[0].get("total_share")  # 单位：股

        print("\n【财务数据】")
        print(f"   数据来源: {financial_data.get('data_source', 'Unknown')}")
        print(f"   报告期: {financial_data.get('report_period', 'Unknown')}")

        # Tushare 数据单位是"元"，需要转换
        revenue_yuan = financial_data.get("revenue")  # 元
        revenue_ttm_yuan = financial_data.get("revenue_ttm")  # 元
        net_profit_yuan = financial_data.get("net_profit")  # 元
        total_equity_yuan = financial_data.get("total_equity")  # 元

        print(
            f"   营业收入（单期）: {revenue_yuan / 100000000:.2f} 亿元" if revenue_yuan else "   营业收入（单期）: N/A",
        )
        print(
            f"   营业收入（TTM）: {revenue_ttm_yuan / 100000000:.2f} 亿元"
            if revenue_ttm_yuan
            else "   营业收入（TTM）: N/A",
        )
        print(
            f"   净利润（单期）: {net_profit_yuan / 100000000:.2f} 亿元"
            if net_profit_yuan
            else "   净利润（单期）: N/A",
        )
        print(f"   净资产: {total_equity_yuan / 100000000:.2f} 亿元" if total_equity_yuan else "   净资产: N/A")
        print(f"   总股本: {total_share_yuan / 100000000:.2f} 亿股" if total_share_yuan else "   总股本: N/A")

        # 3. 获取最新行情
        quote = await self.get_market_quote(code)
        if not quote:
            print(f"❌ 未找到行情数据: {code}")
            return

        price = quote.get("close") or quote.get("price")
        if not price:
            print("❌ 无法获取股价")
            return

        print("\n【行情数据】")
        print(f"   最新价: {price} 元")
        print(f"   更新时间: {quote.get('updated_at', 'Unknown')}")

        # 4. 手动计算 PS
        if not total_share_yuan or total_share_yuan <= 0:
            print(f"❌ 总股本数据无效: {total_share_yuan}")
            return

        if not revenue_yuan or revenue_yuan <= 0:
            print(f"❌ 营业收入数据无效: {revenue_yuan}")
            return

        print("\n【手动计算 PS】")

        # 计算市值（亿元）
        market_cap_yi = price * total_share_yuan / 100000000  # 股价（元）× 总股本（股）/ 1亿

        # 转换营业收入为亿元
        revenue_yi = revenue_yuan / 100000000
        revenue_ttm_yi = revenue_ttm_yuan / 100000000 if revenue_ttm_yuan else None

        print("   市值 = 股价 × 总股本")
        print(f"        = {price} 元 × {total_share_yuan / 100000000:.2f} 亿股")
        print(f"        = {market_cap_yi:.2f} 亿元")

        # 计算 PS（单期）
        ps_single = market_cap_yi / revenue_yi
        print("\n   PS（单期）= 市值 / 营业收入（单期）")
        print(f"            = {market_cap_yi:.2f} 亿元 / {revenue_yi:.2f} 亿元")
        print(f"            = {ps_single:.2f}倍")

        # 计算 PS（TTM）
        if revenue_ttm_yi:
            ps_ttm = market_cap_yi / revenue_ttm_yi
            print("\n   PS（TTM）= 市值 / 营业收入（TTM）")
            print(f"           = {market_cap_yi:.2f} 亿元 / {revenue_ttm_yi:.2f} 亿元")
            print(f"           = {ps_ttm:.2f}倍")

            # 计算差异
            diff_ratio = ps_single / ps_ttm
            print(f"\n   ⚠️ 差异: PS（单期）/ PS（TTM）= {diff_ratio:.2f} 倍")
            if diff_ratio > 1.5:
                print(f"      使用单期数据会高估 PS 约 {(diff_ratio - 1) * 100:.1f}%")
        else:
            print("\n   ⚠️ 警告: 没有 TTM 数据，无法计算准确的 PS")
            ps_ttm = None

        # 5. 对比数据库中存储的 PS
        stored_ps = financial_data.get("ps")
        if stored_ps:
            print("\n【数据库存储的 PS】")
            print(f"   PS: {stored_ps}")

            # 尝试提取数值
            try:
                if isinstance(stored_ps, str):
                    stored_ps_value = float(stored_ps.replace("倍", "").strip())
                else:
                    stored_ps_value = float(stored_ps)

                # 对比
                if ps_ttm:
                    diff = abs(stored_ps_value - ps_ttm)
                    if diff < 0.1:
                        print(f"   ✅ 与手动计算的 PS（TTM）一致: 差异 {diff:.3f}")
                    else:
                        print(f"   ⚠️ 与手动计算的 PS（TTM）不一致: 差异 {diff:.3f}")

                diff = abs(stored_ps_value - ps_single)
                if diff < 0.1:
                    print(f"   ⚠️ 与手动计算的 PS（单期）一致: 差异 {diff:.3f}")
                    if not ps_ttm or abs(stored_ps_value - ps_ttm) > 0.1:
                        print("      这说明数据库使用的是单期数据，不是 TTM！")
            except Exception as e:
                print(f"   ⚠️ 无法解析存储的 PS 值: {stored_ps}, 错误: {e}")

        # 6. 对比 stock_basic_info 中的 PE/PB
        print("\n【stock_basic_info 中的估值指标】")
        print(f"   PE: {stock_info.get('pe')}")
        print(f"   PE_TTM: {stock_info.get('pe_ttm')}")
        print(f"   PB: {stock_info.get('pb')}")
        print(f"   总市值: {stock_info.get('total_mv')} 亿元")

        # 对比市值
        stored_mv = stock_info.get("total_mv")
        if stored_mv:
            mv_diff = abs(stored_mv - market_cap_yi)
            if mv_diff < 1:
                print(f"   ✅ 市值一致: 差异 {mv_diff:.2f} 亿元")
            else:
                print(f"   ⚠️ 市值不一致: 差异 {mv_diff:.2f} 亿元")
                print(f"      数据库: {stored_mv:.2f} 亿元")
                print(f"      手动计算: {market_cap_yi:.2f} 亿元")

        # 7. 总结
        print("\n【验证结论】")
        if revenue_ttm_yi:
            print("   ✅ 有 TTM 数据")
            print(f"   ✅ 正确的 PS 应该是: {ps_ttm:.2f}倍")
            if ps_single / ps_ttm > 1.5:
                print("   ⚠️ 如果使用单期数据，PS 会被高估")
        else:
            print("   ⚠️ 没有 TTM 数据")
            print(f"   ⚠️ 当前只能使用单期数据: {ps_single:.2f}倍")
            print("   ⚠️ 建议重新同步财务数据以获取 TTM 数据")


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python scripts/test_ps_calculation_verification.py <股票代码1> [股票代码2] ...")
        print("\n示例:")
        print("  python scripts/test_ps_calculation_verification.py 600036")
        print("  python scripts/test_ps_calculation_verification.py 000001 000002 600036")
        sys.exit(1)

    stock_codes = sys.argv[1:]

    print("=" * 100)
    print("📊 PS（市销率）计算验证程序")
    print("=" * 100)
    print(f"验证股票: {', '.join(stock_codes)}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    verifier = PSCalculationVerifier()

    try:
        await verifier.connect()

        for code in stock_codes:
            await verifier.verify_stock(code)

        print("\n" + "=" * 100)
        print("✅ 验证完成")
        print("=" * 100)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await verifier.close()


if __name__ == "__main__":
    asyncio.run(main())
