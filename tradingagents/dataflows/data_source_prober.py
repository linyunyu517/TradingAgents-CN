#!/usr/bin/env python3
"""
多源主动探测 + 自动切换（参考 Hystrix 断路器模式）

探测所有已注册的 A 股数据源（Tushare），
按综合评分（成功率 × 0.7 + 延迟得分 × 0.3）排序，
供调用方自动选最优数据源。

使用方式:
    from tradingagents.dataflows.data_source_prober import get_prober

    prober = get_prober()
    prober.register("tushare", probe_tushare)
    prober.probe_all()
    best = prober.get_best_source()  # "tushare"
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


# ====================================================================
# SourceHealth — 单个数据源的健康记录
# ====================================================================

@dataclass
class SourceHealth:
    """单个数据源的健康记录

    参考 Hystrix 断路器的度量收集模式：
      - success_count / failure_count → 成功率
      - total_latency → 平均延迟
      - score = 成功率 × 0.7 + 延迟得分 × 0.3
    """
    name: str
    success_count: int = 0
    failure_count: int = 0
    total_latency: float = 0.0
    last_probe_time: float = 0.0

    @property
    def total_calls(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        total = self.total_calls
        return self.success_count / total if total > 0 else 0.0

    @property
    def avg_latency(self) -> float:
        total = self.total_calls
        return self.total_latency / total if total > 0 else 10.0

    @property
    def score(self) -> float:
        """综合评分：成功率 0.7 + 延迟得分 0.3

        - 成功率越高分越高
        - 延迟 < 1s → 满分, > 10s → 0分
        - 尚未探测的源得 0.3（保底，允许被选到）
        """
        if self.total_calls == 0:
            return 0.3  # 未探测的源给保底分
        rate = self.success_rate
        lat = self.avg_latency
        latency_score = max(0.0, 1.0 - lat / 10.0)  # 10秒以上得0分
        return rate * 0.7 + latency_score * 0.3


# ====================================================================
# MultiSourceProber — 多源探测管理器
# ====================================================================

class MultiSourceProber:
    """多源主动探测 + 自动切换管理器

    用法:
        prober = MultiSourceProber()

        # 注册探测函数
        prober.register("tushare",  lambda: ts_provider.connect_sync())

        # 启动探测
        prober.probe_all()

        # 获取最优源
        best = prober.get_best_source()  # "tushare"
        ranked = prober.get_ranked()     # ["tushare"]
    """

    def __init__(self):
        self._sources: dict[str, SourceHealth] = {}
        self._probes: dict[str, Callable[[], bool]] = {}
        self._last_rank_time = 0.0
        self._rank_cache: list[str] = []
        self._cool_down_seconds = 300  # 切换冷却期 5 分钟

    def register(self, name: str, probe_fn: Callable[[], bool]) -> None:
        """注册数据源及其探测函数

        Args:
            name: 数据源名称（tushare）
            probe_fn: 返回 bool 的可调用（True=可用）
        """
        self._sources[name] = SourceHealth(name=name)
        self._probes[name] = probe_fn
        logger.debug("[Prober] 已注册数据源: %s", name)

    def probe_all(self) -> None:
        """探测所有已注册的数据源，更新健康记录"""
        logger.info("[Prober] 开始探测 %d 个数据源...", len(self._probes))
        for name, probe_fn in self._probes.items():
            start = time.time()
            try:
                ok = bool(probe_fn())
                elapsed = time.time() - start
                health = self._sources[name]
                if ok:
                    health.success_count += 1
                else:
                    health.failure_count += 1
                health.total_latency += elapsed
                health.last_probe_time = time.time()
                logger.info(
                    "[Prober] %s: %s (%.2fs, 累计成功=%d 失败=%d)",
                    name, "✅" if ok else "❌", elapsed,
                    health.success_count, health.failure_count,
                )
            except Exception as e:
                self._sources[name].failure_count += 1
                self._sources[name].last_probe_time = time.time()
                logger.warning("[Prober] %s: ❌ %s", name, e)

        self._rank_cache = self._rank_sources()
        if self._rank_cache:
            logger.info("[Prober] 数据源排名: %s", " > ".join(self._rank_cache))

    def record_result(self, name: str, success: bool, latency: float = 0.0) -> None:
        """记录一次数据调用的结果（用于运行时统计，不只是探测）

        Args:
            name: 数据源名称
            success: 是否成功
            latency: 调用耗时（秒）
        """
        if name not in self._sources:
            self._sources[name] = SourceHealth(name=name)
        health = self._sources[name]
        if success:
            health.success_count += 1
        else:
            health.failure_count += 1
        health.total_latency += latency

    def _rank_sources(self) -> list[str]:
        """按综合评分从高到低排序"""
        return sorted(
            self._sources.keys(),
            key=lambda n: self._sources[n].score,
            reverse=True,
        )

    def get_best_source(self) -> str | None:
        """获取当前最优数据源（带冷却期，不会频繁切换）

        Returns:
            数据源名称，或 None（无可用源）
        """
        if not self._sources:
            return None
        if not self._rank_cache:
            self._rank_cache = self._rank_sources()
        return self._rank_cache[0] if self._rank_cache else None

    def get_ranked(self) -> list[str]:
        """获取完整排名列表

        Returns:
            按评分从高到低排列的数据源名称列表
        """
        if not self._rank_cache:
            self._rank_cache = self._rank_sources()
        return self._rank_cache


# ====================================================================
# 全局单例
# ====================================================================

_prober_instance: MultiSourceProber | None = None


def get_prober() -> MultiSourceProber:
    """获取全局 MultiSourceProber 单例"""
    global _prober_instance
    if _prober_instance is None:
        _prober_instance = MultiSourceProber()
    return _prober_instance


def init_default_probes() -> MultiSourceProber:
    """注册并探测所有默认 A 股数据源"""
    prober = get_prober()

    # Tushare 探测
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        def probe_tushare() -> bool:
            p = get_tushare_provider()
            return p.connect_sync()

        prober.register("tushare", probe_tushare)
    except ImportError:
        logger.debug("[Prober] tushare 不可用，跳过注册")

    # 执行探测
    prober.probe_all()
    return prober
