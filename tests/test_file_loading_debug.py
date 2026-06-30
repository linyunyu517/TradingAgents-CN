#!/usr/bin/env python3
"""
调试文件加载问题
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()


def test_file_loading():
    """测试文件加载"""
    print("🔬 文件加载调试")
    print("=" * 80)

    try:
        from tradingagents.config.config_manager import ConfigManager

        print("🔧 创建ConfigManager...")
        config_manager = ConfigManager()

        print("\n📊 加载定价配置...")
        print("=" * 60)

        # 这会触发详细的文件加载日志
        pricing_configs = config_manager.load_pricing()

        print("=" * 60)
        print(f"📊 最终加载的配置数量: {len(pricing_configs)}")

        # 查找DeepSeek配置
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"📊 DeepSeek配置数量: {len(deepseek_configs)}")

        if deepseek_configs:
            print("✅ 找到DeepSeek配置:")
            for config in deepseek_configs:
                print(
                    f"   - {config.model_name}: 输入¥{config.input_price_per_1k}/1K, 输出¥{config.output_price_per_1k}/1K",
                )
        else:
            print("❌ 未找到DeepSeek配置")

        return True

    except Exception as e:
        print(f"❌ 文件加载测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🔬 文件加载调试测试")
    print("=" * 80)
    print("📝 这个测试将显示实际加载的配置文件内容")
    print("=" * 80)

    success = test_file_loading()

    if success:
        print("\n🎉 文件加载测试完成！")
        print("请查看上面的详细日志，确认加载的文件内容。")
    else:
        print("\n❌ 文件加载测试失败")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
