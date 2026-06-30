# TradingAgents/hpc_loop/__init__.py
"""
HPC-Loop (Hierarchical Predictive Coding Loop) Module
=====================================================

基于层级预测编码与主动推理闭环的架构改进模块。
将系统从开环前馈推理升级为闭环主动推理智能体。

核心组件:
    - MarketGenerativeModel: 宏观生成模型 (L3)
    - GlobalWorkspace: 全局工作空间 (GWS)
    - ActiveInferenceEngine: 主动推理引擎
    - CausalCounterfactualEngine: 因果反事实引擎
    - ComplementaryLearningMemory: 互补学习记忆系统
    - PredictionErrorCalculator: 预测误差计算
"""

from .active_inference import ActionSelection, ActiveInferenceEngine, EFEDecomposition
from .aif_engine import (
    ActiveInference as AIFActiveInference,
)
from .aif_engine import (
    BeliefUpdater,
    GenerativeModel,
    LLMPriorInjector,
)

# AIF (Active Inference Framework) 引擎导出
from .aif_engine import (
    MarketLatentState as AIFMarketLatentState,
)
from .aif_integration import AIFEngineManager
from .causal_counterfactual import (
    CausalCounterfactualEngine,
    CounterfactualResult,
    EffectDecomposition,
)
from .complementary_memory import (
    ComplementaryLearningMemory,
    MemoryTrace,
    TradingEpisode,
)
from .generative_model import MarketGenerativeModel
from .global_workspace import ConsciousContent, GlobalWorkspace

# Phase 2: Hierarchical Model & Meta-Learner
from .hierarchical_model import (
    HierarchicalGenModel,
    LayerConfig,
    TimeScale,
    build_custom_model,
    build_default_4layer_model,
    print_hierarchy_info,
)
from .hpc_config import HPCLoopConfig
from .hpc_integration import HPCLoopManager
from .hpc_state import HPCState, MarketLatentState, MarketPrediction, PredictionError
from .meta_learner import (
    MetaLearner,
    MetaLearnerConfig,
    ModelDiagnostics,
    create_default_meta_learner,
    create_fast_meta_learner,
    simulate_degradation_and_diagnose,
)
from .prediction_error import PredictionErrorCalculator

__all__ = [
    "AIFActiveInference",
    "AIFEngineManager",
    # AIF (Active Inference Framework) 组件
    "AIFMarketLatentState",
    "ActionSelection",
    "ActiveInferenceEngine",
    "BeliefUpdater",
    "CausalCounterfactualEngine",
    "ComplementaryLearningMemory",
    "ConsciousContent",
    "CounterfactualResult",
    "EFEDecomposition",
    "EffectDecomposition",
    "GenerativeModel",
    "GlobalWorkspace",
    # HPC-Loop 核心组件
    "HPCLoopConfig",
    "HPCLoopManager",
    "HPCState",
    # Phase 2: Hierarchical Model & Meta-Learner
    "HierarchicalGenModel",
    "LLMPriorInjector",
    "LayerConfig",
    "MarketGenerativeModel",
    "MarketLatentState",
    "MarketPrediction",
    "MemoryTrace",
    "MetaLearner",
    "MetaLearnerConfig",
    "ModelDiagnostics",
    "PredictionError",
    "PredictionErrorCalculator",
    "TimeScale",
    "TradingEpisode",
    "build_custom_model",
    "build_default_4layer_model",
    "create_default_meta_learner",
    "create_fast_meta_learner",
    "print_hierarchy_info",
    "simulate_degradation_and_diagnose",
]
