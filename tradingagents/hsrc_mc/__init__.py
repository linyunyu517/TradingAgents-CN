# TradingAgents/hsrc_mc/__init__.py
"""
HSR-MC: HyperNetwork-based Self-Referential Meta-Controller
============================================================

基于超网络的自我指涉元控制器——第四轮架构增强。

核心组件:
    - HSRMCConfig:      配置类，控制所有 HSR-MC 开关与超参数
    - MetaObserver:     二阶观察器，监控 L-IWM 各模块的健康状态
    - HyperNetwork:     超网络，根据观察状态生成元参数
    - SelfModel:        自模型，实现自我指涉预测 (Soros + von Foerster)
    - HSRMCManager:     协调器，将所有组件集成到 LangGraph 流程中

理论基础:
    1. 二阶控制论 (von Foerster): 系统观察自身的观察过程
    2. 超网络 (Ha et al., 2016): 小网络生成大网络的参数
    3. 反身性 (Soros, 1987): 认知函数与操纵函数的互相影响
    4. 本征形式 (von Foerster, 1984): 自我指涉的定点解

依赖:
    - numpy: 所有数值计算
    - ..l_iwm: 观察 L-IWM 模块的状态
    - ..hpc_loop: 通过 LangGraph 集成
"""

from .hsrc_config import HSRMCConfig
from .hsrc_integration import HSRMCManager
from .hypernetwork import HyperNetwork
from .meta_observer import MetaObserver
from .self_model import SelfModel

__all__ = [
    "HSRMCConfig",
    "HSRMCManager",
    "HyperNetwork",
    "MetaObserver",
    "SelfModel",
]
