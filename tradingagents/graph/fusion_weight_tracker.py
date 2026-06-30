"""
Fusion Weight Tracker — 动态权重校准模块

追踪每个融合模块（Trader / Diffusion / AIF）的历史决策准确率，
在运行时动态校准 BMA（贝叶斯模型平均）的融合权重。

核心算法:
  权重 = softmax(历史准确率^2)
  - 准确率高的模块获得指数级更高的权重
  - 冷启动时各模块权重相等 (1/N)
  - 准确率在每次分析完成后更新

Usage:
    from tradingagents.graph.fusion_weight_tracker import fusion_tracker
    
    # 在 fusion_node 中获取动态权重
    weights = fusion_tracker.get_weights()
    
    # 在分析完成后记录决策结果
    fusion_tracker.record_decision("trader", action="sell", actual_return=-0.05)
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

# 持久化路径 — 保存在项目 data 目录下
_TRACKER_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TRACKER_FILE = _TRACKER_DATA_DIR / "fusion_weight_history.json"


class FusionWeightTracker:
    """
    融合权重追踪器 — 基于历史准确率的动态 BMA 权重分配
    
    维护一个持久化的模块准确率历史，支持：
    - 冷启动等权重
    - 准确率指数加权 (softmax(a^2))
    - JSON 文件持久化（跨重启保留）
    - 最近 N 次滑动窗口（避免远古数据影响）
    """

    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self._modules = ["trader", "diffusion", "aif"]
        self._history: dict[str, list[bool]] = {}
        self._load()

    # ─── 公开 API ───────────────────────────────────────

    def get_weights(self) -> dict[str, float]:
        """
        返回当前动态权重字典。
        
        算法:
        1. 每个模块 = 最近 window_size 次决策的正确率
        2. 权重 = softmax(正确率^2)
        3. 冷启动时返回均匀权重 {trader: 1/3, diffusion: 1/3, aif: 1/3}
        
        Returns:
            {"trader": 0.5, "diffusion": 0.3, "aif": 0.2}
        """
        accuracies = []
        for m in self._modules:
            history = self._history.get(m, [])
            if not history:
                # 冷启动: 用 0.5 中性值
                accuracies.append(0.5)
            else:
                recent = history[-self.window_size:]
                acc = sum(recent) / len(recent) if recent else 0.5
                accuracies.append(acc)

        # softmax(a^2)
        squared = [a * a for a in accuracies]
        total = sum(squared)
        if total == 0:
            weights = {m: 1.0 / len(self._modules) for m in self._modules}
        else:
            weights = {}
            for i, m in enumerate(self._modules):
                weights[m] = squared[i] / total

        return weights

    def record_decision(
        self,
        module_name: str,
        action: str,
        actual_return: Optional[float] = None,
        is_correct: Optional[bool] = None,
    ) -> None:
        """
        记录一次模块决策的结果，用于后续权重校准。

        Args:
            module_name: 模块名称 (trader / diffusion / aif)
            action: 决策动作 (buy / sell / hold)
            actual_return: 事后实际收益率 (如 -0.05 表示跌 5%)
            is_correct: 直接指定是否正确 (None 时由 actual_return 推断)
        """
        if module_name not in self._modules:
            return

        if is_correct is None and actual_return is not None:
            # 简单的正确性推断：
            # - buy → actual_return > 0 为正确
            # - sell → actual_return < 0 为正确
            # - hold → |actual_return| < 0.02 为正确（窄区间）
            if action == "buy":
                is_correct = actual_return > 0
            elif action == "sell":
                is_correct = actual_return < 0
            else:  # hold
                is_correct = abs(actual_return) < 0.02

        if is_correct is None:
            return

        if module_name not in self._history:
            self._history[module_name] = []
        self._history[module_name].append(is_correct)

        # 限制窗口大小
        if len(self._history[module_name]) > self.window_size * 2:
            self._history[module_name] = self._history[module_name][-self.window_size:]

        self._save()

    def get_accuracy(self, module_name: str) -> float:
        """返回指定模块的当前准确率 (0-1)。"""
        history = self._history.get(module_name, [])
        if not history:
            return 0.5
        recent = history[-self.window_size:]
        return sum(recent) / len(recent)

    def reset(self) -> None:
        """重置所有历史记录。"""
        self._history = {}
        self._save()

    # ─── 持久化 ────────────────────────────────────────

    def _load(self) -> None:
        """从 JSON 文件加载历史。"""
        try:
            if _TRACKER_FILE.exists():
                data = json.loads(_TRACKER_FILE.read_text(encoding="utf-8"))
                raw = data.get("history", {})
                # 反序列化: list[bool] 从 JSON list[int]
                self._history = {}
                for mod, arr in raw.items():
                    self._history[mod] = [bool(v) for v in arr]
        except (json.JSONDecodeError, OSError):
            self._history = {}

    def _save(self) -> None:
        """保存历史到 JSON 文件。"""
        try:
            _TRACKER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 2,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "history": {
                    mod: arr
                    for mod, arr in self._history.items()
                },
            }
            _TRACKER_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 持久化失败不影响核心功能


# ─── 全局单例 ──────────────────────────────────────────
fusion_tracker = FusionWeightTracker(window_size=20)
