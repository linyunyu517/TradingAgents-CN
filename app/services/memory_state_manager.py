"""
内存状态管理器
类似于 analysis-engine 的实现，提供快速的状态读写
"""

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskState:
    """任务状态数据类"""

    task_id: str
    user_id: str
    stock_code: str
    status: TaskStatus
    stock_name: str | None = None
    progress: int = 0
    message: str = ""
    current_step: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    result_data: dict[str, Any] | None = None
    error_message: str | None = None

    # 分析参数
    parameters: dict[str, Any] | None = None

    # 性能指标
    execution_time: float | None = None
    tokens_used: int | None = None
    estimated_duration: float | None = None  # 预估总时长（秒）

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        # 处理枚举类型
        data["status"] = self.status.value
        # 处理时间格式
        if self.start_time:
            data["start_time"] = self.start_time.isoformat()

        # 🐛 [BUG-030] 确保 current_step_name 字段始终存在（前端依赖此字段）
        data["current_step_name"] = self.current_step or ""
        if self.end_time:
            data["end_time"] = self.end_time.isoformat()

        # 添加实时计算的时间信息
        if self.start_time:
            if self.end_time:
                # 任务已完成，使用最终执行时间
                data["elapsed_time"] = self.execution_time or (self.end_time - self.start_time).total_seconds()
                data["remaining_time"] = 0
                data["estimated_total_time"] = data["elapsed_time"]
            else:
                # 任务进行中，实时计算已用时间
                from datetime import datetime

                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                data["elapsed_time"] = elapsed_time

                # 计算预计剩余时间和总时长
                progress = self.progress / 100 if self.progress > 0 else 0

                # 使用任务创建时预估的总时长，如果没有则使用默认值（5分钟）
                estimated_total = self.estimated_duration or 600

                if progress >= 1.0:
                    # 任务已完成
                    data["remaining_time"] = 0
                    data["estimated_total_time"] = elapsed_time
                else:
                    # 使用预估的总时长（固定值）
                    data["estimated_total_time"] = estimated_total
                    # 预计剩余 = 预估总时长 - 已用时间
                    data["remaining_time"] = max(0, estimated_total - elapsed_time)
        else:
            data["elapsed_time"] = 0
            data["remaining_time"] = 600  # 默认10分钟
            data["estimated_total_time"] = 600

        return data


class MemoryStateManager:
    """内存状态管理器"""

    def __init__(self):
        self._tasks: dict[str, TaskState] = {}
        # 🔧 使用 threading.Lock 代替 asyncio.Lock，避免事件循环冲突
        # 当在线程池中执行分析时，会创建新的事件循环，asyncio.Lock 会导致
        # "is bound to a different event loop" 错误
        self._lock = threading.Lock()
        self._websocket_manager = None

    def set_websocket_manager(self, websocket_manager):
        """设置 WebSocket 管理器"""
        self._websocket_manager = websocket_manager

    async def create_task(
        self,
        task_id: str,
        user_id: str,
        stock_code: str,
        parameters: dict[str, Any] | None = None,
        stock_name: str | None = None,
    ) -> TaskState:
        """创建新任务"""
        with self._lock:
            # 计算预估总时长
            estimated_duration = self._calculate_estimated_duration(parameters or {})

            task_state = TaskState(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                stock_name=stock_name,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
                parameters=parameters or {},
                estimated_duration=estimated_duration,
                message="任务已创建，等待执行...",
            )
            self._tasks[task_id] = task_state
            logger.info(f"📝 创建任务状态: {task_id}")
            logger.info(f"⏱️ 预估总时长: {estimated_duration:.1f}秒 ({estimated_duration / 60:.1f}分钟)")
            logger.info(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.info(f"🔍 内存管理器实例ID: {id(self)}")
            return task_state

    def create_task_sync(
        self,
        task_id: str,
        user_id: str,
        stock_code: str,
        status: TaskStatus = TaskStatus.PENDING,
        parameters: dict[str, Any] | None = None,
        stock_name: str | None = None,
    ) -> TaskState:
        """创建新任务（同步版本，用于在线程池中调用）

        Args:
            task_id: 任务ID
            user_id: 用户ID
            stock_code: 股票代码
            status: 初始状态（默认 PENDING）
            parameters: 分析参数
            stock_name: 股票名称

        Returns:
            创建的 TaskState 实例
        """
        with self._lock:
            task_state = TaskState(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                stock_name=stock_name,
                status=status,
                start_time=datetime.now(),
                parameters=parameters or {},
                estimated_duration=max(600.0, self._calculate_estimated_duration(parameters or {})),
                message="任务已创建，等待执行...",
            )
            self._tasks[task_id] = task_state
            logger.info(f"📝 [同步] 创建任务状态: {task_id}")
            return task_state

    def get_status_sync(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态（同步版本，用于非异步上下文）

        与 get_task_dict（async）功能相同，但为同步方法，
        可直接在非事件循环上下文中调用（如线程池、进度回调）。

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典，任务不存在时返回 None
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return task.to_dict()

    def get_user_task_status_sync(self, user_id: str) -> dict[str, Any]:
        """同步获取用户所有任务状态（按用户 ID 查询，供线程池同步代码使用）

        与 list_user_tasks（async）功能相同，但为同步方法。
        返回格式为 {task_id: task_dict}，方便调用方提取 task_id 列表。

        Args:
            user_id: 用户ID

        Returns:
            任务状态字典，格式为 {task_id: task_dict}
        """
        with self._lock:
            result = {}
            for task_id, task in self._tasks.items():
                if task.user_id == user_id:
                    result[task_id] = task.to_dict()
            return result

    def update_progress_sync(self, task_id: str, progress: int, message: str, current_step: str | None = None) -> bool:
        """同步更新任务进度（线程安全），供 _run_async_update_safe 在线程池中调用

        Args:
            task_id: 任务ID
            progress: 进度百分比（0-100）
            message: 进度消息
            current_step: 当前步骤名称（可选）

        Returns:
            是否更新成功
        """
        with self._lock:
            if task_id not in self._tasks:
                # 不打印 warning，此方法是辅助性的，调用方已处理错误
                return False
            task = self._tasks[task_id]
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if current_step is not None:
                task.current_step = current_step
            return True

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        message: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        result_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新任务状态（async 版本，兼容现有 await 调用）

        此方法为 async 方法，生产代码中使用 await 调用。
        内部使用 threading.Lock 保证线程安全。

        Args:
            task_id: 任务ID
            status: 新状态
            message: 状态消息
            progress: 进度百分比（0-100）
            current_step: 当前步骤名称
            result_data: 结果数据
            error_message: 错误消息

        Returns:
            是否更新成功
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"⚠️ 任务不存在: {task_id}")
                return False

            task = self._tasks[task_id]
            task.status = status

            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if current_step is not None:
                task.current_step = current_step
            if result_data is not None:
                task.result_data = result_data
            if error_message is not None:
                task.error_message = error_message

            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.end_time = datetime.now()
                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()

            logger.info(f"📊 更新任务状态: {task_id} -> {status.value} ({progress}%)")

            # WebSocket 推送（如果可用）
            if self._websocket_manager:
                try:
                    progress_update = {
                        "type": "progress_update",
                        "task_id": task_id,
                        "status": status.value,
                        "progress": task.progress,
                        "message": task.message,
                        "current_step": task.current_step,
                        "timestamp": datetime.now().isoformat(),
                    }
                    asyncio.create_task(self._websocket_manager.send_progress_update(task_id, progress_update))
                except Exception as e:
                    logger.warning(f"⚠️ WebSocket 推送失败: {e}")

            return True

    def _calculate_estimated_duration(self, parameters: dict[str, Any]) -> float:
        """根据分析参数计算预估总时长（秒）"""
        # 基础时间（秒）- 环境准备、配置等
        base_time = 60

        # 获取分析参数
        research_depth = parameters.get("research_depth", "标准")
        selected_analysts = parameters.get("selected_analysts", [])
        from tradingagents.llm_clients.provider_keys import normalize_provider_key

        llm_provider = normalize_provider_key(parameters.get("llm_provider", "dashscope"))

        # 研究深度映射
        depth_map = {"快速": 1, "标准": 2, "深度": 3}
        d = depth_map.get(research_depth, 2)

        # 每个分析师的基础耗时（基于真实测试数据）
        analyst_base_time = {
            1: 180,  # 快速分析：每个分析师约3分钟
            2: 360,  # 标准分析：每个分析师约6分钟
            3: 600,  # 深度分析：每个分析师约10分钟
        }.get(d, 360)

        analyst_time = len(selected_analysts) * analyst_base_time

        # 模型速度影响（基于实际测试）
        model_multiplier = {
            "qwen": 1.0,  # 阿里百炼（通义千问）速度适中
            "dashscope": 1.0,  # 阿里百炼速度适中
            "deepseek": 0.7,  # DeepSeek较快
            "google": 1.3,  # Google较慢
        }.get(llm_provider, 1.0)

        # 研究深度额外影响（工具调用复杂度）
        depth_multiplier = {
            1: 0.8,  # 快速分析，较少工具调用
            2: 1.0,  # 标准分析，标准工具调用
            3: 1.3,  # 深度分析，更多工具调用和推理
        }.get(d, 1.0)

        total_time = (base_time + analyst_time) * model_multiplier * depth_multiplier
        return total_time

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int | None = None,
        message: str | None = None,
        current_step: str | None = None,
        result_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新任务状态"""
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"⚠️ 任务不存在: {task_id}")
                return False

            task = self._tasks[task_id]
            task.status = status

            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if current_step is not None:
                task.current_step = current_step
            if result_data is not None:
                # 🔍 调试：检查保存到内存的result_data
                logger.info(f"🔍 [MEMORY] 保存result_data到内存: {task_id}")
                logger.info(f"🔍 [MEMORY] result_data键: {list(result_data.keys()) if result_data else '无'}")
                logger.info(
                    f"🔍 [MEMORY] result_data中有decision: {bool(result_data.get('decision')) if result_data else False}",
                )
                if result_data and result_data.get("decision"):
                    logger.info(f"🔍 [MEMORY] decision内容: {result_data['decision']}")

                task.result_data = result_data
            if error_message is not None:
                task.error_message = error_message

            # 如果任务完成或失败，设置结束时间
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.end_time = datetime.now()
                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()

            logger.info(f"📊 更新任务状态: {task_id} -> {status.value} ({progress}%)")

            # 推送状态更新到 WebSocket
            if self._websocket_manager:
                try:
                    progress_update = {
                        "type": "progress_update",
                        "task_id": task_id,
                        "status": status.value,
                        "progress": task.progress,
                        "message": task.message,
                        "current_step": task.current_step,
                        "timestamp": datetime.now().isoformat(),
                    }
                    # 异步推送，不等待完成
                    asyncio.create_task(self._websocket_manager.send_progress_update(task_id, progress_update))
                except Exception as e:
                    logger.warning(f"⚠️ WebSocket 推送失败: {e}")

            return True

    async def get_task(self, task_id: str) -> TaskState | None:
        """获取任务状态"""
        with self._lock:
            logger.debug(f"🔍 查询任务: {task_id}")
            logger.debug(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.debug(f"🔑 内存中的任务ID列表: {list(self._tasks.keys())}")
            task = self._tasks.get(task_id)
            if task:
                logger.debug(f"✅ 找到任务: {task_id}")
            else:
                logger.debug(f"❌ 未找到任务: {task_id}")
            return task

    async def get_task_dict(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态（字典格式）"""
        task = await self.get_task(task_id)
        return task.to_dict() if task else None

    async def list_all_tasks(
        self, status: TaskStatus | None = None, limit: int = 20, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """获取所有任务列表（不限用户）"""
        with self._lock:
            tasks = []
            for task in self._tasks.values():
                if status is None or task.status == status:
                    item = task.to_dict()
                    # 兼容前端字段
                    if "stock_name" not in item or not item.get("stock_name"):
                        item["stock_name"] = None
                    tasks.append(item)

            # 按开始时间倒序排列
            tasks.sort(key=lambda x: x.get("start_time", ""), reverse=True)

            # 分页
            return tasks[offset : offset + limit]

    async def list_user_tasks(
        self, user_id: str, status: TaskStatus | None = None, limit: int = 20, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """获取用户的任务列表"""
        with self._lock:
            tasks = []
            for task in self._tasks.values():
                if task.user_id == user_id and (status is None or task.status == status):
                    item = task.to_dict()
                    # 兼容前端字段
                    if "stock_name" not in item or not item.get("stock_name"):
                        item["stock_name"] = None
                    tasks.append(item)

            # 按开始时间倒序排列
            tasks.sort(key=lambda x: x.get("start_time", ""), reverse=True)

            # 分页
            return tasks[offset : offset + limit]

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️ 删除任务: {task_id}")
                return True
            return False

    async def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            total_tasks = len(self._tasks)
            status_counts = {}

            for task in self._tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_tasks": total_tasks,
                "status_distribution": status_counts,
                "running_tasks": status_counts.get("running", 0),
                "completed_tasks": status_counts.get("completed", 0),
                "failed_tasks": status_counts.get("failed", 0),
            }

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """清理旧任务"""
        with self._lock:
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            tasks_to_remove = []

            for task_id, task in self._tasks.items():
                if task.start_time and task.start_time.timestamp() < cutoff_time:
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self._tasks[task_id]

            logger.info(f"🧹 清理了 {len(tasks_to_remove)} 个旧任务")
            return len(tasks_to_remove)

    async def cleanup_zombie_tasks(self, max_running_hours: int = 2) -> int:
        """清理僵尸任务（长时间处于 running 状态的任务）

        Args:
            max_running_hours: 最大运行时长（小时），超过此时长的 running 任务将被标记为失败

        Returns:
            清理的任务数量
        """
        with self._lock:
            cutoff_time = datetime.now().timestamp() - (max_running_hours * 3600)
            zombie_tasks = []

            for task_id, task in self._tasks.items():
                # 检查是否是长时间运行的任务
                if task.status in [TaskStatus.RUNNING, TaskStatus.PENDING]:
                    if task.start_time and task.start_time.timestamp() < cutoff_time:
                        zombie_tasks.append(task_id)

            # 将僵尸任务标记为失败
            for task_id in zombie_tasks:
                task = self._tasks[task_id]
                task.status = TaskStatus.FAILED
                task.end_time = datetime.now()
                task.error_message = f"任务超时（运行时间超过 {max_running_hours} 小时）"
                task.message = "任务已超时，自动标记为失败"
                task.progress = 0

                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()

                logger.warning(f"⚠️ 僵尸任务已标记为失败: {task_id} (运行时间: {task.execution_time:.1f}秒)")

            if zombie_tasks:
                logger.info(f"🧹 清理了 {len(zombie_tasks)} 个僵尸任务")

            return len(zombie_tasks)

    async def remove_task(self, task_id: str) -> bool:
        """从内存中删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功删除
        """
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️ 任务已从内存中删除: {task_id}")
                return True
            logger.warning(f"⚠️ 任务不存在于内存中: {task_id}")
            return False


# 全局实例
_memory_state_manager = None


def get_memory_state_manager() -> MemoryStateManager:
    """获取内存状态管理器实例"""
    global _memory_state_manager
    if _memory_state_manager is None:
        _memory_state_manager = MemoryStateManager()
    return _memory_state_manager
