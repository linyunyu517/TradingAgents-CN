# TradingAgents/l_iwm/learnable_gws.py
"""
可学习显著性评估器 (Learnable Saliency Evaluator)
==================================================

替代当前 hpc_loop/global_workspace.py:380 的关键词计数启发式：
    _estimate_novelty(): novelty_keywords = ["突发", "意外", ...], matches * 0.15 + 0.1
    _estimate_impact():  impact_keywords = ["重大", "关键", ...], matches * 0.12 + 0.1
    _estimate_urgency(): urgency_keywords = ["立即", "紧急", ...], matches * 0.15 + 0.05

核心创新:
    1. 可学习文本编码器: TF-IDF → 全连接网络 → 显著性分量
       — 从 NLP 特征中学习各显著性分量的权重
    2. 四项显著性分量: novelty(新颖性), confidence(置信度), impact(影响力), urgency(紧迫性)
       — 每个分量由独立的参数化模型预测
    3. 注意力竞争机制: 可学习的 top-k 选择阈值
    4. 在线适应性: 基于结果反馈 (收益/损失) 更新显著性权重
    5. 信念对比: 与当前信念状态对比，学习哪些信息真正"新颖"

兼容性:
    - 输入: (content: str, confidence: float, belief: Dict) 同 GlobalWorkspace API
    - 输出: Dict[str, float] 包含 novelty, impact, urgency, 总 saliency
"""

import json
import math
import re
from collections import Counter, deque
from typing import Any

import numpy as np

# ==================== 工具函数 ====================


def _he_init(shape: tuple[int, ...]) -> np.ndarray:
    """He 初始化"""
    if len(shape) == 1:
        return np.random.randn(shape[0]) * 0.01
    fan_in = shape[0]
    std = math.sqrt(2.0 / fan_in)
    return np.random.randn(*shape) * std


def _tokenize(text: str) -> list[str]:
    """简单分词 (中英文混合)"""
    # 中文分词: 按字符拆分为 unigram
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    # 英文分词: 按空格和标点拆分
    english_tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return chinese_chars + english_tokens


def _extract_tfidf_features(
    text: str,
    vocab: dict[str, int],
    idf: np.ndarray | None = None,
    normalize: bool = True,
) -> np.ndarray:
    """
    提取 TF-IDF 特征向量

    Args:
        text: 输入文本
        vocab: 词汇表 {词: 索引}
        idf: IDF 向量 (None 则使用统一权重)
        normalize: 是否 L2 归一化

    Returns:
        np.ndarray: TF-IDF 特征向量 [vocab_size]
    """
    d = len(vocab)
    tf = np.zeros(d)
    tokens = _tokenize(text)

    for token in tokens:
        if token in vocab:
            tf[vocab[token]] += 1

    # TF 归一化
    if np.sum(tf) > 0:
        tf = tf / np.sum(tf)

    tfidf = tf * idf if idf is not None else tf

    if normalize and np.linalg.norm(tfidf) > 1e-10:
        tfidf = tfidf / np.linalg.norm(tfidf)

    return tfidf


# ==================== 可学习显著性评估器 ====================


class LearnableSaliencyEvaluator:
    """
    可学习显著性评估器

    替代 GlobalWorkspace._estimate_novelty/_estimate_impact/_estimate_urgency
    的关键词计数启发式方法。使用可学习的神经网络从文本特征中预测
    显著性分量，并通过在线学习从交易结果反馈中优化。

    使用流程:
        evaluator = LearnableSaliencyEvaluator(feature_dim=64)

        # 评估分析报告的显著性
        saliency = evaluator.compute_saliency({
            "novelty": 0.5, "confidence": 0.8, "impact": 0.3, "urgency": 0.1
        })

        # 或者自动分析文本
        components = evaluator.evaluate_content(
            "突发消息: 美联储意外加息50基点",
            confidence=0.85,
            current_belief={"利率": "稳定"}
        )
    """

    # 默认金融关键词表 (用于特征构建)
    NOVELTY_INDICATORS = [
        "突发",
        "意外",
        "首次",
        "突破",
        "创新高",
        "创新低",
        "前所未有",
        "突然",
        "罕见",
        "surprise",
        "unexpected",
        "breakthrough",
        "first",
        "new",
        "record",
    ]

    IMPACT_INDICATORS = [
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
        "加息",
        "降息",
        "制裁",
        "危机",
    ]

    URGENCY_INDICATORS = [
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

    def __init__(
        self,
        config: Any = None,
        feature_dim: int = 64,
        learning_rate: float = 1e-3,
        top_k: int = 3,
        embedding_method: str = "tfidf",
    ):
        """
        初始化可学习显著性评估器

        Args:
            config: LIWMConfig 实例 (可选)
            feature_dim: 特征网络隐层维度
            learning_rate: 学习率
            top_k: 广播时的 top-k 数量
            embedding_method: 编码方法 (tfidf, hybrid)
        """
        if config is not None:
            feature_dim = getattr(config, "gws_feature_dim", feature_dim)
            learning_rate = getattr(config, "gws_learning_rate", learning_rate)
            top_k = getattr(config, "gws_top_k", top_k)
            embedding_method = getattr(config, "gws_embedding_method", embedding_method)

        self.feature_dim = feature_dim
        self.learning_rate = learning_rate
        self.top_k = top_k
        self.embedding_method = embedding_method
        self.train_step = 0

        # ========== 词汇表 ==========
        # 从所有已见文本中构建
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None
        self._doc_freq: Counter = Counter()
        self._total_docs: int = 0
        self._vocab_size: int = 0

        # 预置高频金融词汇
        self._init_vocab()

        # ========== 可学习显著性权重 ==========
        # saliency = w_n * novelty + w_c * confidence + w_i * impact + w_u * urgency
        # 这些权重是可学习的，通过反馈优化
        self.novelty_weight = 0.3
        self.confidence_weight = 0.3
        self.impact_weight = 0.25
        self.urgency_weight = 0.15
        self._saliency_weights = np.array(
            [
                self.novelty_weight,
                self.confidence_weight,
                self.impact_weight,
                self.urgency_weight,
            ],
        )

        # ========== 显著性分量预测网络 ==========
        # 对每个分量 (novelty, impact, urgency) 训练一个小型 MLP
        input_dim = min(feature_dim, 20)  # 使用关键词特征而不是完整 TF-IDF

        # Novelty 网络
        self.W_novelty = _he_init((input_dim, 4))
        self.b_novelty = np.zeros(4)
        self.W_novelty_out = _he_init((4, 1))
        self.b_novelty_out = np.zeros(1)

        # Impact 网络
        self.W_impact = _he_init((input_dim, 4))
        self.b_impact = np.zeros(4)
        self.W_impact_out = _he_init((4, 1))
        self.b_impact_out = np.zeros(1)

        # Urgency 网络
        self.W_urgency = _he_init((input_dim, 4))
        self.b_urgency = np.zeros(4)
        self.W_urgency_out = _he_init((4, 1))
        self.b_urgency_out = np.zeros(1)

        # ========== 优化器 ==========
        self._optimizers = {
            "novelty": _AdamOptimizer(learning_rate),
            "impact": _AdamOptimizer(learning_rate),
            "urgency": _AdamOptimizer(learning_rate),
        }

        # ========== 信念对比 ==========
        self._belief_history: list[dict[str, Any]] = []
        """信念状态历史"""

        self._content_embeddings: deque = deque(maxlen=500)
        """最近内容嵌入向量"""

        # ========== 反馈学习 ==========
        self._feedback_buffer: deque = deque(maxlen=1000)
        """反馈缓冲 (用于在线学习)"""

        self._saliency_history: list[float] = []
        self._component_history: dict[str, list[float]] = {
            "novelty": [],
            "impact": [],
            "urgency": [],
        }

    def _init_vocab(self) -> None:
        """初始化金融领域词汇表"""
        all_keywords = (
            self.NOVELTY_INDICATORS
            + self.IMPACT_INDICATORS
            + self.URGENCY_INDICATORS
            + [
                "买入",
                "卖出",
                "持有",
                "做多",
                "做空",
                "上证",
                "深证",
                "创业板",
                "科创板",
                "PE",
                "PB",
                "ROE",
                "EPS",
                "GDP",
                "CPI",
                "bull",
                "bear",
                "rally",
                "crash",
                "volatility",
                "美联储",
                "央行",
                "财政",
                "政策",
                "监管",
                "业绩",
                "财报",
                "营收",
                "利润",
                "增长",
                "风险",
                "机会",
                "趋势",
                "反转",
                "突破",
                "支撑",
                "阻力",
                "超买",
                "超卖",
                "金叉",
                "死叉",
                "alpha",
                "beta",
                "sharpe",
                "drawdown",
                "quant",
                "algorithm",
                "高频",
                "策略",
                "利好",
                "利空",
                "中性",
                "乐观",
                "悲观",
            ]
        )

        for _i, word in enumerate(all_keywords):
            if word not in self._vocab:
                self._vocab[word] = len(self._vocab)

        self._vocab_size = len(self._vocab)
        self._idf = np.ones(self._vocab_size)

    def _update_vocab(self, text: str) -> None:
        """增量更新词汇表和 IDF"""
        tokens = _tokenize(text)
        seen = set()

        for token in tokens:
            if token not in self._vocab:
                self._vocab[token] = len(self._vocab)
            if token not in seen:
                self._doc_freq[token] += 1
                seen.add(token)

        self._total_docs += 1

        # 更新 IDF
        new_size = len(self._vocab)
        if new_size > self._vocab_size:
            old_idf = self._idf
            self._idf = np.ones(new_size)
            self._idf[: len(old_idf)] = old_idf
            self._vocab_size = new_size

        # IDF(t) = log(N / df(t)) + 1
        for token, df in self._doc_freq.items():
            if token in self._vocab:
                idx = self._vocab[token]
                self._idf[idx] = math.log(self._total_docs / max(df, 1)) + 1

    # ==================== 特征提取 ====================

    def _keyword_features(self, text: str) -> np.ndarray:
        """
        提取关键词特征向量 (快速轻量)

        基于预定义关键词表的命中计数特征。

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 关键词特征 [20]
        """
        text_lower = text.lower()
        features = np.zeros(20)

        # 0-4: Novelty 关键词命中
        for i, kw in enumerate(self.NOVELTY_INDICATORS[:5]):
            features[i] = 1.0 if kw.lower() in text_lower else 0.0

        # 5-9: Impact 关键词命中
        for i, kw in enumerate(self.IMPACT_INDICATORS[:5]):
            features[5 + i] = 1.0 if kw.lower() in text_lower else 0.0

        # 10-14: Urgency 关键词命中
        for i, kw in enumerate(self.URGENCY_INDICATORS[:5]):
            features[10 + i] = 1.0 if kw.lower() in text_lower else 0.0

        # 15: 文本长度 (规范化)
        features[15] = min(1.0, len(text) / 500.0)

        # 16: 数字占比 (数字多的文本通常更具体)
        num_count = len(re.findall(r"\d+\.?\d*", text))
        features[16] = min(1.0, num_count / 10.0)

        # 17: 百分比符号 (市场数据指标)
        pct_count = text.count("%") + text.count("percent")
        features[17] = min(1.0, pct_count / 3.0)

        # 18: 方向性词汇 (涨/跌/升/降)
        direction_words = [
            "涨",
            "跌",
            "升",
            "降",
            "up",
            "down",
            "rise",
            "fall",
            "increase",
            "decrease",
            "positive",
            "negative",
        ]
        dir_count = sum(1 for w in direction_words if w in text_lower)
        features[18] = min(1.0, dir_count / 5.0)

        # 19: 情感词汇 (利好/利空/乐观/悲观)
        sentiment_words = [
            "利好",
            "利空",
            "乐观",
            "悲观",
            "positive",
            "negative",
            "bullish",
            "bearish",
            "favorable",
            "unfavorable",
        ]
        sent_count = sum(1 for w in sentiment_words if w in text_lower)
        features[19] = min(1.0, sent_count / 4.0)

        return features

    def _extract_features(self, text: str) -> np.ndarray:
        """
        提取文本特征 (主入口)

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 特征向量
        """
        self._update_vocab(text)
        keyword_feat = self._keyword_features(text)

        if self.embedding_method == "tfidf":
            # TF-IDF + 关键词特征
            tfidf = _extract_tfidf_features(text, self._vocab, self._idf)
            # 截断/填充到固定维度
            if len(tfidf) > self.feature_dim:
                tfidf = tfidf[: self.feature_dim]
            else:
                tfidf = np.pad(tfidf, (0, max(0, self.feature_dim - len(tfidf))))

            # 混合特征 (前 20 维用关键词特征)
            combined = tfidf.copy()
            combined[: len(keyword_feat)] = keyword_feat
            return combined

        # 仅关键词特征 (填充到 feature_dim)
        if len(keyword_feat) < self.feature_dim:
            return np.pad(keyword_feat, (0, self.feature_dim - len(keyword_feat)))
        return keyword_feat[: self.feature_dim]

    # ==================== 分量网络前向 ====================

    def _network_forward(
        self,
        x: np.ndarray,
        W1: np.ndarray,
        b1: np.ndarray,
        W2: np.ndarray,
        b2: np.ndarray,
    ) -> float:
        """
        小型 MLP 前向传播

        f(x) = sigmoid(W2 * tanh(W1 * x + b1) + b2)

        Args:
            x: 输入特征
            W1, b1: 隐层参数
            W2, b2: 输出层参数

        Returns:
            float: 输出值 [0, 1]
        """
        h = x @ W1 + b1
        h = np.tanh(h)
        out = float((h @ W2 + b2)[0])
        return 1.0 / (1.0 + math.exp(-out))

    def _predict_novelty(self, features: np.ndarray) -> float:
        """预测新颖性得分"""
        return self._network_forward(
            features,
            self.W_novelty,
            self.b_novelty,
            self.W_novelty_out,
            self.b_novelty_out,
        )

    def _predict_impact(self, features: np.ndarray) -> float:
        """预测影响力得分"""
        return self._network_forward(
            features,
            self.W_impact,
            self.b_impact,
            self.W_impact_out,
            self.b_impact_out,
        )

    def _predict_urgency(self, features: np.ndarray) -> float:
        """预测紧迫性得分"""
        return self._network_forward(
            features,
            self.W_urgency,
            self.b_urgency,
            self.W_urgency_out,
            self.b_urgency_out,
        )

    # ==================== 信念对比新颖性 ====================

    def _compute_belief_novelty(self, text: str, belief: dict[str, Any]) -> float:
        """
        基于信念对比的新颖性计算

        如果当前文本包含与信念不一致的信息，新颖性更高。

        Args:
            text: 分析内容
            belief: 当前信念状态

        Returns:
            float: 信念对比新颖性 [0, 1]
        """
        if not belief:
            return 0.5

        text_lower = text.lower()
        text_tokens = set(_tokenize(text))

        # 提取信念中的关键词
        belief_text = str(belief)
        belief_tokens = set(_tokenize(belief_text))

        # 不在信念中的词的比例
        if not text_tokens:
            return 0.0

        novel_tokens = text_tokens - belief_tokens
        token_novelty = len(novel_tokens) / max(len(text_tokens), 1)

        # 信念否定词检测 (如果文本反驳了信念)
        contradiction_signals = [
            "相反",
            "反转",
            "意外",
            "不同于预期",
            "contrary",
            "reversal",
            "unexpected",
            "against",
            "不是",
            "并非",
            "不应",
        ]
        contradiction_count = sum(1 for c in contradiction_signals if c in text_lower)
        contradiction_factor = min(1.0, contradiction_count * 0.3)

        # 综合新颖性: 词汇新颖性 + 矛盾信号
        combined = token_novelty * 0.6 + contradiction_factor * 0.4
        return min(1.0, combined)

    # ==================== 公共 API ====================

    def evaluate_content(
        self,
        content: str,
        confidence: float = 0.5,
        current_belief: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        """
        评估内容的显著性分量

        替代 GlobalWorkspace._estimate_novelty/_impact/_urgency 的三个关键词函数。

        Args:
            content: 分析报告文本
            confidence: Agent 报告的置信度
            current_belief: 当前信念状态 (用于信念对比新颖性)

        Returns:
            Dict 包含 novelty, impact, urgency, belief_novelty
        """
        features = self._keyword_features(content)
        belief = current_belief or {}

        # 使用可学习网络预测各分量
        novelty = self._predict_novelty(features)
        impact = self._predict_impact(features)
        urgency = self._predict_urgency(features)

        # 信念对比新颖性
        belief_novelty = self._compute_belief_novelty(content, belief)

        # 综合新颖性 = max(网络预测, 信念对比)
        combined_novelty = max(novelty, belief_novelty)
        combined_novelty = min(1.0, combined_novelty)

        # 记录
        self._component_history["novelty"].append(combined_novelty)
        self._component_history["impact"].append(impact)
        self._component_history["urgency"].append(urgency)

        return {
            "novelty": combined_novelty,
            "impact": impact,
            "urgency": urgency,
            "belief_novelty": belief_novelty,
            "network_novelty": novelty,
            "confidence": confidence,
        }

    def compute_saliency(
        self,
        components: dict[str, float],
    ) -> float:
        """
        计算总显著性得分

        saliency = w_n * novelty + w_c * confidence + w_i * impact + w_u * urgency

        Args:
            components: 包含 novelty, confidence, impact, urgency 的字典

        Returns:
            float: 显著性得分 [0, 1]
        """
        novelty = max(0.0, min(1.0, components.get("novelty", 0.0)))
        confidence = max(0.0, min(1.0, components.get("confidence", 0.0)))
        impact = max(0.0, min(1.0, components.get("impact", 0.0)))
        urgency = max(0.0, min(1.0, components.get("urgency", 0.0)))

        # 可学习权重
        w_n = float(self._saliency_weights[0])
        w_c = float(self._saliency_weights[1])
        w_i = float(self._saliency_weights[2])
        w_u = float(self._saliency_weights[3])

        total = w_n + w_c + w_i + w_u
        if total > 0:
            w_n, w_c, w_i, w_u = w_n / total, w_c / total, w_i / total, w_u / total

        saliency = w_n * novelty + w_c * confidence + w_i * impact + w_u * urgency
        saliency = max(0.0, min(1.0, saliency))

        self._saliency_history.append(saliency)

        return saliency

    def select_top_k(
        self,
        contents: list[tuple[str, float]],  # (content_id, saliency_score)
    ) -> list[str]:
        """
        选择 top-k 最显著的内容

        替代 GlobalWorkspace.broadcast() 中的固定阈值筛选。

        Args:
            contents: [(content_id, saliency_score), ...]

        Returns:
            List[str]: 选中的 content_id 列表
        """
        if not contents:
            return []

        # 按显著性排序
        sorted_contents = sorted(contents, key=lambda x: x[1], reverse=True)

        # 自适应阈值: top-k 或 显著性 > 均值
        scores = [s for _, s in sorted_contents]
        mean_score = np.mean(scores) if scores else 0.0
        threshold = max(mean_score, 0.3)

        selected = [cid for cid, score in sorted_contents if score >= threshold]

        # 容量限制
        return selected[: self.top_k]

    # ==================== 在线学习 ====================

    def update_from_feedback(
        self,
        content: str,
        components: dict[str, float],
        outcome_reward: float,
    ) -> dict[str, float]:
        """
        根据交易结果反馈更新显著性权重

        如果某显著性分量预测与结果正相关，增加其权重；
        否则减少。

        Args:
            content: 原始内容
            components: 显著性分量
            outcome_reward: 交易结果 (正 → 好结果, 负 → 差结果)

        Returns:
            Dict 包含权重更新信息
        """
        self._feedback_buffer.append(
            {
                "content": content,
                "components": components,
                "reward": outcome_reward,
            },
        )

        # 更新显著性权重 (基于反馈)
        lr = 0.01
        delta = lr * outcome_reward

        self._saliency_weights[0] += delta * components.get("novelty", 0.5)  # novelty
        self._saliency_weights[1] += delta * components.get("confidence", 0.5)  # confidence
        self._saliency_weights[2] += delta * components.get("impact", 0.5)  # impact
        self._saliency_weights[3] += delta * components.get("urgency", 0.5)  # urgency

        # 确保非负
        self._saliency_weights = np.maximum(0.01, self._saliency_weights)

        # 归一化
        self._saliency_weights = self._saliency_weights / np.sum(self._saliency_weights)

        # 更新分量网络 (使用梯度近似)
        features = self._keyword_features(content)
        self._update_component_network(
            "novelty",
            features,
            components.get("novelty", 0.5),
            outcome_reward,
            self.W_novelty,
            self.b_novelty,
            self.W_novelty_out,
            self.b_novelty_out,
            self._optimizers["novelty"],
        )
        self._update_component_network(
            "impact",
            features,
            components.get("impact", 0.3),
            outcome_reward,
            self.W_impact,
            self.b_impact,
            self.W_impact_out,
            self.b_impact_out,
            self._optimizers["impact"],
        )
        self._update_component_network(
            "urgency",
            features,
            components.get("urgency", 0.2),
            outcome_reward,
            self.W_urgency,
            self.b_urgency,
            self.W_urgency_out,
            self.b_urgency_out,
            self._optimizers["urgency"],
        )

        self.train_step += 1

        return {
            "weights": self._saliency_weights.tolist(),
            "reward": outcome_reward,
            "train_step": self.train_step,
        }

    def _update_component_network(
        self,
        name: str,
        features: np.ndarray,
        predicted: float,
        reward: float,
        W1: np.ndarray,
        b1: np.ndarray,
        W2: np.ndarray,
        b2: np.ndarray,
        optimizer: Any,
    ) -> None:
        """
        更新分量网络的参数

        使用简化的 REINFORCE 风格更新:
        如果 reward > 0 (好结果), 推动预测值向当前方向;
        如果 reward < 0 (差结果), 推动预测值反向。

        Args:
            name: 分量名称
            features: 输入特征
            predicted: 当前预测值
            reward: 反馈奖励
            W1, b1, W2, b2: 网络参数
            optimizer: Adam 优化器
        """
        eps = 1e-4
        x = features[:20]  # 使用关键词特征 (前 20 维)

        # 计算一个简化的梯度方向
        # 目标: 如果 reward > 0, 增加预测值, 反之减少
        target_shift = math.tanh(reward) * 0.1  # [-0.1, 0.1]
        target = max(0.0, min(1.0, predicted + target_shift))

        # 参数扰动梯度估计 (SPSA 风格)
        for param_name, param in [
            ("W1", W1),
            ("b1", b1),
            ("W2", W2),
            ("b2", b2),
        ]:
            if param.size == 0:
                continue

            delta = np.random.choice([-1, 1], size=param.shape) * eps

            # 正向扰动
            param_plus = param + delta
            if param_name == "W1":
                pred_plus = self._network_forward(x, param_plus, b1, W2, b2)
            elif param_name == "b1":
                pred_plus = self._network_forward(x, W1, param_plus, W2, b2)
            elif param_name == "W2":
                pred_plus = self._network_forward(x, W1, b1, param_plus, b2)
            else:  # b2
                pred_plus = self._network_forward(x, W1, b1, W2, param_plus)

            loss_plus = (pred_plus - target) ** 2

            # 负向扰动
            param_minus = param - delta
            if param_name == "W1":
                pred_minus = self._network_forward(x, param_minus, b1, W2, b2)
            elif param_name == "b1":
                pred_minus = self._network_forward(x, W1, param_minus, W2, b2)
            elif param_name == "W2":
                pred_minus = self._network_forward(x, W1, b1, param_minus, b2)
            else:  # b2
                pred_minus = self._network_forward(x, W1, b1, W2, param_minus)

            loss_minus = (pred_minus - target) ** 2

            # 梯度近似
            grad_approx = (loss_plus - loss_minus) / (2 * eps)
            grad = delta * grad_approx

            # Adam 更新
            update = optimizer.step(f"{name}_{param_name}", grad.reshape(param.shape))
            param += update.reshape(param.shape)

    def train_on_feedback_buffer(self, batch_size: int = 32) -> dict[str, float]:
        """
        从反馈缓冲中批量训练

        Args:
            batch_size: 批次大小

        Returns:
            Dict 包含训练统计
        """
        if len(self._feedback_buffer) < batch_size:
            return {"loss": 0.0, "samples": 0, "skipped": True}

        indices = np.random.choice(len(self._feedback_buffer), batch_size, replace=False)
        total_update = {
            "weights": self._saliency_weights.tolist(),
            "reward": 0.0,
            "train_step": self.train_step,
        }

        for idx in indices:
            fb = self._feedback_buffer[idx]
            result = self.update_from_feedback(
                fb["content"],
                fb["components"],
                fb["reward"],
            )
            total_update["reward"] += result["reward"]

        total_update["reward"] /= batch_size

        return total_update

    # ==================== 序列化 ====================

    def get_params_dict(self) -> dict[str, Any]:
        """获取所有可学习参数"""
        return {
            "W_novelty": self.W_novelty.tolist(),
            "b_novelty": self.b_novelty.tolist(),
            "W_novelty_out": self.W_novelty_out.tolist(),
            "b_novelty_out": self.b_novelty_out.tolist(),
            "W_impact": self.W_impact.tolist(),
            "b_impact": self.b_impact.tolist(),
            "W_impact_out": self.W_impact_out.tolist(),
            "b_impact_out": self.b_impact_out.tolist(),
            "W_urgency": self.W_urgency.tolist(),
            "b_urgency": self.b_urgency.tolist(),
            "W_urgency_out": self.W_urgency_out.tolist(),
            "b_urgency_out": self.b_urgency_out.tolist(),
            "saliency_weights": self._saliency_weights.tolist(),
            "train_step": self.train_step,
            "vocab": dict(self._vocab),
            "total_docs": self._total_docs,
        }

    def load_params_dict(self, params: dict[str, Any]) -> None:
        """加载可学习参数"""
        param_mapping = {
            "W_novelty": "W_novelty",
            "b_novelty": "b_novelty",
            "W_novelty_out": "W_novelty_out",
            "b_novelty_out": "b_novelty_out",
            "W_impact": "W_impact",
            "b_impact": "b_impact",
            "W_impact_out": "W_impact_out",
            "b_impact_out": "b_impact_out",
            "W_urgency": "W_urgency",
            "b_urgency": "b_urgency",
            "W_urgency_out": "W_urgency_out",
            "b_urgency_out": "b_urgency_out",
        }

        for key, attr in param_mapping.items():
            if key in params:
                setattr(self, attr, np.array(params[key]))

        if "saliency_weights" in params:
            self._saliency_weights = np.array(params["saliency_weights"])

        self.train_step = params.get("train_step", 0)
        self._total_docs = params.get("total_docs", 0)

    def save(self, path: str) -> None:
        """保存模型参数"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_params_dict(), f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        """加载模型参数"""
        with open(path, encoding="utf-8") as f:
            params = json.load(f)
        self.load_params_dict(params)

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "train_step": self.train_step,
            "vocab_size": self._vocab_size,
            "total_docs": self._total_docs,
            "feedback_buffer_size": len(self._feedback_buffer),
            "saliency_weights": self._saliency_weights.tolist(),
            "avg_saliency": float(np.mean(self._saliency_history[-100:])) if self._saliency_history else 0.0,
            "avg_novelty": float(np.mean(self._component_history["novelty"][-100:]))
            if self._component_history["novelty"]
            else 0.0,
            "avg_impact": float(np.mean(self._component_history["impact"][-100:]))
            if self._component_history["impact"]
            else 0.0,
            "avg_urgency": float(np.mean(self._component_history["urgency"][-100:]))
            if self._component_history["urgency"]
            else 0.0,
            "top_k": self.top_k,
        }

    # ==================== SPSA 梯度计算 (供 HSR-MC 使用) ====================

    def _collect_params(self) -> dict[str, np.ndarray]:
        """收集所有可训练参数为 numpy 数组字典（供元学习使用）"""
        params = {}
        for comp in ["novelty", "impact", "urgency"]:
            W1 = getattr(self, f"W_{comp}")
            b1 = getattr(self, f"b_{comp}")
            W2 = getattr(self, f"W_{comp}_out")
            b2 = getattr(self, f"b_{comp}_out")
            params[f"{comp}_W1"] = W1
            params[f"{comp}_b1"] = b1
            params[f"{comp}_W2"] = W2
            params[f"{comp}_b2"] = b2
        params["saliency_weights"] = self._saliency_weights
        return params

    def _compute_gradient_spsa(
        self,
        loss_fn,
        params_dict: dict[str, np.ndarray],
        c: float = 1e-4,
        num_perturbations: int = 1,
    ) -> dict[str, np.ndarray]:
        """
        SPSA (Simultaneous Perturbation Stochastic Approximation) 梯度估计。

        核心公式:
            g_i(θ) ≈ (L(θ + c·Δ) - L(θ - c·Δ)) / (2c·Δ_i)

        其中 Δ 是随机扰动向量，每个分量独立采样自 {±1}。

        Args:
            loss_fn:    Callable[[Dict[str, np.ndarray]], float]
                        接受扰动参数字典，返回标量损失值
            params_dict: 参数字典 {名称: 参数值}
            c:           扰动步长
            num_perturbations: SPSA 扰动次数 (平均以降低方差, 默认 1)

        Returns:
            Dict[str, np.ndarray]: 梯度字典，结构与 params_dict 一致
        """
        grads = {name: np.zeros_like(param) for name, param in params_dict.items()}

        for _ in range(num_perturbations):
            # 为每个参数生成同步随机扰动 Δ ∈ {±1}
            delta = {}
            for name, param in params_dict.items():
                delta[name] = np.random.choice([-1, 1], size=param.shape).astype(param.dtype)

            # 正向扰动: θ + c·Δ
            params_plus = {name: param + c * delta[name] for name, param in params_dict.items()}
            loss_plus = loss_fn(params_plus)

            # 负向扰动: θ - c·Δ
            params_minus = {name: param - c * delta[name] for name, param in params_dict.items()}
            loss_minus = loss_fn(params_minus)

            # SPSA 梯度: (L⁺ - L⁻) / (2c·Δ_i)
            delta_loss = loss_plus - loss_minus
            for name in params_dict:
                grads[name] += (delta_loss / (2.0 * c)) * (1.0 / (delta[name] + 1e-12))

        if num_perturbations > 1:
            for name in grads:
                grads[name] /= num_perturbations

        return grads

    def reset(self) -> None:
        """重置运行时状态 (保留可学习参数)"""
        self._belief_history.clear()
        self._content_embeddings.clear()
        self._feedback_buffer.clear()
        self._saliency_history.clear()
        self._component_history = {"novelty": [], "impact": [], "urgency": []}
        self._doc_freq = Counter()
        self._total_docs = 0


# ==================== Adam 优化器 (内部) ====================


class _AdamOptimizer:
    """NumPy Adam 优化器 (与 L-IWM 其他模块一致)"""

    def __init__(self, lr: float = 1e-3, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m: dict[str, np.ndarray] = {}
        self.v: dict[str, np.ndarray] = {}
        self.t: int = 0

    def step(self, param_name: str, grad: np.ndarray) -> np.ndarray:
        if param_name not in self.m:
            self.m[param_name] = np.zeros_like(grad)
            self.v[param_name] = np.zeros_like(grad)

        self.t += 1
        self.m[param_name] = self.beta1 * self.m[param_name] + (1 - self.beta1) * grad
        self.v[param_name] = self.beta2 * self.v[param_name] + (1 - self.beta2) * (grad**2)

        m_hat = self.m[param_name] / (1 - self.beta1**self.t)
        v_hat = self.v[param_name] / (1 - self.beta2**self.t)

        return -self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset(self) -> None:
        self.m.clear()
        self.v.clear()
        self.t = 0
