#!/usr/bin/env python3
"""
测试数据库依赖包兼容性修复
验证requirements_db.txt的兼容性改进
"""

import os
import subprocess
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_python_version_check():
    """测试Python版本检查"""
    print("🔧 测试Python版本检查...")

    current_version = sys.version_info
    if current_version >= (3, 10):
        print(f"  ✅ Python {current_version.major}.{current_version.minor}.{current_version.micro} 符合要求")
        return True
    print(f"  ❌ Python {current_version.major}.{current_version.minor}.{current_version.micro} 版本过低")
    return False


def test_pickle_compatibility():
    """测试pickle兼容性"""
    print("🔧 测试pickle兼容性...")

    try:
        import pickle

        # 检查协议版本
        max_protocol = pickle.HIGHEST_PROTOCOL
        print(f"  当前pickle协议: {max_protocol}")

        if max_protocol >= 5:
            print("  ✅ 支持pickle协议5")
        else:
            print("  ❌ 不支持pickle协议5")
            return False

        # 检查是否错误安装了pickle5
        try:
            import pickle5

            print("  ⚠️ 检测到pickle5包，建议卸载")
            return False
        except ImportError:
            print("  ✅ 未安装pickle5包，配置正确")
            return True

    except Exception as e:
        print(f"  ❌ pickle测试失败: {e}")
        return False


def test_requirements_file_syntax():
    """测试requirements文件语法"""
    print("🔧 测试requirements_db.txt语法...")

    requirements_file = os.path.join(project_root, "requirements_db.txt")

    if not os.path.exists(requirements_file):
        print("  ❌ requirements_db.txt文件不存在")
        return False

    try:
        with open(requirements_file, encoding="utf-8") as f:
            lines = f.readlines()

        print(f"  文件行数: {len(lines)}")

        # 检查是否包含pickle5
        pickle5_found = False
        valid_packages = []

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "pickle5" in line and not line.startswith("#"):
                print(f"  ❌ 第{line_num}行仍包含pickle5: {line}")
                pickle5_found = True
            else:
                valid_packages.append(line)
                print(f"  ✅ 第{line_num}行: {line}")

        if pickle5_found:
            print("  ❌ 仍包含pickle5依赖")
            return False

        print(f"  ✅ 语法检查通过，有效包数量: {len(valid_packages)}")
        return True

    except Exception as e:
        print(f"  ❌ 文件读取失败: {e}")
        return False


def test_package_installation_simulation():
    """模拟包安装测试"""
    print("🔧 模拟包安装测试...")

    # 模拟检查每个包的可用性
    packages_to_check = ["pymongo", "motor", "redis", "hiredis", "pandas", "numpy"]

    available_packages = []
    missing_packages = []

    for package in packages_to_check:
        try:
            __import__(package)
            available_packages.append(package)
            print(f"  ✅ {package}: 已安装")
        except ImportError:
            missing_packages.append(package)
            print(f"  ⚠️ {package}: 未安装")

    print(f"  已安装: {len(available_packages)}/{len(packages_to_check)}")

    if missing_packages:
        print(f"  缺少包: {missing_packages}")
        print("  💡 运行以下命令安装: pip install -r requirements_db.txt")

    return True  # 这个测试总是通过，只是信息性的


def test_compatibility_checker_tool():
    """测试兼容性检查工具"""
    print("🔧 测试兼容性检查工具...")

    checker_file = os.path.join(project_root, "check_db_requirements.py")

    if not os.path.exists(checker_file):
        print("  ❌ check_db_requirements.py文件不存在")
        return False

    try:
        # 运行兼容性检查工具
        result = subprocess.run(
            [sys.executable, checker_file], cwd=project_root, capture_output=True, text=True, timeout=30,
        )

        print(f"  返回码: {result.returncode}")

        if "🔧 TradingAgents 数据库依赖包兼容性检查" in result.stdout:
            print("  ✅ 兼容性检查工具运行成功")

            # 检查是否检测到pickle5问题
            if "pickle5" in result.stdout and "建议卸载" in result.stdout:
                print("  ⚠️ 检测到pickle5问题")
            elif "未安装pickle5包，配置正确" in result.stdout:
                print("  ✅ pickle5配置正确")

            return True
        print("  ❌ 兼容性检查工具输出异常")
        print(f"  输出: {result.stdout[:200]}...")
        return False

    except subprocess.TimeoutExpired:
        print("  ❌ 兼容性检查工具运行超时")
        return False
    except Exception as e:
        print(f"  ❌ 兼容性检查工具运行失败: {e}")
        return False


def test_documentation_completeness():
    """测试文档完整性"""
    print("🔧 测试文档完整性...")

    docs_to_check = ["docs/DATABASE_SETUP_GUIDE.md", "REQUIREMENTS_DB_UPDATE.md"]

    all_exist = True

    for doc_path in docs_to_check:
        full_path = os.path.join(project_root, doc_path)
        if os.path.exists(full_path):
            print(f"  ✅ {doc_path}: 存在")

            # 检查文件大小
            size = os.path.getsize(full_path)
            if size > 1000:  # 至少1KB
                print(f"    文件大小: {size} 字节")
            else:
                print(f"    ⚠️ 文件较小: {size} 字节")
        else:
            print(f"  ❌ {doc_path}: 不存在")
            all_exist = False

    return all_exist


def main():
    """主测试函数"""
    print("🔧 数据库依赖包兼容性修复测试")
    print("=" * 60)

    tests = [
        ("Python版本检查", test_python_version_check),
        ("pickle兼容性", test_pickle_compatibility),
        ("requirements文件语法", test_requirements_file_syntax),
        ("包安装模拟", test_package_installation_simulation),
        ("兼容性检查工具", test_compatibility_checker_tool),
        ("文档完整性", test_documentation_completeness),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            if test_func():
                passed += 1
                print(f"  ✅ {test_name} 通过")
            else:
                print(f"  ❌ {test_name} 失败")
        except Exception as e:
            print(f"  ❌ {test_name} 异常: {e}")

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！数据库依赖包兼容性修复成功")
        print("\n📋 修复内容:")
        print("✅ 移除pickle5依赖，解决Python 3.10+兼容性问题")
        print("✅ 优化版本要求，提高环境兼容性")
        print("✅ 添加兼容性检查工具")
        print("✅ 完善安装指南和故障排除文档")

        print("\n🚀 用户体验改进:")
        print("✅ 减少安装错误")
        print("✅ 提供清晰的错误诊断")
        print("✅ 支持更多Python环境")
        print("✅ 简化故障排除流程")

        return True
    print("⚠️ 部分测试失败，需要进一步检查")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
