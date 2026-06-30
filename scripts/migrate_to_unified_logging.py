#!/usr/bin/env python3
"""
模块日志迁移脚本
自动将项目模块迁移到统一日志系统
"""

import argparse
import re
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class LoggingMigrator:
    """日志系统迁移器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.migrated_files = []
        self.errors = []

        # 模块到日志初始化函数的映射
        self.module_logger_map = {
            "web": "setup_web_logging",
            "tradingagents/llm_adapters": "setup_llm_logging",
            "tradingagents/dataflows": "setup_dataflow_logging",
            "tradingagents/graph": 'get_logger("graph")',
            "tradingagents/agents": 'get_logger("agents")',
            "tradingagents/api": 'get_logger("api")',
            "tradingagents/utils": 'get_logger("utils")',
            "cli": 'get_logger("cli")',
            "scripts": 'get_logger("scripts")',
        }

    def migrate_file(self, file_path: Path) -> bool:
        """迁移单个文件"""
        try:
            logger.info(f"🔄 迁移文件: {file_path}")

            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # 1. 添加日志导入
            content = self._add_logging_import(content, file_path)

            # 2. 替换logging.getLogger()调用
            content = self._replace_get_logger(content, file_path)

            # 3. 替换print语句
            content = self._replace_print_statements(content)

            # 4. 替换traceback.print_exc()
            content = self._replace_traceback_print(content)

            # 如果有修改，写回文件
            if content != original_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                self.migrated_files.append(str(file_path))
                logger.info(f"✅ 迁移完成: {file_path}")
                return True
            logger.info(f"⏭️  无需修改: {file_path}")
            return False

        except Exception as e:
            error_msg = f"❌ 迁移失败 {file_path}: {e}"
            print(error_msg)
            self.errors.append(error_msg)
            return False

    def _add_logging_import(self, content: str, file_path: Path) -> str:
        """添加统一日志导入"""
        # 检查是否已经有统一日志导入
        if "from tradingagents.utils.logging_init import" in content:
            return content

        # 确定使用哪个日志初始化函数
        logger_func = self._get_logger_function(file_path)

        # 查找合适的插入位置（在其他导入之后）
        lines = content.split("\n")
        insert_pos = 0

        # 找到最后一个import语句的位置
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")) and "logging_init" not in line:
                insert_pos = i + 1

        # 插入日志导入
        if logger_func.startswith("setup_"):
            import_line = f"from tradingagents.utils.logging_init import {logger_func}"
            logger_line = f"logger = {logger_func}()"
        else:
            import_line = "from tradingagents.utils.logging_init import get_logger"
            logger_line = f"logger = {logger_func}"

        lines.insert(insert_pos, "")
        lines.insert(insert_pos + 1, "# 导入统一日志系统")
        lines.insert(insert_pos + 2, import_line)
        lines.insert(insert_pos + 3, logger_line)

        return "\n".join(lines)

    def _get_logger_function(self, file_path: Path) -> str:
        """根据文件路径确定日志初始化函数"""
        path_str = str(file_path)

        for module_path, logger_func in self.module_logger_map.items():
            if module_path in path_str:
                return logger_func

        # 默认使用通用日志器
        return 'get_logger("default")'

    def _replace_get_logger(self, content: str, file_path: Path) -> str:
        """替换logging.getLogger()调用"""
        # 替换 self.logger = logging.getLogger(__name__)
        content = re.sub(r"self\.logger\s*=\s*logging\.getLogger\(__name__\)", "self.logger = logger", content)

        # 替换 logger = logging.getLogger(__name__)
        content = re.sub(r"logger\s*=\s*logging\.getLogger\(__name__\)", "# logger已在导入时初始化", content)

        # 替换其他logging.getLogger()调用
        content = re.sub(r"logging\.getLogger\([^)]+\)", "logger", content)

        return content

    def _replace_print_statements(self, content: str) -> str:
        """替换print语句为logger调用"""
        lines = content.split("\n")
        modified_lines = []

        for line in lines:
            # 跳过注释和字符串中的print
            if line.strip().startswith("#"):
                modified_lines.append(line)
                continue

            # 查找print语句
            print_pattern = r'print\s*\(\s*f?["\']([^"\']*)["\']([^)]*)\)'
            match = re.search(print_pattern, line)

            if match:
                message = match.group(1)
                rest = match.group(2)

                # 根据消息内容确定日志级别
                if any(indicator in message for indicator in ["❌", "错误", "ERROR", "Error", "失败"]):
                    log_level = "error"
                elif any(indicator in message for indicator in ["⚠️", "警告", "WARNING", "Warning"]):
                    log_level = "warning"
                elif any(indicator in message for indicator in ["🔍", "DEBUG", "Debug"]):
                    log_level = "debug"
                else:
                    log_level = "info"

                # 构建新的日志语句
                indent = len(line) - len(line.lstrip())
                if rest.strip():
                    new_line = f'{" " * indent}logger.{log_level}(f"{message}"{rest})'
                else:
                    new_line = f'{" " * indent}logger.{log_level}(f"{message}")'

                modified_lines.append(new_line)
            else:
                modified_lines.append(line)

        return "\n".join(modified_lines)

    def _replace_traceback_print(self, content: str) -> str:
        """替换traceback.print_exc()为logger.error(..., exc_info=True)"""
        # 替换 traceback.print_exc()
        content = re.sub(
            r"traceback\.print_exc\(\)",
            "",  # 删除，因为logger.error(..., exc_info=True)已经包含了
            content,
        )

        # 如果有import traceback但不再使用，可以考虑删除
        # 这里暂时保留，避免破坏其他用途

        return content

    def migrate_directory(self, directory: Path, recursive: bool = True) -> dict[str, int]:
        """迁移目录中的所有Python文件"""
        stats = {"migrated": 0, "skipped": 0, "errors": 0}

        pattern = "**/*.py" if recursive else "*.py"

        for py_file in directory.glob(pattern):
            # 跳过特定文件
            if any(skip in str(py_file) for skip in ["__pycache__", ".git", "test_", "logging_"]):
                continue

            if self.migrate_file(py_file):
                stats["migrated"] += 1
            elif str(py_file) in [error.split(":")[0] for error in self.errors]:
                stats["errors"] += 1
            else:
                stats["skipped"] += 1

        return stats

    def generate_report(self) -> str:
        """生成迁移报告"""
        report = f"""
# 日志系统迁移报告

## 迁移统计
- 成功迁移文件: {len(self.migrated_files)}
- 错误数量: {len(self.errors)}

## 迁移的文件
"""
        for file_path in self.migrated_files:
            report += f"- {file_path}\n"

        if self.errors:
            report += "\n## 错误列表\n"
            for error in self.errors:
                report += f"- {error}\n"

        report += """
## 下一步
1. 测试迁移后的功能
2. 检查日志输出是否正常
3. 调整日志级别配置
4. 验证结构化日志功能
"""

        return report


def main():
    parser = argparse.ArgumentParser(description="迁移项目到统一日志系统")
    parser.add_argument("--target", "-t", help="目标目录或文件")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归处理子目录")
    parser.add_argument("--report", help="生成报告文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要修改的文件，不实际修改")

    args = parser.parse_args()

    # 确定项目根目录
    project_root = Path(__file__).parent.parent

    # 创建迁移器
    migrator = LoggingMigrator(project_root)

    # 确定目标
    if args.target:
        target_path = Path(args.target)
        if not target_path.is_absolute():
            target_path = project_root / target_path
    else:
        target_path = project_root / "tradingagents"

    logger.info(f"🎯 开始迁移: {target_path}")
    logger.info("=")

    # 执行迁移
    if target_path.is_file():
        migrator.migrate_file(target_path)
    else:
        stats = migrator.migrate_directory(target_path, args.recursive)
        logger.error(f"\n📊 迁移统计: 成功={stats['migrated']}, 跳过={stats['skipped']}, 错误={stats['errors']}")

    # 生成报告
    if args.report:
        report = migrator.generate_report()
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"📄 报告已保存到: {args.report}")

    logger.info("\n✅ 迁移完成!")


if __name__ == "__main__":
    main()
