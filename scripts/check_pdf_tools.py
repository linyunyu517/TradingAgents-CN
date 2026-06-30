#!/usr/bin/env python3
"""
PDF导出工具检查脚本
检查系统中PDF导出所需的工具是否已安装
"""

import platform
import subprocess
import sys


def print_header(text):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def check_command(command, name):
    """检查命令是否可用"""
    try:
        result = subprocess.run([command, "--version"], capture_output=True, timeout=5, text=True)
        if result.returncode == 0:
            version = result.stdout.split("\n")[0]
            print(f"✅ {name}: 已安装")
            print(f"   版本: {version}")
            return True
        print(f"❌ {name}: 未安装或无法运行")
        return False
    except FileNotFoundError:
        print(f"❌ {name}: 未安装")
        return False
    except Exception as e:
        print(f"❌ {name}: 检查失败 - {e}")
        return False


def check_python_package(package_name, import_name=None):
    """检查Python包是否已安装"""
    if import_name is None:
        import_name = package_name

    try:
        __import__(import_name)
        print(f"✅ {package_name}: 已安装")
        return True
    except ImportError:
        print(f"❌ {package_name}: 未安装")
        return False


def get_install_instructions():
    """获取安装说明"""
    os_type = platform.system()

    instructions = {
        "Windows": """
📦 Windows 安装指南:

1. 安装 wkhtmltopdf (推荐):
   - 下载: https://wkhtmltopdf.org/downloads.html
   - 选择 Windows 版本 (64-bit)
   - 安装后添加到系统 PATH

   或使用 Chocolatey:
   choco install wkhtmltopdf

2. 安装 Python 包:
   pip install pdfkit pypandoc markdown

3. 安装 Pandoc:
   - 下载: https://pandoc.org/installing.html
   - 或使用 Chocolatey:
   choco install pandoc
""",
        "Darwin": """
📦 macOS 安装指南:

1. 安装 wkhtmltopdf (推荐):
   brew install wkhtmltopdf

2. 安装 Python 包:
   pip install pdfkit pypandoc markdown

3. 安装 Pandoc:
   brew install pandoc
""",
        "Linux": """
📦 Linux 安装指南:

1. 安装 wkhtmltopdf (推荐):
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install wkhtmltopdf

   # CentOS/RHEL
   sudo yum install wkhtmltopdf

2. 安装 Python 包:
   pip install pdfkit pypandoc markdown

3. 安装 Pandoc:
   # Ubuntu/Debian
   sudo apt-get install pandoc

   # CentOS/RHEL
   sudo yum install pandoc
""",
    }

    return instructions.get(os_type, instructions["Linux"])


def main():
    """主函数"""
    print_header("PDF 导出工具检查")

    print(f"\n🖥️  操作系统: {platform.system()} {platform.release()}")
    print(f"🐍 Python 版本: {sys.version.split()[0]}")

    # 检查 Python 包
    print_header("Python 包检查")
    pdfkit_ok = check_python_package("pdfkit")
    pypandoc_ok = check_python_package("pypandoc")
    markdown_ok = check_python_package("markdown")

    # 检查系统工具
    print_header("系统工具检查")
    wkhtmltopdf_ok = check_command("wkhtmltopdf", "wkhtmltopdf")
    pandoc_ok = check_command("pandoc", "Pandoc")

    # 总结
    print_header("检查结果")

    all_ok = all([pdfkit_ok, pypandoc_ok, markdown_ok, wkhtmltopdf_ok, pandoc_ok])

    if all_ok:
        print("✅ 所有 PDF 导出工具已正确安装！")
        print("\n您可以使用以下功能:")
        print("  - Markdown 导出")
        print("  - Word (DOCX) 导出")
        print("  - PDF 导出")
    else:
        print("⚠️  部分工具未安装，PDF 导出功能可能不可用")
        print("\n当前可用功能:")
        if markdown_ok:
            print("  ✅ Markdown 导出")
        if pypandoc_ok and pandoc_ok:
            print("  ✅ Word (DOCX) 导出")
        if pdfkit_ok and wkhtmltopdf_ok:
            print("  ✅ PDF 导出")

        print("\n缺失的工具:")
        if not pdfkit_ok:
            print("  ❌ pdfkit (Python 包)")
        if not pypandoc_ok:
            print("  ❌ pypandoc (Python 包)")
        if not markdown_ok:
            print("  ❌ markdown (Python 包)")
        if not wkhtmltopdf_ok:
            print("  ❌ wkhtmltopdf (系统工具)")
        if not pandoc_ok:
            print("  ❌ Pandoc (系统工具)")

        # 显示安装说明
        print(get_install_instructions())

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
