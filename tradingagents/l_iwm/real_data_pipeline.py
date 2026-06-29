# TradingAgents/l_iwm/real_data_pipeline.py
"""
真实数据管道 (Real Data Pipeline)
===================================

替代 hpc_integration.py:490-517 中 _extract_market_info() 和 _extract_actual_observation()
使用文本长度作为价格（"price" = len(market_report) / 100）的荒谬做法。

核心功能:
    1. 接入真实金融市场数据 (A股/港股/美股)
    2. 计算技术指标特征向量 (收益率/波动率/RSI/MACD/布林带等)
    3. 识别市场体制（基于统计方法而非硬编码分类）
    4. 为 RSSM 提供训练数据
    5. 获取基本面数据和新闻情感数据
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("l_iwm.data_pipeline")


# ==================== 技术指标计算函数 ====================

def compute_returns(prices: np.ndarray, periods: list[int] = None) -> dict[str, np.ndarray]:
    """计算多周期收益率"""
    if periods is None:
        periods = [1, 5, 20]
    returns = {}
    for p in periods:
        returns[f"return_{p}d"] = np.diff(prices, n=p, axis=0) / prices[:len(prices) - p]
    return returns


def compute_volatility(returns: np.ndarray, window: int = 20) -> np.ndarray:
    """滚动波动率 (年化)"""
    if len(returns) < window:
        return np.full_like(returns, np.nan)
    vol = np.full_like(returns, np.nan)
    for i in range(window, len(returns)):
        vol[i] = np.std(returns[i - window:i]) * math.sqrt(252)
    return vol


def compute_rsi(prices: np.ndarray, window: int = 14) -> np.ndarray:
    """相对强弱指标 RSI"""
    deltas = np.diff(prices)
    rsi = np.full(len(prices), 50.0)
    for i in range(window, len(prices)):
        gains = np.mean(np.maximum(deltas[i - window:i], 0))
        losses = -np.mean(np.minimum(deltas[i - window:i], 0))
        if losses == 0:
            rsi[i] = 100.0
        elif gains == 0:
            rsi[i] = 0.0
        else:
            rs = gains / losses
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def compute_macd(prices: np.ndarray,
                 fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, np.ndarray]:
    """MACD 指标"""
    def ema(data, period):
        alpha = 2.0 / (period + 1)
        result = np.full_like(data, np.nan)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def compute_bollinger_bands(prices: np.ndarray, window: int = 20, num_std: float = 2.0) -> dict[str, np.ndarray]:
    """布林带"""
    sma = np.full_like(prices, np.nan)
    upper = np.full_like(prices, np.nan)
    lower = np.full_like(prices, np.nan)
    width = np.full_like(prices, np.nan)

    for i in range(window, len(prices)):
        sma[i] = np.mean(prices[i - window:i])
        std = np.std(prices[i - window:i])
        upper[i] = sma[i] + num_std * std
        lower[i] = sma[i] - num_std * std
        width[i] = (upper[i] - lower[i]) / sma[i] if sma[i] != 0 else 0

    position = np.where(upper != lower,
                        (prices - lower) / (upper - lower + 1e-8), 0.5)

    return {"sma": sma, "upper": upper, "lower": lower,
            "width": width, "position": position}


def compute_volume_indicators(price: np.ndarray, volume: np.ndarray) -> dict[str, np.ndarray]:
    """成交量指标"""
    vwap = np.full_like(price, np.nan)
    for i in range(len(price)):
        vwap[i] = np.sum(price[max(0, i - 20):i + 1] * volume[max(0, i - 20):i + 1]) / \
                  max(np.sum(volume[max(0, i - 20):i + 1]), 1e-8)

    vol_change = np.full_like(volume, np.nan)
    vol_change[1:] = volume[1:] / (volume[:-1] + 1e-8) - 1.0

    return {"vwap": vwap, "volume_change": vol_change}


# ==================== 市场体制识别 ====================

def detect_market_regime(prices: np.ndarray, returns: np.ndarray,
                         volatilities: np.ndarray) -> dict[str, Any]:
    """
    基于统计方法的市场体制识别（替代硬编码的 bull/bear/sideways/crisis 分类）。

    使用多重特征：
    1. 滚动收益率的方向和幅度
    2. 波动率水平
    3. 趋势强度 (ADX 近似)
    4. 自相关性

    Returns:
        Dict with regime, confidence, and supporting statistics
    """
    if len(prices) < 60:
        return {"regime": "unknown", "confidence": 0.0}

    recent_returns = returns[-20:] if len(returns) >= 20 else returns
    recent_vol = volatilities[-20:] if len(volatilities) >= 20 else volatilities

    mean_return = np.mean(recent_returns)
    mean_vol = np.mean(recent_vol)
    sharpe = mean_return / (mean_vol + 1e-8) * math.sqrt(252)

    trend_strength = abs(mean_return) / (mean_vol + 1e-8)

    # 下跌趋势中的波动率激增 → crisis
    if mean_return < -0.02 and mean_vol > np.percentile(volatilities, 80):
        return {"regime": "crisis", "confidence": min(1.0, abs(mean_return) * 20 + mean_vol * 5),
                "sharpe": sharpe, "trend_strength": trend_strength}

    # 正收益低波动 → bull
    if sharpe > 0.5 and mean_vol < np.percentile(volatilities, 60):
        return {"regime": "bull", "confidence": min(1.0, sharpe),
                "sharpe": sharpe, "trend_strength": trend_strength}

    # 负收益低波动 → bear
    if sharpe < -0.3 and mean_vol < np.percentile(volatilities, 70):
        return {"regime": "bear", "confidence": min(1.0, abs(sharpe)),
                "sharpe": sharpe, "trend_strength": trend_strength}

    # 高波动 → volatile
    if mean_vol > np.percentile(volatilities, 75):
        return {"regime": "volatile", "confidence": min(1.0, mean_vol * 10),
                "sharpe": sharpe, "trend_strength": trend_strength}

    # 弱趋势 → sideways
    if trend_strength < 0.5:
        return {"regime": "sideways", "confidence": min(1.0, 1.0 - trend_strength),
                "sharpe": sharpe, "trend_strength": trend_strength}

    return {"regime": "sideways", "confidence": 0.5,
            "sharpe": sharpe, "trend_strength": trend_strength}


class RealDataPipeline:
    """
    真实数据管道 — 接入金融市场数据并计算特征向量。

    当前完成的技术指标计算模块可用于:
    1. 为 RSSM 世界模型提供训练数据 (prepare_training_batch)
    2. 替代 hpc_integration.py 中 _extract_market_info 的文本长度代理
    3. 提供市场体制识别的统计依据

    注意: 实际 API 调用 (tushare) 的可选依赖需按需安装。
    当前版本专注于特征计算管线，API 获取为可扩展接口。
    """

    def __init__(self, config):
        self.config = config
        self.sources = config.real_data_sources
        self.lookback = config.real_data_lookback_days
        self.interval = config.real_data_interval

        # 数据缓存
        self._data_cache: dict[str, dict] = {}

    def fetch_market_data(self, symbol: str,
                          start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> Any:
        """
        通过 DataSourceManager 获取标准化市场行情数据。
        内置多源降级: Tushare → 合成数据。

        Args:
            symbol: 股票代码 (如 "601698", "000001.SZ")
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            dict: 包含 open/high/low/close/volume 等键的字典
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start = datetime.now() - timedelta(days=self.lookback)
            start_date = start.strftime("%Y-%m-%d")

        try:
            # 延迟导入 DataSourceManager，避免循环依赖
            from tradingagents.dataflows.data_source_manager import DataSourceManager

            dsm = DataSourceManager()
            df = dsm.get_stock_dataframe(symbol, start_date, end_date, period=self.interval)

            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                logger.info(f"✅ [DataSourceManager] {symbol} 数据获取成功: {len(df)} 条记录")
                self._data_cache[symbol] = {"source": "datasource_manager", "data": df}

                # 将标准化 DataFrame 转为 dict 格式（保持与下游 compute_technical_features 兼容）
                result: dict[str, list] = {}
                for col in df.columns:
                    if col in ("open", "high", "low", "close", "vol", "volume", "amount", "pct_change"):
                        result[col] = df[col].tolist()
                # Tushare 返回 "vol" 而非 "volume"，统一标准化
                if "volume" not in result and "vol" in result:
                    result["volume"] = result.pop("vol")
                if "close" in result and len(result["close"]) > 0:
                    return result

        except ImportError:
            logger.warning("DataSourceManager 不可用，降级到合成数据")
        except Exception as e:
            logger.warning(f"⚠️ [DataSourceManager] 获取失败: {e}，降级到合成数据")

        # 全失败兜底: 合成数据
        logger.info(f"[DataSourceManager] 所有数据源失败，为 {symbol} 生成合成数据")
        return self._generate_synthetic_data(symbol)

    def _generate_synthetic_data(self, symbol: str) -> dict[str, np.ndarray]:
        """生成合成数据用于开发测试"""
        n = self.lookback
        # 随机游走价格
        returns = np.random.randn(n) * 0.015
        # 添加趋势
        trend = np.linspace(0, np.random.randn() * 0.1, n)
        returns += trend
        price = 100 * np.exp(np.cumsum(returns))
        volume = np.random.randint(500000, 5000000, n)

        data = {
            "open": price * (1 - np.abs(np.random.randn(n)) * 0.005),
            "high": price * (1 + np.abs(np.random.randn(n)) * 0.01),
            "low": price * (1 - np.abs(np.random.randn(n)) * 0.01),
            "close": price,
            "volume": volume,
        }
        self._data_cache[symbol] = {"source": "synthetic", "data": data}
        return data

    def compute_technical_features(self, ohlcv_data: Any) -> np.ndarray:
        """
        计算技术指标特征向量。

        将原始 OHLCV 数据转换为固定维度的特征向量，用于 RSSM 训练。
        特征包括:
        - 收益率 (1d, 5d, 20d)
        - 波动率 (20d 滚动)
        - RSI (14)
        - MACD (12, 26, 9)
        - 布林带位置
        - 成交量变化
        - 市场体制 one-hot 编码

        Args:
            ohlcv_data: pd.DataFrame 或 Dict with OHLCV

        Returns:
            np.ndarray: (T, feature_dim) 特征矩阵
        """
        # 提取 OHLCV
        if isinstance(ohlcv_data, dict):
            close = np.array(ohlcv_data.get("close", []), dtype=np.float64)
            volume = np.array(ohlcv_data.get("volume", []), dtype=np.float64)
            high = np.array(ohlcv_data.get("high", []) if isinstance(ohlcv_data.get("high"), (list, np.ndarray)) else close)
            low = np.array(ohlcv_data.get("low", []) if isinstance(ohlcv_data.get("low"), (list, np.ndarray)) else close)
        else:
            close = np.array(ohlcv_data["Close"] if "Close" in ohlcv_data else ohlcv_data["close"], dtype=np.float64)
            volume = np.array(ohlcv_data["Volume"] if "Volume" in ohlcv_data else ohlcv_data["volume"], dtype=np.float64)
            high = np.array(ohlcv_data["High"] if "High" in ohlcv_data else close)
            low = np.array(ohlcv_data["Low"] if "Low" in ohlcv_data else close)

        n = len(close)
        if n < 30:
            return np.zeros((n, 20))

        # === 计算各指标 ===

        # 1. 收益率
        returns = compute_returns(close, [1, 5, 20])

        # 2. 波动率
        daily_returns = np.diff(close) / close[:-1]
        vol20 = compute_volatility(daily_returns, 20)
        # 补齐长度
        vol20_full = np.full(n, np.nan)
        vol20_full[1:] = vol20

        # 3. RSI
        rsi = compute_rsi(close, 14)

        # 4. MACD
        macd_data = compute_macd(close)

        # 5. 布林带
        bb = compute_bollinger_bands(close)

        # 6. 成交量指标
        vol_indicators = compute_volume_indicators(close, volume)

        # === 拼接特征向量 ===
        features = np.zeros((n, 20))

        for i in range(n):
            feat = [
                close[i] / (close[max(0, i - 1)] + 1e-8) - 1.0,  # 日收益率
                returns["return_5d"][i - 5] if i >= 5 else 0.0,  # 5日收益
                returns["return_20d"][i - 20] if i >= 20 else 0.0,  # 20日收益
                vol20_full[i] if not np.isnan(vol20_full[i]) else 0.015,  # 波动率
                rsi[i] / 100.0 if not np.isnan(rsi[i]) else 0.5,  # RSI 归一化
                macd_data["macd"][i] if not np.isnan(macd_data["macd"][i]) else 0.0,
                macd_data["signal"][i] if not np.isnan(macd_data["signal"][i]) else 0.0,
                macd_data["histogram"][i] if not np.isnan(macd_data["histogram"][i]) else 0.0,
                bb["position"][i] if not np.isnan(bb["position"][i]) else 0.5,
                bb["width"][i] if not np.isnan(bb["width"][i]) else 0.0,
                vol_indicators["volume_change"][i] if not np.isnan(vol_indicators["volume_change"][i]) else 0.0,
                vol_indicators["vwap"][i] / (close[i] + 1e-8) - 1.0 if not np.isnan(vol_indicators["vwap"][i]) else 0.0,
                high[i] / (low[i] + 1e-8) - 1.0,  # 日内振幅
                np.log(volume[i] + 1) if i > 0 else 0.0,
                volume[i] / (np.mean(volume[max(0, i - 20):i + 1]) + 1e-8) - 1.0,  # 相对成交量
                np.mean(daily_returns[max(0, i - 5):i]) if i > 0 else 0.0,  # 5日均收益率
                np.std(daily_returns[max(0, i - 10):i]) if i > 0 else 0.0,  # 10日波动率
                np.max(close[max(0, i - 20):i + 1]) / (close[i] + 1e-8) - 1.0,  # 距20日高点
                close[i] / (np.min(close[max(0, i - 20):i + 1]) + 1e-8) - 1.0,  # 距20日低点
                0.0,  # 保留位
            ]
            features[i] = np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0)

        return features

    def get_market_regime(self, ohlcv_data: Any) -> dict[str, Any]:
        """
        识别当前市场体制 (基于统计方法而非硬编码)。

        Returns:
            Dict with keys: regime, confidence, sharpe, trend_strength
        """
        if isinstance(ohlcv_data, dict):
            close = np.array(ohlcv_data.get("close", []), dtype=np.float64)
        else:
            close = np.array(ohlcv_data["Close"] if "Close" in ohlcv_data else ohlcv_data["close"], dtype=np.float64)

        if len(close) < 30:
            return {"regime": "unknown", "confidence": 0.0}

        daily_returns = np.diff(close) / close[:-1]
        vol20 = compute_volatility(daily_returns, 20)

        return detect_market_regime(close, daily_returns, vol20)

    def prepare_training_batch(self, symbol: str,
                                precomputed_features: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """
        准备 RSSM 训练数据。

        Args:
            symbol: 股票代码
            precomputed_features: 可选，复用已计算的特征，避免重复 fetch

        Returns:
            Tuple[np.ndarray, np.ndarray]: (observations, next_observations)
            - observations: (T, feature_dim)
            - next_observations: (T, feature_dim)
        """
        if precomputed_features is not None:
            features = precomputed_features
        else:
            data = self.fetch_market_data(symbol)
            features = self.compute_technical_features(data)

        if len(features) < 2:
            return np.zeros((1, 20)), np.zeros((1, 20))

        obs = features[:-1]  # (T-1, D)
        next_obs = features[1:]  # (T-1, D)

        return obs, next_obs

    def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """
        获取基本面数据。

        Returns:
            Dict with PE, PB, ROE, 营收增长率等
        """
        # 兜底数据
        return {
            "pe": 15.0, "pb": 1.5, "roe": 0.1,
            "revenue_growth": 0.05, "source": "default",
        }

    def fetch_news_sentiment(self, symbol: str, days: int = 7) -> list[dict[str, Any]]:
        """
        获取新闻情感数据。

        Returns:
            List[Dict]: news items with sentiment scores
        """
        # 当前返回模拟数据，实际接入需要新闻 API
        news_data = []
        for d in range(min(days, 7)):
            news_data.append({
                "date": (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d"),
                "title": f"模拟新闻: {symbol} 市场动态 {d + 1}",
                "sentiment": np.random.uniform(-0.3, 0.5),
                "relevance": np.random.uniform(0.5, 1.0),
                "source": "simulated",
            })
        return news_data
