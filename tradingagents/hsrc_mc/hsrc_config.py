# TradingAgents/hsrc_mc/hsrc_config.py
"""
HSR-MC 配置类
==============

控制 HSR-MC (超网络自指涉元控制器) 的所有开关与超参数。
遵循 Round 2 L-IWM 的配置模式 (LIWMConfig)，通过 .env 文件加载。

用法:
    config = HSRMCConfig.from_env()
    manager = HSRMCManager(config, l_iwm_manager)
"""

import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class HSRMCConfig:
    """
    HSR-MC 主配置。

    所有参数可通过环境变量 HSRC_MC_* 覆盖，也支持 merge_with() 动态合并。
    """

    # ==================== 主开关 ====================
    enabled: bool = True
    """全局启用/禁用 HSR-MC。设置为 False 则跳过所有 HSR-MC 处理。"""

    verbose: bool = False
    """详细日志输出"""

    # ==================== MetaObserver 配置 ====================
    observer_gradient_norm_threshold: float = 10.0
    """梯度范数告警阈值（超过此值触发梯度爆炸告警）"""

    observer_loss_stagnation_window: int = 20
    """损失停滞检测窗口大小（训练步数）"""

    observer_loss_stagnation_tol: float = 1e-6
    """损失停滞容忍度（窗口内最大损失变化小于此值判定为停滞）"""

    observer_performance_decay_window: int = 50
    """性能衰减检测窗口"""

    observer_performance_decay_threshold: float = -0.05
    """性能衰减斜率阈值（负值表示衰减）"""

    observer_learning_imbalance_threshold: float = 0.3
    """学习不平衡检测阈值（模块间梯度范数比的偏差阈值）"""

    observer_regime_change_sensitivity: float = 0.05
    """市场制度变化检测灵敏度（预测误差分布偏移检测）"""

    observer_health_check_interval: int = 10
    """健康检查间隔（训练步数）"""

    observer_max_history: int = 1000
    """观察历史最大长度"""

    # ==================== HyperNetwork 配置 ====================
    hyper_hidden_dim: int = 64
    """超网络隐藏层维度"""

    hyper_learning_rate: float = 1e-3
    """超网络学习率"""

    hyper_beta1: float = 0.9
    """超网络 Adam beta1"""

    hyper_beta2: float = 0.999
    """超网络 Adam beta2"""

    hyper_meta_learning_rate: float = 1e-4
    """元学习率（超网络生成参数的缩放因子）"""

    hyper_output_noise: float = 0.01
    """超网络输出噪声（探索性）"""

    hyper_context_dim: int = 16
    """上下文嵌入维度"""

    # ==================== SelfModel 配置 ====================
    self_model_hidden_dim: int = 32
    """自模型隐藏层维度"""

    self_model_learning_rate: float = 1e-3
    """自模型学习率"""

    self_model_beta1: float = 0.9
    """自模型 Adam beta1"""

    self_model_beta2: float = 0.999
    """自模型 Adam beta2"""

    self_model_prediction_horizon: int = 10
    """自模型预测 horizon（未来多少步的性能）"""

    self_model_reflexivity_strength: float = 0.1
    """反身性效应强度（自预测对实际性能的影响系数）"""

    self_model_deception_threshold: float = 0.15
    """自我欺骗检测阈值（自预测 vs 实际表现的 MAE 阈值）"""

    self_model_history_len: int = 200
    """自模型训练历史长度"""

    # ==================== 元学习循环配置 ====================
    meta_learning_interval: int = 50
    """元学习间隔（每 N 步执行一次完整的元学习更新）"""

    meta_batch_size: int = 32
    """元批次大小"""

    meta_spsa_perturbations: int = 1
    """SPSA 扰动次数（用于元梯度估计）"""

    meta_spsa_c: float = 1e-4
    """SPSA 扰动步长"""

    meta_adjustment_scale: float = 0.5
    """元参数调整幅度缩放因子"""

    # ==================== LangGraph 节点配置 ====================
    node_observe_after: str = "l_iwm_gws"
    """观察节点在哪个节点之后执行"""

    node_adjust_before: str = "hpc_reflect"
    """调整节点在哪个节点之前执行"""

    # 🔥 [Bug #5 修复] 首次运行预热参数
    warmup_runs: int = 3
    """首次运行预热步数（在此步数内使用宽松的异常检测阈值，避免冷启动误报）"""

    # ==================== 日志与调试 ====================
    log_meta_trajectory: bool = False
    """是否记录元学习轨迹（用于事后分析）"""

    @classmethod
    def from_env(cls) -> "HSRMCConfig":
        """
        从环境变量加载配置。

        环境变量命名规则:
            HSRC_MC_<PARAMETER_NAME_UPPERCASE>

        例如:
            HSRC_MC_ENABLED=true
            HSRC_MC_HYPER_HIDDEN_DIM=128
            HSRC_MC_META_LEARNING_INTERVAL=100
        """
        prefix = "HSRC_MC_"
        type_map = {
            bool: lambda v: v.lower() in ("true", "1", "yes"),
            int: int,
            float: float,
            str: str,
        }

        config = cls()
        for field_def in cls.__dataclass_fields__.values():
            env_name = prefix + field_def.name.upper()
            env_val = os.environ.get(env_name)
            if env_val is not None:
                for py_type, converter in type_map.items():
                    if field_def.type is py_type or field_def.type == Optional[py_type]:
                        try:
                            setattr(config, field_def.name, converter(env_val))
                        except (ValueError, TypeError):
                            # 如果转换失败，保持默认值
                            pass
                        break

        return config

    def merge_with(self, overrides: dict[str, Any]) -> "HSRMCConfig":
        """
        用字典覆盖配置项并返回新实例。

        Args:
            overrides: {配置字段名: 新值}

        Returns:
            HSRMCConfig: 新配置实例（原实例不变）
        """
        new_config = HSRMCConfig(**{f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()})
        for key, val in overrides.items():
            if hasattr(new_config, key):
                setattr(new_config, key, val)
        return new_config

    def to_dict(self) -> dict[str, Any]:
        """将配置序列化为字典"""
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}

    @classmethod
    def to_ui_schema(cls) -> list[dict[str, Any]]:
        """生成 UI schema，供 Streamlit 自动渲染配置面板"""
        return [
            # ==================== 基础设置 ====================
            {
                "field": "enabled",
                "label": "启用 HSR-MC",
                "type": "toggle",
                "default": True,
                "help": "全局启用或禁用 HSR-MC 超网络自指涉元控制器",
                "category": "基础设置",
            },
            {
                "field": "verbose",
                "label": "详细日志",
                "type": "toggle",
                "default": False,
                "help": "是否输出详细的日志信息",
                "category": "基础设置",
            },
            # ==================== 观察器配置 ====================
            {
                "field": "observer_gradient_norm_threshold",
                "label": "梯度范数阈值",
                "type": "slider",
                "default": 10.0,
                "min": 0.5,
                "max": 50.0,
                "step": 0.5,
                "help": "梯度范数告警阈值，超过此值触发梯度爆炸告警",
                "category": "观察器配置",
            },
            {
                "field": "observer_loss_stagnation_window",
                "label": "损失停滞窗口",
                "type": "slider",
                "default": 20,
                "min": 10,
                "max": 200,
                "step": 5,
                "help": "损失停滞检测窗口大小（训练步数）",
                "category": "观察器配置",
            },
            {
                "field": "observer_loss_stagnation_tol",
                "label": "损失停滞容忍度",
                "type": "number",
                "default": 1e-6,
                "min": 1e-10,
                "max": 1.0,
                "step": 1e-7,
                "help": "窗口内最大损失变化小于此值判定为停滞",
                "category": "观察器配置",
            },
            {
                "field": "observer_performance_decay_window",
                "label": "性能衰减窗口",
                "type": "slider",
                "default": 50,
                "min": 20,
                "max": 500,
                "step": 5,
                "help": "性能衰减检测窗口",
                "category": "观察器配置",
            },
            {
                "field": "observer_performance_decay_threshold",
                "label": "性能衰减阈值",
                "type": "slider",
                "default": -0.05,
                "min": -1.0,
                "max": 0.0,
                "step": 0.01,
                "help": "性能衰减斜率阈值，负值表示性能下降",
                "category": "观察器配置",
            },
            {
                "field": "observer_learning_imbalance_threshold",
                "label": "学习不平衡阈值",
                "type": "slider",
                "default": 0.3,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "help": "模块间梯度范数比的偏差阈值，超过此值触发学习不平衡告警",
                "category": "观察器配置",
            },
            {
                "field": "observer_regime_change_sensitivity",
                "label": "市场制度变化灵敏度",
                "type": "slider",
                "default": 0.05,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "预测误差分布偏移检测的灵敏度",
                "category": "观察器配置",
            },
            {
                "field": "observer_health_check_interval",
                "label": "健康检查间隔",
                "type": "slider",
                "default": 10,
                "min": 1,
                "max": 100,
                "step": 1,
                "help": "健康检查的执行间隔（训练步数）",
                "category": "观察器配置",
            },
            {
                "field": "observer_max_history",
                "label": "观察历史最大长度",
                "type": "slider",
                "default": 1000,
                "min": 100,
                "max": 10000,
                "step": 100,
                "help": "观察器保存的历史记录最大长度",
                "category": "观察器配置",
            },
            # ==================== 超网络 ====================
            {
                "field": "hyper_hidden_dim",
                "label": "超网络隐藏维度",
                "type": "slider",
                "default": 64,
                "min": 16,
                "max": 256,
                "step": 8,
                "help": "超网络隐藏层神经元的数量",
                "category": "超网络",
            },
            {
                "field": "hyper_learning_rate",
                "label": "超网络学习率",
                "type": "number",
                "default": 0.001,
                "min": 1e-6,
                "max": 0.1,
                "step": 1e-5,
                "help": "超网络使用的 Adam 优化器学习率",
                "category": "超网络",
            },
            {
                "field": "hyper_beta1",
                "label": "Adam Beta1",
                "type": "slider",
                "default": 0.9,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "超网络 Adam 优化器的 beta1 参数",
                "category": "超网络",
            },
            {
                "field": "hyper_beta2",
                "label": "Adam Beta2",
                "type": "slider",
                "default": 0.999,
                "min": 0.0,
                "max": 1.0,
                "step": 0.001,
                "help": "超网络 Adam 优化器的 beta2 参数",
                "category": "超网络",
            },
            {
                "field": "hyper_meta_learning_rate",
                "label": "元学习率",
                "type": "number",
                "default": 0.0001,
                "min": 1e-7,
                "max": 0.1,
                "step": 1e-6,
                "help": "超网络的元学习率，控制生成参数的缩放因子",
                "category": "超网络",
            },
            {
                "field": "hyper_output_noise",
                "label": "输出噪声",
                "type": "slider",
                "default": 0.01,
                "min": 0.0,
                "max": 0.1,
                "step": 0.001,
                "help": "超网络输出添加的探索性噪声",
                "category": "超网络",
            },
            {
                "field": "hyper_context_dim",
                "label": "上下文维度",
                "type": "slider",
                "default": 16,
                "min": 4,
                "max": 64,
                "step": 4,
                "help": "上下文嵌入向量的维度",
                "category": "超网络",
            },
            # ==================== 自模型 ====================
            {
                "field": "self_model_hidden_dim",
                "label": "自模型隐藏维度",
                "type": "slider",
                "default": 32,
                "min": 16,
                "max": 256,
                "step": 8,
                "help": "自模型隐藏层神经元的数量",
                "category": "自模型",
            },
            {
                "field": "self_model_learning_rate",
                "label": "自模型学习率",
                "type": "number",
                "default": 0.001,
                "min": 1e-6,
                "max": 0.1,
                "step": 1e-5,
                "help": "自模型使用的学习率",
                "category": "自模型",
            },
            {
                "field": "self_model_beta1",
                "label": "自模型 Adam Beta1",
                "type": "slider",
                "default": 0.9,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "自模型 Adam 优化器的 beta1 参数",
                "category": "自模型",
            },
            {
                "field": "self_model_beta2",
                "label": "自模型 Adam Beta2",
                "type": "slider",
                "default": 0.999,
                "min": 0.0,
                "max": 1.0,
                "step": 0.001,
                "help": "自模型 Adam 优化器的 beta2 参数",
                "category": "自模型",
            },
            {
                "field": "self_model_prediction_horizon",
                "label": "预测 Horizon",
                "type": "slider",
                "default": 10,
                "min": 1,
                "max": 100,
                "step": 1,
                "help": "自模型预测未来多少步的性能变化",
                "category": "自模型",
            },
            {
                "field": "self_model_reflexivity_strength",
                "label": "自反性强度",
                "type": "slider",
                "default": 0.1,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "自预测对实际性能的反身性影响系数",
                "category": "自模型",
            },
            {
                "field": "self_model_deception_threshold",
                "label": "欺骗检测阈值",
                "type": "slider",
                "default": 0.15,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "自预测与实际表现的 MAE 阈值，超过此值判定为自我欺骗",
                "category": "自模型",
            },
            {
                "field": "self_model_history_len",
                "label": "训练历史长度",
                "type": "slider",
                "default": 200,
                "min": 50,
                "max": 2000,
                "step": 10,
                "help": "自模型训练使用的历史记录长度",
                "category": "自模型",
            },
            # ==================== 元学习 ====================
            {
                "field": "meta_learning_interval",
                "label": "元学习间隔",
                "type": "slider",
                "default": 50,
                "min": 10,
                "max": 200,
                "step": 5,
                "help": "每 N 步执行一次完整的元学习更新",
                "category": "元学习",
            },
            {
                "field": "meta_batch_size",
                "label": "元批次大小",
                "type": "slider",
                "default": 32,
                "min": 2,
                "max": 64,
                "step": 1,
                "help": "元学习使用的批次大小",
                "category": "元学习",
            },
            {
                "field": "meta_spsa_perturbations",
                "label": "SPSA 扰动次数",
                "type": "slider",
                "default": 1,
                "min": 1,
                "max": 20,
                "step": 1,
                "help": "SPSA 随机扰动次数，用于元梯度估计",
                "category": "元学习",
            },
            {
                "field": "meta_spsa_c",
                "label": "SPSA 扰动步长",
                "type": "number",
                "default": 0.0001,
                "min": 1e-10,
                "max": 1.0,
                "step": 1e-5,
                "help": "SPSA 梯度估计的扰动步长",
                "category": "元学习",
            },
            {
                "field": "meta_adjustment_scale",
                "label": "元调整幅度",
                "type": "slider",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "help": "元参数调整幅度的缩放因子",
                "category": "元学习",
            },
            {
                "field": "node_observe_after",
                "label": "观察节点位置",
                "type": "text",
                "default": "l_iwm_gws",
                "help": "观察节点在 LangGraph 中指定节点之后执行",
                "category": "元学习",
            },
            {
                "field": "node_adjust_before",
                "label": "调整节点位置",
                "type": "text",
                "default": "hpc_reflect",
                "help": "调整节点在 LangGraph 中指定节点之前执行",
                "category": "元学习",
            },
            # ==================== 日志与调试 ====================
            {
                "field": "log_meta_trajectory",
                "label": "记录元轨迹",
                "type": "toggle",
                "default": False,
                "help": "是否记录元学习轨迹，用于事后分析和可视化",
                "category": "日志与调试",
            },
        ]

    @classmethod
    def from_ui_values(cls, ui_values: dict[str, Any]) -> "HSRMCConfig":
        """从 UI 表单值创建配置实例"""
        return cls(**{k: v for k, v in ui_values.items() if k in cls.__dataclass_fields__})
