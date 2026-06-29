"""
WebSocket 连接管理器
用于实时推送分析进度更新
"""

import asyncio
import json
import logging
import threading
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 存储活跃连接：{task_id: {websocket1, websocket2, ...}}
        self.active_connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, task_id: str):
        """建立 WebSocket 连接"""
        await websocket.accept()

        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = set()
            self.active_connections[task_id].add(websocket)

        logger.info(f"🔌 WebSocket 连接建立: {task_id}")

    async def disconnect(self, websocket: WebSocket, task_id: str):
        """断开 WebSocket 连接"""
        async with self._lock:
            if task_id in self.active_connections:
                self.active_connections[task_id].discard(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]

        logger.info(f"🔌 WebSocket 连接断开: {task_id}")

    async def send_progress_update(self, task_id: str, message: dict[str, Any]):
        """发送进度更新到指定任务的所有连接"""
        if task_id not in self.active_connections:
            return

        # 复制连接集合以避免在迭代时修改
        connections = self.active_connections[task_id].copy()

        for connection in connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"⚠️ 发送 WebSocket 消息失败: {e}")
                # 移除失效的连接
                async with self._lock:
                    if task_id in self.active_connections:
                        self.active_connections[task_id].discard(connection)

    async def send_ping(self, websocket: WebSocket) -> bool:
        """发送心跳 ping 消息，返回是否成功"""
        try:
            await websocket.send_text(json.dumps({"type": "ping"}))
            return True
        except Exception:
            return False

    async def broadcast_to_user(self, user_id: str, message: dict[str, Any]):
        """向用户的所有连接广播消息"""
        # 这里可以扩展为按用户ID管理连接
        # 目前简化实现，只按任务ID管理

    async def get_connection_count(self, task_id: str) -> int:
        """获取指定任务的连接数"""
        async with self._lock:
            return len(self.active_connections.get(task_id, set()))

    async def get_total_connections(self) -> int:
        """获取总连接数"""
        async with self._lock:
            total = 0
            for connections in self.active_connections.values():
                total += len(connections)
            return total


# 全局实例
_websocket_manager = None
_websocket_manager_lock = threading.Lock()


def get_websocket_manager() -> WebSocketManager:
    """获取 WebSocket 管理器实例（双检锁单例）"""
    global _websocket_manager
    if _websocket_manager is None:
        with _websocket_manager_lock:
            if _websocket_manager is None:
                _websocket_manager = WebSocketManager()
    return _websocket_manager
