#!/usr/bin/env python3
"""
调试300750估值指标计算问题
"""

from tradingagents.config.database_manager import get_database_manager


def debug_valuation_data(stock_code):
    """调试估值数据"""
    print(f"=== 调试股票{stock_code}的估值数据 ===")

    try:
        db_manager = get_database_manager()

        if not db_manager.is_mongodb_available():
            print("❌ MongoDB不可用")
            return None

        client = db_manager.get_mongodb_client()
        db = client["tradingagents"]

        # 1. 检查stock_basic_info中的估值指标
        print("\n📊 1. 检查stock_basic_info中的估值指标:")
        basic_info_collection = db["stock_basic_info"]
        basic_info = basic_info_collection.find_one({"code": stock_code})

        if basic_info:
            print("  ✅ 找到基本信息")
            print(f"  股票名称: {basic_info.get('name', '未知')}")
            print(f"  当前股价: {basic_info.get('close', 'N/A')}")
            print(f"  PE: {basic_info.get('pe', 'N/A')}")
            print(f"  PB: {basic_info.get('pb', 'N/A')}")
            print(f"  PS: {basic_info.get('ps', 'N/A')}")
            print(f"  PE_TTM: {basic_info.get('pe_ttm', 'N/A')}")
            print(f"  总市值: {basic_info.get('total_mv', 'N/A')} 亿元")
        else:
            print("  ❌ 未找到基本信息")

        # 2. 检查stock_financial_data中的财务数据
        print("\n📊 2. 检查stock_financial_data中的财务数据:")
        financial_collection = db["stock_financial_data"]
        financial_doc = financial_collection.find_one({"code": stock_code})

        if financial_doc:
            print("  ✅ 找到财务数据")

            # 检查估值计算所需的关键字段
            key_fields = [
                "net_profit",  # 净利润
                "revenue",  # 营业收入
                "total_hldr_eqy_exc_min_int",  # 股东权益
                "money_cap",  # 总市值
                "roe",  # ROE
                "roa",  # ROA
                "gross_margin",  # 毛利率
                "netprofit_margin",  # 净利率
            ]

            print("  关键财务字段:")
            for field in key_fields:
                value = financial_doc.get(field)
                if value is not None:
                    if isinstance(value, (int, float)) and abs(value) > 1000000:
                        print(f"    {field}: {value:,.0f} ({value / 100000000:.2f}亿)")
                    else:
                        print(f"    {field}: {value}")
                else:
                    print(f"    {field}: None")

            # 检查是否有每股收益和每股净资产相关字段
            eps_fields = ["eps", "basic_eps", "diluted_eps", "基本每股收益"]
            bps_fields = ["bps", "book_value_per_share", "每股净资产", "每股净资产_最新股数"]

            print("\n  每股收益相关字段:")
            for field in eps_fields:
                value = financial_doc.get(field)
                if value is not None:
                    print(f"    {field}: {value}")

            print("\n  每股净资产相关字段:")
            for field in bps_fields:
                value = financial_doc.get(field)
                if value is not None:
                    print(f"    {field}: {value}")

            # 显示所有包含'share'或'per'的字段
            print('\n  所有包含"share"或"per"的字段:')
            for key, value in financial_doc.items():
                if "share" in key.lower() or "per" in key.lower():
                    print(f"    {key}: {value}")
        else:
            print("  ❌ 未找到财务数据")

        # 3. 手动计算估值指标
        print("\n📊 3. 手动计算估值指标:")
        if basic_info and financial_doc:
            current_price = basic_info.get("close", 0)
            total_mv = basic_info.get("total_mv", 0)  # 亿元
            net_profit = financial_doc.get("net_profit", 0)  # 元
            revenue = financial_doc.get("revenue", 0)  # 元
            total_equity = financial_doc.get("total_hldr_eqy_exc_min_int", 0)  # 元

            print(f"  当前股价: {current_price}")
            print(f"  总市值: {total_mv:.2f} 亿元")
            print(f"  净利润: {net_profit:,.0f} 元 ({net_profit / 100000000:.2f}亿)")
            print(f"  营业收入: {revenue:,.0f} 元 ({revenue / 100000000:.2f}亿)")
            print(f"  股东权益: {total_equity:,.0f} 元 ({total_equity / 100000000:.2f}亿)")

            # 计算PE (市值/净利润)
            if net_profit > 0 and total_mv > 0:
                pe_calculated = (total_mv * 100000000) / net_profit
                print(f"  计算PE: {total_mv:.2f}亿 / {net_profit / 100000000:.2f}亿 = {pe_calculated:.2f}")
            else:
                print("  无法计算PE (净利润或市值为0)")

            # 计算PB (市值/净资产)
            if total_equity > 0 and total_mv > 0:
                pb_calculated = (total_mv * 100000000) / total_equity
                print(f"  计算PB: {total_mv:.2f}亿 / {total_equity / 100000000:.2f}亿 = {pb_calculated:.2f}")
            else:
                print("  无法计算PB (净资产或市值为0)")

            # 计算PS (市值/营业收入)
            if revenue > 0 and total_mv > 0:
                ps_calculated = (total_mv * 100000000) / revenue
                print(f"  计算PS: {total_mv:.2f}亿 / {revenue / 100000000:.2f}亿 = {ps_calculated:.2f}")
            else:
                print("  无法计算PS (营业收入或市值为0)")

        return {"basic_info": basic_info, "financial_data": financial_doc}

    except Exception as e:
        print(f"调试时出错: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    debug_valuation_data("300750")
