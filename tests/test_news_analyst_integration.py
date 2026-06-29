#!/usr/bin/env python3
"""
测试新闻分析师与统一新闻工具的集成
"""

import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_news_analyst_integration():
    """测试新闻分析师与统一新闻工具的集成"""

    print("🚀 开始测试新闻分析师集成...")

    try:
        # 导入必要的模块
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        from tradingagents.tools.unified_news_tool import create_unified_news_tool

        print("✅ 成功导入必要模块")

        # 创建模拟工具包
        class MockToolkit:
            def __init__(self):
                # 创建统一新闻工具
                self.unified_news_tool = create_unified_news_tool(self)

            def get_realtime_stock_news(self, params):
                stock_code = params.get("stock_code", "unknown")
                return f"""
【发布时间】2025-07-28 18:00:00
【新闻标题】{stock_code}公司发布重要公告，业绩超预期增长
【文章来源】东方财富网

【新闻内容】
1. 公司Q2季度营收同比增长25%，净利润增长30%
2. 新产品线获得重大突破，市场前景广阔
3. 管理层对下半年业绩表示乐观
4. 分析师上调目标价至50元

【市场影响】
- 短期利好：业绩超预期，市场情绪积极
- 中期利好：新产品线带来增长动力
- 长期利好：行业地位进一步巩固
"""

            def get_google_news(self, params):
                query = params.get("query", "unknown")
                return f"Google新闻搜索结果 - {query}: 相关财经新闻内容"

            def get_global_news_openai(self, params):
                query = params.get("query", "unknown")
                return f"OpenAI全球新闻 - {query}: 国际财经新闻内容"

        toolkit = MockToolkit()
        print("✅ 创建模拟工具包成功")

        # 创建模拟LLM
        class MockLLM:
            def __init__(self):
                self.__class__.__name__ = "MockLLM"

            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                # 模拟LLM响应，包含工具调用
                class MockResult:
                    def __init__(self):
                        self.content = """
# 股票新闻分析报告

## 📈 核心要点
基于最新获取的新闻数据，该股票展现出强劲的业绩增长态势：

### 🎯 业绩亮点
- Q2营收同比增长25%，超出市场预期
- 净利润增长30%，盈利能力显著提升
- 新产品线获得重大突破

### 📊 市场影响分析
**短期影响（1-3个月）**：
- 预期股价上涨5-10%
- 市场情绪转向积极

**中期影响（3-12个月）**：
- 新产品线贡献增量收入
- 估值有望修复至合理水平

### 💰 投资建议
- **评级**：买入
- **目标价**：50元
- **风险等级**：中等

基于真实新闻数据的专业分析报告。
"""
                        # 模拟工具调用
                        self.tool_calls = [
                            {"name": "get_stock_news_unified", "args": {"stock_code": "000001", "max_news": 10}},
                        ]

                return MockResult()

        llm = MockLLM()
        print("✅ 创建模拟LLM成功")

        # 创建新闻分析师
        news_analyst = create_news_analyst(llm, toolkit)
        print("✅ 创建新闻分析师成功")

        # 测试不同股票
        test_stocks = [("000001", "平安银行 - A股"), ("00700", "腾讯控股 - 港股"), ("AAPL", "苹果公司 - 美股")]

        for stock_code, description in test_stocks:
            print(f"\n{'=' * 60}")
            print(f"🔍 测试股票: {stock_code} ({description})")
            print(f"{'=' * 60}")

            try:
                # 调用新闻分析师
                start_time = datetime.now()
                result = news_analyst(
                    {
                        "messages": [],
                        "company_of_interest": stock_code,
                        "trade_date": "2025-07-28",
                        "session_id": f"test_{stock_code}",
                    },
                )
                end_time = datetime.now()

                print(f"⏱️ 分析耗时: {(end_time - start_time).total_seconds():.2f}秒")

                # 检查结果
                if result and "messages" in result and len(result["messages"]) > 0:
                    final_message = result["messages"][-1]
                    if hasattr(final_message, "content"):
                        report = final_message.content
                        print("✅ 成功获取新闻分析报告")
                        print(f"📊 报告长度: {len(report)} 字符")

                        # 显示报告摘要
                        if len(report) > 300:
                            print(f"📝 报告摘要: {report[:300]}...")
                        else:
                            print(f"📝 完整报告: {report}")

                        # 检查是否包含真实新闻特征
                        news_indicators = ["发布时间", "新闻标题", "文章来源", "东方财富", "业绩", "营收"]
                        has_real_news = any(indicator in report for indicator in news_indicators)
                        print(f"🔍 包含真实新闻特征: {'是' if has_real_news else '否'}")

                        if has_real_news:
                            print("🎉 集成测试成功！")
                        else:
                            print("⚠️ 可能需要进一步优化")
                    else:
                        print("❌ 消息内容为空")
                else:
                    print("❌ 未获取到分析结果")

            except Exception as e:
                print(f"❌ 测试股票 {stock_code} 时出错: {e}")
                import traceback

                traceback.print_exc()

        print(f"\n{'=' * 60}")
        print("🎉 新闻分析师集成测试完成!")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_news_analyst_integration()
