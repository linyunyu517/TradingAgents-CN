"""
L-IWM 统一管理器 (l_iwm_integration.py)
========================================

协调所有可学习模块的训练、推理和状态管理。
为 HPC-Loop 的 HPCLoopManager 提供统一集成接口。

设计原则:
1. 条件初始化 — 每个模块通过 config 的 `_enabled` 标志控制是否启用
2. 向后兼容 — 禁用所有 L-IWM 模块时，HPC-Loop 回退到原始硬编码实现
3. 训练编排 — 统一的训练循环协调 RSSM → EFE → Causal → EWC → GWS 训练
4. 状态管理 — 每个模块独立保存/加载，同时支持全局快照
"""

import json
import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np

from .differentiable_causal import DifferentiableCausalDiscovery
from .ewc_memory import EWCMemorySystem
from .l_iwm_config import LIWMConfig
from .learnable_efe import LearnableEFEEvaluator
from .learnable_gws import LearnableSaliencyEvaluator
from .real_data_pipeline import RealDataPipeline
from .rssm_world_model import RSSMWorldModel

logger = logging.getLogger("l_iwm")


class LIWMManager:
    """
    L-IWM (Learnable Internal World Model) 统一管理器。

    管理所有 6 个可学习模块的生命周期:
        - RSSMWorldModel (P0): 可学习世界模型
        - RealDataPipeline (P1): 真实数据管道
        - LearnableEFEEvaluator (P2): 可学习 EFE 评估器
        - DifferentiableCausalDiscovery (P3): 可微分因果发现
        - EWCMemorySystem (P4): EWC 防遗忘记忆系统
        - LearnableSaliencyEvaluator (P5): 可学习显著性评估器

    使用示例:
        config = LIWMConfig()
        manager = LIWMManager(config)
        manager.init_modules()
        result = manager.train_on_batch(symbol="000001.SH")
        stats = manager.get_statistics()
        manager.save_all("./checkpoints/")
    """

    def __init__(
        self,
        config: LIWMConfig | None = None,
        input_dim: int = 20,
    ):
        """
        初始化 L-IWM 管理器。

        Args:
            config: LIWMConfig 实例 (None 则使用默认配置)
            input_dim: RSSM 世界模型的输入观测维度
        """
        self.config = config or LIWMConfig()
        self.input_dim = input_dim
        self.train_step = 0
        self.last_train_time: str | None = None

        # ========== 模块实例 (None 表示未初始化或禁用) ==========
        self.rssm: RSSMWorldModel | None = None
        self.data_pipeline: RealDataPipeline | None = None
        self.efe_evaluator: LearnableEFEEvaluator | None = None
        self.causal_discovery: DifferentiableCausalDiscovery | None = None
        self.ewc_memory: EWCMemorySystem | None = None
        self.gws_evaluator: LearnableSaliencyEvaluator | None = None

        # ========== 集成运行时状态 ==========
        # 缓存从各模块提取的最新状态，供 HPC-Loop 查询
        self._last_latent_state: dict[str, Any] = {}
        """最新 RSSM 隐状态"""

        self._last_efe_decomposition: dict[str, Any] = {}
        """最新 EFE 分解结果"""

        self._last_causal_summary: dict[str, Any] = {}
        """最新因果图摘要"""

        self._last_market_features: np.ndarray = np.zeros(input_dim)
        """最新市场特征向量"""

        # ========== 全局统计 ==========
        self._episode_count: int = 0
        self._batch_train_count: int = 0
        self._module_errors: dict[str, int] = {
            "rssm": 0,
            "data_pipeline": 0,
            "efe_evaluator": 0,
            "causal_discovery": 0,
            "ewc_memory": 0,
            "gws_evaluator": 0,
        }

        # 🔥 [Bug #4 修复] 增强 L-IWM 初始化运行时日志
        logger.info(
            f"LIWMManager 初始化完成. "
            f"启用模块: "
            f"RSSM={self.config.rssm_enabled}, "
            f"Data={self.config.real_data_enabled}, "
            f"EFE={self.config.learnable_efe_enabled}, "
            f"Causal={self.config.diff_causal_enabled}, "
            f"EWC={self.config.ewc_memory_enabled}, "
            f"GWS={self.config.learnable_gws_enabled}",
        )
        logger.info(
            f"[LIWM] 运行时配置: "
            f"数据源={self.config.real_data_sources}, "
            f"回溯天数={self.config.real_data_lookback_days}, "
            f"输入维度={self.input_dim}, "
            f"隐状态维度={self.config.rssm_latent_dim}, "
            f"ESBN维度={self.config.rssm_stochastic_dim}",
        )
        logger.info(
            f"[LIWM] 数据管道状态: "
            f"pipeline={self.data_pipeline is not None}, "
            f"可用数据源={self.config.real_data_sources}",
        )
        if self.config.ewc_memory_enabled:
            logger.info(
                f"[LIWM] EWC 记忆系统配置: "
                f"重要参数阈值={getattr(self.config, 'ewc_importance_threshold', 'N/A')}, "
                f"最大任务数={getattr(self.config, 'ewc_max_tasks', 'N/A')}",
            )

    # ==================== 模块初始化 ====================

    def init_modules(self) -> dict[str, bool]:
        """
        根据配置初始化所有启用的可学习模块。

        每个模块独立初始化，失败不影响其他模块。
        模块可序列化/反序列化，支持热加载和热替换。

        Returns:
            Dict[str, bool]: 每个模块的初始化成功状态
        """
        init_status: dict[str, bool] = {}

        # --- RSSM 世界模型 (P0) ---
        if self.config.rssm_enabled:
            try:
                self.rssm = RSSMWorldModel(self.config, input_dim=self.input_dim)
                init_status["rssm"] = True
                logger.info("[LIWM] ✅ RSSMWorldModel 初始化成功")
            except Exception as e:
                init_status["rssm"] = False
                self._module_errors["rssm"] += 1
                logger.error(f"[LIWM] ❌ RSSMWorldModel 初始化失败: {e}")
        else:
            init_status["rssm"] = False
            logger.info("[LIWM] ⏭ RSSMWorldModel 已禁用")

        # --- 真实数据管道 (P1) ---
        if self.config.real_data_enabled:
            try:
                self.data_pipeline = RealDataPipeline(self.config)
                init_status["data_pipeline"] = True
                logger.info("[LIWM] ✅ RealDataPipeline 初始化成功")
            except Exception as e:
                init_status["data_pipeline"] = False
                self._module_errors["data_pipeline"] += 1
                logger.error(f"[LIWM] ❌ RealDataPipeline 初始化失败: {e}")
        else:
            init_status["data_pipeline"] = False
            logger.info("[LIWM] ⏭ RealDataPipeline 已禁用")

        # --- 可学习 EFE 评估器 (P2) ---
        if self.config.learnable_efe_enabled:
            try:
                state_dim = self.config.rssm_latent_dim + self.config.rssm_stochastic_dim  # 32 + 32 = 64
                self.efe_evaluator = LearnableEFEEvaluator(
                    config=self.config,
                    state_dim=state_dim,
                    hidden_dim=self.config.efe_epistemic_dim,
                    learning_rate=self.config.efe_learning_rate,
                    td_lambda=self.config.efe_td_lambda,
                    exploration_alpha=self.config.efe_exploration_alpha,
                )
                init_status["efe_evaluator"] = True
                logger.info("[LIWM] ✅ LearnableEFEEvaluator 初始化成功")
            except Exception as e:
                init_status["efe_evaluator"] = False
                self._module_errors["efe_evaluator"] += 1
                logger.error(f"[LIWM] ❌ LearnableEFEEvaluator 初始化失败: {e}")
        else:
            init_status["efe_evaluator"] = False
            logger.info("[LIWM] ⏭ LearnableEFEEvaluator 已禁用")

        # --- 可微分因果发现 (P3) ---
        if self.config.diff_causal_enabled:
            try:
                self.causal_discovery = DifferentiableCausalDiscovery(
                    config=self.config,
                    max_nodes=self.config.causal_max_nodes,
                    lambda1=self.config.causal_lambda1,
                    lambda2=self.config.causal_lambda2,
                    w_threshold=self.config.causal_w_threshold,
                    max_iter=self.config.causal_max_iter,
                )
                init_status["causal_discovery"] = True
                logger.info("[LIWM] ✅ DifferentiableCausalDiscovery 初始化成功")
            except Exception as e:
                init_status["causal_discovery"] = False
                self._module_errors["causal_discovery"] += 1
                logger.error(f"[LIWM] ❌ DifferentiableCausalDiscovery 初始化失败: {e}")
        else:
            init_status["causal_discovery"] = False
            logger.info("[LIWM] ⏭ DifferentiableCausalDiscovery 已禁用")

        # --- EWC 记忆系统 (P4) ---
        if self.config.ewc_memory_enabled:
            try:
                self.ewc_memory = EWCMemorySystem(
                    config=self.config,
                    lambda_elasticity=self.config.ewc_elasticity,
                    consolidation_interval=self.config.ewc_consolidation_interval,
                    fisher_samples=self.config.ewc_fisher_samples,
                    importance_threshold=self.config.ewc_importance_threshold,
                )
                init_status["ewc_memory"] = True
                logger.info("[LIWM] ✅ EWCMemorySystem 初始化成功")
            except Exception as e:
                init_status["ewc_memory"] = False
                self._module_errors["ewc_memory"] += 1
                logger.error(f"[LIWM] ❌ EWCMemorySystem 初始化失败: {e}")
        else:
            init_status["ewc_memory"] = False
            logger.info("[LIWM] ⏭ EWCMemorySystem 已禁用")

        # --- 可学习显著性评估器 (P5) ---
        if self.config.learnable_gws_enabled:
            try:
                self.gws_evaluator = LearnableSaliencyEvaluator(
                    config=self.config,
                    feature_dim=self.config.gws_feature_dim,
                    learning_rate=self.config.gws_learning_rate,
                    top_k=self.config.gws_top_k,
                    embedding_method=self.config.gws_embedding_method,
                )
                init_status["gws_evaluator"] = True
                logger.info("[LIWM] ✅ LearnableSaliencyEvaluator 初始化成功")
            except Exception as e:
                init_status["gws_evaluator"] = False
                self._module_errors["gws_evaluator"] += 1
                logger.error(f"[LIWM] ❌ LearnableSaliencyEvaluator 初始化失败: {e}")
        else:
            init_status["gws_evaluator"] = False
            logger.info("[LIWM] ⏭ LearnableSaliencyEvaluator 已禁用")

        # 汇总
        enabled = sum(1 for v in init_status.values() if v)
        total = len(init_status)
        logger.info(f"[LIWM] 模块初始化完成: {enabled}/{total} 模块启用")

        # 如果 RSSM 和 EFE 同时启用，将 RSSM 的 latent state 模板传递给 EFE
        self._sync_module_dependencies()

        return init_status

    def _sync_module_dependencies(self) -> None:
        """同步模块间的依赖关系 (如 RSSM latent dim 与 EFE state dim 的对齐)"""
        # 如果 EFE 配置的 state_dim 与 RSSM latent 维度不匹配，记录警告
        if self.rssm is not None and self.efe_evaluator is not None:
            rssm_state_dim = self.rssm.state_dim  # hidden_dim + stochastic_dim = 288
            efe_state_dim = self.efe_evaluator.state_dim
            if rssm_state_dim != efe_state_dim:
                logger.info(
                    f"[LIWM] RSSM state_dim ({rssm_state_dim}) "
                    f"与 EFE state_dim ({efe_state_dim}) 不匹配。"
                    f"EFE 的 encode_state() 会自动适应。",
                )

        # 诊断：打印所有子模块实际状态
        _enabled_str = ", ".join(
            f"{name}={'✅' if obj else '❌'}"
            for name, obj in [
                ("RSSM", self.rssm),
                ("DataPipeline", self.data_pipeline),
                ("EFE", self.efe_evaluator),
                ("CausalDiscovery", self.causal_discovery),
                ("EWC", self.ewc_memory),
                ("GWS", self.gws_evaluator),
            ]
        )
        logger.info(f"[L-IWM] 🔍 子模块实际状态: {_enabled_str}")
        if not all(
            [
                self.rssm,
                self.data_pipeline,
                self.efe_evaluator,
                self.causal_discovery,
                self.ewc_memory,
                self.gws_evaluator,
            ],
        ):
            logger.warning("[L-IWM] ⚠️ 部分子模块为 None，功能性可能受限")

    # ==================== 训练编排 ====================

    def train_on_batch(
        self,
        symbol: str = "000001.SH",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        统一训练循环：对所有启用的模块执行一步训练。

        训练顺序:
        1. 数据管道: 获取市场数据并计算特征
        2. RSSM 世界模型: 从数据学习 latent 动态 (如启用)
        3. EFE 评估器: 从 RSSM latent + 实际收益学习价值网络 (如启用)
        4. 因果发现: 增量更新因果图 (如启用)
        5. EWC 记忆: 检测任务边界并巩固 (如启用)
        6. GWS 评估器: 从反馈学习显著性 (如启用)

        Args:
            symbol: 股票代码 (默认 "000001.SH" 上证指数)
            context: 可选的上下文信息 (如当前动作、收益等)

        Returns:
            Dict[str, Any]: 各模块的训练结果
        """
        context = context or {}
        results: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "train_step": self.train_step,
            "modules": {},
        }

        # ===== 1. 数据管道 — 获取市场特征 =====
        data_result = self._run_data_pipeline(symbol)
        results["modules"]["data_pipeline"] = data_result
        features = data_result.get("features", np.zeros(self.input_dim))
        data_result.get("regime", {})

        # ===== 2. RSSM 世界模型 — 训练预测 =====
        rssm_result = self._run_rssm_training(features, context)
        results["modules"]["rssm"] = rssm_result

        # 获取 RSSM latent state (用于后续模块)
        latent_state = self._last_latent_state

        # ===== 3. EFE 评估器 — 价值网络学习 =====
        efe_result = self._run_efe_training(latent_state, context)
        results["modules"]["efe_evaluator"] = efe_result

        # ===== 4. 因果发现 — 增量结构学习 =====
        causal_result = self._run_causal_learning(features, context)
        results["modules"]["causal_discovery"] = causal_result

        # ===== 5. EWC 记忆 — 巩固与任务边界检测 =====
        ewc_result = self._run_ewc_consolidation(context)
        results["modules"]["ewc_memory"] = ewc_result

        # ===== 6. GWS 评估器 — 显著性学习 =====
        gws_result = self._run_gws_learning(context)
        results["modules"]["gws_evaluator"] = gws_result

        # ===== 更新全局状态 =====
        self.train_step += 1
        self._batch_train_count += 1
        self.last_train_time = results["timestamp"]

        # 训练步数同步到各模块
        if self.rssm is not None:
            self.rssm.train_step = self.train_step
        if self.efe_evaluator is not None:
            self.efe_evaluator.train_step = self.train_step
        if self.causal_discovery is not None:
            self.causal_discovery._learn_step = self.train_step
        if self.gws_evaluator is not None:
            self.gws_evaluator.train_step = self.train_step

        # 汇总统计
        total_loss = sum(m.get("loss", 0.0) for m in results["modules"].values() if isinstance(m, dict) and "loss" in m)
        results["total_loss"] = total_loss

        logger.debug(f"[LIWM] 训练步 {self.train_step}: loss={total_loss:.6f}, symbol={symbol}")

        return results

    def _run_data_pipeline(self, symbol: str) -> dict[str, Any]:
        """执行数据管道的获取和特征计算"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.data_pipeline is None:
            return result

        try:
            # 获取市场数据
            market_data = self.data_pipeline.fetch_market_data(symbol)

            # 计算技术特征
            features = self.data_pipeline.compute_technical_features(market_data)
            if len(features) > 0:
                self._last_market_features = features[-1]  # 最新时间步特征
            else:
                self._last_market_features = np.zeros(self.input_dim)

            # 市场体制识别
            regime = self.data_pipeline.get_market_regime(market_data)

            # 准备训练数据 (用于 RSSM) — 复用已计算的特征，避免重复 fetch
            obs, next_obs = self.data_pipeline.prepare_training_batch(
                symbol, precomputed_features=features,
            )

            result = {
                "status": "success",
                "has_data": len(features) > 0,
                "feature_dim": features.shape[1] if len(features.shape) > 1 else 0,
                "n_samples": features.shape[0] if len(features.shape) > 0 else 0,
                "regime": regime.get("regime", "unknown"),
                "regime_confidence": regime.get("confidence", 0.0),
                "features": features,
                "observations": obs,
                "next_observations": next_obs,
                "loss": 0.0,
            }
        except Exception as e:
            self._module_errors["data_pipeline"] += 1
            logger.error(f"[LIWM] 数据管道错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _run_rssm_training(
        self,
        features: np.ndarray,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 RSSM 世界模型的训练"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.rssm is None:
            return result

        try:
            # 从 context 提取动作和收益
            action_embed = context.get("action_embed")
            reward = context.get("reward", 0.0)
            done = context.get("done", False)

            if action_embed is not None and len(features) > 0:
                # 存储单步经验
                self.rssm.store_experience(
                    observation=features,
                    action=np.array(action_embed, dtype=np.float64),
                    reward=reward,
                    next_observation=features,  # 简化: 使用当前特征作为下一观测
                    done=done,
                )

            # 从回放缓冲区训练
            losses = self.rssm.train_on_replay(
                batch_size=self.config.rssm_batch_size,
                seq_len=8,
            )

            # 获取隐状态
            self._last_latent_state = self.rssm.get_latent_state()

            result = {
                "status": "success",
                "loss": float(losses.get("total_loss", 0.0)),
                "recon_loss": float(losses.get("recon_loss", 0.0)),
                "kl_loss": float(losses.get("kl_loss", 0.0)),
                "buffer_size": len(self.rssm.replay_buffer),
                "skipped": losses.get("skipped", False),
                "latent_ready": self._last_latent_state.get("h") is not None,
            }
        except Exception as e:
            self._module_errors["rssm"] += 1
            logger.error(f"[LIWM] RSSM 训练错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _run_efe_training(
        self,
        latent_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 EFE 评估器的在线学习"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.efe_evaluator is None:
            return result

        try:
            # 从 context 获取动作和收益信息
            action = context.get("action")
            reward = context.get("reward", 0.0)
            next_latent = context.get("next_latent", latent_state)
            done = context.get("done", False)

            if action is not None:
                # 构建状态字典 (兼容 EFE 评估器的 encode_state)
                state_dict = {
                    "h": latent_state.get("h", np.zeros(self.config.rssm_latent_dim)),
                    "z": latent_state.get("z", np.zeros(self.config.rssm_stochastic_dim)),
                    "reward_pred": latent_state.get("reward_pred", 0.0),
                }
                next_state_dict = {
                    "h": next_latent.get("h", latent_state.get("h")),
                    "z": next_latent.get("z", latent_state.get("z")),
                }

                # 在线 TD 更新
                update_result = self.efe_evaluator.update(
                    state=state_dict,
                    action=action,
                    reward=reward,
                    next_state=next_state_dict,
                    done=done,
                )

                # 更新探索系数
                self.efe_evaluator.update_exploration_alpha(update_result.get("td_error", 0.0))

                # 从经验缓冲批量训练
                batch_result = self.efe_evaluator.train_on_experience(batch_size=32)

                # 缓存最新 EFE 分解 (用于 HPCLoopManager 查询)
                candidate_actions = LearnableEFEEvaluator.ACTIONS
                efe_details = {}
                for act in candidate_actions:
                    efe_details[act] = self.efe_evaluator.evaluate_action(act, state_dict)
                self._last_efe_decomposition = {
                    "details": efe_details,
                    "td_error": update_result.get("td_error", 0.0),
                }

                result = {
                    "status": "success",
                    "loss": float(abs(update_result.get("td_error", 0.0))),
                    "td_error": float(update_result.get("td_error", 0.0)),
                    "current_epistemic": float(update_result.get("current_epistemic", 0.0)),
                    "current_pragmatic": float(update_result.get("current_pragmatic", 0.0)),
                    "exploration_alpha": float(np.exp(self.efe_evaluator.log_exploration_alpha)),
                    "batch_td": float(batch_result.get("batch_td", 0.0)),
                    "buffer_size": len(self.efe_evaluator._experience_buffer),
                }
            else:
                result = {
                    "status": "no_action",
                    "loss": 0.0,
                    "message": "context 中未提供 action, 跳过 EFE 更新",
                }
        except Exception as e:
            self._module_errors["efe_evaluator"] += 1
            logger.error(f"[LIWM] EFE 训练错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _run_causal_learning(
        self,
        features: np.ndarray,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行因果发现的增量结构学习"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.causal_discovery is None:
            return result

        try:
            # 将特征数据添加到因果发现器
            if len(features) > 0:
                # 将一维特征转为矩阵格式
                data_matrix = features.reshape(1, -1) if features.ndim == 1 else features

                # 增量更新
                w_updated = self.causal_discovery.incremental_update(data_matrix, warm_start=True)

                # 缓存因果图摘要
                self._last_causal_summary = self.causal_discovery.get_causal_graph_summary()

                result = {
                    "status": "success",
                    "loss": float(self.causal_discovery._h_function(w_updated)),
                    "num_edges": self._last_causal_summary.get("num_edges", 0),
                    "is_dag": self._last_causal_summary.get("is_dag", False),
                    "h_value": self._last_causal_summary.get("h_value", 0.0),
                    "n_samples": self.causal_discovery._n_samples,
                }
            else:
                result = {"status": "no_data", "loss": 0.0}
        except Exception as e:
            self._module_errors["causal_discovery"] += 1
            logger.error(f"[LIWM] 因果发现错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _run_ewc_consolidation(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 EWC 记忆巩固"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.ewc_memory is None:
            return result

        try:
            # 从 context 或 RSSM 提取模型参数
            model_params = self._collect_model_params()
            episode_data = context.get("episode_data", {})
            task_boundary = context.get("task_boundary")

            if model_params:
                # 确保参数模板已设置
                self.ewc_memory.set_param_template(model_params)

                # 执行巩固钩子
                hook_result = self.ewc_memory.consolidation_hook(
                    episode_data=episode_data,
                    model_params=model_params,
                    task_boundary_detected=task_boundary,
                )

                # 计算 EWC 损失 (用于日志)
                ewc_loss = self.ewc_memory.compute_ewc_loss(model_params)

                result = {
                    "status": "success",
                    "loss": float(ewc_loss),
                    "task_registered": hook_result.get("task_registered", False),
                    "task_id": hook_result.get("task_id"),
                    "num_tasks": len(self.ewc_memory._task_ids),
                    "protection_ratio": self.ewc_memory._protection_ratio,
                }
            else:
                result = {"status": "no_params", "loss": 0.0}
        except Exception as e:
            self._module_errors["ewc_memory"] += 1
            logger.error(f"[LIWM] EWC 巩固错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _run_gws_learning(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 GWS 显著性评估器的在线学习"""
        result: dict[str, Any] = {"status": "skipped", "loss": 0.0}

        if self.gws_evaluator is None:
            return result

        try:
            # 从 context 提取反馈数据
            content = context.get("content")
            outcome_reward = context.get("outcome_reward")

            if content is not None and outcome_reward is not None:
                # 评估内容
                components = self.gws_evaluator.evaluate_content(
                    content=content,
                    confidence=context.get("confidence", 0.5),
                    current_belief=context.get("belief"),
                )

                # 从反馈更新
                update_result = self.gws_evaluator.update_from_feedback(
                    content=content,
                    components=components,
                    outcome_reward=outcome_reward,
                )

                # 批量训练
                self.gws_evaluator.train_on_feedback_buffer(batch_size=32)

                result = {
                    "status": "success",
                    "loss": float(abs(outcome_reward) * 0.1),  # 近似损失
                    "outcome_reward": outcome_reward,
                    "saliency_weights": update_result.get("weights", []),
                    "feedback_buffer": len(self.gws_evaluator._feedback_buffer),
                }
            else:
                result = {"status": "no_feedback", "loss": 0.0}
        except Exception as e:
            self._module_errors["gws_evaluator"] += 1
            logger.error(f"[LIWM] GWS 学习错误: {e}")
            result = {"status": "error", "error": str(e), "loss": 0.0}

        return result

    def _collect_model_params(self) -> dict[str, np.ndarray] | None:
        """
        收集当前所有可学习模块的参数 (用于 EWC 注册)。

        优先使用 RSSM 的参数 (因为 EWC 主要保护世界模型的知识)，
        如果 RSSM 未启用，尝试收集其他模块的参数。

        Returns:
            Optional[Dict[str, np.ndarray]]: 参数名称 → 参数的字典
        """
        if self.rssm is not None:
            params = {}
            for attr_name in dir(self.rssm):
                if attr_name.startswith(("W_", "b_", "U_")):
                    param = getattr(self.rssm, attr_name)
                    if isinstance(param, np.ndarray):
                        params[attr_name] = param
            if params:
                return params

        # 后备: 使用 EFE 评估器的参数
        if self.efe_evaluator is not None:
            params = {}
            for attr_name in [
                "W_epi_1",
                "b_epi_1",
                "W_epi_2",
                "b_epi_2",
                "W_prag_1",
                "b_prag_1",
                "W_prag_2",
                "b_prag_2",
            ]:
                param = getattr(self.efe_evaluator, attr_name, None)
                if param is not None and isinstance(param, np.ndarray):
                    params[attr_name] = param
            if params:
                return params

        return None

    # ==================== HPC-Loop 集成 API ====================

    def get_enhanced_prediction(
        self,
        market_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        生成增强的市场预测 (替代 MarketGenerativeModel.generate_prediction)。

        使用 RSSM 世界模型 (如果启用) 替代原始的硬编码 ±0.5% 预测。
        如果 RSSM 未启用，返回空字典，由调用者回退到原始实现。

        Args:
            market_info: 市场信息字典 (由 _extract_market_info 提取)

        Returns:
            Dict[str, Any]: 增强预测 (包含 predictions, latent_state, latent_embedding)
                          空字典表示 RSSM 不可用
        """
        if self.rssm is None:
            logger.info("[L-IWM] RSSM 未就绪，返回空预测结构")
            return {"rssm_available": False, "prediction": None, "reason": "rssm_not_ready"}

        try:
            # 使用 RSSM 生成预测
            num_steps = self.config.rssm_imagination_horizon
            predictions = self.rssm.predict(
                state=self._last_latent_state,
                num_steps=num_steps,
            )

            latent_state = self.rssm.get_latent_state()

            # 提取隐层嵌入 (供 GWS/EFE 模块使用)
            h = latent_state.get("h")
            z = latent_state.get("z")
            latent_embedding = np.concatenate([h.flatten(), z.flatten()]) if h is not None and z is not None else None

            # 构造响应
            enhanced = {
                "predictions": [p.to_dict() if hasattr(p, "to_dict") else str(p) for p in predictions],
                "latent_state": {
                    "h": h.tolist() if h is not None else None,
                    "z": z.tolist() if z is not None else None,
                    "train_step": latent_state.get("train_step", 0),
                },
                "latent_embedding": latent_embedding.tolist() if latent_embedding is not None else None,
                "num_steps": num_steps,
                "source": "rssm_world_model",
            }

            # 更新缓存
            self._last_latent_state = latent_state

            return enhanced

        except Exception as e:
            logger.error(f"[LIWM] RSSM 预测错误: {e}")
            self._module_errors["rssm"] += 1
            return {"error": str(e), "source": "rssm_world_model"}

    def get_enhanced_market_info(
        self,
        state: dict[str, Any],
        symbol: str = "000001.SH",
    ) -> dict[str, Any]:
        """
        提取增强的市场信息 (替代 _extract_market_info 的文本长度代理)。

        使用 RealDataPipeline 计算真实技术指标，替代原始的文本长度代理。
        如果数据管道未启用，返回空字典。

        Args:
            state: LangGraph state 字典
            symbol: 股票代码

        Returns:
            Dict[str, Any]: 增强市场信息 (包含 features, regime 等)
        """
        if self.data_pipeline is None:
            logger.info("[L-IWM] DataPipeline 未就绪，返回空市场信息结构")
            return {"data_pipeline_available": False, "has_real_data": False, "reason": "data_pipeline_not_ready"}

        try:
            # 获取市场数据
            market_data = self.data_pipeline.fetch_market_data(symbol)

            # 计算技术特征
            features = self.data_pipeline.compute_technical_features(market_data)
            if len(features) > 0:
                latest_features = features[-1]
                self._last_market_features = latest_features
            else:
                latest_features = self._last_market_features

            # 市场体制识别
            regime = self.data_pipeline.get_market_regime(market_data)

            # 构造与原始 _extract_market_info 兼容的返回值
            enhanced = {
                "features": latest_features.tolist() if isinstance(latest_features, np.ndarray) else latest_features,
                "regime": regime.get("regime", "unknown"),
                "regime_confidence": regime.get("confidence", 0.0),
                "price_trend": regime.get("trend", "neutral"),
                "volatility_level": regime.get("volatility", "medium"),
                "has_real_data": len(features) > 0,
                "source": "real_data_pipeline",
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
            }

            return enhanced

        except Exception as e:
            logger.error(f"[LIWM] 市场信息提取错误: {e}")
            return {"error": str(e), "source": "real_data_pipeline"}

    def get_enhanced_efe(
        self,
        latent_state: dict[str, Any],
        candidate_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        计算增强的 EFE 分解 (替代 ActiveInferenceEngine 的手工权重)。

        使用 LearnableEFEEvaluator 替代原始的 hardcoded epistemic/pragmatic 值。
        如果 EFE 评估器未启用，返回空字典。

        Args:
            latent_state: RSSM 隐状态 (或 MarketLatentState)
            candidate_actions: 候选动作列表 (默认使用标准 5 动作)

        Returns:
            Dict[str, Any]: EFE 分解结果 (包含每个动作的 epistemic/pragmatic/efe)
        """
        if self.efe_evaluator is None:
            logger.info("[L-IWM] EFE 评估器未就绪，返回空 EFE 结构")
            return {"efe_available": False, "action_results": None, "reason": "efe_not_ready"}

        try:
            actions = candidate_actions or LearnableEFEEvaluator.ACTIONS
            state_dict = {
                "h": latent_state.get("h", np.zeros(self.config.rssm_latent_dim)),
                "z": latent_state.get("z", np.zeros(self.config.rssm_stochastic_dim)),
            }

            action_results = {}
            for action in actions:
                efe_dict = self.efe_evaluator.evaluate_action(action, state_dict)
                action_results[action] = efe_dict

            # 选择最优动作
            best_action, best_info = self.efe_evaluator.select_action(actions, state_dict)

            enhanced = {
                "action_results": action_results,
                "best_action": best_action,
                "best_efe": best_info.get("expected_free_energy", 0.0),
                "epistemic_value": best_info.get("epistemic_value", 0.0),
                "pragmatic_value": best_info.get("pragmatic_value", 0.0),
                "exploration_bonus": best_info.get("exploration_bonus", 0.0),
                "exploration_alpha": float(np.exp(self.efe_evaluator.log_exploration_alpha)),
                "source": "learnable_efe",
            }

            # 缓存
            self._last_efe_decomposition = enhanced

            return enhanced

        except Exception as e:
            logger.error(f"[LIWM] EFE 计算错误: {e}")
            return {"error": str(e), "source": "learnable_efe"}

    def get_enhanced_causal(
        self,
        action_node: str = "trading_action",
        target_node: str = "price_movement",
    ) -> dict[str, Any]:
        """
        计算增强的因果效应 (替代 CausalCounterfactualEngine 的手工图)。

        使用 DifferentiableCausalDiscovery 学习到的因果权重。
        如果因果发现未启用，返回空字典。

        Args:
            action_node: 干预节点名称
            target_node: 目标节点名称

        Returns:
            Dict[str, Any]: 因果效应分析结果
        """
        if self.causal_discovery is None:
            logger.info("[L-IWM] CausalDiscovery 未就绪，返回空因果结构")
            return {"causal_available": False, "intervention": None, "reason": "causal_not_ready"}

        try:
            # 干预效应
            intervention = self.causal_discovery.compute_intervention_effect(action_node, target_node)

            # 反事实查询
            counterfactual = self.causal_discovery.counterfactual_query(action_node, target_node, evidence_val=1.0)

            # 因果图摘要
            summary = self.causal_discovery.get_causal_graph_summary()

            enhanced = {
                "intervention": {
                    "direct_effect": float(intervention.direct_effect),
                    "total_effect": float(intervention.total_effect),
                    "confidence": float(intervention.confidence),
                    "path_contributions": intervention.path_contributions,
                },
                "counterfactual": counterfactual,
                "causal_graph": {
                    "num_nodes": summary["num_nodes"],
                    "num_edges": summary["num_edges"],
                    "is_dag": summary["is_dag"],
                    "h_value": summary["h_value"],
                    "n_samples": summary["n_samples"],
                },
                "source": "differentiable_causal",
            }

            self._last_causal_summary = summary

            return enhanced

        except Exception as e:
            logger.error(f"[LIWM] 因果分析错误: {e}")
            return {"error": str(e), "source": "differentiable_causal"}

    def get_enhanced_broadcast(
        self,
        contents: list[tuple[str, str, float]],  # [(content_id, text, confidence), ...]
        belief: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        计算增强的广播选择 (替代 GlobalWorkspace 的关键词启发式)。

        使用 LearnableSaliencyEvaluator 替代原始的 _estimate_novelty/_impact/_urgency。
        如果 GWS 评估器未启用，返回空字典。

        Args:
            contents: [(content_id, text, confidence), ...]
            belief: 当前信念状态

        Returns:
            Dict[str, Any]: 显著性评估和 top-k 选择结果
        """
        if self.gws_evaluator is None:
            logger.info("[L-IWM] GWS 评估器未就绪，返回空广播结构")
            return {"gws_available": False, "details": None, "reason": "gws_not_ready"}

        try:
            scored_contents = []
            for content_id, text, confidence in contents:
                # 评估各显著性分量
                components = self.gws_evaluator.evaluate_content(
                    content=text,
                    confidence=confidence,
                    current_belief=belief,
                )

                # 计算总显著性
                saliency = self.gws_evaluator.compute_saliency(components)

                scored_contents.append((content_id, text, confidence, components, saliency))

            # top-k 选择
            saliency_pairs = [(cid, s) for cid, _, _, _, s in scored_contents]
            selected_ids = self.gws_evaluator.select_top_k(saliency_pairs)

            # 构造详细结果
            details = []
            for content_id, text, confidence, components, saliency in scored_contents:
                details.append(
                    {
                        "content_id": content_id,
                        "text_preview": text[:100] + "..." if len(text) > 100 else text,
                        "novelty": components.get("novelty", 0.0),
                        "impact": components.get("impact", 0.0),
                        "urgency": components.get("urgency", 0.0),
                        "confidence": confidence,
                        "saliency": float(saliency),
                        "selected": content_id in selected_ids,
                    },
                )

            # 按显著性排序
            details.sort(key=lambda d: d["saliency"], reverse=True)

            enhanced = {
                "details": details,
                "selected_ids": selected_ids,
                "num_selected": len(selected_ids),
                "saliency_weights": self.gws_evaluator._saliency_weights.tolist(),
                "vocab_size": self.gws_evaluator._vocab_size,
                "source": "learnable_gws",
            }

            return enhanced

        except Exception as e:
            logger.error(f"[LIWM] GWS 广播错误: {e}")
            return {"error": str(e), "source": "learnable_gws"}

    def get_ewc_regularization(
        self,
        current_params: dict[str, np.ndarray] | None = None,
    ) -> float:
        """
        获取 EWC 正则化损失 (用于 HPCLoopManager 训练时调用)。

        在 HPC-Loop 的优化步骤中，将 EWC 损失加到总损失上，
        防止学习新策略时灾难性遗忘。

        Args:
            current_params: 当前模型参数 (None 则自动收集)

        Returns:
            float: EWC 损失值 (0.0 表示 EWC 未启用或无已注册任务)
        """
        if self.ewc_memory is None:
            return 0.0

        if current_params is None:
            current_params = self._collect_model_params()

        if current_params is None:
            return 0.0

        return self.ewc_memory.compute_consolidation_loss(current_params)

    def get_enhanced_nodes(self) -> dict[str, Callable]:
        """
        获取增强的 LangGraph 节点函数映射。

        返回的节点函数与 HPCLoopManager.get_enhanced_nodes() 格式兼容。
        每个节点函数接受 state: Dict[str, Any] 并返回 Dict[str, Any]。

        Returns:
            Dict[str, Callable]: 节点名称 → 节点函数
        """
        nodes: dict[str, Callable] = {}

        if self.rssm is not None:

            def l_iwm_predict_node(state: dict[str, Any]) -> dict[str, Any]:
                """L-IWM 增强预测节点"""
                market_info = _extract_market_info_wrapper(state)
                prediction = self.get_enhanced_prediction(market_info)
                state["l_iwm"] = state.get("l_iwm", {})
                state["l_iwm"]["prediction"] = prediction
                return state

            nodes["l_iwm_predict"] = l_iwm_predict_node

        if self.efe_evaluator is not None:

            def l_iwm_efe_node(state: dict[str, Any]) -> dict[str, Any]:
                """L-IWM 增强 EFE 节点"""
                latent = state.get("l_iwm", {}).get("prediction", {}).get("latent_state", {})
                if not latent:
                    latent = {"h": None, "z": None}
                efe_result = self.get_enhanced_efe(latent)
                state["l_iwm"] = state.get("l_iwm", {})
                state["l_iwm"]["efe"] = efe_result
                return state

            nodes["l_iwm_efe"] = l_iwm_efe_node

        if self.causal_discovery is not None:

            def l_iwm_causal_node(state: dict[str, Any]) -> dict[str, Any]:
                """L-IWM 增强因果节点"""
                causal_result = self.get_enhanced_causal()
                state["l_iwm"] = state.get("l_iwm", {})
                state["l_iwm"]["causal"] = causal_result
                return state

            nodes["l_iwm_causal"] = l_iwm_causal_node

        if self.gws_evaluator is not None:

            def l_iwm_gws_node(state: dict[str, Any]) -> dict[str, Any]:
                """L-IWM 增强 GWS 广播节点"""
                # 从 state 提取 agent 输出
                agent_outputs = _extract_agent_outputs_wrapper(state)
                if agent_outputs:
                    contents = [
                        (ao.get("id", f"agent_{i}"), ao.get("content", ""), ao.get("confidence", 0.5))
                        for i, ao in enumerate(agent_outputs)
                    ]
                    broadcast_result = self.get_enhanced_broadcast(
                        contents,
                        belief=state.get("belief"),
                    )
                    state["l_iwm"] = state.get("l_iwm", {})
                    state["l_iwm"]["broadcast"] = broadcast_result
                return state

            nodes["l_iwm_gws"] = l_iwm_gws_node

        return nodes

    # ==================== 状态管理 ====================

    def get_state_dict(self) -> dict[str, Any]:
        """
        获取所有模块的完整状态快照。

        Returns:
            Dict[str, Any]: 管理器状态 + 所有模块参数
        """
        state: dict[str, Any] = {
            "manager": {
                "train_step": self.train_step,
                "batch_train_count": self._batch_train_count,
                "episode_count": self._episode_count,
                "last_train_time": self.last_train_time,
                "module_errors": dict(self._module_errors),
                "config": self.config.to_dict(),
            },
            "modules": {},
        }

        if self.rssm is not None:
            state["modules"]["rssm"] = self._get_rssm_state()

        if self.data_pipeline is not None:
            state["modules"]["data_pipeline"] = {"status": "active"}

        if self.efe_evaluator is not None:
            state["modules"]["efe_evaluator"] = self.efe_evaluator.get_params_dict()

        if self.causal_discovery is not None:
            state["modules"]["causal_discovery"] = self.causal_discovery.get_params_dict()

        if self.ewc_memory is not None:
            state["modules"]["ewc_memory"] = self.ewc_memory.get_params_dict()

        if self.gws_evaluator is not None:
            state["modules"]["gws_evaluator"] = self.gws_evaluator.get_params_dict()

        return state

    def _get_rssm_state(self) -> dict[str, Any]:
        """提取 RSSM 参数状态"""
        if self.rssm is None:
            return {}
        params = {}
        for attr_name in dir(self.rssm):
            if attr_name.startswith(("W_", "b_", "U_")):
                param = getattr(self.rssm, attr_name)
                if isinstance(param, np.ndarray):
                    params[attr_name] = param.tolist()
        params["train_step"] = self.rssm.train_step
        return params

    def load_state_dict(self, state: dict[str, Any]) -> bool:
        """
        从状态快照恢复所有模块参数。

        Args:
            state: get_state_dict() 返回的状态字典

        Returns:
            bool: 是否完全恢复成功
        """
        if "manager" in state:
            mgr = state["manager"]
            self.train_step = mgr.get("train_step", 0)
            self._batch_train_count = mgr.get("batch_train_count", 0)
            self._episode_count = mgr.get("episode_count", 0)
            self.last_train_time = mgr.get("last_train_time")
            if "module_errors" in mgr:
                self._module_errors.update(mgr["module_errors"])

        modules = state.get("modules", {})
        success = True

        if "rssm" in modules and self.rssm is not None:
            try:
                rssm_params = modules["rssm"]
                for attr_name, value in rssm_params.items():
                    if attr_name == "train_step":
                        self.rssm.train_step = value
                    elif hasattr(self.rssm, attr_name):
                        setattr(self.rssm, attr_name, np.array(value))
                logger.info("[LIWM] ✅ RSSM 参数已恢复")
            except Exception as e:
                logger.error(f"[LIWM] ❌ RSSM 恢复失败: {e}")
                success = False

        if "efe_evaluator" in modules and self.efe_evaluator is not None:
            try:
                self.efe_evaluator.load_params_dict(modules["efe_evaluator"])
                logger.info("[LIWM] ✅ EFE 评估器参数已恢复")
            except Exception as e:
                logger.error(f"[LIWM] ❌ EFE 恢复失败: {e}")
                success = False

        if "causal_discovery" in modules and self.causal_discovery is not None:
            try:
                self.causal_discovery.load_params_dict(modules["causal_discovery"])
                logger.info("[LIWM] ✅ 因果发现参数已恢复")
            except Exception as e:
                logger.error(f"[LIWM] ❌ 因果发现恢复失败: {e}")
                success = False

        if "ewc_memory" in modules and self.ewc_memory is not None:
            try:
                self.ewc_memory.load_params_dict(modules["ewc_memory"])
                logger.info("[LIWM] ✅ EWC 记忆参数已恢复")
            except Exception as e:
                logger.error(f"[LIWM] ❌ EWC 恢复失败: {e}")
                success = False

        if "gws_evaluator" in modules and self.gws_evaluator is not None:
            try:
                self.gws_evaluator.load_params_dict(modules["gws_evaluator"])
                logger.info("[LIWM] ✅ GWS 评估器参数已恢复")
            except Exception as e:
                logger.error(f"[LIWM] ❌ GWS 恢复失败: {e}")
                success = False

        return success

    def save_all(self, directory: str) -> dict[str, bool]:
        """
        将所有模块参数保存到目录。

        每个模块保存为独立的 JSON 文件:
            - l_iwm_manager_state.json (管理器状态)
            - rssm_world_model.json
            - efe_evaluator.json
            - causal_discovery.json
            - ewc_memory.json
            - gws_evaluator.json

        Args:
            directory: 保存目录

        Returns:
            Dict[str, bool]: 文件名 → 保存成功标志
        """
        os.makedirs(directory, exist_ok=True)
        results: dict[str, bool] = {}

        # 管理器状态
        try:
            state = self.get_state_dict()
            path = os.path.join(directory, "l_iwm_manager_state.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            results["l_iwm_manager_state.json"] = True
        except Exception as e:
            logger.error(f"[LIWM] 保存管理器状态失败: {e}")
            results["l_iwm_manager_state.json"] = False

        # 各模块独立保存
        save_tasks = [
            ("rssm_world_model.json", self.rssm, "save"),
            ("efe_evaluator.json", self.efe_evaluator, "save"),
            ("causal_discovery.json", self.causal_discovery, "save"),
            ("ewc_memory.json", self.ewc_memory, "save"),
            ("gws_evaluator.json", self.gws_evaluator, "save"),
        ]

        for filename, module, method_name in save_tasks:
            if module is not None:
                try:
                    path = os.path.join(directory, filename)
                    getattr(module, method_name)(path)
                    results[filename] = True
                except Exception as e:
                    logger.error(f"[LIWM] 保存 {filename} 失败: {e}")
                    results[filename] = False
            else:
                results[filename] = False  # 模块未启用

        n_saved = sum(1 for v in results.values() if v)
        n_total = len(results)
        logger.info(f"[LIWM] 保存完成: {n_saved}/{n_total} 文件")

        return results

    def load_all(self, directory: str) -> dict[str, bool]:
        """
        从目录加载所有模块参数。

        Args:
            directory: 加载目录

        Returns:
            Dict[str, bool]: 文件名 → 加载成功标志
        """
        results: dict[str, bool] = {}

        # 管理器状态
        try:
            path = os.path.join(directory, "l_iwm_manager_state.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    state = json.load(f)
                self.load_state_dict(state)
                results["l_iwm_manager_state.json"] = True
            else:
                results["l_iwm_manager_state.json"] = False
                logger.warning(f"[LIWM] 管理器状态文件不存在: {path}")
        except Exception as e:
            logger.error(f"[LIWM] 加载管理器状态失败: {e}")
            results["l_iwm_manager_state.json"] = False

        # 各模块独立加载
        load_tasks = [
            ("rssm_world_model.json", self.rssm, "load"),
            ("efe_evaluator.json", self.efe_evaluator, "load"),
            ("causal_discovery.json", self.causal_discovery, "load"),
            ("ewc_memory.json", self.ewc_memory, "load"),
            ("gws_evaluator.json", self.gws_evaluator, "load"),
        ]

        for filename, module, method_name in load_tasks:
            if module is not None:
                try:
                    path = os.path.join(directory, filename)
                    if os.path.exists(path):
                        getattr(module, method_name)(path)
                        results[filename] = True
                    else:
                        results[filename] = False
                        logger.warning(f"[LIWM] 模块文件不存在: {path}")
                except Exception as e:
                    logger.error(f"[LIWM] 加载 {filename} 失败: {e}")
                    results[filename] = False
            else:
                results[filename] = False

        n_loaded = sum(1 for v in results.values() if v)
        n_total = len(results)
        logger.info(f"[LIWM] 加载完成: {n_loaded}/{n_total} 文件")

        return results

    # ==================== 统计信息 ====================

    def get_statistics(self) -> dict[str, Any]:
        """
        获取所有模块的统计信息。

        Returns:
            Dict[str, Any]: 层次化的统计信息字典
        """
        stats: dict[str, Any] = {
            "manager": {
                "train_step": self.train_step,
                "batch_train_count": self._batch_train_count,
                "episode_count": self._episode_count,
                "last_train_time": self.last_train_time,
                "module_errors": dict(self._module_errors),
                "total_errors": sum(self._module_errors.values()),
                "enabled_modules": {
                    "rssm": self.config.rssm_enabled and self.rssm is not None,
                    "data_pipeline": self.config.real_data_enabled and self.data_pipeline is not None,
                    "efe_evaluator": self.config.learnable_efe_enabled and self.efe_evaluator is not None,
                    "causal_discovery": self.config.diff_causal_enabled and self.causal_discovery is not None,
                    "ewc_memory": self.config.ewc_memory_enabled and self.ewc_memory is not None,
                    "gws_evaluator": self.config.learnable_gws_enabled and self.gws_evaluator is not None,
                },
            },
            "modules": {},
        }

        # 各模块统计
        if self.rssm is not None:
            stats["modules"]["rssm"] = {
                "train_step": self.rssm.train_step,
                "buffer_size": len(self.rssm.replay_buffer),
                "latent_dim": self.rssm.latent_dim,
                "hidden_dim": self.rssm.hidden_dim,
                "stochastic_dim": self.rssm.stochastic_dim,
            }

        if self.data_pipeline is not None:
            stats["modules"]["data_pipeline"] = {
                "data_sources": self.config.real_data_sources,
                "lookback_days": self.config.real_data_lookback_days,
            }

        if self.efe_evaluator is not None:
            efe_stats = self.efe_evaluator.get_statistics()
            stats["modules"]["efe_evaluator"] = {
                "train_step": efe_stats.get("train_step", 0),
                "buffer_size": efe_stats.get("buffer_size", 0),
                "exploration_alpha": efe_stats.get("exploration_alpha", 0.0),
                "avg_epistemic": efe_stats.get("avg_epistemic", 0.0),
                "avg_pragmatic": efe_stats.get("avg_pragmatic", 0.0),
                "avg_td_error": efe_stats.get("avg_td_error", 0.0),
            }

        if self.causal_discovery is not None:
            causal_stats = self.causal_discovery.get_statistics()
            stats["modules"]["causal_discovery"] = {
                "num_nodes": causal_stats.get("num_nodes", 0),
                "num_edges": causal_stats.get("num_edges", 0),
                "is_dag": causal_stats.get("is_dag", False),
                "h_value": causal_stats.get("h_value", 0.0),
                "n_samples": causal_stats.get("n_samples", 0),
                "edge_density": causal_stats.get("edge_density", 0.0),
            }

        if self.ewc_memory is not None:
            ewc_stats = self.ewc_memory.get_statistics()
            stats["modules"]["ewc_memory"] = {
                "num_protected_tasks": ewc_stats.get("num_protected_tasks", 0),
                "protection_ratio": ewc_stats.get("protection_ratio", 0.0),
                "consolidation_step": ewc_stats.get("consolidation_step", 0),
                "consolidated_episodes": ewc_stats.get("consolidated_episodes", 0),
                "ewc_loss_avg": ewc_stats.get("ewc_loss_avg", 0.0),
            }

        if self.gws_evaluator is not None:
            gws_stats = self.gws_evaluator.get_statistics()
            stats["modules"]["gws_evaluator"] = {
                "train_step": gws_stats.get("train_step", 0),
                "vocab_size": gws_stats.get("vocab_size", 0),
                "feedback_buffer_size": gws_stats.get("feedback_buffer_size", 0),
                "saliency_weights": gws_stats.get("saliency_weights", []),
                "avg_saliency": gws_stats.get("avg_saliency", 0.0),
                "avg_novelty": gws_stats.get("avg_novelty", 0.0),
                "avg_impact": gws_stats.get("avg_impact", 0.0),
                "avg_urgency": gws_stats.get("avg_urgency", 0.0),
            }

        return stats

    def get_module_health(self) -> dict[str, str]:
        """
        获取各模块健康状态。

        Returns:
            Dict[str, str]: 模块名 → "ok", "disabled", 或 "error"
        """
        health: dict[str, str] = {}

        checks = [
            ("rssm", self.config.rssm_enabled, self.rssm),
            ("data_pipeline", self.config.real_data_enabled, self.data_pipeline),
            ("efe_evaluator", self.config.learnable_efe_enabled, self.efe_evaluator),
            ("causal_discovery", self.config.diff_causal_enabled, self.causal_discovery),
            ("ewc_memory", self.config.ewc_memory_enabled, self.ewc_memory),
            ("gws_evaluator", self.config.learnable_gws_enabled, self.gws_evaluator),
        ]

        for name, enabled, instance in checks:
            if not enabled:
                health[name] = "disabled"
            elif instance is None:
                health[name] = "error"
            elif self._module_errors.get(name, 0) > 10:
                health[name] = "degraded"
            else:
                health[name] = "ok"

        return health

    # ==================== 重置 ====================

    def reset(self) -> None:
        """重置所有模块的运行时状态 (保留可学习参数)"""
        if self.rssm is not None:
            self.rssm.replay_buffer.clear()
            self.rssm._last_h = None
            self.rssm._last_z = None

        if self.efe_evaluator is not None:
            self.efe_evaluator.reset()

        if self.causal_discovery is not None:
            self.causal_discovery.reset()

        if self.ewc_memory is not None:
            self.ewc_memory.reset()

        if self.gws_evaluator is not None:
            self.gws_evaluator.reset()

        self.train_step = 0
        self._episode_count = 0
        self._batch_train_count = 0
        self._module_errors = dict.fromkeys(self._module_errors, 0)
        self._last_latent_state = {}
        self._last_efe_decomposition = {}
        self._last_causal_summary = {}
        self.last_train_time = None

        logger.info("[LIWM] 所有模块已重置 (运行时状态)")

    def reset_all(self) -> None:
        """
        完全重置所有模块 (包括可学习参数回到初始状态)。
        谨慎使用 — 会丢失所有已学习的知识。
        """
        self.reset()
        # 重新初始化所有模块
        self.rssm = None
        self.data_pipeline = None
        self.efe_evaluator = None
        self.causal_discovery = None
        self.ewc_memory = None
        self.gws_evaluator = None
        self.init_modules()

        logger.warning("[LIWM] 所有模块已完全重置 (包括参数)")


# ==================== 辅助函数 ====================
# 以下函数提供与 hpc_integration.py 中 _extract_market_info / _extract_agent_outputs 的兼容包装


def _extract_market_info_wrapper(state: dict[str, Any]) -> dict[str, Any]:
    """
    从 LangGraph state 中提取市场信息 (兼容包装)。

    当 L-IWM 未启用时，使用与 hpc_integration.py 相同的提取逻辑，
    确保无缝回退。

    Args:
        state: LangGraph state 字典

    Returns:
        Dict[str, Any]: 市场信息
    """
    market_info = {}

    # 尝试从 state 中提取市场信息
    # 兼容原始格式
    for key in ["market_info", "market_data", "hpc_state"]:
        if key in state:
            candidate = state[key]
            if isinstance(candidate, dict):
                market_info.update(candidate)

    # 提取交易数据 (兼容不同字段名)
    price_keys = ["price", "close", "last_price", "current_price"]
    for k in price_keys:
        for source in [state, market_info]:
            if k in source:
                market_info["price"] = source[k]
                break
        if "price" in market_info:
            break

    volatility_keys = ["volatility", "vol", "uncertainty"]
    for k in volatility_keys:
        for source in [state, market_info]:
            if k in source:
                market_info["volatility"] = source[k]
                break
        if "volatility" in market_info:
            break

    # 默认值
    market_info.setdefault("price", 100.0)
    market_info.setdefault("volatility", 0.015)
    market_info.setdefault("regime", "unknown")

    return market_info


def _extract_agent_outputs_wrapper(state: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从 LangGraph state 中提取各 agent 的输出 (兼容包装)。

    Args:
        state: LangGraph state 字典

    Returns:
        List[Dict[str, Any]]: Agent 输出列表，每个包含 id, content, confidence
    """
    outputs = []

    # 尝试从 state 中提取 agent 输出
    if "agent_outputs" in state:
        candidate = state["agent_outputs"]
        if isinstance(candidate, list):
            outputs.extend(candidate)

    if "messages" in state:
        messages = state["messages"]
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    outputs.append(
                        {
                            "id": msg.get("id", f"msg_{len(outputs)}"),
                            "content": msg.get("content", str(msg)),
                            "confidence": msg.get("confidence", 0.5),
                        },
                    )

    # 如果没有找到，构造一个兜底
    if not outputs:
        # 提取 state 中所有字符串值作为内容
        for key, val in state.items():
            if isinstance(val, str) and len(val) > 20:
                outputs.append(
                    {
                        "id": key,
                        "content": val,
                        "confidence": 0.5,
                    },
                )

    return outputs
