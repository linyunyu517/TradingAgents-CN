#!/usr/bin/env python3
"""
TradingAgents-CN Backend Launcher
快速启动脚本
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    """启动后端服务"""
    print("🚀 TradingAgents-CN Backend Launcher")
    print("=" * 50)

    # BUG-157: 修正 project_root 指向项目根目录（而非 scripts/startup/ 子目录）
    project_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(project_root)

    # 检查Python版本

    # 检查app目录是否存在
    if not (project_root / "app").exists():
        print(f"❌ app directory not found at {project_root / 'app'}")
        sys.exit(1)

    print("✅ Environment check passed")
    print("🔄 Starting backend server...")
    print("-" * 50)

    try:
        # 使用 python -m app 启动
        subprocess.run([sys.executable, "-m", "app"], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
