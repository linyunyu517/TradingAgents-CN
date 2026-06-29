# tradingagents/diffusion/__init__.py
"""
TradingAgents-CN 扩散模型模块

提供 DDIM 确定性采样、1D Temporal U-Net Score Network、
均匀先验退化、以及 DiffusionManager 统一入口。

设计原则:
    - 纯 NumPy 实现，零深度学习框架依赖
    - 与现有 DreamerV3 RSSM 风格一致
    - 扩散输出失败 → 自动退化为均匀先验 (非降级机制)
    - DDIM 50步确定性采样统一策略

模块架构:
    DiffusionConfig          → 全局配置 (config.py)
    DDIMSampler / 工具函数   → DDIM 采样器 (ddim_sampler.py)
    ScoreNetwork / TemporalUNet1D → 去噪网络 (score_network.py)
    UniformPrior / uniform_prior → 均匀先验退化 (uniform_prior.py)
    DiffusionManager         → 统一入口 (diffusion_manager.py)
"""

from __future__ import annotations

from .config import DiffusionConfig
from .ddim_sampler import (
    DDIMSampler,
    ddim_sampling_loop,
    ddim_step,
    sample_with_uncertainty,
)
from .diffusion_generative_model import DiffusionGenerativeModel
from .diffusion_imputer import CSDIImputer
from .diffusion_manager import DiffusionManager, get_diffusion_manager
from .diffusion_portfolio_optimizer import DiffusionPortfolioOptimizer
from .diffusion_scenario import DiffusionScenarioGenerator, EulerMaruyamaSDE
from .diffusion_trader import TradingDecisionDiffuser
from .score_network import (
    ScoreNetwork,
    ScoreTable,
    TemporalUNet1D,
    sinusoidal_embedding,
)
from .uniform_prior import (
    get_uniform_prior_confidence,
    is_uniform_prior_applicable,
    uniform_prior,
)


# UniformPrior 类名别名 (与统一先验的函数接口等价)
class UniformPrior:
    """均匀先验类 (函数式接口的类包装)

    当扩散推理失败时，返回均匀分布样本作为安全回退。
    均匀先验本身就是最大熵分布，表示"无信息偏好"，
    是贝叶斯推理中的合法先验选择。

    用法:
        >>> prior = UniformPrior()
        >>> samples = prior(shape=(32, 4, 32))
        >>> prior_conf = prior.confidence
    """

    def __init__(self, low: float = -1.0, high: float = 1.0):
        self.low = low
        self.high = high
        self._confidence = 0.0

    def __call__(self, shape, dtype=None):
        return uniform_prior(shape, self.low, self.high, dtype)

    @property
    def confidence(self) -> float:
        """均匀先验的置信度为 0.0，表示完全不确定"""
        return self._confidence

    def __repr__(self) -> str:
        return f"UniformPrior(low={self.low}, high={self.high}, confidence={self._confidence})"


__all__ = [
    # 数据补全
    "CSDIImputer",
    # 采样
    "DDIMSampler",
    # 配置
    "DiffusionConfig",
    # === Phase 3: 扩散模块集成 ===
    # 模块 A: 生成式扩散模型
    "DiffusionGenerativeModel",
    # 管理器
    "DiffusionManager",
    "DiffusionPortfolioOptimizer",
    # 模块 C: 扩散场景生成
    "DiffusionScenarioGenerator",
    "EulerMaruyamaSDE",
    # 网络
    "ScoreNetwork",
    "ScoreTable",
    "TemporalUNet1D",
    # 模块 B: 扩散交易决策（并行顾问）
    "TradingDecisionDiffuser",
    # 先验
    "UniformPrior",
    "ddim_sampling_loop",
    "ddim_step",
    "get_diffusion_manager",
    "get_uniform_prior_confidence",
    "is_uniform_prior_applicable",
    "sample_with_uncertainty",
    "sinusoidal_embedding",
    "uniform_prior",
]

__version__ = "0.1.0"
