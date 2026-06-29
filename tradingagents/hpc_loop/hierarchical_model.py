"""
Hierarchical Multi-Scale Generative Model
===========================================
多尺度分层生成模型 — 替换单层 MLP，引入层次化时间尺度处理。

基于 VERSES GENESIS 的分层 Active Inference 架构设计。

架构:
```
Level 3 (策略层 - 周/月):  P(L3_t | L3_{t-1}, L2_t)
Level 2 (模式层 - 日):    P(L2_t | L2_{t-1}, L1_t)
Level 1 (微观层 - 分钟/小时): P(L1_t | L1_{t-1}, L0_t)
Level 0 (原始数据层 - tick): P(L0_t | data_t)
```

每层之间有自上而下的预测和自下而上的预测误差传播。

理论基础:
    - Friston, K. (2008). Hierarchical models in the brain.
    - Parr, T. & Friston, K. (2019). Generalised free energy and active inference.
    - VERSES GENESIS: https://github.com/VERSES/GENESIS
"""

import logging
import os  # [R2 Fix M3] JAX fork-safety 依赖 os.environ
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

# [R2 Fix M3] JAX 线程安全防护：提前设 JAX_PLATFORM_NAME 防止 fork()+JAX 线程池死锁
if os.environ.get("JAX_PLATFORM_NAME") is None:
    os.environ["JAX_PLATFORM_NAME"] = ""

try:
    import jax
    import jax.numpy as jnp
    from jax import grad, jit, lax, random, vmap
    from jax.nn import sigmoid, softmax

    _JAX_AVAILABLE = True
except ImportError:
    _JAX_AVAILABLE = False
    jnp = None
    jax = None
    random = None
    vmap = None
    softmax = None

logger = logging.getLogger("hpc_loop.hierarchical")


# ====================================================================
# 1. TimeScale 枚举
# ====================================================================


class TimeScale(Enum):
    """时间尺度枚举，对应4层金字塔的不同处理粒度"""

    TICK = "tick"  # Level 0: 原始 tick 数据
    MINUTE = "minute"  # Level 1: 分钟/小时级
    HOUR = "hour"  # Level 1-2 过渡
    DAY = "day"  # Level 2: 日级模式
    WEEK = "week"  # Level 3: 周级策略
    MONTH = "month"  # Level 3 扩展

    @property
    def temporal_horizon(self) -> int:
        """返回该时间尺度对应的默认步数窗口"""
        mapping = {
            TimeScale.TICK: 1,
            TimeScale.MINUTE: 60,
            TimeScale.HOUR: 24,
            TimeScale.DAY: 30,
            TimeScale.WEEK: 4,
            TimeScale.MONTH: 12,
        }
        return mapping.get(self, 1)

    @property
    def precision_weight(self) -> float:
        """默认精度权重 — 越高层的先验越强（更慢的更新速率）"""
        mapping = {
            TimeScale.TICK: 0.3,
            TimeScale.MINUTE: 0.5,
            TimeScale.HOUR: 0.7,
            TimeScale.DAY: 0.8,
            TimeScale.WEEK: 0.9,
            TimeScale.MONTH: 0.95,
        }
        return mapping.get(self, 0.5)


# ====================================================================
# 2. LayerConfig 数据类
# ====================================================================


@dataclass
class LayerConfig:
    """每层的配置信息

    Args:
        name: 层名称 (如 "micro", "meso", "macro", "strategic")
        latent_dim: 该层潜变量维度
        time_scale: 该层处理的时间尺度
        temporal_precision: 该层的时间精度权重（对应FEP中的精度加权）
        use_nonlinear: 是否使用非线性 MLP 变换（默认 True）
        hidden_dim: 如果使用 MLP，隐藏层维度（默认 latent_dim * 2）
    """

    name: str
    latent_dim: int
    time_scale: TimeScale = TimeScale.TICK
    temporal_precision: float = 0.5
    use_nonlinear: bool = True
    hidden_dim: int | None = None

    def __post_init__(self):
        if self.hidden_dim is None:
            self.hidden_dim = self.latent_dim * 2
        if self.temporal_precision is None:
            self.temporal_precision = self.time_scale.precision_weight


# ====================================================================
# 辅助函数: 参数初始化
# ====================================================================


def _init_layer_params(
    key: jnp.ndarray,
    layer_idx: int,
    config: LayerConfig,
    upper_dim: int | None = None,
) -> dict[str, jnp.ndarray]:
    """初始化单层所有可学习参数

    Args:
        key: JAX 随机种子
        layer_idx: 层索引
        config: 层配置
        upper_dim: 上层 latent_dim (None 表示最高层)

    Returns:
        dict 包含该层的所有参数
    """
    if not _JAX_AVAILABLE:
        return {}

    d = config.latent_dim

    params = {}

    # A_self[l]: 自身转移矩阵 (latent_dim × latent_dim)
    k, subkey = random.split(key)
    params["A_self"] = random.normal(subkey, (d, d)) * 0.01

    # b[l]: 偏置向量
    k, subkey = random.split(k)
    params["b"] = random.normal(subkey, (d,)) * 0.01

    # A_down[l]: 自上而下预测矩阵 (upper_dim → this_dim)
    if upper_dim is not None:
        k, subkey = random.split(k)
        params["A_down"] = random.normal(subkey, (d, upper_dim)) * 0.01
    else:
        # 最高层没有上层，A_down 恒为零
        params["A_down"] = jnp.zeros((d, 1))

    # A_up[l]: 自下而上预测误差矩阵 (lower_dim → this_dim)
    # 注意：A_up 从下层映射到本层，所以 shape=(this_dim, lower_dim)
    # 但在 forward_bottomup 中，我们需要从下层往上层传播
    # 实际上 A_up 是从下层到上层的映射，所以 shape=(upper_dim, this_dim)
    # 为了统一，我们存 A_up 为 (lower_dim, this_dim)^T 变体
    # 这里存为 (this_dim,) 占位，在 set_lower_dim 时设置
    params["A_up"] = None  # 稍后在 set_lower_dim 时初始化

    # C[l]: 发射矩阵 — 仅最低层需要 (obs_dim × latent_dim)
    # 在 set_obs_dim 时初始化
    params["C"] = None

    # MLP 权重 (如果使用非线性)
    if config.use_nonlinear:
        h = config.hidden_dim
        k, subkey = random.split(k)
        params["W1"] = random.normal(subkey, (h, d)) * jnp.sqrt(2.0 / d)
        k, subkey = random.split(k)
        params["W2"] = random.normal(subkey, (d, h)) * jnp.sqrt(2.0 / h)
    else:
        params["W1"] = None
        params["W2"] = None

    # 转移噪声精度 (log 尺度确保正性)
    params["log_trans_precision"] = jnp.log(jnp.array(10.0))

    return params


# ====================================================================
# 3. HierarchicalGenModel 核心类
# ====================================================================


class HierarchicalGenModel:
    """
    分层多尺度生成模型

    实现4层时间金字塔（可扩展），每层包含：
    - 自转移动力学 P(L_i_t | L_i_{t-1}, a_t)
    - 自上而下先验 P(L_i_t | L_{i+1}_t)
    - 自下而上预测误差传播

    自由能分解：
        F = Σ_l [ KL(q(s_l) || p(s_l)) + E_q[log P(o | s_0)] ]

    Args:
        layer_configs: List[LayerConfig] — 每层的配置
        obs_dim: 观测空间维度（用于最低层的发射矩阵）
        key: JAX 随机种子
    """

    def __init__(
        self,
        layer_configs: list[LayerConfig],
        obs_dim: int = 5,
        key: jnp.ndarray | None = None,
    ):
        if not _JAX_AVAILABLE:
            logger.warning("[Hierarchical] JAX 不可用，运行在降级模式")
            self._degraded = True
            self.layer_configs = layer_configs
            self.n_layers = len(layer_configs)
            self.obs_dim = obs_dim
            return

        self._degraded = False
        self.layer_configs = layer_configs
        self.n_layers = len(layer_configs)
        self.obs_dim = obs_dim

        if key is None:
            key = random.PRNGKey(42)
        self._key = key

        # ---- 初始化每层参数 ----
        self.params: list[dict[str, jnp.ndarray]] = []

        for l in range(self.n_layers):
            cfg = layer_configs[l]
            upper_dim = layer_configs[l + 1].latent_dim if l + 1 < self.n_layers else None
            layer_params = _init_layer_params(key, l, cfg, upper_dim)
            self.params.append(layer_params)
            key, _ = random.split(key)

        # ---- 初始化层间连接（A_up 和 C） ----
        self._init_cross_layer_params(key)

        # ---- 归一化统计 ----
        self._layer_means = [jnp.zeros(cfg.latent_dim) for cfg in layer_configs]
        self._layer_vars = [jnp.ones(cfg.latent_dim) for cfg in layer_configs]

        # ---- 预测误差历史（每层） ----
        self._prediction_error_history: list[list[float]] = [[] for _ in range(self.n_layers)]

    def _init_cross_layer_params(self, key: jnp.ndarray) -> None:
        """初始化层间连接参数"""
        if self._degraded:
            return

        # A_up: 自下而上映射
        # 对 layer l, A_up[l] 从 layer l-1 映射到 layer l
        # 但 layer 0 没有下层
        key_use = key
        for l in range(self.n_layers):
            if l > 0:
                lower_dim = self.layer_configs[l - 1].latent_dim
                this_dim = self.layer_configs[l].latent_dim
                k, subkey = random.split(key_use)
                self.params[l]["A_up"] = random.normal(subkey, (this_dim, lower_dim)) * 0.01
            else:
                # Level 0: 没有下层，A_up 用不上
                self.params[0]["A_up"] = jnp.zeros((self.layer_configs[0].latent_dim, 1))

        # C: 发射矩阵 — 最低层到观测空间
        _k, subkey = random.split(key_use)
        self.params[0]["C"] = random.normal(subkey, (self.obs_dim, self.layer_configs[0].latent_dim)) * 0.1

    # ------------------------------------------------------------------
    # 核心前向方法
    # ------------------------------------------------------------------

    def forward_self(self, layer_idx: int, state_l: jnp.ndarray, action: jnp.ndarray) -> jnp.ndarray:
        """
        计算该层的自转移

        s'_l = tanh(A_self[l] @ s_l + b[l] + MLP(s_l))

        对应 GENESIS 中的 temporal dynamics。

        Args:
            layer_idx: 层索引
            state_l: 该层当前状态, shape=(latent_dim,)
            action: 行动向量, shape=(n_actions,)

        Returns:
            jnp.ndarray: 下一时刻的预测状态, shape=(latent_dim,)
        """
        if self._degraded:
            return state_l

        p = self.params[layer_idx]
        s = state_l

        # 线性部分
        linear = p["A_self"] @ s + p["b"]  # (latent_dim,)

        # 非线性部分 (MLP)
        if p["W1"] is not None:
            h = jnp.tanh(p["W1"] @ s)
            nonlinear = p["W2"] @ h
        else:
            nonlinear = jnp.zeros_like(linear)

        # 组合 + tanh 激活
        next_state = jnp.tanh(linear + nonlinear)

        return next_state

    def forward_topdown(self, upper_state: jnp.ndarray, layer_idx: int) -> jnp.ndarray:
        """
        自上而下预测：上层状态 → 当前层先验

        prior_l = A_down[l] @ upper_state

        对应 GENESIS 中的 "descending message passing"。
        上层（更慢时间尺度）对下层提供先验约束。

        Args:
            upper_state: 上层状态, shape=(upper_dim,)
            layer_idx: 目标层索引（接收先验的层）

        Returns:
            jnp.ndarray: 当前层的先验, shape=(latent_dim,)
        """
        if self._degraded:
            return jnp.zeros(self.layer_configs[layer_idx].latent_dim)

        p = self.params[layer_idx]

        # 最高层没有 A_down（A_down 是零矩阵），返回零先验
        if p["A_down"].shape[-1] == 1 and p["A_down"].shape[0] > 1:
            return jnp.zeros(self.layer_configs[layer_idx].latent_dim)

        prior = p["A_down"] @ upper_state
        return prior

    def forward_bottomup(self, lower_state: jnp.ndarray, lower_predicted: jnp.ndarray, layer_idx: int) -> jnp.ndarray:
        """
        自下而上传播预测误差

        update = A_up[layer_idx] @ (lower_state - lower_predicted)

        对应 "ascending prediction error propagation"。
        下层（更快时间尺度）的预测误差向上层传递，触发上层信念更新。

        Args:
            lower_state: 下层实际状态, shape=(lower_dim,)
            lower_predicted: 下层预测状态, shape=(lower_dim,)
            layer_idx: 目标层索引（接收误差的层）

        Returns:
            jnp.ndarray: 上层的更新信号, shape=(this_dim,)
        """
        if self._degraded:
            return jnp.zeros(self.layer_configs[layer_idx].latent_dim)

        if layer_idx == 0:
            # 最低层没有下层
            return jnp.zeros(self.layer_configs[0].latent_dim)

        p = self.params[layer_idx]
        pred_error = lower_state - lower_predicted  # (lower_dim,)
        update = p["A_up"] @ pred_error  # (this_dim,)
        return update

    # ------------------------------------------------------------------
    # 完整前向传播
    # ------------------------------------------------------------------

    def forward_full(
        self,
        initial_state: dict[int, jnp.ndarray],
        actions: dict[int, jnp.ndarray],
        observation: jnp.ndarray | None = None,
        precision_weights: dict[int, float] | None = None,
    ) -> dict[str, Any]:
        """
        完整的分层前向传播

        算法:
        1. 每层做自转移 (forward_self)
        2. 自上而下计算先验 (forward_topdown)
        3. 用贝叶斯方式融合自转移和自上而下先验
        4. 自下而上传播预测误差 (forward_bottomup)
        5. 记录每层预测误差

        Args:
            initial_state: {layer_idx: state_vector} — 每层的初始状态
            actions: {layer_idx: action_vector} — 每层的行动（如果不同）
            observation: 实际观测（可选，用于计算发射似然）
            precision_weights: {layer_idx: weight} — 精度加权覆盖

        Returns:
            dict:
                posteriors: {layer_idx: state} — 各层后验状态
                prediction_errors: {layer_idx: float} — 各层预测误差范数
                prediction_error_history: — 更新后的历史
                free_energy_components: — 自由能分解
                full_state_vector: — 拼接的全层状态向量
        """
        if self._degraded:
            # 降级模式返回零向量
            dummy = {l: jnp.zeros(self.layer_configs[l].latent_dim) for l in range(self.n_layers)}
            return {
                "posteriors": dummy,
                "prediction_errors": dict.fromkeys(range(self.n_layers), 0.0),
                "prediction_error_history": self._prediction_error_history,
                "free_energy_components": {},
                "full_state_vector": jnp.concatenate(list(dummy.values())),
            }

        # ---- Step 1: 自转移预测 ----
        self_predictions: dict[int, jnp.ndarray] = {}
        for l in range(self.n_layers):
            s = initial_state.get(l, jnp.zeros(self.layer_configs[l].latent_dim))
            a = actions.get(l, jnp.zeros(1))
            self_predictions[l] = self.forward_self(l, s, a)

        # ---- Step 2: 自上而下先验 ----
        topdown_priors: dict[int, jnp.ndarray] = {}
        for l in range(self.n_layers):
            if l < self.n_layers - 1:
                # 上层（更高索引）对下层提供先验
                upper_state = self_predictions[l + 1]
                topdown_priors[l] = self.forward_topdown(upper_state, l)
            else:
                # 最高层：无自上而下先验，用零
                topdown_priors[l] = jnp.zeros(self.layer_configs[l].latent_dim)

        # ---- Step 3: 贝叶斯融合 ----
        # 后验 = 自转移 × 自上而下先验（在 logit 空间加权平均）
        # 使用精度加权：precision 越高，该信息源权重越大
        posteriors: dict[int, jnp.ndarray] = {}
        for l in range(self.n_layers):
            pw = (
                precision_weights.get(l, self.layer_configs[l].temporal_precision)
                if precision_weights
                else self.layer_configs[l].temporal_precision
            )

            # 融合权重
            self_weight = 1.0 - pw * 0.3  # 自转移权重
            prior_weight = pw * 0.3  # 自上而下先验权重

            posterior = self_weight * self_predictions[l] + prior_weight * jnp.tanh(topdown_priors[l])
            posterior = jnp.tanh(posterior)
            posteriors[l] = posterior

        # ---- Step 4: 自下而上预测误差 ----
        prediction_errors: dict[int, float] = {}
        for l in range(1, self.n_layers):
            lower_actual = posteriors[l - 1]
            lower_pred = self_predictions[l - 1]
            update = self.forward_bottomup(lower_actual, lower_pred, l)
            # 用 update 修正上层后验
            posteriors[l] = jnp.tanh(posteriors[l] + update * 0.1)
            # 记录预测误差范数
            pe_norm = float(jnp.linalg.norm(lower_actual - lower_pred))
            prediction_errors[l - 1] = pe_norm
            # 记录日志
            self._prediction_error_history[l - 1].append(pe_norm)

        # 最高层的预测误差为此层自身的不确定性
        if self.n_layers > 0:
            top_idx = self.n_layers - 1
            prediction_errors[top_idx] = float(jnp.linalg.norm(posteriors[top_idx] - self_predictions[top_idx]))
            self._prediction_error_history[top_idx].append(prediction_errors[top_idx])

        # ---- Step 5: 拼接全层状态向量 ----
        full_vector = jnp.concatenate([posteriors[l] for l in range(self.n_layers)])

        # ---- Step 6: 自由能分解（如果有观测） ----
        free_energy_components = {}
        if observation is not None:
            fe_dict = self.compute_free_energy(posteriors, observation)
            free_energy_components = fe_dict

        return {
            "posteriors": posteriors,
            "self_predictions": self_predictions,
            "topdown_priors": topdown_priors,
            "prediction_errors": prediction_errors,
            "prediction_error_history": self._prediction_error_history,
            "free_energy_components": free_energy_components,
            "full_state_vector": full_vector,
        }

    # ------------------------------------------------------------------
    # 变分自由能计算
    # ------------------------------------------------------------------

    def compute_free_energy(
        self,
        hierarchical_state: dict[int, jnp.ndarray],
        observation: jnp.ndarray,
    ) -> dict[str, Any]:
        """
        计算分层变分自由能

        F = Σ_l [ KL(q(s_l) || p(s_l)) + E_q[log P(o | s_0)] ]

        分解：
        - 复杂度项: Σ_l KL(q(s_l) || p(s_l))
        - 准确度项: -E_q[log P(o | s_0)] （仅最低层有发射项）

        Args:
            hierarchical_state: {layer_idx: state}
            observation: 观测向量, shape=(obs_dim,)

        Returns:
            dict:
                total_free_energy: float — 总自由能
                complexity: float — 复杂度项
                accuracy: float — 准确度项
                layer_kl: {layer_idx: float} — 每层 KL
        """
        if self._degraded:
            return {
                "total_free_energy": 0.0,
                "complexity": 0.0,
                "accuracy": 0.0,
                "layer_kl": dict.fromkeys(range(self.n_layers), 0.0),
            }

        # ---- 1. 复杂度项: Σ_l KL(q(s_l) || p(s_l)) ----
        layer_kl = {}
        total_complexity = 0.0

        for l in range(self.n_layers):
            s = hierarchical_state[l]
            cfg = self.layer_configs[l]

            # 先验 p(s_l) ~ N(0, 1)
            # 后验 q(s_l) ~ N(s, 1/β) 其中 β = temporal_precision
            precision = cfg.temporal_precision + 1e-8

            # 高斯 KL 闭式解:
            # KL(N(μ, σ²) || N(0, 1)) = 0.5 * (σ² + μ² - 1 - ln(σ²))
            posterior_var = 1.0 / precision
            kl = 0.5 * jnp.sum(posterior_var + s**2 - 1.0 - jnp.log(posterior_var + 1e-8))
            layer_kl[l] = float(kl)
            total_complexity += float(kl)

        # ---- 2. 准确度项: -E_q[log P(o | s_0)] ----
        # 仅最低层有发射矩阵
        accuracy = 0.0
        if self.params[0]["C"] is not None:
            C_mat = self.params[0]["C"]  # (obs_dim, latent_dim_0)
            s0 = hierarchical_state[0]

            # 预测均值
            pred_obs = C_mat @ s0  # (obs_dim,)

            # 观测噪声精度
            log_prec = self.params[0].get(
                "log_trans_precision",
                jnp.log(jnp.array(10.0)),
            )
            obs_precision = jnp.exp(log_prec)

            # 负对数似然: -log P(o|s0) = 0.5 * [β * (o - μ)² + log(2π/β)]
            err = observation - pred_obs
            nll = 0.5 * jnp.sum(obs_precision * err**2 + jnp.log(2 * jnp.pi / (obs_precision + 1e-8)))
            accuracy = -float(nll)  # 准确度 = 对数似然
        else:
            accuracy = 0.0

        # ---- 3. 总自由能 ----
        # F = 复杂度 - 准确度
        total_fe = total_complexity - accuracy

        return {
            "total_free_energy": total_fe,
            "complexity": total_complexity,
            "accuracy": accuracy,
            "layer_kl": layer_kl,
        }

    # ------------------------------------------------------------------
    # 批量预测 (使用 JAX vmap 替代 Python for 循环)
    # ------------------------------------------------------------------

    def _forward_single_pure(
        self,
        s_flat: jnp.ndarray,
        a_flat: jnp.ndarray,
    ) -> dict[str, Any]:
        """纯 JAX 单次前向传播（无副作用，用于 vmap 批量化）。

        此函数不修改 self._prediction_error_history，返回的 prediction_errors
        为 jnp.ndarray 标量，由调用方负责转换并记录到历史中。

        Args:
            s_flat: 拼接的全层状态向量 [sum(latent_dim),]
            a_flat: 拼接的全层行动向量 [n_layers,]

        Returns:
            dict: 各字段均为 jnp.ndarray（无 Python float 转换）
        """
        # 1. 拆分平坦向量为每层的 dict
        state_dict = {}
        action_dict = {}
        offset = 0
        for l in range(self.n_layers):
            dim = self.layer_configs[l].latent_dim
            state_dict[l] = s_flat[offset : offset + dim]
            offset += dim
            action_dict[l] = a_flat[l : l + 1]

        # 2. 自转移
        self_predictions = {}
        for l in range(self.n_layers):
            s = state_dict.get(l, jnp.zeros(self.layer_configs[l].latent_dim))
            a = action_dict.get(l, jnp.zeros(1))
            self_predictions[l] = self.forward_self(l, s, a)

        # 3. 自上而下先验
        topdown_priors = {}
        for l in range(self.n_layers):
            if l < self.n_layers - 1:
                upper_state = self_predictions[l + 1]
                topdown_priors[l] = self.forward_topdown(upper_state, l)
            else:
                topdown_priors[l] = jnp.zeros(self.layer_configs[l].latent_dim)

        # 4. 贝叶斯融合（纯 JAX，无 Python float 转换）
        posteriors = {}
        for l in range(self.n_layers):
            pw = self.layer_configs[l].temporal_precision
            self_weight = 1.0 - pw * 0.3
            prior_weight = pw * 0.3
            posterior = self_weight * self_predictions[l] + prior_weight * jnp.tanh(topdown_priors[l])
            posterior = jnp.tanh(posterior)
            posteriors[l] = posterior

        # 5. 自下而上预测误差传播（纯 JAX，不修改 self._prediction_error_history）
        prediction_errors = {}
        for l in range(1, self.n_layers):
            lower_actual = posteriors[l - 1]
            lower_pred = self_predictions[l - 1]
            update = self.forward_bottomup(lower_actual, lower_pred, l)
            posteriors[l] = jnp.tanh(posteriors[l] + update * 0.1)
            prediction_errors[l - 1] = jnp.linalg.norm(lower_actual - lower_pred)

        if self.n_layers > 0:
            top_idx = self.n_layers - 1
            prediction_errors[top_idx] = jnp.linalg.norm(posteriors[top_idx] - self_predictions[top_idx])

        # 6. 拼接全层状态向量
        full_vector = jnp.concatenate([posteriors[l] for l in range(self.n_layers)])

        return {
            "posteriors": posteriors,
            "self_predictions": self_predictions,
            "topdown_priors": topdown_priors,
            "prediction_errors": prediction_errors,
            "full_state_vector": full_vector,
        }

    def batch_predict(
        self,
        initial_states: dict[int, jnp.ndarray],
        actions: dict[int, jnp.ndarray],
        n_batch: int = 1,
    ) -> list[dict[str, Any]]:
        """
        批量执行前向传播（使用 JAX vmap 替代 Python for 循环）

        由于 forward_full 访问 self._prediction_error_history 产生副作用，
        核心计算通过 _forward_single_pure 在 JAX 图内完成，
        预测误差记录在 JAX 调用外执行。

        Args:
            initial_states: {layer_idx: state}（支持 batch 维度）
            actions: {layer_idx: action}
            n_batch: 批大小

        Returns:
            List[Dict]: 每批的结果，格式同 forward_full
        """
        if self._degraded:
            return [self.forward_full(initial_states, actions) for _ in range(n_batch)]

        # 将初始状态扩展到 batch 维度
        batched_states = {}
        for l in range(self.n_layers):
            s = initial_states.get(l, jnp.zeros(self.layer_configs[l].latent_dim))
            batched_states[l] = jnp.tile(s[None, :], (n_batch, 1))

        # 行动也扩展
        batched_actions = {}
        for l in range(self.n_layers):
            a = actions.get(l, jnp.zeros(1))
            batched_actions[l] = jnp.tile(a[None, :], (n_batch, 1))

        if _JAX_AVAILABLE:
            # ---- JAX 路径: 将 dict 拼为平坦数组后用 jax.vmap ----
            total_latent_dim = sum(self.layer_configs[l].latent_dim for l in range(self.n_layers))
            states_flat = jnp.zeros((n_batch, total_latent_dim), dtype=jnp.float32)
            actions_flat = jnp.zeros((n_batch, self.n_layers), dtype=jnp.float32)
            offset = 0
            for l in range(self.n_layers):
                dim = self.layer_configs[l].latent_dim
                states_flat = states_flat.at[:, offset : offset + dim].set(batched_states[l])
                offset += dim
                actions_flat = actions_flat.at[:, l].set(batched_actions[l][:, 0])

            # 使用 jax.vmap 批量化纯前向传播
            _vmap_fn = jax.vmap(self._forward_single_pure, in_axes=(0, 0))
            batched_results = _vmap_fn(states_flat, actions_flat)

            # 将 batched_results (dict of batched arrays) 转换为 List[Dict]
            results = []
            for i in range(n_batch):
                result_i = {}
                for key, value in batched_results.items():
                    if isinstance(value, dict):
                        # posteriors / self_predictions / topdown_priors / prediction_errors
                        result_i[key] = {}
                        for sub_key, arr in value.items():
                            val = arr[i]
                            if key == "prediction_errors":
                                # 预测误差需要转换为 Python float 并在历史中记录
                                pe_float = float(val)
                                result_i[key][sub_key] = pe_float
                                self._prediction_error_history[sub_key].append(pe_float)
                            else:
                                result_i[key][sub_key] = val
                    else:
                        # full_state_vector: [n_batch, total_dim]
                        result_i[key] = value[i]

                # 补充 forward_full 中额外的字段
                result_i["free_energy_components"] = {}
                result_i["prediction_error_history"] = self._prediction_error_history
                results.append(result_i)
        else:
            # ---- 降级路径 (JAX 不可用): Python for 循环 ----
            results = []
            for i in range(n_batch):
                single_states = {l: batched_states[l][i] for l in range(self.n_layers)}
                single_actions = {l: batched_actions[l][i] for l in range(self.n_layers)}
                results.append(self.forward_full(single_states, single_actions))

        return results

    # ------------------------------------------------------------------
    # 参数管理
    # ------------------------------------------------------------------

    def get_params(self) -> list[dict[str, jnp.ndarray]]:
        """获取所有层的可学习参数"""
        return [dict(p) for p in self.params]

    def set_params(self, params: list[dict[str, jnp.ndarray]]) -> None:
        """设置所有层的可学习参数"""
        if len(params) != self.n_layers:
            raise ValueError(f"参数列表长度 {len(params)} 与层数 {self.n_layers} 不匹配")
        self.params = [dict(p) for p in params]

    def get_layer_params(self, layer_idx: int) -> dict[str, jnp.ndarray]:
        """获取指定层的参数"""
        return dict(self.params[layer_idx])

    def set_layer_params(self, layer_idx: int, params: dict[str, jnp.ndarray]) -> None:
        """设置指定层的参数"""
        for k, v in params.items():
            if k in self.params[layer_idx]:
                self.params[layer_idx][k] = v

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为可序列化的字典（用于持久化保存）

        Returns:
            dict:
                layer_configs: List[Dict] — 层配置
                params: List[Dict[str, List]] — JAX arrays 转为 list
                obs_dim: int
        """
        if self._degraded:
            return {
                "layer_configs": [
                    {
                        "name": c.name,
                        "latent_dim": c.latent_dim,
                        "time_scale": c.time_scale.value,
                        "temporal_precision": c.temporal_precision,
                    }
                    for c in self.layer_configs
                ],
                "params": [],
                "obs_dim": self.obs_dim,
            }

        serializable_params = []
        for p in self.params:
            sp = {}
            for k, v in p.items():
                if v is None:
                    sp[k] = None
                elif isinstance(v, jnp.ndarray):
                    sp[k] = v.tolist()
                else:
                    sp[k] = v
            serializable_params.append(sp)

        return {
            "layer_configs": [
                {
                    "name": c.name,
                    "latent_dim": c.latent_dim,
                    "time_scale": c.time_scale.value,
                    "temporal_precision": c.temporal_precision,
                }
                for c in self.layer_configs
            ],
            "params": serializable_params,
            "obs_dim": self.obs_dim,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], key: jnp.ndarray | None = None) -> "HierarchicalGenModel":
        """从字典重建模型

        Args:
            data: to_dict() 输出的数据
            key: JAX 随机种子

        Returns:
            HierarchicalGenModel: 重建的模型
        """
        time_scale_map = {
            "tick": TimeScale.TICK,
            "minute": TimeScale.MINUTE,
            "hour": TimeScale.HOUR,
            "day": TimeScale.DAY,
            "week": TimeScale.WEEK,
            "month": TimeScale.MONTH,
        }

        layer_configs = []
        for cd in data["layer_configs"]:
            layer_configs.append(
                LayerConfig(
                    name=cd["name"],
                    latent_dim=cd["latent_dim"],
                    time_scale=time_scale_map.get(cd["time_scale"], TimeScale.TICK),
                    temporal_precision=cd.get("temporal_precision", 0.5),
                ),
            )

        model = cls(layer_configs, obs_dim=data.get("obs_dim", 5), key=key)

        # 恢复参数
        if data.get("params") and not model._degraded:
            for l_idx, sp in enumerate(data["params"]):
                for k, v in sp.items():
                    if v is not None and k in model.params[l_idx]:
                        model.params[l_idx][k] = jnp.array(v)

        return model

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def get_full_state_vector(self, posteriors: dict[int, jnp.ndarray]) -> jnp.ndarray:
        """将各层状态拼接为完整向量"""
        return jnp.concatenate([posteriors[l] for l in range(self.n_layers)])

    def split_full_state_vector(self, full_vector: jnp.ndarray) -> dict[int, jnp.ndarray]:
        """将完整向量拆分为各层状态"""
        result = {}
        offset = 0
        for l in range(self.n_layers):
            dim = self.layer_configs[l].latent_dim
            result[l] = full_vector[offset : offset + dim]
            offset += dim
        return result

    def get_prediction_error_history(self, layer_idx: int | None = None) -> list[float] | list[list[float]]:
        """获取预测误差历史

        Args:
            layer_idx: 如果指定，返回该层的历史；否则返回所有层

        Returns:
            List[float] 或 List[List[float]]
        """
        if layer_idx is not None:
            return list(self._prediction_error_history[layer_idx])
        return [list(h) for h in self._prediction_error_history]

    def reset(self) -> None:
        """重置模型（清空历史，保持参数不变）"""
        self._prediction_error_history = [[] for _ in range(self.n_layers)]
        self._layer_means = [jnp.zeros(cfg.latent_dim) for cfg in self.layer_configs]
        self._layer_vars = [jnp.ones(cfg.latent_dim) for cfg in self.layer_configs]

    @property
    def total_latent_dim(self) -> int:
        """所有层潜变量维度之和"""
        return sum(cfg.latent_dim for cfg in self.layer_configs)


# ====================================================================
# 4. 便捷函数
# ====================================================================


def build_default_4layer_model(key: jnp.ndarray) -> HierarchicalGenModel:
    """构建默认4层模型

    架构:
        Level 3 (strategic): latent_dim=64, scale=WEEK  — 策略层
        Level 2 (macro):     latent_dim=32, scale=DAY    — 模式层
        Level 1 (meso):      latent_dim=16, scale=MINUTE — 微观层
        Level 0 (micro):     latent_dim=8,  scale=TICK   — 原始数据层

    Returns:
        HierarchicalGenModel: 4层模型实例
    """
    configs = [
        LayerConfig(
            name="micro",
            latent_dim=8,
            time_scale=TimeScale.TICK,
            temporal_precision=TimeScale.TICK.precision_weight,
        ),
        LayerConfig(
            name="meso",
            latent_dim=16,
            time_scale=TimeScale.MINUTE,
            temporal_precision=TimeScale.MINUTE.precision_weight,
        ),
        LayerConfig(
            name="macro",
            latent_dim=32,
            time_scale=TimeScale.DAY,
            temporal_precision=TimeScale.DAY.precision_weight,
        ),
        LayerConfig(
            name="strategic",
            latent_dim=64,
            time_scale=TimeScale.WEEK,
            temporal_precision=TimeScale.WEEK.precision_weight,
        ),
    ]
    return HierarchicalGenModel(configs, obs_dim=5, key=key)


def build_custom_model(
    layer_dims: list[int],
    time_scales: list[TimeScale],
    obs_dim: int = 5,
    key: jnp.ndarray | None = None,
) -> HierarchicalGenModel:
    """构建自定义分层模型

    Args:
        layer_dims: 每层 latent_dim 列表（从低到高）
        time_scales: 每层的时间尺度列表
        obs_dim: 观测维度
        key: JAX 随机种子

    Returns:
        HierarchicalGenModel
    """
    assert len(layer_dims) == len(time_scales), "layer_dims 和 time_scales 长度必须一致"

    names = ["micro", "meso", "macro", "strategic", "meta"]
    configs = []
    for i, (dim, ts) in enumerate(zip(layer_dims, time_scales, strict=False)):
        name = names[i] if i < len(names) else f"layer_{i}"
        configs.append(
            LayerConfig(
                name=name,
                latent_dim=dim,
                time_scale=ts,
                temporal_precision=ts.precision_weight,
            ),
        )

    return HierarchicalGenModel(configs, obs_dim=obs_dim, key=key)


# ====================================================================
# 内省工具
# ====================================================================


def print_hierarchy_info(model: HierarchicalGenModel) -> str:
    """打印分层模型的结构信息"""
    lines = ["=== HierarchicalGenModel 结构 ==="]
    lines.append(f"总层数: {model.n_layers}")
    lines.append(f"总潜变量维度: {model.total_latent_dim}")
    lines.append(f"观测维度: {model.obs_dim}")
    lines.append("")

    for l in range(model.n_layers):
        cfg = model.layer_configs[l]
        params = model.params[l] if not model._degraded else {}
        n_params = sum(np.prod(v.shape) if hasattr(v, "shape") else 0 for v in params.values() if v is not None)
        lines.append(
            f"  Level {l} ({cfg.name}): "
            f"dim={cfg.latent_dim}, "
            f"scale={cfg.time_scale.value}, "
            f"precision={cfg.temporal_precision:.3f}, "
            f"params={n_params}",
        )

    return "\n".join(lines)


# ====================================================================
# __all__ 导出
# ====================================================================

__all__ = [
    "HierarchicalGenModel",
    "LayerConfig",
    "TimeScale",
    "build_custom_model",
    "build_default_4layer_model",
    "print_hierarchy_info",
]
