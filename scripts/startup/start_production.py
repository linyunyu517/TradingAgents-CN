#!/usr/bin/env python3
"""
TradingAgents-CN Backend Production Launcher
生产环境启动脚本
"""

import os
import sys
from pathlib import Path

import uvicorn

# BUG-158: 修正 project_root 指向项目根目录（而非 scripts/startup/ 子目录）
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings


def _release_port(host: str, port: int) -> None:
    """释放被占用的端口（如果被占用则自动 kill 占用进程）

    🔥 [BUG-045 扩散修复] 在 uvicorn.run() 前检查并释放端口，
    避免 [Errno 10048] 启动失败
    """
    import re
    import socket
    import subprocess
    import time

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((host, port))
    sock.close()

    if result == 0:
        print(f"⚠️ 端口 {port} 已被占用，尝试自动释放...")
        try:
            netstat_out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, timeout=5)
            pid_match = re.search(r"LISTENING\s+(\d+)", netstat_out)
            if pid_match:
                pid = pid_match.group(1)
                print(f"  发现占用进程 PID={pid}，正在终止...")
                subprocess.check_output(f"taskkill /F /PID {pid}", shell=True, text=True, timeout=5)
                time.sleep(1)
                print(f"✅ 端口 {port} 已成功释放")
        except subprocess.TimeoutExpired:
            print("  自动释放超时")
        except Exception as e:
            print(f"  自动释放异常: {e}")


def main():
    """生产环境启动函数"""
    print("🚀 Starting TradingAgents-CN Backend (Production Mode)")
    print(f"📍 Host: {settings.HOST}")
    print(f"🔌 Port: {settings.PORT}")
    print("🔒 Production Mode: Enabled")
    print("-" * 50)

    # 🔥 [BUG-045 扩散修复] 启动前检查端口可用性，自动释放被占用的端口
    _release_port(settings.HOST, settings.PORT)

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=False,
            log_level="warning",
            access_log=False,
            workers=4,  # 多进程
            loop="uvloop",  # 高性能事件循环
            http="httptools",  # 高性能HTTP解析器
            # 生产环境优化
            backlog=2048,
            limit_concurrency=1000,
            limit_max_requests=10000,
            timeout_keep_alive=5,
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 设置生产环境变量
    os.environ["DEBUG"] = "False"
    main()
