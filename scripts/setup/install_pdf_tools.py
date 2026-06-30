#!/usr/bin/env python3
"""
PDF 导出工具安装脚本

此脚本帮助安装 PDF 导出所需的依赖包。

支持的 PDF 生成工具：
1. WeasyPrint（推荐）- 纯 Python 实现，无需外部依赖
2. pdfkit + wkhtmltopdf - 需要安装 wkhtmltopdf
3. Pandoc - 需要安装 pandoc

使用方法：
    python scripts/setup/install_pdf_tools.py
"""

import platform
import subprocess
import sys


def run_command(command, description):
    """运行命令并显示结果"""
    print(f"\n{'=' * 60}")
    print(f"📦 {description}")
    print(f"{'=' * 60}")
    print(f"命令: {command}")

    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ 成功: {description}")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {description}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return False


def check_installed(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name

    try:
        __import__(import_name)
        print(f"✅ {package_name} 已安装")
        return True
    except ImportError:
        print(f"❌ {package_name} 未安装")
        return False


def install_weasyprint():
    """安装 WeasyPrint"""
    print("\n" + "=" * 60)
    print("📦 安装 WeasyPrint（推荐）")
    print("=" * 60)
    print("WeasyPrint 是一个纯 Python 的 PDF 生成工具，无需外部依赖。")
    print("优点：")
    print("  - 纯 Python 实现，跨平台")
    print("  - 支持 CSS 样式")
    print("  - 中文支持良好")
    print("  - 无需安装额外的系统工具")

    if check_installed("weasyprint"):
        return True

    print("\n开始安装 WeasyPrint...")

    # Windows 需要先安装 GTK3
    if platform.system() == "Windows":
        print("\n⚠️ Windows 系统需要先安装 GTK3 运行时")
        print("请访问: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases")
        print("下载并安装 gtk3-runtime-x.x.x-x-x-x-ts-win64.exe")
        print("\n或者使用 WeasyPrint 的 Windows 版本:")

        success = run_command(f"{sys.executable} -m pip install weasyprint", "安装 WeasyPrint")
    else:
        # Linux/Mac 可以直接安装
        success = run_command(f"{sys.executable} -m pip install weasyprint", "安装 WeasyPrint")

    return success


def install_pdfkit():
    """安装 pdfkit"""
    print("\n" + "=" * 60)
    print("📦 安装 pdfkit + wkhtmltopdf")
    print("=" * 60)
    print("pdfkit 需要配合 wkhtmltopdf 使用。")
    print("优点：")
    print("  - 渲染效果好")
    print("  - 支持复杂的 HTML/CSS")

    if check_installed("pdfkit"):
        print("✅ pdfkit 已安装")
    else:
        print("\n开始安装 pdfkit...")
        success = run_command(f"{sys.executable} -m pip install pdfkit", "安装 pdfkit")
        if not success:
            return False

    # 检查 wkhtmltopdf
    print("\n检查 wkhtmltopdf...")
    try:
        result = subprocess.run("wkhtmltopdf --version", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ wkhtmltopdf 已安装")
            print(result.stdout)
            return True
    except Exception:
        pass

    print("❌ wkhtmltopdf 未安装")
    print("\n请手动安装 wkhtmltopdf:")

    system = platform.system()
    if system == "Windows":
        print("  Windows: https://wkhtmltopdf.org/downloads.html")
        print("  下载并安装 wkhtmltopdf-x.x.x.exe")
    elif system == "Darwin":
        print("  macOS: brew install wkhtmltopdf")
    elif system == "Linux":
        print("  Ubuntu/Debian: sudo apt-get install wkhtmltopdf")
        print("  CentOS/RHEL: sudo yum install wkhtmltopdf")

    return False


def install_pandoc():
    """安装 Pandoc 相关工具"""
    print("\n" + "=" * 60)
    print("📦 安装 Pandoc（回退方案）")
    print("=" * 60)
    print("Pandoc 是一个通用的文档转换工具。")

    # 安装 pypandoc
    if check_installed("pypandoc"):
        print("✅ pypandoc 已安装")
    else:
        print("\n开始安装 pypandoc...")
        success = run_command(f"{sys.executable} -m pip install pypandoc", "安装 pypandoc")
        if not success:
            return False

    # 检查 pandoc
    print("\n检查 pandoc...")
    try:
        result = subprocess.run("pandoc --version", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ pandoc 已安装")
            print(result.stdout.split("\n")[0])
            return True
    except Exception:
        pass

    print("❌ pandoc 未安装")
    print("\n请手动安装 pandoc:")

    system = platform.system()
    if system == "Windows":
        print("  Windows: https://pandoc.org/installing.html")
        print("  或使用: choco install pandoc")
    elif system == "Darwin":
        print("  macOS: brew install pandoc")
    elif system == "Linux":
        print("  Ubuntu/Debian: sudo apt-get install pandoc")
        print("  CentOS/RHEL: sudo yum install pandoc")

    return False


def install_markdown():
    """安装 markdown 库"""
    print("\n" + "=" * 60)
    print("📦 安装 markdown（必需）")
    print("=" * 60)

    if check_installed("markdown"):
        return True

    return run_command(f"{sys.executable} -m pip install markdown", "安装 markdown")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 PDF 导出工具安装脚本")
    print("=" * 60)
    print(f"Python 版本: {sys.version}")
    print(f"操作系统: {platform.system()} {platform.release()}")

    # 1. 安装 markdown（必需）
    install_markdown()

    # 2. 安装 WeasyPrint（推荐）
    weasyprint_ok = install_weasyprint()

    # 3. 安装 pdfkit（可选）
    pdfkit_ok = install_pdfkit()

    # 4. 安装 Pandoc（回退）
    pandoc_ok = install_pandoc()

    # 总结
    print("\n" + "=" * 60)
    print("📊 安装总结")
    print("=" * 60)

    if weasyprint_ok:
        print("✅ WeasyPrint 可用（推荐）")
    else:
        print("❌ WeasyPrint 不可用")

    if pdfkit_ok:
        print("✅ pdfkit + wkhtmltopdf 可用")
    else:
        print("⚠️ pdfkit + wkhtmltopdf 不完全可用")

    if pandoc_ok:
        print("✅ Pandoc 可用（回退方案）")
    else:
        print("⚠️ Pandoc 不完全可用")

    print("\n" + "=" * 60)
    if weasyprint_ok or pdfkit_ok or pandoc_ok:
        print("✅ 至少有一个 PDF 生成工具可用，可以开始使用！")
    else:
        print("❌ 没有可用的 PDF 生成工具，请按照上述提示安装。")
    print("=" * 60)

    print("\n💡 推荐安装顺序:")
    print("  1. WeasyPrint（最简单，推荐）")
    print("  2. pdfkit + wkhtmltopdf（效果好）")
    print("  3. Pandoc（回退方案）")


if __name__ == "__main__":
    main()
