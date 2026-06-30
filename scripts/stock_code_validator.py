# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("default")


def validate_stock_code(original_code: str, processed_content: str) -> str:
    """
    验证处理后的内容中是否包含正确的股票代码

    Args:
        original_code: 原始股票代码
        processed_content: 处理后的内容

    Returns:
        str: 验证并修正后的内容
    """

    # 定义常见的错误映射
    error_mappings = {
        "002027": ["002021", "002026", "002028"],  # 分众传媒常见错误
        "002021": ["002027"],  # 反向映射
    }

    if original_code in error_mappings:
        for wrong_code in error_mappings[original_code]:
            if wrong_code in processed_content:
                logger.error(f"🔍 [股票代码验证] 发现错误代码 {wrong_code}，修正为 {original_code}")
                processed_content = processed_content.replace(wrong_code, original_code)

    return processed_content
