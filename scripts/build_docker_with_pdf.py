#!/usr/bin/env python3
"""
构建包含PDF支持的Docker镜像
"""

import subprocess
import sys
import time
from pathlib import Path

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


def run_command(command, description, timeout=300):
    """运行命令并显示进度"""
    logger.info(f"\n🔄 {description}...")
    logger.info(f"命令: {command}")

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)

        if result.returncode == 0:
            logger.info(f"✅ {description}成功")
            if result.stdout.strip():
                logger.info(f"输出: {result.stdout.strip()}")
            return True
        logger.error(f"❌ {description}失败")
        logger.error(f"错误: {result.stderr.strip()}")
        return False

    except subprocess.TimeoutExpired:
        logger.error(f"❌ {description}超时")
        return False
    except Exception as e:
        logger.error(f"❌ {description}异常: {e}")
        return False


def check_dockerfile():
    """检查Dockerfile是否包含PDF依赖"""
    logger.debug("🔍 检查Dockerfile配置...")

    dockerfile_path = Path("Dockerfile")
    if not dockerfile_path.exists():
        logger.error("❌ Dockerfile不存在")
        return False

    content = dockerfile_path.read_text()

    required_packages = ["wkhtmltopdf", "xvfb", "fonts-wqy-zenhei", "pandoc"]

    missing_packages = []
    for package in required_packages:
        if package not in content:
            missing_packages.append(package)

    if missing_packages:
        logger.warning(f"⚠️ Dockerfile缺少PDF依赖: {', '.join(missing_packages)}")
        logger.info("请确保Dockerfile包含以下包:")
        for package in required_packages:
            logger.info(f"  - {package}")
        return False

    logger.info("✅ Dockerfile包含所有PDF依赖")
    return True


def build_docker_image():
    """构建Docker镜像"""
    return run_command(
        "docker build -t tradingagents-cn:latest .",
        "构建Docker镜像",
        timeout=600,  # 10分钟超时
    )


def test_docker_container():
    """测试Docker容器"""
    logger.info("\n🧪 测试Docker容器...")

    # 启动容器进行测试
    start_cmd = """docker run -d --name tradingagents-test \
        -e DOCKER_CONTAINER=true \
        -e DISPLAY=:99 \
        tradingagents-cn:latest \
        python scripts/test_docker_pdf.py"""

    if not run_command(start_cmd, "启动测试容器", timeout=60):
        return False

    # 等待容器启动
    time.sleep(5)

    # 获取测试结果
    logs_cmd = "docker logs tradingagents-test"
    result = run_command(logs_cmd, "获取测试日志", timeout=30)

    # 清理测试容器
    cleanup_cmd = "docker rm -f tradingagents-test"
    run_command(cleanup_cmd, "清理测试容器", timeout=30)

    return result


def main():
    """主函数"""
    logger.info("🐳 构建包含PDF支持的Docker镜像")
    logger.info("=")

    # 检查当前目录
    if not Path("Dockerfile").exists():
        logger.error("❌ 请在项目根目录运行此脚本")
        return False

    steps = [
        ("检查Dockerfile配置", check_dockerfile),
        ("构建Docker镜像", build_docker_image),
        ("测试Docker容器", test_docker_container),
    ]

    for step_name, step_func in steps:
        logger.info(f"\n{'=' * 20} {step_name} {'=' * 20}")

        if not step_func():
            logger.error(f"\n❌ {step_name}失败，构建中止")
            return False

    logger.info("\n")
    logger.info("🎉 Docker镜像构建完成！")
    logger.info("=")

    logger.info("\n📋 使用说明:")
    logger.info("1. 启动完整服务:")
    logger.info("   docker-compose up -d")
    logger.info("\n2. 仅启动Web服务:")
    logger.info("   docker run -p 8501:8501 tradingagents-cn:latest")
    logger.info("\n3. 测试PDF功能:")
    logger.info("   docker run tradingagents-cn:latest python scripts/test_docker_pdf.py")

    logger.info("\n💡 提示:")
    logger.info("- PDF导出功能已在Docker环境中优化")
    logger.info("- 支持中文字体和虚拟显示器")
    logger.info("- 如遇问题请查看容器日志")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
