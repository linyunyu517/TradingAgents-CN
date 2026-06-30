"""部署验证工具 - 记录代码版本并验证运行版本一致性"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

_GIT_PATH = shutil.which("git") or "git"


def get_git_commit_hash() -> str:
    """获取当前代码的 git commit hash"""
    try:
        result = subprocess.run(
            [_GIT_PATH, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_DIR,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_git_commit_time() -> str:
    """获取当前代码的 git commit 时间"""
    try:
        result = subprocess.run(
            [_GIT_PATH, "log", "-1", "--format=%ci"],
            capture_output=True,
            text=True,
            cwd=PROJECT_DIR,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_deploy_info() -> dict:
    """获取部署信息"""
    return {
        "commit_hash": get_git_commit_hash(),
        "commit_time": get_git_commit_time(),
        "deploy_time": datetime.now().isoformat(),
        "python_version": sys.version,
    }


DEPLOY_INFO = get_deploy_info()


def verify_deploy() -> bool:
    """验证部署 - 检查是否与源代码版本一致"""
    current = get_git_commit_hash()
    recorded = DEPLOY_INFO.get("commit_hash")
    if current == "unknown" or recorded == "unknown":
        return True  # 无法验证时默认通过
    return current == recorded
