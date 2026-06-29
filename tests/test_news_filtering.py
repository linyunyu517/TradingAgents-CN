"""
测试新闻过滤功能
验证基于规则的过滤器和增强过滤器的效果
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime

import pandas as pd


def test_basic_news_filter():
    """测试基础新闻过滤器"""
    print("=== 测试基础新闻过滤器 ===")

    try:
        from tradingagents.utils.news_filter import create_news_filter

        # 创建过滤器
        filter = create_news_filter("600036")
        print("✅ 成功创建招商银行(600036)新闻过滤器")

        # 模拟新闻数据
        test_news = pd.DataFrame(
            [
                {
                    "新闻标题": "招商银行发布2024年第三季度业绩报告",
                    "新闻内容": "招商银行今日发布第三季度财报，净利润同比增长8%，资产质量持续改善，不良贷款率进一步下降...",
                },
                {
                    "新闻标题": "上证180ETF指数基金（530280）自带杠铃策略",
                    "新闻内容": "数据显示，上证180指数前十大权重股分别为贵州茅台、招商银行600036、五粮液等，该ETF基金采用被动投资策略...",
                },
                {
                    "新闻标题": "银行ETF指数(512730)多只成分股上涨",
                    "新闻内容": "银行板块今日表现强势，招商银行、工商银行、建设银行等多只成分股上涨，银行ETF基金受益明显...",
                },
                {
                    "新闻标题": "招商银行与某科技公司签署战略合作协议",
                    "新闻内容": "招商银行宣布与知名科技公司达成战略合作，将在数字化转型、金融科技创新等方面深度合作，推动银行业务升级...",
                },
                {
                    "新闻标题": "无标题",
                    "新闻内容": "指数基金跟踪上证180指数，该指数包含180只大盘蓝筹股，权重股包括招商银行等金融股...",
                },
            ],
        )

        print(f"📊 测试新闻数量: {len(test_news)}条")

        # 执行过滤
        start_time = time.time()
        filtered_news = filter.filter_news(test_news, min_score=30)
        filter_time = time.time() - start_time

        print(f"⏱️ 过滤耗时: {filter_time:.3f}秒")
        print(f"📈 过滤结果: {len(test_news)}条 -> {len(filtered_news)}条")

        if not filtered_news.empty:
            print("\n🎯 过滤后的新闻:")
            for idx, (_, row) in enumerate(filtered_news.iterrows(), 1):
                print(f"{idx}. {row['新闻标题']} (评分: {row['relevance_score']:.1f})")

        # 获取过滤统计
        stats = filter.get_filter_statistics(test_news, filtered_news)
        print("\n📊 过滤统计:")
        print(f"  - 过滤率: {stats['filter_rate']:.1f}%")
        print(f"  - 平均评分: {stats['avg_score']:.1f}")
        print(f"  - 最高评分: {stats['max_score']:.1f}")

        return True

    except Exception as e:
        print(f"❌ 基础过滤器测试失败: {e}")
        return False


def test_enhanced_news_filter():
    """测试增强新闻过滤器"""
    print("\n=== 测试增强新闻过滤器 ===")

    try:
        from tradingagents.utils.enhanced_news_filter import create_enhanced_news_filter

        # 创建增强过滤器（不使用外部模型依赖）
        enhanced_filter = create_enhanced_news_filter(
            "600036",
            use_semantic=False,  # 暂时不使用语义模型
            use_local_model=False,  # 暂时不使用本地模型
        )
        print("✅ 成功创建增强新闻过滤器")

        # 使用相同的测试数据
        test_news = pd.DataFrame(
            [
                {
                    "新闻标题": "招商银行发布2024年第三季度业绩报告",
                    "新闻内容": "招商银行今日发布第三季度财报，净利润同比增长8%，资产质量持续改善，不良贷款率进一步下降...",
                },
                {
                    "新闻标题": "上证180ETF指数基金（530280）自带杠铃策略",
                    "新闻内容": "数据显示，上证180指数前十大权重股分别为贵州茅台、招商银行600036、五粮液等，该ETF基金采用被动投资策略...",
                },
                {
                    "新闻标题": "招商银行股东大会通过分红方案",
                    "新闻内容": "招商银行股东大会审议通过2024年度利润分配方案，每10股派发现金红利12元，分红率达到30%...",
                },
                {
                    "新闻标题": "招商银行信用卡业务创新发展",
                    "新闻内容": "招商银行信用卡中心推出多项创新产品，包括数字化信用卡、消费分期等，用户体验显著提升...",
                },
            ],
        )

        print(f"📊 测试新闻数量: {len(test_news)}条")

        # 执行增强过滤
        start_time = time.time()
        enhanced_filtered = enhanced_filter.filter_news_enhanced(test_news, min_score=40)
        filter_time = time.time() - start_time

        print(f"⏱️ 增强过滤耗时: {filter_time:.3f}秒")
        print(f"📈 增强过滤结果: {len(test_news)}条 -> {len(enhanced_filtered)}条")

        if not enhanced_filtered.empty:
            print("\n🎯 增强过滤后的新闻:")
            for idx, (_, row) in enumerate(enhanced_filtered.iterrows(), 1):
                print(f"{idx}. {row['新闻标题']}")
                print(
                    f"   综合评分: {row['final_score']:.1f} (规则:{row['rule_score']:.1f}, 语义:{row['semantic_score']:.1f}, 分类:{row['classification_score']:.1f})",
                )

        return True

    except Exception as e:
        print(f"❌ 增强过滤器测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_real_news_filtering():
    """测试真实新闻数据过滤"""
    print("\n=== 测试真实新闻数据过滤 ===")

    try:
        from tradingagents.dataflows.akshare_utils import get_stock_news_em

        from tradingagents.utils.news_filter import create_news_filter

        print("📡 正在获取招商银行真实新闻数据...")

        # 获取真实新闻数据
        start_time = time.time()
        real_news = get_stock_news_em("600036")
        fetch_time = time.time() - start_time

        if real_news.empty:
            print("❌ 未获取到真实新闻数据")
            return False

        print(f"✅ 成功获取真实新闻: {len(real_news)}条，耗时: {fetch_time:.2f}秒")

        # 显示前3条新闻标题
        print("\n📰 原始新闻标题示例:")
        for idx, (_, row) in enumerate(real_news.head(3).iterrows(), 1):
            title = row.get("新闻标题", "无标题")
            print(f"{idx}. {title}")

        # 创建过滤器并过滤
        filter = create_news_filter("600036")

        start_time = time.time()
        filtered_real_news = filter.filter_news(real_news, min_score=30)
        filter_time = time.time() - start_time

        print("\n🔍 过滤结果:")
        print(f"  - 原始新闻: {len(real_news)}条")
        print(f"  - 过滤后新闻: {len(filtered_real_news)}条")
        print(f"  - 过滤率: {(len(real_news) - len(filtered_real_news)) / len(real_news) * 100:.1f}%")
        print(f"  - 过滤耗时: {filter_time:.3f}秒")

        if not filtered_real_news.empty:
            avg_score = filtered_real_news["relevance_score"].mean()
            max_score = filtered_real_news["relevance_score"].max()
            print(f"  - 平均评分: {avg_score:.1f}")
            print(f"  - 最高评分: {max_score:.1f}")

            print("\n🎯 过滤后高质量新闻标题:")
            for idx, (_, row) in enumerate(filtered_real_news.head(5).iterrows(), 1):
                title = row.get("新闻标题", "无标题")
                score = row.get("relevance_score", 0)
                print(f"{idx}. {title} (评分: {score:.1f})")

        return True

    except Exception as e:
        print(f"❌ 真实新闻过滤测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_news_filter_integration():
    """测试新闻过滤集成功能"""
    print("\n=== 测试新闻过滤集成功能 ===")

    try:
        from tradingagents.utils.news_filter_integration import apply_news_filtering_patches

        print("🔧 正在应用新闻过滤补丁...")
        enhanced_function = apply_news_filtering_patches()

        print("✅ 新闻过滤补丁应用成功")

        # 测试增强版函数
        print("🧪 测试增强版实时新闻函数...")

        test_result = enhanced_function(
            ticker="600036", curr_date=datetime.now().strftime("%Y-%m-%d"), enable_filter=True, min_score=30,
        )

        print(f"📊 增强版函数返回结果长度: {len(test_result)} 字符")

        if "过滤新闻报告" in test_result:
            print("✅ 检测到过滤功能已生效")
        else:
            print("ℹ️ 使用了原始新闻报告")

        return True

    except Exception as e:
        print(f"❌ 新闻过滤集成测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🚀 开始新闻过滤功能测试")
    print("=" * 50)

    test_results = []

    # 1. 测试基础过滤器
    test_results.append(("基础新闻过滤器", test_basic_news_filter()))

    # 2. 测试增强过滤器
    test_results.append(("增强新闻过滤器", test_enhanced_news_filter()))

    # 3. 测试真实新闻过滤
    test_results.append(("真实新闻数据过滤", test_real_news_filtering()))

    # 4. 测试集成功能
    test_results.append(("新闻过滤集成功能", test_news_filter_integration()))

    # 输出测试总结
    print("\n" + "=" * 50)
    print("📋 测试结果总结:")

    passed = 0
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  - {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 总体结果: {passed}/{len(test_results)} 项测试通过")

    if passed == len(test_results):
        print("🎉 所有测试通过！新闻过滤功能工作正常")
    else:
        print("⚠️ 部分测试失败，请检查相关功能")


if __name__ == "__main__":
    main()
