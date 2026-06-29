"""
预测编码新闻分析器 - 数学层
Phase 1【器】: 情感分析 + 主题聚类 + 信息熵 + 叙事结构
Phase 2【术】: 预测编码信念更新

依赖: numpy (零新增依赖!)
新增依赖: 0
"""

import re
import math
import logging
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional
from datetime import datetime

import numpy as np

logger = logging.getLogger("analysts.news_math")

# ╔══════════════════════════════════════════════════════════════╗
# ║ 中文金融情感词库 (hardcoded, ~480词, 零外部依赖)          ║
# ╚══════════════════════════════════════════════════════════════╝
# 权重范围: -1.0 (极负面) ~ +1.0 (极正面)
FINANCIAL_SENTIMENT_LEXICON: Dict[str, float] = {
    # ─── 强烈正面 +0.8~+1.0 ───
    "涨停": 0.90, "一字板": 0.85, "连板": 0.85, "创新高": 0.90,
    "突破": 0.70, "业绩大增": 0.95, "扭亏为盈": 0.90, "超预期": 0.85,
    "重大利好": 0.90, "重组获批": 0.85, "业绩爆发": 0.90,
    "盈利预增": 0.85, "利润大增": 0.90, "营收增长": 0.70,
    "中标": 0.55, "回购": 0.60, "增持": 0.65, "分红": 0.45,
    "扩张": 0.40, "签约": 0.35, "合作": 0.35, "战略合作": 0.50,
    "强于大盘": 0.60, "买入评级": 0.70, "推荐评级": 0.65,
    "利好": 0.75, "放量上涨": 0.70, "触底反弹": 0.65,
    "供不应求": 0.60, "市占率提升": 0.70, "毛利率提升": 0.75,
    "新签订单": 0.55, "订单饱满": 0.65, "产能释放": 0.60,
    "政策利好": 0.65, "减税": 0.55, "降息": 0.45,
    # ─── 中性偏正面 +0.1~+0.3 ───
    "稳定增长": 0.30, "小幅上涨": 0.25, "企稳": 0.20,
    "平稳运行": 0.15, "正常波动": 0.10, "温和上涨": 0.30,
    "关注": 0.15, "保持": 0.10, "定期报告": 0.10,
    "审议": 0.10, "公告": 0.05, "通知": 0.05,
    # ─── 中性 +0.0 ───
    "震荡": 0.0, "横盘": 0.0, "持平": 0.0, "不变": 0.0,
    "调整": 0.0, "正常": 0.0, "稳定": 0.0,
    # ─── 中性偏负面 -0.1~-0.3 ───
    "小幅下跌": -0.25, "波动": -0.10, "不确定性": -0.20,
    "承压": -0.30, "乏力": -0.25, "放缓": -0.25,
    "关注风险": -0.20, "需谨慎": -0.20,
    "减持": -0.50, "亏损": -0.55, "下跌": -0.40,
    "诉讼": -0.50, "仲裁": -0.45, "处罚": -0.60,
    "违规": -0.60, "警告": -0.45, "问询": -0.35,
    # ─── 强烈负面 -0.8~-1.0 ───
    "跌停": -0.90, "爆雷": -0.95, "退市": -0.95,
    "立案": -0.85, "调查": -0.75, "停牌核查": -0.70,
    "业绩亏损": -0.85, "利润下滑": -0.75, "营收下降": -0.65,
    "资不抵债": -0.90, "债务违约": -0.90, "st": -0.85,
    "暂停上市": -0.95, "强制退市": -0.95,
    "重大违法": -0.90, "涉嫌": -0.70, "黑天鹅": -0.85,
    "崩盘": -0.90, "恐慌": -0.75, "踩踏": -0.80,
    "评级下调": -0.60, "卖出评级": -0.70, "弱于大盘": -0.55,
    "股东减持": -0.55, "套现": -0.50, "质押风险": -0.60,
    # ─── 行业/事件词 (有情感倾向) ───
    "新能源": 0.30, "光伏": 0.25, "半导体": 0.35,
    "人工智能": 0.40, "AI": 0.40, "芯片": 0.35,
    "国产替代": 0.45, "专精特新": 0.40, "龙头": 0.35,
    "疫情": -0.30, "贸易摩擦": -0.35, "制裁": -0.55,
    "反垄断": -0.35, "监管": -0.20, "整改": -0.40,
    # ─── 主题标签词 (不直接情感, 用于主题分组) ───
    "业绩": 0.0, "财报": 0.0, "年报": 0.0, "季报": 0.0,
    "董事会": 0.0, "股东大会": 0.0, "决议": 0.0,
    "增发": -0.20, "配股": -0.20, "可转债": 0.0,
    "股权激励": 0.30, "员工持股": 0.25,
}

# 中文停用词 (常见于新闻标题/内容中无意义的词)
STOP_WORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "之", "与", "及", "或", "但", "而", "且", "因为", "所以", "如果",
    "虽然", "但是", "然而", "不过", "例如", "比如", "以及", "关于",
    "可以", "可能", "应该", "能够", "已经", "正在", "将", "被", "把",
    "从", "对", "为", "以", "向", "于", "由", "按", "按照", "通过",
    "目前", "今日", "昨日", "本月", "今年", "本周", "本次", "此前",
    "进行", "提供", "实现", "表示", "显示", "指出", "提到", "公布",
    "发布", "报道", "记者", "获悉", "了解", "相关", "有关",
})

# 新闻标题中的情绪符号映射
SENTIMENT_EMOJI_MAP = {
    "📈": 0.5, "📉": -0.5, "💰": 0.3, "⚠️": -0.3,
    "🔥": 0.4, "💥": -0.4, "✅": 0.3, "❌": -0.3,
    "🎉": 0.4, "🌟": 0.4, "😱": -0.5, "🤔": 0.0,
}


# ═══════════════════════════════════════════════════════════════
# 模块A: 中文新闻解析 + 情感分析
# ═══════════════════════════════════════════════════════════════

def _extract_news_items(text: str) -> List[Dict]:
    """
    从统一新闻工具返回的文本中解析出单条新闻条目.
    支持: "## N. 📈/📉 标题" 格式, 以及纯文本段落分割.
    """
    if not text or not text.strip():
        return []

    items = []
    lines = text.split("\n")
    current_item = None
    current_content = []

    # 尝试解析结构化格式
    heading_pattern = re.compile(r'^##\s*\d+\.?\s*([\U0001F300-\U0001FFFF]?)\s*(.*)')
    separator_pattern = re.compile(r'^---+\s*$|^[-]{3,}$')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 检测新条目开头: "## N. 📈 Title"
        m = heading_pattern.match(stripped)
        if m:
            # 保存上一条
            if current_item:
                current_item["content"] = "\n".join(current_content).strip()
                items.append(current_item)
            current_item = {"title": m.group(2).strip(), "emoji": m.group(1), "content": ""}
            current_content = []
            continue

        # 检测分割线
        if separator_pattern.match(stripped):
            if current_item:
                current_item["content"] = "\n".join(current_content).strip()
                items.append(current_item)
            current_item = None
            current_content = []
            continue

        if current_item is not None:
            current_content.append(stripped)

    # 保存最后一条
    if current_item:
        current_item["content"] = "\n".join(current_content).strip()
        items.append(current_item)

    # 如果没有解析出任何条目, 按段落分割
    if not items:
        paragraphs = [l.strip() for l in lines if l.strip()]
        for p in paragraphs[:20]:  # 最多20段
            items.append({"title": p[:80], "emoji": "", "content": p})

    return items


def _tokenize_chinese(text: str) -> List[str]:
    """基于字符和已知词汇的简单中文分词 (无需jieba)."""
    if not text:
        return []

    # 1. 提取英文单词和数字
    tokens = []
    # 匹配英文词、数字、中文字符
    for part in re.findall(r'[a-zA-Z]+|[0-9]+\.?[0-9]*%?|[^\x00-\x7F]', text):
        part = part.strip()
        if not part:
            continue
        # 对中文字符串, 按字符拆分并对停用词过滤
        if re.match(r'^[\u4e00-\u9fff]+$', part):
            # 用滑动窗口尝试匹配已知词
            matched = False
            # 先尝试整词匹配已知词汇
            if part in FINANCIAL_SENTIMENT_LEXICON or part in STOP_WORDS:
                if part not in STOP_WORDS:
                    tokens.append(part)
                matched = True
            if not matched:
                # 按字符拆
                for ch in part:
                    if ch not in STOP_WORDS:
                        tokens.append(ch)
        else:
            if part.lower() not in STOP_WORDS:
                tokens.append(part.lower())
    return tokens


def _compute_sentiment(text: str) -> float:
    """基于情感词库计算文本情感得分 ∈ [-1, 1]."""
    tokens = _tokenize_chinese(text)
    if not tokens:
        return 0.0

    # 对每个token尝试与词库匹配 (支持多字词)
    score = 0.0
    match_count = 0

    # 对大段文本, 滑动窗口匹配已知词汇
    text_windows = text
    matched_words = set()
    # 先匹配长词 (优先匹配 4-2 字词)
    for word_len in [4, 3, 2]:
        for i in range(len(text_windows) - word_len + 1):
            word = text_windows[i:i + word_len]
            if word in matched_words:
                continue
            if word in FINANCIAL_SENTIMENT_LEXICON:
                score += FINANCIAL_SENTIMENT_LEXICON[word]
                match_count += 1
                matched_words.add(word)

    # 也检查emojis
    for ch in text:
        if ch in SENTIMENT_EMOJI_MAP:
            score += SENTIMENT_EMOJI_MAP[ch]
            match_count += 1

    if match_count == 0:
        return 0.0

    # sigmoid-like squash: 平均分映射到 [-1, 1], 但保留信号强度
    avg_score = score / match_count
    return max(-1.0, min(1.0, avg_score))


# ═══════════════════════════════════════════════════════════════
# 模块B: TF-IDF 主题聚类
# ═══════════════════════════════════════════════════════════════

def _cluster_by_topic(items: List[Dict]) -> Tuple[List[int], int]:
    """
    基于纯Python TF-IDF + 相似度聚类的主题聚类 (零外部依赖).
    返回 (cluster_labels, n_clusters).
    当条目数 < 3 时返回单簇, 免聚类.
    """
    n = len(items)
    if n < 3:
        return [0] * n, 1

    texts = [f"{item['title']} {item['content'][:200]}" for item in items]

    try:
        # ===== 纯Python TF-IDF =====
        # 1. 构建 char n-gram → 频率表
        doc_ngrams: List[Counter] = []
        all_vocab: Dict[str, int] = {}
        doc_freq: Dict[str, int] = {}
        char_ranges = [(1, 3)]  # 1-3 char n-grams

        for text in texts:
            counter: Counter = Counter()
            for start, end in char_ranges:
                for n_size in range(start, end + 1):
                    for i in range(max(0, len(text) - n_size + 1)):
                        ngram = text[i:i + n_size]
                        if ngram not in all_vocab:
                            all_vocab[ngram] = len(all_vocab)
                        counter[ngram] += 1
            for ngram in counter:
                doc_freq[ngram] = doc_freq.get(ngram, 0) + 1
            doc_ngrams.append(counter)

        # 特征裁剪: 保留最多100个高频n-gram
        max_features = 100
        if len(all_vocab) > max_features:
            total_freq: Counter = Counter()
            for ng in doc_ngrams:
                total_freq.update(ng)
            top_feats = set(w for w, _ in total_freq.most_common(max_features))
            new_vocab: Dict[str, int] = {}
            for w in sorted(top_feats):
                new_vocab[w] = len(new_vocab)
            all_vocab = new_vocab

        # 2. 计算TF-IDF向量 (numpy矩阵)
        n_docs = len(texts)
        n_vocab = len(all_vocab)
        vectors = np.zeros((n_docs, n_vocab), dtype=np.float32)

        for doc_idx, ngram_counts in enumerate(doc_ngrams):
            total = sum(ngram_counts.values())
            if total == 0:
                continue
            for ngram, count in ngram_counts.items():
                if ngram not in all_vocab:
                    continue
                tf = count / total
                idf = math.log((n_docs + 1) / (doc_freq.get(ngram, 0) + 1)) + 1
                vectors[doc_idx, all_vocab[ngram]] = tf * idf

        # 3. 余弦相似度矩阵
        sim_matrix = np.zeros((n_docs, n_docs), dtype=np.float32)
        norms = np.sqrt(np.sum(vectors ** 2, axis=1))
        for i in range(n_docs):
            if norms[i] == 0:
                continue
            for j in range(i + 1, n_docs):
                if norms[j] == 0:
                    continue
                sim = float(np.dot(vectors[i], vectors[j]) / (norms[i] * norms[j]))
                # 负相似度抹零
                sim = max(0.0, sim)
                sim_matrix[i, j] = sim
                sim_matrix[j, i] = sim

        # 4. 基于相似度阈值的连通分量聚类
        threshold = 0.12
        labels = [-1] * n_docs
        current_label = 0
        for i in range(n_docs):
            if labels[i] >= 0:
                continue
            labels[i] = current_label
            for j in range(n_docs):
                if labels[j] < 0 and sim_matrix[i, j] >= threshold:
                    labels[j] = current_label
            current_label += 1

        effective = current_label
        # 如果全部分到一簇, 用平均相似度等分
        if effective <= 1 and n_docs > 1:
            n_split = max(2, min(5, n_docs // 3))
            avg_sims = [float(np.mean(sim_matrix[i])) if n_docs > 1 else 0.0 for i in range(n_docs)]
            sorted_idx = sorted(range(n_docs), key=lambda i: avg_sims[i])
            labels = [0] * n_docs
            for rank, si in enumerate(sorted_idx):
                labels[si] = rank % n_split
            effective = n_split

        return labels, effective

    except Exception as e:
        logger.warning(f"[主题聚类] 纯Python TF-IDF 失败: {e}, 回退到单簇")
        return [0] * n, 1


# ═══════════════════════════════════════════════════════════════
# 模块C: 信息熵 + 叙事结构
# ═══════════════════════════════════════════════════════════════

def _compute_information_entropy(items: List[Dict]) -> Dict:
    """
    计算信息熵和新闻新颖性.
    基于主题分布熵、情感多样性.
    """
    n = len(items)
    if n == 0:
        return {"entropy_bits": 0.0, "novelty_score": 0.0, "surprise_index": 0.0}

    # 1. 情感分布 → 情感熵
    sentiments = [item.get("sentiment", 0.0) for item in items]
    bins = [-1.0, -0.3, 0.0, 0.3, 1.0]
    labels = ["negative", "mild_negative", "neutral", "positive"]
    hist = np.zeros(len(labels))
    for s in sentiments:
        for i in range(len(labels)):
            if bins[i] <= s <= bins[i + 1]:
                hist[i] += 1
                break
    hist = hist / max(n, 1)
    hist = hist[hist > 0]
    entropy = -np.sum(hist * np.log2(hist)) if len(hist) > 0 else 0.0
    # 归一化到 [0, log2(4)=2]
    entropy_bits = min(entropy / 2.0, 1.0)

    # 2. 新颖性: 情感极值的比例 (偏离中性的新闻占比)
    extreme_count = sum(1 for s in sentiments if abs(s) > 0.4)
    novelty_score = extreme_count / max(n, 1)

    # 3. 意外度: 情感与预期偏差 (假设预期 = 均值)
    mean_sentiment = np.mean(sentiments) if sentiments else 0.0
    surprise = np.std(sentiments) if len(sentiments) > 1 else 0.0
    surprise_index = min(surprise, 1.0)

    return {
        "entropy_bits": round(entropy_bits, 4),
        "novelty_score": round(novelty_score, 4),
        "surprise_index": round(surprise_index, 4),
        "sentiment_std": round(float(surprise), 4),
    }


def _analyze_narrative_structure(items: List[Dict], labels: List[int]) -> Dict:
    """
    分析叙事结构: 共识/分歧/异常.
    基于主题组内的情感一致性.
    """
    if not items:
        return {"consensus": 0.0, "divergence": 0.0, "anomaly_count": 0}

    # 按主题分组
    groups = defaultdict(list)
    for item, label in zip(items, labels):
        groups[int(label)].append(item)

    theme_analyses = []
    total_items = len(items)
    anomalies = []

    for group_id, group_items in groups.items():
        n = len(group_items)
        sentiments = [it.get("sentiment", 0.0) for it in group_items]
        mean_s = np.mean(sentiments) if sentiments else 0.0
        std_s = np.std(sentiments) if len(sentiments) > 1 else 0.0

        # 主题情感共识: 1 - 归一化标准差
        consensus = 1.0 - min(std_s, 1.0)

        # 代表性标题
        titles = [it.get("title", "")[:30] for it in group_items[:3]]

        theme_analyses.append({
            "theme_id": group_id,
            "count": n,
            "weight": round(n / max(total_items, 1), 3),
            "avg_sentiment": round(float(mean_s), 4),
            "consensus": round(float(consensus), 4),
            "representative": titles,
        })

        # 检测异常新闻 (与组内情感偏差 > 2std)
        if std_s > 0.01:
            for it in group_items:
                s = it.get("sentiment", 0.0)
                if abs(s - mean_s) > 2 * std_s:
                    anomalies.append({
                        "title": it.get("title", "")[:50],
                        "deviation": round(float(s - mean_s), 4),
                    })

    # 全局共识度: 加权平均
    total_weight = sum(t["weight"] for t in theme_analyses) or 1.0
    global_consensus = sum(t["consensus"] * t["weight"] for t in theme_analyses) / total_weight

    # 分歧度: 主题间情感差异
    if len(theme_analyses) > 1:
        theme_sentiments = [t["avg_sentiment"] for t in theme_analyses]
        divergence = float(np.std(theme_sentiments))
    else:
        divergence = 0.0

    return {
        "consensus": round(float(global_consensus), 4),
        "divergence": round(float(divergence), 4),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:3],  # 最多返回3条
        "theme_groups": sorted(theme_analyses, key=lambda x: x["count"], reverse=True),
    }


# ═══════════════════════════════════════════════════════════════
# 模块D: 预测编码信念更新
# ═══════════════════════════════════════════════════════════════

class PredictiveCodingFusion:
    """
    预测编码融合器: 先验信念 → 预测误差 → 后验信念更新.

    基于自由能原理的简化版:
    - 先验信念 = long-term EMA (指数移动平均)
    - 预测误差 = 当前观测 - 先验信念
    - 信念更新 = 预测误差 * 学习率 * 叙事一致性调节
    - 置信度 = 1 - 信息熵 * 0.5
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha  # EMA平滑系数

    def update(self,
               current_sentiment: float,
               prior_sentiment: float = 0.0,
               consensus: float = 0.5,
               entropy: float = 0.5,
               ) -> Dict:
        """
        执行一步预测编码信念更新.

        Args:
            current_sentiment: 当前整体情感 ∈ [-1, 1]
            prior_sentiment: 先验信念 (来自历史或默认0)
            consensus: 叙事共识度 [0, 1]
            entropy: 信息熵 [0, 1]

        Returns:
            dict: {direction, strength, confidence, prediction_error, posterior}
        """
        # 预测误差
        prediction_error = current_sentiment - prior_sentiment

        # 学习率: 共识度高时信任观测更多, 分歧大时信任先验更多
        lr = self.alpha * (0.5 + 0.5 * consensus)

        # 信念更新
        # 熵越低(信息越明确) → 更新幅度越大
        info_quality = 1.0 - entropy * 0.5
        belief_update = prediction_error * lr * info_quality

        # 后验信念
        posterior = prior_sentiment + belief_update
        posterior = max(-1.0, min(1.0, posterior))

        # 方向判断
        if posterior > 0.15:
            direction = "bullish"
        elif posterior < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"

        # 置信度: 共识高+熵低 → 置信度高
        confidence = (0.5 + 0.3 * consensus - 0.2 * entropy)
        confidence = max(0.1, min(0.95, confidence))

        # 信号强度
        strength = abs(posterior)

        return {
            "direction": direction,
            "strength": round(float(strength), 4),
            "confidence": round(float(confidence), 4),
            "prior": round(float(prior_sentiment), 4),
            "prediction_error": round(float(prediction_error), 4),
            "posterior_sentiment": round(float(posterior), 4),
            "belief_update": round(float(belief_update), 4),
        }


# ═══════════════════════════════════════════════════════════════
# 主入口: 完整数学层
# ═══════════════════════════════════════════════════════════════

def run_full_math_layer(news_text: str,
                        ticker: str = "",
                        prior_sentiment: float = 0.0,
                        ) -> Dict:
    """
    对新闻文本执行完整数学层分析.

    Args:
        news_text: 统一新闻工具返回的原始文本
        ticker: 股票代码
        prior_sentiment: 先验情感信念 (来自历史或默认0)

    Returns:
        dict: 全部计算好的特征
            {
                "overall_sentiment": float,
                "news_count": int,
                "entropy": {...},
                "narrative": {...},
                "belief_update": {...},
                "top_news": [...]
            }
    """
    start = datetime.now()
    logger.info(f"[news_math] 开始分析 {ticker}, 文本长度={len(news_text) if news_text else 0}")

    if not news_text or not news_text.strip():
        logger.warning("[news_math] 新闻文本为空, 返回默认特征")
        return {
            "overall_sentiment": 0.0,
            "news_count": 0,
            "entropy": {"entropy_bits": 0.0, "novelty_score": 0.0, "surprise_index": 0.0},
            "narrative": {"consensus": 0.0, "divergence": 0.0, "anomaly_count": 0, "theme_groups": []},
            "belief_update": {"direction": "neutral", "strength": 0.0, "confidence": 0.1},
            "top_news": [],
            "compute_time_ms": 0.0,
        }

    # Phase 1A: 解析 + 情感
    items = _extract_news_items(news_text)
    for item in items:
        full_text = f"{item['title']} {item['content']}"
        item["sentiment"] = _compute_sentiment(full_text)
        # 将emoji情感叠加
        if item.get("emoji") in SENTIMENT_EMOJI_MAP:
            item["sentiment"] = (item["sentiment"] + SENTIMENT_EMOJI_MAP[item["emoji"]]) / 2

    logger.info(f"[news_math] 解析出 {len(items)} 条新闻, 情感计算完成")

    if not items:
        return _empty_result()

    # Phase 1B: 主题聚类
    labels, n_clusters = _cluster_by_topic(items)

    # Phase 1C: 信息熵
    entropy = _compute_information_entropy(items)

    # Phase 1D: 叙事结构
    narrative = _analyze_narrative_structure(items, labels)

    # Phase 2: 预测编码信念更新
    overall_sentiment = float(np.mean([it.get("sentiment", 0.0) for it in items]))
    predictor = PredictiveCodingFusion()
    belief = predictor.update(
        current_sentiment=overall_sentiment,
        prior_sentiment=prior_sentiment,
        consensus=narrative["consensus"],
        entropy=entropy["entropy_bits"],
    )

    # 选择最值得关注的新闻 (异常 + 极端情感)
    top_news = []
    # 异常新闻优先
    for anom in narrative.get("anomalies", []):
        top_news.append(anom["title"])
    # 补充极端情感新闻
    sorted_items = sorted(items, key=lambda x: abs(x.get("sentiment", 0.0)), reverse=True)
    for item in sorted_items:
        title = item.get("title", "")[:60]
        if title and title not in top_news:
            top_news.append(title)
        if len(top_news) >= 5:
            break

    elapsed = (datetime.now() - start).total_seconds() * 1000

    result = {
        "overall_sentiment": round(float(overall_sentiment), 4),
        "news_count": len(items),
        "topic_count": n_clusters,
        "entropy": entropy,
        "narrative": narrative,
        "belief_update": belief,
        "top_news": top_news[:5],
        "compute_time_ms": round(elapsed, 1),
    }

    logger.info(f"[news_math] 完成: sentiment={overall_sentiment:.3f}, "
                f"belief={belief['direction']}, "
                f"themes={n_clusters}, time={elapsed:.0f}ms")
    return result


def _empty_result() -> Dict:
    return {
        "overall_sentiment": 0.0,
        "news_count": 0,
        "topic_count": 0,
        "entropy": {"entropy_bits": 0.0, "novelty_score": 0.0, "surprise_index": 0.0},
        "narrative": {"consensus": 0.0, "divergence": 0.0, "anomaly_count": 0, "theme_groups": []},
        "belief_update": {"direction": "neutral", "strength": 0.0, "confidence": 0.1, "prior": 0.0,
                          "prediction_error": 0.0, "posterior_sentiment": 0.0, "belief_update": 0.0},
        "top_news": [],
        "compute_time_ms": 0.0,
    }
