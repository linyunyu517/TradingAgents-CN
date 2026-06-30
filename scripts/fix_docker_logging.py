#!/usr/bin/env python3
"""
修复Docker环境下的日志文件生成问题
"""

from pathlib import Path


def fix_docker_logging_config():
    """修复Docker日志配置"""
    print("🔧 修复Docker环境日志配置...")

    # 1. 修改 logging_docker.toml
    docker_config_file = Path("config/logging_docker.toml")
    if docker_config_file.exists():
        print(f"📝 修改 {docker_config_file}")

        # 读取现有配置
        with open(docker_config_file, encoding="utf-8") as f:
            content = f.read()

        # 修改配置：启用文件日志
        new_content = content.replace(
            "[logging.handlers.file]\nenabled = false",
            '[logging.handlers.file]\nenabled = true\nlevel = "DEBUG"\nmax_size = "100MB"\nbackup_count = 5\ndirectory = "/app/logs"',
        )

        new_content = new_content.replace("disable_file_logging = true", "disable_file_logging = false")

        new_content = new_content.replace("stdout_only = true", "stdout_only = false")

        # 写回文件
        with open(docker_config_file, "w", encoding="utf-8") as f:
            f.write(new_content)

        print("✅ Docker日志配置已修复")
    else:
        print("⚠️ Docker日志配置文件不存在，创建新的...")
        create_docker_logging_config()


def create_docker_logging_config():
    """创建新的Docker日志配置"""
    docker_config_content = """# Docker环境专用日志配置 - 修复版
# 同时支持控制台输出和文件日志

[logging]
level = "INFO"

[logging.format]
console = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
file = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s"
structured = "json"

[logging.handlers]

# 控制台输出
[logging.handlers.console]
enabled = true
colored = false
level = "INFO"

# 文件输出 - 启用！
[logging.handlers.file]
enabled = true
level = "DEBUG"
max_size = "100MB"
backup_count = 5
directory = "/app/logs"

# 结构化日志
[logging.handlers.structured]
enabled = true
level = "INFO"
directory = "/app/logs"

[logging.loggers]
[logging.loggers.tradingagents]
level = "INFO"

[logging.loggers.web]
level = "INFO"

[logging.loggers.streamlit]
level = "WARNING"

[logging.loggers.urllib3]
level = "WARNING"

[logging.loggers.requests]
level = "WARNING"

# Docker配置 - 修复版
[logging.docker]
enabled = true
stdout_only = false  # 不只输出到stdout
disable_file_logging = false  # 不禁用文件日志

[logging.performance]
enabled = true
log_slow_operations = true
slow_threshold_seconds = 10.0

[logging.security]
enabled = true
log_api_calls = true
log_token_usage = true
mask_sensitive_data = true

[logging.business]
enabled = true
log_analysis_events = true
log_user_actions = true
log_export_events = true
"""

    # 确保config目录存在
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    # 写入配置文件
    docker_config_file = config_dir / "logging_docker.toml"
    with open(docker_config_file, "w", encoding="utf-8") as f:
        f.write(docker_config_content)

    print(f"✅ 创建新的Docker日志配置: {docker_config_file}")


def update_docker_compose():
    """更新docker-compose.yml环境变量"""
    print("\n🐳 检查docker-compose.yml配置...")

    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        print("❌ docker-compose.yml文件不存在")
        return

    with open(compose_file, encoding="utf-8") as f:
        content = f.read()

    # 检查是否已有正确的环境变量
    required_vars = ['TRADINGAGENTS_LOG_DIR: "/app/logs"', 'TRADINGAGENTS_LOG_FILE: "/app/logs/tradingagents.log"']

    missing_vars = []
    for var in required_vars:
        if var not in content:
            missing_vars.append(var)

    if missing_vars:
        print(f"⚠️ 缺少环境变量: {missing_vars}")
        print("💡 请确保docker-compose.yml包含以下环境变量:")
        for var in required_vars:
            print(f"   {var}")
    else:
        print("✅ docker-compose.yml环境变量配置正确")


def create_test_script():
    """创建测试脚本"""
    print("\n📝 创建日志测试脚本...")

    test_script_content = '''#!/usr/bin/env python3
"""
测试Docker环境下的日志功能
"""

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_logging():
    """测试日志功能"""
    print("🧪 测试Docker环境日志功能")
    print("=" * 50)

    try:
        # 设置Docker环境变量
        os.environ['DOCKER_CONTAINER'] = 'true'
        os.environ['TRADINGAGENTS_LOG_DIR'] = '/app/logs'

        # 导入日志模块
        from tradingagents.utils.logging_init import init_logging, get_logger

        # 初始化日志
        print("📋 初始化日志系统...")
        init_logging()

        # 获取日志器
        logger = get_logger('test')

        # 测试各种级别的日志
        print("📝 写入测试日志...")
        logger.debug("🔍 这是DEBUG级别日志")
        logger.info("ℹ️ 这是INFO级别日志")
        logger.warning("⚠️ 这是WARNING级别日志")
        logger.error("❌ 这是ERROR级别日志")

        # 检查日志文件
        log_dir = Path("/app/logs")
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log*"))
            print(f"📄 找到日志文件: {len(log_files)} 个")
            for log_file in log_files:
                size = log_file.stat().st_size
                print(f"   📄 {log_file.name}: {size} 字节")
        else:
            print("❌ 日志目录不存在")

        print("✅ 日志测试完成")
        return True

    except Exception as e:
        print(f"❌ 日志测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_logging()
    sys.exit(0 if success else 1)
'''

    test_file = Path("test_docker_logging.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_script_content)

    print(f"✅ 创建测试脚本: {test_file}")


def main():
    """主函数"""
    print("🚀 TradingAgents Docker日志修复工具")
    print("=" * 60)

    # 1. 修复Docker日志配置
    fix_docker_logging_config()

    # 2. 检查docker-compose配置
    update_docker_compose()

    # 3. 创建测试脚本
    create_test_script()

    print("\n" + "=" * 60)
    print("🎉 Docker日志修复完成！")
    print("\n💡 接下来的步骤:")
    print("1. 重新构建Docker镜像: docker-compose build")
    print("2. 重启容器: docker-compose down && docker-compose up -d")
    print("3. 测试日志: docker exec TradingAgents-web python test_docker_logging.py")
    print("4. 检查日志文件: ls -la logs/")
    print("5. 实时查看: tail -f logs/tradingagents.log")

    print("\n🔧 如果仍然没有日志文件，请检查:")
    print("- 容器是否正常启动: docker-compose ps")
    print("- 应用是否正常运行: docker-compose logs web")
    print("- 日志目录权限: ls -la logs/")


if __name__ == "__main__":
    main()
