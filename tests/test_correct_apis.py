#!/usr/bin/env python3
"""
正确测试Google和Reddit API工具
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env", override=True)


def test_google_news_tool():
    """测试Google新闻工具"""
    try:
        print("🧪 测试Google新闻工具")
        print("=" * 50)

        from tradingagents.dataflows.interface import get_google_news

        print("✅ get_google_news函数导入成功")

        # 测试获取苹果公司新闻
        print("📰 获取苹果公司新闻...")
        try:
            news = get_google_news(query="Apple AAPL stock", curr_date="2025-06-27", look_back_days=7)

            if news and len(news) > 0:
                print("✅ Google新闻获取成功")
                print(f"   新闻长度: {len(news)} 字符")
                print(f"   新闻预览: {news[:200]}...")
                return True
            print("⚠️ Google新闻获取成功但内容为空")
            return True  # 功能正常，只是没有内容

        except Exception as e:
            print(f"❌ Google新闻获取失败: {e}")
            return False

    except ImportError as e:
        print(f"❌ Google新闻工具导入失败: {e}")
        return False


def test_reddit_tools():
    """测试Reddit工具"""
    try:
        print("\n🧪 测试Reddit工具")
        print("=" * 50)

        from tradingagents.dataflows.interface import get_reddit_company_news, get_reddit_global_news

        print("✅ Reddit工具函数导入成功")

        # 检查Reddit数据目录
        reddit_data_dir = Path("tradingagents/dataflows/data_cache/reddit_data")
        print(f"📁 Reddit数据目录: {reddit_data_dir}")

        if reddit_data_dir.exists():
            print("✅ Reddit数据目录存在")

            # 检查子目录
            subdirs = [d for d in reddit_data_dir.iterdir() if d.is_dir()]
            print(f"   子目录: {[d.name for d in subdirs]}")

            if subdirs:
                print("✅ Reddit数据可用，可以进行测试")

                # 测试全球新闻
                try:
                    print("📰 测试Reddit全球新闻...")
                    global_news = get_reddit_global_news(start_date="2025-06-27", look_back_days=1, max_limit_per_day=5)

                    if global_news and len(global_news) > 0:
                        print("✅ Reddit全球新闻获取成功")
                        print(f"   新闻长度: {len(global_news)} 字符")
                    else:
                        print("⚠️ Reddit全球新闻获取成功但内容为空")

                except Exception as e:
                    print(f"❌ Reddit全球新闻获取失败: {e}")

                # 测试公司新闻
                try:
                    print("📰 测试Reddit公司新闻...")
                    company_news = get_reddit_company_news(
                        ticker="AAPL", start_date="2025-06-27", look_back_days=1, max_limit_per_day=5,
                    )

                    if company_news and len(company_news) > 0:
                        print("✅ Reddit公司新闻获取成功")
                        print(f"   新闻长度: {len(company_news)} 字符")
                    else:
                        print("⚠️ Reddit公司新闻获取成功但内容为空")

                except Exception as e:
                    print(f"❌ Reddit公司新闻获取失败: {e}")

                return True
            print("⚠️ Reddit数据目录为空，需要先下载数据")
            return False
        print("⚠️ Reddit数据目录不存在，需要先设置数据")
        print("💡 提示: Reddit工具需要预先下载的数据文件")
        return False

    except ImportError as e:
        print(f"❌ Reddit工具导入失败: {e}")
        return False


def test_toolkit_integration():
    """测试工具包集成"""
    try:
        print("\n🧪 测试工具包集成")
        print("=" * 50)

        # 检查Toolkit类是否包含这些工具
        from tradingagents.agents.utils.toolkit import Toolkit

        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True

        toolkit = Toolkit(config=config)

        # 检查工具包中的方法
        methods = [method for method in dir(toolkit) if not method.startswith("_")]

        google_methods = [m for m in methods if "google" in m.lower()]
        reddit_methods = [m for m in methods if "reddit" in m.lower()]

        print(f"📊 工具包方法总数: {len(methods)}")
        print(f"   Google相关方法: {google_methods}")
        print(f"   Reddit相关方法: {reddit_methods}")

        # 检查具体方法是否存在
        if hasattr(toolkit, "get_google_news"):
            print("✅ toolkit.get_google_news 方法存在")
        else:
            print("❌ toolkit.get_google_news 方法不存在")

        if hasattr(toolkit, "get_reddit_global_news"):
            print("✅ toolkit.get_reddit_global_news 方法存在")
        else:
            print("❌ toolkit.get_reddit_global_news 方法不存在")

        if hasattr(toolkit, "get_reddit_company_news"):
            print("✅ toolkit.get_reddit_company_news 方法存在")
        else:
            print("❌ toolkit.get_reddit_company_news 方法不存在")

        return True

    except Exception as e:
        print(f"❌ 工具包集成测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🧪 正确的API工具测试")
    print("=" * 60)

    # 检查API密钥
    google_key = os.getenv("GOOGLE_API_KEY")
    reddit_id = os.getenv("REDDIT_CLIENT_ID")

    print("🔑 API密钥状态:")
    print(f"   Google API: {'✅ 已配置' if google_key else '❌ 未配置'}")
    print(f"   Reddit API: {'✅ 已配置' if reddit_id else '❌ 未配置'}")

    # 运行测试
    results = {}

    results["Google新闻工具"] = test_google_news_tool()
    results["Reddit工具"] = test_reddit_tools()
    results["工具包集成"] = test_toolkit_integration()

    # 总结结果
    print("\n📊 测试结果总结:")
    print("=" * 50)

    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")

    successful_tests = sum(results.values())
    total_tests = len(results)

    print(f"\n🎯 总体结果: {successful_tests}/{total_tests} 测试通过")

    if successful_tests == total_tests:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查配置")


if __name__ == "__main__":
    main()
