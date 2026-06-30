# TradingAgents/l_iwm/rssm_world_model.py
"""
RSSM 可学习世界模型 (Recurrent State Space Model)
=================================================

理论基础: Hafner et al. 2023 DreamerV3 (ICLR 2023)

替代当前 hpc_loop/generative_model.py 中的硬编码预测函数（如 _predicted_price_change
使用 {"bull": 0.005, "bear": -0.005} 的硬编码映射）。

核心创新:
    1. Encoder: 市场观测 → 确定性隐状态 h (MLP)
    2. RSSM: GRU 驱动的隐动态 + 随机状态 z_t (先验/后验)
    3. Decoder: 隐状态 → 观测重建 (用于预测)
    4. Reward Predictor: 隐状态 → 预期收益
    5. 全部使用 NumPy 手动实现，无外部深度学习依赖

数学公式:
    h_t = GRU(h_{t-1}, z_{t-1}, a_{t-1}, x_t)   # 确定性状态
    z_t_prior ~ N(μ_prior(h_t), σ_prior(h_t))   # 随机状态（先验）
    z_t_post ~ N(μ_post(h_t, x_t), σ_post(h_t, x_t))  # 随机状态（后验）
    x̂_t = Decoder(h_t, z_t)                     # 观测重建
    r̂_t = RewardPredictor(h_t, z_t)             # 收益预测
"""

import json
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

# ==================== NumPy Adam 优化器 ====================


class AdamOptimizer:
    """NumPy 实现的 Adam 优化器"""

    def __init__(self, lr: float = 3e-4, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m = {}
        self.v = {}
        self.t = 0

    def step(self, param_name: str, grad: np.ndarray) -> np.ndarray:
        """返回更新后的参数值"""
        if param_name not in self.m:
            self.m[param_name] = np.zeros_like(grad)
            self.v[param_name] = np.zeros_like(grad)

        self.t += 1
        self.m[param_name] = self.beta1 * self.m[param_name] + (1 - self.beta1) * grad
        self.v[param_name] = self.beta2 * self.v[param_name] + (1 - self.beta2) * (grad**2)

        m_hat = self.m[param_name] / (1 - self.beta1**self.t)
        v_hat = self.v[param_name] / (1 - self.beta2**self.t)

        return -self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def reset(self):
        self.m.clear()
        self.v.clear()
        self.t = 0


# ==================== 工具函数 ====================


def he_init(fan_in: int, fan_out: int) -> np.ndarray:
    """He 正态初始化"""
    std = math.sqrt(2.0 / fan_in)
    return np.random.randn(fan_in, fan_out) * std


def glorot_init(fan_in: int, fan_out: int) -> np.ndarray:
    """Glorot (Xavier) 正态初始化"""
    std = math.sqrt(2.0 / (fan_in + fan_out))
    return np.random.randn(fan_in, fan_out) * std


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """数值稳定的 softmax"""
    x_max = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - x_max)
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


def calculate_kl_divergence(mean_p, std_p, mean_q, std_q):
    """计算两个高斯分布之间的 KL 散度
    KL(N(μ_p,σ_p) || N(μ_q,σ_q))
    """
    var_p = std_p**2
    var_q = std_q**2
    kl = np.log(std_q / std_p) + (var_p + (mean_p - mean_q) ** 2) / (2 * var_q) - 0.5
    return np.sum(kl, axis=-1, keepdims=True)


@dataclass
class MarketPrediction:
    """与 hpc_loop/hpc_state.py MarketPrediction 兼容的预测结果"""

    price_prediction: dict[str, float] = field(default_factory=dict)
    volatility_prediction: dict[str, float] = field(default_factory=dict)
    sentiment_prediction: dict[str, float] = field(default_factory=dict)
    macro_prediction: dict[str, Any] = field(default_factory=dict)
    tick_prediction: dict[str, float] = field(default_factory=dict)
    minute_prediction: dict[str, float] = field(default_factory=dict)
    daily_prediction: dict[str, float] = field(default_factory=dict)
    weekly_prediction: dict[str, float] = field(default_factory=dict)
    monthly_prediction: dict[str, float] = field(default_factory=dict)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    timestamp: str = ""
    latent_state: dict[str, Any] | None = None


class RSSMWorldModel:
    """
    RSSM 可学习世界模型 — 替代 MarketGenerativeModel 的硬编码预测。

    核心组件:
    1. Encoder: 市场观测 → 初始隐状态
    2. RSSM 核心: GRU + 先验/后验网络
    3. Decoder: (h, z) → 观测重建
    4. Reward Predictor: (h, z) → 预期收益
    5. Continue Predictor: (h, z) → episode 是否结束

    使用 NumPy 手动实现所有矩阵运算，无 PyTorch 依赖。
    """

    def __init__(self, config, input_dim: int = 20):
        """
        Args:
            config: LIWMConfig 实例
            input_dim: 输入观测维度 (技术指标特征数)
        """
        self.input_dim = input_dim
        self.latent_dim = config.rssm_latent_dim  # 32
        self.hidden_dim = config.rssm_hidden_dim  # 256
        self.stochastic_dim = config.rssm_stochastic_dim  # 32
        self.learning_rate = config.rssm_learning_rate  # 3e-4
        self.kl_beta = config.rssm_kl_beta  # 0.1

        # 动作嵌入维度 (买入/持有/卖出 + 数据收集)
        self.action_dim = 8

        # 组合隐状态维度
        self.state_dim = self.hidden_dim + self.stochastic_dim  # 256 + 32 = 288

        # Adam 优化器
        self.optimizer = AdamOptimizer(lr=self.learning_rate)

        # 经验回放缓冲区
        self.replay_buffer = deque(maxlen=config.rssm_buffer_size)

        # 训练步数计数器
        self.train_step = 0

        # 初始化所有权重
        self._init_weights()

        # 保存最后隐状态
        self._last_h = None
        self._last_z = None

    def _init_weights(self):
        """He/Glorot 初始化所有可学习参数"""
        d = self.input_dim
        h = self.hidden_dim
        z = self.stochastic_dim
        a = self.action_dim

        # ===== Encoder: x → h_init =====
        self.W_enc = he_init(d, h)  # (d, h)
        self.b_enc = np.zeros(h)  # (h,)

        # ===== GRU 参数 =====
        # 输入: x (d) + z (z) + a (a) → combined input
        # GRU 有三个门: z (update), r (reset), h (candidate)
        # 将三个门的权重合并为一个矩阵 (3*h, input_dim) 以提高效率
        gru_input_dim = d + z + a
        self.W_gru_z = glorot_init(gru_input_dim, h)  # (d+z+a, h)
        self.W_gru_r = glorot_init(gru_input_dim, h)
        self.W_gru_h = glorot_init(gru_input_dim, h)
        self.U_gru_z = glorot_init(h, h)  # 隐状态-隐状态权重
        self.U_gru_r = glorot_init(h, h)
        self.U_gru_h = glorot_init(h, h)
        self.b_gru_z = np.zeros(h)
        self.b_gru_r = np.zeros(h)
        self.b_gru_h = np.zeros(h)

        # ===== 先验网络 p(z | h) =====
        self.W_prior_mean = he_init(h, z)
        self.b_prior_mean = np.zeros(z)
        self.W_prior_std = he_init(h, z)
        self.b_prior_std = np.zeros(z)

        # ===== 后验网络 q(z | h, x) =====
        self.W_post_mean = he_init(h + d, z)
        self.b_post_mean = np.zeros(z)
        self.W_post_std = he_init(h + d, z)
        self.b_post_std = np.zeros(z)

        # ===== Decoder: (h, z) → x̂ =====
        self.W_dec = he_init(h + z, d)
        self.b_dec = np.zeros(d)

        # ===== Reward Predictor: (h, z) → r̂ =====
        self.W_reward_mean = he_init(h + z, 1)
        self.b_reward_mean = np.zeros(1)

        # ===== Continue Predictor: (h, z) → cont̂ (sigmoid) =====
        self.W_continue = he_init(h + z, 1)
        self.b_continue = np.zeros(1)

    # ==================== 前向传播 ====================

    def encode(self, observation: np.ndarray) -> np.ndarray:
        """
        编码观测到初始隐状态。

        Args:
            observation: (batch, input_dim) 或 (input_dim,)

        Returns:
            h: (batch, hidden_dim) 或 (hidden_dim,)
        """
        single = observation.ndim == 1
        if single:
            observation = observation.reshape(1, -1)

        h = observation @ self.W_enc + self.b_enc
        h = np.tanh(h)

        if single:
            h = h[0]
        return h

    def gru_step(self, h_prev: np.ndarray, x_t: np.ndarray) -> np.ndarray:
        """
        GRU 单元前向传播。

        Args:
            h_prev: (batch, hidden_dim) 上一隐状态
            x_t: (batch, input_dim + z_dim + action_dim) 当前输入

        Returns:
            h_new: (batch, hidden_dim) 新隐状态
        """
        # Update gate
        z_t = x_t @ self.W_gru_z + h_prev @ self.U_gru_z + self.b_gru_z
        z_t = 1.0 / (1.0 + np.exp(-z_t))  # sigmoid

        # Reset gate
        r_t = x_t @ self.W_gru_r + h_prev @ self.U_gru_r + self.b_gru_r
        r_t = 1.0 / (1.0 + np.exp(-r_t))  # sigmoid

        # Candidate hidden state
        h_candidate = x_t @ self.W_gru_h + (r_t * h_prev) @ self.U_gru_h + self.b_gru_h
        h_candidate = np.tanh(h_candidate)

        # New hidden state
        h_new = (1 - z_t) * h_prev + z_t * h_candidate

        return h_new

    def _sample_gaussian(self, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
        """重参数化采样: z = mean + std * eps"""
        eps = np.random.randn(*mean.shape).astype(np.float64)
        return mean + std * eps

    def rssm_step(self, h_prev: np.ndarray, z_prev: np.ndarray, action: np.ndarray, observation: np.ndarray) -> tuple:
        """
        单步 RSSM 前向传播。

        Args:
            h_prev: (batch, hidden_dim) 上一确定性状态
            z_prev: (batch, stochastic_dim) 上一随机状态
            action: (batch, action_dim) 当前动作嵌入
            observation: (batch, input_dim) 当前观测

        Returns:
            h_new: (batch, hidden_dim)
            z_prior: (batch, stochastic_dim) 先验随机状态
            z_post: (batch, stochastic_dim) 后验随机状态
            x_recon: (batch, input_dim) 重建观测
            prior_mean: 先验均值
            prior_std: 先验标准差
            post_mean: 后验均值
            post_std: 后验标准差
        """
        observation.shape[0]

        # === Step 1: GRU 更新 (确定性状态) ===
        # 拼接输入: [obs, z_prev, action]
        gru_input = np.concatenate([observation, z_prev, action], axis=-1)
        h_new = self.gru_step(h_prev, gru_input)

        # === Step 2: 先验 p(z_t | h_t) ===
        prior_mean = h_new @ self.W_prior_mean + self.b_prior_mean
        prior_std = h_new @ self.W_prior_std + self.b_prior_std
        prior_std = np.exp(prior_std * 0.5)  # 转换为标准差 (对数方差 → 标准差)
        prior_std = np.clip(prior_std, 0.1, 1.0)

        # === Step 3: 后验 q(z_t | h_t, x_t) ===
        post_input = np.concatenate([h_new, observation], axis=-1)
        post_mean = post_input @ self.W_post_mean + self.b_post_mean
        post_std = post_input @ self.W_post_std + self.b_post_std
        post_std = np.exp(post_std * 0.5)
        post_std = np.clip(post_std, 0.1, 1.0)

        # === Step 4: 采样随机状态 ===
        z_prior = self._sample_gaussian(prior_mean, prior_std)
        z_post = self._sample_gaussian(post_mean, post_std)

        # === Step 5: 重建观测 ===
        dec_input = np.concatenate([h_new, z_post], axis=-1)
        x_recon = dec_input @ self.W_dec + self.b_dec

        return h_new, z_prior, z_post, x_recon, prior_mean, prior_std, post_mean, post_std

    def compute_loss(self, h, z, observation, reward, done, prior_mean, prior_std, post_mean, post_std, x_recon):
        """
        计算联合损失:
        L = L_recon + β * L_KL + L_reward + L_continue

        Args:
            均为批数据

        Returns:
            dict: 损失分量
        """
        observation.shape[0]

        # === 1. 观测重建损失 (MSE) ===
        recon_loss = 0.5 * np.mean((x_recon - observation) ** 2)

        # === 2. KL 散度 (先验 vs 后验) ===
        kl_loss = np.mean(calculate_kl_divergence(post_mean, post_std, prior_mean, prior_std))
        # KL 平衡: 使用 kl_beta 加权
        kl_loss = self.kl_beta * kl_loss

        # === 3. 收益预测损失 (MSE) ===
        dec_input = np.concatenate([h, z], axis=-1)
        reward_pred = dec_input @ self.W_reward_mean + self.b_reward_mean
        reward_pred = reward_pred.squeeze(-1)
        reward_loss = 0.5 * np.mean((reward_pred - reward) ** 2)

        # === 4. Continue 预测损失 (BCE) ===
        cont_logits = dec_input @ self.W_continue + self.b_continue
        cont_logits = cont_logits.squeeze(-1)
        # 二分类交叉熵
        cont_loss = np.mean(
            -done * np.log(1.0 / (1.0 + np.exp(-cont_logits)) + 1e-8)
            - (1 - done) * np.log(1.0 - 1.0 / (1.0 + np.exp(-cont_logits)) + 1e-8),
        )

        total_loss = recon_loss + kl_loss + reward_loss + cont_loss

        return {
            "total_loss": total_loss,
            "recon_loss": recon_loss,
            "kl_loss": kl_loss,
            "reward_loss": reward_loss,
            "cont_loss": cont_loss,
        }

    def update(self, batch: dict[str, np.ndarray]) -> dict[str, float]:
        """
        使用 SGD (Adam) 更新所有参数。

        Args:
            batch: {
                "observations": (batch, seq_len, input_dim),
                "actions": (batch, seq_len, action_dim),
                "rewards": (batch, seq_len),
                "dones": (batch, seq_len),
            }

        Returns:
            Dict: 损失分量
        """
        obs = batch["observations"]
        actions = batch["actions"]
        rewards = batch["rewards"]
        dones = batch["dones"]

        batch_size, seq_len, _ = obs.shape

        # === 前向传播收集序列 ===
        h = np.zeros((batch_size, self.hidden_dim))
        z = np.zeros((batch_size, self.stochastic_dim))

        h_all, z_all = [], []
        prior_means, prior_stds = [], []
        post_means, post_stds = [], []
        x_recons = []

        for t in range(seq_len):
            obs_t = obs[:, t, :]
            act_t = actions[:, t, :]

            h, _z_prior, z_post, x_recon, pm, ps, qm, qs = self.rssm_step(h, z, act_t, obs_t)
            # 使用后验 z 作为下一时间步的输入
            z = z_post

            h_all.append(h)
            z_all.append(z)
            prior_means.append(pm)
            prior_stds.append(ps)
            post_means.append(qm)
            post_stds.append(qs)
            x_recons.append(x_recon)

        # 堆叠
        h_stack = np.stack(h_all, axis=1)  # (B, T, H)
        z_stack = np.stack(z_all, axis=1)  # (B, T, Z)
        pm_stack = np.stack(prior_means, axis=1)
        ps_stack = np.stack(prior_stds, axis=1)
        qm_stack = np.stack(post_means, axis=1)
        qs_stack = np.stack(post_stds, axis=1)
        xr_stack = np.stack(x_recons, axis=1)

        # === 计算损失 ===
        losses = self.compute_loss(
            h_stack.reshape(-1, self.hidden_dim),
            z_stack.reshape(-1, self.stochastic_dim),
            obs.reshape(-1, self.input_dim),
            rewards.reshape(-1),
            dones.reshape(-1),
            pm_stack.reshape(-1, self.stochastic_dim),
            ps_stack.reshape(-1, self.stochastic_dim),
            qm_stack.reshape(-1, self.stochastic_dim),
            qs_stack.reshape(-1, self.stochastic_dim),
            xr_stack.reshape(-1, self.input_dim),
        )

        # === 反向传播 (有限差分梯度近似) ===
        # 使用中心差分法计算每个参数的梯度：
        #   ∂L/∂θ_i ≈ (L(θ + ε·e_i) - L(θ - ε·e_i)) / (2ε)
        # 对每个参数随机采样 min(N, 100) 个维度以控制计算成本
        # 注意：这是在无 PyTorch/JAX autograd 条件下的实用替代方案

        # 构造 loss_fn 闭包：接受扰动参数名→扰动值，重跑前向传播
        obs_ref, actions_ref, rewards_ref, dones_ref = obs, actions, rewards, dones

        def loss_fn(**perturbed):
            saved = {}
            for pname, pval in perturbed.items():
                saved[pname] = getattr(self, pname)
                setattr(self, pname, pval)

            # 重跑完整前向传播
            h_ = np.zeros((batch_size, self.hidden_dim))
            z_ = np.zeros((batch_size, self.stochastic_dim))
            h_all_, z_all_ = [], []
            pm_all_, ps_all_ = [], []
            qm_all_, qs_all_ = [], []
            xr_all_ = []

            for t in range(seq_len):
                ot = obs_ref[:, t, :]
                at = actions_ref[:, t, :]
                h_, z_prior_, z_post_, x_recon_, pm_, ps_, qm_, qs_ = self.rssm_step(h_, z_, at, ot)
                z_ = z_post_
                h_all_.append(h_)
                z_all_.append(z_)
                pm_all_.append(pm_)
                ps_all_.append(ps_)
                qm_all_.append(qm_)
                qs_all_.append(qs_)
                xr_all_.append(x_recon_)

            loss_result = self.compute_loss(
                np.stack(h_all_, axis=1).reshape(-1, self.hidden_dim),
                np.stack(z_all_, axis=1).reshape(-1, self.stochastic_dim),
                obs_ref.reshape(-1, self.input_dim),
                rewards_ref.reshape(-1),
                dones_ref.reshape(-1),
                np.stack(pm_all_, axis=1).reshape(-1, self.stochastic_dim),
                np.stack(ps_all_, axis=1).reshape(-1, self.stochastic_dim),
                np.stack(qm_all_, axis=1).reshape(-1, self.stochastic_dim),
                np.stack(qs_all_, axis=1).reshape(-1, self.stochastic_dim),
                np.stack(xr_all_, axis=1).reshape(-1, self.input_dim),
            )

            # 恢复原始参数
            for pname, pval in saved.items():
                setattr(self, pname, pval)

            return loss_result["total_loss"]

        params_dict = self._get_params_dict()
        grads = self._compute_gradients_fd(loss_fn, params_dict, epsilon=1e-5)

        # === Adam 参数更新 ===
        self.train_step += 1
        self._apply_gradients(grads)

        return {k: float(v) for k, v in losses.items()}

    def _get_params_dict(self) -> dict[str, np.ndarray]:
        """收集所有可训练参数字典（供有限差分梯度计算使用）"""
        return {
            "W_enc": self.W_enc,
            "b_enc": self.b_enc,
            "W_gru_z": self.W_gru_z,
            "W_gru_r": self.W_gru_r,
            "W_gru_h": self.W_gru_h,
            "U_gru_z": self.U_gru_z,
            "U_gru_r": self.U_gru_r,
            "U_gru_h": self.U_gru_h,
            "b_gru_z": self.b_gru_z,
            "b_gru_r": self.b_gru_r,
            "b_gru_h": self.b_gru_h,
            "W_prior_mean": self.W_prior_mean,
            "b_prior_mean": self.b_prior_mean,
            "W_prior_std": self.W_prior_std,
            "b_prior_std": self.b_prior_std,
            "W_post_mean": self.W_post_mean,
            "b_post_mean": self.b_post_mean,
            "W_post_std": self.W_post_std,
            "b_post_std": self.b_post_std,
            "W_dec": self.W_dec,
            "b_dec": self.b_dec,
            "W_reward_mean": self.W_reward_mean,
            "b_reward_mean": self.b_reward_mean,
            "W_continue": self.W_continue,
            "b_continue": self.b_continue,
        }

    def _compute_gradients_fd(self, loss_fn, params_dict, epsilon=1e-5):
        """
        有限差分梯度近似 (Finite Difference)。

        对每个参数随机采样 min(N, 100) 个维度，使用中心差分：
            ∂L/∂θ_i ≈ (L(θ + ε·e_i) - L(θ - ε·e_i)) / (2ε)

        Args:
            loss_fn: 接受 perturbed 关键字参数，返回标量损失
            params_dict: {参数名: 参数值} 字典
            epsilon: 扰动步长

        Returns:
            Dict[str, np.ndarray]: 梯度字典
        """
        rng = np.random.RandomState(self.train_step if hasattr(self, "train_step") else 42)
        grads = {}

        for name, param in params_dict.items():
            grad = np.zeros_like(param)
            param_flat = param.flatten()
            n_dims = len(param_flat)
            n_samples = min(n_dims, 100)

            if n_dims == 0:
                grads[name] = grad
                continue

            # 随机采样维度索引
            sampled_indices = rng.choice(n_dims, size=n_samples, replace=False)

            for idx in sampled_indices:
                # 构造单位方向向量 e_d
                e_d = np.zeros(n_dims, dtype=param.dtype)
                e_d[idx] = 1.0
                e_d = e_d.reshape(param.shape)

                # 中心差分: L(θ + ε·e_d) - L(θ - ε·e_d) / (2ε)
                loss_plus = loss_fn(**{name: param + epsilon * e_d})
                loss_minus = loss_fn(**{name: param - epsilon * e_d})

                grad_flat = grad.flatten()
                grad_flat[idx] = (loss_plus - loss_minus) / (2.0 * epsilon)

            grads[name] = grad

        return grads

    def _apply_gradients(self, grads: dict[str, np.ndarray]):
        """应用 Adam 梯度更新"""
        for name, grad in grads.items():
            update = self.optimizer.step(name, grad)
            param = getattr(self, name)
            setattr(self, name, param + update)

    # ==================== 公共 API ====================

    def predict(self, state: dict[str, Any], num_steps: int = 5) -> list[MarketPrediction]:
        """
        基于当前隐状态预测未来多步市场状态。
        替代 generative_model.py 中 _predicted_price_change() 的硬编码 ±0.5% 预测。

        Args:
            state: 包含 "h" (hidden) 和 "z" (stochastic) 的字典
            num_steps: 预测步数

        Returns:
            List[MarketPrediction]: 多步预测结果
        """
        h = state.get("h", self._last_h)
        z = state.get("z", self._last_z)

        if h is None:
            h = np.zeros(self.hidden_dim)
        if z is None:
            z = np.zeros(self.stochastic_dim)

        predictions = []
        # 假设默认无操作动作
        null_action = np.zeros(self.action_dim)

        for _ in range(num_steps):
            # RSSM 前向 (先验模式, 无观测更新)
            # 在预测模式下不使用观测，仅用先验
            prior_mean = h @ self.W_prior_mean + self.b_prior_mean
            prior_std = h @ self.W_prior_std + self.b_prior_std
            prior_std = np.exp(prior_std * 0.5)
            prior_std = np.clip(prior_std, 0.1, 1.0)
            z = self._sample_gaussian(prior_mean[np.newaxis, :], prior_std[np.newaxis, :])[0]

            # GRU 步进
            gru_input = np.concatenate(
                [
                    np.zeros(self.input_dim),  # 无观测
                    z,
                    null_action,
                ],
                axis=-1,
            )[np.newaxis, :]

            # 手动 GRU 步进
            h_prev = h[np.newaxis, :] if h.ndim == 1 else h
            z_t = gru_input @ self.W_gru_z + h_prev @ self.U_gru_z + self.b_gru_z
            z_t = 1.0 / (1.0 + np.exp(-z_t))
            r_t = gru_input @ self.W_gru_r + h_prev @ self.U_gru_r + self.b_gru_r
            r_t = 1.0 / (1.0 + np.exp(-r_t))
            h_candidate = gru_input @ self.W_gru_h + (r_t * h_prev) @ self.U_gru_h + self.b_gru_h
            h_candidate = np.tanh(h_candidate)
            h_new = ((1 - z_t) * h_prev + z_t * h_candidate)[0]
            h = h_new

            # 重建预测
            dec_input = np.concatenate([h, z])[np.newaxis, :]
            x_pred = (dec_input @ self.W_dec + self.b_dec)[0]

            # 收益预测
            reward_pred = float((dec_input @ self.W_reward_mean + self.b_reward_mean)[0, 0])

            # 构造 MarketPrediction（兼容格式）
            pred = MarketPrediction(
                price_prediction={
                    "mean": float(x_pred[0] if self.input_dim > 0 else 0.0),
                    "lower": float(x_pred[0] - 0.02 if self.input_dim > 0 else -0.02),
                    "upper": float(x_pred[0] + 0.02 if self.input_dim > 0 else 0.02),
                },
                volatility_prediction={
                    "mean": float(x_pred[2] if self.input_dim > 2 else 0.015),
                    "lower": float(x_pred[2] * 0.5 if self.input_dim > 2 else 0.005),
                    "upper": float(x_pred[2] * 1.5 if self.input_dim > 2 else 0.03),
                },
                sentiment_prediction={
                    "mean": float(x_pred[1] if self.input_dim > 1 else 0.0),
                },
                confidence_scores={
                    "price": 0.8,
                    "volatility": 0.7,
                    "overall": 0.75,
                },
                macro_prediction={},
                timestamp=datetime.now().isoformat(),
                latent_state={"h": h, "z": z, "reward_pred": reward_pred},
            )
            predictions.append(pred)

        # 保存最后状态
        self._last_h = h
        self._last_z = z

        return predictions

    def get_latent_state(self) -> dict[str, Any]:
        """获取当前隐状态 (兼容 MarketGenerativeModel API)"""
        return {
            "h": self._last_h,
            "z": self._last_z,
            "train_step": self.train_step,
        }

    def store_experience(
        self, observation: np.ndarray, action: np.ndarray, reward: float, next_observation: np.ndarray, done: bool,
    ):
        """存储经验到回放缓冲区"""
        self.replay_buffer.append(
            {
                "obs": observation,
                "action": action,
                "reward": reward,
                "next_obs": next_observation,
                "done": done,
            },
        )

    def train_on_replay(self, batch_size: int = 32, seq_len: int = 8) -> dict[str, float]:
        """从回放缓冲区采样一个批次并训练"""
        if len(self.replay_buffer) < batch_size * seq_len:
            return {"total_loss": 0.0, "skipped": True}

        # 随机采样序列
        buffer = list(self.replay_buffer)
        indices = np.random.choice(len(buffer) - seq_len, batch_size)

        obs_seq = []
        act_seq = []
        rew_seq = []
        done_seq = []

        for idx in indices:
            obs_seq.append(np.stack([buffer[i]["obs"] for i in range(idx, idx + seq_len)]))
            act_seq.append(np.stack([buffer[i]["action"] for i in range(idx, idx + seq_len)]))
            rew_seq.append([buffer[i]["reward"] for i in range(idx, idx + seq_len)])
            done_seq.append([buffer[i]["done"] for i in range(idx, idx + seq_len)])

        batch = {
            "observations": np.stack(obs_seq),
            "actions": np.stack(act_seq),
            "rewards": np.array(rew_seq),
            "dones": np.array(done_seq, dtype=np.float64),
        }

        losses = self.update(batch)
        return losses

    def save(self, path: str):
        """保存模型参数"""
        params = {}
        for attr_name in dir(self):
            if attr_name.startswith(("W_", "b_", "U_")):
                param = getattr(self, attr_name)
                if isinstance(param, np.ndarray):
                    params[attr_name] = param.tolist()
        params["train_step"] = self.train_step
        with open(path, "w") as f:
            json.dump(params, f, indent=2, ensure_ascii=False)

    def load(self, path: str):
        """加载模型参数"""
        with open(path) as f:
            params = json.load(f)
        for attr_name, value in params.items():
            if attr_name == "train_step":
                self.train_step = value
            else:
                setattr(self, attr_name, np.array(value))
