#!/usr/bin/env python3
"""
TradingAgents-CN 后端直接启动脚本
控制日志级别，减少不必要的文件监控日志
"""

import logging
import os
import sys

import uvicorn

# 添加app目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


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


def setup_logging():
    """设置日志配置"""
    # 设置watchfiles日志级别为WARNING，减少文件变化日志
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    # 设置uvicorn日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # 确保webapi日志正常显示
    logging.getLogger("webapi").setLevel(logging.INFO)

    # 设置根日志级别
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """主函数"""
    print("🚀 启动 TradingAgents-CN 后端服务...")

    # 设置日志
    setup_logging()

    # 🔥 [BUG-045 扩散修复] 启动前检查端口可用性，自动释放被占用的端口
    _release_port("0.0.0.0", 8000)

    # 启动uvicorn服务器
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        log_level="info",
        access_log=True,
        # 减少文件监控的敏感度
        reload_delay=0.5,
        # 忽略某些文件类型的变化
        reload_excludes=["*.pyc", "*.pyo", "__pycache__", ".git", "*.log"],
    )


if __name__ == "__main__":
    main()
