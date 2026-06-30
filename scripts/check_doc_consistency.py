#!/usr/bin/env python3
"""
文档一致性检查脚本
检查文档与代码的一致性，确保文档内容准确反映实际实现
"""

import ast
import re
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DocumentationChecker:
    """文档一致性检查器"""

    def __init__(self):
        self.project_root = project_root
        self.docs_dir = self.project_root / "docs"
        self.code_dir = self.project_root / "tradingagents"
        self.issues = []

    def check_all(self) -> dict[str, list[str]]:
        """执行所有检查"""
        print("🔍 开始文档一致性检查...")

        results = {
            "version_consistency": self.check_version_consistency(),
            "agent_architecture": self.check_agent_architecture(),
            "code_examples": self.check_code_examples(),
            "api_references": self.check_api_references(),
            "file_existence": self.check_file_existence(),
        }

        return results

    def check_version_consistency(self) -> list[str]:
        """检查版本一致性"""
        print("📋 检查版本一致性...")
        issues = []

        # 读取项目版本
        version_file = self.project_root / "VERSION"
        if not version_file.exists():
            issues.append("❌ VERSION 文件不存在")
            return issues

        project_version = version_file.read_text().strip()
        print(f"   项目版本: {project_version}")

        # 检查文档中的版本信息
        doc_files = list(self.docs_dir.rglob("*.md"))
        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")

                # 检查是否有版本头部
                if content.startswith("---"):
                    # 解析YAML头部
                    yaml_end = content.find("---", 3)
                    if yaml_end > 0:
                        yaml_content = content[3:yaml_end]

                        # 检查版本字段
                        version_match = re.search(r"version:\s*(.+)", yaml_content)
                        if version_match:
                            doc_version = version_match.group(1).strip()
                            if doc_version != project_version:
                                issues.append(
                                    f"⚠️ {doc_file.relative_to(self.project_root)}: 版本不一致 (文档: {doc_version}, 项目: {project_version})",
                                )
                        else:
                            issues.append(f"⚠️ {doc_file.relative_to(self.project_root)}: 缺少版本信息")
                # 核心文档应该有版本头部
                elif any(keyword in str(doc_file) for keyword in ["agents", "architecture", "development"]):
                    issues.append(f"⚠️ {doc_file.relative_to(self.project_root)}: 缺少版本头部")

            except Exception as e:
                issues.append(f"❌ 读取文档失败 {doc_file}: {e}")

        return issues

    def check_agent_architecture(self) -> list[str]:
        """检查智能体架构描述的一致性"""
        print("🤖 检查智能体架构一致性...")
        issues = []

        # 检查实际的智能体实现
        agents_code_dir = self.code_dir / "agents"
        if not agents_code_dir.exists():
            issues.append("❌ 智能体代码目录不存在")
            return issues

        # 获取实际的智能体列表
        actual_agents = {}
        for category in ["analysts", "researchers", "managers", "trader", "risk_mgmt"]:
            category_dir = agents_code_dir / category
            if category_dir.exists():
                actual_agents[category] = []
                for py_file in category_dir.glob("*.py"):
                    if py_file.name != "__init__.py":
                        actual_agents[category].append(py_file.stem)

        print(f"   发现的智能体: {actual_agents}")

        # 检查文档中的智能体描述
        agents_doc_dir = self.docs_dir / "agents"
        if agents_doc_dir.exists():
            for doc_file in agents_doc_dir.glob("*.md"):
                try:
                    content = doc_file.read_text(encoding="utf-8")

                    # 检查是否提到了BaseAnalyst类（应该已经移除）
                    if "class BaseAnalyst" in content:
                        issues.append(f"⚠️ {doc_file.name}: 仍然提到BaseAnalyst类，应该更新为函数式架构")

                    # 检查是否提到了create_*_analyst函数
                    if "create_" in content and "analyst" in content:
                        if "def create_" not in content:
                            issues.append(f"⚠️ {doc_file.name}: 提到create函数但没有正确的函数签名")

                except Exception as e:
                    issues.append(f"❌ 读取智能体文档失败 {doc_file}: {e}")

        return issues

    def check_code_examples(self) -> list[str]:
        """检查文档中的代码示例"""
        print("💻 检查代码示例...")
        issues = []

        doc_files = list(self.docs_dir.rglob("*.md"))
        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")

                # 提取Python代码块
                python_blocks = re.findall(r"```python\n(.*?)\n```", content, re.DOTALL)

                for i, code_block in enumerate(python_blocks):
                    # 基本语法检查
                    try:
                        # 简单的语法检查
                        ast.parse(code_block)
                    except SyntaxError as e:
                        issues.append(f"❌ {doc_file.relative_to(self.project_root)} 代码块 {i + 1}: 语法错误 - {e}")

                    # 检查是否使用了已废弃的类
                    if "BaseAnalyst" in code_block:
                        issues.append(
                            f"⚠️ {doc_file.relative_to(self.project_root)} 代码块 {i + 1}: 使用了已废弃的BaseAnalyst类",
                        )

                    # 检查导入语句的正确性
                    import_lines = [
                        line.strip() for line in code_block.split("\n") if line.strip().startswith("from tradingagents")
                    ]
                    for import_line in import_lines:
                        # 简单检查模块路径是否存在
                        if "from tradingagents.agents.analysts.base_analyst" in import_line:
                            issues.append(
                                f"⚠️ {doc_file.relative_to(self.project_root)} 代码块 {i + 1}: 导入不存在的base_analyst模块",
                            )

            except Exception as e:
                issues.append(f"❌ 检查代码示例失败 {doc_file}: {e}")

        return issues

    def check_api_references(self) -> list[str]:
        """检查API参考文档"""
        print("📚 检查API参考...")
        issues = []

        # 检查是否有API参考文档
        api_ref_dir = self.docs_dir / "reference"
        if not api_ref_dir.exists():
            issues.append("⚠️ 缺少API参考文档目录")
            return issues

        # 检查智能体API文档
        agents_ref = api_ref_dir / "agents"
        if not agents_ref.exists():
            issues.append("⚠️ 缺少智能体API参考文档")

        return issues

    def check_file_existence(self) -> list[str]:
        """检查文档中引用的文件是否存在"""
        print("📁 检查文件引用...")
        issues = []

        doc_files = list(self.docs_dir.rglob("*.md"))
        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")

                # 检查相对路径引用
                relative_refs = re.findall(r"\[.*?\]\(([^)]+)\)", content)
                for ref in relative_refs:
                    if ref.startswith(("http", "https", "mailto")):
                        continue

                    # 解析相对路径
                    ref_path = doc_file.parent / ref
                    if not ref_path.exists():
                        issues.append(f"❌ {doc_file.relative_to(self.project_root)}: 引用的文件不存在 - {ref}")

            except Exception as e:
                issues.append(f"❌ 检查文件引用失败 {doc_file}: {e}")

        return issues

    def generate_report(self, results: dict[str, list[str]]) -> str:
        """生成检查报告"""
        report = ["# 文档一致性检查报告\n"]
        report.append(f"**检查时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        total_issues = sum(len(issues) for issues in results.values())
        report.append(f"**总问题数**: {total_issues}\n")

        for category, issues in results.items():
            report.append(f"## {category.replace('_', ' ').title()}\n")

            if not issues:
                report.append("✅ 无问题发现\n")
            else:
                for issue in issues:
                    report.append(f"- {issue}")
                report.append("")

        return "\n".join(report)


def main():
    """主函数"""
    checker = DocumentationChecker()
    results = checker.check_all()

    # 生成报告
    report = checker.generate_report(results)

    # 保存报告
    report_file = checker.project_root / "docs" / "CONSISTENCY_CHECK_REPORT.md"
    report_file.write_text(report, encoding="utf-8")

    print(f"\n📊 检查完成！报告已保存到: {report_file}")
    print(f"总问题数: {sum(len(issues) for issues in results.values())}")

    # 如果有严重问题，返回非零退出码
    critical_issues = sum(1 for issues in results.values() for issue in issues if issue.startswith("❌"))
    if critical_issues > 0:
        print(f"⚠️ 发现 {critical_issues} 个严重问题，建议立即修复")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
