#!/usr/bin/env python3
"""
独立的文档转换测试脚本
用于测试Markdown到Word/PDF的转换，无需重新生成分析内容
"""

import os
import tempfile

import pypandoc


def test_markdown_content():
    """生成测试用的Markdown内容"""

    # 模拟真实的分析结果数据
    test_content = """# 605499 股票分析报告

**生成时间**: 2025-01-12 16:20:00
**分析状态**: 正式分析

## 🎯 投资决策摘要

| 指标 | 数值 |
|------|------|
| **投资建议** | BUY |
| **置信度** | 85.0% |
| **风险评分** | 25.0% |
| **目标价位** | ¥275.00 |

### 分析推理
基于技术分析和基本面分析，该股票显示出强劲的上涨趋势。市场情绪积极，建议买入。

## 📋 分析配置信息

- **LLM提供商**: qwen
- **LLM模型**: qwen-turbo
- **分析师**: market, fundamentals
- **研究深度**: 标准分析

## 📊 市场技术分析

### 技术指标分析
- **趋势方向**: 上涨
- **支撑位**: ¥250.00
- **阻力位**: ¥300.00
- **RSI指标**: 65 (中性偏强)

### 成交量分析
近期成交量放大，显示市场关注度提升。

## 📈 基本面分析

### 财务状况
- **营收增长**: 15.2%
- **净利润率**: 8.5%
- **ROE**: 12.3%

### 行业地位
公司在行业中处于领先地位，具有较强的竞争优势。

## ⚠️ 风险提示

1. **市场风险**: 整体市场波动可能影响股价
2. **行业风险**: 行业政策变化风险
3. **公司风险**: 经营管理风险

## 📝 免责声明

本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。

---
*报告生成时间: 2025-01-12 16:20:00*
"""

    return test_content


def save_test_content():
    """保存测试内容到文件"""
    content = test_markdown_content()

    with open("test_content.md", "w", encoding="utf-8") as f:
        f.write(content)

    print("✅ 测试内容已保存到 test_content.md")
    print(f"📊 内容长度: {len(content)} 字符")
    return content


def test_word_conversion(md_content):
    """测试Word转换"""
    print("\n🔄 测试Word转换...")

    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
            output_file = tmp_file.name

        print(f"📁 临时文件: {output_file}")

        # 测试不同的转换参数
        test_cases = [
            {"name": "基础转换", "format": "markdown", "extra_args": []},
            {"name": "带目录转换", "format": "markdown", "extra_args": ["--toc", "--number-sections"]},
            {"name": "禁用YAML转换", "format": "markdown", "extra_args": ["--from=markdown-yaml_metadata_block"]},
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 测试 {i}: {test_case['name']}")
            print(f"🔧 参数: format={test_case['format']}, extra_args={test_case['extra_args']}")

            try:
                pypandoc.convert_text(
                    md_content,
                    "docx",
                    format=test_case["format"],
                    outputfile=output_file,
                    extra_args=test_case["extra_args"],
                )

                # 检查文件
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    file_size = os.path.getsize(output_file)
                    print(f"✅ 转换成功! 文件大小: {file_size} 字节")

                    # 保存成功的文件
                    success_file = f"test_output_{i}.docx"
                    os.rename(output_file, success_file)
                    print(f"💾 文件已保存为: {success_file}")
                    return True
                print("❌ 转换失败: 文件未生成或为空")

            except Exception as e:
                print(f"❌ 转换失败: {e}")

            # 清理临时文件
            if os.path.exists(output_file):
                os.unlink(output_file)

        return False

    except Exception as e:
        print(f"❌ Word转换测试失败: {e}")
        return False


def test_pdf_conversion(md_content):
    """测试PDF转换"""
    print("\n🔄 测试PDF转换...")

    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            output_file = tmp_file.name

        print(f"📁 临时文件: {output_file}")

        # 测试不同的PDF引擎
        test_engines = [("wkhtmltopdf", "HTML转PDF引擎"), ("weasyprint", "现代HTML转PDF引擎"), (None, "默认引擎")]

        for i, (engine, description) in enumerate(test_engines, 1):
            print(f"\n📊 测试 {i}: {description}")

            try:
                extra_args = []
                if engine:
                    extra_args.append(f"--pdf-engine={engine}")
                    print(f"🔧 使用引擎: {engine}")
                else:
                    print("🔧 使用默认引擎")

                pypandoc.convert_text(
                    md_content, "pdf", format="markdown", outputfile=output_file, extra_args=extra_args,
                )

                # 检查文件
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    file_size = os.path.getsize(output_file)
                    print(f"✅ 转换成功! 文件大小: {file_size} 字节")

                    # 保存成功的文件
                    success_file = f"test_output_{i}.pdf"
                    os.rename(output_file, success_file)
                    print(f"💾 文件已保存为: {success_file}")
                    return True
                print("❌ 转换失败: 文件未生成或为空")

            except Exception as e:
                print(f"❌ 转换失败: {e}")

            # 清理临时文件
            if os.path.exists(output_file):
                os.unlink(output_file)

        return False

    except Exception as e:
        print(f"❌ PDF转换测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🧪 独立文档转换测试 (Volume映射版本)")
    print("=" * 50)
    print(f"📁 当前工作目录: {os.getcwd()}")
    print(f"🐳 Docker环境检测: {os.path.exists('/.dockerenv')}")

    # 保存测试内容
    md_content = save_test_content()

    # 测试Word转换
    word_success = test_word_conversion(md_content)

    # 测试PDF转换
    pdf_success = test_pdf_conversion(md_content)

    # 总结
    print("\n" + "=" * 50)
    print("📊 测试结果总结")
    print("=" * 50)
    print(f"Word转换: {'✅ 成功' if word_success else '❌ 失败'}")
    print(f"PDF转换:  {'✅ 成功' if pdf_success else '❌ 失败'}")

    if word_success or pdf_success:
        print("\n🎉 至少有一种格式转换成功!")
        print("💡 可以将成功的参数应用到主程序中")
    else:
        print("\n⚠️ 所有转换都失败了")
        print("💡 需要检查pandoc安装和配置")


if __name__ == "__main__":
    main()
