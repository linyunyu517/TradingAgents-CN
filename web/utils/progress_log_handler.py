"""
进度日志处理器
将日志系统中的模块完成消息转发给进度跟踪器
"""


import logging
import threading

from .async_progress_tracker import AsyncProgressTracker


class ProgressLogHandler(logging.Handler):
    """
    自定义日志处理器，将模块开始/完成消息转发给进度跟踪器
    """

    # 类级别的跟踪器注册表
    _trackers: dict[str, "AsyncProgressTracker"] = {}
    _lock = threading.Lock()

    @classmethod
    def register_tracker(cls, analysis_id: str, tracker):
        """注册进度跟踪器"""
        try:
            with cls._lock:
                cls._trackers[analysis_id] = tracker
            # 在锁外面打印，避免死锁
            print(f"📊 [进度集成] 注册跟踪器: {analysis_id}")
        except Exception as e:
            print(f"❌ [进度集成] 注册跟踪器失败: {e}")

    @classmethod
    def unregister_tracker(cls, analysis_id: str):
        """注销进度跟踪器"""
        try:
            removed = False
            with cls._lock:
                if analysis_id in cls._trackers:
                    del cls._trackers[analysis_id]
                    removed = True
            # 在锁外面打印，避免死锁
            if removed:
                print(f"📊 [进度集成] 注销跟踪器: {analysis_id}")
        except Exception as e:
            print(f"❌ [进度集成] 注销跟踪器失败: {e}")

    def emit(self, record):
        """处理日志记录"""
        try:
            message = record.getMessage()

            # 只处理模块开始和完成的消息
            if "[模块开始]" in message or "[模块完成]" in message:
                # 尝试从消息中提取股票代码来匹配分析
                stock_symbol = self._extract_stock_symbol(message)

                # 查找匹配的跟踪器（减少锁持有时间）
                trackers_copy = {}
                with self._lock:
                    trackers_copy = self._trackers.copy()

                # 在锁外面处理跟踪器更新
                for analysis_id, tracker in trackers_copy.items():
                    # 简单匹配：如果跟踪器存在且状态为running，就更新
                    if hasattr(tracker, "progress_data") and tracker.progress_data.get("status") == "running":
                        try:
                            tracker.update_progress(message)
                            print(f"📊 [进度集成] 转发消息到 {analysis_id}: {message[:50]}...")
                            break  # 只更新第一个匹配的跟踪器
                        except Exception as e:
                            print(f"❌ [进度集成] 更新失败: {e}")

        except Exception as e:
            # 不要让日志处理器的错误影响主程序
            print(f"❌ [进度集成] 日志处理错误: {e}")

    def _extract_stock_symbol(self, message: str) -> str | None:
        """从消息中提取股票代码"""
        import re

        # 尝试匹配 "股票: XXXXX" 格式
        match = re.search(r"股票:\s*([A-Za-z0-9]+)", message)
        if match:
            return match.group(1)

        return None

# 全局日志处理器实例
_progress_handler = None

def setup_progress_log_integration():
    """设置进度日志集成"""
    global _progress_handler

    if _progress_handler is None:
        _progress_handler = ProgressLogHandler()
        _progress_handler.setLevel(logging.INFO)

        # 添加到tools日志器（模块完成消息来自这里）
        tools_logger = logging.getLogger("tools")
        tools_logger.addHandler(_progress_handler)

        print("✅ [进度集成] 日志处理器已设置")

    return _progress_handler

def register_analysis_tracker(analysis_id: str, tracker):
    """注册分析跟踪器"""
    handler = setup_progress_log_integration()
    ProgressLogHandler.register_tracker(analysis_id, tracker)

def unregister_analysis_tracker(analysis_id: str):
    """注销分析跟踪器"""
    ProgressLogHandler.unregister_tracker(analysis_id)
