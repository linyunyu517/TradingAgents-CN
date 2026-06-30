# tradingagents/diffusion/score_network.py
"""
Score Network 基类与 1D Temporal U-Net 实现

提供:
    - ScoreNetwork 抽象基类：定义去噪网络接口
    - TemporalUNet1D：1D 卷积时序 U-Net，适合金融时间序列
    - ScoreTable：预计算的 score lookup table 缓存
    - SinusoidalEmbedding：Transformer 风格的时间步位置编码

所有实现均为纯 NumPy，零深度学习框架依赖。
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import OrderedDict

import numpy as np

from .config import DiffusionConfig

# ==================================================================
# 工具函数
# ==================================================================


def sinusoidal_embedding(timestep: int, embedding_dim: int, max_period: int = 10000) -> np.ndarray:
    """Transformer 风格的正弦位置编码

    将标量时间步 t 编码为 embedding_dim 维度的正弦/余弦向量，
    使网络能够感知时间步的绝对和相对位置。

    Args:
        timestep: 扩散时间步 t (1-indexed)
        embedding_dim: 嵌入维度 (必须为偶数)
        max_period: 最大周期 (默认 10000, 与 Transformer 一致)

    Returns:
        np.ndarray: shape (embedding_dim,) 时间嵌入向量
    """
    assert embedding_dim % 2 == 0, "embedding_dim 必须为偶数"

    half_dim = embedding_dim // 2
    # 频率: 1 / (10000^(2i/d))
    freqs = np.exp(-math.log(max_period) * np.arange(half_dim, dtype=np.float64) / half_dim)
    # 角度: t * 频率
    args = np.float64(timestep) * freqs
    # 正弦和余弦交替拼接
    embedding = np.concatenate([np.sin(args), np.cos(args)])
    return embedding


def _time_embedding_batch(timesteps: np.ndarray, embedding_dim: int) -> np.ndarray:
    """批量计算时间步嵌入

    Args:
        timesteps: shape (batch,) 时间步数组
        embedding_dim: 嵌入维度

    Returns:
        np.ndarray: shape (batch, embedding_dim)
    """
    embeddings = []
    for t in timesteps:
        embeddings.append(sinusoidal_embedding(int(t), embedding_dim))
    return np.stack(embeddings, axis=0)


def _zero_module(module: dict) -> dict:
    """将模块的所有权重初始化为零 (用于残差连接)"""
    zeroed = {}
    for key, val in module.items():
        zeroed[key] = np.zeros_like(val)
    return zeroed


# ==================================================================
# 层实现 (纯 NumPy)
# ==================================================================


class Conv1D:
    """1D 卷积层 (NumPy 实现)

    使用 im2col 方法将卷积运算转化为矩阵乘法，
    支持 padding 和 dilation。

    Attributes:
        in_channels: 输入通道数
        out_channels: 输出通道数
        kernel_size: 卷积核大小
        padding: 填充大小
        W: 权重, shape (out_channels, in_channels, kernel_size)
        b: 偏置, shape (out_channels,)
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        stride: int = 1,
        padding: int = 0,
        init_scale: float = 0.1,
    ):
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.padding = padding

        # Kaiming 初始化
        scale = init_scale / math.sqrt(in_channels * kernel_size)
        self.W = np.random.randn(out_channels, in_channels, kernel_size).astype(np.float64) * scale
        self.b = np.zeros(out_channels, dtype=np.float64)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播

        Args:
            x: shape (batch, in_channels, seq_len)

        Returns:
            np.ndarray: shape (batch, out_channels, seq_len')
                其中 seq_len' = floor((seq_len + 2*padding - kernel_size) / stride) + 1
        """
        batch, in_c, seq_len = x.shape
        if in_c != self.in_channels:
            raise ValueError(
                f"Conv1D 输入通道不匹配: 期望 {self.in_channels}, 实际 {in_c}. "
                f"(层: ({self.in_channels}→{self.out_channels}), "
                f"kernel={self.kernel_size}, stride={self.stride})"
            )
        K = self.kernel_size
        S = self.stride
        P = self.padding

        # padding
        x_padded = np.pad(x, ((0, 0), (0, 0), (P, P)), mode="constant") if P > 0 else x

        # im2col: 将输入展开为矩阵
        # 每个 stride 位置提取 kernel_size 长度的窗口
        padded_len = seq_len + 2 * P
        out_len = (padded_len - K) // S + 1
        cols = np.zeros((batch, in_c, K, out_len), dtype=np.float64)

        for i in range(out_len):
            start = i * S
            cols[:, :, :, i] = x_padded[:, :, start : start + K]

        # 矩阵乘法
        W_flat = self.W.reshape(self.out_channels, -1)  # (out_c, in_c * K)
        cols_flat = cols.reshape(batch, -1, out_len)  # (batch, in_c * K, out_len)

        out = np.zeros((batch, self.out_channels, out_len), dtype=np.float64)
        for b in range(batch):
            out[b] = W_flat @ cols_flat[b]

        out += self.b[:, np.newaxis]
        return out

    def get_parameters(self) -> dict[str, np.ndarray]:
        return {"W": self.W.copy(), "b": self.b.copy()}

    def set_parameters(self, params: dict[str, np.ndarray]) -> None:
        self.W = params["W"].copy()
        self.b = params["b"].copy()

    def validate_dimensions(self, x: np.ndarray) -> None:
        """验证输入张量维度与本层权重维度兼容

        Args:
            x: 输入张量, shape (batch, in_channels, seq_len)

        Raises:
            ValueError: 当维度不匹配时提供清晰的诊断信息
        """
        if x.shape[1] != self.in_channels:
            raise ValueError(
                f"Conv1D 维度不匹配: 输入 in_channels={x.shape[1]}, "
                f"本层期望 in_channels={self.in_channels} "
                f"(out_channels={self.out_channels}, kernel_size={self.kernel_size})",
            )
        # 验证 W 的存储维度与声明一致
        if self.W.shape[1] != self.in_channels:
            raise ValueError(
                f"Conv1D 权重维度异常: W.in_channels={self.W.shape[1]}, "
                f"但 self.in_channels={self.in_channels}. "
                f"这可能是因为 rebuild() 后旧权重未被完全替换。",
            )


class ConvTranspose1D:
    """1D 转置卷积层 (NumPy 实现)

    用于 U-Net 上采样路径。

    Attributes:
        in_channels: 输入通道数
        out_channels: 输出通道数
        kernel_size: 卷积核大小
        stride: 步长
        padding: 填充大小
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        stride: int = 2,
        padding: int = 0,
        init_scale: float = 0.1,
    ):
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.padding = padding

        scale = init_scale / math.sqrt(in_channels * kernel_size)
        self.W = np.random.randn(in_channels, out_channels, kernel_size).astype(np.float64) * scale
        self.b = np.zeros(out_channels, dtype=np.float64)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播

        Args:
            x: shape (batch, in_channels, seq_len)

        Returns:
            np.ndarray: shape (batch, out_channels, seq_len')
        """
        batch, in_c, seq_len = x.shape
        K = self.kernel_size
        S = self.stride
        P = self.padding

        # 输出长度
        out_len = (seq_len - 1) * S + K - 2 * P

        # 初始化输出
        out = np.zeros((batch, self.out_channels, out_len), dtype=np.float64)

        # 转置卷积: 将每个输入位置展开到输出
        for b in range(batch):
            for i in range(in_c):
                for j in range(seq_len):
                    # 输入位置 j 贡献到输出的 S*j 到 S*j + K
                    start = S * j
                    end = start + K
                    if start < out_len and end <= out_len:
                        # 对每个输出通道
                        for o in range(self.out_channels):
                            out[b, o, start:end] += x[b, i, j] * self.W[i, o, :]

        # 去除 padding
        if P > 0:
            out = out[:, :, P:-P]

        # 添加偏置
        out += self.b[:, np.newaxis]

        return out

    def get_parameters(self) -> dict[str, np.ndarray]:
        return {"W": self.W.copy(), "b": self.b.copy()}

    def validate_dimensions(self, x: np.ndarray) -> None:
        """验证输入张量维度与本层权重维度兼容

        Args:
            x: 输入张量, shape (batch, in_channels, seq_len)

        Raises:
            ValueError: 当维度不匹配时提供清晰的诊断信息
        """
        if x.shape[1] != self.in_channels:
            raise ValueError(
                f"ConvTranspose1D 维度不匹配: 输入 in_channels={x.shape[1]}, "
                f"本层期望 in_channels={self.in_channels} "
                f"(out_channels={self.out_channels}, kernel_size={self.kernel_size})",
            )


class ResidualBlock1D:
    """1D 残差块 (NumPy 实现)

    包含两个 Conv1D 层 + 时间步 FiLM 调制 + 跳跃连接。

    结构:
        x → Conv1D → GroupNorm → SiLU → FiLM(t_emb) → Conv1D → GroupNorm → + → output
        |                                                                    ↑
        └──────────────────────── 跳跃连接 (1x1 Conv 调整维度) ──────────────┘
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        padding: int = 1,
        film_dim: int = 128,
    ):
        self.in_channels = in_channels
        self.out_channels = out_channels

        # 第一个卷积 (显式关键字参数，避免 stride/padding 位置混淆)
        self.conv1 = Conv1D(in_channels, out_channels, kernel_size, stride=1, padding=padding)
        # 第二个卷积
        self.conv2 = Conv1D(out_channels, out_channels, kernel_size, stride=1, padding=padding)
        # 时间步 FiLM 调制 (film_dim -> out_channels)
        self.film_gamma = Conv1D(film_dim, out_channels, kernel_size=1, stride=1, padding=0)
        self.film_beta = Conv1D(film_dim, out_channels, kernel_size=1, stride=1, padding=0)
        # 跳跃连接 (如果维度不匹配)
        if in_channels != out_channels:
            self.skip_conv = Conv1D(in_channels, out_channels, kernel_size=1, stride=1, padding=0)
        else:
            self.skip_conv = None

    def validate_dimensions(self, x: np.ndarray, t_emb: np.ndarray) -> None:
        """验证残差块内所有子层的维度兼容性

        Args:
            x: 输入张量, shape (batch, in_channels, seq_len)
            t_emb: 时间步嵌入, shape (batch, cond_dim)
        """
        self.conv1.validate_dimensions(x)
        # conv2 接收 conv1 的输出，维度为 (batch, out_channels, seq_len)
        # film_gamma/beta 接收 t_emb 在 seq_len 维度的扩展
        film_in = t_emb[:, :, np.newaxis]  # (batch, film_dim, 1)
        self.film_gamma.validate_dimensions(film_in)
        self.film_beta.validate_dimensions(film_in)
        # conv2 接收 film 调制后的 h, 维度为 (batch, out_channels, seq_len)
        conv2_in = np.zeros((x.shape[0], self.out_channels, x.shape[2]), dtype=np.float64)
        self.conv2.validate_dimensions(conv2_in)
        if self.skip_conv is not None:
            self.skip_conv.validate_dimensions(x)

    def forward(self, x: np.ndarray, t_emb: np.ndarray) -> np.ndarray:
        """前向传播

        Args:
            x: shape (batch, in_channels, seq_len)
            t_emb: shape (batch, cond_dim) 时间步嵌入

        Returns:
            np.ndarray: shape (batch, out_channels, seq_len)
        """
        # 输入分支
        h = self.conv1.forward(x)
        h = self._silu(h)

        # FiLM: 时间步调制
        # gamma = t_emb -> conv -> reshape to broadcast
        gamma = self.film_gamma.forward(t_emb[:, :, np.newaxis])  # (batch, out_channels, 1)
        beta = self.film_beta.forward(t_emb[:, :, np.newaxis])  # (batch, out_channels, 1)
        h = h * (1.0 + gamma) + beta

        # 第二个卷积
        h = self.conv2.forward(h)

        # 跳跃连接
        skip = self.skip_conv.forward(x) if self.skip_conv is not None else x

        return h + skip

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        """SiLU (Swish) 激活函数: x * sigmoid(x)"""
        return x * (1.0 / (1.0 + np.exp(-x)))

    def get_parameters(self) -> dict[str, np.ndarray]:
        params = {
            "conv1": self.conv1.get_parameters(),
            "conv2": self.conv2.get_parameters(),
            "film_gamma": self.film_gamma.get_parameters(),
            "film_beta": self.film_beta.get_parameters(),
        }
        if self.skip_conv is not None:
            params["skip_conv"] = self.skip_conv.get_parameters()
        return params

    def set_parameters(self, params: dict) -> None:
        self.conv1.set_parameters(params["conv1"])
        self.conv2.set_parameters(params["conv2"])
        self.film_gamma.set_parameters(params["film_gamma"])
        self.film_beta.set_parameters(params["film_beta"])
        if self.skip_conv is not None and "skip_conv" in params:
            self.skip_conv.set_parameters(params["skip_conv"])


# ==================================================================
# Score Network 基类
# ==================================================================


class ScoreNetwork(ABC):
    """Score Network 抽象基类

    定义去噪网络的标准接口。所有具体的去噪网络架构
    (TemporalUNet1D, TransformerDenoiser 等) 都应继承此类。

    核心功能:
        forward(x, t, cond) -> ε_θ(x_t, t, cond)
            预测添加的噪声 ε，用于 DDIM 采样器的去噪步骤。
    """

    @abstractmethod
    def forward(
        self,
        x: np.ndarray,
        t: int,
        cond: np.ndarray | None = None,
    ) -> np.ndarray:
        """预测噪声 ε_θ(x_t, t, cond)

        Args:
            x: 当前时间步的噪声数据, shape (batch, channels, seq_len)
            t: 当前扩散时间步 (1-indexed)
            cond: 条件向量, shape (batch, cond_dim) 或 None

        Returns:
            np.ndarray: 预测噪声, shape 与 x 相同
        """
        ...

    def __call__(
        self,
        x: np.ndarray,
        t: int,
        cond: np.ndarray | None = None,
    ) -> np.ndarray:
        """便捷调用接口"""
        return self.forward(x, t, cond)

    @abstractmethod
    def load_weights(self, weight_dict: dict[str, np.ndarray]) -> None:
        """从权重字典加载预训练权重

        Args:
            weight_dict: 包含所有层参数的嵌套字典
        """
        ...

    @abstractmethod
    def get_weights(self) -> dict[str, np.ndarray]:
        """导出当前权重为字典 (用于保存)"""
        ...


# ==================================================================
# 1D Temporal U-Net
# ==================================================================


class TemporalUNet1D(ScoreNetwork):
    """1D Temporal U-Net 去噪网络

    专为时序数据设计的 U-Net 架构:
        - 下采样路径: Conv1D(stride=2) + ResidualBlock × num_res_blocks
        - 瓶颈层: Self-Attention (可选)
        - 上采样路径: ConvTranspose1D(stride=2) + Skip Connection + ResidualBlock
        - 时间嵌入: SinusoidalEmbedding → MLP → FiLM 注入各层
        - 条件注入: 条件向量通过 FiLM 调制

    通道维度设计:
        Level 0:  hidden_dim          通道, seq_len
        Level 1:  hidden_dim * 2      通道, seq_len // 2
        Level 2:  hidden_dim * 4      通道, seq_len // 4  (num_down_blocks=3)
        ...

    跳跃连接通过 [interpolate](score_network.py:647) 自动处理空间维度不匹配。

    Args:
        config: 扩散模型配置
        in_channels: 输入通道数 (默认 hidden_dim)
        out_channels: 输出通道数 (默认 hidden_dim)
        num_down_blocks: 下采样块数 (默认 2)
        use_attention: 瓶颈层是否使用 Self-Attention
        attention_heads: Self-Attention 头数
    """

    def __init__(
        self,
        config: DiffusionConfig,
        in_channels: int | None = None,
        out_channels: int | None = None,
        num_down_blocks: int = 2,
        use_attention: bool = True,
        attention_heads: int = 4,
    ):
        super().__init__()

        self.config = config
        hidden_dim = config.hidden_dim
        cond_dim = config.cond_dim
        num_res_blocks = config.num_res_blocks
        n_down = num_down_blocks

        self.in_channels = in_channels or hidden_dim
        self.out_channels = out_channels or hidden_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_down_blocks = n_down
        self.num_res_blocks = num_res_blocks
        self.use_attention = use_attention
        self.attention_heads = attention_heads

        # ================================================================
        # 初始化所有网络层
        # ================================================================
        self._init_layers()

    # ------------------------------------------------------------------
    # 层重建 (用于懒初始化维度校准)
    # ------------------------------------------------------------------

    def _init_layers(self) -> None:
        """根据当前 in_channels / out_channels / hidden_dim / cond_dim 重建所有网络层

        从 __init__ 提取的通用初始化逻辑，供 rebuild() 和首次构造调用。
        每次调用会完全替换所有层实例，确保无陈旧引用残留。
        """
        hidden_dim = self.hidden_dim
        cond_dim = self.cond_dim
        n_down = self.num_down_blocks
        num_res_blocks = self.num_res_blocks

        # ================================================================
        # 通道倍增因子: level 0→1×, level 1→2×, level 2→4×, ...
        # ================================================================
        self.ch_mult = [1]
        for l in range(1, n_down):
            self.ch_mult.append(2**l)

        # ================================================================
        # 时间嵌入 MLP: hidden_dim → hidden_dim → hidden_dim
        # ================================================================
        self.time_embed_dim = hidden_dim
        self.time_mlp_w1 = np.random.randn(hidden_dim, hidden_dim).astype(np.float64) * 0.02
        self.time_mlp_b1 = np.zeros(hidden_dim, dtype=np.float64)
        self.time_mlp_w2 = np.random.randn(hidden_dim, hidden_dim).astype(np.float64) * 0.02
        self.time_mlp_b2 = np.zeros(hidden_dim, dtype=np.float64)

        # ================================================================
        # 条件嵌入 MLP: cond_dim → hidden_dim
        # ================================================================
        self.cond_mlp_w = np.random.randn(cond_dim, hidden_dim).astype(np.float64) * 0.02
        self.cond_mlp_b = np.zeros(hidden_dim, dtype=np.float64)

        # ================================================================
        # 输入投影: in_channels → hidden_dim
        # ================================================================
        self.input_proj = Conv1D(self.in_channels, hidden_dim, kernel_size=3, padding=1)

        # ================================================================
        # 下采样路径 (完全重建列表，确保无旧层引用残留)
        # ================================================================
        self.down_blocks: list[list[ResidualBlock1D]] = []
        self.down_conv: list[Conv1D | None] = []
        self.down_level_channels: list[int] = []

        for l in range(n_down):
            level_ch = hidden_dim * self.ch_mult[l]

            block_list: list[ResidualBlock1D] = []
            for j in range(num_res_blocks):
                in_ch = level_ch
                block = ResidualBlock1D(
                    in_channels=in_ch,
                    out_channels=level_ch,
                    kernel_size=3,
                    padding=1,
                    film_dim=hidden_dim,
                )
                block_list.append(block)
            self.down_blocks.append(block_list)
            self.down_level_channels.append(level_ch)

            if l < n_down - 1:
                next_ch = hidden_dim * self.ch_mult[l + 1]
                self.down_conv.append(Conv1D(level_ch, next_ch, kernel_size=4, stride=2, padding=1))
            else:
                self.down_conv.append(None)

        # ================================================================
        # 瓶颈层 (完全重建列表)
        # ================================================================
        bottleneck_ch = hidden_dim * self.ch_mult[-1]
        self.bottleneck_resblocks: list[ResidualBlock1D] = []
        for _ in range(num_res_blocks):
            self.bottleneck_resblocks.append(
                ResidualBlock1D(
                    in_channels=bottleneck_ch,
                    out_channels=bottleneck_ch,
                    kernel_size=3,
                    padding=1,
                    film_dim=hidden_dim,
                ),
            )

        # Self-Attention in bottleneck
        if self.use_attention:
            self.attn_proj_q = np.random.randn(bottleneck_ch, bottleneck_ch).astype(np.float64) * 0.02
            self.attn_proj_k = np.random.randn(bottleneck_ch, bottleneck_ch).astype(np.float64) * 0.02
            self.attn_proj_v = np.random.randn(bottleneck_ch, bottleneck_ch).astype(np.float64) * 0.02
            self.attn_proj_out = np.random.randn(bottleneck_ch, bottleneck_ch).astype(np.float64) * 0.02

        # ================================================================
        # 上采样路径 (完全重建列表)
        # ================================================================
        self.up_blocks: list[list[ResidualBlock1D]] = []
        self.up_conv: list[ConvTranspose1D | None] = []

        reversed_levels = list(range(n_down - 1, -1, -1))
        for _idx, l in enumerate(reversed_levels):
            level_ch = hidden_dim * self.ch_mult[l]
            skip_ch = self.down_level_channels[l]

            incoming_ch = bottleneck_ch if l == n_down - 1 else level_ch

            concat_ch = incoming_ch + skip_ch

            block_list: list[ResidualBlock1D] = []
            for j in range(num_res_blocks):
                in_ch = concat_ch if j == 0 else level_ch
                block = ResidualBlock1D(
                    in_channels=in_ch,
                    out_channels=level_ch,
                    kernel_size=3,
                    padding=1,
                    film_dim=hidden_dim,
                )
                block_list.append(block)
            self.up_blocks.append(block_list)

            if l > 0:
                next_ch = hidden_dim * self.ch_mult[l - 1]
                self.up_conv.append(ConvTranspose1D(level_ch, next_ch, kernel_size=4, stride=2, padding=1))
            else:
                self.up_conv.append(None)

        # ================================================================
        # 输出投影: hidden_dim → out_channels
        # ================================================================
        self.output_proj = Conv1D(hidden_dim, self.out_channels, kernel_size=3, padding=1)

    def rebuild(
        self,
        in_channels: int,
        out_channels: int,
        hidden_dim: int | None = None,
        cond_dim: int | None = None,
        num_res_blocks: int | None = None,
    ) -> None:
        """根据新维度重建网络（懒初始化维度校准用）

        Args:
            in_channels:  输入通道数
            out_channels: 输出通道数
            hidden_dim:   隐藏层维度 (None 则保持当前值)
            cond_dim:     条件嵌入维度 (None 则保持当前值)
            num_res_blocks: 残差块数量 (None 则保持当前值)
        """
        self.in_channels = in_channels
        self.out_channels = out_channels
        if hidden_dim is not None:
            self.hidden_dim = hidden_dim
        if cond_dim is not None:
            self.cond_dim = cond_dim
        if num_res_blocks is not None:
            self.num_res_blocks = num_res_blocks

        # 重新初始化所有层
        self._init_layers()

    # ------------------------------------------------------------------
    # 前向传播
    # ------------------------------------------------------------------

    def _validate_all_dimensions(self, x: np.ndarray, t_emb: np.ndarray | None = None) -> None:
        """验证网络中所有层在 dummy 输入下的维度兼容性

        在 rebuild() 后调用，确保所有 Conv1D / ConvTranspose1D /
        ResidualBlock1D 的维度与当前配置一致。

        Args:
            x: 模拟输入, shape (batch, in_channels, seq_len)
            t_emb: 模拟时间嵌入, shape (batch, cond_dim)

        Raises:
            ValueError: 当任意层维度不匹配时抛出详细错误
        """
        n_down = self.num_down_blocks
        x.shape[0]

        # 验证各层名称 → 实例的映射
        layer_registry = []

        # 输入投影
        layer_registry.append(("input_proj", self.input_proj))

        # 下采样块内的所有子层
        for l in range(n_down):
            for j, block in enumerate(self.down_blocks[l]):
                prefix = f"down_blocks[{l}][{j}]"
                layer_registry.append((f"{prefix}.conv1", block.conv1))
                layer_registry.append((f"{prefix}.conv2", block.conv2))
                layer_registry.append((f"{prefix}.film_gamma", block.film_gamma))
                layer_registry.append((f"{prefix}.film_beta", block.film_beta))
                if block.skip_conv is not None:
                    layer_registry.append((f"{prefix}.skip_conv", block.skip_conv))
            if self.down_conv[l] is not None:
                layer_registry.append((f"down_conv[{l}]", self.down_conv[l]))

        # 瓶颈块
        for j, block in enumerate(self.bottleneck_resblocks):
            prefix = f"bottleneck_resblocks[{j}]"
            layer_registry.append((f"{prefix}.conv1", block.conv1))
            layer_registry.append((f"{prefix}.conv2", block.conv2))
            layer_registry.append((f"{prefix}.film_gamma", block.film_gamma))
            layer_registry.append((f"{prefix}.film_beta", block.film_beta))
            if block.skip_conv is not None:
                layer_registry.append((f"{prefix}.skip_conv", block.skip_conv))

        # 上采样块
        reversed_levels = list(range(n_down - 1, -1, -1))
        for idx, l in enumerate(reversed_levels):
            for j, block in enumerate(self.up_blocks[idx]):
                prefix = f"up_blocks[{idx}][{j}]"
                layer_registry.append((f"{prefix}.conv1", block.conv1))
                layer_registry.append((f"{prefix}.conv2", block.conv2))
                layer_registry.append((f"{prefix}.film_gamma", block.film_gamma))
                layer_registry.append((f"{prefix}.film_beta", block.film_beta))
                if block.skip_conv is not None:
                    layer_registry.append((f"{prefix}.skip_conv", block.skip_conv))
            if self.up_conv[idx] is not None:
                layer_registry.append((f"up_conv[{idx}]", self.up_conv[idx]))

        # 输出投影
        layer_registry.append(("output_proj", self.output_proj))

        # 逐一验证维度
        errors = []
        for name, layer in layer_registry:
            if isinstance(layer, Conv1D):
                x.shape[1] if name == "input_proj" else None

                # 检查 W 的 shape 是否与声明一致
                w_expected_in = layer.W.shape[1]  # 实际存储的 in_channels
                layer.W.shape[2]  # 实际存储的 kernel_size
                if w_expected_in != layer.in_channels:
                    errors.append(
                        f"{name}: W.in_channels={w_expected_in}, "
                        f"但 layer.in_channels={layer.in_channels} "
                        f"(W 可能来自旧重建)",
                    )
            elif isinstance(layer, ConvTranspose1D):
                if layer.W.shape[0] != layer.in_channels:
                    errors.append(f"{name}: W.in_channels={layer.W.shape[0]}, 但 layer.in_channels={layer.in_channels}")

        if errors:
            raise ValueError(f"维度验证失败 (rebuild 后 {len(errors)} 个层不匹配):\n  " + "\n  ".join(errors))

    def forward(
        self,
        x: np.ndarray,
        t: int,
        cond: np.ndarray | None = None,
    ) -> np.ndarray:
        """预测噪声 ε_θ(x_t, t, cond)

        Args:
            x: 噪声数据, shape (batch, channels, seq_len)
            t: 当前时间步 (1-indexed)
            cond: 条件向量, shape (batch, cond_dim) 或 None

        Returns:
            np.ndarray: 预测噪声, shape 与 x 相同
        """
        batch = x.shape[0]
        n_down = self.num_down_blocks

        # === 1. 时间嵌入 ===
        t_emb = sinusoidal_embedding(t, self.hidden_dim)
        t_emb = t_emb[np.newaxis, :]  # (1, hidden_dim)
        t_emb = t_emb @ self.time_mlp_w1 + self.time_mlp_b1
        t_emb = self._silu(t_emb)
        t_emb = t_emb @ self.time_mlp_w2 + self.time_mlp_b2  # (1, hidden_dim)
        # 广播到 batch
        t_emb = np.broadcast_to(t_emb, (batch, self.hidden_dim))

        # === 2. 条件嵌入 ===
        if cond is not None:
            cond_emb = cond @ self.cond_mlp_w + self.cond_mlp_b
            cond_emb = self._silu(cond_emb)
        else:
            cond_emb = np.zeros((batch, self.hidden_dim), dtype=np.float64)

        # 合并: film_cond = t_emb + cond_emb
        film_cond = t_emb + cond_emb  # (batch, hidden_dim)

        # === 3. 输入投影 ===
        h = self.input_proj.forward(x)  # (batch, hidden_dim, seq_len)

        # === 4. 下采样 + 保存跳跃连接 ===
        skips: list[np.ndarray] = []
        for l in range(n_down):
            for block in self.down_blocks[l]:
                h = block.forward(h, film_cond)
            skips.append(h.copy())  # 保存当前 level 的输出作为 skip 连接

            # 下采样卷积 (除最后一层)
            if self.down_conv[l] is not None:
                h = self.down_conv[l].forward(h)
                h = np.maximum(h, 0.0)  # ReLU

        # === 5. 瓶颈 ===
        for block in self.bottleneck_resblocks:
            h = block.forward(h, film_cond)

        if self.use_attention:
            h = self._self_attention(h)

        # === 6. 上采样 + 跳跃连接 ===
        # 逆向遍历 down levels
        reversed_levels = list(range(n_down - 1, -1, -1))
        for idx, l in enumerate(reversed_levels):
            # 获取对应的跳跃连接
            skip = skips[l]

            # 如果空间维度不匹配，插值 h 到 skip 的长度
            if h.shape[-1] != skip.shape[-1]:
                h = self._interpolate(h, skip.shape[-1])

            # 拼接 skip 连接
            h = np.concatenate([h, skip], axis=1)  # (batch, in_ch+skip_ch, seq_len)

            # 残差块序列
            for block in self.up_blocks[idx]:
                h = block.forward(h, film_cond)

            # 上采样卷积 (除 level 0)
            if self.up_conv[idx] is not None:
                h = self.up_conv[idx].forward(h)
                h = self._silu(h)

        # === 7. 输出投影 ===
        out = self.output_proj.forward(h)
        return out

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x * (1.0 / (1.0 + np.exp(-x)))

    @staticmethod
    def _interpolate(x: np.ndarray, target_len: int) -> np.ndarray:
        """简单线性插值调整序列长度

        Args:
            x: shape (batch, channels, seq_len)
            target_len: 目标长度

        Returns:
            np.ndarray: shape (batch, channels, target_len)
        """
        batch, channels, seq_len = x.shape
        if seq_len == target_len:
            return x
        # 防御: 零长度输入 → 返回零填充
        if seq_len == 0 or target_len <= 0:
            return np.zeros((batch, channels, max(target_len, 0)), dtype=np.float64)

        indices = np.linspace(0, seq_len - 1, target_len)
        out = np.zeros((batch, channels, target_len), dtype=np.float64)
        for b in range(batch):
            for c in range(channels):
                out[b, c] = np.interp(indices, np.arange(seq_len), x[b, c])
        return out

    def _self_attention(self, x: np.ndarray) -> np.ndarray:
        """简单的 Self-Attention (瓶颈层使用)

        Args:
            x: shape (batch, channels, seq_len)

        Returns:
            np.ndarray: shape 与输入相同
        """
        _batch, channels, _seq_len = x.shape

        bottleneck_ch = self.attn_proj_q.shape[0]
        if channels != bottleneck_ch:
            raise ValueError(
                f"Self-Attention 通道不匹配: 瓶颈层维度 {bottleneck_ch}, "
                f"输入通道 {channels}. 请检查 hidden_dim 与 ch_mult 配置是否一致."
            )

        x_flat = x.transpose(0, 2, 1)  # (batch, seq_len, channels)
        Q = x_flat @ self.attn_proj_q.T
        K = x_flat @ self.attn_proj_k.T
        V = x_flat @ self.attn_proj_v.T

        scale = 1.0 / math.sqrt(channels)
        attn_weights = Q @ K.transpose(0, 2, 1) * scale
        attn_weights = self._softmax(attn_weights)

        out = attn_weights @ V
        out = out @ self.attn_proj_out.T
        out = out.transpose(0, 2, 1)

        return x + out  # 残差连接

    @staticmethod
    def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        x_max = x.max(axis=axis, keepdims=True)
        e_x = np.exp(x - x_max)
        return e_x / e_x.sum(axis=axis, keepdims=True)

    # ------------------------------------------------------------------
    # 权重管理
    # ------------------------------------------------------------------

    def load_weights(self, weight_dict: dict[str, np.ndarray]) -> None:
        for key, val in weight_dict.items():
            if hasattr(self, key):
                setattr(self, key, val)

    def get_weights(self) -> dict[str, np.ndarray]:
        """导出所有权重（包括 Conv1D、ConvTranspose1D、Attention、MLP）"""
        weights: dict[str, np.ndarray] = {}
        # MLP
        weights["time_mlp_w1"] = self.time_mlp_w1.copy()
        weights["time_mlp_b1"] = self.time_mlp_b1.copy()
        weights["time_mlp_w2"] = self.time_mlp_w2.copy()
        weights["time_mlp_b2"] = self.time_mlp_b2.copy()
        weights["cond_mlp_w"] = self.cond_mlp_w.copy()
        weights["cond_mlp_b"] = self.cond_mlp_b.copy()
        # Input/Output projection
        for prefix, layer in [("input_proj", self.input_proj), ("output_proj", self.output_proj)]:
            for k, v in layer.get_parameters().items():
                weights[f"{prefix}_{k}"] = v
        # Down blocks (ResidualBlock1D + Conv1D)
        for l_idx, blocks in enumerate(self.down_blocks):
            for b_idx, block in enumerate(blocks):
                for k, v in block.get_parameters().items():
                    weights[f"down_{l_idx}_{b_idx}_{k}"] = v
            conv = self.down_conv[l_idx]
            if conv is not None:
                for k, v in conv.get_parameters().items():
                    weights[f"down_conv_{l_idx}_{k}"] = v
        # Bottleneck
        for b_idx, block in enumerate(self.bottleneck_resblocks):
            for k, v in block.get_parameters().items():
                weights[f"bottleneck_{b_idx}_{k}"] = v
        if self.use_attention:
            for name in ("attn_proj_q", "attn_proj_k", "attn_proj_v", "attn_proj_out"):
                weights[name] = getattr(self, name).copy()
        # Up blocks (ResidualBlock1D + ConvTranspose1D)
        for u_idx, blocks in enumerate(self.up_blocks):
            for b_idx, block in enumerate(blocks):
                for k, v in block.get_parameters().items():
                    weights[f"up_{u_idx}_{b_idx}_{k}"] = v
            conv = self.up_conv[u_idx]
            if conv is not None:
                for k, v in conv.get_parameters().items():
                    weights[f"up_conv_{u_idx}_{k}"] = v
        return weights


# ==================================================================
# Score Table 缓存
# ==================================================================


class ScoreTable:
    """预计算的 Score Lookup Table

    将常见条件组合下的 score 网络输出缓存起来，
    在条件复用时跳过前向传播，延迟降至 ~10ms。

    使用 LRU (Least Recently Used) 淘汰策略。

    Attributes:
        max_size: 最大缓存条目数
        cache: OrderedDict, key -> (score, usage_count)
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: tuple) -> np.ndarray | None:
        """查询缓存

        Args:
            key: 缓存键, 通常为 (cond_hash, timestep)

        Returns:
            Optional[np.ndarray]: 缓存的 score, 未命中时返回 None
        """
        if key in self._cache:
            # LRU: 移动到末尾 (最近使用)
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            return value
        self._misses += 1
        return None

    def put(self, key: tuple, value: np.ndarray) -> None:
        """存入缓存

        Args:
            key: 缓存键
            value: score 值
        """
        if len(self._cache) >= self.max_size:
            # LRU 淘汰: 移除最早未使用的条目
            self._cache.popitem(last=False)
        self._cache[key] = value

    def get_hit_rate(self) -> float:
        """获取缓存命中率"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def __len__(self) -> int:
        return len(self._cache)

    def __repr__(self) -> str:
        return f"ScoreTable(size={len(self._cache)}/{self.max_size}, hit_rate={self.get_hit_rate():.1%})"
