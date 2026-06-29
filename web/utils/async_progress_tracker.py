#!/usr/bin/env python3
"""
异步进度跟踪器
支持Redis和文件两种存储方式，前端定时轮询获取进度
"""

import json
import os
import time
from pathlib import Path
from typing import Any

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("async_progress")


def safe_serialize(obj):
    """安全序列化对象，处理不可序列化的类型"""
    # 特殊处理LangChain消息对象
    if hasattr(obj, "__class__") and "Message" in obj.__class__.__name__:
        try:
            # 尝试使用LangChain的序列化方法
            if hasattr(obj, "dict"):
                return obj.dict()
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            # 手动提取消息内容
            return {
                "type": obj.__class__.__name__,
                "content": getattr(obj, "content", str(obj)),
                "additional_kwargs": getattr(obj, "additional_kwargs", {}),
                "response_metadata": getattr(obj, "response_metadata", {}),
            }
        except Exception:
            # 如果所有方法都失败，返回字符串表示
            return {"type": obj.__class__.__name__, "content": str(obj)}

    if hasattr(obj, "dict"):
        # Pydantic对象
        try:
            return obj.dict()
        except Exception:
            return str(obj)
    elif hasattr(obj, "__dict__"):
        # 普通对象，转换为字典
        result = {}
        for key, value in obj.__dict__.items():
            if not key.startswith("_"):  # 跳过私有属性
                try:
                    json.dumps(value)  # 测试是否可序列化
                    result[key] = value
                except (TypeError, ValueError):
                    result[key] = safe_serialize(value)  # 递归处理
        return result
    elif isinstance(obj, (list, tuple)):
        return [safe_serialize(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: safe_serialize(value) for key, value in obj.items()}
    else:
        try:
            json.dumps(obj)  # 测试是否可序列化
            return obj
        except (TypeError, ValueError):
            return str(obj)  # 转换为字符串


class AsyncProgressTracker:
    """异步进度跟踪器"""

    def __init__(self, analysis_id: str, analysts: list[str], research_depth: int, llm_provider: str):
        self.analysis_id = analysis_id
        self.analysts = analysts
        self.research_depth = research_depth
        self.llm_provider = llm_provider
        self.start_time = time.time()

        # 生成分析步骤
        self.analysis_steps = self._generate_dynamic_steps()
        self.estimated_duration = self._estimate_total_duration()

        # 初始化状态
        self.current_step = 0
        self.progress_data = {
            "analysis_id": analysis_id,
            "status": "running",
            "current_step": 0,
            "total_steps": len(self.analysis_steps),
            "progress_percentage": 0.0,
            "current_step_name": self.analysis_steps[0]["name"],
            "current_step_description": self.analysis_steps[0]["description"],
            "elapsed_time": 0.0,
            "estimated_total_time": self.estimated_duration,
            "remaining_time": self.estimated_duration,
            "last_message": "准备开始分析...",
            "last_update": time.time(),
            "start_time": self.start_time,
            "steps": self.analysis_steps,
        }

        # 尝试初始化Redis，失败则使用文件
        self.redis_client = None
        self.use_redis = self._init_redis()

        if not self.use_redis:
            # 使用文件存储
            self.progress_file = f"./data/progress_{analysis_id}.json"
            os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)

        # 保存初始状态
        self._save_progress()

        logger.info(f"📊 [异步进度] 初始化完成: {analysis_id}, 存储方式: {'Redis' if self.use_redis else '文件'}")

        # 注册到日志系统进行自动进度更新
        try:
            import threading

            from .progress_log_handler import register_analysis_tracker

            # 使用超时机制避免死锁
            def register_with_timeout():
                try:
                    register_analysis_tracker(self.analysis_id, self)
                    print(f"✅ [进度集成] 跟踪器注册成功: {self.analysis_id}")
                except Exception as e:
                    print(f"❌ [进度集成] 跟踪器注册失败: {e}")

            # 在单独线程中注册，避免阻塞主线程
            register_thread = threading.Thread(target=register_with_timeout, daemon=True)
            register_thread.start()
            register_thread.join(timeout=2.0)  # 2秒超时

            if register_thread.is_alive():
                print(f"⚠️ [进度集成] 跟踪器注册超时，继续执行: {self.analysis_id}")

        except ImportError:
            logger.debug("📊 [异步进度] 日志集成不可用")
        except Exception as e:
            print(f"❌ [进度集成] 跟踪器注册异常: {e}")

    def _init_redis(self) -> bool:
        """初始化Redis连接"""
        try:
            # 首先检查REDIS_ENABLED环境变量
            redis_enabled_raw = os.getenv("REDIS_ENABLED", "false")
            redis_enabled = redis_enabled_raw.lower()
            logger.info(f"🔍 [Redis检查] REDIS_ENABLED原值='{redis_enabled_raw}' -> 处理后='{redis_enabled}'")

            if redis_enabled != "true":
                logger.info("📊 [异步进度] Redis已禁用，使用文件存储")
                return False

            import redis

            # 从环境变量获取Redis配置
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_password = os.getenv("REDIS_PASSWORD", None)
            redis_db = int(os.getenv("REDIS_DB", 0))

            # 创建Redis连接
            if redis_password:
                self.redis_client = redis.Redis(
                    host=redis_host, port=redis_port, password=redis_password, db=redis_db, decode_responses=True,
                )
            else:
                self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

            # 测试连接
            self.redis_client.ping()
            logger.info(f"📊 [异步进度] Redis连接成功: {redis_host}:{redis_port}")
            return True
        except Exception as e:
            logger.warning(f"📊 [异步进度] Redis连接失败，使用文件存储: {e}")
            return False

    def _generate_dynamic_steps(self) -> list[dict]:
        """根据分析师数量和研究深度动态生成分析步骤"""
        steps = [
            {"name": "📋 准备阶段", "description": "验证股票代码，检查数据源可用性", "weight": 0.05},
            {"name": "🔧 环境检查", "description": "检查API密钥配置，确保数据获取正常", "weight": 0.02},
            {"name": "💰 成本估算", "description": "根据分析深度预估API调用成本", "weight": 0.01},
            {"name": "⚙️ 参数设置", "description": "配置分析参数和AI模型选择", "weight": 0.02},
            {"name": "🚀 启动引擎", "description": "初始化AI分析引擎，准备开始分析", "weight": 0.05},
        ]

        # 为每个分析师添加专门的步骤
        analyst_base_weight = 0.6 / len(self.analysts)  # 60%的时间用于分析师工作
        for analyst in self.analysts:
            analyst_info = self._get_analyst_step_info(analyst)
            steps.append(
                {
                    "name": analyst_info["name"],
                    "description": analyst_info["description"],
                    "weight": analyst_base_weight,
                },
            )

        # 根据研究深度添加后续步骤
        if self.research_depth >= 2:
            # 标准和深度分析包含研究员辩论
            steps.extend(
                [
                    {"name": "📈 多头观点", "description": "从乐观角度分析投资机会和上涨潜力", "weight": 0.06},
                    {"name": "📉 空头观点", "description": "从谨慎角度分析投资风险和下跌可能", "weight": 0.06},
                    {"name": "🤝 观点整合", "description": "综合多空观点，形成平衡的投资建议", "weight": 0.05},
                ],
            )

        # 所有深度都包含交易决策
        steps.append({"name": "💡 投资建议", "description": "基于分析结果制定具体的买卖建议", "weight": 0.06})

        if self.research_depth >= 3:
            # 深度分析包含详细风险评估
            steps.extend(
                [
                    {"name": "🔥 激进策略", "description": "评估高风险高收益的投资策略", "weight": 0.03},
                    {"name": "🛡️ 保守策略", "description": "评估低风险稳健的投资策略", "weight": 0.03},
                    {"name": "⚖️ 平衡策略", "description": "评估风险收益平衡的投资策略", "weight": 0.03},
                    {"name": "🎯 风险控制", "description": "制定风险控制措施和止损策略", "weight": 0.04},
                ],
            )
        else:
            # 快速和标准分析的简化风险评估
            steps.append({"name": "⚠️ 风险提示", "description": "识别主要投资风险并提供风险提示", "weight": 0.05})

        # 最后的整理步骤
        steps.append({"name": "📊 生成报告", "description": "整理所有分析结果，生成最终投资报告", "weight": 0.04})

        # 重新平衡权重，确保总和为1.0
        total_weight = sum(step["weight"] for step in steps)
        for step in steps:
            step["weight"] = step["weight"] / total_weight

        return steps

    def _get_analyst_display_name(self, analyst: str) -> str:
        """获取分析师显示名称（保留兼容性）"""
        name_map = {
            "market": "市场分析师",
            "fundamentals": "基本面分析师",
            "technical": "技术分析师",
            "sentiment": "情绪分析师",
            "risk": "风险分析师",
        }
        return name_map.get(analyst, f"{analyst}分析师")

    def _get_analyst_step_info(self, analyst: str) -> dict[str, str]:
        """获取分析师步骤信息（名称和描述）"""
        analyst_info = {
            "market": {"name": "📊 市场分析", "description": "分析股价走势、成交量、市场热度等市场表现"},
            "fundamentals": {"name": "💼 基本面分析", "description": "分析公司财务状况、盈利能力、成长性等基本面"},
            "technical": {"name": "📈 技术分析", "description": "分析K线图形、技术指标、支撑阻力等技术面"},
            "sentiment": {"name": "💭 情绪分析", "description": "分析市场情绪、投资者心理、舆论倾向等"},
            "news": {"name": "📰 新闻分析", "description": "分析相关新闻、公告、行业动态对股价的影响"},
            "social_media": {"name": "🌐 社交媒体", "description": "分析社交媒体讨论、网络热度、散户情绪等"},
            "risk": {"name": "⚠️ 风险分析", "description": "识别投资风险、评估风险等级、制定风控措施"},
        }

        return analyst_info.get(analyst, {"name": f"🔍 {analyst}分析", "description": f"进行{analyst}相关的专业分析"})

    def _estimate_total_duration(self) -> float:
        """根据分析师数量、研究深度、模型类型预估总时长（秒）"""
        # 基础时间（秒）- 环境准备、配置等
        base_time = 60

        # 每个分析师的实际耗时（基于真实测试数据）
        analyst_base_time = {
            1: 180,  # 快速分析：每个分析师约3分钟
            2: 360,  # 标准分析：每个分析师约6分钟
            3: 600,  # 深度分析：每个分析师约10分钟
        }.get(self.research_depth, 360)

        analyst_time = len(self.analysts) * analyst_base_time

        # 模型速度影响（基于实际测试）
        model_multiplier = {
            "dashscope": 1.0,  # 阿里百炼速度适中
            "deepseek": 0.7,  # DeepSeek较快
            "google": 1.3,  # Google较慢
        }.get(self.llm_provider, 1.0)

        # 研究深度额外影响（工具调用复杂度）
        depth_multiplier = {
            1: 0.8,  # 快速分析，较少工具调用
            2: 1.0,  # 基础分析，标准工具调用
            3: 1.3,  # 标准分析，更多工具调用和推理
        }.get(self.research_depth, 1.0)

        total_time = (base_time + analyst_time) * model_multiplier * depth_multiplier
        return total_time

    def update_progress(self, message: str, step: int | None = None):
        """更新进度状态"""
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        # 自动检测步骤
        if step is None:
            step = self._detect_step_from_message(message)

        # 更新步骤（防止倒退）
        if step is not None and step >= self.current_step:
            self.current_step = step
            logger.debug(f"📊 [异步进度] 步骤推进到 {self.current_step + 1}/{len(self.analysis_steps)}")

        # 如果是完成消息，确保进度为100%
        if "分析完成" in message or "分析成功" in message or "✅ 分析完成" in message:
            self.current_step = len(self.analysis_steps) - 1
            logger.info("📊 [异步进度] 分析完成，设置为最终步骤")

        # 计算进度
        progress_percentage = self._calculate_weighted_progress() * 100
        remaining_time = self._estimate_remaining_time(progress_percentage / 100, elapsed_time)

        # 更新进度数据
        current_step_info = (
            self.analysis_steps[self.current_step]
            if self.current_step < len(self.analysis_steps)
            else self.analysis_steps[-1]
        )

        # 特殊处理工具调用消息，更新步骤描述但不改变步骤
        step_description = current_step_info["description"]
        if "工具调用" in message:
            # 提取工具名称并更新描述
            if "get_stock_market_data_unified" in message:
                step_description = "正在获取市场数据和技术指标..."
            elif "get_stock_fundamentals_unified" in message:
                step_description = "正在获取基本面数据和财务指标..."
            elif "get_china_stock_data" in message:
                step_description = "正在获取A股市场数据..."
            elif "get_china_fundamentals" in message:
                step_description = "正在获取A股基本面数据..."
            else:
                step_description = "正在调用分析工具..."
        elif "模块开始" in message:
            step_description = f"开始{current_step_info['name']}..."
        elif "模块完成" in message:
            step_description = f"{current_step_info['name']}已完成"

        self.progress_data.update(
            {
                "current_step": self.current_step,
                "progress_percentage": progress_percentage,
                "current_step_name": current_step_info["name"],
                "current_step_description": step_description,
                "elapsed_time": elapsed_time,
                "remaining_time": remaining_time,
                "last_message": message,
                "last_update": current_time,
                "status": "completed" if progress_percentage >= 100 else "running",
            },
        )

        # 保存到存储
        self._save_progress()

        # 详细的更新日志
        step_name = current_step_info.get("name", "未知")
        logger.info(f"📊 [进度更新] {self.analysis_id}: {message[:50]}...")
        logger.debug(
            f"📊 [进度详情] 步骤{self.current_step + 1}/{len(self.analysis_steps)} ({step_name}), 进度{progress_percentage:.1f}%, 耗时{elapsed_time:.1f}s",
        )

    def _detect_step_from_message(self, message: str) -> int | None:
        """根据消息内容智能检测当前步骤"""
        message_lower = message.lower()

        # 开始分析阶段 - 只匹配最初的开始消息
        if "🚀 开始股票分析" in message or "验证" in message or "预获取" in message or "数据准备" in message:
            return 0
        # 环境准备阶段
        if "环境" in message or "api" in message_lower or "密钥" in message:
            return 1
        # 成本预估阶段
        if "成本" in message or "预估" in message:
            return 2
        # 参数配置阶段
        if "配置" in message or "参数" in message:
            return 3
        # 引擎初始化阶段
        if "初始化" in message or "引擎" in message:
            return 4
        # 模块开始日志 - 只在第一次开始时推进步骤
        if "模块开始" in message:
            # 从日志中提取分析师类型，匹配新的步骤名称
            if "market_analyst" in message or "market" in message:
                return self._find_step_by_keyword(["市场分析", "市场"])
            if "fundamentals_analyst" in message or "fundamentals" in message:
                return self._find_step_by_keyword(["基本面分析", "基本面"])
            if "technical_analyst" in message or "technical" in message:
                return self._find_step_by_keyword(["技术分析", "技术"])
            if "sentiment_analyst" in message or "sentiment" in message:
                return self._find_step_by_keyword(["情绪分析", "情绪"])
            if "news_analyst" in message or "news" in message:
                return self._find_step_by_keyword(["新闻分析", "新闻"])
            if "social_media_analyst" in message or "social" in message:
                return self._find_step_by_keyword(["社交媒体", "社交"])
            if "risk_analyst" in message or "risk" in message:
                return self._find_step_by_keyword(["风险分析", "风险"])
            if "bull_researcher" in message or "bull" in message:
                return self._find_step_by_keyword(["多头观点", "多头", "看涨"])
            if "bear_researcher" in message or "bear" in message:
                return self._find_step_by_keyword(["空头观点", "空头", "看跌"])
            if "research_manager" in message:
                return self._find_step_by_keyword(["观点整合", "整合"])
            if "trader" in message:
                return self._find_step_by_keyword(["投资建议", "建议"])
            if "risk_manager" in message:
                return self._find_step_by_keyword(["风险控制", "控制"])
            if "graph_signal_processing" in message or "signal" in message:
                return self._find_step_by_keyword(["生成报告", "报告"])
        # 工具调用日志 - 不推进步骤，只更新描述
        elif "工具调用" in message:
            # 保持当前步骤，不推进
            return None
        # 模块完成日志 - 推进到下一步
        elif "模块完成" in message:
            # 模块完成时，从当前步骤推进到下一步
            # 不再依赖模块名称，而是基于当前进度推进
            next_step = min(self.current_step + 1, len(self.analysis_steps) - 1)
            logger.debug(f"📊 [步骤推进] 模块完成，从步骤{self.current_step}推进到步骤{next_step}")
            return next_step

        return None

    def _find_step_by_keyword(self, keywords) -> int | None:
        """根据关键词查找步骤索引"""
        if isinstance(keywords, str):
            keywords = [keywords]

        for i, step in enumerate(self.analysis_steps):
            for keyword in keywords:
                if keyword in step["name"]:
                    return i
        return None

    def _get_next_step(self, keyword: str) -> int | None:
        """获取指定步骤的下一步"""
        current_step_index = self._find_step_by_keyword(keyword)
        if current_step_index is not None:
            return min(current_step_index + 1, len(self.analysis_steps) - 1)
        return None

    def _calculate_weighted_progress(self) -> float:
        """根据步骤权重计算进度"""
        if self.current_step >= len(self.analysis_steps):
            return 1.0

        # 如果是最后一步，返回100%
        if self.current_step == len(self.analysis_steps) - 1:
            return 1.0

        completed_weight = sum(step["weight"] for step in self.analysis_steps[: self.current_step])
        total_weight = sum(step["weight"] for step in self.analysis_steps)

        return min(completed_weight / total_weight, 1.0)

    def _estimate_remaining_time(self, progress: float, elapsed_time: float) -> float:
        """基于预估总时长计算剩余时间"""
        # 如果进度已完成，剩余时间为0
        if progress >= 1.0:
            return 0.0

        # 使用预估的总时长（固定值）
        # 预计剩余 = 预估总时长 - 已用时间
        remaining = max(self.estimated_duration - elapsed_time, 0)

        return remaining

    def _save_progress(self):
        """保存进度到存储"""
        try:
            current_step_name = self.progress_data.get("current_step_name", "未知")
            progress_pct = self.progress_data.get("progress_percentage", 0)
            status = self.progress_data.get("status", "running")

            if self.use_redis:
                # 保存到Redis（安全序列化）
                key = f"progress:{self.analysis_id}"
                safe_data = safe_serialize(self.progress_data)
                data_json = json.dumps(safe_data, ensure_ascii=False)
                self.redis_client.setex(key, 3600, data_json)  # 1小时过期

                logger.info(
                    f"📊 [Redis写入] {self.analysis_id} -> {status} | {current_step_name} | {progress_pct:.1f}%",
                )
                logger.debug(f"📊 [Redis详情] 键: {key}, 数据大小: {len(data_json)} 字节")
            else:
                # 保存到文件（安全序列化）
                safe_data = safe_serialize(self.progress_data)
                with open(self.progress_file, "w", encoding="utf-8") as f:
                    json.dump(safe_data, f, ensure_ascii=False, indent=2)

                logger.info(f"📊 [文件写入] {self.analysis_id} -> {status} | {current_step_name} | {progress_pct:.1f}%")
                logger.debug(f"📊 [文件详情] 路径: {self.progress_file}")

        except Exception as e:
            logger.error(f"📊 [异步进度] 保存失败: {e}")
            # 尝试备用存储方式
            try:
                if self.use_redis:
                    # Redis失败，尝试文件存储
                    logger.warning("📊 [异步进度] Redis保存失败，尝试文件存储")
                    backup_file = f"./data/progress_{self.analysis_id}.json"
                    os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                    safe_data = safe_serialize(self.progress_data)
                    with open(backup_file, "w", encoding="utf-8") as f:
                        json.dump(safe_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"📊 [备用存储] 文件保存成功: {backup_file}")
                else:
                    # 文件存储失败，尝试简化数据
                    logger.warning("📊 [异步进度] 文件保存失败，尝试简化数据")
                    simplified_data = {
                        "analysis_id": self.analysis_id,
                        "status": self.progress_data.get("status", "unknown"),
                        "progress_percentage": self.progress_data.get("progress_percentage", 0),
                        "last_message": str(self.progress_data.get("last_message", "")),
                        "last_update": self.progress_data.get("last_update", time.time()),
                    }
                    backup_file = f"./data/progress_{self.analysis_id}.json"
                    with open(backup_file, "w", encoding="utf-8") as f:
                        json.dump(simplified_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"📊 [备用存储] 简化数据保存成功: {backup_file}")
            except Exception as backup_e:
                logger.error(f"📊 [异步进度] 备用存储也失败: {backup_e}")

    def get_progress(self) -> dict[str, Any]:
        """获取当前进度"""
        return self.progress_data.copy()

    def mark_completed(self, message: str = "分析完成", results: Any = None):
        """标记分析完成"""
        self.update_progress(message)
        self.progress_data["status"] = "completed"
        self.progress_data["progress_percentage"] = 100.0
        self.progress_data["remaining_time"] = 0.0

        # 保存分析结果（安全序列化）
        if results is not None:
            try:
                self.progress_data["raw_results"] = safe_serialize(results)
                logger.info(f"📊 [异步进度] 保存分析结果: {self.analysis_id}")
            except Exception as e:
                logger.warning(f"📊 [异步进度] 结果序列化失败: {e}")
                self.progress_data["raw_results"] = str(results)  # 最后的fallback

        self._save_progress()
        logger.info(f"📊 [异步进度] 分析完成: {self.analysis_id}")

        # 从日志系统注销
        try:
            from .progress_log_handler import unregister_analysis_tracker

            unregister_analysis_tracker(self.analysis_id)
        except ImportError:
            pass

    def mark_failed(self, error_message: str):
        """标记分析失败"""
        self.progress_data["status"] = "failed"
        self.progress_data["last_message"] = f"分析失败: {error_message}"
        self.progress_data["last_update"] = time.time()
        self._save_progress()
        logger.error(f"📊 [异步进度] 分析失败: {self.analysis_id}, 错误: {error_message}")

        # 从日志系统注销
        try:
            from .progress_log_handler import unregister_analysis_tracker

            unregister_analysis_tracker(self.analysis_id)
        except ImportError:
            pass


def get_progress_by_id(analysis_id: str) -> dict[str, Any] | None:
    """根据分析ID获取进度"""
    try:
        # 检查REDIS_ENABLED环境变量
        redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"

        # 如果Redis启用，先尝试Redis
        if redis_enabled:
            try:
                import redis

                # 从环境变量获取Redis配置
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = int(os.getenv("REDIS_PORT", 6379))
                redis_password = os.getenv("REDIS_PASSWORD", None)
                redis_db = int(os.getenv("REDIS_DB", 0))

                # 创建Redis连接
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host, port=redis_port, password=redis_password, db=redis_db, decode_responses=True,
                    )
                else:
                    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

                key = f"progress:{analysis_id}"
                data = redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.debug(f"📊 [异步进度] Redis读取失败: {e}")

        # 尝试文件
        progress_file = f"./data/progress_{analysis_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, encoding="utf-8") as f:
                return json.load(f)

        return None
    except Exception as e:
        logger.error(f"📊 [异步进度] 获取进度失败: {analysis_id}, 错误: {e}")
        return None


def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    if seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    hours = seconds / 3600
    return f"{hours:.1f}小时"


def get_latest_analysis_id() -> str | None:
    """获取最新的分析ID"""
    try:
        # 检查REDIS_ENABLED环境变量
        redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"

        # 如果Redis启用，先尝试从Redis获取
        if redis_enabled:
            try:
                import redis

                # 从环境变量获取Redis配置
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = int(os.getenv("REDIS_PORT", 6379))
                redis_password = os.getenv("REDIS_PASSWORD", None)
                redis_db = int(os.getenv("REDIS_DB", 0))

                # 创建Redis连接
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host, port=redis_port, password=redis_password, db=redis_db, decode_responses=True,
                    )
                else:
                    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

                # 获取所有progress键
                keys = redis_client.keys("progress:*")
                if not keys:
                    return None

                # 获取每个键的数据，找到最新的
                latest_time = 0
                latest_id = None

                for key in keys:
                    try:
                        data = redis_client.get(key)
                        if data:
                            progress_data = json.loads(data)
                            last_update = progress_data.get("last_update", 0)
                            if last_update > latest_time:
                                latest_time = last_update
                                # 从键名中提取analysis_id (去掉"progress:"前缀)
                                latest_id = key.replace("progress:", "")
                    except Exception:
                        continue

                if latest_id:
                    logger.info(f"📊 [恢复分析] 找到最新分析ID: {latest_id}")
                    return latest_id

            except Exception as e:
                logger.debug(f"📊 [恢复分析] Redis查找失败: {e}")

        # 如果Redis失败或未启用，尝试从文件查找
        data_dir = Path("data")
        if data_dir.exists():
            progress_files = list(data_dir.glob("progress_*.json"))
            if progress_files:
                # 按修改时间排序，获取最新的
                latest_file = max(progress_files, key=lambda f: f.stat().st_mtime)
                # 从文件名提取analysis_id
                filename = latest_file.name
                if filename.startswith("progress_") and filename.endswith(".json"):
                    analysis_id = filename[9:-5]  # 去掉前缀和后缀
                    logger.debug(f"📊 [恢复分析] 从文件找到最新分析ID: {analysis_id}")
                    return analysis_id

        return None
    except Exception as e:
        logger.error(f"📊 [恢复分析] 获取最新分析ID失败: {e}")
        return None
