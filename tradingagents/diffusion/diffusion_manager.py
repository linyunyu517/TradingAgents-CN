# tradingagents/diffusion/diffusion_manager.py
"""
DiffusionManager — 扩散模型统一入口管理器

采用单例模式，管理所有扩散子模块的生命周期：
    - DiffusionConfig: 全局配置
    - DDIMSampler: 确定性采样器
    - ScoreNetwork: 去噪网络 (按需加载)
    - ScoreTable: 预计算缓存

提供统一的 sample() 接口，失败时自动退化为均匀先验。
"""

from __future__ import annotations

import logging

import numpy as np

from .config import DiffusionConfig
from .ddim_sampler import ddim_sampling_loop, sample_with_uncertainty
from .score_network import ScoreNetwork, ScoreTable
from .uniform_prior import is_uniform_prior_applicable, uniform_prior

logger = logging.getLogger(__name__)


class DiffusionManager:
    """扩散模型管理器 — 单例模式

    管理所有扩散子模块的生命周期，提供统一的采样接口。
    当扩散推理失败时，自动退化为均匀先验（非降级机制）。

    使用方式:
        >>> config = DiffusionConfig()
        >>> manager = DiffusionManager(config)
        >>> samples = manager.sample("default", (32, 4, 32), cond=condition)
    """

    _instance: DiffusionManager | None = None

    def __new__(cls, config: DiffusionConfig | None = None) -> DiffusionManager:
        """单例模式: 全局只有一个 DiffusionManager 实例

        Args:
            config: 扩散模型配置 (仅首次调用时生效)

        Returns:
            DiffusionManager: 共享实例
        """
        if cls._instance is None:
            if config is None:
                config = DiffusionConfig()
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(self, config: DiffusionConfig | None = None) -> None:
        """初始化管理器

        Args:
            config: 扩散模型配置
        """
        if self._initialized:
            return

        self.config = config or DiffusionConfig()

        # === 子模块 ===
        # DDIM 采样器 (无状态工具函数，直接引用模块函数)
        self.sampler = None  # 保留为属性兼容性

        # Score Network 模型缓存 {name: ScoreNetwork}
        self._models: dict[str, ScoreNetwork] = {}

        # Score Table 缓存
        if self.config.use_score_cache:
            self.score_table = ScoreTable(max_size=self.config.score_cache_size)
        else:
            self.score_table = None

        # 是否已启用
        self._enabled = True

        self._initialized = True
        logger.info(
            "DiffusionManager 初始化完毕: config=%s",
            self.config,
        )

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """管理器是否已启用"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    # ------------------------------------------------------------------
    # 模型管理
    # ------------------------------------------------------------------

    def register_model(
        self,
        name: str,
        model: ScoreNetwork,
    ) -> None:
        """注册一个 Score Network 模型

        Args:
            name: 模型名称 (如 "default", "generator", "decision_diffuser")
            model: ScoreNetwork 实例
        """
        self._models[name] = model
        logger.info("注册扩散模型 '%s': %s", name, type(model).__name__)

    def get_model(self, name: str) -> ScoreNetwork | None:
        """获取已注册的 Score Network

        Args:
            name: 模型名称

        Returns:
            Optional[ScoreNetwork]: 模型实例，未找到时返回 None
        """
        return self._models.get(name)

    def has_model(self, name: str) -> bool:
        """检查指定名称的模型是否已注册"""
        return name in self._models

    def list_models(self) -> list:
        """列出所有已注册的模型名称"""
        return list(self._models.keys())

    # ------------------------------------------------------------------
    # 统一采样接口
    # ------------------------------------------------------------------

    def sample(
        self,
        model_name: str,
        shape: tuple[int, ...],
        cond: np.ndarray | None = None,
        use_cache: bool = True,
    ) -> np.ndarray:
        """统一采样接口

        执行 DDIM 确定性采样，失败时自动退化为均匀先验。

        Args:
            model_name: 模型名称，用于查找已注册的 ScoreNetwork
            shape: 采样形状 (batch, *data_dim)
            cond: 条件向量, shape (batch, cond_dim) 或 None
            use_cache: 是否尝试从 Score Table 获取缓存结果

        Returns:
            np.ndarray: 生成的样本，shape 与输入 shape 相同
                当扩散推理失败时，返回均匀先验样本
        """
        # 1. 检查模型是否可用（不允许静默降级）
        model = self.get_model(model_name)
        if model is None:
            error_msg = (
                f"扩散模型 '{model_name}' 未注册 (shape={shape})，"
                f"退化路径已被禁用。请先调用 register_model() 注册模型。"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 2. 尝试从 Score Table 缓存获取
        if use_cache and self.score_table is not None and cond is not None:
            cache_key = (model_name, cond.tobytes())
            cached = self.score_table.get(cache_key)
            if cached is not None and cached.shape == shape:
                logger.debug("Score Table 命中: model='%s'", model_name)
                return cached

        # 3. 执行 DDIM 采样（不允许静默降级：任何故障都会向上传播）
        result = ddim_sampling_loop(
            model_denoise_fn=model.forward,
            shape=shape,
            config=self.config,
            cond=cond,
            return_all_steps=False,
        )

        # 4. 有效性检查（不允许静默降级：NaN/Inf 输出直接报错）
        if is_uniform_prior_applicable(result):
            error_msg = (
                f"扩散采样输出无效 (NaN/Inf/flat): model='{model_name}', "
                f"shape={shape}，退化路径已被禁用。请检查 ScoreNetwork 权重或输入数据。"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 5. 缓存结果
        if use_cache and self.score_table is not None and cond is not None:
            self.score_table.put(cache_key, result.copy())

        return result

    def sample_with_uncertainty(
        self,
        model_name: str,
        shape: tuple[int, ...],
        cond: np.ndarray | None = None,
        n_samples: int = 16,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """带不确定性量化的采样

        执行多次 DDIM 采样，返回均值、标准差和所有样本。

        Args:
            model_name: 模型名称
            shape: 采样形状
            cond: 条件向量
            n_samples: 采样次数

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]:
                (mean, std, all_samples)
        """
        model = self.get_model(model_name)
        if model is None:
            logger.warning(
                "扩散模型 '%s' 未注册，不确定性量化退化为均匀先验",
                model_name,
            )
            samples = np.stack([uniform_prior(shape) for _ in range(n_samples)], axis=0)
            mean = samples.mean(axis=0)
            std = samples.std(axis=0)
            return mean, std, samples

        try:
            return sample_with_uncertainty(
                model_denoise_fn=model.forward,
                shape=shape,
                config=self.config,
                cond=cond,
                n_samples=n_samples,
            )
        except Exception as e:
            logger.error(
                "不确定性量化失败: model='%s', error=%s, 退化为均匀先验",
                model_name,
                e,
            )
            samples = np.stack([uniform_prior(shape) for _ in range(n_samples)], axis=0)
            mean = samples.mean(axis=0)
            std = samples.std(axis=0)
            return mean, std, samples

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置管理器状态 (清空模型缓存和 Score Table)"""
        self._models.clear()
        if self.score_table is not None:
            self.score_table.clear()
        logger.info("DiffusionManager 已重置")

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例 (主要用于测试)"""
        cls._instance = None

    def __repr__(self) -> str:
        return f"DiffusionManager(config={self.config}, models={list(self._models.keys())}, enabled={self._enabled})"


# ------------------------------------------------------------------
# 便捷工厂函数
# ------------------------------------------------------------------


def get_diffusion_manager(config: DiffusionConfig | None = None) -> DiffusionManager:
    """获取 DiffusionManager 单例

    便捷函数，等价于 DiffusionManager(config)。

    Args:
        config: 扩散模型配置

    Returns:
        DiffusionManager: 全局唯一的 DiffusionManager 实例
    """
    return DiffusionManager(config)
