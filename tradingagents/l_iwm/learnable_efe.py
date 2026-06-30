# TradingAgents/l_iwm/learnable_efe.py
"""
可学习 EFE 评估器 (Learnable Expected Free Energy Evaluator)
=============================================================

理论基础: Friston Active Inference (2010, 2013); DreamerV3 (Hafner et al., 2023)

替代当前 hpc_loop/active_inference.py:203 中手工分配的认知价值：
    info_gains = {"买入": 0.3, "卖出": 0.3, "持有": 0.05, "获取数据": 0.6}

核心创新:
    1. Epistemic Value Network: (state_embedding, action_embedding) → epistemic_value
       — 从经验中学习各行动的信息增益，替代手工权重
    2. Pragmatic Value Network: (state_embedding, action_embedding) → pragmatic_value
       — 学习风险调整后的预期效用，替代固定风险溢价公式
    3. Action Embeddings: 每个交易动作的可学习嵌入表示（8维）
    4. 可学习探索奖励: 基于状态新颖性的参数化探索奖励，α 系数可学习
    5. TD(λ) 在线学习: 使用实际收益信号更新价值网络
    6. Adam 优化器 (纯 NumPy 实现，兼容 RSSM 的 AdamOptimizer)

数学公式:
    G(π) = -(EpistemicValue(s, a) + PragmaticValue(s, a) + ExplorationBonus(s))

    EpistemicValue(s, a) = f_epistemic(concat(encode(s), embed(a)))
    PragmaticValue(s, a) = f_pragmatic(concat(encode(s), embed(a)))

    TD Error: δ = r + γ * V(s') - V(s)
    Loss: L = δ² + L2_regularization

兼容性:
    - 输入: Dict[str, Any] 状态字典 (同 ActiveInferenceEngine API)
    - 支持 RSSM latent state (h, z 向量)
    - 输出: 与 EFEDecomposition 兼容的 float 值
"""

import json
import math
from collections import deque
from typing import Any

import numpy as np

# ==================== 小工具函数 ====================


def _he_init(shape: tuple[int, ...]) -> np.ndarray:
    """He 初始化 (ReLU 适用)"""
    if len(shape) == 1:
        return np.random.randn(shape[0]) * 0.01
    fan_in = shape[0]
    std = math.sqrt(2.0 / fan_in)
    return np.random.randn(*shape) * std


def _glorot_init(shape: tuple[int, ...]) -> np.ndarray:
    """Glorot/Xavier 初始化 (tanh/sigmoid 适用)"""
    if len(shape) == 1:
        return np.random.randn(shape[0]) * 0.01
    fan_in, fan_out = shape[0], shape[-1]
    limit = math.sqrt(6.0 / (fan_in + fan_out))
    return np.random.uniform(-limit, limit, size=shape)


# ==================== 可学习 EFE 评估器 ====================


class LearnableEFEEvaluator:
    """
    可学习 EFE 评估器

    使用参数化神经网络替代 ActiveInferenceEngine 中手工分配的认知价值和实用价值。
    所有参数通过 Adam 优化器从实际交易经验中学习。

    使用流程:
        evaluator = LearnableEFEEvaluator(config, state_dim=32)
        epistemic = evaluator.compute_epistemic_value(state, "买入")
        pragmatic = evaluator.compute_pragmatic_value(state, "买入")
        efe = evaluator.compute_efe(state, "买入")
        evaluator.update(state, "买入", reward=0.01, next_state)
    """

    # ==================== 标准动作集 ====================
    ACTIONS = ["买入", "卖出", "持有", "获取数据", "调整仓位"]
    ACTION_TO_IDX = {a: i for i, a in enumerate(ACTIONS)}

    def __init__(
        self,
        config: Any = None,
        state_dim: int = 32,
        action_embed_dim: int = 8,
        hidden_dim: int = 8,
        learning_rate: float = 1e-3,
        gamma: float = 0.95,
        td_lambda: float = 0.9,
        exploration_alpha: float = 0.2,
        l2_reg: float = 1e-5,
    ):
        """
        初始化可学习 EFE 评估器

        Args:
            config: LIWMConfig 实例 (可选，提供则覆盖以下参数)
            state_dim: 状态编码维度 (跟 RSSM latent dim 一致)
            action_embed_dim: 动作嵌入维度
            hidden_dim: 价值网络隐层维度
            learning_rate: Adam 学习率
            gamma: 折扣因子
            td_lambda: TD(λ) 回溯系数
            exploration_alpha: 探索奖励初始系数
            l2_reg: L2 正则化系数
        """
        # 从配置加载参数
        if config is not None:
            state_dim = getattr(config, "rssm_latent_dim", state_dim)
            hidden_dim = getattr(config, "efe_epistemic_dim", hidden_dim)
            learning_rate = getattr(config, "efe_learning_rate", learning_rate)
            td_lambda = getattr(config, "efe_td_lambda", td_lambda)
            exploration_alpha = getattr(config, "efe_exploration_alpha", exploration_alpha)

        self.state_dim = state_dim
        self.action_embed_dim = action_embed_dim
        self.hidden_dim = hidden_dim
        self.gamma = gamma
        self.td_lambda = td_lambda
        self.l2_reg = l2_reg
        self.train_step = 0

        # ========== 可学习参数 ==========

        # 1. 动作嵌入矩阵 [num_actions × action_embed_dim]
        self.num_actions = len(self.ACTIONS)
        self.action_embeddings = _glorot_init((self.num_actions, action_embed_dim))

        # 2. 认知价值网络 (Epistemic Value): state+action → epistemic
        #    f_epistemic = W2 * ReLU(W1 * x + b1) + b2
        input_dim = state_dim + action_embed_dim
        self.W_epi_1 = _he_init((input_dim, hidden_dim))
        self.b_epi_1 = np.zeros(hidden_dim)
        self.W_epi_2 = _he_init((hidden_dim, 1))
        self.b_epi_2 = np.zeros(1)

        # 3. 实用价值网络 (Pragmatic Value): state+action → pragmatic
        self.W_prag_1 = _he_init((input_dim, hidden_dim))
        self.b_prag_1 = np.zeros(hidden_dim)
        self.W_prag_2 = _he_init((hidden_dim, 1))
        self.b_prag_2 = np.zeros(1)

        # 4. 状态编码器 (State Encoder): raw state → state_embedding
        #    如果状态已经是向量（如 RSSM latent），直接使用
        #    如果是字典，通过可学习投影映射
        self.W_state_proj = _he_init((state_dim, state_dim))
        self.b_state_proj = np.zeros(state_dim)

        # 5. 探索系数 (可学习的 α)
        self.log_exploration_alpha = np.array(math.log(max(exploration_alpha, 1e-6)))

        # ========== 优化器 ==========
        self.optimizer_epistemic = _AdamOptimizer(learning_rate)
        self.optimizer_pragmatic = _AdamOptimizer(learning_rate)
        self.optimizer_embed = _AdamOptimizer(learning_rate * 0.5)  # 嵌入学习率更低
        self.optimizer_state_proj = _AdamOptimizer(learning_rate * 0.5)
        self.optimizer_alpha = _AdamOptimizer(learning_rate * 0.1)  # α 学习率最低

        # ========== 运行时状态 ==========
        self._state_visitation: dict[str, int] = {}
        """状态访问计数 (用于探索奖励)"""

        self._action_counts: dict[str, int] = dict.fromkeys(self.ACTIONS, 0)
        """行动执行计数"""

        self._experience_buffer: deque = deque(maxlen=5000)
        """经验回放缓冲区"""

        # ========== 统计信息 ==========
        self.epistemic_history: list[float] = []
        self.pragmatic_history: list[float] = []
        self.td_error_history: list[float] = []

    # ==================== 状态编码 ====================

    def encode_state(self, state: dict[str, Any]) -> np.ndarray:
        """
        将状态字典编码为固定维度向量

        支持:
        - RSSM latent state: {"h": np.ndarray, "z": np.ndarray} (优先使用)
        - MarketLatentState: 提取关键数值字段
        - 通用字典: 连接数值字段
        - 已有向量: 直接使用

        Args:
            state: 市场状态字典

        Returns:
            np.ndarray: 状态嵌入向量 [state_dim]
        """
        # Case 1: RSSM latent state (h, z 向量)
        if "h" in state and isinstance(state["h"], np.ndarray):
            h = state["h"].flatten()
            z = state.get("z", np.zeros(self.state_dim)).flatten()
            raw = np.concatenate([h[: self.state_dim // 2], z[: self.state_dim // 2]])
            if len(raw) < self.state_dim:
                raw = np.pad(raw, (0, self.state_dim - len(raw)))
            return raw[: self.state_dim]

        # Case 2: 已经是向量
        if isinstance(state.get("latent"), np.ndarray):
            latent = state["latent"].flatten()
            if len(latent) >= self.state_dim:
                return latent[: self.state_dim]
            return np.pad(latent, (0, self.state_dim - len(latent)))

        # Case 3: 字典 → 提取数值字段
        numeric_fields = []
        for key in [
            "price",
            "volatility",
            "uncertainty",
            "entropy",
            "regime_value",
            "sentiment",
            "momentum",
            "volume_ratio",
            "rsi",
            "macd",
        ]:
            val = state.get(key, 0.0)
            if isinstance(val, (int, float)):
                numeric_fields.append(float(val))
            elif isinstance(val, np.ndarray):
                numeric_fields.extend(val.flatten().tolist()[:3])

        if len(numeric_fields) >= self.state_dim:
            return np.array(numeric_fields[: self.state_dim], dtype=np.float64)
        if len(numeric_fields) > 0:
            raw = np.array(numeric_fields, dtype=np.float64)
            return np.pad(raw, (0, self.state_dim - len(raw)))
        return np.zeros(self.state_dim)

    def _state_signature(self, state: dict[str, Any]) -> str:
        """生成状态签名 (用于访问计数)"""
        price = state.get("price", 0)
        volatility = state.get("volatility", 0)
        regime = state.get("regime", "unknown")
        price_bucket = round(price / 10) * 10 if isinstance(price, (int, float)) else 0
        vol_bucket = round(float(volatility) * 10) / 10 if isinstance(volatility, (int, float)) else 0
        return f"{price_bucket}_{vol_bucket}_{regime}"

    # ==================== 动作嵌入 ====================

    def action_to_embedding(self, action: str) -> np.ndarray:
        """
        获取动作的可学习嵌入向量

        Args:
            action: 动作名称 (如 "买入", "卖出", "持有")

        Returns:
            np.ndarray: 动作嵌入 [action_embed_dim]
        """
        idx = self.ACTION_TO_IDX.get(action, 0)
        return self.action_embeddings[idx].copy()

    def _compute_input(self, state: dict[str, Any], action: str) -> np.ndarray:
        """
        计算价值网络的输入: concat(encode(state), embed(action))

        Args:
            state: 市场状态字典
            action: 动作名称

        Returns:
            np.ndarray: 联合输入向量 [state_dim + action_embed_dim]
        """
        s = self.encode_state(state)
        a = self.action_to_embedding(action)
        return np.concatenate([s, a])

    # ==================== 前向计算 ====================

    def _epistemic_forward(self, x: np.ndarray) -> float:
        """
        认知价值网络前向传播

        f(x) = W2 * ReLU(W1 * x + b1) + b2

        Args:
            x: 联合输入向量 [state_dim + action_embed_dim]

        Returns:
            float: 认知价值
        """
        h = x @ self.W_epi_1 + self.b_epi_1
        h = np.maximum(0, h)  # ReLU
        out = float((h @ self.W_epi_2 + self.b_epi_2)[0])
        # 非线性映射到 [0, 1] 范围 (sigmoid)
        return 1.0 / (1.0 + math.exp(-out))

    def _pragmatic_forward(self, x: np.ndarray) -> float:
        """
        实用价值网络前向传播

        g(x) = W2 * tanh(W1 * x + b1) + b2

        Args:
            x: 联合输入向量 [state_dim + action_embed_dim]

        Returns:
            float: 实用价值
        """
        h = x @ self.W_prag_1 + self.b_prag_1
        h = np.tanh(h)  # tanh
        out = float((h @ self.W_prag_2 + self.b_prag_2)[0])
        # 非线性映射到 [0, 1] 范围
        return 1.0 / (1.0 + math.exp(-out))

    def compute_epistemic_value(
        self,
        state: dict[str, Any],
        action: str,
    ) -> float:
        """
        计算认知价值 (信息增益)

        替代 ActiveInferenceEngine.compute_epistemic_value() 的手工权重分配。
        从经验中学习每个动作在每种状态下能带来多少信息增益。

        Args:
            state: 当前市场状态
            action: 候选动作

        Returns:
            float: 认知价值 [0, 1]
        """
        x = self._compute_input(state, action)
        return self._epistemic_forward(x)

    def compute_pragmatic_value(
        self,
        state: dict[str, Any],
        action: str,
    ) -> float:
        """
        计算实用价值 (预期效用)

        替代 ActiveInferenceEngine.compute_pragmatic_value() 的固定风险溢价公式。
        从实际收益反馈中学习风险调整后的预期效用。

        Args:
            state: 当前市场状态
            action: 候选动作

        Returns:
            float: 实用价值 [0, 1]
        """
        x = self._compute_input(state, action)
        return self._pragmatic_forward(x)

    def compute_efe(
        self,
        state: dict[str, Any],
        action: str,
        exploration_bonus: float | None = None,
    ) -> float:
        """
        计算期望自由能 (Expected Free Energy)

        G(π) = -(EpistemicValue + PragmaticValue + ExplorationBonus)

        Args:
            state: 当前市场状态
            action: 候选动作
            exploration_bonus: 外部探索奖励 (None 则自动计算)

        Returns:
            float: EFE (越小越好)
        """
        epistemic = self.compute_epistemic_value(state, action)
        pragmatic = self.compute_pragmatic_value(state, action)
        bonus = self.compute_exploration_bonus(state, action) if exploration_bonus is None else exploration_bonus

        return -(epistemic + pragmatic + bonus)

    def compute_exploration_bonus(self, state: dict[str, Any], action: str) -> float:
        """
        可学习探索奖励

        替代 ActiveInferenceEngine.exploration_bonus() 的固定公式。
        探索奖励 = α * (1 / (1 + visits))

        其中 α 是可学习参数，从经验中调整探索-利用平衡。

        Args:
            state: 当前市场状态
            action: 候选动作

        Returns:
            float: 探索奖励附加项
        """
        signature = self._state_signature(state)
        state_visits = self._state_visitation.get(signature, 0)
        action_count = self._action_counts.get(action, 0)

        # 访问越少 → 探索奖励越高
        state_bonus = 1.0 / (1.0 + state_visits)
        action_bonus = 1.0 / (1.0 + action_count)

        # 可学习 α 系数
        alpha = math.exp(self.log_exploration_alpha)
        bonus = alpha * (0.6 * state_bonus + 0.4 * action_bonus)

        return max(0.0, min(1.0, bonus))

    def evaluate_action(
        self,
        action: str,
        state: dict[str, Any],
    ) -> dict[str, float]:
        """
        评估单个动作的完整 EFE 分解

        Args:
            action: 动作名称
            state: 当前市场状态

        Returns:
            Dict 包含 epistemic_value, pragmatic_value, exploration_bonus, expected_free_energy
        """
        epistemic = self.compute_epistemic_value(state, action)
        pragmatic = self.compute_pragmatic_value(state, action)
        bonus = self.compute_exploration_bonus(state, action)
        efe = self.compute_efe(state, action, exploration_bonus=bonus)

        return {
            "action": action,
            "epistemic_value": epistemic,
            "pragmatic_value": pragmatic,
            "exploration_bonus": bonus,
            "expected_free_energy": efe,
        }

    def select_action(
        self,
        candidate_actions: list[str],
        state: dict[str, Any],
    ) -> tuple[str, dict[str, float]]:
        """
        选择最小化 EFE 的动作

        Args:
            candidate_actions: 候选动作列表
            state: 当前市场状态

        Returns:
            (selected_action, efe_dict) 元组
        """
        evaluations = []
        for action in candidate_actions:
            efe_dict = self.evaluate_action(action, state)
            evaluations.append(efe_dict)

        # 按 EFE 升序排序 (越小越好)
        evaluations.sort(key=lambda e: e["expected_free_energy"])

        if not evaluations:
            return candidate_actions[0], {"expected_free_energy": 0.0}

        selected = evaluations[0]

        # 更新统计
        self._action_counts[selected["action"]] = self._action_counts.get(selected["action"], 0) + 1
        signature = self._state_signature(state)
        self._state_visitation[signature] = self._state_visitation.get(signature, 0) + 1

        return selected["action"], selected

    # ==================== 在线学习 ====================

    def update(
        self,
        state: dict[str, Any],
        action: str,
        reward: float,
        next_state: dict[str, Any],
        done: bool = False,
    ) -> dict[str, float]:
        """
        在线 TD 学习更新

        使用实际收益信号更新价值网络参数。
        TD(0): δ = r + γ * V(s') - V(s)

        Args:
            state: 当前状态
            action: 执行的动作
            reward: 实际收益
            next_state: 下一个状态
            done: 是否终止

        Returns:
            Dict 包含损失和 TD 误差
        """
        # 存储经验
        self._experience_buffer.append(
            {
                "state": state,
                "action": action,
                "reward": reward,
                "next_state": next_state,
                "done": done,
            },
        )

        # 计算 TD 目标
        x = self._compute_input(state, action)
        x_next = self._compute_input(next_state, action)

        # 当前价值
        current_epistemic = self._epistemic_forward(x)
        current_pragmatic = self._pragmatic_forward(x)

        # 下一状态价值 (bootstrap)
        next_epistemic = self._epistemic_forward(x_next)
        next_pragmatic = self._pragmatic_forward(x_next)

        # 总价值 = epistemic + pragmatic
        V_s = current_epistemic + current_pragmatic
        V_s_next = next_epistemic + next_pragmatic

        # TD 目标
        td_target = reward + (0.0 if done else self.gamma * V_s_next)

        # TD 误差
        td_error = td_target - V_s

        # ========== 梯度计算 (有限差分 + 解析混合) ==========
        # 对两个网络分别计算损失: L = δ² + L2
        # 这里使用简化的参数扰动梯度

        # 认知网络梯度 (epistemic 部分)
        eps = 1e-4

        # 更新认知价值网络
        grad_W_epi_1 = np.zeros_like(self.W_epi_1)
        grad_b_epi_1 = np.zeros_like(self.b_epi_1)
        grad_W_epi_2 = np.zeros_like(self.W_epi_2)
        grad_b_epi_2 = np.zeros_like(self.b_epi_2)

        # 有限差分: 认知网络参数扰动
        for name, param, grad in [
            ("W_epi_1", self.W_epi_1, grad_W_epi_1),
            ("b_epi_1", self.b_epi_1, grad_b_epi_1),
            ("W_epi_2", self.W_epi_2, grad_W_epi_2),
            ("b_epi_2", self.b_epi_2, grad_b_epi_2),
        ]:
            if param.size == 0:
                continue
            # SPSA 风格随机扰动
            delta = np.random.choice([-1, 1], size=param.shape) * eps
            param.flatten()
            delta.flatten()

            # 正向扰动
            param_plus = param + delta
            setattr(self, name, param_plus)
            epi_plus = self._epistemic_forward(x)
            loss_plus = (reward + self.gamma * V_s_next - (epi_plus + current_pragmatic)) ** 2

            # 负向扰动
            param_minus = param - delta
            setattr(self, name, param_minus)
            epi_minus = self._epistemic_forward(x)
            loss_minus = (reward + self.gamma * V_s_next - (epi_minus + current_pragmatic)) ** 2

            # 梯度 = (loss_plus - loss_minus) / (2 * eps) * delta_sign
            grad_approx = (loss_plus - loss_minus) / (2 * eps)
            grad[:] = (delta * grad_approx).reshape(grad.shape)

            # 恢复参数
            setattr(self, name, param)

        # 更新实用价值网络
        grad_W_prag_1 = np.zeros_like(self.W_prag_1)
        grad_b_prag_1 = np.zeros_like(self.b_prag_1)
        grad_W_prag_2 = np.zeros_like(self.W_prag_2)
        grad_b_prag_2 = np.zeros_like(self.b_prag_2)

        for name, param, grad in [
            ("W_prag_1", self.W_prag_1, grad_W_prag_1),
            ("b_prag_1", self.b_prag_1, grad_b_prag_1),
            ("W_prag_2", self.W_prag_2, grad_W_prag_2),
            ("b_prag_2", self.b_prag_2, grad_b_prag_2),
        ]:
            if param.size == 0:
                continue
            delta = np.random.choice([-1, 1], size=param.shape) * eps

            # 正向扰动
            param_plus = param + delta
            setattr(self, name, param_plus)
            prag_plus = self._pragmatic_forward(x)
            loss_plus = (reward + self.gamma * V_s_next - (current_epistemic + prag_plus)) ** 2

            # 负向扰动
            param_minus = param - delta
            setattr(self, name, param_minus)
            prag_minus = self._pragmatic_forward(x)
            loss_minus = (reward + self.gamma * V_s_next - (current_epistemic + prag_minus)) ** 2

            grad_approx = (loss_plus - loss_minus) / (2 * eps)
            grad[:] = (delta * grad_approx).reshape(grad.shape)

            setattr(self, name, param)

        # ========== L2 正则化梯度 ==========
        l2_grad_W_epi_1 = 2 * self.l2_reg * self.W_epi_1
        l2_grad_W_epi_2 = 2 * self.l2_reg * self.W_epi_2
        l2_grad_W_prag_1 = 2 * self.l2_reg * self.W_prag_1
        l2_grad_W_prag_2 = 2 * self.l2_reg * self.W_prag_2

        # ========== Adam 参数更新 ==========
        self.train_step += 1

        self.W_epi_1 += self.optimizer_epistemic.step("W_epi_1", grad_W_epi_1 - l2_grad_W_epi_1)
        self.b_epi_1 += self.optimizer_epistemic.step("b_epi_1", grad_b_epi_1)
        self.W_epi_2 += self.optimizer_epistemic.step("W_epi_2", grad_W_epi_2 - l2_grad_W_epi_2)
        self.b_epi_2 += self.optimizer_epistemic.step("b_epi_2", grad_b_epi_2)

        self.W_prag_1 += self.optimizer_pragmatic.step("W_prag_1", grad_W_prag_1 - l2_grad_W_prag_1)
        self.b_prag_1 += self.optimizer_pragmatic.step("b_prag_1", grad_b_prag_1)
        self.W_prag_2 += self.optimizer_pragmatic.step("W_prag_2", grad_W_prag_2 - l2_grad_W_prag_2)
        self.b_prag_2 += self.optimizer_pragmatic.step("b_prag_2", grad_b_prag_2)

        # 记录统计
        self.epistemic_history.append(current_epistemic)
        self.pragmatic_history.append(current_pragmatic)
        self.td_error_history.append(td_error)

        return {
            "td_error": float(td_error),
            "td_target": float(td_target),
            "current_epistemic": float(current_epistemic),
            "current_pragmatic": float(current_pragmatic),
            "train_step": self.train_step,
        }

    def train_on_experience(self, batch_size: int = 32) -> dict[str, float]:
        """
        从经验回放缓冲区批量训练

        Args:
            batch_size: 批次大小

        Returns:
            Dict 包含平均损失和 TD 误差
        """
        if len(self._experience_buffer) < batch_size:
            return {"batch_loss": 0.0, "batch_td": 0.0, "skipped": True}

        # 随机采样
        indices = np.random.choice(len(self._experience_buffer), batch_size, replace=False)
        total_loss = 0.0
        total_td = 0.0

        for idx in indices:
            exp = self._experience_buffer[idx]
            result = self.update(
                exp["state"],
                exp["action"],
                exp["reward"],
                exp["next_state"],
                exp.get("done", False),
            )
            total_loss += result["td_error"] ** 2
            total_td += abs(result["td_error"])

        return {
            "batch_loss": float(total_loss / batch_size),
            "batch_td": float(total_td / batch_size),
            "batch_size": batch_size,
            "buffer_size": len(self._experience_buffer),
            "skipped": False,
        }

    def update_exploration_alpha(self, td_error: float) -> None:
        """
        基于 TD 误差调整探索系数

        当 TD 误差大时，说明模型预测不准，应增加探索 (提高 α)；
        当 TD 误差小时，说明模型已较准确，可减少探索 (降低 α)。

        Args:
            td_error: 当前 TD 误差
        """
        # α 调整规则: α += lr * tanh(td_error) * (1 - α)
        alpha = math.exp(self.log_exploration_alpha)
        adjustment = math.tanh(td_error) * (1.0 - alpha)
        new_alpha = alpha + 0.01 * adjustment
        new_alpha = max(0.01, min(1.0, new_alpha))
        self.log_exploration_alpha = math.log(new_alpha)

    # ==================== 序列化 ====================

    def get_params_dict(self) -> dict[str, Any]:
        """获取所有可学习参数 (用于保存)"""
        return {
            "action_embeddings": self.action_embeddings.tolist(),
            "W_epi_1": self.W_epi_1.tolist(),
            "b_epi_1": self.b_epi_1.tolist(),
            "W_epi_2": self.W_epi_2.tolist(),
            "b_epi_2": self.b_epi_2.tolist(),
            "W_prag_1": self.W_prag_1.tolist(),
            "b_prag_1": self.b_prag_1.tolist(),
            "W_prag_2": self.W_prag_2.tolist(),
            "b_prag_2": self.b_prag_2.tolist(),
            "W_state_proj": self.W_state_proj.tolist(),
            "b_state_proj": self.b_state_proj.tolist(),
            "log_exploration_alpha": float(self.log_exploration_alpha),
            "train_step": self.train_step,
        }

    def load_params_dict(self, params: dict[str, Any]) -> None:
        """加载可学习参数 (从保存恢复)"""
        for key, val in params.items():
            if hasattr(self, key):
                if isinstance(val, list):
                    setattr(self, key, np.array(val))
                elif isinstance(val, (int, float)):
                    setattr(self, key, val)

    def save(self, path: str) -> None:
        """保存模型参数到 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_params_dict(), f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        """从 JSON 文件加载模型参数"""
        with open(path, encoding="utf-8") as f:
            params = json.load(f)
        self.load_params_dict(params)

    def get_statistics(self) -> dict[str, Any]:
        """获取评估器统计信息"""
        return {
            "train_step": self.train_step,
            "buffer_size": len(self._experience_buffer),
            "exploration_alpha": float(math.exp(self.log_exploration_alpha)),
            "avg_epistemic": float(np.mean(self.epistemic_history[-100:])) if self.epistemic_history else 0.0,
            "avg_pragmatic": float(np.mean(self.pragmatic_history[-100:])) if self.pragmatic_history else 0.0,
            "avg_td_error": float(np.mean(self.td_error_history[-100:])) if self.td_error_history else 0.0,
            "action_counts": dict(self._action_counts),
        }

    # ==================== SPSA 梯度计算 (供 HSR-MC 使用) ====================

    def _collect_params(self) -> dict[str, np.ndarray]:
        """收集所有可训练参数为 numpy 数组字典（供元学习使用）"""
        return {
            "W_epi_1": self.W_epi_1,
            "b_epi_1": self.b_epi_1,
            "W_epi_2": self.W_epi_2,
            "b_epi_2": self.b_epi_2,
            "W_prag_1": self.W_prag_1,
            "b_prag_1": self.b_prag_1,
            "W_prag_2": self.W_prag_2,
            "b_prag_2": self.b_prag_2,
            "action_embeddings": self.action_embeddings,
            "W_state_proj": self.W_state_proj,
            "b_state_proj": self.b_state_proj,
            "log_exploration_alpha": np.array([self.log_exploration_alpha]),
        }

    def _compute_gradient_spsa(
        self,
        loss_fn,
        params_dict: dict[str, np.ndarray],
        c: float = 1e-4,
        num_perturbations: int = 1,
    ) -> dict[str, np.ndarray]:
        """
        SPSA (Simultaneous Perturbation Stochastic Approximation) 梯度估计。

        核心公式:
            g_i(θ) ≈ (L(θ + c·Δ) - L(θ - c·Δ)) / (2c·Δ_i)

        其中 Δ 是随机扰动向量，每个分量独立采样自 {±1}。

        相比逐维有限差分 (FD)，SPSA 每次迭代仅需 2 次损失计算 (num_perturbations=1)，
        在参数维度 N 较大时比 FD 的 O(N) 次计算效率高得多。

        Args:
            loss_fn:    Callable[[Dict[str, np.ndarray]], float]
                        接受扰动参数字典，返回标量损失值
            params_dict: 参数字典 {名称: 参数值}
            c:           扰动步长
            num_perturbations: SPSA 扰动次数 (平均以降低方差, 默认 1)

        Returns:
            Dict[str, np.ndarray]: 梯度字典，结构与 params_dict 一致
        """
        grads = {name: np.zeros_like(param) for name, param in params_dict.items()}

        for _ in range(num_perturbations):
            # 为每个参数生成同步随机扰动 Δ ∈ {±1}
            delta = {}
            for name, param in params_dict.items():
                delta[name] = np.random.choice([-1, 1], size=param.shape).astype(param.dtype)

            # 正向扰动: θ + c·Δ
            params_plus = {name: param + c * delta[name] for name, param in params_dict.items()}
            loss_plus = loss_fn(params_plus)

            # 负向扰动: θ - c·Δ
            params_minus = {name: param - c * delta[name] for name, param in params_dict.items()}
            loss_minus = loss_fn(params_minus)

            # SPSA 梯度: (L⁺ - L⁻) / (2c·Δ_i)
            delta_loss = loss_plus - loss_minus
            for name in params_dict:
                grads[name] += (delta_loss / (2.0 * c)) * (1.0 / (delta[name] + 1e-12))

        if num_perturbations > 1:
            for name in grads:
                grads[name] /= num_perturbations

        return grads

    def reset(self) -> None:
        """重置运行时状态 (保留可学习参数)"""
        self._state_visitation.clear()
        self._action_counts = dict.fromkeys(self.ACTIONS, 0)
        self._experience_buffer.clear()
        self.epistemic_history.clear()
        self.pragmatic_history.clear()
        self.td_error_history.clear()


# ==================== NumPy Adam 优化器 (内部) ====================


class _AdamOptimizer:
    """
    NumPy 实现的 Adam 优化器 (与 RSSM 的 AdamOptimizer 功能一致)
    用于可学习 EFE 评估器的参数更新。
    """

    def __init__(self, lr: float = 1e-3, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m: dict[str, np.ndarray] = {}
        self.v: dict[str, np.ndarray] = {}
        self.t: int = 0

    def step(self, param_name: str, grad: np.ndarray) -> np.ndarray:
        """
        计算 Adam 参数更新量

        Args:
            param_name: 参数名称 (用于跟踪动量)
            grad: 梯度

        Returns:
            np.ndarray: 参数更新量 (需加到参数上)
        """
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
        """重置优化器状态"""
        self.m.clear()
        self.v.clear()
        self.t = 0
