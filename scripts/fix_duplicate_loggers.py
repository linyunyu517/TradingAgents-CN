#!/usr/bin/env python3
"""
修复重复logger定义问题的脚本

这个脚本会:
1. 扫描所有Python文件
2. 检测重复的logger = get_logger()定义
3. 移除重复定义，只保留文件头部的第一个定义
4. 生成详细的修复报告
"""

import os
import re


def find_python_files(root_dir: str, exclude_dirs: list[str] | None = None) -> list[str]:
    """查找所有Python文件"""
    if exclude_dirs is None:
        exclude_dirs = ["env", ".env", "__pycache__", ".git", "node_modules", ".venv"]

    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))

    return python_files


def analyze_logger_definitions(file_path: str) -> dict:
    """分析文件中的logger定义"""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return {"error": str(e), "logger_lines": []}

    logger_lines = []
    logger_pattern = re.compile(r"^\s*logger\s*=\s*get_logger\s*\(")

    for i, line in enumerate(lines, 1):
        if logger_pattern.match(line):
            logger_lines.append(
                {"line_number": i, "content": line.strip(), "indentation": len(line) - len(line.lstrip())},
            )

    return {"total_lines": len(lines), "logger_lines": logger_lines, "has_duplicates": len(logger_lines) > 1}


def find_import_section_end(lines: list[str]) -> int:
    """找到import语句结束的位置"""
    import_end = 0
    in_docstring = False
    docstring_char = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 处理文档字符串
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) == 1:  # 开始文档字符串
                    in_docstring = True
                # 如果同一行包含开始和结束，则不进入文档字符串状态
        elif docstring_char in stripped:
            in_docstring = False
            continue

        if in_docstring:
            continue

        # 跳过注释和空行
        if not stripped or stripped.startswith("#"):
            continue

        # 检查是否是import语句
        if (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("sys.path.")
            or stripped.startswith("load_dotenv(")
        ):
            import_end = i + 1
        elif stripped and not stripped.startswith("#"):
            # 遇到非import语句，停止
            break

    return import_end


def fix_duplicate_loggers(file_path: str) -> dict:
    """修复文件中的重复logger定义"""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return {"success": False, "error": f"读取文件失败: {e!s}"}

    analysis = analyze_logger_definitions(file_path)

    if not analysis["has_duplicates"]:
        return {"success": True, "message": "无需修复", "changes": 0}

    logger_lines = analysis["logger_lines"]
    if len(logger_lines) <= 1:
        return {"success": True, "message": "无需修复", "changes": 0}

    # 找到import语句结束位置
    import_end = find_import_section_end(lines)

    # 确定要保留的logger定义
    keep_logger = None
    remove_lines = []

    # 优先保留在import区域附近的logger定义
    for logger_info in logger_lines:
        line_num = logger_info["line_number"] - 1  # 转换为0索引
        if line_num <= import_end + 5:  # 在import区域附近
            if keep_logger is None:
                keep_logger = logger_info
            else:
                remove_lines.append(line_num)
        else:
            remove_lines.append(line_num)

    # 如果没有在import区域找到，保留第一个
    if keep_logger is None:
        keep_logger = logger_lines[0]
        remove_lines = [info["line_number"] - 1 for info in logger_lines[1:]]

    # 移除重复的logger定义（从后往前删除以保持行号正确）
    remove_lines.sort(reverse=True)
    changes_made = 0

    for line_num in remove_lines:
        if 0 <= line_num < len(lines):
            # 检查是否确实是logger定义
            if "logger = get_logger(" in lines[line_num]:
                lines.pop(line_num)
                changes_made += 1

    if changes_made > 0:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return {
                "success": True,
                "message": f"移除了{changes_made}个重复的logger定义",
                "changes": changes_made,
                "kept_logger": keep_logger["content"],
                "removed_count": changes_made,
            }
        except Exception as e:
            return {"success": False, "error": f"写入文件失败: {e!s}"}

    return {"success": True, "message": "无需修复", "changes": 0}


def main():
    """主函数"""
    root_dir = "c:\\code\\TradingAgentsCN"

    print("🔍 开始扫描Python文件...")
    python_files = find_python_files(root_dir)
    print(f"📁 找到 {len(python_files)} 个Python文件")

    # 分析所有文件
    print("\n📊 分析logger定义...")
    files_with_duplicates = []
    total_duplicates = 0

    for file_path in python_files:
        analysis = analyze_logger_definitions(file_path)
        if analysis.get("has_duplicates", False):
            files_with_duplicates.append((file_path, analysis))
            total_duplicates += len(analysis["logger_lines"]) - 1

    print(f"⚠️  发现 {len(files_with_duplicates)} 个文件有重复logger定义")
    print(f"📈 总共有 {total_duplicates} 个重复定义需要修复")

    if not files_with_duplicates:
        print("✅ 没有发现重复的logger定义！")
        return

    # 修复重复定义
    print("\n🔧 开始修复重复logger定义...")
    fixed_files = 0
    total_changes = 0
    errors = []

    for file_path, analysis in files_with_duplicates:
        rel_path = os.path.relpath(file_path, root_dir)
        print(f"\n📝 处理: {rel_path}")
        print(f"   发现 {len(analysis['logger_lines'])} 个logger定义")

        result = fix_duplicate_loggers(file_path)

        if result["success"]:
            if result["changes"] > 0:
                fixed_files += 1
                total_changes += result["changes"]
                print(f"   ✅ {result['message']}")
                if "kept_logger" in result:
                    print(f"   📌 保留: {result['kept_logger']}")
            else:
                print(f"   ℹ️  {result['message']}")
        else:
            errors.append((rel_path, result["error"]))
            print(f"   ❌ {result['error']}")

    # 生成报告
    print("\n" + "=" * 60)
    print("📋 修复报告")
    print("=" * 60)
    print(f"✅ 成功修复文件数: {fixed_files}")
    print(f"🔧 总共移除重复定义: {total_changes}")
    print(f"❌ 修复失败文件数: {len(errors)}")

    if errors:
        print("\n❌ 修复失败的文件:")
        for file_path, error in errors:
            print(f"   - {file_path}: {error}")

    # 保存详细报告
    report_file = "duplicate_logger_fix_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 重复Logger定义修复报告\n\n")
        f.write("## 概要\n\n")
        f.write(f"- 扫描文件总数: {len(python_files)}\n")
        f.write(f"- 发现重复定义文件数: {len(files_with_duplicates)}\n")
        f.write(f"- 成功修复文件数: {fixed_files}\n")
        f.write(f"- 总共移除重复定义: {total_changes}\n")
        f.write(f"- 修复失败文件数: {len(errors)}\n\n")

        if errors:
            f.write("## 修复失败的文件\n\n")
            for file_path, error in errors:
                f.write(f"- `{file_path}`: {error}\n")
            f.write("\n")

        f.write("## 修复详情\n\n")
        for file_path, analysis in files_with_duplicates:
            rel_path = os.path.relpath(file_path, root_dir)
            f.write(f"### {rel_path}\n\n")
            f.write(f"- 原有logger定义数: {len(analysis['logger_lines'])}\n")
            f.writelines(f"  - 第{logger_info['line_number']}行: `{logger_info['content']}`\n" for _i, logger_info in enumerate(analysis["logger_lines"]))
            f.write("\n")

    print(f"\n📄 详细报告已保存到: {report_file}")
    print("\n🎉 修复完成！")


if __name__ == "__main__":
    main()
