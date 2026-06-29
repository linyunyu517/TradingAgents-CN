#!/usr/bin/env python3
"""
验证Docker环境下的日志功能
"""

import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def check_container_status():
    """检查容器状态"""
    print("🐳 检查容器状态...")

    success, output, error = run_command("docker-compose ps")
    if success:
        print("✅ 容器状态:")
        print(output)

        # 检查web容器是否运行
        if "TradingAgents-web" in output and "Up" in output:
            return True
        print("❌ TradingAgents-web容器未正常运行")
        return False
    print(f"❌ 无法获取容器状态: {error}")
    return False


def trigger_logs_in_container():
    """在容器内触发日志生成"""
    print("\n📝 在容器内触发日志生成...")

    # 测试命令
    test_cmd = '''python -c "
import os
import sys
sys.path.insert(0, '/app')

# 设置环境变量
os.environ['DOCKER_CONTAINER'] = 'true'
os.environ['TRADINGAGENTS_LOG_DIR'] = '/app/logs'

try:
    from tradingagents.utils.logging_init import init_logging, get_logger

    print('🔧 初始化日志系统...')
    init_logging()

    print('📝 获取日志器...')
    logger = get_logger('docker_test')

    print('✍️ 写入测试日志...')
    logger.info('🧪 Docker环境日志测试 - INFO级别')
    logger.warning('⚠️ Docker环境日志测试 - WARNING级别')
    logger.error('❌ Docker环境日志测试 - ERROR级别')

    print('✅ 日志写入完成')

    # 检查日志文件
    import glob
    log_files = glob.glob('/app/logs/*.log*')
    print(f'📄 找到日志文件: {len(log_files)} 个')
    for log_file in log_files:
        size = os.path.getsize(log_file)
        print(f'   📄 {log_file}: {size} 字节')

except Exception as e:
    print(f'❌ 日志测试失败: {e}')
    import traceback
    traceback.print_exc()
"'''

    success, output, error = run_command(f"docker exec TradingAgents-web {test_cmd}")

    if success:
        print("✅ 容器内日志测试:")
        print(output)
        return True
    print("❌ 容器内日志测试失败:")
    print(f"错误: {error}")
    return False


def check_local_logs():
    """检查本地日志文件"""
    print("\n📁 检查本地日志文件...")

    logs_dir = Path("logs")
    if not logs_dir.exists():
        print("❌ logs目录不存在")
        return False

    log_files = list(logs_dir.glob("*.log*"))

    if not log_files:
        print("⚠️ 未找到日志文件")
        return False

    print(f"✅ 找到 {len(log_files)} 个日志文件:")

    for log_file in log_files:
        stat = log_file.stat()
        size = stat.st_size
        mtime = stat.st_mtime

        print(f"   📄 {log_file.name}")
        print(f"      大小: {size:,} 字节")
        print(f"      修改时间: {time.ctime(mtime)}")

        # 显示最后几行内容
        if size > 0:
            try:
                with open(log_file, encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        print("      最后3行:")
                        for line in lines[-3:]:
                            print(f"        {line.rstrip()}")
            except Exception as e:
                print(f"      ⚠️ 无法读取文件: {e}")
        print()

    return True


def check_container_logs():
    """检查容器内日志文件"""
    print("\n🐳 检查容器内日志文件...")

    success, output, error = run_command("docker exec TradingAgents-web ls -la /app/logs/")

    if success:
        print("✅ 容器内日志目录:")
        print(output)

        # 检查具体的日志文件
        success2, output2, _error2 = run_command("docker exec TradingAgents-web find /app/logs -name '*.log*' -type f")
        if success2 and output2.strip():
            print("📄 容器内日志文件:")
            for log_file in output2.strip().split("\n"):
                if log_file.strip():
                    print(f"   {log_file}")

                    # 获取文件大小
                    success3, output3, _error3 = run_command(f"docker exec TradingAgents-web wc -c {log_file}")
                    if success3:
                        size = output3.strip().split()[0]
                        print(f"      大小: {size} 字节")
        else:
            print("⚠️ 容器内未找到日志文件")

        return True
    print(f"❌ 无法访问容器内日志目录: {error}")
    return False


def check_docker_stdout_logs():
    """检查Docker标准输出日志"""
    print("\n📋 检查Docker标准输出日志...")

    success, output, error = run_command("docker logs --tail 20 TradingAgents-web")

    if success:
        print("✅ Docker标准输出日志 (最后20行):")
        print("-" * 60)
        print(output)
        print("-" * 60)
        return True
    print(f"❌ 无法获取Docker日志: {error}")
    return False


def main():
    """主函数"""
    print("🚀 Docker日志功能验证")
    print("=" * 60)

    results = []

    # 1. 检查容器状态
    results.append(("容器状态", check_container_status()))

    # 2. 触发日志生成
    results.append(("日志生成", trigger_logs_in_container()))

    # 等待一下让日志写入
    print("\n⏳ 等待日志写入...")
    time.sleep(3)

    # 3. 检查本地日志
    results.append(("本地日志", check_local_logs()))

    # 4. 检查容器内日志
    results.append(("容器内日志", check_container_logs()))

    # 5. 检查Docker标准日志
    results.append(("Docker标准日志", check_docker_stdout_logs()))

    # 总结结果
    print("\n" + "=" * 60)
    print("📋 验证结果总结")
    print("=" * 60)

    passed = 0
    for check_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{check_name}: {status}")
        if result:
            passed += 1

    print(f"\n📊 总体结果: {passed}/{len(results)} 项检查通过")

    if passed == len(results):
        print("\n🎉 所有检查都通过！日志功能正常")
        print("\n💡 现在可以:")
        print("   - 查看实时日志: tail -f logs/tradingagents.log")
        print("   - 查看Docker日志: docker-compose logs -f web")
        print("   - 使用日志工具: python view_logs.py")
    elif passed >= len(results) * 0.6:
        print("\n✅ 大部分功能正常")
        print("⚠️ 部分功能需要进一步检查")
    else:
        print("\n⚠️ 多项检查失败，需要进一步排查")
        print("\n🔧 建议:")
        print("   1. 重新构建镜像: docker-compose build")
        print("   2. 重启容器: docker-compose down && docker-compose up -d")
        print("   3. 检查配置: cat config/logging_docker.toml")

    return passed >= len(results) * 0.8


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
