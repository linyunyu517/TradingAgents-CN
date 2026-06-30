#!/usr/bin/env python3
"""
测试新的在线工具配置系统
验证环境变量和配置文件的集成
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_online_tools_config():
    """测试在线工具配置"""
    print("🧪 测试在线工具配置系统")
    print("=" * 60)

    # 1. 检查环境变量
    print("\n📋 环境变量检查:")
    env_vars = {
        "ONLINE_TOOLS_ENABLED": os.getenv("ONLINE_TOOLS_ENABLED", "未设置"),
        "ONLINE_NEWS_ENABLED": os.getenv("ONLINE_NEWS_ENABLED", "未设置"),
        "REALTIME_DATA_ENABLED": os.getenv("REALTIME_DATA_ENABLED", "未设置"),
        "OPENAI_ENABLED": os.getenv("OPENAI_ENABLED", "未设置"),
    }

    for var, value in env_vars.items():
        status = "✅" if value != "未设置" else "⚠️"
        print(f"   {status} {var}: {value}")

    # 2. 测试配置文件读取
    print("\n🔧 配置文件测试:")
    try:
        from tradingagents.default_config import DEFAULT_CONFIG

        config_items = {
            "online_tools": DEFAULT_CONFIG.get("online_tools"),
            "online_news": DEFAULT_CONFIG.get("online_news"),
            "realtime_data": DEFAULT_CONFIG.get("realtime_data"),
        }

        for key, value in config_items.items():
            print(f"   ✅ {key}: {value}")

    except Exception as e:
        print(f"   ❌ 配置文件读取失败: {e}")
        return False

    # 3. 测试配置逻辑
    print("\n🧠 配置逻辑验证:")

    # 检查在线工具总开关
    online_tools = DEFAULT_CONFIG.get("online_tools", False)
    online_news = DEFAULT_CONFIG.get("online_news", False)
    realtime_data = DEFAULT_CONFIG.get("realtime_data", False)

    print(f"   📊 在线工具总开关: {'🟢 启用' if online_tools else '🔴 禁用'}")
    print(f"   📰 在线新闻工具: {'🟢 启用' if online_news else '🔴 禁用'}")
    print(f"   📈 实时数据获取: {'🟢 启用' if realtime_data else '🔴 禁用'}")

    # 4. 配置建议
    print("\n💡 配置建议:")
    if not online_tools and not realtime_data:
        print("   ✅ 当前为离线模式，适合开发和测试，节省API成本")
    elif online_tools and realtime_data:
        print("   ⚠️ 当前为完全在线模式，会消耗较多API配额")
    else:
        print("   🔧 当前为混合模式，部分功能在线，部分离线")

    if online_news and not online_tools:
        print("   💡 建议：新闻工具已启用但总开关关闭，可能导致功能冲突")

    return True


def test_toolkit_integration():
    """测试工具包集成"""
    print("\n🔗 工具包集成测试:")
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        # 创建工具包实例
        toolkit = Toolkit(config=DEFAULT_CONFIG)
        print("   ✅ Toolkit实例创建成功")

        # 检查在线工具可用性
        online_tools = ["get_google_news", "get_reddit_news", "get_reddit_stock_info", "get_chinese_social_sentiment"]

        available_tools = []
        for tool_name in online_tools:
            if hasattr(toolkit, tool_name):
                available_tools.append(tool_name)
                print(f"   ✅ {tool_name} 可用")
            else:
                print(f"   ❌ {tool_name} 不可用")

        print(f"\n   📊 可用在线工具: {len(available_tools)}/{len(online_tools)}")

        return len(available_tools) > 0

    except Exception as e:
        print(f"   ❌ 工具包集成测试失败: {e}")
        return False


def show_config_examples():
    """显示配置示例"""
    print("\n📝 配置示例:")
    print("=" * 60)

    examples = {
        "开发模式 (离线)": {
            "ONLINE_TOOLS_ENABLED": "false",
            "ONLINE_NEWS_ENABLED": "false",
            "REALTIME_DATA_ENABLED": "false",
            "说明": "完全离线，使用缓存数据，节省成本",
        },
        "测试模式 (部分在线)": {
            "ONLINE_TOOLS_ENABLED": "false",
            "ONLINE_NEWS_ENABLED": "true",
            "REALTIME_DATA_ENABLED": "false",
            "说明": "新闻在线，数据离线，平衡功能和成本",
        },
        "生产模式 (完全在线)": {
            "ONLINE_TOOLS_ENABLED": "true",
            "ONLINE_NEWS_ENABLED": "true",
            "REALTIME_DATA_ENABLED": "true",
            "说明": "完全在线，获取最新数据，适合实盘交易",
        },
    }

    for mode, config in examples.items():
        print(f"\n🔧 {mode}:")
        for key, value in config.items():
            if key == "说明":
                print(f"   💡 {value}")
            else:
                print(f"   {key}={value}")


def main():
    """主测试函数"""
    print("🚀 在线工具配置系统测试")
    print("=" * 70)

    # 运行测试
    config_success = test_online_tools_config()
    toolkit_success = test_toolkit_integration()

    # 显示配置示例
    show_config_examples()

    # 总结
    print("\n📊 测试总结:")
    print("=" * 60)
    print(f"   配置系统: {'✅ 正常' if config_success else '❌ 异常'}")
    print(f"   工具包集成: {'✅ 正常' if toolkit_success else '❌ 异常'}")

    if config_success and toolkit_success:
        print("\n🎉 在线工具配置系统运行正常！")
        print("💡 您现在可以通过环境变量灵活控制在线/离线模式")
    else:
        print("\n⚠️ 发现问题，请检查配置")

    return config_success and toolkit_success


if __name__ == "__main__":
    main()
