#!/usr/bin/env python3
"""
数据获取调用分析工具
专门分析数据获取相关的日志，提供详细的调用统计和性能分析
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("scripts")


class DataCallAnalyzer:
    """数据获取调用分析器"""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.data_calls = []
        self.tool_calls = []
        self.data_source_calls = []

    def parse_logs(self):
        """解析日志文件"""
        if not self.log_file.exists():
            logger.error(f"❌ 日志文件不存在: {self.log_file}")
            return

        logger.info(f"📖 解析数据获取日志: {self.log_file}")

        with open(self.log_file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # 尝试解析结构化日志（JSON）
                if line.startswith("{"):
                    try:
                        entry = json.loads(line)
                        self._process_structured_entry(entry, line_num)
                        continue
                    except json.JSONDecodeError:
                        pass

                # 解析普通日志
                self._process_regular_log(line, line_num)

        logger.info(
            f"✅ 解析完成: {len(self.data_calls)} 条数据调用, {len(self.tool_calls)} 条工具调用, {len(self.data_source_calls)} 条数据源调用",
        )

    def _process_structured_entry(self, entry: dict[str, Any], line_num: int):
        """处理结构化日志条目"""
        event_type = entry.get("event_type", "")

        if "data_fetch" in event_type:
            self.data_calls.append(
                {
                    "type": "structured",
                    "line_num": line_num,
                    "timestamp": entry.get("timestamp"),
                    "event_type": event_type,
                    "symbol": entry.get("symbol"),
                    "start_date": entry.get("start_date"),
                    "end_date": entry.get("end_date"),
                    "data_source": entry.get("data_source"),
                    "duration": entry.get("duration"),
                    "result_length": entry.get("result_length"),
                    "result_preview": entry.get("result_preview"),
                    "error": entry.get("error"),
                    "entry": entry,
                },
            )

        elif "tool_call" in event_type:
            self.tool_calls.append(
                {
                    "type": "structured",
                    "line_num": line_num,
                    "timestamp": entry.get("timestamp"),
                    "event_type": event_type,
                    "tool_name": entry.get("tool_name"),
                    "duration": entry.get("duration"),
                    "args_info": entry.get("args_info"),
                    "result_info": entry.get("result_info"),
                    "error": entry.get("error"),
                    "entry": entry,
                },
            )

        elif "unified_data_call" in event_type:
            self.data_source_calls.append(
                {
                    "type": "structured",
                    "line_num": line_num,
                    "timestamp": entry.get("timestamp"),
                    "event_type": event_type,
                    "function": entry.get("function"),
                    "ticker": entry.get("ticker"),
                    "start_date": entry.get("start_date"),
                    "end_date": entry.get("end_date"),
                    "duration": entry.get("duration"),
                    "result_length": entry.get("result_length"),
                    "result_preview": entry.get("result_preview"),
                    "error": entry.get("error"),
                    "entry": entry,
                },
            )

    def _process_regular_log(self, line: str, line_num: int):
        """处理普通日志行"""
        # 匹配数据获取相关的日志
        patterns = [
            (r"📊.*\[数据获取\].*symbol=(\w+).*start_date=([^,]+).*end_date=([^,]+)", "data_fetch"),
            (r"🔧.*\[工具调用\].*(\w+)", "tool_call"),
            (r"📊.*\[统一接口\].*获取(\w+)股票数据", "unified_call"),
            (r"📊.*\[(Tushare|AKShare|BaoStock|TDX)\].*调用参数.*symbol=(\w+)", "data_source_call"),
        ]

        for pattern, call_type in patterns:
            match = re.search(pattern, line)
            if match:
                # 提取时间戳
                timestamp_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
                timestamp = timestamp_match.group(1) if timestamp_match else None

                if call_type == "data_fetch":
                    self.data_calls.append(
                        {
                            "type": "regular",
                            "line_num": line_num,
                            "timestamp": timestamp,
                            "symbol": match.group(1),
                            "start_date": match.group(2),
                            "end_date": match.group(3),
                            "raw_line": line,
                        },
                    )
                elif call_type == "tool_call":
                    self.tool_calls.append(
                        {
                            "type": "regular",
                            "line_num": line_num,
                            "timestamp": timestamp,
                            "tool_name": match.group(1),
                            "raw_line": line,
                        },
                    )
                elif call_type == "data_source_call":
                    self.data_source_calls.append(
                        {
                            "type": "regular",
                            "line_num": line_num,
                            "timestamp": timestamp,
                            "data_source": match.group(1),
                            "symbol": match.group(2),
                            "raw_line": line,
                        },
                    )
                break

    def analyze_data_calls(self) -> dict[str, Any]:
        """分析数据获取调用"""
        logger.info("\n📊 数据获取调用分析")
        logger.info("=")

        analysis = {
            "total_calls": len(self.data_calls),
            "by_symbol": defaultdict(int),
            "by_data_source": defaultdict(int),
            "by_date_range": defaultdict(int),
            "performance": {"total_duration": 0, "avg_duration": 0, "slow_calls": [], "fast_calls": []},
            "success_rate": {"total": 0, "success": 0, "warning": 0, "error": 0},
        }

        durations = []

        for call in self.data_calls:
            # 统计股票代码
            symbol = call.get("symbol")
            if symbol:
                analysis["by_symbol"][symbol] += 1

            # 统计数据源
            data_source = call.get("data_source")
            if data_source:
                analysis["by_data_source"][data_source] += 1

            # 统计日期范围
            start_date = call.get("start_date")
            end_date = call.get("end_date")
            if start_date and end_date:
                date_range = f"{start_date} to {end_date}"
                analysis["by_date_range"][date_range] += 1

            # 性能分析
            duration = call.get("duration")
            if duration:
                durations.append(duration)
                analysis["performance"]["total_duration"] += duration

                if duration > 5.0:  # 超过5秒的慢调用
                    analysis["performance"]["slow_calls"].append(
                        {
                            "symbol": symbol,
                            "duration": duration,
                            "data_source": data_source,
                            "line_num": call.get("line_num"),
                        },
                    )
                elif duration < 1.0:  # 小于1秒的快调用
                    analysis["performance"]["fast_calls"].append(
                        {
                            "symbol": symbol,
                            "duration": duration,
                            "data_source": data_source,
                            "line_num": call.get("line_num"),
                        },
                    )

            # 成功率分析
            event_type = call.get("event_type", "")
            if "success" in event_type:
                analysis["success_rate"]["success"] += 1
            elif "warning" in event_type:
                analysis["success_rate"]["warning"] += 1
            elif "error" in event_type or "exception" in event_type:
                analysis["success_rate"]["error"] += 1

            analysis["success_rate"]["total"] += 1

        # 计算平均时间
        if durations:
            analysis["performance"]["avg_duration"] = sum(durations) / len(durations)

        # 输出分析结果
        logger.info(f"📈 总调用次数: {analysis['total_calls']}")

        if analysis["by_symbol"]:
            logger.info("\n📊 按股票代码统计 (前10):")
            for symbol, count in Counter(analysis["by_symbol"]).most_common(10):
                logger.info(f"  - {symbol}: {count} 次")

        if analysis["by_data_source"]:
            logger.info("\n🔧 按数据源统计:")
            for source, count in Counter(analysis["by_data_source"]).most_common():
                logger.info(f"  - {source}: {count} 次")

        if durations:
            logger.info("\n⏱️  性能统计:")
            logger.info(f"  - 总耗时: {analysis['performance']['total_duration']:.2f}s")
            logger.info(f"  - 平均耗时: {analysis['performance']['avg_duration']:.2f}s")
            logger.info(f"  - 慢调用 (>5s): {len(analysis['performance']['slow_calls'])} 次")
            logger.info(f"  - 快调用 (<1s): {len(analysis['performance']['fast_calls'])} 次")

        if analysis["success_rate"]["total"] > 0:
            success_pct = (analysis["success_rate"]["success"] / analysis["success_rate"]["total"]) * 100
            logger.info("\n✅ 成功率统计:")
            logger.info(f"  - 成功: {analysis['success_rate']['success']} ({success_pct:.1f}%)")
            logger.warning(f"  - 警告: {analysis['success_rate']['warning']}")
            logger.error(f"  - 错误: {analysis['success_rate']['error']}")

        return analysis

    def analyze_tool_calls(self) -> dict[str, Any]:
        """分析工具调用"""
        logger.info("\n🔧 工具调用分析")
        logger.info("=")

        analysis = {
            "total_calls": len(self.tool_calls),
            "by_tool": defaultdict(int),
            "performance": defaultdict(list),
            "success_rate": defaultdict(int),
        }

        for call in self.tool_calls:
            tool_name = call.get("tool_name", "unknown")
            analysis["by_tool"][tool_name] += 1

            duration = call.get("duration")
            if duration:
                analysis["performance"][tool_name].append(duration)

            event_type = call.get("event_type", "")
            if "success" in event_type:
                analysis["success_rate"][f"{tool_name}_success"] += 1
            elif "error" in event_type:
                analysis["success_rate"][f"{tool_name}_error"] += 1

        # 输出结果
        logger.info(f"🔧 总工具调用: {analysis['total_calls']}")

        if analysis["by_tool"]:
            logger.info("\n📊 按工具统计:")
            for tool, count in Counter(analysis["by_tool"]).most_common():
                logger.info(f"  - {tool}: {count} 次")

                # 性能统计
                if tool in analysis["performance"]:
                    durations = analysis["performance"][tool]
                    avg_duration = sum(durations) / len(durations)
                    logger.info(f"    平均耗时: {avg_duration:.2f}s")

        return analysis

    def generate_report(self) -> str:
        """生成分析报告"""
        logger.info("\n📋 生成数据获取分析报告")
        logger.info("=")

        data_analysis = self.analyze_data_calls()
        tool_analysis = self.analyze_tool_calls()

        report = f"""
# 数据获取调用分析报告

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
日志文件: {self.log_file}

## 概览
- 数据获取调用: {data_analysis["total_calls"]}
- 工具调用: {tool_analysis["total_calls"]}
- 数据源调用: {len(self.data_source_calls)}

## 数据获取性能
- 总耗时: {data_analysis["performance"]["total_duration"]:.2f}s
- 平均耗时: {data_analysis["performance"]["avg_duration"]:.2f}s
- 慢调用数量: {len(data_analysis["performance"]["slow_calls"])}

## 成功率
- 成功调用: {data_analysis["success_rate"]["success"]}
- 警告调用: {data_analysis["success_rate"]["warning"]}
- 错误调用: {data_analysis["success_rate"]["error"]}

## 建议
"""

        # 添加建议
        if data_analysis["performance"]["avg_duration"] > 3.0:
            report += "- ⚠️ 平均数据获取时间较长，建议优化缓存策略\n"

        if data_analysis["success_rate"]["error"] > 0:
            report += f"- ❌ 发现 {data_analysis['success_rate']['error']} 个数据获取错误，建议检查数据源配置\n"

        if len(data_analysis["performance"]["slow_calls"]) > 5:
            report += "- 🐌 慢调用较多，建议分析网络连接和API限制\n"

        return report


def main():
    parser = argparse.ArgumentParser(description="数据获取调用分析工具")
    parser.add_argument("log_file", help="日志文件路径")
    parser.add_argument("--output", "-o", help="输出报告文件路径")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    args = parser.parse_args()

    log_file = Path(args.log_file)
    analyzer = DataCallAnalyzer(log_file)

    try:
        analyzer.parse_logs()
        report = analyzer.generate_report()

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"📄 报告已保存到: {args.output}")
        else:
            print(report)

    except Exception as e:
        logger.error(f"❌ 分析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
