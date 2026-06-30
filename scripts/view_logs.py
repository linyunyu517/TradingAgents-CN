#!/usr/bin/env python3
"""
TradingAgents 日志查看工具
方便查看和分析应用日志
"""

import time
from datetime import datetime
from pathlib import Path


def get_log_files():
    """获取所有日志文件"""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return []

    log_files = []
    for pattern in ["*.log", "*.log.*"]:
        log_files.extend(logs_dir.glob(pattern))

    return sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)


def show_log_files():
    """显示所有日志文件"""
    log_files = get_log_files()

    if not log_files:
        print("📋 未找到日志文件")
        return []

    print(f"📋 找到 {len(log_files)} 个日志文件:")
    print("-" * 60)

    for i, log_file in enumerate(log_files, 1):
        stat = log_file.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)

        # 格式化文件大小
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        print(f"{i:2d}. 📄 {log_file.name}")
        print(f"     📊 大小: {size_str}")
        print(f"     🕒 修改时间: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    return log_files


def view_log_file(log_file, lines=50):
    """查看日志文件内容"""
    print(f"📄 查看日志文件: {log_file.name}")
    print("=" * 80)

    try:
        with open(log_file, encoding="utf-8") as f:
            content = f.readlines()

        if not content:
            print("📋 日志文件为空")
            return

        total_lines = len(content)
        print(f"📊 总行数: {total_lines:,}")

        if lines > 0:
            if lines >= total_lines:
                print("📋 显示全部内容:")
                start_line = 0
            else:
                print(f"📋 显示最后 {lines} 行:")
                start_line = total_lines - lines

            print("-" * 80)
            for i, line in enumerate(content[start_line:], start_line + 1):
                print(f"{i:6d} | {line.rstrip()}")
        else:
            print("📋 显示全部内容:")
            print("-" * 80)
            for i, line in enumerate(content, 1):
                print(f"{i:6d} | {line.rstrip()}")

        print("-" * 80)

    except Exception as e:
        print(f"❌ 读取文件失败: {e}")


def tail_log_file(log_file):
    """实时跟踪日志文件"""
    print(f"📄 实时跟踪日志文件: {log_file.name}")
    print("📋 按 Ctrl+C 停止跟踪")
    print("=" * 80)

    try:
        with open(log_file, encoding="utf-8") as f:
            # 移动到文件末尾
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {line.rstrip()}")
                else:
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n⏹️ 停止跟踪")
    except Exception as e:
        print(f"❌ 跟踪失败: {e}")


def search_logs(keyword, log_files=None):
    """搜索日志内容"""
    if log_files is None:
        log_files = get_log_files()

    if not log_files:
        print("📋 未找到日志文件")
        return

    print(f"🔍 搜索关键词: '{keyword}'")
    print("=" * 80)

    total_matches = 0

    for log_file in log_files:
        try:
            with open(log_file, encoding="utf-8") as f:
                lines = f.readlines()

            matches = []
            for i, line in enumerate(lines, 1):
                if keyword.lower() in line.lower():
                    matches.append((i, line.rstrip()))

            if matches:
                print(f"📄 {log_file.name} ({len(matches)} 个匹配)")
                print("-" * 60)

                for line_num, line in matches[-10:]:  # 显示最后10个匹配
                    print(f"{line_num:6d} | {line}")

                if len(matches) > 10:
                    print(f"     ... 还有 {len(matches) - 10} 个匹配")

                print()
                total_matches += len(matches)

        except Exception as e:
            print(f"❌ 搜索 {log_file.name} 失败: {e}")

    print(f"🎯 总共找到 {total_matches} 个匹配")


def main():
    """主函数"""
    print("🚀 TradingAgents 日志查看工具")
    print("=" * 50)

    while True:
        print("\n💡 选择操作:")
        print("1. 📋 显示所有日志文件")
        print("2. 👀 查看日志文件内容")
        print("3. 📺 实时跟踪日志")
        print("4. 🔍 搜索日志内容")
        print("5. 🐳 查看Docker日志")
        print("0. 🚪 退出")

        try:
            choice = input("\n请选择 (0-5): ").strip()

            if choice == "0":
                print("👋 再见！")
                break
            if choice == "1":
                show_log_files()
            elif choice == "2":
                log_files = show_log_files()
                if log_files:
                    try:
                        file_num = int(input(f"\n选择文件 (1-{len(log_files)}): ")) - 1
                        if 0 <= file_num < len(log_files):
                            lines = input("显示行数 (默认50，0=全部): ").strip()
                            lines = int(lines) if lines else 50
                            view_log_file(log_files[file_num], lines)
                        else:
                            print("❌ 无效选择")
                    except ValueError:
                        print("❌ 请输入有效数字")
            elif choice == "3":
                log_files = show_log_files()
                if log_files:
                    try:
                        file_num = int(input(f"\n选择文件 (1-{len(log_files)}): ")) - 1
                        if 0 <= file_num < len(log_files):
                            tail_log_file(log_files[file_num])
                        else:
                            print("❌ 无效选择")
                    except ValueError:
                        print("❌ 请输入有效数字")
            elif choice == "4":
                keyword = input("输入搜索关键词: ").strip()
                if keyword:
                    search_logs(keyword)
                else:
                    print("❌ 请输入关键词")
            elif choice == "5":
                print("🐳 查看Docker容器日志...")
                print("💡 运行以下命令查看Docker日志:")
                print("   docker-compose logs -f web")
                print("   docker logs TradingAgents-web")
            else:
                print("❌ 无效选择，请重新输入")

        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")


if __name__ == "__main__":
    main()
