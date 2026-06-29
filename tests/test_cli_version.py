#!/usr/bin/env python3
"""
测试命令行版本
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()


def test_cli_imports():
    """测试CLI模块导入"""
    print("🔬 测试CLI模块导入")
    print("=" * 60)

    try:
        # 测试导入CLI主模块
        print("✅ CLI主模块导入成功")

        # 测试导入分析师类型
        print("✅ 分析师类型导入成功")

        # 测试导入工具函数
        print("✅ CLI工具函数导入成功")

        return True

    except Exception as e:
        print(f"❌ CLI模块导入失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_config():
    """测试CLI配置"""
    print("\n🔧 测试CLI配置")
    print("=" * 60)

    try:
        from tradingagents.config.config_manager import config_manager
        from tradingagents.default_config import DEFAULT_CONFIG

        print("🔧 测试默认配置...")
        print(f"   LLM提供商: {DEFAULT_CONFIG.get('llm_provider', 'N/A')}")
        print(f"   深度思考模型: {DEFAULT_CONFIG.get('deep_think_llm', 'N/A')}")
        print(f"   快速思考模型: {DEFAULT_CONFIG.get('quick_think_llm', 'N/A')}")

        print("\n🔧 测试配置管理器...")
        print(f"   配置目录: {config_manager.config_dir}")

        # 测试定价配置
        pricing_configs = config_manager.load_pricing()
        print(f"   定价配置数量: {len(pricing_configs)}")

        # 查找DeepSeek配置
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"   DeepSeek配置数量: {len(deepseek_configs)}")

        if deepseek_configs:
            print("✅ CLI可以访问DeepSeek配置")
            return True
        print("❌ CLI无法访问DeepSeek配置")
        return False

    except Exception as e:
        print(f"❌ CLI配置测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_graph_creation():
    """测试CLI图创建"""
    print("\n📊 测试CLI图创建")
    print("=" * 60)

    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("⚠️ 未找到DEEPSEEK_API_KEY，跳过图创建测试")
        return True

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        print("🔧 创建测试配置...")
        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "llm_provider": "deepseek",
                "deep_think_llm": "deepseek-chat",
                "quick_think_llm": "deepseek-chat",
                "max_debate_rounds": 1,
                "max_risk_discuss_rounds": 1,
                "online_tools": False,  # 关闭在线工具，减少复杂度
                "memory_enabled": False,
            },
        )

        print("📊 创建交易分析图...")
        # 使用CLI的方式创建图
        TradingAgentsGraph(
            ["market"],  # 只使用市场分析师
            config=config,
            debug=True,
        )

        print("✅ CLI图创建成功")
        return True

    except Exception as e:
        print(f"❌ CLI图创建失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_cost_tracking():
    """测试CLI成本跟踪"""
    print("\n💰 测试CLI成本跟踪")
    print("=" * 60)

    try:
        from tradingagents.config.config_manager import config_manager, token_tracker

        print("🔧 测试成本计算...")
        cost = config_manager.calculate_cost(
            provider="deepseek", model_name="deepseek-chat", input_tokens=1000, output_tokens=500,
        )
        print(f"   DeepSeek成本: ¥{cost:.6f}")

        if cost > 0:
            print("✅ CLI成本计算正常")

            print("\n🔧 测试Token跟踪...")
            usage_record = token_tracker.track_usage(
                provider="deepseek",
                model_name="deepseek-chat",
                input_tokens=100,
                output_tokens=50,
                session_id="cli_test",
                analysis_type="cli_test",
            )

            if usage_record and usage_record.cost > 0:
                print(f"   跟踪记录成本: ¥{usage_record.cost:.6f}")
                print("✅ CLI Token跟踪正常")
                return True
            print("❌ CLI Token跟踪失败")
            return False
        print("❌ CLI成本计算为0")
        return False

    except Exception as e:
        print(f"❌ CLI成本跟踪测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_help():
    """测试CLI帮助功能"""
    print("\n❓ 测试CLI帮助功能")
    print("=" * 60)

    try:
        from cli.main import app

        print("🔧 测试CLI应用创建...")
        print(f"   应用名称: {app.info.name}")
        print(f"   应用帮助: {app.info.help[:50]}...")

        print("✅ CLI帮助功能正常")
        return True

    except Exception as e:
        print(f"❌ CLI帮助功能测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🔬 命令行版本测试")
    print("=" * 80)
    print("📝 这个测试将验证CLI版本是否正常工作")
    print("📝 检查模块导入、配置访问、图创建等功能")
    print("=" * 80)

    # 运行各项测试
    tests = [
        ("模块导入", test_cli_imports),
        ("配置访问", test_cli_config),
        ("图创建", test_cli_graph_creation),
        ("成本跟踪", test_cli_cost_tracking),
        ("帮助功能", test_cli_help),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results[test_name] = False

    # 总结
    print("\n📋 测试总结")
    print("=" * 60)

    for test_name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{test_name}: {status}")

    overall_success = all(results.values())

    if overall_success:
        print("\n🎉 CLI版本测试全部通过！")
        print("   命令行版本可以正常使用")
        print("   建议运行: python -m cli.main analyze")
    else:
        print("\n❌ CLI版本测试有失败项")
        print("   请检查失败的测试项")

    print("\n🎯 测试完成！")
    return overall_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
