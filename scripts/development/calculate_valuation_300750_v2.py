#!/usr/bin/env python3
"""
计算股票300750的估值指标 - 改进版本
"""

from tradingagents.config.database_manager import get_database_manager


def calculate_valuation_ratios_v2(stock_code):
    """计算估值比率 - 使用正确的数据源"""
    print(f"=== 计算股票{stock_code}的估值指标 (改进版本) ===")

    try:
        db_manager = get_database_manager()

        if not db_manager.is_mongodb_available():
            print("❌ MongoDB不可用")
            return None

        client = db_manager.get_mongodb_client()
        db = client["tradingagents"]

        # 1. 从stock_basic_info获取基本信息和估值指标
        basic_info_collection = db["stock_basic_info"]
        basic_info = basic_info_collection.find_one({"code": stock_code})

        if basic_info:
            print("✅ 找到基本信息数据")
            print(f"  股票名称: {basic_info.get('name', '未知')}")
            print(f"  行业: {basic_info.get('industry', '未知')}")
            print(f"  市场: {basic_info.get('market', '未知')}")

            # 显示已有的估值指标
            valuation_fields = ["pe", "pb", "ps", "pe_ttm", "pb_mrq"]
            print("\n📊 已有估值指标:")
            for field in valuation_fields:
                if field in basic_info and basic_info[field] is not None:
                    print(f"  {field.upper()}: {basic_info[field]}")

            # 显示市值相关信息
            market_fields = ["total_mv", "circ_mv"]
            print("\n💰 市值信息:")
            for field in market_fields:
                if field in basic_info and basic_info[field] is not None:
                    print(f"  {field}: {basic_info[field]:.2f} 亿元")
        else:
            print("❌ 未找到基本信息数据")

        # 2. 从market_quotes获取最新股价
        market_quotes_collection = db["market_quotes"]
        market_quote = market_quotes_collection.find_one({"code": stock_code})

        if market_quote:
            print("\n✅ 找到市场报价数据")
            price_fields = ["close", "open", "high", "low"]
            for field in price_fields:
                if field in market_quote:
                    print(f"  {field}: {market_quote[field]}")
        else:
            print("\n❌ 未找到市场报价数据")

        # 3. 从stock_financial_data获取财务数据
        financial_collection = db["stock_financial_data"]
        financial_doc = financial_collection.find_one({"code": stock_code})

        if financial_doc:
            print("\n✅ 找到财务数据")

            # 显示关键财务指标
            financial_fields = ["net_profit", "revenue", "total_hldr_eqy_exc_min_int", "money_cap"]
            print("  关键财务指标:")
            for field in financial_fields:
                if field in financial_doc and financial_doc[field] is not None:
                    value = financial_doc[field]
                    if isinstance(value, (int, float)) and abs(value) > 1000000:
                        print(f"    {field}: {value:,.0f} ({value / 100000000:.2f}亿)")
                    else:
                        print(f"    {field}: {value}")
        else:
            print("\n❌ 未找到财务数据")

        # 4. 综合分析
        print("\n🎯 估值分析总结:")

        if basic_info:
            pe = basic_info.get("pe")
            pb = basic_info.get("pb")

            if pe is not None:
                print(f"  PE比率: {pe} ({'偏高' if pe > 30 else '偏低' if pe < 15 else '适中'})")

            if pb is not None:
                print(f"  PB比率: {pb} ({'偏高' if pb > 3 else '偏低' if pb < 1 else '适中'})")

            total_mv = basic_info.get("total_mv")
            if total_mv is not None:
                print(f"  总市值: {total_mv:.2f}亿元")

        return {"basic_info": basic_info, "market_quote": market_quote, "financial_data": financial_doc}

    except Exception as e:
        print(f"计算估值指标时出错: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    calculate_valuation_ratios_v2("300750")
