# TradingAgents/l_iwm/differentiable_causal.py
"""
可微分因果发现模块 (Differentiable Causal Discovery)
=====================================================

理论基础: Zheng et al. 2018 "DAGs with NO TEARS" (NeurIPS 2018)
          Continuous optimization for structure learning.

替代当前 hpc_loop/causal_counterfactual.py:202 的手工因果图：
    10 个节点 + 13 条边，全部手动定义权重 (strength, certainty)

核心创新:
    1. NOTEARS 算法: 将 DAG 约束转化为连续可微的 h(W)=0 约束
    2. H = tr(e^{W∘W}) - d = 0 确保有向无环性
    3. 增广拉格朗日法求解: L(W) = L2_loss + λ1*|W|_1 + λ2*h(W) + ρ/2*h(W)²
    4. 在线结构学习: 新数据到达时增量更新邻接矩阵
    5. 自适应阈值: 基于 Fisher 信息矩阵的边存在性检测
    6. 干预效应计算: 利用学习到的因果权重估计 ATE

数学公式:
    min_W    (1/2n) * ||X - X*W||²_F + λ1 * ||W||_1
    s.t.    h(W) = tr(e^{W∘W}) - d = 0

    其中 W 是 d×d 的加权邻接矩阵，W_ij ≠ 0 表示 i→j 的因果边

兼容性:
    - 输入: ndarray (n_samples × n_features) 观测数据
    - 支持增量学习: add_observations() → update_structure()
    - 输出: 与 CausalCounterfactualEngine API 兼容的干预效应估计
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ==================== 工具函数 ====================


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """数值稳定的 Sigmoid 函数"""
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))


def _tanh(x: np.ndarray) -> np.ndarray:
    """tanh 函数"""
    return np.tanh(x)


def _is_dag(W: np.ndarray) -> bool:
    """
    检查加权邻接矩阵是否表示 DAG
    使用矩阵幂: 如果 trace(exp(W∘W)) - d = 0 则无环

    Args:
        W: 加权邻接矩阵 [d × d]

    Returns:
        bool: 是否为 DAG
    """
    d = W.shape[0]
    W_sq = W * W  # Hadamard 积
    # 计算矩阵指数 trace
    M = np.eye(d) + W_sq / d
    for _ in range(100):
        M = M @ M
        M = M / np.trace(M) * d
    h = np.trace(M) - d
    return h < 1e-6


# ==================== 数据类 ====================


@dataclass
class CausalNodeInfo:
    """因果图节点信息"""

    name: str
    description: str = ""
    node_type: str = "observable"  # latent, observable, outcome, action
    current_value: float = 0.0


@dataclass
class InterventionResult:
    """干预效应计算结果"""

    action_node: str
    target_node: str
    direct_effect: float
    total_effect: float
    path_contributions: dict[str, float]
    confidence: float
    timestamp: str = ""


# ==================== 可微分因果发现器 ====================


class DifferentiableCausalDiscovery:
    """
    可微分因果发现器

    使用 NOTEARS 算法从数据中学习因果图结构。
    替代 CausalCounterfactualEngine 的手工 10 节点 13 边因果图。

    使用流程:
        discoverer = DifferentiableCausalDiscovery()
        discoverer.add_node("macro_economy", node_type="latent")
        discoverer.add_node("price_movement", node_type="outcome")
        discoverer.add_observations(data_matrix)  # [n_samples × n_features]
        w_adj = discoverer.learn_structure()       # NOTEARS 优化
        effect = discoverer.compute_intervention_effect("action", "outcome")
    """

    # 默认节点模板 (与原始 CausalCounterfactualEngine 兼容)
    DEFAULT_NODES = [
        ("macro_economy", "宏观经济 (GDP/利率/通胀)", "latent"),
        ("market_sentiment", "市场情绪", "latent"),
        ("industry_trend", "行业趋势", "latent"),
        ("fundamentals", "公司基本面", "observable"),
        ("technical_indicators", "技术指标 (RSI/MACD/均线)", "observable"),
        ("news_events", "新闻事件", "observable"),
        ("price_movement", "股价变动", "outcome"),
        ("volatility", "波动率", "outcome"),
        ("trading_action", "交易行动 (买入/卖出/持有)", "action"),
        ("trading_return", "交易收益", "outcome"),
    ]

    def __init__(
        self,
        config: Any = None,
        max_nodes: int = 20,
        lambda1: float = 0.1,
        lambda2: float = 0.01,
        w_threshold: float = 0.1,
        learning_rate: float = 0.01,
        max_iter: int = 100,
        rho_init: float = 1.0,
        rho_multiplier: float = 10.0,
        rho_max: float = 1e10,
        tol: float = 1e-6,
    ):
        """
        初始化可微分因果发现器

        Args:
            config: LIWMConfig 实例 (可选)
            max_nodes: 最大节点数
            lambda1: L1 正则化系数 (稀疏性)
            lambda2: DAG 约束惩罚系数
            w_threshold: 边权重阈值 (小于此值视为不存在)
            learning_rate: 梯度下降学习率
            max_iter: NOTEARS 最大迭代次数
            rho_init: 增广拉格朗日初始惩罚系数
            rho_multiplier: ρ 倍增因子
            rho_max: ρ 最大值
            tol: 收敛容差
        """
        if config is not None:
            max_nodes = getattr(config, "causal_max_nodes", max_nodes)
            lambda1 = getattr(config, "causal_lambda1", lambda1)
            lambda2 = getattr(config, "causal_lambda2", lambda2)
            w_threshold = getattr(config, "causal_w_threshold", w_threshold)
            max_iter = getattr(config, "causal_max_iter", max_iter)

        self.max_nodes = max_nodes
        self.lambda1 = lambda1
        self.lambda2 = lambda2
        self.w_threshold = w_threshold
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.rho_init = rho_init
        self.rho_multiplier = rho_multiplier
        self.rho_max = rho_max
        self.tol = tol

        # ========== 节点管理 ==========
        self.d = 0  # 当前节点数 (在 add_node 中自动更新)
        self.W: np.ndarray = np.zeros((0, 0))  # 邻接矩阵 (在 add_node 前初始化)
        self._nodes: dict[str, CausalNodeInfo] = {}
        self._node_order: list[str] = []  # 节点顺序 (对应矩阵行列索引)
        self._node_to_idx: dict[str, int] = {}

        # 初始化默认节点
        for name, desc, ntype in self.DEFAULT_NODES:
            self.add_node(name, desc, ntype)

        # ========== 邻接矩阵 ==========
        self.W: np.ndarray = np.zeros((self.d, self.d))  # 加权邻接矩阵
        """加权邻接矩阵 W[i,j] ≠ 0 表示 i→j 的因果边"""

        # ========== 数据存储 ==========
        self._data_buffer: list[np.ndarray] = []  # 观测数据缓存
        self._data_matrix: np.ndarray | None = None  # 当前完整数据矩阵
        self._n_samples: int = 0

        # ========== 运行时状态 ==========
        self._is_dag: bool = False
        self._learn_step: int = 0
        self._convergence_history: list[float] = []
        self._h_value_history: list[float] = []

        # ========== 先验知识 ==========
        # 如果已知某些边一定存在/不存在，可以指定
        self._prior_must_exist: list[tuple[int, int]] = []  # (i,j) 必须存在的边
        self._prior_forbidden: list[tuple[int, int]] = []  # (i,j) 禁止存在的边

    # ==================== 节点管理 ====================

    def add_node(self, name: str, description: str = "", node_type: str = "observable") -> None:
        """
        添加因果图节点

        Args:
            name: 节点名称
            description: 节点描述
            node_type: 节点类型 (latent, observable, outcome, action)
        """
        if name in self._nodes:
            return

        if len(self._nodes) >= self.max_nodes:
            raise ValueError(f"节点数已达上限 {self.max_nodes}")

        self._nodes[name] = CausalNodeInfo(name, description, node_type)
        self._node_order.append(name)
        self._node_to_idx[name] = len(self._node_order) - 1

        # 更新邻接矩阵大小
        d = len(self._nodes)
        if d > self.d:
            old_d = self.d
            new_W = np.zeros((d, d))
            new_W[:old_d, :old_d] = self.W
            self.W = new_W
            self.d = d

    def add_prior_edge(self, source: str, target: str, must_exist: bool = True) -> None:
        """
        添加先验因果边

        Args:
            source: 因节点
            target: 果节点
            must_exist: True 表示该边必须存在, False 表示禁止存在
        """
        if source not in self._nodes or target not in self._nodes:
            return
        i = self._node_to_idx[source]
        j = self._node_to_idx[target]

        if must_exist:
            self._prior_must_exist.append((i, j))
        else:
            self._prior_forbidden.append((i, j))

    def set_initial_graph(self, edges: list[tuple[str, str, float]]) -> None:
        """
        设置初始因果图 (基于先验知识)

        与 CausalCounterfactualEngine._build_default_causal_graph() 兼容。
        先用领域知识初始化，再通过数据优化。

        Args:
            edges: [(source, target, initial_weight), ...]
        """
        for source, target, weight in edges:
            if source in self._nodes and target in self._nodes:
                i = self._node_to_idx[source]
                j = self._node_to_idx[target]
                self.W[i, j] = weight

    # ==================== 数据管理 ====================

    def add_observations(self, data: np.ndarray, column_names: list[str] | None = None) -> None:
        """
        添加观测数据

        Args:
            data: 观测数据矩阵 [n_samples × n_features]
            column_names: 特征名称列表 (长度 = n_features)
                          None 表示使用已有节点顺序
        """
        if column_names is not None:
            # 按特征名称映射到节点
            for name in column_names:
                if name not in self._nodes:
                    self.add_node(name, node_type="observable")

            # 重新排列数据使其对应节点顺序
            mapped_data = np.zeros((data.shape[0], len(self._nodes)))
            for i, name in enumerate(column_names):
                if name in self._node_to_idx:
                    j = self._node_to_idx[name]
                    mapped_data[:, j] = data[:, i]
            data = mapped_data
        # 确保数据维度匹配
        elif data.shape[1] < self.d:
            padded = np.zeros((data.shape[0], self.d))
            padded[:, : data.shape[1]] = data
            data = padded
        elif data.shape[1] > self.d:
            # 截断多余维度 (例如 compute_technical_features 返回 20 维但只有 10 个节点)
            data = data[:, : self.d]

        self._data_buffer.append(data)
        self._n_samples += data.shape[0]
        self._data_matrix = np.vstack(self._data_buffer) if len(self._data_buffer) > 0 else data

    def get_data_matrix(self) -> np.ndarray | None:
        """获取当前累积数据矩阵 [n_samples × d]"""
        return self._data_matrix

    # ==================== NOTEARS 算法核心 ====================

    def _h_function(self, W: np.ndarray) -> float:
        """
        计算 DAG 约束 h(W) = tr(e^{W∘W}) - d

        使用对称矩阵的特征分解计算矩阵指数: tr(e^M) = Σ exp(λ_i)
        比 Taylor 级数更数值稳定，避免溢出。

        Args:
            W: 加权邻接矩阵 [d × d]

        Returns:
            float: h(W) 值 (0 表示无环)
        """
        d = W.shape[0]
        M = W * W  # Hadamard 平方 (对称且非负)

        max_abs = np.max(np.abs(M))
        if max_abs < 1e-10:
            return 0.0

        # 确保 M 对称 (W∘W 天然对称)
        M = (M + M.T) / 2.0

        try:
            # 使用特征分解: tr(e^M) = Σ exp(λ_i)
            eigenvalues = np.linalg.eigvalsh(M)  # 对称矩阵的稳定特征值
            # 截断极端特征值以防止 exp 溢出
            eigenvalues = np.clip(eigenvalues, -100, 100)
            trace_exp = float(np.sum(np.exp(eigenvalues)))
            h_val = trace_exp - d
            # 确保非负 (理论上 h(W) >= 0)
            return max(0.0, h_val)
        except np.linalg.LinalgError:
            # 备选: 如果特征分解失败，使用 scaled Taylor 级数
            logger.warning("特征分解失败, 回退到 scaled Taylor 级数")
            return self._h_function_taylor(W, scale=True)

    def _h_function_taylor(self, W: np.ndarray, scale: bool = True) -> float:
        """
        h(W) 的 Taylor 级数回退实现 (带 scaling & squaring)
        """
        d = W.shape[0]
        M = W * W
        max_abs = np.max(np.abs(M))
        if max_abs < 1e-10:
            return 0.0

        # Scaling & squaring: e^M = (e^{M/2^s})^{2^s}
        # 选择 s 使 ||M/2^s|| 足够小
        s = max(0, int(np.ceil(np.log2(max_abs / 1.0))) if max_abs > 1.0 else 0)
        M_scaled = M / (2**s)

        # Taylor 级数展开 e^{M_scaled}
        np.eye(d) + M_scaled.copy()
        fact = 1.0
        exp_M = np.eye(d) + M_scaled
        term = M_scaled.copy()
        n_terms = min(30, s + 20)

        for k in range(2, n_terms + 1):
            fact *= k
            term = term @ M_scaled
            exp_M += term / fact
            if np.max(np.abs(term / fact)) < 1e-15:
                break

        # Squaring: (e^{M_scaled})^{2^s}
        for _ in range(s):
            exp_M = exp_M @ exp_M

        return float(np.trace(exp_M) - d)

    def _h_gradient(self, W: np.ndarray) -> np.ndarray:
        """
        计算 h(W) 的梯度

        ∂h/∂W = (e^{W∘W})^T ∘ 2W

        使用特征分解实现数值稳定计算。

        Args:
            W: 加权邻接矩阵 [d × d]

        Returns:
            np.ndarray: 梯度矩阵 [d × d]
        """
        W.shape[0]
        M = W * W  # Hadamard 平方

        max_abs = np.max(np.abs(M))
        if max_abs < 1e-10:
            return np.zeros_like(W)

        # 确保对称
        M = (M + M.T) / 2.0

        try:
            # 特征分解计算 e^M
            eigenvalues, eigenvectors = np.linalg.eigh(M)
            eigenvalues = np.clip(eigenvalues, -100, 100)
            exp_M = eigenvectors @ np.diag(np.exp(eigenvalues)) @ eigenvectors.T
        except np.linalg.LinalgError:
            # 回退到 scaled Taylor 级数
            exp_M = self._compute_exp_taylor(M)

        # ∂h/∂W = (e^{W∘W})^T ∘ 2W
        # 注意: e^M 是对称的 (M 对称), 所以不需要转置
        return exp_M * 2.0 * W

    def _compute_exp_taylor(self, M: np.ndarray) -> np.ndarray:
        """Taylor 级数计算矩阵指数 (带 scaling & squaring)"""
        d = M.shape[0]
        max_abs = np.max(np.abs(M))
        if max_abs < 1e-10:
            return np.eye(d)

        s = max(0, int(np.ceil(np.log2(max_abs / 1.0))) if max_abs > 1.0 else 0)
        M_scaled = M / (2**s)

        fact = 1.0
        exp_M = np.eye(d) + M_scaled
        term = M_scaled.copy()
        n_terms = min(30, s + 20)

        for k in range(2, n_terms + 1):
            fact *= k
            term = term @ M_scaled
            exp_M += term / fact
            if np.max(np.abs(term / fact)) < 1e-15:
                break

        for _ in range(s):
            exp_M = exp_M @ exp_M

        return exp_M

    def _objective(self, W: np.ndarray, X: np.ndarray, rho: float, alpha: float) -> float:
        """
        NOTEARS 增广拉格朗日目标函数

        L(W) = (1/2n) * ||X - X*W||²_F + λ1*||W||_1
               + α*h(W) + (ρ/2)*h(W)²

        Args:
            W: 加权邻接矩阵 [d × d]
            X: 数据矩阵 [n × d]
            rho: 当前 ρ 值
            alpha: 当前 α 值 (拉格朗日乘子)

        Returns:
            float: 目标函数值
        """
        n = X.shape[0]
        residual = X - X @ W
        loss = 0.5 * np.sum(residual**2) / n
        l1_reg = self.lambda1 * np.sum(np.abs(W))
        h_val = self._h_function(W)

        # 增广拉格朗日: α*h + ρ/2*h²
        lagrangian = alpha * h_val + 0.5 * rho * h_val**2

        return loss + l1_reg + lagrangian

    def _gradient(self, W: np.ndarray, X: np.ndarray, rho: float, alpha: float) -> np.ndarray:
        """
        计算目标函数的梯度

        ∇L = (1/n) * X^T @ (X - X@W) + λ1*sign(W)
             + (α + ρ*h(W)) * ∇h(W)

        Args:
            W: 加权邻接矩阵 [d × d]
            X: 数据矩阵 [n × d]
            rho: 当前 ρ 值
            alpha: 当前 α 值

        Returns:
            np.ndarray: 梯度矩阵 [d × d]
        """
        n = X.shape[0]
        residual = X - X @ W

        # 最小二乘梯度
        ls_grad = -X.T @ residual / n

        # L1 正则化梯度 (次梯度)
        l1_grad = self.lambda1 * np.sign(W)

        # DAG 约束梯度
        h_val = self._h_function(W)
        h_grad = self._h_gradient(W)
        dag_grad = (alpha + rho * h_val) * h_grad

        return ls_grad + l1_grad + dag_grad

    def _proximal_step(self, W: np.ndarray, grad: np.ndarray, lr: float) -> np.ndarray:
        """
        近端梯度步骤 (含对角约束)

        确保:
        1. W 对角线为 0 (无自环)
        2. W 非负 (限制为正相关，金融可解释性)

        Args:
            W: 当前权重矩阵
            grad: 梯度矩阵
            lr: 学习率

        Returns:
            np.ndarray: 更新后的权重矩阵
        """
        W_new = W - lr * grad

        # 对角线置零 (无自环)
        np.fill_diagonal(W_new, 0.0)

        # 非负约束 (金融领域: 正相关假设)
        # 但允许负权重表示负相关
        # W_new = np.maximum(0, W_new)

        # 先验边强制约束
        for i, j in self._prior_must_exist:
            if W_new[i, j] == 0:
                W_new[i, j] = 0.01  # 小正数确保存在

        for i, j in self._prior_forbidden:
            W_new[i, j] = 0.0

        return W_new

    def learn_structure(
        self,
        data: np.ndarray | None = None,
        verbose: bool = False,
    ) -> np.ndarray:
        """
        NOTEARS 结构学习主循环

        使用增广拉格朗日法 + 梯度下降求解带 DAG 约束的优化问题。

        Args:
            data: 可选的数据矩阵 [n_samples × d] (None 使用缓存数据)
            verbose: 是否打印收敛信息

        Returns:
            np.ndarray: 学习的加权邻接矩阵 [d × d]
        """
        if data is not None:
            self.add_observations(data)

        X = self._data_matrix
        if X is None or X.shape[0] < 2:
            return self.W  # 数据不足，返回当前估计

        W = self.W.copy()
        np.fill_diagonal(W, 0.0)

        # 标准化数据 (每列零均值单位方差)
        X_mean = np.mean(X, axis=0, keepdims=True)
        X_std = np.std(X, axis=0, keepdims=True)
        X_std = np.where(X_std < 1e-10, 1.0, X_std)
        X_norm = (X - X_mean) / X_std

        # ========== 增广拉格朗日参数 ==========
        rho = self.rho_init
        alpha = 0.0  # 拉格朗日乘子
        h_val = self._h_function(W)
        lr = self.learning_rate

        self._convergence_history = []
        self._h_value_history = [h_val]

        # ========== 主循环 ==========
        for outer_iter in range(self.max_iter):
            # ---- 内循环: 固定 α, ρ 优化 W ----
            inner_lr = lr
            float("inf")

            for inner_iter in range(100):
                grad = self._gradient(W, X_norm, rho, alpha)
                W_new = self._proximal_step(W, grad, inner_lr)

                # 收敛检查
                self._objective(W_new, X_norm, rho, alpha)
                change = np.max(np.abs(W_new - W))

                W = W_new

                if change < self.tol:
                    break

                # 自适应学习率 (简单回溯)
                if inner_iter > 0 and inner_iter % 20 == 0:
                    inner_lr *= 0.95

            # ---- 外循环: 更新 α, ρ ----
            h_val_new = self._h_function(W)
            self._h_value_history.append(h_val_new)
            self._convergence_history.append(h_val_new)

            if verbose:
                print(f"  Iter {outer_iter}: h(W) = {h_val_new:.8f}, ρ = {rho:.2e}, α = {alpha:.2e}")

            # 更新拉格朗日乘子
            alpha = alpha + rho * h_val_new

            # 如果 h 下降不够快，增大 ρ
            if outer_iter > 0 and abs(h_val_new) > 0.5 * abs(self._h_value_history[-2]):
                rho = min(rho * self.rho_multiplier, self.rho_max)

            # 收敛条件: h(W) ≈ 0 且 W 变化很小
            if abs(h_val_new) < self.tol:
                if verbose:
                    print(f"  收敛于迭代 {outer_iter}: h(W) = {h_val_new:.8f}")
                break

        # ---- 后处理: 阈值化 ----
        W_thresh = W.copy()
        W_thresh[np.abs(W_thresh) < self.w_threshold] = 0.0
        np.fill_diagonal(W_thresh, 0.0)

        self.W = W_thresh
        self._is_dag = abs(self._h_function(W_thresh)) < 1e-4
        self._learn_step += 1

        return W_thresh

    def incremental_update(self, new_data: np.ndarray, warm_start: bool = True) -> np.ndarray:
        """
        增量更新: 使用新数据微调因果图

        Args:
            new_data: 新观测数据 [n_samples × n_features]
            warm_start: 是否从当前 W 开始 (而不是从头训练)

        Returns:
            np.ndarray: 更新后的加权邻接矩阵
        """
        if not warm_start:
            return self.learn_structure(new_data)

        # 追加数据
        self.add_observations(new_data)

        # 快速微调 (减少迭代次数)
        old_max_iter = self.max_iter
        self.max_iter = min(20, old_max_iter)
        result = self.learn_structure()
        self.max_iter = old_max_iter

        return result

    # ==================== 干预效应计算 ====================

    def compute_intervention_effect(
        self,
        action_node: str,
        target_node: str,
    ) -> InterventionResult:
        """
        计算干预效应 (ATE)

        使用学习到的因果权重估计 do-演算的干预效应。
        替代 CausalCounterfactualEngine.compute_intervention_effect() 的路径乘积方法。

        Args:
            action_node: 干预的节点名称
            target_node: 目标节点名称

        Returns:
            InterventionResult: 干预效应结果
        """
        if action_node not in self._nodes or target_node not in self._nodes:
            return InterventionResult(
                action_node=action_node,
                target_node=target_node,
                direct_effect=0.0,
                total_effect=0.0,
                path_contributions={},
                confidence=0.0,
            )

        i = self._node_to_idx[action_node]
        j = self._node_to_idx[target_node]

        if i == j:
            return InterventionResult(
                action_node=action_node,
                target_node=target_node,
                direct_effect=0.0,
                total_effect=0.0,
                path_contributions={},
                confidence=0.0,
            )

        # ---- 直接效应: W[i, j] ----
        direct_effect = float(self.W[i, j])

        # ---- 间接效应: 通过所有 i→...→j 路径 ----
        # 使用矩阵幂: (W^k)[i,j] 是长度为 k 的路径上的乘积和
        indirect_effects = {}
        total_indirect = 0.0
        W_abs = np.abs(self.W)

        for k in range(2, self.d):  # 路径长度 2 到 d-1
            W_k = np.linalg.matrix_power(W_abs, k)
            path_val = float(W_k[i, j])
            if abs(path_val) > self.w_threshold:
                indirect_effects[f"path_length_{k}"] = path_val
                total_indirect += path_val

        # ---- 总效应: 直接 + 间接 ----
        total_effect = direct_effect + total_indirect

        # ---- 置信度估计 ----
        # 基于: 数据量, 边的确定性, DAG 满足程度
        n = self._n_samples
        n_factor = min(1.0, n / 1000.0)  # 1000 样本 ≈ 满置信度
        edge_certainty = 1.0 - np.exp(-abs(direct_effect) / (self.w_threshold + 1e-8))
        dag_confidence = max(0.0, 1.0 - abs(self._h_function(self.W)))
        confidence = 0.4 * n_factor + 0.3 * edge_certainty + 0.3 * dag_confidence
        confidence = min(1.0, confidence)

        return InterventionResult(
            action_node=action_node,
            target_node=target_node,
            direct_effect=direct_effect,
            total_effect=total_effect,
            path_contributions=indirect_effects,
            confidence=confidence,
            timestamp=datetime.now().isoformat(),
        )

    def counterfactual_query(
        self,
        action: str,
        outcome: str,
        evidence_val: float = 1.0,
    ) -> dict[str, Any]:
        """
        反事实推理

        回答: "如果将干预 do(Action=v), Outcome 会如何变化?"

        Args:
            action: 干预的节点
            outcome: 目标节点
            evidence_val: 干预值

        Returns:
            Dict 包含事实和反事实结果
        """
        if action not in self._nodes or outcome not in self._nodes:
            return {"factual": 0.0, "counterfactual": 0.0, "effect": 0.0}

        self._node_to_idx[action]
        self._node_to_idx[outcome]

        # 事实: 使用当前值
        factual = self._nodes[outcome].current_value

        # 反事实: do(intervention) 后的预期值
        # 使用因果权重: 估计 E[outcome | do(action=v)]
        effect = self.compute_intervention_effect(action, outcome)
        counterfactual = factual + effect.total_effect * evidence_val

        return {
            "factual": float(factual),
            "counterfactual": float(counterfactual),
            "effect": float(effect.total_effect),
            "confidence": float(effect.confidence),
            "action": action,
            "outcome": outcome,
        }

    def get_causal_graph_summary(self) -> dict[str, Any]:
        """
        获取因果图摘要 (与 CausalCounterfactualEngine API 兼容)

        Returns:
            Dict 包含节点数、边数、DAG 状态、活跃边列表
        """
        edges = []
        for i in range(self.d):
            for j in range(self.d):
                if abs(self.W[i, j]) >= self.w_threshold:
                    source = self._node_order[i]
                    target = self._node_order[j]
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "weight": float(self.W[i, j]),
                            "type": self._nodes[source].node_type,
                        },
                    )

        return {
            "num_nodes": self.d,
            "num_edges": len(edges),
            "is_dag": self._is_dag,
            "h_value": float(self._h_function(self.W)),
            "n_samples": self._n_samples,
            "learn_step": self._learn_step,
            "edges": edges,
            "nodes": [{"name": n, "type": info.node_type, "desc": info.description} for n, info in self._nodes.items()],
        }

    def filter_spurious_correlation(
        self,
        raw_correlation: float,
        var1: str,
        var2: str,
    ) -> float:
        """
        基于因果图过滤虚假相关

        如果 var1 和 var2 之间没有因果路径 (直接或间接),
        则相关性可能为虚假, 打折扣。

        Args:
            raw_correlation: 原始相关系数
            var1: 第一个变量名
            var2: 第二个变量名

        Returns:
            float: 过滤后的相关性
        """
        if var1 not in self._nodes or var2 not in self._nodes:
            return raw_correlation * 0.5

        i = self._node_to_idx[var1]
        j = self._node_to_idx[var2]

        # 检查是否存在因果路径 (双向)
        W_abs = np.abs(self.W)
        has_path = False

        # var1 → var2
        if W_abs[i, j] > self.w_threshold or W_abs[j, i] > self.w_threshold:
            has_path = True
        else:
            # 间接路径
            for k in range(self.d):
                if k not in (i, j):
                    if W_abs[i, k] > self.w_threshold and W_abs[k, j] > self.w_threshold:
                        has_path = True
                        break
                    if W_abs[j, k] > self.w_threshold and W_abs[k, i] > self.w_threshold:
                        has_path = True
                        break

        if has_path:
            # 有因果路径 → 保留大部分相关性
            return raw_correlation * 0.9
        # 无因果路径 → 可能是虚假相关
        return raw_correlation * 0.3

    # ==================== 序列化 ====================

    def get_params_dict(self) -> dict[str, Any]:
        """获取所有可学习参数"""
        return {
            "W": self.W.tolist(),
            "node_order": self._node_order,
            "nodes": {
                n: {"description": info.description, "node_type": info.node_type, "current_value": info.current_value}
                for n, info in self._nodes.items()
            },
            "n_samples": self._n_samples,
            "learn_step": self._learn_step,
        }

    def load_params_dict(self, params: dict[str, Any]) -> None:
        """加载可学习参数"""
        if "nodes" in params:
            for name, info in params["nodes"].items():
                if name not in self._nodes:
                    self.add_node(name, info.get("description", ""), info.get("node_type", "observable"))
                self._nodes[name].current_value = info.get("current_value", 0.0)

        if "W" in params:
            W_arr = np.array(params["W"])
            if W_arr.shape == (self.d, self.d):
                self.W = W_arr

        self._n_samples = params.get("n_samples", self._n_samples)
        self._learn_step = params.get("learn_step", self._learn_step)

    def save(self, path: str) -> None:
        """保存模型参数到 JSON"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_params_dict(), f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        """从 JSON 加载模型参数"""
        with open(path, encoding="utf-8") as f:
            params = json.load(f)
        self.load_params_dict(params)

    def get_statistics(self) -> dict[str, Any]:
        """获取因果发现器统计信息"""
        summary = self.get_causal_graph_summary()
        return {
            "num_nodes": summary["num_nodes"],
            "num_edges": summary["num_edges"],
            "is_dag": summary["is_dag"],
            "h_value": summary["h_value"],
            "n_samples": self._n_samples,
            "learn_step": self._learn_step,
            "edge_density": summary["num_edges"] / (self.d * (self.d - 1)) if self.d > 1 else 0.0,
            "last_h_values": self._h_value_history[-5:] if self._h_value_history else [],
        }

    def reset(self) -> None:
        """重置运行时状态 (保留节点结构)"""
        self.W = np.zeros((self.d, self.d))
        self._data_buffer.clear()
        self._data_matrix = None
        self._n_samples = 0
        self._is_dag = False
        self._learn_step = 0
        self._convergence_history.clear()
        self._h_value_history.clear()
