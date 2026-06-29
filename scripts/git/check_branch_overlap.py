#!/usr/bin/env python3
"""
检查分支重叠和合并状态
分析AKShare和Tushare相关分支的关系
"""

import subprocess

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class BranchAnalyzer:
    def __init__(self):
        self.branches_to_check = [
            "feature/akshare-integration",
            "feature/akshare-integration-clean",
            "feature/tushare-integration",
        ]

    def run_git_command(self, command: list[str]) -> tuple:
        """运行Git命令"""
        try:
            result = subprocess.run(["git", *command], capture_output=True, text=True, check=True)
            return True, result.stdout.strip(), result.stderr.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stdout, e.stderr

    def get_branch_commits(self, branch: str) -> set[str]:
        """获取分支的提交哈希"""
        success, stdout, _ = self.run_git_command(["log", "--format=%H", branch])
        if success:
            return set(stdout.split("\n")) if stdout else set()
        return set()

    def get_branch_files(self, branch: str) -> set[str]:
        """获取分支修改的文件"""
        success, stdout, _ = self.run_git_command(["diff", "--name-only", "main", branch])
        if success:
            return set(stdout.split("\n")) if stdout else set()
        return set()

    def check_branch_exists(self, branch: str) -> bool:
        """检查分支是否存在"""
        success, _, _ = self.run_git_command(["show-ref", "--verify", f"refs/heads/{branch}"])
        return success

    def get_merge_base(self, branch1: str, branch2: str) -> str:
        """获取两个分支的合并基点"""
        success, stdout, _ = self.run_git_command(["merge-base", branch1, branch2])
        return stdout if success else ""

    def is_branch_merged(self, branch: str, target: str = "main") -> bool:
        """检查分支是否已合并到目标分支"""
        success, stdout, _ = self.run_git_command(["branch", "--merged", target])
        if success:
            merged_branches = [line.strip().replace("* ", "") for line in stdout.split("\n")]
            return branch in merged_branches
        return False

    def analyze_branches(self):
        """分析分支关系"""
        logger.debug("🔍 分析AKShare和Tushare分支关系")
        logger.info("=")

        # 检查分支存在性
        existing_branches = []
        for branch in self.branches_to_check:
            if self.check_branch_exists(branch):
                existing_branches.append(branch)
                logger.info(f"✅ 分支存在: {branch}")
            else:
                logger.error(f"❌ 分支不存在: {branch}")

        if len(existing_branches) < 2:
            logger.warning("\n⚠️ 可分析的分支数量不足")
            return

        logger.info(f"\n📊 分析 {len(existing_branches)} 个现有分支...")

        # 获取每个分支的提交和文件
        branch_data = {}
        for branch in existing_branches:
            commits = self.get_branch_commits(branch)
            files = self.get_branch_files(branch)
            is_merged = self.is_branch_merged(branch)

            branch_data[branch] = {
                "commits": commits,
                "files": files,
                "commit_count": len(commits),
                "file_count": len(files),
                "is_merged": is_merged,
            }

            logger.info(f"\n📋 {branch}:")
            logger.info(f"   提交数量: {len(commits)}")
            logger.info(f"   修改文件: {len(files)}")
            logger.info(f"   已合并到main: {'是' if is_merged else '否'}")

        # 分析分支重叠
        logger.info("\n🔄 分析分支重叠关系...")

        if "feature/tushare-integration" in branch_data:
            tushare_commits = branch_data["feature/tushare-integration"]["commits"]
            tushare_files = branch_data["feature/tushare-integration"]["files"]

            for branch in existing_branches:
                if branch == "feature/tushare-integration":
                    continue

                branch_commits = branch_data[branch]["commits"]
                branch_files = branch_data[branch]["files"]

                # 计算重叠
                commit_overlap = len(branch_commits.intersection(tushare_commits))
                file_overlap = len(branch_files.intersection(tushare_files))

                commit_percentage = (commit_overlap / len(branch_commits) * 100) if branch_commits else 0
                file_percentage = (file_overlap / len(branch_files) * 100) if branch_files else 0

                logger.info(f"\n🔗 {branch} vs feature/tushare-integration:")
                logger.info(f"   提交重叠: {commit_overlap}/{len(branch_commits)} ({commit_percentage:.1f}%)")
                logger.info(f"   文件重叠: {file_overlap}/{len(branch_files)} ({file_percentage:.1f}%)")

                # 判断是否可以删除
                if commit_percentage > 80 or file_percentage > 80:
                    logger.info(f"   💡 建议: 可以安全删除 {branch}")
                elif branch_data[branch]["is_merged"]:
                    logger.info(f"   💡 建议: 已合并到main，可以删除 {branch}")
                else:
                    logger.warning(f"   ⚠️ 建议: 需要进一步检查 {branch}")

        # 生成清理建议
        self.generate_cleanup_recommendations(branch_data)

    def generate_cleanup_recommendations(self, branch_data: dict):
        """生成清理建议"""
        logger.info("\n🧹 分支清理建议")
        logger.info("=")

        can_delete = []
        should_keep = []

        for branch, data in branch_data.items():
            if branch == "feature/tushare-integration":
                should_keep.append(branch)
                continue

            if data["is_merged"]:
                can_delete.append(f"{branch} (已合并到main)")
            elif data["commit_count"] == 0:
                can_delete.append(f"{branch} (无新提交)")
            else:
                # 需要进一步检查
                should_keep.append(f"{branch} (需要检查)")

        if can_delete:
            logger.info("✅ 可以安全删除的分支:")
            for branch in can_delete:
                logger.info(f"   - {branch}")

            logger.info("\n🔧 删除命令:")
            for branch_info in can_delete:
                branch = branch_info.split(" (")[0]
                logger.info(f"   git branch -d {branch}")
                logger.info(f"   git push origin --delete {branch}")

        if should_keep:
            logger.warning("\n⚠️ 建议保留的分支:")
            for branch in should_keep:
                logger.info(f"   - {branch}")

        # 特别建议
        logger.info("\n💡 特别建议:")
        logger.info("   1. feature/tushare-integration 包含最完整的功能，应该保留")
        logger.info("   2. 如果AKShare分支的功能已经在Tushare分支中，可以删除")
        logger.info("   3. 删除前建议创建备份分支")
        logger.info("   4. 确认团队成员没有在使用这些分支")

    def create_backup_script(self):
        """创建备份脚本"""
        logger.info("\n💾 创建备份脚本")
        logger.info("=")

        backup_script = """#!/bin/bash
# 分支备份脚本
echo "🔄 创建分支备份..."

# 创建备份分支
git checkout feature/akshare-integration 2>/dev/null && git checkout -b backup/akshare-integration-$(date +%Y%m%d)
git checkout feature/akshare-integration-clean 2>/dev/null && git checkout -b backup/akshare-integration-clean-$(date +%Y%m%d)

# 推送备份到远程
git push origin backup/akshare-integration-$(date +%Y%m%d) 2>/dev/null
git push origin backup/akshare-integration-clean-$(date +%Y%m%d) 2>/dev/null

echo "✅ 备份完成"
"""

        with open("backup_branches.sh", "w") as f:
            f.write(backup_script)

        logger.info("📝 备份脚本已创建: backup_branches.sh")
        logger.info("💡 使用方法: bash backup_branches.sh")


def main():
    analyzer = BranchAnalyzer()
    analyzer.analyze_branches()
    analyzer.create_backup_script()

    logger.info("\n🎯 总结建议:")
    logger.info("1. 运行此脚本查看详细分析结果")
    logger.info("2. 如果确认AKShare分支功能已包含在Tushare分支中，可以删除")
    logger.info("3. 删除前先创建备份分支")
    logger.info("4. 保留feature/tushare-integration作为主要开发分支")


if __name__ == "__main__":
    main()
