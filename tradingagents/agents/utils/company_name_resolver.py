"""
公司名称解析器（统一共享模块）

合并了 tradingagents/agents/ 下7个文件中重复的 _get_company_name() 函数和 us_stock_names 字典。
所有分析师和研究节点统一从此模块导入，消除代码重复。

历史:
    - B08 (BUG-009): 合并重复的 _get_company_name() 函数
    - B09 (BUG-010): 合并重复的 us_stock_names 字典
"""

from tradingagents.utils.logging_init import get_logger

logger = get_logger(__name__)

# ====================================================================
# B09: 统一美股名称映射表
# 从7个重复定义中提取，合并为一个共享常量
# ====================================================================
US_STOCK_NAMES: dict[str, str] = {
    "AAPL": "苹果公司",
    "TSLA": "特斯拉",
    "NVDA": "英伟达",
    "MSFT": "微软",
    "GOOGL": "谷歌",
    "AMZN": "亚马逊",
    "META": "Meta",
    "NFLX": "奈飞",
}


def get_company_name(
    ticker: str,
    market_info: dict,
    analyst_name: str = "默认",
) -> str:
    """
    根据股票代码和所属市场获取公司名称（中文）。

    统一了7个模块中独立的 _get_company_name 实现：
      - market_analyst / news_analyst / social_media_analyst
      - fundamentals_analyst / china_market_analyst
      - bull_researcher / bear_researcher

    Args:
        ticker: 股票代码，如 '000001', 'TSLA', '00700.HK'
        market_info: 市场信息字典，必须包含键 is_china / is_hk / is_us
        analyst_name: 日志前缀标识，默认 '默认'

    Returns:
        str: 公司名称，无法解析时返回友好默认值
    """
    try:
        # ------------------------------------------------------------
        # 中国A股
        # ------------------------------------------------------------
        if market_info.get("is_china"):
            from tradingagents.dataflows.interface import get_china_stock_info_unified

            stock_info = get_china_stock_info_unified(ticker)
            logger.debug(
                f"📊 [{analyst_name}] 获取股票信息返回: {stock_info[:200] if stock_info else 'None'}...",
            )

            if stock_info and "股票名称:" in stock_info:
                company_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                logger.info(
                    f"✅ [{analyst_name}] 成功获取中国股票名称: {ticker} -> {company_name}",
                )
                return company_name

            # 降级方案：从 data_source_manager 直接获取字典
            logger.warning(
                f"⚠️ [{analyst_name}] 无法从统一接口解析股票名称: {ticker}，尝试降级方案",
            )
            try:
                from tradingagents.dataflows.data_source_manager import (
                    get_china_stock_info_unified as get_info_dict,
                )

                info_dict = get_info_dict(ticker)
                if info_dict and info_dict.get("name"):
                    company_name = info_dict["name"]
                    logger.info(
                        f"✅ [{analyst_name}] 降级方案成功获取股票名称: {ticker} -> {company_name}",
                    )
                    return company_name
            except Exception as e:
                logger.error(f"❌ [{analyst_name}] 降级方案也失败: {e}")

            logger.error(
                f"❌ [{analyst_name}] 所有方案都无法获取股票名称: {ticker}",
            )
            return f"股票代码{ticker}"

        # ------------------------------------------------------------
        # 港股
        # ------------------------------------------------------------
        if market_info.get("is_hk"):
            try:
                clean_ticker = ticker.replace(".HK", "").replace(".hk", "")
                company_name = f"港股{clean_ticker}"
                logger.debug(
                    f"📊 [{analyst_name}] 使用改进港股工具获取名称: {ticker} -> {company_name}",
                )
                return company_name
            except Exception as e:
                logger.debug(
                    f"📊 [{analyst_name}] 改进港股工具获取名称失败: {e}",
                )
                clean_ticker = ticker.replace(".HK", "").replace(".hk", "")
                return f"港股{clean_ticker}"

        # ------------------------------------------------------------
        # 美股
        # ------------------------------------------------------------
        if market_info.get("is_us"):
            company_name = US_STOCK_NAMES.get(
                ticker.upper(),
                f"美股{ticker}",
            )
            logger.debug(
                f"📊 [{analyst_name}] 美股名称映射: {ticker} -> {company_name}",
            )
            return company_name

        # ------------------------------------------------------------
        # 未知市场
        # ------------------------------------------------------------
        return f"股票{ticker}"

    except Exception as e:
        logger.error(f"❌ [{analyst_name}] 获取公司名称失败: {e}")
        return f"股票{ticker}"
