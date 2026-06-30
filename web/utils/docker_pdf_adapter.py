#!/usr/bin/env python3
"""
Docker环境PDF导出适配器
处理Docker容器中的PDF生成特殊需求
"""

import os
import subprocess
import tempfile

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("web")


def is_docker_environment() -> bool:
    """检测是否在Docker环境中运行"""
    try:
        # 检查/.dockerenv文件
        if os.path.exists("/.dockerenv"):
            return True

        # 检查cgroup信息
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if "docker" in content or "containerd" in content:
                return True
    except Exception:
        pass  # 无法检测 Docker，继续使用 env var 判断

    # 检查环境变量
    return os.environ.get("DOCKER_CONTAINER", "").lower() == "true"


def setup_xvfb_display():
    """设置虚拟显示器 (Docker环境需要)"""
    if not is_docker_environment():
        return True

    try:
        # 检查Xvfb是否已经在运行
        try:
            result = subprocess.run(["pgrep", "Xvfb"], capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("✅ Xvfb已在运行")
                os.environ["DISPLAY"] = ":99"
                return True
        except Exception:
            logger.debug("检查 Xvfb 是否在运行失败")

        # 启动Xvfb虚拟显示器 (后台运行)
        subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1024x768x24", "-ac", "+extension", "GLX"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 等待一下让Xvfb启动
        import time

        time.sleep(2)

        # 设置DISPLAY环境变量
        os.environ["DISPLAY"] = ":99"
        logger.info("✅ Docker虚拟显示器设置成功")
        return True
    except Exception as e:
        logger.error(f"⚠️ 虚拟显示器设置失败: {e}")
        # 即使Xvfb失败，也尝试继续，某些情况下wkhtmltopdf可以无头运行
        return False


def get_docker_wkhtmltopdf_args():
    """获取Docker环境下wkhtmltopdf的特殊参数"""
    if not is_docker_environment():
        return []

    # 这些是wkhtmltopdf的参数，不是pandoc的参数
    return ["--disable-smart-shrinking", "--print-media-type", "--no-background", "--disable-javascript", "--quiet"]


def test_docker_pdf_generation() -> bool:
    """测试Docker环境下的PDF生成"""
    if not is_docker_environment():
        return True

    try:
        import pypandoc

        # 设置虚拟显示器
        setup_xvfb_display()

        # 测试内容
        test_html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Docker PDF Test</title>
        </head>
        <body>
            <h1>Docker PDF 测试</h1>
            <p>这是在Docker环境中生成的PDF测试文档。</p>
            <p>中文字符测试：你好世界！</p>
        </body>
        </html>
        """

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_file = tmp.name

        # Docker环境下使用简化的参数
        extra_args = [
            "--pdf-engine=wkhtmltopdf",
            "--pdf-engine-opt=--disable-smart-shrinking",
            "--pdf-engine-opt=--quiet",
        ]

        pypandoc.convert_text(test_html, "pdf", format="html", outputfile=output_file, extra_args=extra_args)

        # 检查文件是否生成
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            os.unlink(output_file)  # 清理测试文件
            logger.info("✅ Docker PDF生成测试成功")
            return True
        logger.error("❌ Docker PDF生成测试失败")
        return False

    except Exception as e:
        logger.error(f"❌ Docker PDF测试失败: {e}")
        return False


def get_docker_pdf_extra_args():
    """获取Docker环境下PDF生成的额外参数"""
    base_args = ["--toc", "--number-sections", "-V", "geometry:margin=2cm", "-V", "documentclass=article"]

    if is_docker_environment():
        # Docker环境下的特殊配置 - 使用正确的pandoc参数格式
        docker_args = []
        wkhtmltopdf_args = get_docker_wkhtmltopdf_args()

        # 将wkhtmltopdf参数正确传递给pandoc
        for arg in wkhtmltopdf_args:
            docker_args.extend(["--pdf-engine-opt=" + arg])

        return base_args + docker_args

    return base_args


def check_docker_pdf_dependencies():
    """检查Docker环境下PDF生成的依赖"""
    if not is_docker_environment():
        return True, "非Docker环境"

    missing_deps = []

    # 检查wkhtmltopdf
    try:
        result = subprocess.run(["wkhtmltopdf", "--version"], capture_output=True, timeout=10)
        if result.returncode != 0:
            missing_deps.append("wkhtmltopdf")
    except Exception:
        missing_deps.append("wkhtmltopdf")

    # 检查Xvfb
    try:
        result = subprocess.run(["Xvfb", "-help"], capture_output=True, timeout=10)
        if result.returncode not in [0, 1]:  # Xvfb -help 返回1是正常的
            missing_deps.append("xvfb")
    except Exception:
        missing_deps.append("xvfb")

    # 检查字体
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/liberation/",
    ]

    font_found = any(os.path.exists(path) for path in font_paths)
    if not font_found:
        missing_deps.append("chinese-fonts")

    if missing_deps:
        return False, f"缺少依赖: {', '.join(missing_deps)}"

    return True, "所有依赖已安装"


def get_docker_status_info():
    """获取Docker环境状态信息"""
    info = {
        "is_docker": is_docker_environment(),
        "dependencies_ok": False,
        "dependency_message": "",
        "pdf_test_ok": False,
    }

    if info["is_docker"]:
        info["dependencies_ok"], info["dependency_message"] = check_docker_pdf_dependencies()
        if info["dependencies_ok"]:
            info["pdf_test_ok"] = test_docker_pdf_generation()
    else:
        info["dependencies_ok"] = True
        info["dependency_message"] = "非Docker环境，使用标准配置"
        info["pdf_test_ok"] = True

    return info


if __name__ == "__main__":
    logger.info("🐳 Docker PDF适配器测试")
    logger.info("=")

    status = get_docker_status_info()

    logger.info(f"Docker环境: {'是' if status['is_docker'] else '否'}")
    logger.error(f"依赖检查: {'✅' if status['dependencies_ok'] else '❌'} {status['dependency_message']}")
    logger.error(f"PDF测试: {'✅' if status['pdf_test_ok'] else '❌'}")

    if status["is_docker"] and status["dependencies_ok"] and status["pdf_test_ok"]:
        logger.info("\n🎉 Docker PDF功能完全正常！")
    elif status["is_docker"] and not status["dependencies_ok"]:
        logger.warning("\n⚠️ Docker环境缺少PDF依赖，请重新构建镜像")
    elif status["is_docker"] and not status["pdf_test_ok"]:
        logger.error("\n⚠️ Docker PDF测试失败，可能需要调整配置")
    else:
        logger.info("\n✅ 非Docker环境，使用标准PDF配置")
