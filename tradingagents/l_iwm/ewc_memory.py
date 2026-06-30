# TradingAgents/l_iwm/ewc_memory.py
"""
EWC 弹性权重巩固记忆系统 (Elastic Weight Consolidation Memory)
===============================================================

理论基础: Kirkpatrick et al. 2017 "Overcoming catastrophic forgetting in neural networks"
          (PNAS 2017)

增强当前 hpc_loop/complementary_memory.py 中的简单 EMA 统计巩固：
    当前: _consolidate_episode() 仅更新运行均值 (EMA)
    EWC:  Fisher 信息矩阵保护重要权重，防止灾难性遗忘

核心创新:
    1. Fisher 信息矩阵: 估计每个参数对过往任务的重要性
       F_ij = E[(∂L/∂θ_i) * (∂L/∂θ_j)]
    2. EWC 损失: L(θ) = L_new(θ) + λ/2 * Σ_i F_i * (θ_i - θ_i*)²
       其中 θ* 是旧任务的最优参数，λ 控制弹性强度
    3. 任务边界检测: 基于分布漂移 (KS 检验/MMD) 自动检测任务切换
    4. 选择性巩固: 只保护 Fisher 信息高于阈值的参数
    5. 内存预算管理: 限制 Fisher 对角矩阵存储大小

数学公式:
    L_EWC(θ) = L_B(θ) + Σ_j (λ/2) * F_j * (θ_j - θ*_A,j)²

    其中:
    - L_B(θ): 当前任务 B 的损失
    - θ*_A: 任务 A 学习后的最优参数
    - F_j: 参数 θ_j 的 Fisher 信息 (对角线近似)
    - λ: EWC 弹性系数 (越大对旧任务保护越强)

兼容性:
    - 输入: 外部模型的参数 dict 或 flat numpy array
    - 支持与 ComplementaryLearningMemory 协同工作
    - 提供 consolidation_hook() 在记忆巩固时调用
"""

import json
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

# ==================== 工具函数 ====================


def _compute_fisher_diagonal(
    params: dict[str, np.ndarray],
    loss_gradient_fn: Callable[[dict[str, np.ndarray]], dict[str, np.ndarray]],
    n_samples: int = 50,
) -> dict[str, np.ndarray]:
    """
    计算 Fisher 信息矩阵的对角线近似

    F_i = E[(∂L/∂θ_i)²]

    Args:
        params: 模型参数字典 {name: ndarray}
        loss_gradient_fn: 函数，输入参数字典，输出梯度字典
        n_samples: 采样次数

    Returns:
        Dict[str, np.ndarray]: Fisher 对角线估计
    """
    fisher = {}
    squared_gradients = {name: np.zeros_like(param) for name, param in params.items()}

    for _ in range(n_samples):
        gradients = loss_gradient_fn(params)
        for name, grad in gradients.items():
            if name in squared_gradients:
                squared_gradients[name] += grad**2

    for name in params:
        fisher[name] = squared_gradients[name] / n_samples

    return fisher


def _flatten_params(params: dict[str, np.ndarray]) -> np.ndarray:
    """将参数字典展平为一维数组"""
    return np.concatenate([p.flatten() for p in params.values()])


def _unflatten_params(
    flat: np.ndarray,
    template: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """将一维数组还原为参数字典"""
    params = {}
    offset = 0
    for name, template_arr in template.items():
        size = template_arr.size
        params[name] = flat[offset : offset + size].reshape(template_arr.shape)
        offset += size
    return params


# ==================== 任务检测器 ====================


class TaskChangeDetector:
    """
    任务变化检测器

    基于数据分布漂移检测市场体制变化 (任务切换边界)。
    使用统计检验判断新数据是否来自与旧数据相同的分布。

    方法:
    - Kolmogorov-Smirnov 检验 (单变量)
    - 简单阈值: 均值/方差漂移
    """

    def __init__(
        self,
        method: str = "mean_shift",
        threshold_std: float = 2.0,
        window_size: int = 100,
    ):
        """
        Args:
            method: 检测方法 ("mean_shift", "ks_test")
            threshold_std: 均值漂移阈值 (标准差倍数)
            window_size: 滑动窗口大小
        """
        self.method = method
        self.threshold_std = threshold_std
        self.window_size = window_size

        self._reference_mean: np.ndarray | None = None
        self._reference_std: np.ndarray | None = None
        self._observations: list[np.ndarray] = []
        self._task_id: int = 0
        self._change_points: list[int] = []

    def update(self, data_point: np.ndarray) -> bool:
        """
        更新检测器，检测是否发生了任务变化

        Args:
            data_point: 新数据点

        Returns:
            bool: 是否检测到任务变化
        """
        self._observations.append(data_point.flatten())

        if len(self._observations) > self.window_size * 2:
            self._observations.pop(0)

        n = len(self._observations)
        if n < self.window_size:
            return False

        # 计算参考分布 (前 window_size 个样本)
        if self._reference_mean is None:
            ref_data = np.stack(self._observations[: self.window_size])
            self._reference_mean = np.mean(ref_data, axis=0)
            self._reference_std = np.std(ref_data, axis=0) + 1e-8
            return False

        # 当前窗口 (最近 window_size 个样本)
        current_data = np.stack(self._observations[-self.window_size :])
        current_mean = np.mean(current_data, axis=0)

        # 计算标准化漂移量
        normalized_shift = np.abs(current_mean - self._reference_mean) / self._reference_std
        max_shift = float(np.max(normalized_shift))

        if max_shift > self.threshold_std:
            # 检测到任务变化
            self._task_id += 1
            self._change_points.append(len(self._observations))

            # 重置参考分布
            self._reference_mean = current_mean.copy()
            self._reference_std = np.std(current_data, axis=0) + 1e-8

            return True

        return False

    @property
    def current_task_id(self) -> int:
        """当前任务 ID"""
        return self._task_id

    @property
    def num_detected_changes(self) -> int:
        """检测到的变化次数"""
        return len(self._change_points)

    def reset(self):
        """重置检测器"""
        self._reference_mean = None
        self._reference_std = None
        self._observations.clear()
        self._task_id = 0
        self._change_points.clear()


# ==================== EWC 记忆系统 ====================


class EWCMemorySystem:
    """
    EWC 弹性权重巩固记忆系统

    增强 ComplementaryLearningMemory 的 consolidate() 方法，
    防止学习新交易策略时灾难性遗忘已有知识。

    使用流程:
        ewc = EWCMemorySystem(lambda_elasticity=100.0)

        # 任务 A: 学习趋势跟踪策略
        params_a = model.get_params()
        ewc.register_task(params_a, task_id=0, fisher=fisher_a)

        # 任务 B: 学习均值回归策略 (EWC 保护任务 A 的知识)
        params_b = model.get_params()  # 更新后
        ewc_loss = ewc.compute_ewc_loss(params_b, current_task_id=1)
        total_loss = task_b_loss + ewc_loss  # 联合训练

        # 在记忆巩固时调用
        ewc.consolidation_hook(episode_data)
    """

    def __init__(
        self,
        config: Any = None,
        lambda_elasticity: float = 100.0,
        consolidation_interval: int = 100,
        fisher_samples: int = 50,
        importance_threshold: float = 0.01,
        max_tasks: int = 20,
        memory_decay: float = 0.99,
    ):
        """
        初始化 EWC 记忆系统

        Args:
            config: LIWMConfig 实例 (可选)
            lambda_elasticity: EWC 弹性系数 λ (越大对旧权重保护越强)
            consolidation_interval: 记忆巩固间隔 (episode 数)
            fisher_samples: Fisher 信息矩阵估算采样数
            importance_threshold: Fisher 信息重要性阈值
            max_tasks: 最多保护的任务数 (FIFO)
            memory_decay: 旧任务记忆衰减因子
        """
        if config is not None:
            lambda_elasticity = getattr(config, "ewc_elasticity", lambda_elasticity)
            consolidation_interval = getattr(config, "ewc_consolidation_interval", consolidation_interval)
            fisher_samples = getattr(config, "ewc_fisher_samples", fisher_samples)
            importance_threshold = getattr(config, "ewc_importance_threshold", importance_threshold)

        self.lambda_elasticity = lambda_elasticity
        self.consolidation_interval = consolidation_interval
        self.fisher_samples = fisher_samples
        self.importance_threshold = importance_threshold
        self.max_tasks = max_tasks
        self.memory_decay = memory_decay

        # ========== EWC 状态 ==========
        # 存储每个注册任务的 Fisher 信息对角线和最优参数
        self._fisher_matrices: list[dict[str, np.ndarray]] = []
        """Fisher 信息矩阵列表 (每个任务一个)"""

        self._optimal_params: list[dict[str, np.ndarray]] = []
        """每个任务的最优参数"""

        self._task_ids: list[int] = []
        """任务 ID 列表"""

        self._task_importances: list[float] = []
        """每个任务的重要性权重 (用于加权 EWC 损失)"""

        # ========== 巩固状态 ==========
        self._consolidation_step: int = 0
        self._last_consolidation_episode: int = 0
        self._consolidated_episodes: int = 0

        # ========== 在线学习缓冲 ==========
        self._episode_buffer: deque = deque(maxlen=1000)
        """最近的 episode 数据缓冲"""

        self._parameter_snapshots: deque = deque(maxlen=50)
        """参数快照历史"""

        # ========== 任务检测 ==========
        self._task_detector = TaskChangeDetector()

        # ========== 统计 ==========
        self._ewc_loss_history: list[float] = []
        self._task_change_history: list[int] = []
        self._protection_ratio: float = 0.0
        """被保护的参数比例"""

        # ========== 参数存储模板 ==========
        self._param_template: dict[str, np.ndarray] | None = None
        """参数结构模板"""

    # ==================== 参数管理 ====================

    def set_param_template(self, params: dict[str, np.ndarray]) -> None:
        """
        设置参数结构模板 (从模型参数中学习)

        Args:
            params: 模型参数字典
        """
        self._param_template = {name: arr.copy() for name, arr in params.items()}

    def _validate_params(self, params: dict[str, np.ndarray]) -> bool:
        """验证参数是否与模板匹配"""
        if self._param_template is None:
            self.set_param_template(params)
            return True

        if set(params.keys()) != set(self._param_template.keys()):
            return False

        return all(params[name].shape == self._param_template[name].shape for name in params)

    # ==================== Fisher 信息矩阵管理 ====================

    def estimate_fisher(
        self,
        params: dict[str, np.ndarray],
        data_samples: list[Any],
        loss_gradient_fn: Callable[[dict[str, np.ndarray], Any], dict[str, np.ndarray]],
    ) -> dict[str, np.ndarray]:
        """
        估计 Fisher 信息矩阵 (对角线近似)

        F_i = (1/N) * Σ_n (∂L_n/∂θ_i)²

        其中 L_n 是第 n 个样本的损失。

        Args:
            params: 当前模型参数
            data_samples: 数据样本列表
            loss_gradient_fn: 函数 (params, sample) → 梯度字典

        Returns:
            Dict[str, np.ndarray]: Fisher 对角线
        """
        fisher = {name: np.zeros_like(param) for name, param in params.items()}

        n_samples = min(len(data_samples), self.fisher_samples)
        if n_samples == 0:
            # 无数据时使用均匀 Fisher
            for name, param in params.items():
                fisher[name] = np.ones_like(param) * 0.01
            return fisher

        # 采样
        indices = np.random.choice(len(data_samples), n_samples, replace=False)
        for idx in indices:
            sample = data_samples[idx]
            gradients = loss_gradient_fn(params, sample)
            for name, grad in gradients.items():
                if name in fisher:
                    fisher[name] += grad**2

        # 平均
        for name in fisher:
            fisher[name] /= n_samples

        return fisher

    def estimate_fisher_empirical(
        self,
        params: dict[str, np.ndarray],
        param_noise_std: float = 0.001,
        n_samples: int = 100,
    ) -> dict[str, np.ndarray]:
        """
        使用参数扰动法估计 Fisher 信息

        当没有梯度函数时，可以通过对参数加噪并观测损失变化来估计。
        这是一种近似方法。

        Args:
            params: 当前参数
            param_noise_std: 参数扰动标准差
            n_samples: 采样次数

        Returns:
            Dict[str, np.ndarray]: Fisher 对角线估计
        """
        fisher = {name: np.zeros_like(param) for name, param in params.items()}

        # 使用参数值本身的平方作为重要性的代理
        # 较大的参数往往更重要 (magnitude-based importance)
        for name, param in params.items():
            # Fisher ≈ (param / max_param)² 的归一化版本
            param_flat = param.flatten()
            max_abs = np.max(np.abs(param_flat))
            importance = (param_flat / max_abs) ** 2 if max_abs > 1e-08 else np.ones_like(param_flat) * 0.01

            # 添加随机噪声方差分量
            noise_var = param_noise_std**2
            importance = importance + noise_var

            fisher[name] = importance.reshape(param.shape)

        return fisher

    def register_task(
        self,
        params: dict[str, np.ndarray],
        task_id: int,
        fisher: dict[str, np.ndarray] | None = None,
        importance: float = 1.0,
    ) -> None:
        """
        注册一个已完成的任务 (保存 Fisher + 最优参数)

        在训练完一个任务/体制后调用。

        Args:
            params: 训练后的最优参数
            task_id: 任务标识符
            fisher: Fisher 信息矩阵 (None 时自动估计)
            importance: 任务重要性权重
        """
        if not self._validate_params(params):
            raise ValueError("参数结构与模板不匹配")

        # 保存参数副本
        param_copy = {name: arr.copy() for name, arr in params.items()}

        if fisher is None:
            fisher = self.estimate_fisher_empirical(params)

        fisher_copy = {name: arr.copy() for name, arr in fisher.items()}

        # 应用重要性阈值
        for name in fisher_copy:
            fisher_copy[name] = np.where(
                fisher_copy[name] >= self.importance_threshold,
                fisher_copy[name],
                0.0,
            )

        # 添加到任务列表
        self._fisher_matrices.append(fisher_copy)
        self._optimal_params.append(param_copy)
        self._task_ids.append(task_id)
        self._task_importances.append(importance)

        # FIFO 淘汰
        if len(self._fisher_matrices) > self.max_tasks:
            self._fisher_matrices.pop(0)
            self._optimal_params.pop(0)
            self._task_ids.pop(0)
            self._task_importances.pop(0)

        # 更新保护比例统计
        self._update_protection_ratio()

    # ==================== EWC 损失计算 ====================

    def compute_ewc_loss(
        self,
        current_params: dict[str, np.ndarray],
        current_task_id: int | None = None,
    ) -> float:
        """
        计算 EWC 正则化损失

        L_EWC = Σ_j (λ/2) * F_j * (θ_j - θ*_A,j)²

        Args:
            current_params: 当前模型参数 (训练中)
            current_task_id: 当前任务 ID (None 表示全部任务)

        Returns:
            float: EWC 损失值
        """
        if not self._fisher_matrices:
            return 0.0

        if not self._validate_params(current_params):
            return 0.0

        total_ewc_loss = 0.0
        total_weight = 0.0

        # 遍历所有已注册的旧任务
        for t_idx in range(len(self._fisher_matrices)):
            # 跳过当前任务
            if current_task_id is not None and self._task_ids[t_idx] == current_task_id:
                continue

            fisher_t = self._fisher_matrices[t_idx]
            opt_params_t = self._optimal_params[t_idx]
            importance_t = self._task_importances[t_idx]

            # 对每个参数计算 EWC 项
            task_loss = 0.0
            n_params = 0

            for name in current_params:
                if name not in fisher_t or name not in opt_params_t:
                    continue

                # (θ - θ*)²
                param_diff = current_params[name] - opt_params_t[name]
                squared_diff = param_diff**2

                # F * (θ - θ*)²
                weighted_diff = fisher_t[name] * squared_diff

                task_loss += float(np.sum(weighted_diff))
                n_params += param_diff.size

            if n_params > 0:
                avg_task_loss = task_loss / n_params
                total_ewc_loss += importance_t * avg_task_loss
                total_weight += importance_t

        if total_weight > 0:
            total_ewc_loss /= total_weight

        # 应用弹性系数
        ewc_loss = 0.5 * self.lambda_elasticity * total_ewc_loss

        # 记录统计
        self._ewc_loss_history.append(ewc_loss)

        return ewc_loss

    def compute_ewc_gradient(
        self,
        current_params: dict[str, np.ndarray],
        current_task_id: int | None = None,
    ) -> dict[str, np.ndarray]:
        """
        计算 EWC 损失对每个参数的梯度

        ∂L_EWC/∂θ_i = λ * Σ_j F_j,i * (θ_i - θ*_j,i)

        Args:
            current_params: 当前参数
            current_task_id: 当前任务 ID

        Returns:
            Dict[str, np.ndarray]: 每个参数的 EWC 梯度
        """
        ewc_grads = {name: np.zeros_like(param) for name, param in current_params.items()}

        if not self._fisher_matrices:
            return ewc_grads

        total_weight = sum(self._task_importances)

        for t_idx in range(len(self._fisher_matrices)):
            if current_task_id is not None and self._task_ids[t_idx] == current_task_id:
                continue

            fisher_t = self._fisher_matrices[t_idx]
            opt_params_t = self._optimal_params[t_idx]
            importance_t = self._task_importances[t_idx] / total_weight if total_weight > 0 else 0.0

            for name in current_params:
                if name in fisher_t and name in opt_params_t:
                    # ∂/∂θ: λ * F * (θ - θ*)
                    param_diff = current_params[name] - opt_params_t[name]
                    ewc_grads[name] += importance_t * self.lambda_elasticity * fisher_t[name] * param_diff

        # 除以任务数以平均
        if len(self._fisher_matrices) > 0:
            for name in ewc_grads:
                ewc_grads[name] /= max(len(self._fisher_matrices) - (1 if current_task_id is not None else 0), 1)

        return ewc_grads

    # ==================== 记忆巩固集成 ====================

    def consolidation_hook(
        self,
        episode_data: dict[str, Any],
        model_params: dict[str, np.ndarray] | None = None,
        task_boundary_detected: bool | None = None,
    ) -> dict[str, Any]:
        """
        记忆巩固钩子

        在 ComplementaryLearningMemory.consolidate() 被调用时触发。
        执行:
        1. 检测是否到了巩固时机
        2. 检测任务边界 (体制变化)
        3. 如果需要，注册新任务

        Args:
            episode_data: 当前 episode 数据
            model_params: 当前模型参数 (可选)
            task_boundary_detected: 是否强制检测到任务边界 (None 自动检测)

        Returns:
            Dict 包含巩固结果
        """
        self._consolidation_step += 1
        self._episode_buffer.append(episode_data)

        result = {
            "ewc_loss": 0.0,
            "task_registered": False,
            "task_id": None,
            "consolidation_step": self._consolidation_step,
        }

        # 检查是否应执行巩固
        episodes_since_last = self._consolidation_step - self._last_consolidation_episode
        if episodes_since_last < self.consolidation_interval:
            return result

        # 检测任务边界
        is_task_boundary = task_boundary_detected
        if is_task_boundary is None and model_params is not None:
            # 使用数据分布检测
            if "features" in episode_data:
                features = np.array(episode_data["features"])
                is_task_boundary = self._task_detector.update(features)

        # 如果在任务边界且有模型参数，注册新任务
        if is_task_boundary and model_params is not None and self._validate_params(model_params):
            task_id = self._task_detector.current_task_id
            fisher = self.estimate_fisher_empirical(model_params)
            self.register_task(model_params, task_id, fisher)

            self._last_consolidation_episode = self._consolidation_step
            self._consolidated_episodes += 1
            self._task_change_history.append(task_id)

            result["task_registered"] = True
            result["task_id"] = task_id

        return result

    def compute_consolidation_loss(
        self,
        current_params: dict[str, np.ndarray],
        current_task_id: int | None = None,
    ) -> float:
        """
        计算巩固损失 (用于训练时的正则化)

        在 ComplementaryLearningMemory.consolidate() 中调用，
        将 EWC 损失加到总损失中。

        Args:
            current_params: 当前参数
            current_task_id: 当前任务 ID

        Returns:
            float: EWC 巩固损失
        """
        ewc_loss = self.compute_ewc_loss(current_params, current_task_id)
        return ewc_loss

    # ==================== 在线适应性 ====================

    def update_importance(
        self,
        task_id: int,
        performance_delta: float,
    ) -> None:
        """
        基于性能变化更新任务重要性

        如果旧任务性能显著下降，增加其重要性权重。

        Args:
            task_id: 任务 ID
            performance_delta: 性能变化 (负值表示下降)
        """
        for i, tid in enumerate(self._task_ids):
            if tid == task_id:
                if performance_delta < 0:
                    # 性能下降 → 增加保护
                    self._task_importances[i] *= 1.0 - performance_delta
                    self._task_importances[i] = min(10.0, self._task_importances[i])
                else:
                    # 性能提升 → 正常衰减
                    self._task_importances[i] *= self.memory_decay
                break

    def decay_old_tasks(self) -> None:
        """
        衰减旧任务的重要性 (时间衰减)

        越早的任务获得越少的保护，为学习新任务腾出容量。
        """
        for i in range(len(self._task_importances)):
            # 时间衰减: 越旧的任务权重越小
            age_factor = self.memory_decay ** (len(self._task_importances) - i - 1)
            self._task_importances[i] *= age_factor

        # 重新归一化
        total = sum(self._task_importances)
        if total > 0:
            self._task_importances = [imp / total for imp in self._task_importances]

    # ==================== 辅助方法 ====================

    def _update_protection_ratio(self) -> None:
        """更新被保护参数的比例"""
        if not self._fisher_matrices:
            self._protection_ratio = 0.0
            return

        # 计算有多少参数在任何任务中被保护
        total_params = 0
        protected_params = 0

        if self._param_template:
            for name, param in self._param_template.items():
                total_params += param.size
                is_protected = False
                for fisher in self._fisher_matrices:
                    if name in fisher and np.any(fisher[name] >= self.importance_threshold):
                        is_protected = True
                        break
                if is_protected:
                    protected_params += param.size

        self._protection_ratio = protected_params / max(total_params, 1)

    def get_task_info(self) -> list[dict[str, Any]]:
        """获取所有已注册任务的信息"""
        tasks = []
        for i in range(len(self._task_ids)):
            fisher_i = self._fisher_matrices[i]
            n_protected = sum(int(np.sum(f > self.importance_threshold)) for f in fisher_i.values())
            n_total = sum(f.size for f in fisher_i.values())

            tasks.append(
                {
                    "task_id": self._task_ids[i],
                    "importance": self._task_importances[i],
                    "protected_params": n_protected,
                    "total_params": n_total,
                    "protection_ratio": n_protected / max(n_total, 1),
                },
            )

        return tasks

    def get_memory_usage(self) -> dict[str, int]:
        """获取内存使用统计"""
        total_bytes = 0
        for fisher in self._fisher_matrices:
            for arr in fisher.values():
                total_bytes += arr.nbytes
        for params in self._optimal_params:
            for arr in params.values():
                total_bytes += arr.nbytes

        return {
            "num_tasks": len(self._task_ids),
            "fisher_matrices_bytes": total_bytes,
            "episode_buffer_size": len(self._episode_buffer),
            "parameter_snapshots": len(self._parameter_snapshots),
        }

    # ==================== 序列化 ====================

    def get_params_dict(self) -> dict[str, Any]:
        """获取序列化参数"""
        return {
            "fisher_matrices": [
                {name: arr.tolist() for name, arr in fisher.items()} for fisher in self._fisher_matrices
            ],
            "optimal_params": [{name: arr.tolist() for name, arr in params.items()} for params in self._optimal_params],
            "task_ids": self._task_ids,
            "task_importances": self._task_importances,
            "consolidation_step": self._consolidation_step,
            "consolidated_episodes": self._consolidated_episodes,
            "protection_ratio": self._protection_ratio,
        }

    def load_params_dict(self, data: dict[str, Any]) -> None:
        """加载序列化参数"""
        self._fisher_matrices = [
            {name: np.array(arr) for name, arr in fisher.items()} for fisher in data.get("fisher_matrices", [])
        ]
        self._optimal_params = [
            {name: np.array(arr) for name, arr in params.items()} for params in data.get("optimal_params", [])
        ]
        self._task_ids = data.get("task_ids", [])
        self._task_importances = data.get("task_importances", [])
        self._consolidation_step = data.get("consolidation_step", 0)
        self._consolidated_episodes = data.get("consolidated_episodes", 0)
        self._protection_ratio = data.get("protection_ratio", 0.0)

    def save(self, path: str) -> None:
        """保存到 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_params_dict(), f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        """从 JSON 文件加载"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.load_params_dict(data)

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "num_protected_tasks": len(self._task_ids),
            "protection_ratio": self._protection_ratio,
            "lambda_elasticity": self.lambda_elasticity,
            "consolidation_step": self._consolidation_step,
            "consolidated_episodes": self._consolidated_episodes,
            "ewc_loss_avg": float(np.mean(self._ewc_loss_history[-100:])) if self._ewc_loss_history else 0.0,
            "task_changes_detected": self._task_detector.num_detected_changes,
            "fisher_samples": self.fisher_samples,
        }

    def reset(self) -> None:
        """重置运行时状态"""
        self._fisher_matrices.clear()
        self._optimal_params.clear()
        self._task_ids.clear()
        self._task_importances.clear()
        self._consolidation_step = 0
        self._last_consolidation_episode = 0
        self._consolidated_episodes = 0
        self._episode_buffer.clear()
        self._parameter_snapshots.clear()
        self._ewc_loss_history.clear()
        self._task_change_history.clear()
        self._protection_ratio = 0.0
        self._task_detector.reset()
