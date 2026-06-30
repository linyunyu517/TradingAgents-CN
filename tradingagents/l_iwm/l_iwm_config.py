# TradingAgents/l_iwm/l_iwm_config.py
"""
L-IWM 全局配置模块

集中管理 L-IWM 所有可学习模块的可配置参数，
支持环境变量加载和运行时动态调整。
遵循 HPC-Loop 的命名约定和环境变量前缀规范。
"""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LIWMConfig:
    """
    L-IWM (Learnable Internal World Model) 全局配置。

    所有参数可通过环境变量 L_IWM_ 前缀覆盖。
    保持向后兼容：禁用所有可学习模块时，HPC-Loop 回退到原始硬编码实现。
    """

    # ==================== 可学习模块启用开关 ====================
    rssm_enabled: bool = True
    """是否启用 RSSM 可学习世界模型 (替代硬编码生成模型)"""

    real_data_enabled: bool = True
    """是否启用真实数据管道 (替代文本长度代理)"""

    learnable_efe_enabled: bool = True
    """是否启用可学习 EFE 评估器 (替代手工认知价值分配)"""

    diff_causal_enabled: bool = True
    """是否启用可微分因果发现 (替代手工因果图)"""

    ewc_memory_enabled: bool = True
    """是否启用 EWC 防遗忘记忆系统 (增强互补记忆)"""

    learnable_gws_enabled: bool = True
    """是否启用可学习显著性评估器 (替代关键词启发式)"""

    # ==================== RSSM 世界模型参数 ====================
    rssm_latent_dim: int = 32
    """确定性隐状态维度"""

    rssm_hidden_dim: int = 256
    """GRU 隐藏单元数"""

    rssm_stochastic_dim: int = 32
    """随机状态维度 (z_t 的维度)"""

    rssm_learning_rate: float = 3e-4
    """RSSM 学习率 (Adam)"""

    rssm_imagination_horizon: int = 15
    """隐空间想象轨迹长度"""

    rssm_kl_beta: float = 0.1
    """KL 散度正则化系数"""

    rssm_batch_size: int = 32
    """训练批次大小"""

    rssm_buffer_size: int = 10000
    """经验回放缓冲区大小"""

    # ==================== 真实数据管道参数 ====================
    real_data_sources: list = field(default_factory=lambda: ["tushare"])
    """数据源列表（优先级从高到低: tushare）"""

    real_data_interval: str = "1d"
    """数据间隔 (1d, 1h, 5m 等)"""

    real_data_lookback_days: int = 365
    """回溯天数"""

    real_data_max_symbols: int = 50
    """同时监控的最大股票数量"""

    # ==================== 可学习 EFE 参数 ====================
    efe_epistemic_dim: int = 8
    """认知价值网络隐层维度"""

    efe_pragmatic_dim: int = 8
    """实用价值网络隐层维度"""

    efe_learning_rate: float = 1e-3
    """EFE 网络学习率"""

    efe_td_lambda: float = 0.9
    """TD(λ) 回溯系数"""

    efe_exploration_alpha: float = 0.2
    """探索奖励的可学习系数"""

    # ==================== 可微分因果发现参数 ====================
    causal_max_nodes: int = 20
    """因果图最大节点数"""

    causal_threshold: float = 0.3
    """因果边存在阈值"""

    causal_w_threshold: float = 0.1
    """权重矩阵稀疏化阈值"""

    causal_lambda1: float = 0.1
    """L1 正则化系数"""

    causal_lambda2: float = 0.01
    """DAG 约束惩罚系数"""

    causal_max_iter: int = 100
    """NOTEARS 最大迭代次数"""

    # ==================== EWC 记忆参数 ====================
    ewc_elasticity: float = 100.0
    """EWC 弹性系数 λ (越大 → 对旧权重保护越强)"""

    ewc_consolidation_interval: int = 100
    """记忆巩固间隔 (episode 数)"""

    ewc_fisher_samples: int = 50
    """Fisher 信息矩阵估算采样数"""

    ewc_importance_threshold: float = 0.01
    """Fisher 信息重要性阈值 (低于此值的参数不保护)"""

    # ==================== 可学习 GWS 参数 ====================
    gws_feature_dim: int = 64
    """显著性网络特征维度"""

    gws_learning_rate: float = 1e-3
    """显著性网络学习率"""

    gws_top_k: int = 3
    """广播时选择的 top-k 显著内容"""

    gws_embedding_method: str = "tfidf"
    """Agent 输出编码方法: tfidf, average, learned"""

    # ==================== 训练与日志 ====================
    train_epochs: int = 10
    """离线训练轮数"""

    online_learning_rate: float = 1e-4
    """在线学习的学习率(低于离线)"""

    log_level: str = "INFO"
    """日志级别"""

    debug_mode: bool = False
    """调试模式"""

    @classmethod
    def from_env(cls) -> "LIWMConfig":
        """从环境变量加载配置 (环境变量覆盖默认值)"""
        config = cls()

        bool_map = {"true": True, "false": False, "1": True, "0": False}
        prefix = "L_IWM_"

        for field_info in cls.__dataclass_fields__.values():
            env_name = prefix + field_info.name.upper()
            env_value = os.getenv(env_name)
            if env_value is not None:
                if field_info.type in (bool, "bool"):
                    setattr(config, field_info.name, bool_map.get(env_value.lower(), False))
                elif field_info.type in (int, "int"):
                    setattr(config, field_info.name, int(env_value))
                elif field_info.type in (float, "float"):
                    setattr(config, field_info.name, float(env_value))
                elif field_info.type in (str, "str"):
                    setattr(config, field_info.name, env_value)

        return config

    def to_dict(self) -> dict[str, Any]:
        """将配置转换为字典"""
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}

    @classmethod
    def to_ui_schema(cls) -> list[dict[str, Any]]:
        """生成 UI schema，供 Streamlit 自动渲染配置面板"""
        return [
            # ==================== RSSM 状态模型 ====================
            {
                "field": "rssm_enabled",
                "label": "启用 RSSM 状态模型",
                "type": "toggle",
                "default": True,
                "help": "是否启用 RSSM 可学习世界模型，替代硬编码生成模型",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_latent_dim",
                "label": "RSSM 潜在维度",
                "type": "slider",
                "default": 32,
                "min": 8,
                "max": 128,
                "step": 8,
                "help": "确定性隐状态向量的维度",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_hidden_dim",
                "label": "RSSM 隐藏维度",
                "type": "slider",
                "default": 256,
                "min": 64,
                "max": 512,
                "step": 8,
                "help": "GRU 隐藏单元数量",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_stochastic_dim",
                "label": "RSSM 随机维度",
                "type": "slider",
                "default": 32,
                "min": 8,
                "max": 128,
                "step": 8,
                "help": "随机状态向量 z_t 的维度",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_learning_rate",
                "label": "RSSM 学习率",
                "type": "number",
                "default": 0.0003,
                "min": 1e-6,
                "max": 0.1,
                "step": 1e-5,
                "help": "RSSM 模型使用的 Adam 优化器学习率",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_imagination_horizon",
                "label": "想象推演步数",
                "type": "slider",
                "default": 15,
                "min": 5,
                "max": 50,
                "step": 1,
                "help": "隐空间中想象轨迹的长度（推演步数）",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_kl_beta",
                "label": "KL 散度系数",
                "type": "slider",
                "default": 0.1,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "KL 散度正则化系数，控制先验和后验的匹配程度",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_batch_size",
                "label": "训练批次大小",
                "type": "slider",
                "default": 32,
                "min": 8,
                "max": 256,
                "step": 8,
                "help": "RSSM 模型训练时的批次大小",
                "category": "RSSM 状态模型",
            },
            {
                "field": "rssm_buffer_size",
                "label": "经验回放缓冲区大小",
                "type": "slider",
                "default": 10000,
                "min": 1000,
                "max": 100000,
                "step": 1000,
                "help": "经验回放缓冲区的最大容量",
                "category": "RSSM 状态模型",
            },
            # ==================== 实时数据源 ====================
            {
                "field": "real_data_enabled",
                "label": "启用实时数据集成",
                "type": "toggle",
                "default": True,
                "help": "是否启用真实数据管道，替代文本长度代理数据",
                "category": "实时数据源",
            },
            {
                "field": "real_data_sources",
                "label": "数据源选择",
                "type": "select",
                "default": "tushare",
                "options": ["tushare"],
                "help": "逗号分隔的数据源列表，支持多个数据源同时使用",
                "category": "实时数据源",
            },
            {
                "field": "real_data_interval",
                "label": "数据间隔",
                "type": "select",
                "default": "1d",
                "options": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
                "help": "数据采样间隔",
                "category": "实时数据源",
            },
            {
                "field": "real_data_lookback_days",
                "label": "回溯天数",
                "type": "slider",
                "default": 365,
                "min": 30,
                "max": 730,
                "step": 1,
                "help": "历史数据回溯的天数",
                "category": "实时数据源",
            },
            {
                "field": "real_data_max_symbols",
                "label": "最大股票数",
                "type": "slider",
                "default": 50,
                "min": 1,
                "max": 200,
                "step": 1,
                "help": "同时监控的最大股票数量",
                "category": "实时数据源",
            },
            # ==================== EFE 学习 ====================
            {
                "field": "learnable_efe_enabled",
                "label": "启用可学习 EFE",
                "type": "toggle",
                "default": True,
                "help": "是否启用可学习 EFE 评估器，替代手工认知价值分配",
                "category": "EFE 学习",
            },
            {
                "field": "efe_epistemic_dim",
                "label": "认知价值网络维度",
                "type": "slider",
                "default": 8,
                "min": 4,
                "max": 128,
                "step": 4,
                "help": "认知价值网络的隐层维度",
                "category": "EFE 学习",
            },
            {
                "field": "efe_pragmatic_dim",
                "label": "实用价值网络维度",
                "type": "slider",
                "default": 8,
                "min": 4,
                "max": 128,
                "step": 4,
                "help": "实用价值网络的隐层维度",
                "category": "EFE 学习",
            },
            {
                "field": "efe_learning_rate",
                "label": "EFE 学习率",
                "type": "number",
                "default": 0.001,
                "min": 1e-6,
                "max": 0.1,
                "step": 1e-5,
                "help": "EFE 价值网络的学习率",
                "category": "EFE 学习",
            },
            {
                "field": "efe_td_lambda",
                "label": "TD 回溯系数",
                "type": "slider",
                "default": 0.9,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "TD(lambda) 回溯系数，控制时间差分学习的偏差-方差权衡",
                "category": "EFE 学习",
            },
            {
                "field": "efe_exploration_alpha",
                "label": "探索系数",
                "type": "slider",
                "default": 0.2,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "探索奖励的可学习系数",
                "category": "EFE 学习",
            },
            # ==================== 因果推断 ====================
            {
                "field": "diff_causal_enabled",
                "label": "启用微分因果推断",
                "type": "toggle",
                "default": True,
                "help": "是否启用可微分因果发现，替代手工构建的因果图",
                "category": "因果推断",
            },
            {
                "field": "causal_max_nodes",
                "label": "因果图最大节点",
                "type": "slider",
                "default": 20,
                "min": 3,
                "max": 50,
                "step": 1,
                "help": "因果图中允许的最大节点数量",
                "category": "因果推断",
            },
            {
                "field": "causal_threshold",
                "label": "因果阈值",
                "type": "slider",
                "default": 0.3,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "因果边存在的阈值",
                "category": "因果推断",
            },
            {
                "field": "causal_w_threshold",
                "label": "权重稀疏化阈值",
                "type": "slider",
                "default": 0.1,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "权重矩阵稀疏化的阈值",
                "category": "因果推断",
            },
            {
                "field": "causal_lambda1",
                "label": "L1 正则化系数",
                "type": "number",
                "default": 0.1,
                "min": 0.0,
                "max": 10.0,
                "step": 0.01,
                "help": "因果发现中的 L1 正则化系数",
                "category": "因果推断",
            },
            {
                "field": "causal_lambda2",
                "label": "DAG 约束系数",
                "type": "number",
                "default": 0.01,
                "min": 0.0,
                "max": 1.0,
                "step": 0.001,
                "help": "DAG 约束惩罚系数",
                "category": "因果推断",
            },
            {
                "field": "causal_max_iter",
                "label": "最大迭代次数",
                "type": "slider",
                "default": 100,
                "min": 10,
                "max": 1000,
                "step": 10,
                "help": "NOTEARS 优化最大迭代次数",
                "category": "因果推断",
            },
            # ==================== 记忆与学习 ====================
            {
                "field": "ewc_memory_enabled",
                "label": "启用 EWC 记忆",
                "type": "toggle",
                "default": True,
                "help": "是否启用 EWC 防遗忘记忆系统，增强互补记忆",
                "category": "记忆与学习",
            },
            {
                "field": "learnable_gws_enabled",
                "label": "启用可学习 GWS",
                "type": "toggle",
                "default": True,
                "help": "是否启用可学习显著性评估器，替代关键词启发式方法",
                "category": "记忆与学习",
            },
            {
                "field": "ewc_elasticity",
                "label": "EWC 弹性系数",
                "type": "slider",
                "default": 100.0,
                "min": 0.1,
                "max": 1000.0,
                "step": 1.0,
                "help": "EWC 弹性系数，越大表示对旧权重保护越强",
                "category": "记忆与学习",
            },
            {
                "field": "ewc_consolidation_interval",
                "label": "EWC 巩固间隔",
                "type": "slider",
                "default": 100,
                "min": 10,
                "max": 1000,
                "step": 10,
                "help": "EWC 记忆巩固间隔（训练 episode 数）",
                "category": "记忆与学习",
            },
            {
                "field": "ewc_fisher_samples",
                "label": "Fisher 采样数",
                "type": "slider",
                "default": 50,
                "min": 10,
                "max": 500,
                "step": 10,
                "help": "Fisher 信息矩阵估算使用的采样数量",
                "category": "记忆与学习",
            },
            {
                "field": "ewc_importance_threshold",
                "label": "Fisher 重要性阈值",
                "type": "slider",
                "default": 0.01,
                "min": 0.0,
                "max": 1.0,
                "step": 0.001,
                "help": "Fisher 信息重要性阈值，低于此值的参数参数不进行保护",
                "category": "记忆与学习",
            },
            {
                "field": "gws_feature_dim",
                "label": "GWS 特征维度",
                "type": "slider",
                "default": 64,
                "min": 8,
                "max": 256,
                "step": 8,
                "help": "显著性网络的特征向量维度",
                "category": "记忆与学习",
            },
            {
                "field": "gws_learning_rate",
                "label": "GWS 学习率",
                "type": "number",
                "default": 0.001,
                "min": 1e-6,
                "max": 0.1,
                "step": 1e-5,
                "help": "显著性网络的学习率",
                "category": "记忆与学习",
            },
            {
                "field": "gws_top_k",
                "label": "GWS Top-K",
                "type": "slider",
                "default": 3,
                "min": 1,
                "max": 20,
                "step": 1,
                "help": "广播时选择的 top-k 最显著内容数量",
                "category": "记忆与学习",
            },
            {
                "field": "gws_embedding_method",
                "label": "编码方法",
                "type": "select",
                "default": "tfidf",
                "options": ["tfidf", "average", "learned"],
                "help": "Agent 输出的编码方法",
                "category": "记忆与学习",
            },
            {
                "field": "train_epochs",
                "label": "训练轮数",
                "type": "slider",
                "default": 10,
                "min": 5,
                "max": 200,
                "step": 1,
                "help": "离线训练的总轮数",
                "category": "记忆与学习",
            },
            {
                "field": "online_learning_rate",
                "label": "在线学习率",
                "type": "number",
                "default": 0.0001,
                "min": 1e-7,
                "max": 0.01,
                "step": 1e-5,
                "help": "在线学习的学习率（通常低于离线学习率）",
                "category": "记忆与学习",
            },
            # ==================== 日志与调试 ====================
            {
                "field": "log_level",
                "label": "日志级别",
                "type": "select",
                "default": "INFO",
                "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
                "help": "日志输出级别",
                "category": "日志与调试",
            },
            {
                "field": "debug_mode",
                "label": "调试模式",
                "type": "toggle",
                "default": False,
                "help": "开启后打印详细中间结果，用于调试",
                "category": "日志与调试",
            },
        ]

    @classmethod
    def from_ui_values(cls, ui_values: dict[str, Any]) -> "LIWMConfig":
        """从 UI 表单值创建配置实例"""
        return cls(**{k: v for k, v in ui_values.items() if k in cls.__dataclass_fields__})

    def merge_with(self, overrides: dict[str, Any]) -> "LIWMConfig":
        """合并覆盖配置，返回新实例"""
        new_config = LIWMConfig()
        for field_name in self.__dataclass_fields__:
            if field_name in overrides:
                setattr(new_config, field_name, overrides[field_name])
            else:
                setattr(new_config, field_name, getattr(self, field_name))
        return new_config
