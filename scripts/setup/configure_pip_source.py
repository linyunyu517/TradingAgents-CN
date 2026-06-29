#!/usr/bin/env python3
"""
配置pip源为国内镜像
提高包安装速度
"""

import sys
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


def configure_pip_source():
    """配置pip源"""
    logger.info("🔧 配置pip源为国内镜像")
    logger.info("=")

    # 获取pip配置目录
    if sys.platform == "win32":
        # Windows
        pip_config_dir = Path.home() / "pip"
        config_file = pip_config_dir / "pip.ini"
    else:
        # Linux/macOS
        pip_config_dir = Path.home() / ".pip"
        config_file = pip_config_dir / "pip.conf"

    logger.info(f"📁 pip配置目录: {pip_config_dir}")
    logger.info(f"📄 配置文件: {config_file}")

    # 创建配置目录
    pip_config_dir.mkdir(exist_ok=True)
    logger.info("✅ 配置目录已创建")

    # 可选的镜像源
    mirrors = {
        "清华大学": {"url": "https://pypi.tuna.tsinghua.edu.cn/simple/", "trusted_host": "pypi.tuna.tsinghua.edu.cn"},
        "阿里云": {"url": "https://mirrors.aliyun.com/pypi/simple/", "trusted_host": "mirrors.aliyun.com"},
        "中科大": {"url": "https://pypi.mirrors.ustc.edu.cn/simple/", "trusted_host": "pypi.mirrors.ustc.edu.cn"},
        "豆瓣": {"url": "https://pypi.douban.com/simple/", "trusted_host": "pypi.douban.com"},
        "华为云": {
            "url": "https://mirrors.huaweicloud.com/repository/pypi/simple/",
            "trusted_host": "mirrors.huaweicloud.com",
        },
    }

    logger.info("\n📋 可用的镜像源:")
    for i, (name, info) in enumerate(mirrors.items(), 1):
        logger.info(f"  {i}. {name}: {info['url']}")

    # 默认选择清华大学镜像（通常最快最稳定）
    selected_mirror = mirrors["清华大学"]
    logger.info("\n✅ 自动选择: 清华大学镜像")
    logger.info(f"   URL: {selected_mirror['url']}")

    # 生成配置内容
    if sys.platform == "win32":
        # Windows pip.ini格式
        config_content = f"""[global]
index-url = {selected_mirror["url"]}
trusted-host = {selected_mirror["trusted_host"]}
timeout = 120

[install]
trusted-host = {selected_mirror["trusted_host"]}
"""
    else:
        # Linux/macOS pip.conf格式
        config_content = f"""[global]
index-url = {selected_mirror["url"]}
trusted-host = {selected_mirror["trusted_host"]}
timeout = 120

[install]
trusted-host = {selected_mirror["trusted_host"]}
"""

    # 写入配置文件
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info(f"✅ pip配置已保存到: {config_file}")
    except Exception as e:
        logger.error(f"❌ 配置保存失败: {e}")
        return False

    # 测试配置
    logger.info("\n🧪 测试pip配置...")
    try:
        import subprocess

        # 测试pip源
        result = subprocess.run(
            [sys.executable, "-m", "pip", "config", "list"], capture_output=True, text=True, timeout=10,
        )

        if result.returncode == 0:
            logger.info("✅ pip配置测试成功")
            logger.info("📊 当前配置:")
            for line in result.stdout.split("\n"):
                if line.strip():
                    logger.info(f"  {line}")
        else:
            logger.error(f"⚠️ pip配置测试失败: {result.stderr}")

    except Exception as e:
        logger.warning(f"⚠️ 无法测试pip配置: {e}")

    # 生成使用说明
    logger.info("\n📋 使用说明:")
    logger.info("1. 配置已永久生效，以后安装包会自动使用国内镜像")
    logger.info("2. 如需临时使用其他源，可以使用:")
    logger.info("   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ package_name")
    logger.info("3. 如需恢复默认源，删除配置文件:")
    logger.info(f"   del {config_file}")

    return True


def install_database_packages():
    """安装数据库相关包"""
    logger.info("\n📦 安装数据库相关包...")

    packages = ["pymongo", "redis"]

    for package in packages:
        logger.info(f"\n📥 安装 {package}...")
        try:
            import subprocess

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package], capture_output=True, text=True, timeout=120,
            )

            if result.returncode == 0:
                logger.info(f"✅ {package} 安装成功")
            else:
                logger.error(f"❌ {package} 安装失败:")
                print(result.stderr)

        except subprocess.TimeoutExpired:
            logger.info(f"⏰ {package} 安装超时")
        except Exception as e:
            logger.error(f"❌ {package} 安装异常: {e}")


def create_pip_upgrade_script():
    """创建pip升级脚本"""
    logger.info("\n📝 创建pip管理脚本...")

    project_root = Path(__file__).parent.parent.parent
    script_content = """@echo off
REM pip管理脚本 - 使用国内镜像

echo 🔧 pip管理工具
echo ================

echo.
echo 1. 升级pip
python -m pip install --upgrade pip

echo.
echo 2. 安装常用包
python -m pip install pymongo redis pandas requests

echo.
echo 3. 显示已安装包
python -m pip list

echo.
echo 4. 检查pip配置
python -m pip config list

echo.
echo ✅ 完成!
pause
"""

    script_file = project_root / "scripts" / "setup" / "pip_manager.bat"
    try:
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script_content)
        logger.info(f"✅ pip管理脚本已创建: {script_file}")
    except Exception as e:
        logger.error(f"⚠️ 脚本创建失败: {e}")


def main():
    """主函数"""
    try:
        # 配置pip源
        success = configure_pip_source()

        if success:
            # 安装数据库包
            install_database_packages()

            # 创建管理脚本
            create_pip_upgrade_script()

            logger.info("\n🎉 pip源配置完成!")
            logger.info("\n💡 建议:")
            logger.info("1. 重新运行系统初始化: python scripts/setup/initialize_system.py")
            logger.info("2. 检查系统状态: python scripts/validation/check_system_status.py")
            logger.info("3. 使用pip管理脚本: scripts/setup/pip_manager.bat")

        return success

    except Exception as e:
        logger.error(f"❌ 配置失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
