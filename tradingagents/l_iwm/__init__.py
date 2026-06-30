# TradingAgents/l_iwm/__init__.py
"""
L-IWM (Learnable Internal World Model) Module
==============================================

HPC-Loop 的第二代升级：将所有硬编码启发式规则升级为可学习的参数化函数。

核心模块:
    - RSSMWorldModel: P0 — 可学习世界模型 (替代 MarketGenerativeModel 的硬编码预测)
    - RealDataPipeline: P1 — 真实数据管道 (替代 _extract_market_info 的文本长度代理)
    - LearnableEFEEvaluator: P2 — 可学习 EFE 评估器 (替代 ActiveInferenceEngine 的手工权重)
    - DifferentiableCausalDiscovery: P3 — 可微分因果发现 (替代 CausalCounterfactualEngine 的手工图)
    - EWCMemorySystem: P4 — EWC 防遗忘记忆系统 (增强 ComplementaryLearningMemory)
    - LearnableSaliencyEvaluator: P5 — 可学习显著性评估器 (替代 GlobalWorkspace 的关键词启发式)
    - LIWMManager: 统一管理器，协调所有可学习模块
"""

from .differentiable_causal import DifferentiableCausalDiscovery, InterventionResult
from .ewc_memory import EWCMemorySystem
from .l_iwm_config import LIWMConfig
from .l_iwm_integration import LIWMManager
from .learnable_efe import LearnableEFEEvaluator
from .learnable_gws import LearnableSaliencyEvaluator
from .real_data_pipeline import RealDataPipeline
from .rssm_world_model import RSSMWorldModel

__all__ = [
    "DifferentiableCausalDiscovery",
    "EWCMemorySystem",
    "InterventionResult",
    "LIWMConfig",
    "LIWMManager",
    "LearnableEFEEvaluator",
    "LearnableSaliencyEvaluator",
    "RSSMWorldModel",
    "RealDataPipeline",
]
