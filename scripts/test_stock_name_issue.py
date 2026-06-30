"""
测试市场分析时股票名称获取问题
"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def test_get_company_name():
    """测试从股票代码获取公司名称"""
    print("\n" + "=" * 60)
    print("测试：从股票代码获取公司名称")
    print("=" * 60)

    # 测试股票代码
    test_symbols = [
        "000001",  # 平安银行
        "600519",  # 贵州茅台
        "601127",  # 小康股份
        "688008",  # 澜起科技
    ]

    for symbol in test_symbols:
        print(f"\n{'=' * 60}")
        print(f"测试股票: {symbol}")
        print(f"{'=' * 60}")

        # 1. 测试 get_china_stock_info_unified
        print("\n1️⃣ 测试 get_china_stock_info_unified:")
        try:
            from tradingagents.dataflows.interface import get_china_stock_info_unified

            stock_info = get_china_stock_info_unified(symbol)
            print(f"返回结果:\n{stock_info}")

            # 检查是否包含股票名称
            if "股票名称:" in stock_info:
                name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                print(f"✅ 成功解析股票名称: {name}")
            else:
                print("❌ 返回结果中没有'股票名称:'字段")

        except Exception as e:
            print(f"❌ 调用失败: {e}")
            import traceback

            traceback.print_exc()

        # 2. 测试 market_analyst 中的 _get_company_name 函数
        print("\n2️⃣ 测试 market_analyst._get_company_name:")
        try:
            from tradingagents.agents.analysts.market_analyst import _get_company_name
            from tradingagents.utils.stock_utils import StockUtils

            market_info = StockUtils.get_market_info(symbol)
            company_name = _get_company_name(symbol, market_info)
            print(f"返回结果: {company_name}")

            if company_name.startswith("股票代码"):
                print("❌ 返回的是默认名称，说明获取失败")
            else:
                print("✅ 成功获取公司名称")

        except Exception as e:
            print(f"❌ 调用失败: {e}")
            import traceback

            traceback.print_exc()

        # 3. 测试 data_source_manager.get_china_stock_info_unified
        print("\n3️⃣ 测试 data_source_manager.get_china_stock_info_unified:")
        try:
            from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified

            info_dict = get_china_stock_info_unified(symbol)
            print(f"返回结果: {info_dict}")

            if info_dict and info_dict.get("name"):
                print(f"✅ 成功获取股票名称: {info_dict['name']}")
            else:
                print("❌ 返回结果中没有name字段或为空")

        except Exception as e:
            print(f"❌ 调用失败: {e}")
            import traceback

            traceback.print_exc()


def test_data_source_config():
    """测试数据源配置"""
    print("\n" + "=" * 60)
    print("测试：数据源配置")
    print("=" * 60)

    try:
        from tradingagents.dataflows.data_source_manager import get_data_source_manager

        manager = get_data_source_manager()

        print(f"\n当前数据源: {manager.current_source.value}")
        print(f"可用数据源: {[s.value for s in manager.available_sources]}")

        # 检查是否启用了 app cache
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled

            use_cache = use_app_cache_enabled(False)
            print(f"App Cache 启用状态: {use_cache}")
        except Exception as e:
            print(f"无法检查 App Cache 状态: {e}")

    except Exception as e:
        print(f"❌ 获取数据源配置失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("\n🔍 开始测试股票名称获取问题...")

    # 测试数据源配置
    test_data_source_config()

    # 测试股票名称获取
    test_get_company_name()

    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
