# TradingAgents/hpc_loop/hpc_config.py
"""
HPC-Loop 配置模块

集中管理 HPC-Loop 所有组件的可配置参数，
支持环境变量覆盖和运行时动态调整。
"""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HPCLoopConfig:
    """
    HPC-Loop 全局配置。

    所有参数可通过环境变量或直接传入覆盖。
    环境变量前缀: HPC_LOOP_
    """

    # ==================== 全局开关 ====================
    enabled: bool = True
    """是否启用 HPC-Loop 增强"""

    parallel_analysts: bool = True
    """是否将分析师层从串行改为并行执行"""

    # ==================== 全局工作空间 (GWS) ====================
    gws_enabled: bool = True
    """是否启用全局工作空间"""

    gws_capacity: int = 4
    """全局工作空间容量 (conscious chunks)"""

    gws_saliency_threshold: float = 0.3
    """显著性阈值，低于此值的 Agent 输出不被广播"""

    gws_novelty_weight: float = 0.25
    """显著性计算：新颖性权重"""

    gws_confidence_weight: float = 0.25
    """显著性计算：置信度权重"""

    gws_impact_weight: float = 0.30
    """显著性计算：影响力权重"""

    gws_urgency_weight: float = 0.20
    """显著性计算：紧迫性权重"""

    # ==================== 生成模型 (旧 HPC Dict 路径) ====================
    generative_model_enabled: bool = True
    """是否启用宏观生成模型"""

    generative_model_history_window: int = 150
    """生成模型维护的历史窗口大小"""

    generative_model_latent_dim: int = 32
    """[旧 HPC] 生成模型隐状态维度 (32D, dict 风格表征)
       注意: 此配置用于 MarketGenerativeModel (generative_model.py, 旧 HPC 路径)。
       AIF 引擎 (aif_engine.py) 使用 aif_latent_dim=8 (JAX 紧凑向量)。
       两者故意不同，通过 _adapt_s_t_dim() 自动适配。"""

    generative_model_learning_rate: float = 0.01
    """变分更新学习率"""

    generative_model_scales: list[str] = field(default_factory=lambda: ["tick", "minute", "daily", "weekly", "monthly"])
    """多尺度时间结构"""

    # ==================== 主动推理引擎 ====================
    active_inference_enabled: bool = True
    """是否启用主动推理引擎"""

    epistemic_weight: float = 0.4
    """认知价值权重 (信息增益 vs. 预期收益)"""

    pragmatic_weight: float = 0.6
    """实用价值权重"""

    exploration_decay: float = 0.95
    """探索奖励衰减因子"""

    min_exploration_bonus: float = 0.01
    """最小探索奖励"""

    # ==================== 因果反事实引擎 ====================
    causal_inference_enabled: bool = True
    """是否启用因果反事实引擎"""

    causal_graph_max_nodes: int = 30
    """因果图最大节点数"""

    causal_dag_confidence_threshold: float = 0.3
    """因果边置信度阈值"""

    # ==================== 互补学习记忆系统 ====================
    memory_enabled: bool = True
    """是否启用互补学习记忆系统"""

    memory_hippocampus_max_episodes: int = 1000
    """海马体 (快通道) 最大 episode 数"""

    memory_consolidation_interval: int = 24
    """记忆巩固间隔 (小时)"""

    memory_replay_batch_size: int = 32
    """睡眠回放批次大小"""

    memory_similarity_top_k: int = 5
    """相似检索 top-k"""

    memory_saliency_threshold: float = 0.5
    """记忆巩固的显著性阈值"""

    # ==================== 预测误差计算 ====================
    prediction_error_enabled: bool = True
    """是否启用预测误差计算"""

    prediction_error_surprise_threshold: float = 1.5
    """惊奇检测阈值 (标准差倍数)"""

    prediction_error_precision_dynamics: bool = True
    """是否启用精度动态更新"""

    prediction_error_rate: float = 0.15
    """预测误差率 — 用于精度动态更新的学习率 / 误差归一化衰减因子"""

    # ==================== 日志与调试 ====================
    log_level: str = "INFO"
    """日志级别"""

    debug_mode: bool = False
    """调试模式 (打印详细中间结果)"""

    # ==================== L-IWM 可学习模块集成 ====================
    l_iwm_enabled: bool = True
    """是否启用 L-IWM 可学习模块 (替代原始硬编码实现)"""

    l_iwm_config_path: str = ""
    """L-IWM 配置文件路径 (空字符串使用默认 LIWMConfig)"""

    l_iwm_input_dim: int = 20
    """L-IWM RSSM 世界模型的输入观测维度"""

    # ==================== HSR-MC 超网络自指涉元控制器 ====================
    hsrc_mc_enabled: bool = True
    """是否启用 HSR-MC (超网络自指涉元控制器) — 在 L-IWM 之上提供元学习"""

    hsrc_mc_config_path: str = ""
    """HSR-MC 配置文件路径 (空字符串使用默认 HSRMCConfig.from_env())"""

    # ==================== AIF (Active Inference Framework, JAX 路径) ====================
    use_aif_engine: bool = True
    """是否启用 AIF 引擎 (替代原始 HPC 规则)"""

    aif_latent_dim: int = 8
    """[AIF JAX] 隐状态维度 (8D 紧凑向量, 用于 GenerativeModel/aif_engine.py)
       组成: [regime_logits(4), volatility_mu(1), trend_mu(1), momentum(1), sentiment(1)]
       注意: 此配置不同于 generative_model_latent_dim=32 (旧 HPC dict 路径)。
       两者故意不一致，分别服务不同子系统，通过 _adapt_s_t_dim() 自动适配。"""

    aif_n_samples: int = 100
    """AIF Monte Carlo 采样数"""

    aif_learning_rate: float = 0.01
    """AIF 变分学习率"""

    aif_efe_temperature: float = 1.0
    """AIF EFE 温度参数 (探索/利用平衡)"""

    # ==================== 扩散生成模型 (Diffusion Generative) ====================
    diffusion_generative_enabled: bool = True
    """是否启用扩散增强生成模型"""

    diffusion_num_timesteps: int = 20
    """[优化 2026-06-22] DDIM 采样步数。从 100 降至 20，配合 diffusion/config.py 的渐进式采样优化。"""

    # ==================== 分层生成模型 + 元学习器 ====================
    use_hierarchical_model: bool = True
    """是否启用分层生成模型 (GENESIS 4层架构)"""

    meta_cycle_interval: int = 50
    """元循环执行间隔 (步数)"""

    meta_window_size: int = 50
    """元学习器滑动窗口大小"""

    meta_learning_rate: float = 0.001
    """元学习器学习率"""

    meta_cusum_threshold: float = 4.0
    """CUSUM 退化检测阈值"""

    @classmethod
    def from_env(cls) -> "HPCLoopConfig":
        """从环境变量加载配置 (环境变量覆盖默认值)"""
        config = cls()

        # 布尔值映射
        bool_map = {"true": True, "false": False, "1": True, "0": False}

        # 环境变量前缀
        prefix = "HPC_LOOP_"

        for field_info in cls.__dataclass_fields__.values():
            env_name = prefix + field_info.name.upper()
            env_value = os.getenv(env_name)
            if env_value is not None:
                # 尝试类型转换
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
        result = {}
        for field_name in self.__dataclass_fields__:
            result[field_name] = getattr(self, field_name)
        return result

    @classmethod
    def to_ui_schema(cls) -> list[dict[str, Any]]:
        """生成 UI schema，供 Streamlit 自动渲染配置面板"""
        return [
            # ==================== 基础设置 ====================
            {
                "field": "enabled",
                "label": "启用 HPC-Loop",
                "type": "toggle",
                "default": True,
                "help": "是否启用 HPC-Loop 增强分析流程",
                "category": "基础设置",
            },
            {
                "field": "parallel_analysts",
                "label": "并行分析师",
                "type": "toggle",
                "default": True,
                "help": "将分析师层从串行改为并行执行，提升分析速度",
                "category": "基础设置",
            },
            # ==================== 全局工作空间(GWS) ====================
            {
                "field": "gws_enabled",
                "label": "启用全局工作空间",
                "type": "toggle",
                "default": True,
                "help": "是否启用全局工作空间(GWS)机制，用于广播显著 Agent 输出",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_capacity",
                "label": "工作空间容量",
                "type": "slider",
                "default": 4,
                "min": 1,
                "max": 50,
                "step": 1,
                "help": "全局工作空间可同时容纳的 conscious chunks 数量",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_saliency_threshold",
                "label": "显著性阈值",
                "type": "slider",
                "default": 0.3,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "Agent 输出的显著性阈值，低于此值的输出不会被广播到全局工作空间",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_novelty_weight",
                "label": "新颖性权重",
                "type": "slider",
                "default": 0.25,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "显著性计算中新颖性的权重系数",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_confidence_weight",
                "label": "置信度权重",
                "type": "slider",
                "default": 0.25,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "显著性计算中置信度的权重系数",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_impact_weight",
                "label": "影响力权重",
                "type": "slider",
                "default": 0.30,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "显著性计算中影响力的权重系数",
                "category": "全局工作空间(GWS)",
            },
            {
                "field": "gws_urgency_weight",
                "label": "紧迫性权重",
                "type": "slider",
                "default": 0.20,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "显著性计算中紧迫性的权重系数",
                "category": "全局工作空间(GWS)",
            },
            # ==================== 生成式模型 ====================
            {
                "field": "generative_model_enabled",
                "label": "启用生成式模型",
                "type": "toggle",
                "default": True,
                "help": "是否启用宏观生成式模型，用于多尺度时间结构建模",
                "category": "生成式模型",
            },
            {
                "field": "generative_model_history_window",
                "label": "历史窗口大小",
                "type": "slider",
                "default": 100,
                "min": 5,
                "max": 500,
                "step": 1,
                "help": "生成模型维护的历史窗口大小（时间步数）",
                "category": "生成式模型",
            },
            {
                "field": "generative_model_latent_dim",
                "label": "隐状态维度",
                "type": "slider",
                "default": 32,
                "min": 8,
                "max": 256,
                "step": 8,
                "help": "生成模型的隐状态向量维度",
                "category": "生成式模型",
            },
            {
                "field": "generative_model_learning_rate",
                "label": "变分学习率",
                "type": "number",
                "default": 0.01,
                "min": 0.0001,
                "max": 1.0,
                "step": 0.001,
                "help": "变分更新学习率",
                "category": "生成式模型",
            },
            {
                "field": "generative_model_scales",
                "label": "多尺度时间层级",
                "type": "text",
                "default": "tick,minute,daily,weekly,monthly",
                "help": "逗号分隔的多尺度时间层级列表",
                "category": "生成式模型",
            },
            # ==================== 主动推理 ====================
            {
                "field": "active_inference_enabled",
                "label": "启用主动推理",
                "type": "toggle",
                "default": True,
                "help": "是否启用主动推理引擎，用于认知价值和实用价值的平衡",
                "category": "主动推理",
            },
            {
                "field": "epistemic_weight",
                "label": "认知价值权重",
                "type": "slider",
                "default": 0.4,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "认知价值（信息增益）在策略选择中的权重",
                "category": "主动推理",
            },
            {
                "field": "pragmatic_weight",
                "label": "实用价值权重",
                "type": "slider",
                "default": 0.6,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "实用价值（预期收益）在策略选择中的权重",
                "category": "主动推理",
            },
            {
                "field": "exploration_decay",
                "label": "探索衰减率",
                "type": "slider",
                "default": 0.95,
                "min": 0.5,
                "max": 1.0,
                "step": 0.01,
                "help": "探索奖励随时间的衰减因子",
                "category": "主动推理",
            },
            {
                "field": "min_exploration_bonus",
                "label": "最小探索奖励",
                "type": "slider",
                "default": 0.01,
                "min": 0.0,
                "max": 0.5,
                "step": 0.01,
                "help": "探索奖励的最小值，防止探索完全消失",
                "category": "主动推理",
            },
            # ==================== 高级模块(因果/记忆/预测) ====================
            {
                "field": "causal_inference_enabled",
                "label": "启用因果推断",
                "type": "toggle",
                "default": True,
                "help": "是否启用因果反事实引擎，用于因果分析与反事实推演",
                "category": "高级模块",
            },
            {
                "field": "causal_graph_max_nodes",
                "label": "因果图最大节点数",
                "type": "slider",
                "default": 20,
                "min": 3,
                "max": 50,
                "step": 1,
                "help": "因果图中允许的最大节点数量",
                "category": "高级模块",
            },
            {
                "field": "causal_dag_confidence_threshold",
                "label": "因果置信度阈值",
                "type": "slider",
                "default": 0.3,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "因果边存在的置信度阈值",
                "category": "高级模块",
            },
            {
                "field": "memory_enabled",
                "label": "启用记忆模块",
                "type": "toggle",
                "default": True,
                "help": "是否启用互补学习记忆系统",
                "category": "高级模块",
            },
            {
                "field": "memory_hippocampus_max_episodes",
                "label": "海马体最大容量",
                "type": "slider",
                "default": 1000,
                "min": 100,
                "max": 10000,
                "step": 100,
                "help": "海马体（快速通道）存储的最大 episode 数量",
                "category": "高级模块",
            },
            {
                "field": "memory_consolidation_interval",
                "label": "记忆巩固间隔",
                "type": "slider",
                "default": 24,
                "min": 1,
                "max": 168,
                "step": 1,
                "help": "记忆巩固间隔（小时）",
                "category": "高级模块",
            },
            {
                "field": "memory_replay_batch_size",
                "label": "回放批次大小",
                "type": "slider",
                "default": 32,
                "min": 8,
                "max": 256,
                "step": 8,
                "help": "睡眠回放阶段的批次大小",
                "category": "高级模块",
            },
            {
                "field": "memory_similarity_top_k",
                "label": "相似检索 Top-K",
                "type": "slider",
                "default": 5,
                "min": 1,
                "max": 50,
                "step": 1,
                "help": "记忆相似检索时返回的 top-k 结果数量",
                "category": "高级模块",
            },
            {
                "field": "memory_saliency_threshold",
                "label": "记忆显著性阈值",
                "type": "slider",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "记忆巩固过程中使用的显著性阈值",
                "category": "高级模块",
            },
            {
                "field": "prediction_error_enabled",
                "label": "启用预测误差",
                "type": "toggle",
                "default": True,
                "help": "是否启用预测误差计算模块",
                "category": "高级模块",
            },
            {
                "field": "prediction_error_surprise_threshold",
                "label": "惊奇检测阈值",
                "type": "slider",
                "default": 2.0,
                "min": 0.5,
                "max": 10.0,
                "step": 0.1,
                "help": "惊奇检测阈值（标准差倍数），超过此值触发惊奇信号",
                "category": "高级模块",
            },
            {
                "field": "prediction_error_precision_dynamics",
                "label": "精度动态更新",
                "type": "toggle",
                "default": True,
                "help": "是否启用预测精度的动态更新机制",
                "category": "高级模块",
            },
            # ==================== L-IWM 集成 ====================
            {
                "field": "l_iwm_enabled",
                "label": "启用 L-IWM 集成",
                "type": "toggle",
                "default": False,
                "help": "是否启用 L-IWM 可学习模块（替代原始硬编码实现）",
                "category": "L-IWM 集成",
            },
            {
                "field": "l_iwm_config_path",
                "label": "L-IWM 配置路径",
                "type": "text",
                "default": "",
                "help": "L-IWM 配置文件路径，留空使用默认 LIWMConfig",
                "category": "L-IWM 集成",
            },
            {
                "field": "l_iwm_input_dim",
                "label": "L-IWM 输入维度",
                "type": "slider",
                "default": 20,
                "min": 4,
                "max": 128,
                "step": 1,
                "help": "L-IWM RSSM 世界模型的输入观测维度",
                "category": "L-IWM 集成",
            },
            # ==================== HSR-MC 集成 ====================
            {
                "field": "hsrc_mc_enabled",
                "label": "启用 HSR-MC 集成",
                "type": "toggle",
                "default": False,
                "help": "是否启用 HSR-MC（超网络自指涉元控制器）",
                "category": "HSR-MC 集成",
            },
            {
                "field": "hsrc_mc_config_path",
                "label": "HSR-MC 配置路径",
                "type": "text",
                "default": "",
                "help": "HSR-MC 配置文件路径，留空使用默认 HSRMCConfig",
                "category": "HSR-MC 集成",
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
                "help": "开启后打印详细的中间计算结果，用于调试",
                "category": "日志与调试",
            },
        ]

    @classmethod
    def from_ui_values(cls, ui_values: dict[str, Any]) -> "HPCLoopConfig":
        """从 UI 表单值创建配置实例"""
        return cls(**{k: v for k, v in ui_values.items() if k in cls.__dataclass_fields__})

    def merge_with(self, overrides: dict[str, Any]) -> "HPCLoopConfig":
        """合并覆盖配置，返回新实例"""
        new_config = HPCLoopConfig()
        for field_name in self.__dataclass_fields__:
            if field_name in overrides:
                setattr(new_config, field_name, overrides[field_name])
            else:
                setattr(new_config, field_name, getattr(self, field_name))
        return new_config

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HPCLoopConfig":
        """从字典重建配置"""
        config = cls()
        for field_name in cls.__dataclass_fields__:
            if field_name in d:
                setattr(config, field_name, d[field_name])
        return config
