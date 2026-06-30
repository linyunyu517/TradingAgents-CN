"""
Debate key points extraction utilities for incremental summarization.

Extracts the most information-dense sentences from each debate round
using pure Python rule-based scoring (~1ms). No LLM calls needed.
"""

import re
from typing import List

# ── scoring weights ──────────────────────────────────────────────
_PRICE_WEIGHT = 3     # "XX元" price targets
_STANCE_WEIGHT = 3    # 买入/卖出/持有 etc.
_ARG_WEIGHT = 2       # 因为/理由/核心 etc.
_FIN_WEIGHT = 2       # 营收/PE/ROE etc.
_NUM_WEIGHT = 1       # any number

# ── patterns ─────────────────────────────────────────────────────
_PRICE_RE = re.compile(r'[\d]+\.?[\d]*[\s-]*[元美元]')
_SENTENCE_SPLIT_RE = re.compile(r'[。！？\n]')

_STANCE_WORDS = frozenset({
    "买入", "卖出", "持有", "看涨", "看跌", "推荐",
    "增持", "减持", "建议买入", "建议卖出", "强烈推荐",
})

_ARG_MARKERS = frozenset({
    "因为", "因此", "理由是", "核心", "关键",
    "首先", "其次", "最后", "综上", "总体来看",
    "更重要的是", "值得注意的是",
})

_FIN_TERMS = frozenset({
    "营收", "利润", "收入", "成本", "毛利率", "净利率",
    "PE", "PB", "ROE", "ROA", "增长", "下降", "提升",
    "改善", "恶化", "风险", "机会", "估值", "市盈率",
    "市净率", "股息", "现金流", "负债", "资产", "股东",
    "回报", "收益率", "目标价",
})


def extract_debate_key_points(text: str, speaker: str) -> List[str]:
    """Extract key points from a single debate response (~150 chars).

    Algorithm
    --------
    1. Split into sentences
    2. Score each sentence by information density
    3. Return top-scored sentences (max ~150 chars total)

    Returns empty list if nothing meaningful found (fallback to
    first non-trivial sentence).
    """
    raw_sentences = _SENTENCE_SPLIT_RE.split(text)
    sentences = [s.strip() for s in raw_sentences if s.strip() and len(s.strip()) > 1]

    scored: List[tuple] = []
    for sent in sentences:
        score = 0
        if _PRICE_RE.search(sent):
            score += _PRICE_WEIGHT
        if any(w in sent for w in _STANCE_WORDS):
            score += _STANCE_WEIGHT
        if any(m in sent for m in _ARG_MARKERS):
            score += _ARG_WEIGHT
        if any(t in sent for t in _FIN_TERMS):
            score += _FIN_WEIGHT
        if re.search(r"\d+", sent):
            score += _NUM_WEIGHT
        if score > 0:
            scored.append((score, sent))

    scored.sort(key=lambda x: x[0], reverse=True)

    result: List[str] = []
    total_len = 0
    MAX_CHARS = 150
    for _score, sent in scored[:5]:
        line = f"[{speaker}] {sent}"
        if total_len + len(line) > MAX_CHARS and result:
            break
        result.append(line)
        total_len += len(line)

    # fallback
    if not result:
        for s in sentences[:3]:
            if len(s) > 10:
                result.append(f"[{speaker}] {s[:80]}")
                break

    return result


def merge_key_points(existing: str, new_points: List[str], max_chars: int = 600) -> str:
    """Append deduplicated key points to the running summary.

    Dedup strategy: first 30 chars (fingerprint). If the same
    fingerprint already exists in *any* line, skip the new point.
    """
    if not new_points:
        return existing

    # Build fingerprint set from existing summary
    existing_lines = set(existing.split("\n")) if existing else set()
    seen_fingerprints: set = set()
    for line in existing_lines:
        fp = line[:30].strip()
        if fp:
            seen_fingerprints.add(fp)

    new_lines: List[str] = []
    for pt in new_points:
        fp = pt[:30]
        if fp not in seen_fingerprints:
            new_lines.append(pt)
            seen_fingerprints.add(fp)

    if not new_lines:
        return existing

    updated = existing.rstrip("\n")
    if updated:
        updated += "\n"
    updated += "\n".join(new_lines)

    # Hard cap
    if len(updated) > max_chars:
        mid = max_chars // 2
        updated = updated[:mid] + "\n...(truncated)...\n" + updated[-mid:]

    return updated
