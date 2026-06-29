#!/usr/bin/env python3
"""
测试LLM工具调用机制的详细调试脚本
模拟实际的LLM工具调用过程
"""

import logging
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.dataflows.realtime_news_utils import get_realtime_stock_news

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def test_function_exists():
    """测试函数是否存在"""
    logger.info("========== 测试1: 函数存在性检查 ==========")

    # 检查直接导入的函数
    logger.info(f"get_realtime_stock_news 函数: {get_realtime_stock_news}")
    logger.info(f"函数类型: {type(get_realtime_stock_news)}")

    # 检查Toolkit中的函数
    try:
        toolkit_func = getattr(Toolkit, "get_realtime_stock_news", None)
        logger.info(f"Toolkit.get_realtime_stock_news: {toolkit_func}")
        logger.info(f"Toolkit函数类型: {type(toolkit_func)}")
    except Exception as e:
        logger.error(f"获取Toolkit函数失败: {e}")


def test_direct_call():
    """测试直接函数调用"""
    logger.info("========== 测试2: 直接函数调用 ==========")
    try:
        curr_date = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"调用参数: ticker='000858', date='{curr_date}'")

        start_time = datetime.now()
        result = get_realtime_stock_news("000858", curr_date)
        end_time = datetime.now()

        logger.info(f"调用成功，耗时: {(end_time - start_time).total_seconds():.2f}秒")
        logger.info(f"返回结果类型: {type(result)}")
        logger.info(f"返回结果长度: {len(result)} 字符")
        logger.info(f"结果前100字符: {result[:100]}...")
        return True, result
    except Exception as e:
        logger.error(f"直接调用失败: {e}")
        import traceback

        logger.error(f"错误详情: {traceback.format_exc()}")
        return False, None


def test_toolkit_call():
    """测试Toolkit调用"""
    logger.info("========== 测试3: Toolkit调用 ==========")
    try:
        curr_date = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"调用参数: ticker='000858', date='{curr_date}'")

        start_time = datetime.now()
        result = Toolkit.get_realtime_stock_news("000858", curr_date)
        end_time = datetime.now()

        logger.info(f"Toolkit调用成功，耗时: {(end_time - start_time).total_seconds():.2f}秒")
        logger.info(f"返回结果类型: {type(result)}")
        logger.info(f"返回结果长度: {len(result)} 字符")
        logger.info(f"结果前100字符: {result[:100]}...")
        return True, result
    except Exception as e:
        logger.error(f"Toolkit调用失败: {e}")
        import traceback

        logger.error(f"错误详情: {traceback.format_exc()}")
        return False, None


def test_toolkit_attributes():
    """测试Toolkit的属性和方法"""
    logger.info("========== 测试4: Toolkit属性检查 ==========")

    # 列出Toolkit的所有属性
    toolkit_attrs = [attr for attr in dir(Toolkit) if not attr.startswith("_")]
    logger.info(f"Toolkit可用属性: {toolkit_attrs}")

    # 检查是否有get_realtime_stock_news
    if "get_realtime_stock_news" in toolkit_attrs:
        logger.info("✓ get_realtime_stock_news 在Toolkit中存在")
    else:
        logger.warning("✗ get_realtime_stock_news 不在Toolkit中")

    # 检查Toolkit类型
    logger.info(f"Toolkit类型: {type(Toolkit)}")
    logger.info(f"Toolkit模块: {Toolkit.__module__ if hasattr(Toolkit, '__module__') else 'N/A'}")


def simulate_llm_tool_call():
    """模拟LLM工具调用过程"""
    logger.info("========== 测试5: 模拟LLM工具调用 ==========")

    # 模拟LLM工具调用的参数格式
    tool_call_params = {
        "name": "get_realtime_stock_news",
        "arguments": {"ticker": "000858", "date": datetime.now().strftime("%Y-%m-%d")},
    }

    logger.info(f"模拟工具调用参数: {tool_call_params}")

    try:
        # 尝试通过反射调用
        func_name = tool_call_params["name"]
        args = tool_call_params["arguments"]

        if hasattr(Toolkit, func_name):
            func = getattr(Toolkit, func_name)
            logger.info(f"找到函数: {func}")

            start_time = datetime.now()
            result = func(**args)
            end_time = datetime.now()

            logger.info(f"模拟LLM调用成功，耗时: {(end_time - start_time).total_seconds():.2f}秒")
            logger.info(f"返回结果长度: {len(result)} 字符")
            return True, result
        logger.error(f"函数 {func_name} 不存在于Toolkit中")
        return False, None

    except Exception as e:
        logger.error(f"模拟LLM调用失败: {e}")
        import traceback

        logger.error(f"错误详情: {traceback.format_exc()}")
        return False, None


def main():
    """主测试函数"""
    logger.info("开始LLM工具调用机制详细测试")
    logger.info("=" * 60)

    # 测试1: 函数存在性
    test_function_exists()

    # 测试2: 直接调用
    direct_success, direct_result = test_direct_call()

    # 测试3: Toolkit调用
    toolkit_success, toolkit_result = test_toolkit_call()

    # 测试4: Toolkit属性检查
    test_toolkit_attributes()

    # 测试5: 模拟LLM调用
    llm_success, _llm_result = simulate_llm_tool_call()

    # 结果汇总
    logger.info("=" * 60)
    logger.info("========== 测试结果汇总 ==========")
    logger.info(f"直接函数调用: {'✓ 成功' if direct_success else '✗ 失败'}")
    logger.info(f"Toolkit调用: {'✓ 成功' if toolkit_success else '✗ 失败'}")
    logger.info(f"模拟LLM调用: {'✓ 成功' if llm_success else '✗ 失败'}")

    # 分析问题
    if direct_success and not toolkit_success:
        logger.warning("🔍 问题分析: Toolkit工具绑定存在问题")
    elif direct_success and not llm_success:
        logger.warning("🔍 问题分析: LLM工具调用机制存在问题")
    elif not direct_success:
        logger.warning("🔍 问题分析: 函数本身存在问题")
    else:
        logger.info("🔍 问题分析: 所有调用方式都成功")

    # 比较结果
    if direct_success and toolkit_success:
        if direct_result == toolkit_result:
            logger.info("✓ 直接调用和Toolkit调用结果一致")
        else:
            logger.warning("⚠ 直接调用和Toolkit调用结果不一致")
            logger.info(f"直接调用结果长度: {len(direct_result)}")
            logger.info(f"Toolkit调用结果长度: {len(toolkit_result)}")


if __name__ == "__main__":
    main()
