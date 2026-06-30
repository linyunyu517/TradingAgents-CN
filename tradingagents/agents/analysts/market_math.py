#!/usr/bin/env python3
"""
市场数学模块 - 因果拓扑流形分析器 Phase1【器】
=====================================================
为市场分析师提供数学结构提取层，包括：
1. TDA 拓扑数据分析（持续同调）
2. VMD 变分模态分解（多尺度分解）
3. 传递熵因果发现（成交量-价格因果方向）
4. 市场状态分类（相态检测）

设计原则：
- 所有计算可选降级（库不存在时优雅跳过）
- 所有计算<2秒
- 输入输出均为标准 NumPy 数组
- 纯函数，无副作用

理论根基：
- TDA ↔ 拓扑学（持续同调理论）
- VMD ↔ 信号处理（变分模态分解）
- 传递熵 ↔ 信息论 / 因果发现
- 相变检测 ↔ 复杂系统临界性理论
"""

import logging
import warnings
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")
logger = logging.getLogger("default")

# ============================================================
# 库可用性检测（优雅降级）
# ============================================================
_TDA_AVAILABLE = False
_VMD_AVAILABLE = False
_PERSIM_AVAILABLE = False
_CCM_AVAILABLE = False

try:
    from ripser import ripser
    _TDA_AVAILABLE = True
except ImportError:
    pass

try:
    from vmdpy import VMD
    _VMD_AVAILABLE = True
except ImportError:
    pass

try:
    from persim import sliced_wasserstein
    _PERSIM_AVAILABLE = True
except ImportError:
    pass




# ============================================================
# Phase 1【器】- 1. 拓扑数据分析 (TDA)
# ============================================================
def _takens_embedding(signal: np.ndarray, dim: int = 3, tau: int = 1) -> np.ndarray:
    """
    Takens 嵌入：将一维时间序列重构为相空间点云。
    当 giotto-tda 不可用时使用简单实现。

    Args:
        signal: 一维时间序列
        dim: 嵌入维度（默认3，足够捕获市场动力学）
        tau: 时间延迟（默认1，日线数据相邻天）

    Returns:
        (n_points, dim) 维相空间点云
    """
    n = len(signal) - (dim - 1) * tau
    if n < 2:
        return np.empty((0, dim))
    return np.array([signal[i: i + dim * tau: tau] for i in range(n)])


def compute_tda_features(close_prices: np.ndarray) -> dict[str, Any]:
    """
    计算价格序列的拓扑特征。

    Args:
        close_prices: 收盘价序列 (n_days,)

    Returns:
        dict: {
            "available": bool,
            "betti_1": int,          # 1维空洞数（异常结构）
            "max_persistence": float, # 最大持续长度（结构重要性）
            "embed_dim": int,         # 嵌入维度
            "tau": int,              # 时间延迟
            "topological_entropy": float,  # 拓扑熵（复杂度指标）
        }
    """
    if not _TDA_AVAILABLE or len(close_prices) < 15:
        return {"available": False}

    try:
        # Step 1: 自适应嵌入参数
        dim = min(5, len(close_prices) // 10)
        dim = max(2, dim)  # 至少2维
        tau = 1

        # Step 2: Takens 嵌入
        point_cloud = _takens_embedding(close_prices, dim=dim, tau=tau)
        if point_cloud.shape[0] < 5:
            return {"available": False}

        # Step 3: 计算持续同调（H0 + H1）
        diagrams = ripser(point_cloud, maxdim=1)["dgms"]

        # H1（1维空洞）分析
        h1 = diagrams[1]
        if len(h1) == 0:
            return {
                "available": True,
                "betti_1": 0,
                "max_persistence": 0.0,
                "embed_dim": dim,
                "tau": tau,
                "topological_entropy": 0.0,
            }

        # 过滤噪声（只保留持续长度 > 中位数的特征）
        persistence = h1[:, 1] - h1[:, 0]
        threshold = np.median(persistence) if len(persistence) > 1 else 0
        significant = persistence > threshold

        # 拓扑熵 = 持久熵（信息论视角）
        if np.sum(persistence) > 0:
            prob = persistence / np.sum(persistence)
            topo_entropy = -np.sum(prob * np.log(prob + 1e-10))
        else:
            topo_entropy = 0.0

        return {
            "available": True,
            "betti_1": int(np.sum(significant)),
            "max_persistence": float(np.max(persistence)),
            "embed_dim": dim,
            "tau": tau,
            "topological_entropy": float(topo_entropy),
        }

    except Exception as e:
        logger.warning(f"⚠️ [TDA] 计算失败(非致命): {e}")
        return {"available": False}


# ============================================================
# Phase 1【器】- 2. 变分模态分解 (VMD 多尺度分解)
# ============================================================
def compute_vmd_features(close_prices: np.ndarray, K: int = 4) -> dict[str, Any]:
    """
    将价格序列分解为K个内蕴模态函数（IMF），
    分别对应不同时间尺度的市场动力学。

    Args:
        close_prices: 收盘价序列
        K: 模态数（默认4：超短期/短期/中期/长期）

    Returns:
        dict: {
            "available": bool,
            "mode_{i}_trend": float,   # 模态i的净趋势
            "mode_{i}_std": float,     # 模态i的波动率
            "dominant_mode": int,      # 主导模态（能量最大）
            "mode_energy_ratio": [float, ...],  # 各模态能量占比
        }
    """
    if not _VMD_AVAILABLE or len(close_prices) < 20:
        return {"available": False}

    try:
        # VMD 分解
        u, _, _ = VMD(
            close_prices, alpha=2000, tau=0, K=K, DC=0, init=1, tol=1e-7,
        )

        features: dict[str, Any] = {"available": True}
        energies = []

        for i in range(K):
            mode = u[i, :]
            trend = float(mode[-1] - mode[0])
            std = float(np.std(mode))
            energy = float(np.sum(mode**2))
            energies.append(energy)

            features[f"mode_{i}_trend"] = trend
            features[f"mode_{i}_std"] = std

        total_energy = sum(energies)
        energy_ratios = [e / total_energy if total_energy > 0 else 0 for e in energies]

        features["dominant_mode"] = int(np.argmax(energies))
        features["mode_energy_ratio"] = energy_ratios

        return features

    except Exception as e:
        logger.warning(f"⚠️ [VMD] 计算失败(非致命): {e}")
        return {"available": False}


# ============================================================
# Phase 1【器】- 3. 传递熵因果发现
# ============================================================
def compute_causal_features(
    close_prices: np.ndarray, volumes: np.ndarray,
) -> dict[str, Any]:
    """
    用量-价 滞后交叉相关分析，判断因果方向。

    原理：Granger因果的简化版本—如果量(t)能预测价(t+1)，
    则量→价有因果流。反之亦然。

    Args:
        close_prices: 收盘价序列
        volumes: 成交量序列

    Returns:
        dict: {
            "available": bool,
            "causal_direction": str,     # "量驱动价" / "价驱动量" / "双向" / "无显著因果"
            "te_volume_to_price": float, # 量→价的相关强度（滞后1期）
            "te_price_to_volume": float, # 价→量的相关强度（滞后1期）
        }
    """
    if len(close_prices) < 30 or len(volumes) < 30:
        return {"available": False}

    try:
        # 计算收益率（标准化量价至同一量纲）
        price_ret = np.diff(np.log(close_prices + 1e-10))
        vol_ret = np.diff(np.log(volumes + 1e-10))

        # 滞后交叉相关（滞后1期）
        # 量(t) → 价(t+1)
        lag_vp = min(len(vol_ret) - 1, len(price_ret) - 1)
        te_vp = float(np.corrcoef(vol_ret[:lag_vp], price_ret[1:lag_vp + 1])[0, 1])
        te_vp = abs(te_vp) if not np.isnan(te_vp) else 0.0

        # 价(t) → 量(t+1)
        lag_pv = min(len(price_ret) - 1, len(vol_ret) - 1)
        te_pv = float(np.corrcoef(price_ret[:lag_pv], vol_ret[1:lag_pv + 1])[0, 1])
        te_pv = abs(te_pv) if not np.isnan(te_pv) else 0.0

        # 判断方向（阈值0.1：超过10%的线性预测力）
        threshold = 0.1
        vp_significant = te_vp > threshold
        pv_significant = te_pv > threshold

        if vp_significant and pv_significant:
            direction = "双向" if abs(te_vp - te_pv) < 0.05 else \
                ("量驱动价" if te_vp > te_pv else "价驱动量")
        elif vp_significant:
            direction = "量驱动价"
        elif pv_significant:
            direction = "价驱动量"
        else:
            direction = "无显著因果"

        return {
            "available": True,
            "causal_direction": direction,
            "te_volume_to_price": round(te_vp, 4),
            "te_price_to_volume": round(te_pv, 4),
        }

    except Exception as e:
        logger.warning(f"⚠️ [因果] 计算失败(非致命): {e}")
        return {"available": False}


# ============================================================
# Phase 2【术】- 市场状态分类
# ============================================================
def compute_regime_features(
    close_prices: np.ndarray,
    tda_features: dict | None = None,
) -> dict[str, Any]:
    """
    基于统计特征 + 拓扑特征进行市场状态分类。

    Args:
        close_prices: 收盘价序列
        tda_features: TDA 特征（可选，用于增强分类）

    Returns:
        dict: {
            "volatility_regime": str,    # "低波动" / "正常波动" / "高波动"
            "trend_regime": str,         # "上涨" / "震荡" / "下跌"
            "regime_confidence": float,  # 分类置信度 (0-1)
            "critical_slowing": bool,    # 是否临界慢化（相变前兆）
            "combined_state": str,       # 综合状态描述
        }
    """
    if len(close_prices) < 10:
        return {"available": False}

    try:
        # === 波动率状态 ===
        log_returns = np.diff(np.log(close_prices + 1e-10))
        volatility = float(np.std(log_returns)) if len(log_returns) > 1 else 0.0

        if volatility < 0.01:
            vol_regime = "低波动"
        elif volatility < 0.03:
            vol_regime = "正常波动"
        else:
            vol_regime = "高波动"

        # === 趋势状态 ===
        short_window = min(5, len(close_prices))
        mid_window = min(20, len(close_prices))

        short_sma = np.mean(close_prices[-short_window:])
        mid_sma = np.mean(close_prices[-mid_window:])
        trend_strength = (short_sma / mid_sma - 1) if mid_sma > 0 else 0

        if abs(trend_strength) < 0.02:
            trend_regime = "震荡"
        elif trend_strength > 0:
            trend_regime = "上涨"
        else:
            trend_regime = "下跌"

        # === 临界慢化检测（Fisher 信息近似） ===
        # 原理：系统接近临界点时，自相关↑ 方差↑ 恢复率↓
        recent = close_prices[-min(30, len(close_prices)):]
        if len(recent) > 5:
            lag1_autocorr = float(np.corrcoef(recent[:-1], recent[1:])[0, 1])
            # Fisher 信息估计：高自相关 + 高方差 = 靠近临界点
            fisher = (1 - abs(lag1_autocorr)) * (1 + volatility)
            critical_slowing = fisher < 0.3  # Fisher信息低 = 临界慢化
        else:
            lag1_autocorr = 0.0
            critical_slowing = False

        # === 综合状态 ===
        if critical_slowing and trend_strength > 0.05:
            combined = f"{trend_regime}末期(临界)"
        elif critical_slowing and trend_strength < -0.05:
            combined = f"{trend_regime}末期(筑底)"
        else:
            combined = f"{trend_regime}+{vol_regime}"

        return {
            "available": True,
            "volatility_regime": vol_regime,
            "trend_regime": trend_regime,
            "regime_confidence": round(1 - volatility, 2),
            "critical_slowing": bool(critical_slowing),
            "lag1_autocorr": round(float(lag1_autocorr), 4),
            "combined_state": combined,
        }

    except Exception as e:
        logger.warning(f"⚠️ [Regime] 计算失败(非致命): {e}")
        return {"available": False}


# ============================================================
# 统一入口：一句话计算所有数学特征
# ============================================================
def compute_all_features(
    close_prices: np.ndarray,
    volumes: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    一次调用，计算所有数学特征（TDA + VMD + Causal + Regime）。

    Args:
        close_prices: 收盘价序列 (n_days,)
        volumes: 成交量序列 (n_days,)，可选

    Returns:
        dict: {
            "tda": {...},
            "vmd": {...},
            "causal": {...},
            "regime": {...},
            "computation_time_ms": float,  # 总计算时间（毫秒）
        }
    """
    import time

    t0 = time.perf_counter()

    result = {
        "tda": compute_tda_features(close_prices),
        "vmd": compute_vmd_features(close_prices, K=4),
        "regime": compute_regime_features(close_prices),
    }

    # 因果发现需要成交量数据
    if volumes is not None and len(volumes) == len(close_prices):
        result["causal"] = compute_causal_features(close_prices, volumes)
    else:
        result["causal"] = {"available": False}

    # 将TDA特征注入regime（增强分类）
    tda_feats = result.get("tda", {})
    if tda_feats.get("available") and tda_feats.get("betti_1", 0) > 2:
        regime = result.get("regime", {})
        if regime.get("available"):
            regime["combined_state"] = f"{regime.get('combined_state', '未知')}+异常结构"

    t1 = time.perf_counter()
    result["computation_time_ms"] = round((t1 - t0) * 1000, 1)

    return result
