# TradingAgents/hpc_loop/complementary_memory.py
"""
互补学习记忆系统 (Complementary Learning Memory)

实现 McClelland 互补学习系统理论 (Complementary Learning Systems, CLS)。
分离快速情景记忆 (海马体/Hippocampus) 和慢速语义记忆 (新皮层/Neocortex)。

理论基础:
    - McClelland et al. (1995) 互补学习系统
    - 海马体: 快速编码、模式分离、episodic memory
    - 新皮层: 慢速学习、结构化知识、语义记忆
    - 睡眠回放机制 (replay) 和记忆巩固 (consolidation)
"""

import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np


@dataclass
class TradingEpisode:
    """
    交易事件 — 海马体 (快通道) 的基本存储单元

    包含完整交易情景: 上下文 → 决策 → 结果
    """

    episode_id: str = ""
    """事件唯一标识"""

    timestamp: str = ""
    """事件时间戳"""

    ticker: str = ""
    """股票代码"""

    market_context: dict[str, Any] = field(default_factory=dict)
    """市场上下文 (价格、波动率、情绪等)"""

    action: str = ""
    """执行行动 (买入/卖出/持有)"""

    decision_rationale: str = ""
    """决策理由"""

    outcome: float | None = None
    """交易结果 (收益率)"""

    confidence: float = 0.0
    """决策时的置信度"""

    prediction_error: float = 0.0
    """决策后的预测误差"""

    saliency_score: float = 0.0
    """事件显著性 (用于巩固筛选)"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """附加元数据"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "action": self.action,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "saliency_score": self.saliency_score,
        }


@dataclass
class MemoryTrace:
    """
    快慢通道联合检索结果

    包含来自海马体的情景记忆和来自新皮层的语义知识。
    """

    episodic_memories: list[TradingEpisode]
    """海马体检索到的情景记忆"""

    semantic_knowledge: list[dict[str, Any]]
    """新皮层检索到的语义知识"""

    integrated_summary: str = ""
    """整合后的记忆摘要"""

    retrieval_time: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_episodic": len(self.episodic_memories),
            "num_semantic": len(self.semantic_knowledge),
            "integrated_summary": self.integrated_summary[:200] + "..."
            if len(self.integrated_summary) > 200
            else self.integrated_summary,
            "retrieval_time": self.retrieval_time,
        }


@dataclass
class MarketRegime:
    """
    市场体制 (新皮层慢速学习提取的统计规律)
    """

    regime_type: str
    """体制类型"""

    characteristics: dict[str, float]
    """体制特征"""

    transition_probability: dict[str, float]
    """转移到其他体制的概率"""

    typical_outcomes: dict[str, float]
    """典型交易结果统计"""

    confidence: float = 0.0
    """对该体制识别的置信度"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_type": self.regime_type,
            "characteristics": self.characteristics,
            "transition_probability": self.transition_probability,
            "confidence": self.confidence,
        }


class ComplementaryLearningMemory:
    """
    互补学习记忆系统

    快通道 (海马体 / Hippocampus):
    - 存储最近的交易事件和市场模式
    - 快速学习和模式分离
    - 有限容量滑动窗口

    慢通道 (新皮层 / Neocortex):
    - 通过回放和巩固提取长期统计知识
    - 结构化知识图表示
    - 防止灾难性遗忘

    使用流程:
        memory = ComplementaryLearningMemory()
        memory.store_episode(episode)
        similar = memory.retrieve_similar(query, k=5)
        memory.consolidate()
    """

    def __init__(self, config=None):
        from .hpc_config import HPCLoopConfig

        self.config = config or HPCLoopConfig()

        # ==================== 快通道: 海马体 ====================
        self._hippocampus: deque = deque(maxlen=self.config.memory_hippocampus_max_episodes)
        """海马体存储 (按时间顺序, 循环缓冲区)"""

        self._hippocampus_index: dict[str, list[int]] = defaultdict(list)
        """海马体快速索引 {ticker: [位置]}"""

        # ==================== 慢通道: 新皮层 ====================
        self._neocortex_knowledge: dict[str, dict[str, Any]] = {}
        """新皮层知识库 {概念: {特征: 值}}"""

        self._neocortex_graph: dict[str, set[str]] = defaultdict(set)
        """新皮层知识图 {概念: {相关概念}}"""

        self._market_regimes: dict[str, MarketRegime] = {}
        """已识别的市场体制"""

        # ==================== 统计与状态 ====================
        self._action_outcomes: dict[str, list[float]] = defaultdict(list)
        """各行动的历史结果"""

        self._regime_transition_counts: dict[tuple[str, str], int] = defaultdict(int)
        """体制转移计数"""

        self._last_consolidation_time: datetime | None = None
        """上次巩固时间"""

        self._consolidation_count: int = 0
        """巩固次数"""

        self._episode_counter: int = 0
        """事件计数器"""

    # ==================== 快通道: 事件存储 ====================

    def store_episode(self, episode: TradingEpisode) -> None:
        """
        存储交易事件到快通道 (海马体)

        Args:
            episode: 交易事件
        """
        # 生成事件ID (如未提供)
        if not episode.episode_id:
            self._episode_counter += 1
            episode.episode_id = f"ep_{self._episode_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if not episode.timestamp:
            episode.timestamp = datetime.now().isoformat()

        # 计算显著性得分 (如未提供)
        if episode.saliency_score == 0.0:
            episode.saliency_score = self._compute_saliency(episode)

        # 存储到海马体
        self._hippocampus.append(episode)

        # 更新索引
        ticker = episode.ticker or "unknown"
        self._hippocampus_index[ticker].append(len(self._hippocampus) - 1)

        # 更新行动统计
        if episode.action and episode.outcome is not None:
            self._action_outcomes[episode.action].append(episode.outcome)

    def retrieve_similar(
        self,
        current_market_state: dict[str, Any],
        k: int = 5,
    ) -> list[TradingEpisode]:
        """
        快速检索 k 个最相似的历史事件

        使用组合相似度: 价格相似度 + 波动率相似度 + 体制相似度

        Args:
            current_market_state: 当前市场状态
            k: 返回的最相似事件数

        Returns:
            List[TradingEpisode]: 最相似的历史事件
        """
        if not self._hippocampus:
            return []

        # 计算每个历史事件与当前状态的相似度
        scored_episodes = []
        for episode in self._hippocampus:
            similarity = self._compute_similarity(current_market_state, episode.market_context)
            scored_episodes.append((similarity, episode))

        # 按相似度降序排序
        scored_episodes.sort(key=lambda x: x[0], reverse=True)

        return [ep for _, ep in scored_episodes[:k]]

    def pattern_separation(
        self,
        similar_episodes: list[TradingEpisode],
        threshold: float = 0.85,
    ) -> list[tuple[TradingEpisode, TradingEpisode, float]]:
        """
        模式分离: 区分相似的经历

        计算高度相似事件之间的差异, 帮助区分看似相同但结果不同的模式。

        Args:
            similar_episodes: 相似事件列表
            threshold: 相似度阈值

        Returns:
            List[Tuple]: (ep1, ep2, 差异得分)
        """
        distinct_pairs = []
        for i in range(len(similar_episodes)):
            for j in range(i + 1, len(similar_episodes)):
                sim = self._compute_similarity(
                    similar_episodes[i].market_context,
                    similar_episodes[j].market_context,
                )
                if sim >= threshold:
                    # 计算结果差异
                    outcome_i = similar_episodes[i].outcome or 0.0
                    outcome_j = similar_episodes[j].outcome or 0.0
                    outcome_diff = abs(outcome_i - outcome_j)
                    if outcome_diff > 0.01:  # 结果显著不同但上下文相似 → 分离
                        distinct_pairs.append((similar_episodes[i], similar_episodes[j], outcome_diff))

        # 按结果差异降序排序
        distinct_pairs.sort(key=lambda x: x[2], reverse=True)
        return distinct_pairs

    # ==================== 慢通道: 巩固与知识提取 ====================

    def consolidate(
        self,
        threshold_saliency: float | None = None,
        force: bool = False,
    ) -> int:
        """
        回放和巩固: 从快通道向慢通道迁移重要模式

        选择高显著性的海马体事件, 更新新皮层知识。

        Args:
            threshold_saliency: 显著性阈值 (默认使用配置值)
            force: 是否强制执行 (忽略时间间隔检查)

        Returns:
            int: 巩固的事件数
        """
        # 检查是否应执行巩固
        if not force and self._last_consolidation_time is not None:
            hours_since = (datetime.now() - self._last_consolidation_time).total_seconds() / 3600
            if hours_since < self.config.memory_consolidation_interval:
                return 0

        if threshold_saliency is None:
            threshold_saliency = self.config.memory_saliency_threshold

        # 选择高显著性事件
        salient_episodes = [ep for ep in self._hippocampus if ep.saliency_score >= threshold_saliency]

        if not salient_episodes:
            return 0

        # 重放: 将显著事件的知识整合到新皮层
        consolidated_count = 0
        for episode in salient_episodes:
            self._consolidate_episode(episode)
            consolidated_count += 1

        # 更新市场体制知识
        self._update_regime_knowledge()

        # 更新统计
        self._consolidation_count += 1
        self._last_consolidation_time = datetime.now()

        return consolidated_count

    def _consolidate_episode(self, episode: TradingEpisode) -> None:
        """
        将单个事件巩固到新皮层知识库

        提取关键概念和关系。
        """
        # 提取体制-行动-结果关系
        regime = episode.market_context.get("regime", "unknown")
        action = episode.action
        outcome = episode.outcome

        # 更新体制-行动知识
        concept_key = f"regime_{regime}_action_{action}"
        if concept_key not in self._neocortex_knowledge:
            self._neocortex_knowledge[concept_key] = {
                "regime": regime,
                "action": action,
                "count": 0,
                "total_outcome": 0.0,
                "best_outcome": -float("inf"),
                "worst_outcome": float("inf"),
            }

        knowledge = self._neocortex_knowledge[concept_key]
        knowledge["count"] += 1
        if outcome is not None:
            knowledge["total_outcome"] += outcome
            knowledge["avg_outcome"] = knowledge["total_outcome"] / knowledge["count"]
            knowledge["best_outcome"] = max(knowledge["best_outcome"], outcome)
            knowledge["worst_outcome"] = min(knowledge["worst_outcome"], outcome)

        # 更新知识图连接
        if regime != "unknown":
            self._neocortex_graph[regime].add(action)
            if outcome is not None:
                outcome_category = "positive" if outcome > 0 else "negative"
                self._neocortex_graph[regime].add(f"outcome_{outcome_category}")

    def _update_regime_knowledge(self) -> None:
        """基于海马体数据更新市场体制知识"""
        if not self._hippocampus:
            return

        # 收集各体制下的事件
        regime_episodes: dict[str, list[TradingEpisode]] = defaultdict(list)
        for ep in self._hippocampus:
            regime = ep.market_context.get("regime", "unknown")
            regime_episodes[regime].append(ep)

        # 更新每个体制的知识
        for regime, episodes in regime_episodes.items():
            outcomes = [ep.outcome for ep in episodes if ep.outcome is not None]
            confidences = [ep.confidence for ep in episodes]

            if regime not in self._market_regimes:
                self._market_regimes[regime] = MarketRegime(
                    regime_type=regime,
                    characteristics={},
                    transition_probability={},
                    typical_outcomes={},
                )

            mr = self._market_regimes[regime]
            if outcomes:
                mr.typical_outcomes = {
                    "mean": np.mean(outcomes),
                    "std": np.std(outcomes) if len(outcomes) > 1 else 0.0,
                    "positive_ratio": sum(1 for o in outcomes if o > 0) / len(outcomes),
                    "count": len(outcomes),
                }
            if confidences:
                mr.confidence = np.mean(confidences)

    def extract_statistical_regularity(self) -> MarketRegime:
        """
        提取当前市场统计规律/体制

        Returns:
            MarketRegime: 当前市场体制知识
        """
        # 返回置信度最高的体制知识
        if not self._market_regimes:
            return MarketRegime(
                regime_type="unknown",
                characteristics={},
                transition_probability={},
                typical_outcomes={},
                confidence=0.0,
            )

        return max(
            self._market_regimes.values(),
            key=lambda r: r.confidence,
        )

    def sleep_replay(self) -> dict[str, Any]:
        """
        类睡眠回放: 离线时对重要事件做 shuffled replay

        防止灾难性遗忘 (catastrophic forgetting):
        1. 从海马体采样重要事件
        2. 打乱顺序 (shuffled replay)
        3. 巩固到新皮层

        Returns:
            Dict: 回放统计
        """
        if not self._hippocampus:
            return {"replayed": 0, "patterns_extracted": 0}

        # 采样事件 (优先级: 高显著性事件)
        episodes = list(self._hippocampus)
        saliencies = [ep.saliency_score for ep in episodes]

        # 使用 softmax 采样
        exp_sal = [np.exp(s * 2) for s in saliencies]
        prob = [s / sum(exp_sal) for s in exp_sal]

        # 采样并打乱
        batch_size = min(self.config.memory_replay_batch_size, len(episodes))
        sampled_indices = np.random.choice(len(episodes), size=batch_size, replace=False, p=prob)
        sampled_episodes = [episodes[i] for i in sampled_indices]
        random.shuffle(sampled_episodes)  # 打乱顺序

        # 巩固到新皮层
        patterns_before = len(self._neocortex_knowledge)
        for episode in sampled_episodes:
            self._consolidate_episode(episode)

        patterns_extracted = len(self._neocortex_knowledge) - patterns_before

        return {
            "replayed": batch_size,
            "patterns_extracted": patterns_extracted,
            "hippocampus_size": len(self._hippocampus),
            "neocortex_size": len(self._neocortex_knowledge),
        }

    # ==================== 联合检索 ====================

    def joint_retrieval(
        self,
        query_state: dict[str, Any],
        k: int = 5,
    ) -> MemoryTrace:
        """
        快慢通道联合检索

        同时从海马体和新皮层检索信息，整合后返回。

        Args:
            query_state: 查询状态 (市场上下文)
            k: 检索数量

        Returns:
            MemoryTrace: 联合检索结果
        """
        # 1. 海马体检索 (具体类似情境)
        episodic = self.retrieve_similar(query_state, k=k)

        # 2. 新皮层检索 (抽象知识)
        semantic = self._retrieve_semantic(query_state)

        # 3. 整合摘要
        summary_parts = []
        if episodic:
            summary_parts.append(f"海马体检索到 {len(episodic)} 个类似情景:")
            for ep in episodic[:3]:
                outcome_str = f"{ep.outcome:+.2%}" if ep.outcome is not None else "待评估"
                summary_parts.append(f"  - [{ep.ticker}] {ep.action}: {outcome_str} (置信度={ep.confidence:.2f})")

        if semantic:
            summary_parts.append(f"\n新皮层检索到 {len(semantic)} 条知识:")
            for item in semantic[:3]:
                summary_parts.append(f"  - {item.get('summary', '')}")

        return MemoryTrace(
            episodic_memories=episodic,
            semantic_knowledge=semantic,
            integrated_summary="\n".join(summary_parts),
            retrieval_time=datetime.now().isoformat(),
        )

    def _retrieve_semantic(
        self,
        query_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """从新皮层检索语义知识"""
        results = []

        regime = query_state.get("regime", "unknown")
        action = query_state.get("action", "")

        # 检索体制相关知识
        if regime in self._market_regimes:
            mr = self._market_regimes[regime]
            results.append(
                {
                    "type": "regime_knowledge",
                    "summary": f"体制 {regime}: 平均收益率={mr.typical_outcomes.get('mean', 0):.2%}, "
                    f"胜率={mr.typical_outcomes.get('positive_ratio', 0):.1%}, "
                    f"样本数={mr.typical_outcomes.get('count', 0)}",
                    "data": mr.to_dict(),
                },
            )

        # 检索体制-行动知识
        if action:
            concept_key = f"regime_{regime}_action_{action}"
            if concept_key in self._neocortex_knowledge:
                kn = self._neocortex_knowledge[concept_key]
                results.append(
                    {
                        "type": "action_knowledge",
                        "summary": f"在 {regime} 下执行 {action}: "
                        f"平均={kn.get('avg_outcome', 0):.2%}, "
                        f"最佳={kn.get('best_outcome', 0):.2%}, "
                        f"最差={kn.get('worst_outcome', 0):.2%}, "
                        f"次数={kn.get('count', 0)}",
                        "data": dict(kn),
                    },
                )

        # 检索所有行动的知识 (如果 action 为空)
        if not action:
            for _key, kn in self._neocortex_knowledge.items():
                if kn.get("regime") == regime:
                    results.append(
                        {
                            "type": "action_knowledge",
                            "summary": f"{kn.get('action', '?')}: "
                            f"平均={kn.get('avg_outcome', 0):.2%}, "
                            f"次数={kn.get('count', 0)}",
                            "data": dict(kn),
                        },
                    )

        return results

    # ==================== 内部辅助方法 ====================

    def _compute_similarity(
        self,
        state_a: dict[str, Any],
        state_b: dict[str, Any],
    ) -> float:
        """
        计算两个市场状态的相似度

        使用加权特征相似度。
        """
        if not state_a or not state_b:
            return 0.0

        # 定义相似度特征和权重
        feature_weights = {
            "price": 0.3,
            "volatility": 0.2,
            "sentiment": 0.15,
            "regime": 0.25,
            "volume": 0.1,
        }

        total_similarity = 0.0
        total_weight = 0.0

        for feature, weight in feature_weights.items():
            val_a = state_a.get(feature)
            val_b = state_b.get(feature)

            if val_a is None or val_b is None:
                continue

            if feature == "regime":
                # 体制: 精确匹配
                sim = 1.0 if val_a == val_b else 0.0
            elif isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                # 数值特征: 归一化相似度
                diff = abs(val_a - val_b)
                sim = 1.0 / (1.0 + diff * 10)  # 距离衰减
            else:
                # 字符串: 使用 Jaccard 相似度近似
                set_a = set(str(val_a).lower().split())
                set_b = set(str(val_b).lower().split())
                if not set_a and not set_b:
                    sim = 1.0
                elif not set_a or not set_b:
                    sim = 0.0
                else:
                    intersection = set_a & set_b
                    union = set_a | set_b
                    sim = len(intersection) / len(union) if union else 0.0

            total_similarity += weight * sim
            total_weight += weight

        return total_similarity / total_weight if total_weight > 0 else 0.0

    def _compute_saliency(self, episode: TradingEpisode) -> float:
        """
        计算事件的显著性得分

        综合: 结果绝对值 + 置信度倒数 + 预测误差
        """
        saliency = 0.0
        n_features = 0

        # 结果显著性 (高收益/高亏损)
        if episode.outcome is not None:
            outcome_saliency = min(1.0, abs(episode.outcome) * 5)
            saliency += outcome_saliency * 0.4
            n_features += 0.4

        # 预测误差显著性
        if episode.prediction_error > 0:
            error_saliency = min(1.0, episode.prediction_error * 2)
            saliency += error_saliency * 0.3
            n_features += 0.3

        # 低置信度但好结果 (意外收获)
        if episode.confidence < 0.5 and episode.outcome and episode.outcome > 0.05:
            saliency += 0.3
            n_features += 0.3

        return saliency / n_features if n_features > 0 else 0.1

    # ==================== 查询与统计 ====================

    def get_statistics(self) -> dict[str, Any]:
        """获取记忆系统统计"""
        return {
            "hippocampus_size": len(self._hippocampus),
            "hippocampus_max": self.config.memory_hippocampus_max_episodes,
            "neocortex_knowledge_entries": len(self._neocortex_knowledge),
            "neocortex_graph_nodes": len(self._neocortex_graph),
            "market_regimes_identified": len(self._market_regimes),
            "action_types_tracked": len(self._action_outcomes),
            "consolidation_count": self._consolidation_count,
            "last_consolidation": self._last_consolidation_time.isoformat() if self._last_consolidation_time else None,
            "total_episodes": self._episode_counter,
        }

    def get_action_performance(self) -> dict[str, dict[str, float]]:
        """获取各行动的历史表现统计"""
        stats = {}
        for action, outcomes in self._action_outcomes.items():
            if outcomes:
                stats[action] = {
                    "count": len(outcomes),
                    "mean": float(np.mean(outcomes)),
                    "std": float(np.std(outcomes)) if len(outcomes) > 1 else 0.0,
                    "max": float(np.max(outcomes)),
                    "min": float(np.min(outcomes)),
                    "win_rate": sum(1 for o in outcomes if o > 0) / len(outcomes),
                    "sharpe": float(np.mean(outcomes) / max(np.std(outcomes), 1e-8)),
                }
        return stats

    def reset(self) -> None:
        """重置记忆系统"""
        self._hippocampus.clear()
        self._hippocampus_index.clear()
        self._neocortex_knowledge.clear()
        self._neocortex_graph.clear()
        self._market_regimes.clear()
        self._action_outcomes.clear()
        self._regime_transition_counts.clear()
        self._last_consolidation_time = None
        self._consolidation_count = 0
        self._episode_counter = 0
