#!/usr/bin/env python3
"""
测试Web API中的AKShare功能
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")


def test_akshare_web_api():
    """测试AKShare在Web API中的表现"""
    print("=" * 60)
    print("🌐 测试AKShare Web API兼容性")
    print("=" * 60)

    try:
        from app.services.data_source_adapters import AKShareAdapter

        adapter = AKShareAdapter()

        if not adapter.is_available():
            print("❌ AKShare适配器不可用")
            return None

        print("✅ AKShare适配器可用")

        # 模拟Web API的测试流程
        results = {}
        total_start = time.time()

        # 1. 股票列表测试
        print("\n1. 📊 股票列表测试...")
        start = time.time()
        try:
            stock_df = adapter.get_stock_list()
            duration = time.time() - start

            if stock_df is not None and not stock_df.empty:
                results["stock_list"] = {
                    "status": "success",
                    "count": len(stock_df),
                    "duration": duration,
                    "message": f"Successfully fetched {len(stock_df)} stocks",
                }
                print(f"   ✅ 成功: {len(stock_df)}条记录，耗时: {duration:.1f}秒")
            else:
                results["stock_list"] = {
                    "status": "failed",
                    "count": 0,
                    "duration": duration,
                    "message": "No stock data returned",
                }
                print(f"   ❌ 失败: 无数据返回，耗时: {duration:.1f}秒")
        except Exception as e:
            duration = time.time() - start
            results["stock_list"] = {"status": "error", "count": 0, "duration": duration, "message": f"Error: {e!s}"}
            print(f"   ❌ 错误: {e}，耗时: {duration:.1f}秒")

        # 2. 交易日期测试
        print("\n2. 📅 交易日期测试...")
        start = time.time()
        try:
            latest_date = adapter.find_latest_trade_date()
            duration = time.time() - start

            if latest_date:
                results["trade_date"] = {
                    "status": "success",
                    "date": latest_date,
                    "duration": duration,
                    "message": f"Found latest trade date: {latest_date}",
                }
                print(f"   ✅ 成功: {latest_date}，耗时: {duration:.1f}秒")
            else:
                results["trade_date"] = {
                    "status": "failed",
                    "date": None,
                    "duration": duration,
                    "message": "No trade date found",
                }
                print(f"   ❌ 失败: 无交易日期，耗时: {duration:.1f}秒")
        except Exception as e:
            duration = time.time() - start
            results["trade_date"] = {"status": "error", "date": None, "duration": duration, "message": f"Error: {e!s}"}
            print(f"   ❌ 错误: {e}，耗时: {duration:.1f}秒")

        # 3. 财务数据测试
        print("\n3. 💰 财务数据测试...")
        start = time.time()
        try:
            trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            basic_df = adapter.get_daily_basic(trade_date)
            duration = time.time() - start

            if basic_df is not None and not basic_df.empty:
                results["daily_basic"] = {
                    "status": "success",
                    "count": len(basic_df),
                    "duration": duration,
                    "message": f"Successfully fetched basic data for {trade_date}, {len(basic_df)} records",
                }
                print(f"   ✅ 成功: {len(basic_df)}条记录，耗时: {duration:.1f}秒")
            else:
                results["daily_basic"] = {
                    "status": "failed",
                    "count": 0,
                    "duration": duration,
                    "message": "No daily basic data available or not supported",
                }
                print(f"   ❌ 失败: 无财务数据，耗时: {duration:.1f}秒")
        except Exception as e:
            duration = time.time() - start
            results["daily_basic"] = {"status": "error", "count": 0, "duration": duration, "message": f"Error: {e!s}"}
            print(f"   ❌ 错误: {e}，耗时: {duration:.1f}秒")

        total_duration = time.time() - total_start

        # 输出Web API格式的结果
        print("\n📊 Web API测试结果:")
        print(f"   总耗时: {total_duration:.1f}秒")

        web_result = {
            "name": "akshare",
            "priority": 2,
            "description": "开源金融数据库，提供基础的股票信息",
            "available": True,
            "tests": {
                "stock_list": results.get("stock_list", {}),
                "trade_date": results.get("trade_date", {}),
                "daily_basic": results.get("daily_basic", {}),
            },
            "total_duration": total_duration,
        }

        print("\n🔍 详细结果:")
        for test_name, test_result in web_result["tests"].items():
            status = test_result.get("status", "unknown")
            duration = test_result.get("duration", 0)
            message = test_result.get("message", "No message")

            status_icon = "✅" if status == "success" else "❌"
            print(f"   {status_icon} {test_name}: {message} ({duration:.1f}s)")

        # Web超时评估
        print("\n🌐 Web兼容性评估:")
        if total_duration < 30:
            print(f"   🎯 优秀: 总耗时 {total_duration:.1f}秒 < 30秒")
        elif total_duration < 60:
            print(f"   ⚠️ 可接受: 总耗时 {total_duration:.1f}秒 < 60秒")
        else:
            print(f"   ❌ 超时风险: 总耗时 {total_duration:.1f}秒 > 60秒")

        return web_result

    except Exception as e:
        print(f"❌ Web API测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = test_akshare_web_api()
    if result:
        print(f"\n✅ 测试完成，AKShare Web API兼容性: {'良好' if result['total_duration'] < 60 else '需要优化'}")
    else:
        print("\n❌ 测试失败")
