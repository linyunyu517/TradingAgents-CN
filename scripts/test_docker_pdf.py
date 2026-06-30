#!/usr/bin/env python3
"""
Docker环境PDF功能测试脚本
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_docker_environment():
    """测试Docker环境检测"""
    print("🔍 测试Docker环境检测...")

    try:
        from web.utils.docker_pdf_adapter import is_docker_environment

        is_docker = is_docker_environment()
        print(f"Docker环境: {'是' if is_docker else '否'}")
        return is_docker
    except ImportError as e:
        print(f"❌ 导入Docker适配器失败: {e}")
        return False


def test_docker_dependencies():
    """测试Docker依赖"""
    print("\n🔍 测试Docker依赖...")

    try:
        from web.utils.docker_pdf_adapter import check_docker_pdf_dependencies

        deps_ok, message = check_docker_pdf_dependencies()
        print(f"依赖检查: {'✅' if deps_ok else '❌'} {message}")
        return deps_ok
    except ImportError as e:
        print(f"❌ 导入Docker适配器失败: {e}")
        return False


def test_docker_pdf_generation():
    """测试Docker PDF生成"""
    print("\n🔍 测试Docker PDF生成...")

    try:
        from web.utils.docker_pdf_adapter import test_docker_pdf_generation

        pdf_ok = test_docker_pdf_generation()
        print(f"PDF生成: {'✅' if pdf_ok else '❌'}")
        return pdf_ok
    except ImportError as e:
        print(f"❌ 导入Docker适配器失败: {e}")
        return False


def test_report_exporter():
    """测试报告导出器Docker集成"""
    print("\n🔍 测试报告导出器Docker集成...")

    try:
        from web.utils.report_exporter import ReportExporter

        exporter = ReportExporter()
        print("导出器创建: ✅")
        print(f"  export_available: {exporter.export_available}")
        print(f"  pandoc_available: {exporter.pandoc_available}")
        print(f"  is_docker: {exporter.is_docker}")

        # 测试Markdown导出
        test_results = {
            "stock_symbol": "DOCKER_TEST",
            "decision": {
                "action": "buy",
                "confidence": 0.85,
                "risk_score": 0.3,
                "target_price": "¥15.50",
                "reasoning": "Docker环境测试报告生成。",
            },
            "state": {"market_report": "Docker环境技术分析测试。", "fundamentals_report": "Docker环境基本面分析测试。"},
            "llm_provider": "test",
            "llm_model": "test-model",
            "analysts": ["Docker测试分析师"],
            "research_depth": "测试分析",
            "is_demo": True,
        }

        # 测试Markdown生成
        md_content = exporter.generate_markdown_report(test_results)
        print(f"Markdown生成: ✅ ({len(md_content)} 字符)")

        # 如果在Docker环境且pandoc可用，测试PDF生成
        if exporter.is_docker and exporter.pandoc_available:
            try:
                pdf_content = exporter.generate_pdf_report(test_results)
                print(f"Docker PDF生成: ✅ ({len(pdf_content)} 字节)")
                return True
            except Exception as e:
                print(f"Docker PDF生成: ❌ {e}")
                return False
        else:
            print("跳过PDF测试 (非Docker环境或pandoc不可用)")
            return True

    except Exception as e:
        print(f"❌ 报告导出器测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🐳 Docker环境PDF功能测试")
    print("=" * 50)

    tests = [
        ("Docker环境检测", test_docker_environment),
        ("Docker依赖检查", test_docker_dependencies),
        ("Docker PDF生成", test_docker_pdf_generation),
        ("报告导出器集成", test_report_exporter),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append((test_name, False))

    # 总结
    print("\n" + "=" * 50)
    print("📊 Docker测试结果总结")
    print("=" * 50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1

    print(f"\n总计: {passed}/{total} 测试通过")

    # 环境建议
    print("\n💡 环境建议:")
    print("-" * 30)

    if passed == total:
        print("🎉 Docker PDF功能完全正常！")
    elif passed >= total - 1:
        print("⚠️ 大部分功能正常，可能有小问题")
        print("建议: 检查Docker镜像是否包含所有必要依赖")
    else:
        print("❌ Docker PDF功能存在问题")
        print("建议:")
        print("1. 重新构建Docker镜像")
        print("2. 确保Dockerfile包含PDF依赖")
        print("3. 检查容器运行权限")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
