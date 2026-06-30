"""
新闻过滤功能演示脚本
展示如何使用不同的新闻过滤方法来提高新闻质量
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import pandas as pd


def demo_basic_filtering():
    """演示基础新闻过滤功能"""
    print("🔍 演示1: 基础新闻过滤功能")
    print("-" * 40)

    from tradingagents.utils.news_filter import create_news_filter

    # 创建招商银行新闻过滤器
    filter = create_news_filter("600036")

    # 模拟混合质量的新闻数据
    mixed_news = pd.DataFrame(
        [
            {
                "新闻标题": "招商银行发布2024年第三季度财报",
                "新闻内容": "招商银行今日发布第三季度财报，净利润同比增长8%，资产质量持续改善...",
            },
            {
                "新闻标题": "上证180ETF指数基金投资策略分析",
                "新闻内容": "上证180指数包含招商银行等180只大盘蓝筹股，ETF基金采用被动投资策略...",
            },
            {
                "新闻标题": "招商银行信用卡业务创新发展",
                "新闻内容": "招商银行信用卡中心推出多项创新产品，数字化转型成效显著...",
            },
            {"新闻标题": "无标题", "新闻内容": "指数基金跟踪上证180指数，权重股包括招商银行等金融股..."},
        ],
    )

    print(f"📊 原始新闻: {len(mixed_news)}条")

    # 执行过滤
    filtered_news = filter.filter_news(mixed_news, min_score=30)

    print(f"✅ 过滤后新闻: {len(filtered_news)}条")
    print(f"📈 过滤率: {(len(mixed_news) - len(filtered_news)) / len(mixed_news) * 100:.1f}%")

    print("\n🎯 高质量新闻:")
    for idx, (_, row) in enumerate(filtered_news.iterrows(), 1):
        print(f"{idx}. {row['新闻标题']} (评分: {row['relevance_score']:.1f})")

    return filtered_news


def demo_real_news_filtering():
    """演示真实新闻数据过滤"""
    print("\n🌐 演示2: 真实新闻数据过滤")
    print("-" * 40)

    from tradingagents.dataflows.akshare_utils import get_stock_news_em

    from tradingagents.utils.news_filter import create_news_filter

    # 获取真实新闻
    print("📡 正在获取招商银行真实新闻...")
    real_news = get_stock_news_em("600036")

    if real_news.empty:
        print("❌ 未获取到新闻数据")
        return None

    print(f"✅ 获取到 {len(real_news)} 条新闻")

    # 显示原始新闻质量
    print("\n📰 原始新闻标题示例:")
    for idx, (_, row) in enumerate(real_news.head(3).iterrows(), 1):
        title = row.get("新闻标题", "无标题")
        print(f"{idx}. {title}")

    # 创建过滤器
    filter = create_news_filter("600036")

    # 过滤新闻
    filtered_news = filter.filter_news(real_news, min_score=30)

    print("\n🔍 过滤结果:")
    print(f"  原始新闻: {len(real_news)}条")
    print(f"  过滤后新闻: {len(filtered_news)}条")
    print(f"  过滤率: {(len(real_news) - len(filtered_news)) / len(real_news) * 100:.1f}%")

    if not filtered_news.empty:
        avg_score = filtered_news["relevance_score"].mean()
        print(f"  平均相关性评分: {avg_score:.1f}")

        print("\n🎯 过滤后高质量新闻:")
        for idx, (_, row) in enumerate(filtered_news.head(5).iterrows(), 1):
            title = row.get("新闻标题", "无标题")
            score = row.get("relevance_score", 0)
            print(f"{idx}. {title} (评分: {score:.1f})")

    return filtered_news


def demo_enhanced_filtering():
    """演示增强新闻过滤功能"""
    print("\n⚡ 演示3: 增强新闻过滤功能")
    print("-" * 40)

    from tradingagents.utils.enhanced_news_filter import create_enhanced_news_filter

    # 创建增强过滤器（仅使用规则过滤，避免外部依赖）
    enhanced_filter = create_enhanced_news_filter("600036", use_semantic=False, use_local_model=False)

    # 测试数据
    test_news = pd.DataFrame(
        [
            {
                "新闻标题": "招商银行董事会决议公告",
                "新闻内容": "招商银行董事会审议通过重要决议，包括高管任免、业务发展战略等重要事项...",
            },
            {
                "新闻标题": "招商银行与科技公司战略合作",
                "新闻内容": "招商银行宣布与知名科技公司达成战略合作协议，共同推进金融科技创新...",
            },
            {
                "新闻标题": "银行板块ETF基金表现分析",
                "新闻内容": "银行ETF基金今日上涨，成分股包括招商银行、工商银行等多只银行股...",
            },
        ],
    )

    print(f"📊 测试新闻: {len(test_news)}条")

    # 执行增强过滤
    enhanced_result = enhanced_filter.filter_news_enhanced(test_news, min_score=40)

    print(f"✅ 增强过滤结果: {len(enhanced_result)}条")

    if not enhanced_result.empty:
        print("\n🎯 增强过滤后的新闻:")
        for idx, (_, row) in enumerate(enhanced_result.iterrows(), 1):
            print(f"{idx}. {row['新闻标题']}")
            print(f"   综合评分: {row['final_score']:.1f}")

    return enhanced_result


def demo_integrated_filtering():
    """演示集成新闻过滤功能"""
    print("\n🔧 演示4: 集成新闻过滤功能")
    print("-" * 40)

    from tradingagents.utils.news_filter_integration import create_filtered_realtime_news_function

    # 创建增强版实时新闻函数
    enhanced_news_func = create_filtered_realtime_news_function()

    print("🧪 测试增强版实时新闻函数...")

    # 调用增强版函数
    result = enhanced_news_func(
        ticker="600036", curr_date=datetime.now().strftime("%Y-%m-%d"), enable_filter=True, min_score=30,
    )

    print(f"📊 返回结果长度: {len(result)} 字符")

    # 检查是否包含过滤信息
    if "过滤新闻报告" in result:
        print("✅ 检测到过滤功能已生效")
        print("📈 新闻质量得到提升")
    else:
        print("ℹ️ 使用了原始新闻报告")

    # 显示部分结果
    print("\n📄 报告预览:")
    preview = result[:300] + "..." if len(result) > 300 else result
    print(preview)

    return result


def main():
    """主演示函数"""
    print("🚀 新闻过滤功能演示")
    print("=" * 50)
    print("本演示将展示如何使用不同的新闻过滤方法来提高新闻质量")
    print()

    try:
        # 演示1: 基础过滤
        demo_basic_filtering()

        # 演示2: 真实新闻过滤
        demo_real_news_filtering()

        # 演示3: 增强过滤
        demo_enhanced_filtering()

        # 演示4: 集成过滤
        demo_integrated_filtering()

        print("\n" + "=" * 50)
        print("🎉 演示完成！")
        print()
        print("💡 总结:")
        print("1. 基础过滤器：通过关键词规则快速过滤低质量新闻")
        print("2. 真实数据过滤：有效解决东方财富新闻质量问题")
        print("3. 增强过滤器：支持多种过滤策略的综合评分")
        print("4. 集成功能：无缝集成到现有新闻获取流程")
        print()
        print("🔧 使用建议:")
        print("- 对于A股新闻，建议使用基础过滤器（快速、有效）")
        print("- 对于重要分析，可以使用增强过滤器（更精确）")
        print("- 集成功能可以直接替换现有新闻获取函数")

    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
