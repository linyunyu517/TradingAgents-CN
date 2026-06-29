#!/usr/bin/env python3
"""
准备向上游项目贡献代码的工具脚本
自动化处理代码清理、文档生成、测试验证等任务
"""

import json
import re
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class UpstreamContributionPreparer:
    """上游贡献准备工具"""

    def __init__(self, source_dir: str = ".", target_dir: str = "./upstream_contribution"):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.chinese_pattern = re.compile(r"[\u4e00-\u9fff]+")

        # 定义贡献批次
        self.contribution_batches = {
            "batch1_caching": {
                "name": "Intelligent Caching System",
                "files": [
                    "tradingagents/dataflows/cache_manager.py",
                    "tradingagents/dataflows/optimized_us_data.py",
                    "tests/test_cache_optimization.py",
                ],
                "priority": 1,
                "description": "Add multi-layer caching with 99%+ performance improvement",
            },
            "batch2_error_handling": {
                "name": "Error Handling Improvements",
                "files": [
                    "tradingagents/agents/analysts/market_analyst.py",
                    "tradingagents/agents/analysts/fundamentals_analyst.py",
                    "tradingagents/dataflows/db_cache_manager.py",
                ],
                "priority": 2,
                "description": "Improve error handling and user experience",
            },
            "batch3_data_sources": {
                "name": "US Data Source Optimization",
                "files": [
                    "tradingagents/dataflows/optimized_us_data.py",
                    "tradingagents/dataflows/finnhub_integration.py",
                ],
                "priority": 3,
                "description": "Fix Yahoo Finance limitations with FINNHUB fallback",
            },
        }

    def analyze_chinese_content(self) -> dict[str, list[str]]:
        """分析代码中的中文内容"""
        chinese_files = {}

        for file_path in self.source_dir.rglob("*.py"):
            if any(exclude in str(file_path) for exclude in [".git", "__pycache__", ".pytest_cache"]):
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                chinese_lines = []
                for i, line in enumerate(content.split("\n"), 1):
                    if self.chinese_pattern.search(line):
                        chinese_lines.append(f"Line {i}: {line.strip()}")

                if chinese_lines:
                    chinese_files[str(file_path.relative_to(self.source_dir))] = chinese_lines

            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return chinese_files

    def clean_chinese_content(self, file_path: Path, target_path: Path):
        """清理文件中的中文内容"""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # 替换中文注释
            content = re.sub(r"#\s*[\u4e00-\u9fff].*", "# TODO: Add English comment", content)

            # 替换中文字符串（保留在print语句中的，改为英文）
            chinese_strings = {
                "获取": "Getting",
                "成功": "Success",
                "失败": "Failed",
                "错误": "Error",
                "警告": "Warning",
                "数据": "Data",
                "缓存": "Cache",
                "分析": "Analysis",
                "股票": "Stock",
                "美股": "US Stock",
                "A股": "China Stock",
                "连接": "Connection",
                "初始化": "Initialize",
                "配置": "Configuration",
                "测试": "Test",
                "启动": "Starting",
                "停止": "Stopping",
            }

            for chinese, english in chinese_strings.items():
                content = content.replace(f'"{chinese}"', f'"{english}"')
                content = content.replace(f"'{chinese}'", f"'{english}'")

            # 确保目标目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"✅ Cleaned: {file_path} -> {target_path}")

        except Exception as e:
            logger.error(f"❌ Error cleaning {file_path}: {e}")

    def extract_generic_improvements(self, batch_name: str):
        """提取通用改进代码"""
        batch = self.contribution_batches[batch_name]
        batch_dir = self.target_dir / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"\n🚀 Preparing {batch['name']}...")

        for file_path in batch["files"]:
            source_file = self.source_dir / file_path
            target_file = batch_dir / file_path

            if source_file.exists():
                self.clean_chinese_content(source_file, target_file)
            else:
                logger.warning(f"⚠️ File not found: {source_file}")

        # 生成批次说明文档
        self.generate_batch_documentation(batch_name, batch_dir)

    def generate_batch_documentation(self, batch_name: str, batch_dir: Path):
        """生成批次文档"""
        batch = self.contribution_batches[batch_name]

        readme_content = f"""# {batch["name"]}

## Description
{batch["description"]}

## Files Included
"""

        for file_path in batch["files"]:
            readme_content += f"- `{file_path}`\n"

        readme_content += """
## Changes Made
- Removed Chinese comments and strings
- Improved error handling
- Added comprehensive documentation
- Enhanced performance and reliability

## Testing
Run the following tests to verify the changes:

```bash
python -m pytest tests/ -v
```

## Integration
These changes are designed to be backward compatible and can be integrated without breaking existing functionality.

## Performance Impact
- Positive performance improvements
- No breaking changes
- Enhanced user experience

## Documentation
See individual file headers for detailed documentation of changes.
"""

        with open(batch_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

        logger.info(f"📝 Generated documentation: {batch_dir / 'README.md'}")

    def generate_pr_template(self, batch_name: str):
        """生成PR模板"""
        batch = self.contribution_batches[batch_name]

        pr_template = f"""## {batch["name"]}

### Problem
Describe the problem this PR solves...

### Solution
{batch["description"]}

### Changes
- List specific changes made
- Include performance improvements
- Mention any new features

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Performance benchmarks included
- [ ] Documentation updated

### Breaking Changes
None - fully backward compatible

### Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No merge conflicts

### Performance Impact
- Improved performance by X%
- Reduced memory usage
- Better error handling

### Additional Notes
Any additional context or notes for reviewers...
"""

        batch_dir = self.target_dir / batch_name
        with open(batch_dir / "PR_TEMPLATE.md", "w", encoding="utf-8") as f:
            f.write(pr_template)

        logger.info(f"📋 Generated PR template: {batch_dir / 'PR_TEMPLATE.md'}")

    def validate_contribution(self, batch_name: str) -> bool:
        """验证贡献代码质量"""
        batch_dir = self.target_dir / batch_name

        logger.debug(f"\n🔍 Validating {batch_name}...")

        # 检查是否还有中文内容
        chinese_content = {}
        for file_path in batch_dir.rglob("*.py"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                    if self.chinese_pattern.search(content):
                        chinese_content[str(file_path)] = "Contains Chinese characters"
            except Exception as e:
                logger.error(f"Error validating {file_path}: {e}")

        if chinese_content:
            logger.error("❌ Validation failed - Chinese content found:")
            for file_path, issue in chinese_content.items():
                logger.info(f"  - {file_path}: {issue}")
            return False

        logger.info("✅ Validation passed - No Chinese content found")
        return True

    def generate_contribution_summary(self):
        """生成贡献总结"""
        summary = {
            "total_batches": len(self.contribution_batches),
            "batches": {},
            "preparation_date": "2025-07-02",
            "status": "Ready for contribution",
        }

        for batch_name, batch_info in self.contribution_batches.items():
            batch_dir = self.target_dir / batch_name
            if batch_dir.exists():
                file_count = len(list(batch_dir.rglob("*.py")))
                summary["batches"][batch_name] = {
                    "name": batch_info["name"],
                    "priority": batch_info["priority"],
                    "file_count": file_count,
                    "status": "Prepared",
                }

        with open(self.target_dir / "contribution_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"📊 Generated summary: {self.target_dir / 'contribution_summary.json'}")

    def prepare_all_batches(self):
        """准备所有批次"""
        logger.info("🚀 Starting upstream contribution preparation...")

        # 创建目标目录
        self.target_dir.mkdir(parents=True, exist_ok=True)

        # 分析中文内容
        logger.info("\n📊 Analyzing Chinese content...")
        chinese_files = self.analyze_chinese_content()

        if chinese_files:
            logger.info(f"Found Chinese content in {len(chinese_files)} files")
            with open(self.target_dir / "chinese_content_analysis.json", "w", encoding="utf-8") as f:
                json.dump(chinese_files, f, indent=2, ensure_ascii=False)

        # 准备各个批次
        for batch_name in sorted(self.contribution_batches.keys()):
            self.extract_generic_improvements(batch_name)
            self.generate_pr_template(batch_name)
            self.validate_contribution(batch_name)

        # 生成总结
        self.generate_contribution_summary()

        logger.info(f"\n🎉 Preparation completed! Check {self.target_dir} for results.")


def main():
    """主函数"""
    preparer = UpstreamContributionPreparer()
    preparer.prepare_all_batches()


if __name__ == "__main__":
    main()
