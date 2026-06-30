#!/usr/bin/env python3
"""
批量更新文档脚本
为所有核心文档添加版本信息头部，修复常见问题
"""

import re
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DocumentationUpdater:
    """文档批量更新器"""

    def __init__(self):
        self.project_root = project_root
        self.docs_dir = self.project_root / "docs"

        # 读取当前版本
        version_file = self.project_root / "VERSION"
        if version_file.exists():
            self.current_version = version_file.read_text().strip()
        else:
            self.current_version = "cn-0.1.13-preview"

        self.current_date = datetime.now().strftime("%Y-%m-%d")

        # 需要添加版本头部的核心文档
        self.core_docs = [
            "agents/managers.md",
            "agents/researchers.md",
            "agents/risk-management.md",
            "agents/trader.md",
            "architecture/agent-architecture.md",
            "architecture/data-flow-architecture.md",
            "architecture/system-architecture.md",
            "development/CONTRIBUTING.md",
            "development/development-workflow.md",
        ]

    def create_version_header(self, status: str = "待更新") -> str:
        """创建版本信息头部"""
        return f"""---
version: {self.current_version}
last_updated: {self.current_date}
code_compatibility: {self.current_version}
status: {status}
---

"""

    def add_version_headers(self) -> list[str]:
        """为核心文档添加版本头部"""
        print("📝 为核心文档添加版本头部...")
        updated_files = []

        for doc_path in self.core_docs:
            full_path = self.docs_dir / doc_path
            if not full_path.exists():
                print(f"   ⚠️ 文件不存在: {doc_path}")
                continue

            try:
                content = full_path.read_text(encoding="utf-8")

                # 检查是否已有版本头部
                if content.startswith("---"):
                    print(f"   ✅ 已有版本头部: {doc_path}")
                    continue

                # 添加版本头部
                new_content = self.create_version_header() + content
                full_path.write_text(new_content, encoding="utf-8")
                updated_files.append(doc_path)
                print(f"   ✅ 已更新: {doc_path}")

            except Exception as e:
                print(f"   ❌ 更新失败 {doc_path}: {e}")

        return updated_files

    def fix_code_blocks(self) -> list[str]:
        """修复文档中的代码块问题"""
        print("🔧 修复代码块问题...")
        fixed_files = []

        # 查找所有markdown文件
        md_files = list(self.docs_dir.rglob("*.md"))

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                original_content = content

                # 修复常见的代码块问题

                # 1. 修复中文冒号
                content = re.sub(r"：", ":", content)

                # 2. 修复箭头符号（在代码块中）
                content = re.sub(r"→", "->", content)

                # 3. 修复BaseAnalyst引用（在代码块外的说明中）
                if "BaseAnalyst" in content and "已废弃" not in content:
                    # 在提到BaseAnalyst的地方添加废弃说明
                    content = re.sub(r"BaseAnalyst", "BaseAnalyst (已废弃，现使用函数式架构)", content)

                # 4. 修复不完整的代码块
                # 查找以```python开始但没有正确结束的代码块
                python_blocks = re.findall(r"```python\n(.*?)\n```", content, re.DOTALL)
                for block in python_blocks:
                    if block.strip().endswith(":") and not block.strip().endswith('"""'):
                        # 不完整的函数定义，添加pass
                        fixed_block = block + "\n    pass"
                        content = content.replace(f"```python\n{block}\n```", f"```python\n{fixed_block}\n```")

                # 如果内容有变化，保存文件
                if content != original_content:
                    md_file.write_text(content, encoding="utf-8")
                    fixed_files.append(str(md_file.relative_to(self.project_root)))
                    print(f"   ✅ 已修复: {md_file.relative_to(self.project_root)}")

            except Exception as e:
                print(f"   ❌ 修复失败 {md_file}: {e}")

        return fixed_files

    def update_status_tracking(self, updated_files: list[str], fixed_files: list[str]):
        """更新文档状态追踪"""
        print("📊 更新文档状态追踪...")

        status_file = self.docs_dir / "DOCUMENTATION_STATUS.md"
        if not status_file.exists():
            print("   ⚠️ 状态追踪文件不存在")
            return

        try:
            content = status_file.read_text(encoding="utf-8")

            # 更新最后更新时间
            content = re.sub(r"> \*\*最后更新\*\*: \d{4}-\d{2}-\d{2}", f"> **最后更新**: {self.current_date}", content)

            # 在文档末尾添加更新记录
            update_record = f"""
## 最新更新记录

### {self.current_date} 批量更新
- ✅ 为 {len(updated_files)} 个核心文档添加了版本头部
- 🔧 修复了 {len(fixed_files)} 个文档的代码块问题
- 📝 更新了文档状态追踪

**更新的文档:**
{chr(10).join(f"- {file}" for file in updated_files)}

**修复的文档:**
{chr(10).join(f"- {file}" for file in fixed_files)}
"""

            content += update_record
            status_file.write_text(content, encoding="utf-8")
            print("   ✅ 状态追踪已更新")

        except Exception as e:
            print(f"   ❌ 更新状态追踪失败: {e}")

    def generate_summary_report(self, updated_files: list[str], fixed_files: list[str]) -> str:
        """生成更新摘要报告"""
        report = f"""# 文档批量更新报告

**更新时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**项目版本**: {self.current_version}

## 更新摘要

- 📝 添加版本头部: {len(updated_files)} 个文件
- 🔧 修复代码块问题: {len(fixed_files)} 个文件
- 📊 更新状态追踪: 1 个文件

## 详细更新列表

### 添加版本头部的文档
{chr(10).join(f"- ✅ {file}" for file in updated_files) if updated_files else "- 无"}

### 修复代码块的文档
{chr(10).join(f"- 🔧 {file}" for file in fixed_files) if fixed_files else "- 无"}

## 下一步建议

1. **继续更新其他文档**: 还有更多文档需要添加版本头部
2. **验证代码示例**: 检查修复后的代码块是否正确
3. **更新API参考**: 创建或更新API参考文档
4. **建立定期检查**: 设置定期的文档一致性检查

## 质量检查

建议运行以下命令验证更新效果：
```bash
python scripts/check_doc_consistency.py
```

---
*此报告由批量更新脚本自动生成*
"""
        return report


def main():
    """主函数"""
    print("🚀 开始批量更新文档...")

    updater = DocumentationUpdater()

    # 1. 添加版本头部
    updated_files = updater.add_version_headers()

    # 2. 修复代码块问题
    fixed_files = updater.fix_code_blocks()

    # 3. 更新状态追踪
    updater.update_status_tracking(updated_files, fixed_files)

    # 4. 生成摘要报告
    report = updater.generate_summary_report(updated_files, fixed_files)
    report_file = updater.project_root / "docs" / "BATCH_UPDATE_REPORT.md"
    report_file.write_text(report, encoding="utf-8")

    print("\n📊 批量更新完成！")
    print(f"   📝 添加版本头部: {len(updated_files)} 个文件")
    print(f"   🔧 修复代码块: {len(fixed_files)} 个文件")
    print(f"   📄 报告已保存到: {report_file}")

    print("\n💡 建议运行以下命令验证更新效果:")
    print("   python scripts/check_doc_consistency.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
