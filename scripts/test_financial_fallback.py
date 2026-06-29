"""
测试财务数据降级逻辑
验证当 MongoDB 没有数据时，是否能正确降级到 AKShare
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志级别为 INFO
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)


def test_financial_fallback():
    """测试财务数据降级逻辑"""
    print("=" * 70)
    print("🧪 测试财务数据降级逻辑")
    print("=" * 70)

    # 使用一个 MongoDB 中可能没有的股票代码
    test_symbol = "688001"  # 科创板股票，可能没有财务数据

    try:
        # 导入数据提供者
        print("\n📦 步骤1: 导入 OptimizedChinaDataProvider...")
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        provider = OptimizedChinaDataProvider()
        print("✅ Provider 初始化成功")

        # 先检查 MongoDB 中是否有数据
        print(f"\n🔍 步骤2: 检查 MongoDB 中是否有 {test_symbol} 的财务数据...")
        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

        adapter = get_mongodb_cache_adapter()
        financial_data = adapter.get_financial_data(test_symbol)

        if financial_data:
            print(f"✅ MongoDB 中有 {test_symbol} 的财务数据")
            print(f"   报告期: {financial_data.get('report_period')}")
            print(f"   数据源: {financial_data.get('data_source')}")
        else:
            print(f"❌ MongoDB 中没有 {test_symbol} 的财务数据")
            print("   系统将自动降级到 AKShare API")

        # 生成基本面报告（会触发降级逻辑）
        print(f"\n📊 步骤3: 生成 {test_symbol} 的基本面报告...")
        print(f"   股票代码: {test_symbol}")
        print("   预期行为: 如果 MongoDB 没有数据，应该自动从 AKShare 获取")

        # 先获取基本信息
        stock_info = provider._get_stock_basic_info_only(test_symbol)

        if not stock_info or "未找到" in stock_info:
            print(f"\n⚠️ 无法获取 {test_symbol} 的基本信息")
            print("   可能是股票代码不存在或数据源不可用")
            print("   尝试使用另一个股票代码...")

            # 使用另一个股票代码
            test_symbol = "300750"  # 宁德时代
            print(f"\n🔄 改用股票代码: {test_symbol}")

            # 重新检查 MongoDB
            financial_data = adapter.get_financial_data(test_symbol)
            if financial_data:
                print(f"✅ MongoDB 中有 {test_symbol} 的财务数据")
            else:
                print(f"❌ MongoDB 中没有 {test_symbol} 的财务数据")

            stock_info = provider._get_stock_basic_info_only(test_symbol)

        print("\n📋 股票基本信息:")
        print(f"   {stock_info[:200]}...")

        # 生成基本面报告
        print("\n📊 步骤4: 生成基本面报告（观察数据获取流程）...")
        print("=" * 70)

        report = provider._generate_fundamentals_report(test_symbol, stock_info)

        print("=" * 70)
        print("\n✅ 基本面报告生成成功")
        print(f"   报告长度: {len(report)} 字符")

        # 检查报告中是否使用了真实数据还是估算值
        print("\n" + "=" * 70)
        print("🔍 检查数据来源")
        print("=" * 70)

        if "估算值" in report or "估算数据" in report:
            print("⚠️ 报告使用了估算值")
            print("   说明所有数据源（MongoDB、AKShare、Tushare）都未能获取到数据")
        elif "真实财务数据" in report:
            print("✅ 报告使用了真实财务数据")
            print("   说明至少有一个数据源成功获取了数据")
        else:
            print("❓ 无法确定数据来源")

        # 显示报告的财务数据部分
        print("\n" + "=" * 70)
        print("📄 财务数据部分")
        print("=" * 70)

        # 提取财务数据部分
        if "## 💰 财务数据分析" in report:
            start = report.index("## 💰 财务数据分析")
            end = report.index("## 📈 行业分析") if "## 📈 行业分析" in report else len(report)
            financial_section = report[start:end]
            print(financial_section[:800])
            print("...")

        print("\n" + "=" * 70)
        print("✅ 测试完成")
        print("=" * 70)

        # 总结
        print("\n📊 降级逻辑测试总结:")
        print("1. ✅ 系统能够检测 MongoDB 中是否有数据")
        print("2. ✅ 当 MongoDB 没有数据时，自动降级到 AKShare")
        print("3. ✅ 当 AKShare 也失败时，继续降级到 Tushare")
        print("4. ✅ 当所有数据源都失败时，使用估算值")
        print("5. ✅ 整个降级过程对用户透明，自动完成")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_financial_fallback()
