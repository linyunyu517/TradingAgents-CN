# TradingAgents/hsrc_mc/hsrc_integration.py
"""
HSR-MC 统一管理器 (hsrc_integration.py)
========================================

协调 MetaObserver, HyperNetwork, SelfModel 三个组件，
为 HPC-Loop 的 LangGraph 流程提供 HSR-MC 节点。

职责:
    1. 管理 HSR-MC 三个组件的生命周期
    2. 提供元学习循环 (meta_learning_loop)
    3. 提供在线元学习步骤 (online_meta_step)
    4. 创建 LangGraph 节点函数

集成方式:
    HSRMCManager 被 HPCLoopManager 实例化，
    然后通过 get_enhanced_nodes() 和 get_enhanced_edges()
    将其节点插入 LangGraph 流程。
"""

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

from .hsrc_config import HSRMCConfig
from .hypernetwork import HyperNetwork
from .meta_observer import MetaObserver
from .self_model import SelfModel

logger = logging.getLogger("hsrc_mc")


class HSRMCManager:
    """
    HSR-MC 管理器 — 协调所有元学习组件。

    使用流程:
        manager = HSRMCManager(config, l_iwm_manager)
        result = manager.online_meta_step(module_losses, grads_dict, module_performance)
        observe_result = manager.run_observe_node(state)
        adjust_result = manager.run_adjust_node(state)
        reflect_result = manager.run_reflect_node(state)
        meta_result = manager.run_meta_update_node(state)
    """

    def __init__(self, config: HSRMCConfig, l_iwm_manager=None):
        """
        Args:
            config: HSRMCConfig 实例
            l_iwm_manager: LIWMManager 实例 (可选，用于访问模块状态)
        """
        self.config = config
        self.l_iwm_manager = l_iwm_manager

        # 观察向量维度: 6模块 * 3特征 + 5制度onehot + 3健康onehot = 26
        self._observation_dim = len(MetaObserver.MODULE_NAMES) * 3 + 5 + 3

        # ==================== 三大核心组件 ====================
        self.observer = MetaObserver(config)
        self.hypernetwork = HyperNetwork(config, input_dim=self._observation_dim)
        self.self_model = SelfModel(
            config,
            input_dim=config.self_model_prediction_horizon,
            n_modules=len(MetaObserver.MODULE_NAMES),
        )

        # ==================== 运行时状态 ====================
        self._step: int = 0
        self._is_initialized: bool = True

        # 最近元参数缓存
        self._last_meta_params: dict[str, Any] | None = None
        self._last_observation_result: dict[str, Any] | None = None
        self._last_adjustment_result: dict[str, Any] | None = None
        self._last_reflection_result: dict[str, Any] | None = None

        # 性能历史 (用于自模型输入)
        self._performance_history: dict[str, deque] = {
            name: deque(maxlen=config.self_model_history_len) for name in MetaObserver.MODULE_NAMES
        }

        # 元学习轨迹日志
        self._meta_trajectory: list[dict[str, Any]] = []

        # 是否已启用
        self._enabled: bool = config.enabled

        logger.info(
            f"[HSR-MC] 初始化完成: enabled={self._enabled}, "
            f"observation_dim={self._observation_dim}, "
            f"hyper_output_dim={self.hypernetwork.output_dim}",
        )
        logger.info(
            f"[HSR-MC] 组件状态: observer={self.observer is not None}, "
            f"hypernetwork={self.hypernetwork is not None}, "
            f"self_model={self.self_model is not None}, "
            f"warmup_runs={getattr(config, 'warmup_runs', 'N/A')}",
        )
        logger.info(
            f"[HSR-MC] 观察器配置: "
            f"max_history={config.observer_max_history}, "
            f"health_check_interval={config.observer_health_check_interval}, "
            f"gradient_threshold={config.observer_gradient_norm_threshold}",
        )

    # ==================== 属性 ====================

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        self.config.enabled = value
        logger.info(f"[HSR-MC] {'启用' if value else '禁用'}")

    # ==================== 在线元学习步骤 ====================

    def online_meta_step(
        self,
        module_losses: dict[str, float],
        grads_dict: dict[str, np.ndarray] | None = None,
        module_performance: dict[str, float] | None = None,
        prediction_errors: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        执行一步在线元学习。

        流程:
            1. MetaObserver 观察系统状态
            2. 记录性能历史
            3. 如果到达元学习间隔，执行完整元学习循环
            4. 否则只执行观察

        Args:
            module_losses: {模块名: 损失值}
            grads_dict: {参数名: 梯度数组} (可选)
            module_performance: {模块名: 性能指标} (可选)
            prediction_errors: 预测误差列表 (可选)

        Returns:
            Dict: 元学习结果
        """
        if not self._enabled:
            logger.warning("[HSR-MC] ⚠️ online_meta_step 跳过（HSR-MC 已禁用）")
            return {"skipped": True, "reason": "HSR-MC 已禁用"}

        self._step += 1

        # 1. 观察
        observation_result = self.observer.observe(
            module_losses=module_losses,
            grads_dict=grads_dict,
            module_performance=module_performance,
            prediction_errors=prediction_errors,
        )

        # 2. 记录性能历史
        if module_performance is not None:
            for name in MetaObserver.MODULE_NAMES:
                if name in module_performance:
                    self._performance_history[name].append(module_performance[name])

        # 3. 是否执行完整元学习
        if self._step % self.config.meta_learning_interval == 0:
            return self._run_meta_learning_cycle(observation_result)
        self._last_observation_result = observation_result
        return {
            "step": self._step,
            "observation": observation_result,
            "meta_update": False,
            "next_meta_step": self._step
            + (self.config.meta_learning_interval - self._step % self.config.meta_learning_interval),
        }

    # ==================== 元学习循环 ====================

    def _run_meta_learning_cycle(self, observation_result: dict[str, Any]) -> dict[str, Any]:
        """
        执行完整的元学习循环。

        流程:
            1. 获取观察向量和反身性向量
            2. HyperNetwork 生成元参数
            3. SelfModel 预测性能
            4. 反身性修正
            5. 应用元参数调整
            6. 记录轨迹

        Returns:
            Dict: 完整元学习结果
        """
        # 1. 获取观察向量
        obs_vector = self.observer.get_observation_vector()

        # 2. 获取反身性向量
        reflexivity_vector = self.self_model.get_reflexivity_vector()

        # 3. 构建上下文向量 (观察 + 反身性)
        context_vector = np.concatenate([obs_vector, reflexivity_vector])

        # 4. HyperNetwork 生成元参数
        meta_params = self.hypernetwork.generate(obs_vector, add_noise=True)
        self._last_meta_params = meta_params

        # 5. SelfModel 预测性能
        perf_window = {name: list(self._performance_history[name]) for name in MetaObserver.MODULE_NAMES}
        predictions = self.self_model.predict(perf_window)

        # 6. 反身性修正
        reflexivity_corrections = self.self_model.compute_reflexivity_effect(meta_params)

        # 7. 应用反身性修正到元参数
        corrected_params = self._apply_reflexivity_corrections(meta_params, reflexivity_corrections)

        # 8. 记录
        result = {
            "step": self._step,
            "observation": observation_result,
            "meta_update": True,
            "meta_params": corrected_params,
            "predictions": predictions,
            "reflexivity_corrections": reflexivity_corrections,
            "context_vector": context_vector.tolist(),
        }

        self._last_observation_result = observation_result
        self._last_adjustment_result = result

        # 9. 轨迹记录
        if self.config.log_meta_trajectory:
            self._meta_trajectory.append(
                {
                    "step": self._step,
                    "meta_params": corrected_params,
                    "predictions": predictions,
                    "health": observation_result.get("health", {}),
                    "anomalies": observation_result.get("anomalies", []),
                },
            )

        return result

    def _apply_reflexivity_corrections(
        self,
        meta_params: dict[str, Any],
        corrections: dict[str, float],
    ) -> dict[str, Any]:
        """
        将反身性修正应用到元参数上。

        Args:
            meta_params: HyperNetwork 生成的元参数
            corrections: {模块名: 修正因子}

        Returns:
            Dict: 修正后的元参数
        """
        corrected = {
            "learning_rate_factors": {},
            "regularization_factors": {},
            "priority_adjustments": {},
            "global_exploration_factor": meta_params.get("global_exploration_factor", 1.0),
            "global_lr_scale": meta_params.get("global_lr_scale", 1.0),
            "raw_output": meta_params.get("raw_output", np.array([])),
        }

        for name in MetaObserver.MODULE_NAMES:
            cf = corrections.get(name, 1.0)
            lr_factor = meta_params.get("learning_rate_factors", {}).get(name, 1.0)
            reg_factor = meta_params.get("regularization_factors", {}).get(name, 1.0)
            pri_adj = meta_params.get("priority_adjustments", {}).get(name, 0.0)

            # 反身性修正
            corrected["learning_rate_factors"][name] = lr_factor * cf
            corrected["regularization_factors"][name] = reg_factor * cf
            corrected["priority_adjustments"][name] = pri_adj + (cf - 1.0) * 0.1

        return corrected

    # ==================== SelfModel 更新 ====================

    def update_self_model(
        self,
        actual_performance: dict[str, float],
    ) -> dict[str, float]:
        """
        用实际性能数据更新自模型。

        应在每次完整的前向传播后调用。

        Args:
            actual_performance: {模块名: 实际性能值}

        Returns:
            Dict: 自模型训练统计
        """
        if not self._enabled:
            return {"skipped": True}

        perf_window = {name: list(self._performance_history[name]) for name in MetaObserver.MODULE_NAMES}

        result = self.self_model.update(perf_window, actual_performance)
        return result

    # ==================== LangGraph 节点工厂 ====================

    def create_observe_node(self) -> Callable:
        """
        创建 HSR-MC 观察节点。

        该节点:
            1. 从 state 中提取模块损失和梯度
            2. 执行观察
            3. 将观察结果写入 state

        Returns:
            Callable: LangGraph 节点函数
        """

        def hsrc_observe_node(state: dict[str, Any]) -> dict[str, Any]:
            _t0 = time.time()
            logger.info("[HSR-MC] 🔍 hsrc_observe 开始执行...")

            if not self._enabled:
                logger.info("[HSR-MC] ⚠️ hsrc_observe 跳过（未启用）")
                return {"hsrc_mc": {"observe_skipped": True}}

            try:
                # 从 state 提取模块信息
                module_losses = state.get("module_losses", {})
                grads_info = state.get("gradient_info")
                module_perf = state.get("module_performance")
                pred_errors = state.get("prediction_errors")

                # 执行在线元学习步骤
                result = self.online_meta_step(
                    module_losses=module_losses,
                    grads_dict=grads_info,
                    module_performance=module_perf,
                    prediction_errors=pred_errors,
                )

                elapsed = time.time() - _t0
                logger.info(f"[HSR-MC] ✅ hsrc_observe 完成, 耗时{elapsed:.2f}s")

                # 写入 state
                return {
                    "hsrc_mc": {
                        "meta_result": result,
                        "step": self._step,
                        "health": self.observer.get_health_report() if self._enabled else {},
                        "anomalies": self.observer.get_anomalies() if self._enabled else [],
                        "regime": self.observer.get_regime_info() if self._enabled else {},
                        "intervention_suggestions": (
                            self.observer.get_intervention_suggestions() if self._enabled else []
                        ),
                    },
                }
            except Exception as e:
                elapsed = time.time() - _t0
                logger.error(f"[HSR-MC] ❌ hsrc_observe 异常 ({elapsed:.2f}s): {e}", exc_info=True)
                return {"hsrc_mc": {"observe_error": str(e), "elapsed": elapsed, "skipped": True}}

        return hsrc_observe_node

    def create_adjust_node(self) -> Callable:
        """
        创建 HSR-MC 调整节点。

        该节点:
            1. 从 state 读取观察结果
            2. 根据元参数调整模块配置
            3. 将调整写入 state

        Returns:
            Callable: LangGraph 节点函数
        """

        def hsrc_adjust_node(state: dict[str, Any]) -> dict[str, Any]:
            _t0 = time.time()
            logger.info("[HSR-MC] 🔧 hsrc_adjust 开始执行...")

            if not self._enabled:
                logger.info("[HSR-MC] ⚠️ hsrc_adjust 跳过（未启用）")
                return {"hsrc_mc_adjust": {"adjust_skipped": True}}

            try:
                meta_result = state.get("hsrc_mc", {}).get("meta_result", {})
                meta_params = meta_result.get("meta_params", {}) if meta_result else {}

                # 提取要应用于模块的调整
                adjustments = {}
                if meta_params:
                    adjustments = {
                        "learning_rate_factors": meta_params.get("learning_rate_factors", {}),
                        "regularization_factors": meta_params.get("regularization_factors", {}),
                        "priority_adjustments": meta_params.get("priority_adjustments", {}),
                        "global_exploration_factor": meta_params.get("global_exploration_factor", 1.0),
                        "global_lr_scale": meta_params.get("global_lr_scale", 1.0),
                    }

                # 如果有 LIWMManager，应用调整
                if self.l_iwm_manager is not None and adjustments:
                    self._apply_adjustments(adjustments)

                elapsed = time.time() - _t0
                logger.info(f"[HSR-MC] ✅ hsrc_adjust 完成, 耗时{elapsed:.2f}s")

                return {
                    "hsrc_mc_adjust": {
                        "adjustments": adjustments,
                        "step": self._step,
                    },
                }
            except Exception as e:
                elapsed = time.time() - _t0
                logger.error(f"[HSR-MC] ❌ hsrc_adjust 异常 ({elapsed:.2f}s): {e}", exc_info=True)
                return {"hsrc_mc_adjust": {"adjust_error": str(e), "elapsed": elapsed, "skipped": True}}

        return hsrc_adjust_node

    def create_reflect_node(self) -> Callable:
        """
        创建 HSR-MC 自指涉节点。

        该节点:
            1. 检测自我欺骗
            2. 计算反身性修正
            3. 更新自模型

        Returns:
            Callable: LangGraph 节点函数
        """

        def hsrc_reflect_node(state: dict[str, Any]) -> dict[str, Any]:
            _t0 = time.time()
            logger.info("[HSR-MC] 🔄 hsrc_reflect 开始执行...")

            if not self._enabled:
                logger.info("[HSR-MC] ⚠️ hsrc_reflect 跳过（未启用）")
                return {"hsrc_mc_reflect": {"reflect_skipped": True}}

            try:
                # 获取实际性能
                actual_perf = state.get("module_performance", {})
                if actual_perf:
                    self.update_self_model(actual_perf)

                # 检测自我欺骗
                deception = self.self_model.detect_self_deception()

                # 获取反身性向量
                reflexivity = self.self_model.get_reflexivity_vector()

                elapsed = time.time() - _t0
                logger.info(f"[HSR-MC] ✅ hsrc_reflect 完成, 耗时{elapsed:.2f}s")

                result = {
                    "hsrc_mc_reflect": {
                        "deception": deception,
                        "reflexivity_vector": reflexivity.tolist(),
                        "self_model_stats": self.self_model.get_statistics(),
                        "step": self._step,
                    },
                }

                self._last_reflection_result = result
                return result
            except Exception as e:
                elapsed = time.time() - _t0
                logger.error(f"[HSR-MC] ❌ hsrc_reflect 异常 ({elapsed:.2f}s): {e}", exc_info=True)
                return {"hsrc_mc_reflect": {"reflect_error": str(e), "elapsed": elapsed, "skipped": True}}

        return hsrc_reflect_node

    def create_meta_update_node(self) -> Callable:
        """
        创建 HSR-MC 元更新节点。

        该节点:
            1. 收集本轮元学习结果
            2. 更新超网络参数（如果有元梯度）
            3. 更新轨迹日志

        Returns:
            Callable: LangGraph 节点函数
        """

        def hsrc_meta_update_node(state: dict[str, Any]) -> dict[str, Any]:
            _t0 = time.time()
            logger.info("[HSR-MC] 📊 hsrc_meta_update 开始执行...")

            if not self._enabled:
                logger.info("[HSR-MC] ⚠️ hsrc_meta_update 跳过（未启用）")
                return {"hsrc_mc_meta": {"meta_update_skipped": True}}

            try:
                # 聚合本轮结果
                state.get("hsrc_mc", {}).get("meta_result", {})
                state.get("hsrc_mc_adjust", {})
                state.get("hsrc_mc_reflect", {})

                # 更新 HyperNetwork (如果有元梯度)
                # 注意: 元梯度通过 SPSA 从 SelfModel 的损失传播
                meta_grads = state.get("meta_gradients")
                hyper_update_stats = {}
                if meta_grads is not None:
                    hyper_update_stats = self.hypernetwork.update(meta_grads)

                elapsed = time.time() - _t0
                logger.info(f"[HSR-MC] ✅ hsrc_meta_update 完成, 耗时{elapsed:.2f}s")

                result = {
                    "hsrc_mc_meta": {
                        "hyper_update": hyper_update_stats,
                        "hyper_stats": self.hypernetwork.get_statistics(),
                        "self_model_stats": self.self_model.get_statistics(),
                        "step": self._step,
                    },
                }

                return result
            except Exception as e:
                elapsed = time.time() - _t0
                logger.error(f"[HSR-MC] ❌ hsrc_meta_update 异常 ({elapsed:.2f}s): {e}", exc_info=True)
                return {"hsrc_mc_meta": {"meta_update_error": str(e), "elapsed": elapsed, "skipped": True}}

        return hsrc_meta_update_node

    # ==================== LangGraph 节点和边配置 ====================

    def get_enhanced_nodes(self) -> dict[str, Callable]:
        """
        获取所有 HSR-MC LangGraph 节点。

        Returns:
            Dict[str, Callable]: {节点名: 节点函数}
        """
        return {
            "hsrc_observe": self.create_observe_node(),
            "hsrc_adjust": self.create_adjust_node(),
            "hsrc_reflect": self.create_reflect_node(),
            "hsrc_meta_update": self.create_meta_update_node(),
        }

    def get_enhanced_edges(self) -> list[dict[str, Any]]:
        """
        获取 HSR-MC 边配置。

        HSR-MC 节点插入位置:
            ... → l_iwm_gws → hsrc_observe → hsrc_adjust → hsrc_reflect → hsrc_meta_update → hpc_reflect → ...

        Returns:
            List[Dict]: 边定义列表
        """
        return [
            # 从 L-IWM 最后一个节点到 HSR-MC 观察节点
            {
                "from": self.config.node_observe_after,
                "to": "hsrc_observe",
                "condition": None,
            },
            # HSR-MC 内部链路
            {
                "from": "hsrc_observe",
                "to": "hsrc_adjust",
                "condition": None,
            },
            {
                "from": "hsrc_adjust",
                "to": "hsrc_reflect",
                "condition": None,
            },
            {
                "from": "hsrc_reflect",
                "to": "hsrc_meta_update",
                "condition": None,
            },
            # 回到主流程
            {
                "from": "hsrc_meta_update",
                "to": self.config.node_adjust_before,
                "condition": None,
            },
        ]

    # ==================== 模块调整 ====================

    def _apply_adjustments(self, adjustments: dict[str, Any]) -> None:
        """
        将元参数调整应用到 L-IWM 模块。

        注意: 实际应用中，需要在 LIWMManager 中添加 set_learning_rate() 等方法。
        当前实现记录调整日志，供后续集成。

        Args:
            adjustments: 调整参数字典
        """
        lr_factors = adjustments.get("learning_rate_factors", {})
        reg_factors = adjustments.get("regularization_factors", {})
        global_lr_scale = adjustments.get("global_lr_scale", 1.0)

        # 记录调整信息
        for name, factor in lr_factors.items():
            effective_factor = factor * global_lr_scale
            if abs(effective_factor - 1.0) > 0.05:
                logger.info(f"[HSR-MC] 调整 {name} 学习率: factor={effective_factor:.3f}")

        for name, factor in reg_factors.items():
            if abs(factor - 1.0) > 0.05:
                logger.info(f"[HSR-MC] 调整 {name} 正则化: factor={factor:.3f}")

        exploration = adjustments.get("global_exploration_factor", 1.0)
        if abs(exploration - 1.0) > 0.05:
            logger.info(f"[HSR-MC] 调整全局探索率: factor={exploration:.3f}")

    # ==================== 状态管理 ====================

    def get_state_dict(self) -> dict[str, Any]:
        """获取 HSR-MC 完整状态字典"""
        return {
            "config": self.config.to_dict(),
            "hypernetwork": self.hypernetwork.get_params_dict(),
            "self_model": {
                "train_step": self.self_model.train_step,
                "W_shared": self.self_model.W_shared.tolist(),
                "b_shared": self.self_model.b_shared.tolist(),
                "W_heads": [w.tolist() for w in self.self_model.W_heads],
                "b_heads": [b.tolist() for b in self.self_model.b_heads],
            },
            "step": self._step,
            "trajectory": (self._meta_trajectory[-100:] if self.config.log_meta_trajectory else []),
        }

    def load_state_dict(self, state: dict[str, Any]) -> bool:
        """加载 HSR-MC 状态"""
        try:
            if "hypernetwork" in state:
                self.hypernetwork.load_params_dict(state["hypernetwork"])
            if "self_model" in state:
                sm = state["self_model"]
                self.self_model.train_step = sm.get("train_step", 0)
                if "W_shared" in sm:
                    self.self_model.W_shared = np.array(sm["W_shared"])
                if "b_shared" in sm:
                    self.self_model.b_shared = np.array(sm["b_shared"])
                if "W_heads" in sm:
                    self.self_model.W_heads = np.array(sm["W_heads"])
                if "b_heads" in sm:
                    self.self_model.b_heads = np.array(sm["b_heads"])
            if "step" in state:
                self._step = state["step"]
            return True
        except Exception as e:
            logger.error(f"[HSR-MC] 加载状态失败: {e}")
            return False

    def get_statistics(self) -> dict[str, Any]:
        """获取 HSR-MC 统计信息"""
        return {
            "enabled": self._enabled,
            "step": self._step,
            "observer": {
                "anomaly_count": len(self.observer.get_anomalies()),
                "regime": self.observer.get_regime_info().get("regime", "unknown"),
                "overall_health": self.observer.get_health_report().get("overall_health", "unknown"),
            },
            "hypernetwork": self.hypernetwork.get_statistics(),
            "self_model": self.self_model.get_statistics(),
            "trajectory_length": len(self._meta_trajectory),
        }

    def reset(self) -> None:
        """重置 HSR-MC 管理器状态"""
        self._step = 0
        self.observer.reset()
        self.hypernetwork.reset()
        self.self_model.reset()
        self._last_meta_params = None
        self._last_observation_result = None
        self._last_adjustment_result = None
        self._last_reflection_result = None
        self._meta_trajectory.clear()
        for name in MetaObserver.MODULE_NAMES:
            self._performance_history[name].clear()
        logger.info("[HSR-MC] 已重置")

    def __repr__(self) -> str:
        return (
            f"HSRMCManager(enabled={self._enabled}, step={self._step}, "
            f"observer_anomalies={len(self.observer.get_anomalies())})"
        )
