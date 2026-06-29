#!/usr/bin/env python3
"""
语法检查器 - 检查项目中所有Python文件的语法错误
Syntax Checker - Check syntax errors in all Python files in the project
"""

import os
import py_compile
import sys
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("default")


def find_python_files(root_dir: str, exclude_dirs: list[str] | None = None) -> list[str]:
    """
    查找项目中所有Python文件，排除指定目录
    Find all Python files in the project, excluding specified directories
    """
    if exclude_dirs is None:
        exclude_dirs = ["env", "venv", "__pycache__", ".git", "node_modules", ".pytest_cache"]

    python_files = []
    root_path = Path(root_dir)

    for file_path in root_path.rglob("*.py"):
        # 检查是否在排除目录中
        if any(exclude_dir in file_path.parts for exclude_dir in exclude_dirs):
            continue
        python_files.append(str(file_path))

    return sorted(python_files)


def check_syntax(file_path: str) -> tuple[bool, str]:
    """
    检查单个Python文件的语法
    Check syntax of a single Python file

    Returns:
        Tuple[bool, str]: (是否有语法错误, 错误信息)
    """
    try:
        py_compile.compile(file_path, doraise=True)
        return False, ""
    except py_compile.PyCompileError as e:
        return True, str(e)
    except Exception as e:
        return True, f"Unexpected error: {e!s}"


def main():
    """
    主函数 - 执行语法检查
    Main function - Execute syntax checking
    """
    logger.error("🔍 开始检查项目中的Python文件语法错误...")
    logger.debug("🔍 Starting syntax check for Python files in the project...\n")

    # 获取当前目录
    current_dir = os.getcwd()
    logger.info(f"📁 检查目录: {current_dir}")
    logger.info(f"📁 Checking directory: {current_dir}\n")

    # 查找所有Python文件
    python_files = find_python_files(current_dir)
    logger.info(f"📊 找到 {len(python_files)} 个Python文件")
    logger.info(f"📊 Found {len(python_files)} Python files\n")

    # 检查语法错误
    error_files = []
    success_count = 0

    for i, file_path in enumerate(python_files, 1):
        relative_path = os.path.relpath(file_path, current_dir)
        logger.info(f"[{i:3d}/{len(python_files)}] 检查: {relative_path}", end=" ")

        has_error, error_msg = check_syntax(file_path)

        if has_error:
            logger.error("❌ 语法错误")
            error_files.append((relative_path, error_msg))
        else:
            logger.info("✅ 语法正确")
            success_count += 1

    # 输出结果摘要
    logger.info("\n")
    logger.info("📋 检查结果摘要 | Check Results Summary")
    logger.info("=")
    logger.info(f"✅ 语法正确的文件: {success_count}")
    logger.info(f"✅ Files with correct syntax: {success_count}")
    logger.error(f"❌ 有语法错误的文件: {len(error_files)}")
    logger.error(f"❌ Files with syntax errors: {len(error_files)}")

    if error_files:
        logger.error("\n🚨 语法错误详情 | Syntax Error Details:")
        logger.info("-")
        for file_path, error_msg in error_files:
            logger.info(f"\n📄 文件: {file_path}")
            logger.info(f"📄 File: {file_path}")
            logger.error(f"🔴 错误: {error_msg}")
            logger.error(f"🔴 Error: {error_msg}")

        logger.error("\n💡 建议: 请修复上述语法错误后重新运行检查")
        logger.info("💡 Suggestion: Please fix the above syntax errors and run the check again")
        sys.exit(1)
    else:
        logger.info("\n🎉 恭喜！所有Python文件语法检查通过！")
        logger.info("🎉 Congratulations! All Python files passed syntax check!")
        sys.exit(0)


if __name__ == "__main__":
    main()
