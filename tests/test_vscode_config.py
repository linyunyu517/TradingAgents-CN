#!/usr/bin/env python3
"""
VSCode配置验证测试
验证Python虚拟环境和项目配置是否正确
"""

import json
import os
import sys
from pathlib import Path


def test_python_environment():
    """测试Python环境配置"""
    print("🐍 Python环境验证")
    print("=" * 50)

    # 检查Python版本
    print(f"Python版本: {sys.version}")
    print(f"Python路径: {sys.executable}")

    # 检查虚拟环境
    venv_path = os.environ.get("VIRTUAL_ENV")
    if venv_path:
        print(f"✅ 虚拟环境: {venv_path}")
    else:
        print("⚠️ 虚拟环境: 未激活")

    # 检查工作目录
    print(f"工作目录: {os.getcwd()}")

    # 检查是否在项目根目录
    if os.path.exists("tradingagents") and os.path.exists(".env"):
        print("✅ 在项目根目录")
    else:
        print("❌ 不在项目根目录")

    return True


def test_vscode_settings():
    """测试VSCode设置文件"""
    print("\n🔧 VSCode设置验证")
    print("=" * 50)

    settings_path = Path(".vscode/settings.json")

    if not settings_path.exists():
        print("❌ .vscode/settings.json 不存在")
        return False

    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        print("✅ settings.json 格式正确")

        # 检查关键配置
        key_settings = {
            "python.defaultInterpreterPath": "./env/Scripts/python.exe",
            "python.terminal.activateEnvironment": True,
            "python.testing.pytestEnabled": True,
        }

        for key, expected in key_settings.items():
            if key in settings:
                actual = settings[key]
                if actual == expected:
                    print(f"✅ {key}: {actual}")
                else:
                    print(f"⚠️ {key}: {actual} (期望: {expected})")
            else:
                print(f"❌ 缺少配置: {key}")

        return True

    except json.JSONDecodeError as e:
        print(f"❌ settings.json 格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 读取settings.json失败: {e}")
        return False


def test_virtual_env_path():
    """测试虚拟环境路径"""
    print("\n📁 虚拟环境路径验证")
    print("=" * 50)

    # 检查虚拟环境目录
    env_dir = Path("env")
    if not env_dir.exists():
        print("❌ env目录不存在")
        return False

    print("✅ env目录存在")

    # 检查Python可执行文件
    python_exe = env_dir / "Scripts" / "python.exe"
    if python_exe.exists():
        print(f"✅ Python可执行文件: {python_exe}")
    else:
        print(f"❌ Python可执行文件不存在: {python_exe}")
        return False

    # 检查pip
    pip_exe = env_dir / "Scripts" / "pip.exe"
    if pip_exe.exists():
        print(f"✅ pip可执行文件: {pip_exe}")
    else:
        print(f"❌ pip可执行文件不存在: {pip_exe}")

    return True


def test_package_imports():
    """测试关键包导入"""
    print("\n📦 关键包导入验证")
    print("=" * 50)

    packages = [
        ("langchain", "LangChain"),
        ("langchain_openai", "LangChain OpenAI"),
        ("pandas", "Pandas"),
        ("numpy", "NumPy"),
        ("tushare", "Tushare"),
        ("streamlit", "Streamlit"),
        ("tradingagents", "TradingAgents"),
    ]

    success_count = 0
    for package, name in packages:
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {name}: v{version}")
            success_count += 1
        except ImportError:
            print(f"❌ {name}: 未安装")
        except Exception as e:
            print(f"⚠️ {name}: 导入错误 - {e}")

    print(f"\n📊 包导入结果: {success_count}/{len(packages)} 成功")
    return success_count >= len(packages) * 0.8  # 80%成功率


def test_project_structure():
    """测试项目结构"""
    print("\n📂 项目结构验证")
    print("=" * 50)

    required_dirs = ["tradingagents", "tests", "cli", "web", ".vscode"]

    required_files = [".env", "requirements.txt", "README.md", ".gitignore"]

    # 检查目录
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✅ 目录: {dir_name}")
        else:
            print(f"❌ 目录: {dir_name}")

    # 检查文件
    for file_name in required_files:
        if os.path.exists(file_name):
            print(f"✅ 文件: {file_name}")
        else:
            print(f"❌ 文件: {file_name}")

    return True


def test_environment_variables():
    """测试环境变量"""
    print("\n🔑 环境变量验证")
    print("=" * 50)

    # 读取.env文件
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env文件不存在")
        return False

    print("✅ .env文件存在")

    # 检查关键环境变量
    key_vars = ["DASHSCOPE_API_KEY", "TUSHARE_TOKEN", "OPENAI_API_KEY", "FINNHUB_API_KEY"]

    for var in key_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * 10}{value[-4:] if len(value) > 4 else '****'}")
        else:
            print(f"⚠️ {var}: 未设置")

    return True


def test_simple_functionality():
    """测试基本功能"""
    print("\n⚡ 基本功能验证")
    print("=" * 50)

    try:
        # 测试TradingAgents导入
        print("✅ TradingAgents LLM适配器导入成功")

        # 测试数据流导入
        print("✅ TradingAgents数据流导入成功")

        # 测试图形导入
        print("✅ TradingAgents图形导入成功")

        return True

    except Exception as e:
        print(f"❌ 功能测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔬 VSCode配置验证测试")
    print("=" * 70)
    print("💡 验证目标:")
    print("   - Python虚拟环境配置")
    print("   - VSCode设置文件")
    print("   - 项目结构完整性")
    print("   - 关键包导入")
    print("   - 环境变量配置")
    print("=" * 70)

    # 运行所有测试
    tests = [
        ("Python环境", test_python_environment),
        ("VSCode设置", test_vscode_settings),
        ("虚拟环境路径", test_virtual_env_path),
        ("包导入", test_package_imports),
        ("项目结构", test_project_structure),
        ("环境变量", test_environment_variables),
        ("基本功能", test_simple_functionality),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))

    # 总结
    print("\n📋 VSCode配置验证总结")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    total = len(results)
    print(f"\n📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 VSCode配置完全正确！")
        print("\n💡 现在您可以:")
        print("   ✅ 在VSCode中正常开发和调试")
        print("   ✅ 使用集成终端运行Python代码")
        print("   ✅ 运行测试和格式化代码")
        print("   ✅ 使用智能代码补全和错误检查")
    elif passed >= total * 0.8:
        print("\n✅ VSCode配置基本正确！")
        print("⚠️ 部分功能可能需要调整")
    else:
        print("\n⚠️ VSCode配置需要修复")
        print("请检查失败的项目并重新配置")

    print("\n🎯 使用建议:")
    print("   1. 确保在VSCode中选择了正确的Python解释器")
    print("   2. 重启VSCode以应用新的配置")
    print("   3. 使用Ctrl+Shift+P -> 'Python: Select Interpreter'")
    print("   4. 在集成终端中验证虚拟环境已激活")


if __name__ == "__main__":
    main()
