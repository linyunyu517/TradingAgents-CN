# TradingAgents/hpc_loop/global_workspace.py
"""
全局工作空间 (Global Workspace)

实现 Baars-Dehaene 全局工作空间理论 (Global Workspace Theory, GWT)。
多个并行的无意识处理器 (Agent) 竞争进入全局工作空间，
只有超过显著性阈值的信息被广播到所有下游模块。

理论基础:
    - Baars Global Workspace Theory (1988, 2005)
    - Dehaene Global Neuronal Workspace (2017)
    - 选择性注意与信息瓶颈
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from .hpc_config import HPCLoopConfig


@dataclass
class ConsciousContent:
    """
    进入全局工作空间的"意识内容"

    每个内容来自一个 Agent 的分析结果，
    包含显著性分数、置信度和原始分析文本。
    """

    agent_id: str
    """源 Agent 标识符"""

    content: str
    """分析结果文本"""

    confidence: float
    """置信度 (0-1)"""

    saliency_score: float
    """显著性得分"""

    novelty: float
    """新颖性 (与当前信念的 KL 散度)"""

    impact: float
    """对决策的预期影响"""

    urgency: float
    """时间紧迫性"""

    timestamp: str = ""
    """生成时间"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """附加元数据"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "content": self.content[:200] + "..." if len(self.content) > 200 else self.content,
            "confidence": self.confidence,
            "saliency_score": self.saliency_score,
            "novelty": self.novelty,
            "impact": self.impact,
            "urgency": self.urgency,
            "timestamp": self.timestamp,
        }


@dataclass
class WorkspaceState:
    """
    全局工作空间状态

    包含当前工作空间中的所有意识内容，
    以及广播历史和工作空间动态统计。
    """

    contents: list[ConsciousContent] = field(default_factory=list)
    """当前工作空间内容列表 (按显著性排序, 最多 capacity 个)"""

    broadcast_history: list[list[ConsciousContent]] = field(default_factory=list)
    """广播历史 (每次广播的快照)"""

    total_submissions: int = 0
    """总提交次数"""

    total_broadcasts: int = 0
    """总广播次数"""

    avg_saliency: float = 0.0
    """平均显著性"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contents": [c.to_dict() for c in self.contents],
            "total_submissions": self.total_submissions,
            "total_broadcasts": self.total_broadcasts,
            "avg_saliency": self.avg_saliency,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkspaceState":
        """从字典重建"""
        contents = []
        for c in d.get("contents", []):
            if isinstance(c, dict):
                contents.append(
                    ConsciousContent(
                        agent_id=c.get("agent_id", ""),
                        content=c.get("content", ""),
                        confidence=c.get("confidence", 0.0),
                        saliency_score=c.get("saliency_score", 0.0),
                        novelty=c.get("novelty", 0.0),
                        impact=c.get("impact", 0.0),
                        urgency=c.get("urgency", 0.0),
                        timestamp=c.get("timestamp", ""),
                    ),
                )
        return cls(
            contents=contents,
            total_submissions=d.get("total_submissions", 0),
            total_broadcasts=d.get("total_broadcasts", 0),
            avg_saliency=d.get("avg_saliency", 0.0),
        )


class GlobalWorkspace:
    # 类级别引用，支持通过 gws.__class__.WorkspaceState 访问
    WorkspaceState = WorkspaceState
    """
    全局工作空间

    核心功能:
    1. 接收多个并行 Agent 的输出
    2. 使用注意力竞争机制计算显著性得分
    3. 只有超过阈值的 Agent 输出被广播到全局工作空间
    4. 工作空间内容成为决策模块的输入

    使用流程:
        gws = GlobalWorkspace(capacity=4)
        gws.submit_agent_output("market_analyst", "看涨信号...", confidence=0.85)
        gws.submit_agent_output("news_analyst", "负面新闻...", confidence=0.72)
        broadcast = gws.broadcast()  # 返回竞争胜出的内容
        workspace_state = gws.get_workspace_state()
    """

    def __init__(self, config: HPCLoopConfig | None = None):
        self.config = config or HPCLoopConfig()

        # 工作空间容量 (来自 GWT 理论的 4±1 chunks)
        self._capacity = self.config.gws_capacity

        # 显著性阈值
        self._saliency_threshold = self.config.gws_saliency_threshold

        # 内部状态
        self._state = WorkspaceState()

        # 待处理的 Agent 输出队列
        self._pending_submissions: list[ConsciousContent] = []

        # 显著性权重配置
        self._weights = {
            "novelty": self.config.gws_novelty_weight,
            "confidence": self.config.gws_confidence_weight,
            "impact": self.config.gws_impact_weight,
            "urgency": self.config.gws_urgency_weight,
        }

    def submit_agent_output(
        self,
        agent_id: str,
        analysis_result: str,
        confidence: float,
        novelty: float | None = None,
        impact: float | None = None,
        urgency: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        接收 Agent 提交的分析结果

        Args:
            agent_id: Agent 标识符 (如 "market_analyst")
            analysis_result: 分析结果文本
            confidence: 置信度 (0-1)
            novelty: 新颖性得分 (若为None则自动计算)
            impact: 影响力得分 (若为None则自动估算)
            urgency: 时间紧迫性 (若为None则自动估算)
            metadata: 附加元数据
        """
        # 自动计算未提供的显著性分量
        if novelty is None:
            novelty = self._estimate_novelty(analysis_result)
        if impact is None:
            impact = self._estimate_impact(analysis_result)
        if urgency is None:
            urgency = self._estimate_urgency(analysis_result)

        # 计算显著性得分
        saliency = self.compute_saliency(
            {
                "novelty": novelty,
                "confidence": confidence,
                "impact": impact,
                "urgency": urgency,
            },
        )

        content = ConsciousContent(
            agent_id=agent_id,
            content=analysis_result,
            confidence=confidence,
            saliency_score=saliency,
            novelty=novelty,
            impact=impact,
            urgency=urgency,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )

        self._pending_submissions.append(content)
        self._state.total_submissions += 1

    def compute_saliency(
        self,
        agent_output: dict[str, float],
    ) -> float:
        """
        计算显著性得分

        显著性 = f(novelty, confidence, impact, urgency)
             = w_n * novelty + w_c * confidence + w_i * impact + w_u * urgency

        Args:
            agent_output: 包含 novelty, confidence, impact, urgency 的字典

        Returns:
            float: 显著性得分 (0-1)
        """
        novelty = agent_output.get("novelty", 0.0)
        confidence = agent_output.get("confidence", 0.0)
        impact = agent_output.get("impact", 0.0)
        urgency = agent_output.get("urgency", 0.0)

        saliency = (
            self._weights["novelty"] * max(0, min(1, novelty))
            + self._weights["confidence"] * max(0, min(1, confidence))
            + self._weights["impact"] * max(0, min(1, impact))
            + self._weights["urgency"] * max(0, min(1, urgency))
        )

        return max(0, min(1, saliency))

    def broadcast(self) -> list[ConsciousContent]:
        """
        广播：竞争胜出的内容进入全局工作空间

        处理流程:
        1. 合并待处理内容和当前工作空间内容
        2. 按显著性排序
        3. 筛选超过阈值的内容
        4. 保留容量限制内的 top-k 内容
        5. 记录广播历史

        Returns:
            List[ConsciousContent]: 进入工作空间的内容列表 (按显著性降序)
        """
        # 合并待处理内容和当前内容
        all_contents = self._pending_submissions + self._state.contents
        self._pending_submissions.clear()

        if not all_contents:
            return []

        # 按显著性降序排序
        all_contents.sort(key=lambda c: c.saliency_score, reverse=True)

        # 筛选超过阈值的内容
        selected = [c for c in all_contents if c.saliency_score >= self._saliency_threshold]

        # 容量限制
        selected = selected[: self._capacity]

        # 更新工作空间状态
        self._state.contents = selected
        self._state.total_broadcasts += 1

        if selected:
            self._state.avg_saliency = 0.9 * self._state.avg_saliency + 0.1 * np.mean(
                [c.saliency_score for c in selected],
            )

        # 记录广播历史
        self._state.broadcast_history.append(selected)

        return selected

    def get_state(self) -> WorkspaceState:
        """获取当前工作空间状态"""
        return self._state

    def get_workspace_state(self) -> WorkspaceState:
        """获取当前工作空间状态 (别名)"""
        return self._state

    def get_broadcast_summary(self) -> str:
        """
        获取广播摘要文本 (用于整合到 LLM Prompt 中)

        Returns:
            str: 格式化的广播摘要
        """
        contents = self._state.contents
        if not contents:
            return "[全局工作空间: 无内容]"

        summary_parts = [f"━━━ 全局工作空间广播 (容量 {self._capacity}) ━━━"]

        for i, content in enumerate(contents, 1):
            summary_parts.append(
                f"\n[{i}] Agent: {content.agent_id} "
                f"(显著性: {content.saliency_score:.2f}, "
                f"置信度: {content.confidence:.2f})",
            )
            summary_parts.append(f"    {content.content[:250]}")

        summary_parts.append(f"\n━━━ 共 {len(contents)} 个内容项 ━━━")
        return "\n".join(summary_parts)

    def compute_novelty_vs_belief(
        self,
        content: str,
        current_belief: dict[str, Any],
    ) -> float:
        """
        计算内容相对于当前信念的新颖性

        使用近似 KL 散度或文本嵌入相似度估计。
        目前使用基于内容长度的简单启发式方法。

        Args:
            content: 分析内容
            current_belief: 当前信念状态

        Returns:
            float: 新颖性得分 (0-1)
        """
        if not current_belief:
            return 0.5  # 没有先验信念时，默认为中等新颖

        # 计算内容中独特关键词的比例作为新颖性代理
        # 在实际应用中，应使用嵌入向量相似度
        content_words = set(content.lower().split())
        belief_text = str(current_belief)
        belief_words = set(belief_text.lower().split())

        if not content_words:
            return 0.0

        # 不在信念中的词的比例
        novel_words = content_words - belief_words
        novelty_ratio = len(novel_words) / max(len(content_words), 1)

        return min(1.0, novelty_ratio * 2)  # 放大

    def reset(self) -> None:
        """重置全局工作空间"""
        self._state = WorkspaceState()
        self._pending_submissions.clear()

    # ==================== 内部估算方法 ====================

    def _estimate_novelty(self, content: str) -> float:
        """基于内容特征的启发式新颖性估算"""
        # 含有特定关键词表示可能有新颖信息
        novelty_keywords = [
            "突发",
            "意外",
            "首次",
            "突破",
            "创新高",
            "创新低",
            "surprise",
            "unexpected",
            "breakthrough",
            "record",
            "首次",
            "前所未有",
            "突然",
            "罕见",
        ]
        content_lower = content.lower()
        matches = sum(1 for kw in novelty_keywords if kw.lower() in content_lower)
        return min(1.0, matches * 0.15 + 0.1)

    def _estimate_impact(self, content: str) -> float:
        """基于内容特征的启发式影响力估算"""
        impact_keywords = [
            "重大",
            "关键",
            "决定性",
            "显著",
            "大幅",
            "重要",
            "major",
            "critical",
            "decisive",
            "significant",
            "涨停",
            "跌停",
            "崩盘",
            "暴涨",
            "暴跌",
        ]
        content_lower = content.lower()
        matches = sum(1 for kw in impact_keywords if kw.lower() in content_lower)
        return min(1.0, matches * 0.12 + 0.1)

    def _estimate_urgency(self, content: str) -> float:
        """基于内容特征的启发式紧迫性估算"""
        urgency_keywords = [
            "立即",
            "紧急",
            "马上",
            "即将",
            "迫在眉睫",
            "urgent",
            "immediate",
            "deadline",
            "now",
            "今晚",
            "今天",
            "明日",
            "盘前",
            "盘后",
        ]
        content_lower = content.lower()
        matches = sum(1 for kw in urgency_keywords if kw.lower() in content_lower)
        return min(1.0, matches * 0.15 + 0.05)
