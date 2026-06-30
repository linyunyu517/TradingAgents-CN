#!/usr/bin/env python3
"""
版本管理工具
用于管理TradingAgents项目的版本号和发布流程
"""

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class VersionManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.version_file = self.project_root / "VERSION"
        self.changelog_file = self.project_root / "CHANGELOG.md"

    def get_current_version(self):
        """获取当前版本号"""
        try:
            with open(self.version_file) as f:
                return f.read().strip()
        except FileNotFoundError:
            return "cn-0.0.0"

    def set_version(self, version):
        """设置版本号"""
        with open(self.version_file, "w") as f:
            f.write(version)
        logger.info(f"✅ 版本号已更新为: {version}")

    def bump_version(self, bump_type):
        """递增版本号"""
        current = self.get_current_version()

        # 处理cn-前缀
        if current.startswith("cn-"):
            prefix = "cn-"
            version_part = current[3:]  # 去掉cn-前缀
        else:
            prefix = "cn-"  # 默认添加cn-前缀
            version_part = current

        try:
            major, minor, patch = map(int, version_part.split("."))
        except ValueError:
            # 如果解析失败，使用默认值
            major, minor, patch = 0, 1, 0

        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1
        else:
            raise ValueError("bump_type must be 'major', 'minor', or 'patch'")

        new_version = f"{prefix}{major}.{minor}.{patch}"
        self.set_version(new_version)
        return new_version

    def create_git_tag(self, version, message=None):
        """创建Git标签"""
        if message is None:
            message = f"Release version {version}"

        try:
            # 创建标签
            subprocess.run(["git", "tag", "-a", f"v{version}", "-m", message], check=True, cwd=self.project_root)
            logger.info(f"✅ Git标签 v{version} 已创建")

            # 推送标签
            subprocess.run(["git", "push", "origin", f"v{version}"], check=True, cwd=self.project_root)
            logger.info(f"✅ Git标签 v{version} 已推送到远程仓库")

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ 创建Git标签失败: {e}")

    def update_changelog(self, version, changes=None):
        """更新CHANGELOG文件"""
        if not self.changelog_file.exists():
            logger.error("❌ CHANGELOG.md 文件不存在")
            return

        # 读取现有内容
        with open(self.changelog_file, encoding="utf-8") as f:
            content = f.read()

        # 准备新版本条目
        today = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"\n## [{version}] - {today}\n\n"

        if changes:
            new_entry += changes + "\n"
        else:
            new_entry += "### 更改\n- 版本更新\n"

        # 在第一个版本条目前插入新条目
        lines = content.split("\n")
        insert_index = 0
        for i, line in enumerate(lines):
            if line.startswith("## [") and "Unreleased" not in line:
                insert_index = i
                break

        lines.insert(insert_index, new_entry)

        # 写回文件
        with open(self.changelog_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"✅ CHANGELOG.md 已更新，添加版本 {version}")

    def release(self, bump_type, message=None, changes=None):
        """执行完整的发布流程"""
        logger.info("🚀 开始发布流程...")

        # 检查Git状态
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=self.project_root,
            )
            if result.stdout.strip():
                logger.error("❌ 工作目录不干净，请先提交所有更改")
                return False
        except subprocess.CalledProcessError:
            logger.error("❌ 无法检查Git状态")
            return False

        # 递增版本号
        old_version = self.get_current_version()
        new_version = self.bump_version(bump_type)
        logger.info(f"📈 版本号从 {old_version} 更新到 {new_version}")

        # 更新CHANGELOG
        self.update_changelog(new_version, changes)

        # 提交版本更改
        try:
            subprocess.run(["git", "add", "VERSION", "CHANGELOG.md"], check=True, cwd=self.project_root)
            commit_message = message or f"chore: release version {new_version}"
            subprocess.run(["git", "commit", "-m", commit_message], check=True, cwd=self.project_root)
            logger.info("✅ 版本更改已提交")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ 提交失败: {e}")
            return False

        # 创建Git标签
        self.create_git_tag(new_version, message)

        logger.info(f"🎉 版本 {new_version} 发布完成！")
        return True

    def show_info(self):
        """显示版本信息"""
        current_version = self.get_current_version()
        logger.info("📊 TradingAgents 版本信息")
        logger.info(f"当前版本: {current_version}")
        logger.info(f"版本文件: {self.version_file}")
        logger.info(f"更新日志: {self.changelog_file}")

        # 显示Git标签
        try:
            result = subprocess.run(
                ["git", "tag", "--list", "v*"], capture_output=True, text=True, cwd=self.project_root,
            )
            tags = result.stdout.strip().split("\n") if result.stdout.strip() else []
            logger.info(f"Git标签: {', '.join(tags) if tags else '无'}")
        except subprocess.CalledProcessError:
            logger.info("Git标签: 无法获取")


def main():
    parser = argparse.ArgumentParser(description="TradingAgents 版本管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 显示信息命令
    subparsers.add_parser("info", help="显示版本信息")

    # 设置版本命令
    set_parser = subparsers.add_parser("set", help="设置版本号")
    set_parser.add_argument("version", help="版本号 (例如: 1.2.3)")

    # 递增版本命令
    bump_parser = subparsers.add_parser("bump", help="递增版本号")
    bump_parser.add_argument("type", choices=["major", "minor", "patch"], help="递增类型")

    # 发布命令
    release_parser = subparsers.add_parser("release", help="执行发布流程")
    release_parser.add_argument("type", choices=["major", "minor", "patch"], help="版本递增类型")
    release_parser.add_argument("-m", "--message", help="发布消息")
    release_parser.add_argument("-c", "--changes", help="更改说明")

    # 创建标签命令
    tag_parser = subparsers.add_parser("tag", help="为当前版本创建Git标签")
    tag_parser.add_argument("-m", "--message", help="标签消息")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    vm = VersionManager()

    if args.command == "info":
        vm.show_info()
    elif args.command == "set":
        vm.set_version(args.version)
    elif args.command == "bump":
        new_version = vm.bump_version(args.type)
        logger.info(f"新版本: {new_version}")
    elif args.command == "release":
        vm.release(args.type, args.message, args.changes)
    elif args.command == "tag":
        current_version = vm.get_current_version()
        vm.create_git_tag(current_version, args.message)


if __name__ == "__main__":
    main()
