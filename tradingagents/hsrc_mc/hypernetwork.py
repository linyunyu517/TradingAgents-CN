# TradingAgents/hsrc_mc/hypernetwork.py
"""
HyperNetwork — 超网络元控制器
==============================

理论基础: HyperNetworks (Ha et al., 2016, ICLR)
    "HyperNetworks are neural networks that generate the weights for another
    neural network (the target network)."

    在 HSR-MC 中，HyperNetwork 接收 MetaObserver 的观察向量，生成:
    - 各模块的学习率调整因子
    - 各模块的正则化强度调整
    - 各模块的优先级/探索率调整

关键设计:
    1. 轻量级: 隐藏层 64 维，总参数量约 5K
    2. 条件生成: 输出取决于当前系统状态
    3. 带噪输出: 增加探索性 (noise = 0.01)
    4. Adam 优化: 纯 NumPy 实现

输入: observation_vector (来自 MetaObserver.get_observation_vector())
输出: meta_params (调整各模块超参数的向量)
"""

import math
from collections import deque
from typing import Any

import numpy as np


def _he_init(shape: tuple[int, ...]) -> np.ndarray:
    """He 初始化"""
    if len(shape) == 1:
        return np.random.randn(shape[0]) * 0.01
    fan_in = shape[0]
    std = math.sqrt(2.0 / fan_in)
    return np.random.randn(*shape) * std


class _AdamOptimizer:
    """内部 Adam 优化器 (与 L-IWM 风格一致)"""

    def __init__(self, lr: float = 1e-3, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m: dict[str, np.ndarray] = {}
        self.v: dict[str, np.ndarray] = {}
        self.t: int = 0

    def step(self, param_name: str, grad: np.ndarray) -> np.ndarray:
        if param_name not in self.m:
            self.m[param_name] = np.zeros_like(grad)
            self.v[param_name] = np.zeros_like(grad)

        self.t += 1
        self.m[param_name] = self.beta1 * self.m[param_name] + (1 - self.beta1) * grad
        self.v[param_name] = self.beta2 * self.v[param_name] + (1 - self.beta2) * (grad**2)

        m_hat = self.m[param_name] / (1 - self.beta1**self.t)
        v_hat = self.v[param_name] / (1 - self.beta2**self.t)

        return -self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset(self) -> None:
        self.m.clear()
        self.v.clear()
        self.t = 0


class HyperNetwork:
    """
    超网络 — 根据系统观察状态生成元参数。

    网络结构:
        Input (n_features) → Linear + ReLU → Hidden (64) → Linear → Output (n_meta_params)

    输出元参数:
        - 每个模块的学习率调整因子 (6)
        - 每个模块的正则化强度调整 (6)
        - 全局探索率调整 (1)
        - 全局学习率缩放 (1)
        - 模块优先级调整 (6)
        合计: 20 维

    使用流程:
        hypernet = HyperNetwork(config, input_dim)
        meta_params = hypernet.generate(observation_vector)
        hypernet.update(grads_of_loss_wrt_params)
    """

    # 模块名称列表
    MODULE_NAMES = ["RSSM", "RealDataPipeline", "EFE", "Causal", "EWC", "GWS"]

    def __init__(self, config, input_dim: int):
        """
        Args:
            config: HSRMCConfig 实例
            input_dim: 输入观察向量的维度
        """
        self.config = config
        hidden_dim = config.hyper_hidden_dim
        self.input_dim = input_dim

        # 输出维度: 6模块 * 3类元参数 + 全局2 = 20
        self.output_dim = len(self.MODULE_NAMES) * 3 + 2

        # ==================== 网络参数 ====================
        # W1: (input_dim, hidden_dim), b1: (hidden_dim,)
        self.W1 = _he_init((input_dim, hidden_dim))
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)

        # W2: (hidden_dim, output_dim), b2: (output_dim,)
        self.W2 = _he_init((hidden_dim, self.output_dim))
        self.b2 = np.zeros(self.output_dim, dtype=np.float32)

        # ==================== 优化器 ====================
        self.optimizer = _AdamOptimizer(
            lr=config.hyper_learning_rate,
            beta1=config.hyper_beta1,
            beta2=config.hyper_beta2,
        )

        # ==================== 训练状态 ====================
        self.train_step: int = 0
        self._last_input: np.ndarray | None = None
        self._last_output: np.ndarray | None = None

        # 元参数历史（用于日志）
        self._output_history: deque = deque(maxlen=100)

        # 随机数生成器
        self._rng = np.random.RandomState(42)

    # ==================== 前向传播 ====================

    def generate(
        self,
        observation_vector: np.ndarray,
        add_noise: bool = True,
    ) -> dict[str, Any]:
        """
        根据观察向量生成元参数。

        Args:
            observation_vector: (input_dim,) 观察向量
            add_noise: 是否添加探索噪声

        Returns:
            Dict:
                - "learning_rate_factors": {模块名: 因子 (0.1~3.0)}
                - "regularization_factors": {模块名: 因子 (0.1~3.0)}
                - "priority_adjustments": {模块名: 调整 (-0.5~+0.5)}
                - "global_exploration_factor": float (0.1~3.0)
                - "global_lr_scale": float (0.1~3.0)
                - "raw_output": np.ndarray (output_dim,)
        """
        self._last_input = observation_vector.copy()

        # 前向传播
        h = observation_vector @ self.W1 + self.b1
        h = np.maximum(h, 0.0)  # ReLU

        raw = h @ self.W2 + self.b2

        # 添加探索噪声
        if add_noise:
            noise = self._rng.randn(self.output_dim) * self.config.hyper_output_noise
            raw = raw + noise

        self._last_output = raw.copy()
        self._output_history.append(raw.copy())

        # 解码为结构化元参数
        return self._decode_output(raw)

    def _decode_output(self, raw: np.ndarray) -> dict[str, Any]:
        """
        将原始网络输出解码为结构化元参数字典。

        输出向量结构:
            [0:6]   — 学习率因子 (每个模块, sigmoid → [0.1, 3.0])
            [6:12]  — 正则化因子 (每个模块, sigmoid → [0.1, 3.0])
            [12:18] — 优先级调整 (每个模块, tanh → [-0.5, +0.5])
            [18]    — 全局探索因子 (sigmoid → [0.1, 3.0])
            [19]    — 全局学习率缩放 (sigmoid → [0.1, 3.0])
        """
        assert len(raw) == self.output_dim, f"Expected {self.output_dim}, got {len(raw)}"

        # 使用 sigmoid 将输出映射到 (0, 1)，再缩放到 [0.1, 3.0]
        def _sigmoid_scale(x, lo=0.1, hi=3.0):
            return lo + (hi - lo) / (1.0 + math.exp(-x))

        # tanh 映射到 [-0.5, 0.5]
        def _tanh_scale(x):
            return 0.5 * math.tanh(x)

        lr_factors = {}
        reg_factors = {}
        pri_adjustments = {}

        for i, name in enumerate(self.MODULE_NAMES):
            lr_factors[name] = _sigmoid_scale(float(raw[i]))
            reg_factors[name] = _sigmoid_scale(float(raw[i + 6]))
            pri_adjustments[name] = _tanh_scale(float(raw[i + 12]))

        global_exploration = _sigmoid_scale(float(raw[18]))
        global_lr_scale = _sigmoid_scale(float(raw[19]))

        return {
            "learning_rate_factors": lr_factors,
            "regularization_factors": reg_factors,
            "priority_adjustments": pri_adjustments,
            "global_exploration_factor": global_exploration,
            "global_lr_scale": global_lr_scale,
            "raw_output": raw.copy(),
        }

    # ==================== 元学习更新 ====================

    def update(
        self,
        meta_grads: dict[str, np.ndarray],
    ) -> dict[str, float]:
        """
        使用元梯度更新超网络参数。

        Args:
            meta_grads: {参数名: 梯度数组} 字典
                       keys: "W1", "b1", "W2", "b2"

        Returns:
            Dict: 更新统计
        """
        self.train_step += 1

        updates = {}
        for name in ["W1", "b1", "W2", "b2"]:
            if name in meta_grads:
                update = self.optimizer.step(f"hyper_{name}", meta_grads[name])
                param = getattr(self, name)
                setattr(self, name, param + update)
                updates[name] = float(np.linalg.norm(update))

        return {
            "W1_update_norm": updates.get("W1", 0.0),
            "b1_update_norm": updates.get("b1", 0.0),
            "W2_update_norm": updates.get("W2", 0.0),
            "b2_update_norm": updates.get("b2", 0.0),
            "train_step": self.train_step,
        }

    # ==================== 参数管理 ====================

    def get_params_dict(self) -> dict[str, Any]:
        """获取所有可训练参数"""
        return {
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "train_step": self.train_step,
        }

    def load_params_dict(self, params: dict[str, Any]) -> None:
        """加载可训练参数"""
        for key in ["W1", "b1", "W2", "b2"]:
            if key in params:
                setattr(self, key, np.array(params[key]))
        if "train_step" in params:
            self.train_step = params["train_step"]

    def get_statistics(self) -> dict[str, Any]:
        """获取超网络统计信息"""
        return {
            "train_step": self.train_step,
            "W1_norm": float(np.linalg.norm(self.W1)),
            "W2_norm": float(np.linalg.norm(self.W2)),
            "output_dim": self.output_dim,
            "input_dim": self.input_dim,
        }

    def reset(self) -> None:
        """重置超网络状态"""
        self.train_step = 0
        self._last_input = None
        self._last_output = None
        self._output_history.clear()
        self.optimizer.reset()
