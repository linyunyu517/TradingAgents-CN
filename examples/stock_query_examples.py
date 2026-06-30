#!/usr/bin/env python3
"""
股票查询示例（增强版）
演示如何使用新的股票数据服务，支持完整的降级机制
"""

import os
import sys

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("default")

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from tradingagents.api.stock_api import (
        check_service_status,
        get_all_stocks,
        get_market_summary,
        get_stock_data,
        get_stock_info,
        search_stocks,
    )

    API_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ 新API不可用，使用传统方式: {e}")
    API_AVAILABLE = False
    # 回退到传统方式
    from tradingagents.dataflows.database_manager import get_database_manager

from datetime import datetime, timedelta


def demo_service_status():
    """
    演示服务状态检查
    """
    logger.info("\n=== 服务状态检查 ===")

    if not API_AVAILABLE:
        logger.error("❌ 新API不可用，跳过状态检查")
        return

    status = check_service_status()
    logger.info("📊 当前服务状态:")

    for key, value in status.items():
        if key == "service_available":
            icon = "✅" if value else "❌"
            logger.info(f"  {icon} 服务可用性: {value}")
        elif key == "mongodb_status":
            icon = "✅" if value == "connected" else "⚠️" if value == "disconnected" else "❌"
            logger.info(f"  {icon} MongoDB状态: {value}")
        elif key == "unified_api_status":
            icon = "✅" if value == "available" else "⚠️" if value == "limited" else "❌"
            logger.info(f"  {icon} 统一数据接口状态: {value}")
        else:
            logger.info(f"  📋 {key}: {value}")


def demo_single_stock_query():
    """
    演示单个股票查询（带降级机制）
    """
    logger.info("\n=== 单个股票查询示例 ===")

    stock_codes = ["000001", "000002", "600000", "300001"]

    for stock_code in stock_codes:
        logger.debug(f"\n🔍 查询股票 {stock_code}:")

        if API_AVAILABLE:
            # 使用新API
            stock_info = get_stock_info(stock_code)

            if "error" in stock_info:
                logger.error(f"  ❌ {stock_info['error']}")
                if "suggestion" in stock_info:
                    logger.info(f"  💡 {stock_info['suggestion']}")
            else:
                logger.info(f"  ✅ 代码: {stock_info.get('code')}")
                logger.info(f"  📝 名称: {stock_info.get('name')}")
                logger.info(f"  🏢 市场: {stock_info.get('market')}")
                logger.info(f"  📊 类别: {stock_info.get('category')}")
                logger.info(f"  🔗 数据源: {stock_info.get('source')}")
                logger.info(f"  🕒 更新时间: {stock_info.get('updated_at', 'N/A')[:19]}")
        else:
            # 使用传统方式
            logger.warning("  ⚠️ 使用传统查询方式")
            db_manager = get_database_manager()
            if db_manager.is_mongodb_available():
                try:
                    collection = db_manager.mongodb_db["stock_basic_info"]
                    stock = collection.find_one({"code": stock_code})
                    if stock:
                        logger.info(f"  ✅ 找到: {stock.get('name')}")
                    else:
                        logger.error("  ❌ 未找到股票信息")
                except Exception as e:
                    logger.error(f"  ❌ 查询失败: {e}")
            else:
                logger.error("  ❌ 数据库连接失败")


def demo_stock_search():
    """
    演示股票搜索功能
    """
    logger.info("\n=== 股票搜索示例 ===")

    if not API_AVAILABLE:
        logger.error("❌ 新API不可用，跳过搜索演示")
        return

    keywords = ["平安", "银行", "科技", "000001"]

    for keyword in keywords:
        logger.debug(f"\n🔍 搜索关键词: '{keyword}'")

        results = search_stocks(keyword)

        if not results or (len(results) == 1 and "error" in results[0]):
            logger.error("  ❌ 未找到匹配的股票")
            if results and "error" in results[0]:
                logger.info(f"  💡 {results[0].get('suggestion', '')}")
        else:
            logger.info(f"  ✅ 找到 {len(results)} 只匹配的股票:")
            for i, stock in enumerate(results[:5], 1):  # 只显示前5个
                if "error" not in stock:
                    logger.info(f"    {i}. {stock.get('code'):6s} - {stock.get('name'):15s} [{stock.get('market')}]")


def demo_market_overview():
    """
    演示市场概览功能
    """
    logger.info("\n=== 市场概览示例 ===")

    if not API_AVAILABLE:
        logger.error("❌ 新API不可用，跳过市场概览")
        return

    summary = get_market_summary()

    if "error" in summary:
        logger.error(f"❌ {summary['error']}")
        if "suggestion" in summary:
            logger.info(f"💡 {summary['suggestion']}")
    else:
        logger.info("📊 市场统计信息:")
        logger.info(f"  📈 总股票数: {summary.get('total_count', 0):,}")
        logger.info(f"  🏢 沪市股票: {summary.get('shanghai_count', 0):,}")
        logger.info(f"  🏢 深市股票: {summary.get('shenzhen_count', 0):,}")
        logger.info(f"  🔗 数据源: {summary.get('data_source', 'unknown')}")

        # 显示类别统计
        category_stats = summary.get("category_stats", {})
        if category_stats:
            logger.info("\n📋 按类别统计:")
            for category, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {category}: {count:,} 只")


def demo_stock_data_query():
    """
    演示股票历史数据查询（带降级机制）
    """
    logger.info("\n=== 股票历史数据查询示例 ===")

    if not API_AVAILABLE:
        logger.error("❌ 新API不可用，跳过历史数据查询")
        return

    stock_code = "000001"
    logger.info(f"📊 获取股票 {stock_code} 的历史数据...")

    # 获取最近30天的数据
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    result = get_stock_data(stock_code, start_date, end_date)

    # 显示结果（截取前500个字符以避免输出过长）
    if len(result) > 500:
        logger.info("📋 数据获取结果（前500字符）:")
        print(result[:500] + "...")
    else:
        logger.info("📋 数据获取结果:")
        print(result)


def demo_fallback_mechanism():
    """
    演示降级机制
    """
    logger.info("\n=== 降级机制演示 ===")

    if not API_AVAILABLE:
        logger.error("❌ 新API不可用，无法演示降级机制")
        return

    logger.info("🔄 降级机制说明:")
    logger.info("  1. 优先从MongoDB获取数据")
    logger.info("  2. MongoDB不可用时，降级到Tushare数据接口")
    logger.info("  3. Tushare数据接口不可用时，提供基础的降级数据")
    logger.info("  4. 获取到的数据会自动缓存到MongoDB（如果可用）")

    # 测试一个可能不存在的股票代码
    test_code = "999999"
    logger.info(f"\n🧪 测试不存在的股票代码 {test_code}:")

    result = get_stock_info(test_code)
    if "error" in result:
        logger.error(f"  ❌ 预期的错误: {result['error']}")
    else:
        logger.info(f"  ✅ 意外获得数据: {result.get('name')}")


def main():
    """
    主函数
    """
    logger.info("🚀 股票查询示例程序（增强版）")
    logger.info("=")

    if API_AVAILABLE:
        logger.info("✅ 使用新的股票数据API（支持降级机制）")
    else:
        logger.warning("⚠️ 新API不可用，使用传统查询方式")

    try:
        # 执行各种查询示例
        demo_service_status()
        demo_single_stock_query()
        demo_stock_search()
        demo_market_overview()
        demo_stock_data_query()
        demo_fallback_mechanism()

        logger.info("\n")
        logger.info("✅ 所有查询示例执行完成")
        logger.info("\n💡 使用建议:")
        logger.info("  1. 确保MongoDB已正确配置以获得最佳性能")
        logger.info("  2. 网络连接正常时可以使用Tushare数据接口作为备选")
        logger.info("  3. 定期运行数据同步脚本更新股票信息")

    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断程序")
    except Exception as e:
        logger.error(f"\n❌ 程序执行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
