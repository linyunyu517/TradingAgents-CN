#!/usr/bin/env python3
"""
确保logs目录存在的脚本
在启动Docker容器前运行，创建必要的logs目录
"""

import os
import sys
from pathlib import Path


def ensure_logs_directory():
    """确保logs目录存在"""
    # 获取项目根目录
    project_root = Path(__file__).parent
    logs_dir = project_root / "logs"

    print("🚀 TradingAgents 日志目录检查")
    print("=" * 40)
    print(f"📁 项目根目录: {project_root}")
    print(f"📁 日志目录: {logs_dir}")

    # 创建logs目录
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True, exist_ok=True)
        print("✅ 创建logs目录")
    else:
        print("📁 logs目录已存在")

    # 设置目录权限（Linux/macOS）
    if os.name != "nt":  # 不是Windows
        try:
            os.chmod(logs_dir, 0o755)
            print("✅ 设置目录权限: 755")
        except Exception as e:
            print(f"⚠️ 设置权限失败: {e}")

    # 创建.gitkeep文件
    gitkeep_file = logs_dir / ".gitkeep"
    if not gitkeep_file.exists():
        gitkeep_file.touch()
        print("✅ 创建.gitkeep文件")

    # 创建README文件
    readme_file = logs_dir / "README.md"
    if not readme_file.exists():
        readme_content = """# TradingAgents 日志目录

此目录用于存储 TradingAgents 应用的日志文件。

## 日志文件说明

- `tradingagents.log` - 主应用日志文件
- `tradingagents_error.log` - 错误日志文件（如果有错误）
- `*.log.*` - 轮转的历史日志文件

## Docker映射

在Docker环境中，此目录映射到容器内的 `/app/logs` 目录。
容器内生成的所有日志文件都会出现在这里。

## 获取日志

如果遇到问题需要发送日志给开发者，请发送：
1. `tradingagents.log` - 主日志文件
2. `tradingagents_error.log` - 错误日志文件（如果存在）

## 实时查看日志

```bash
# Linux/macOS
tail -f logs/tradingagents.log

# Windows PowerShell
Get-Content logs/tradingagents.log -Wait
```
"""
        readme_file.write_text(readme_content, encoding="utf-8")
        print("✅ 创建README.md文件")

    # 检查现有日志文件
    log_files = list(logs_dir.glob("*.log*"))
    if log_files:
        print(f"\n📋 现有日志文件 ({len(log_files)} 个):")
        for log_file in sorted(log_files):
            size = log_file.stat().st_size
            print(f"   📄 {log_file.name} ({size:,} 字节)")
    else:
        print("\n📋 暂无日志文件")

    print("\n🎉 日志目录准备完成！")
    print(f"📁 日志将保存到: {logs_dir.absolute()}")

    return True


def main():
    """主函数"""
    try:
        ensure_logs_directory()
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
