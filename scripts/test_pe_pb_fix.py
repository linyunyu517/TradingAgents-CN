#!/usr/bin/env python3
"""
测试 PE/PB 修复

功能：
1. 测试 _parse_mongodb_financial_data 的三层降级逻辑
2. 测试 realtime_metrics 的异步客户端兼容性
3. 验证基本面分析报告能否正确显示 PE/PB

使用方法：
    python scripts/test_pe_pb_fix.py 600036
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_parse_mongodb_financial_data(code: str):
    """测试 MongoDB 财务数据解析（三层降级逻辑）"""
    logger.info("=" * 80)
    logger.info("🧪 测试 1: _parse_mongodb_financial_data 三层降级逻辑")
    logger.info("=" * 80)

    from pymongo import MongoClient

    from app.core.config import settings
    from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

    # 连接数据库
    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]

    code6 = str(code).zfill(6)

    # 获取 stock_basic_info
    basic_info = db.stock_basic_info.find_one({"code": code6})

    if not basic_info:
        logger.error(f"❌ 未找到股票 {code6} 的基础信息")
        return False

    logger.info("✅ 找到股票基础信息")
    logger.info(f"   PE: {basic_info.get('pe', 'N/A')}")
    logger.info(f"   PB: {basic_info.get('pb', 'N/A')}")
    logger.info(f"   PE_TTM: {basic_info.get('pe_ttm', 'N/A')}")

    # 创建 Provider 实例
    provider = OptimizedChinaDataProvider()

    # 测试解析
    logger.info("\n🔧 调用 _parse_mongodb_financial_data...")

    try:
        # 模拟 financial_data（使用 basic_info 作为输入）
        metrics = provider._parse_mongodb_financial_data(basic_info, 41.86)

        logger.info("\n✅ 解析成功！")
        logger.info(f"   PE: {metrics.get('pe', 'N/A')}")
        logger.info(f"   PB: {metrics.get('pb', 'N/A')}")
        logger.info(f"   ROE: {metrics.get('roe', 'N/A')}")
        logger.info(f"   ROA: {metrics.get('roa', 'N/A')}")

        # 验证 PE/PB 是否正确获取
        if metrics.get("pe") != "N/A" and metrics.get("pb") != "N/A":
            logger.info("\n🎉 测试通过：PE/PB 数据正确获取！")
            return True
        logger.error("\n❌ 测试失败：PE/PB 仍然是 N/A")
        return False

    except Exception as e:
        logger.error(f"❌ 解析失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False

    finally:
        client.close()


def test_realtime_metrics(code: str):
    """测试 realtime_metrics 的异步客户端兼容性"""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 测试 2: realtime_metrics 异步客户端兼容性")
    logger.info("=" * 80)

    from pymongo import MongoClient

    from app.core.config import settings
    from tradingagents.dataflows.realtime_metrics import get_pe_pb_with_fallback

    code6 = str(code).zfill(6)

    # 测试 1: 使用同步客户端
    logger.info("\n🔧 测试 1: 使用同步客户端")
    try:
        sync_client = MongoClient(settings.MONGO_URI)
        metrics = get_pe_pb_with_fallback(code6, sync_client)

        if metrics:
            logger.info("✅ 同步客户端测试成功")
            logger.info(f"   PE: {metrics.get('pe', 'N/A')}")
            logger.info(f"   PB: {metrics.get('pb', 'N/A')}")
            logger.info(f"   数据来源: {metrics.get('source', 'N/A')}")
        else:
            logger.error("❌ 同步客户端测试失败：返回空")

        sync_client.close()
    except Exception as e:
        logger.error(f"❌ 同步客户端测试异常: {e}")
        import traceback

        logger.error(traceback.format_exc())

    # 测试 2: 使用异步客户端（模拟诊断脚本的场景）
    logger.info("\n🔧 测试 2: 使用异步客户端")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        async_client = AsyncIOMotorClient(settings.MONGO_URI)

        metrics = get_pe_pb_with_fallback(code6, async_client)

        if metrics:
            logger.info("✅ 异步客户端测试成功（已自动转换为同步）")
            logger.info(f"   PE: {metrics.get('pe', 'N/A')}")
            logger.info(f"   PB: {metrics.get('pb', 'N/A')}")
            logger.info(f"   数据来源: {metrics.get('source', 'N/A')}")
            return True
        logger.error("❌ 异步客户端测试失败：返回空")
        return False

    except Exception as e:
        logger.error(f"❌ 异步客户端测试异常: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def test_fundamentals_report(code: str):
    """测试基本面分析报告生成"""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 测试 3: 基本面分析报告生成")
    logger.info("=" * 80)

    from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

    code6 = str(code).zfill(6)

    try:
        provider = OptimizedChinaDataProvider()

        # 获取股票基础信息
        stock_data = provider._get_stock_basic_info_only(code6)

        logger.info("\n🔧 生成基本面分析报告...")

        # 生成报告
        report = provider._generate_fundamentals_report(code6, stock_data)

        # 检查报告中是否包含 PE/PB 数据
        if "市盈率" in report or "PE" in report or "P/E" in report:
            logger.info("✅ 报告包含 PE 数据")

            # 提取 PE 相关内容
            lines = report.split("\n")
            for line in lines:
                if "PE" in line or "市盈率" in line or "P/E" in line:
                    logger.info(f"   {line.strip()}")
        else:
            logger.warning("⚠️  报告不包含 PE 数据")

        if "市净率" in report or "PB" in report or "P/B" in report:
            logger.info("✅ 报告包含 PB 数据")

            # 提取 PB 相关内容
            lines = report.split("\n")
            for line in lines:
                if "PB" in line or "市净率" in line or "P/B" in line:
                    logger.info(f"   {line.strip()}")
        else:
            logger.warning("⚠️  报告不包含 PB 数据")

        # 检查是否有"缺乏具体的财务数据"的提示
        if "缺乏具体的财务数据" in report or "无法进行精确的估值分析" in report:
            logger.error("\n❌ 测试失败：报告仍然提示缺乏财务数据")
            logger.info("\n报告片段:")
            logger.info(report[:500])
            return False
        logger.info("\n🎉 测试通过：报告包含完整的财务数据！")
        return True

    except Exception as e:
        logger.error(f"❌ 报告生成失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def main(code: str):
    """主函数"""
    logger.info("=" * 80)
    logger.info(f"🚀 测试 PE/PB 修复 - 股票代码: {code}")
    logger.info("=" * 80)

    results = []

    # 测试 1
    result1 = test_parse_mongodb_financial_data(code)
    results.append(("MongoDB 财务数据解析", result1))

    # 测试 2
    result2 = test_realtime_metrics(code)
    results.append(("实时指标计算", result2))

    # 测试 3
    result3 = test_fundamentals_report(code)
    results.append(("基本面分析报告", result3))

    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("📊 测试总结")
    logger.info("=" * 80)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"   {test_name}: {status}")

    all_passed = all(result for _, result in results)

    if all_passed:
        logger.info("\n🎉 所有测试通过！PE/PB 修复成功！")
    else:
        logger.error("\n❌ 部分测试失败，请检查日志")

    logger.info("=" * 80)

    return all_passed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="测试 PE/PB 修复", formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("code", type=str, help="股票代码（6位）")

    args = parser.parse_args()

    success = main(args.code)
    sys.exit(0 if success else 1)
