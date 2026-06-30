#!/usr/bin/env python3
"""
TradingAgents 中文演示脚本 - 使用阿里百炼大模型
专门针对中文用户优化的股票分析演示
"""

import os
import sys
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("default")

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.llm_adapters import ChatDashScope

# 加载 .env 文件
load_dotenv()


def analyze_stock_with_chinese_output(stock_symbol="AAPL", analysis_date="2024-05-10"):
    """使用阿里百炼进行中文股票分析"""

    logger.info("🚀 TradingAgents 中文股票分析 - 阿里百炼版本")
    logger.info("=")

    # 检查API密钥
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    finnhub_key = os.getenv("FINNHUB_API_KEY")

    if not dashscope_key:
        logger.error("❌ 错误: 未找到 DASHSCOPE_API_KEY 环境变量")
        return None

    if not finnhub_key:
        logger.error("❌ 错误: 未找到 FINNHUB_API_KEY 环境变量")
        return None

    logger.info(f"✅ 阿里百炼 API 密钥: {dashscope_key[:10]}...")
    logger.info(f"✅ FinnHub API 密钥: {finnhub_key[:10]}...")
    print()

    try:
        logger.info("🤖 正在初始化阿里百炼大模型...")

        # 创建阿里百炼模型实例
        llm = ChatDashScope(model="qwen-plus-latest", temperature=0.1, max_tokens=3000)

        logger.info("✅ 模型初始化成功!")
        print()

        logger.info(f"📈 开始分析股票: {stock_symbol}")
        logger.info(f"📅 分析日期: {analysis_date}")
        logger.info("⏳ 正在进行智能分析，请稍候...")
        print()

        # 构建中文分析提示
        system_prompt = """你是一位专业的股票分析师，具有丰富的金融市场经验。请用中文进行分析，确保内容专业、客观、易懂。

你的任务是对指定股票进行全面分析，包括：
1. 技术面分析
2. 基本面分析
3. 市场情绪分析
4. 风险评估
5. 投资建议

请确保分析结果：
- 使用中文表达
- 内容专业准确
- 结构清晰
- 包含具体的数据和指标
- 提供明确的投资建议"""

        user_prompt = """请对苹果公司(AAPL)进行全面的股票分析。

分析要求：
1. **技术面分析**：
   - 价格趋势分析
   - 关键技术指标（MA、MACD、RSI、布林带等）
   - 支撑位和阻力位
   - 成交量分析

2. **基本面分析**：
   - 公司财务状况
   - 营收和利润趋势
   - 市场地位和竞争优势
   - 未来增长前景

3. **市场情绪分析**：
   - 投资者情绪
   - 分析师评级
   - 机构持仓情况
   - 市场热点关注度

4. **风险评估**：
   - 主要风险因素
   - 宏观经济影响
   - 行业竞争风险
   - 监管风险

5. **投资建议**：
   - 明确的买入/持有/卖出建议
   - 目标价位
   - 投资时间框架
   - 风险控制建议

请用中文撰写详细的分析报告，确保内容专业且易于理解。"""

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        # 生成分析报告
        response = llm.invoke(messages)

        logger.info("🎯 中文分析报告:")
        logger.info("=")
        print(response.content)
        logger.info("=")

        print()
        logger.info("✅ 分析完成!")
        print()
        logger.info("🌟 阿里百炼大模型优势:")
        logger.info("  - 中文理解和表达能力强")
        logger.info("  - 金融专业知识丰富")
        logger.info("  - 分析逻辑清晰严谨")
        logger.info("  - 适合中国投资者使用习惯")

        return response.content

    except Exception as e:
        logger.error(f"❌ 分析过程中出现错误: {e!s}")
        import traceback

        logger.error("🔍 详细错误信息:")
        traceback.print_exc()
        return None


def compare_models_chinese():
    """比较不同通义千问模型的中文表达能力"""
    logger.info("\n🔄 比较不同通义千问模型的中文分析能力")
    logger.info("=")

    models = [("qwen-turbo", "通义千问 Turbo"), ("qwen-plus", "通义千问 Plus"), ("qwen-max", "通义千问 Max")]

    question = "请用一段话总结苹果公司当前的投资价值，包括优势和风险。"

    for model_id, model_name in models:
        try:
            logger.info(f"\n🧠 {model_name} 分析:")
            logger.info("-")

            llm = ChatDashScope(model=model_id, temperature=0.1, max_tokens=500)
            response = llm.invoke([HumanMessage(content=question)])

            print(response.content)

        except Exception as e:
            logger.error(f"❌ {model_name} 分析失败: {e!s}")


def main():
    """主函数"""
    # 进行完整的股票分析
    analyze_stock_with_chinese_output("AAPL", "2024-05-10")

    # 比较不同模型
    compare_models_chinese()

    logger.info("\n💡 使用建议:")
    logger.info("  1. 通义千问Plus适合日常分析，平衡性能和成本")
    logger.info("  2. 通义千问Max适合深度分析，质量最高")
    logger.info("  3. 通义千问Turbo适合快速查询，响应最快")
    logger.info("  4. 所有模型都针对中文进行了优化")


if __name__ == "__main__":
    main()
