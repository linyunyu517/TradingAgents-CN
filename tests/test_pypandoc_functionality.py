#!/usr/bin/env python3
"""
测试pypandoc功能
验证导出功能的依赖是否正常工作
"""

import os
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_pypandoc_import():
    """测试pypandoc导入"""
    print("🔍 测试pypandoc导入...")
    try:
        import pypandoc

        print("✅ pypandoc导入成功")
        return True
    except ImportError as e:
        print(f"❌ pypandoc导入失败: {e}")
        return False


def test_pandoc_version():
    """测试pandoc版本"""
    print("\n🔍 测试pandoc版本...")
    try:
        import pypandoc

        version = pypandoc.get_pandoc_version()
        print(f"✅ Pandoc版本: {version}")
        return True
    except Exception as e:
        print(f"❌ 获取pandoc版本失败: {e}")
        return False


def test_pandoc_download():
    """测试pandoc自动下载"""
    print("\n🔍 测试pandoc自动下载...")
    try:
        import pypandoc

        # 检查是否已有pandoc
        try:
            version = pypandoc.get_pandoc_version()
            print(f"✅ Pandoc已存在: {version}")
            return True
        except Exception:
            print("⚠️ Pandoc不存在，尝试下载...")

        # 尝试下载
        pypandoc.download_pandoc()

        # 再次检查
        version = pypandoc.get_pandoc_version()
        print(f"✅ Pandoc下载成功: {version}")
        return True

    except Exception as e:
        print(f"❌ Pandoc下载失败: {e}")
        return False


def test_markdown_conversion():
    """测试Markdown转换功能"""
    print("\n🔍 测试Markdown转换...")

    try:
        import pypandoc

        # 测试内容
        test_markdown = """# 测试报告

## 基本信息
- **股票代码**: TEST001
- **生成时间**: 2025-01-12 15:30:00

## 分析结果
这是一个测试报告，用于验证pypandoc的转换功能。

### 技术分析
- 价格趋势：上涨
- 成交量：正常
- 技术指标：良好

### 投资建议
**建议**: 买入
**置信度**: 85%

---
*报告生成时间: 2025-01-12 15:30:00*
"""

        print("📄 测试Markdown内容准备完成")

        # 测试转换为HTML
        try:
            html_output = pypandoc.convert_text(test_markdown, "html", format="markdown")
            print("✅ Markdown → HTML 转换成功")
            print(f"   输出长度: {len(html_output)} 字符")
        except Exception as e:
            print(f"❌ Markdown → HTML 转换失败: {e}")
            return False

        # 测试转换为DOCX
        try:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                output_file = tmp_file.name

            pypandoc.convert_text(
                test_markdown,
                "docx",
                format="markdown",
                outputfile=output_file,
                extra_args=["--toc", "--number-sections"],
            )

            # 检查文件是否生成
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print("✅ Markdown → DOCX 转换成功")
                print(f"   文件大小: {file_size} 字节")

                # 清理临时文件
                os.unlink(output_file)
            else:
                print("❌ DOCX文件未生成")
                return False

        except Exception as e:
            print(f"❌ Markdown → DOCX 转换失败: {e}")
            return False

        # 测试转换为PDF (可能失败，因为需要额外工具)
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                output_file = tmp_file.name

            pypandoc.convert_text(
                test_markdown, "pdf", format="markdown", outputfile=output_file, extra_args=["--pdf-engine=wkhtmltopdf"],
            )

            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print("✅ Markdown → PDF 转换成功")
                print(f"   文件大小: {file_size} 字节")

                # 清理临时文件
                os.unlink(output_file)
            else:
                print("⚠️ PDF文件未生成 (可能缺少PDF引擎)")

        except Exception as e:
            print(f"⚠️ Markdown → PDF 转换失败: {e}")
            print("   这是正常的，PDF转换需要额外的工具如wkhtmltopdf")

        return True

    except Exception as e:
        print(f"❌ 转换测试失败: {e}")
        return False


def test_report_exporter():
    """测试报告导出器"""
    print("\n🔍 测试报告导出器...")

    try:
        from web.utils.report_exporter import ReportExporter

        # 创建导出器实例
        exporter = ReportExporter()
        print("✅ 报告导出器创建成功")
        print(f"   导出功能可用: {exporter.export_available}")
        print(f"   Pandoc可用: {exporter.pandoc_available}")

        # 测试数据
        test_results = {
            "stock_symbol": "TEST001",
            "decision": {
                "action": "buy",
                "confidence": 0.85,
                "risk_score": 0.3,
                "target_price": "¥15.50",
                "reasoning": "基于技术分析和基本面分析，该股票具有良好的投资价值。",
            },
            "state": {
                "market_report": "技术指标显示上涨趋势，成交量放大。",
                "fundamentals_report": "公司财务状况良好，盈利能力强。",
                "sentiment_report": "市场情绪积极，投资者信心较强。",
            },
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
            "analysts": ["技术分析师", "基本面分析师", "情绪分析师"],
            "research_depth": "深度分析",
            "is_demo": False,
        }

        # 测试Markdown导出
        try:
            md_content = exporter.generate_markdown_report(test_results)
            print("✅ Markdown报告生成成功")
            print(f"   内容长度: {len(md_content)} 字符")
        except Exception as e:
            print(f"❌ Markdown报告生成失败: {e}")
            return False

        # 测试DOCX导出 (如果pandoc可用)
        if exporter.pandoc_available:
            try:
                docx_content = exporter.generate_docx_report(test_results)
                print("✅ DOCX报告生成成功")
                print(f"   内容大小: {len(docx_content)} 字节")
            except Exception as e:
                print(f"❌ DOCX报告生成失败: {e}")
                return False
        else:
            print("⚠️ 跳过DOCX测试 (pandoc不可用)")

        return True

    except Exception as e:
        print(f"❌ 报告导出器测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🧪 pypandoc功能测试")
    print("=" * 50)

    tests = [
        ("pypandoc导入", test_pypandoc_import),
        ("pandoc版本", test_pandoc_version),
        ("pandoc下载", test_pandoc_download),
        ("Markdown转换", test_markdown_conversion),
        ("报告导出器", test_report_exporter),
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
    print("📊 测试结果总结")
    print("=" * 50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！pypandoc功能正常")
        return True
    print("⚠️ 部分测试失败，请检查配置")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
