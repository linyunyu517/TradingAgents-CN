#!/usr/bin/env python3
"""
Pandoc安装脚本
自动安装pandoc工具，用于报告导出功能
"""

import platform
import subprocess
import sys

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


def check_pandoc():
    """检查pandoc是否已安装"""
    try:
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.split("\n")[0]
            logger.info(f"✅ Pandoc已安装: {version}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass

    logger.error("❌ Pandoc未安装")
    return False


def install_pandoc_python():
    """使用pypandoc下载pandoc"""
    try:
        import pypandoc

        logger.info("🔄 正在使用pypandoc下载pandoc...")
        pypandoc.download_pandoc()
        logger.info("✅ Pandoc下载成功！")
        return True
    except ImportError:
        logger.error("❌ pypandoc未安装，请先运行: pip install pypandoc")
        return False
    except Exception as e:
        logger.error(f"❌ Pandoc下载失败: {e}")
        return False


def install_pandoc_system():
    """使用系统包管理器安装pandoc"""
    system = platform.system().lower()

    if system == "windows":
        return install_pandoc_windows()
    if system == "darwin":  # macOS
        return install_pandoc_macos()
    if system == "linux":
        return install_pandoc_linux()
    logger.error(f"❌ 不支持的操作系统: {system}")
    return False


def install_pandoc_windows():
    """在Windows上安装pandoc"""
    logger.info("🔄 尝试在Windows上安装pandoc...")

    # 尝试使用Chocolatey
    try:
        result = subprocess.run(["choco", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("🔄 使用Chocolatey安装pandoc...")
            result = subprocess.run(["choco", "install", "pandoc", "-y"], capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("✅ Pandoc安装成功！")
                return True
            logger.error(f"❌ Chocolatey安装失败: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("⚠️ Chocolatey未安装")

    # 尝试使用winget
    try:
        result = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("🔄 使用winget安装pandoc...")
            result = subprocess.run(
                ["winget", "install", "JohnMacFarlane.Pandoc"], capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info("✅ Pandoc安装成功！")
                return True
            logger.error(f"❌ winget安装失败: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("⚠️ winget未安装")

    logger.error("❌ 系统包管理器安装失败")
    return False


def install_pandoc_macos():
    """在macOS上安装pandoc"""
    logger.info("🔄 尝试在macOS上安装pandoc...")

    # 尝试使用Homebrew
    try:
        result = subprocess.run(["brew", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("🔄 使用Homebrew安装pandoc...")
            result = subprocess.run(["brew", "install", "pandoc"], capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("✅ Pandoc安装成功！")
                return True
            logger.error(f"❌ Homebrew安装失败: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("⚠️ Homebrew未安装")

    logger.error("❌ 系统包管理器安装失败")
    return False


def install_pandoc_linux():
    """在Linux上安装pandoc"""
    logger.info("🔄 尝试在Linux上安装pandoc...")

    # 尝试使用apt (Ubuntu/Debian)
    try:
        result = subprocess.run(["apt", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("🔄 使用apt安装pandoc...")
            result = subprocess.run(["sudo", "apt-get", "update"], capture_output=True, text=True, timeout=120)
            result = subprocess.run(
                ["sudo", "apt-get", "install", "-y", "pandoc"], capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info("✅ Pandoc安装成功！")
                return True
            logger.error(f"❌ apt安装失败: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 尝试使用yum (CentOS/RHEL)
    try:
        result = subprocess.run(["yum", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("🔄 使用yum安装pandoc...")
            result = subprocess.run(
                ["sudo", "yum", "install", "-y", "pandoc"], capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info("✅ Pandoc安装成功！")
                return True
            logger.error(f"❌ yum安装失败: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    logger.error("❌ 系统包管理器安装失败")
    return False


def main():
    """主函数"""
    logger.info("🔧 Pandoc安装脚本")
    logger.info("=")

    # 检查是否已安装
    if check_pandoc():
        logger.info("✅ Pandoc已可用，无需安装")
        return True

    logger.info("\n🔄 开始安装pandoc...")

    # 方法1: 使用pypandoc下载
    logger.info("\n📦 方法1: 使用pypandoc下载")
    if install_pandoc_python() and check_pandoc():
        return True

    # 方法2: 使用系统包管理器
    logger.info("\n🖥️ 方法2: 使用系统包管理器")
    if install_pandoc_system() and check_pandoc():
        return True

    # 安装失败
    logger.error("\n❌ 所有安装方法都失败了")
    logger.info("\n📖 手动安装指南:")
    logger.info("1. 访问 https://github.com/jgm/pandoc/releases")
    logger.info("2. 下载适合您系统的安装包")
    logger.info("3. 按照官方文档安装")
    logger.info("4. 确保pandoc在系统PATH中")

    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
