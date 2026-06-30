"""
Checkpoint Manager — 模型检查点管理

用于扩散模型和 AIF 生成模型的 numpy 权重持久化。
纯 Python + NumPy 实现，零深度学习框架依赖。

用法:
    mgr = CheckpointManager()
    mgr.save(step=42, models={"diffusion": diffuser.model})
    loaded = mgr.load_latest()
"""

import glob
import json
import logging
import os
import time
from typing import Any

import numpy as np

logger = logging.getLogger("checkpoint_manager")


def _get_model_state(model: Any) -> dict[str, np.ndarray] | None:
    """从模型中提取所有可学习参数（支持 TemporalUNet1D 和相似架构）

    遍历模型的所有属性，寻找 Conv1D 和 ConvTranspose1D 层。
    返回 {layer_name: {"W": ndarray, "b": ndarray}} 的字典。
    """
    state: dict[str, Any] = {}
    for attr_name in dir(model):
        if attr_name.startswith("_"):
            continue
        try:
            layer = getattr(model, attr_name)
            if layer is None:
                continue
        except Exception:
            continue

        # Conv1D / ConvTranspose1D
        if hasattr(layer, "W") and hasattr(layer, "b") and hasattr(layer, "in_channels"):
            w = getattr(layer, "W", None)
            b = getattr(layer, "b", None)
            if isinstance(w, np.ndarray) and isinstance(b, np.ndarray):
                state[attr_name] = {
                    "W_shape": list(w.shape),
                    "b_shape": list(b.shape),
                    "W": w.tolist(),
                    "b": b.tolist(),
                }

    # 递归搜索嵌套对象（如 down_blocks, up_blocks 等列表中的层）
    for list_attr in ("down_blocks", "up_blocks", "bottleneck_resblocks"):
        container = getattr(model, list_attr, None)
        if container is None:
            continue
        if isinstance(container, (list, tuple)):
            for idx, block in enumerate(container):
                block_state = _get_model_state(block)
                if block_state is not None:
                    for k, v in block_state.items():
                        state[f"{list_attr}[{idx}].{k}"] = v

    return state if state else None


# ====================================================================
# [FIX 2026-06-26] 新参数收集/恢复函数
# 参考 PyTorch state_dict() / load_state_dict() 设计模式
#
# 递归遍历模型所有属性，支持任意深度嵌套:
#   - Conv1D/ConvTranspose1D (直接属性)
#   - np.ndarray (直接属性)
#   - list/tuple 任意深度嵌套
#   - 普通对象的非私有属性
# ====================================================================

_SKIP_TYPES = (int, float, str, bool, bytes, type(None))


def _collect_params(model: Any, prefix: str = "") -> dict[str, np.ndarray]:
    """递归收集模型中所有可训练参数（支持任意深度嵌套）

    参考 PyTorch state_dict() 设计模式。

    处理 4 种类型:
      1. Conv1D/ConvTranspose1D → 保存 "层名/W", "层名/b"
      2. np.ndarray → 直接保存为 "层名"
      3. list/tuple → 递归每个元素，key 加 [idx]
      4. 其他对象 → 递归每个非私有、非 callable、非基础类型的属性

    Args:
        model: 任意对象（TemporalUNet1D、ResBlock、list 等）
        prefix: key 前缀（递归时用）

    Returns:
        {"input_proj/W": ndarray, "input_proj/b": ndarray, "time_mlp_w1": ndarray, ...}
    """
    params: dict[str, np.ndarray] = {}

    # 类型 1: Conv1D / ConvTranspose1D
    if hasattr(model, "W") and hasattr(model, "b") and hasattr(model, "in_channels"):
        w = getattr(model, "W", None)
        b = getattr(model, "b", None)
        if isinstance(w, np.ndarray) and isinstance(b, np.ndarray):
            params[f"{prefix}W"] = w.copy()
            params[f"{prefix}b"] = b.copy()
        return params

    # 类型 2: np.ndarray
    if isinstance(model, np.ndarray):
        params[prefix.rstrip(".")] = model.copy()
        return params

    # 类型 3: list / tuple
    if isinstance(model, (list, tuple)):
        for idx, item in enumerate(model):
            item_params = _collect_params(item, f"{prefix}[{idx}].")
            params.update(item_params)
        return params

    # 类型 4: 普通对象 → 遍历属性
    for attr_name in dir(model):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(model, attr_name)
        except Exception:
            continue
        if attr is None or callable(attr) or isinstance(attr, _SKIP_TYPES):
            continue
        item_params = _collect_params(attr, f"{prefix}{attr_name}.")
        params.update(item_params)

    return params


def _assign_params(
    model: Any, params: dict[str, np.ndarray], prefix: str = "",
) -> int:
    """递归将参数恢复到模型中（_collect_params 的逆操作）

    Args:
        model: 模型对象
        params: _collect_params 输出的参数字典
        prefix: 当前前缀（递归用）

    Returns:
        int: 成功恢复的参数数量
    """
    restored = 0

    # 类型 1: Conv1D / ConvTranspose1D → W 和 b
    if hasattr(model, "W") and hasattr(model, "b"):
        w_key = f"{prefix}W"
        b_key = f"{prefix}b"
        if w_key in params and b_key in params:
            w_val = params[w_key]
            b_val = params[b_key]
            if model.W.shape == w_val.shape and model.b.shape == b_val.shape:
                model.W = w_val.copy()
                model.b = b_val.copy()
                restored += 1
        return restored

    # 类型 2: np.ndarray → 标记匹配（由外层 setattr 处理）
    if isinstance(model, np.ndarray):
        key = prefix.rstrip(".")
        if key in params and model.shape == params[key].shape:
            return 1
        return 0

    # 类型 3: list / tuple
    if isinstance(model, (list, tuple)):
        for idx in range(len(model)):
            restored += _assign_params(
                model[idx], params, f"{prefix}[{idx}].",
            )
        return restored

    # 类型 4: 普通对象 → 遍历属性
    for attr_name in dir(model):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(model, attr_name)
        except Exception:
            continue
        if attr is None or callable(attr) or isinstance(attr, _SKIP_TYPES):
            continue

        # np.ndarray → 直接 setattr
        if isinstance(attr, np.ndarray):
            key = f"{prefix}{attr_name}"
            if key in params and attr.shape == params[key].shape:
                setattr(model, attr_name, params[key].copy())
                restored += 1
                continue

        restored += _assign_params(attr, params, f"{prefix}{attr_name}.")

    return restored


def _set_model_state(model: Any, state: dict[str, Any]) -> int:
    """将 checkpoint 中的参数恢复到模型中

    Args:
        model: TemporalUNet1D 或兼容架构
        state: 从 _get_model_state 或 checkpoint 加载的 dict

    Returns:
        int: 成功恢复的参数数量
    """
    restored = 0
    for attr_name, param_data in state.items():
        # 解析 attr_name 定位到具体层
        parts = attr_name.split(".")
        target = model
        try:
            for part in parts:
                if "[" in part and "]" in part:
                    # 处理 list[index] 语法
                    base = part[: part.index("[")]
                    idx = int(part[part.index("[") + 1 : part.index("]")])
                    target = getattr(target, base)[idx]
                else:
                    target = getattr(target, part)

            w = np.array(param_data["W"], dtype=np.float64)
            b = np.array(param_data["b"], dtype=np.float64)

            if hasattr(target, "W") and hasattr(target, "b"):
                if target.W.shape == w.shape and target.b.shape == b.shape:
                    target.W = w
                    target.b = b
                    restored += 1
                else:
                    logger.warning(
                        "[Checkpoint] 形状不匹配: %s, "
                        "期望 W=%s b=%s, 实际 W=%s b=%s",
                        attr_name,
                        list(target.W.shape), list(target.b.shape),
                        list(w.shape), list(b.shape),
                    )
        except (AttributeError, IndexError, KeyError, ValueError) as e:
            logger.debug("[Checkpoint] 跳过 %s: %s", attr_name, e)

    return restored


class CheckpointManager:
    """检查点管理器

    管理扩散模型和 AIF 生成模型的保存和加载。
    自动清理旧版本，保留最近 N 版。

    Args:
        base_dir: checkpoint 存储目录
        keep_last: 保留的最近版本数
    """

    def __init__(self, base_dir: str = "checkpoints", keep_last: int = 3):
        self.base_dir = base_dir
        self.keep_last = keep_last
        os.makedirs(base_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def save(self, step: int, models: dict[str, Any], metadata: dict | None = None) -> str:
        """保存所有模型的 checkpoint

        Args:
            step: 当前训练步数
            models: {"diffusion": model, "aif_gm": model} 格式
            metadata: 额外元数据（loss, epoch 等）

        Returns:
            str: 保存的文件路径
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_data: dict[str, Any] = {
            "step": step,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "models": {},
        }

        for name, model in models.items():
            state = _collect_params(model)
            if state:
                save_data["models"][name] = state
                logger.info(
                    "[Checkpoint] 已保存 %s: %d 个参数 (新格式)",
                    name, len(state),
                )
            else:
                logger.warning("[Checkpoint] %s: 无可保存参数", name)

        filename = f"checkpoint_step{step}_{timestamp}.npz"
        filepath = os.path.join(self.base_dir, filename)

        # 使用 np.savez_compressed 保存为压缩 npz
        arrays: dict[str, np.ndarray] = {}
        for model_name, model_state in save_data["models"].items():
            for param_key, param_value in model_state.items():
                # param_key 如 "input_proj/W", "time_mlp_w1"
                arr_key = f"{model_name}/{param_key}"
                arrays[arr_key] = param_value.astype(np.float64)

        # 保存元数据为 JSON
        meta_path = os.path.join(self.base_dir, f"meta_step{step}_{timestamp}.json")
        with open(meta_path, "w") as f:
            json.dump({
                "step": step,
                "timestamp": timestamp,
                "model_names": list(save_data["models"].keys()),
                "metadata": metadata or {},
            }, f, indent=2)

        np.savez_compressed(filepath, **arrays)
        logger.info("[Checkpoint] ✅ 已保存: %s (%.1f KB)", filename, os.path.getsize(filepath) / 1024)

        self._cleanup_old()
        return filepath

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_latest(self) -> dict[str, dict[str, Any]]:
        """加载最新的 checkpoint

        Returns:
            {"diffusion": {"W_...": ..., ...}, "aif_gm": ...} 格式的 dict
            如果没有可用 checkpoint 则返回空 dict
        """
        meta_files = sorted(glob.glob(os.path.join(self.base_dir, "meta_step*.json")))
        if not meta_files:
            logger.info("[Checkpoint] 未找到 checkpoint，使用随机初始化")
            return {}

        latest_meta = meta_files[-1]
        with open(latest_meta) as f:
            meta = json.load(f)

        step = meta["step"]
        timestamp = meta["timestamp"]
        model_names = meta["model_names"]

        # 查找对应的 npz 文件
        npz_path = os.path.join(self.base_dir, f"checkpoint_step{step}_{timestamp}.npz")
        if not os.path.exists(npz_path):
            logger.warning("[Checkpoint] ⚠️ 找不到 %s，尝试其他文件", npz_path)
            npz_files = sorted(glob.glob(os.path.join(self.base_dir, "checkpoint_step*.npz")))
            if not npz_files:
                return {}
            npz_path = npz_files[-1]

        loaded = np.load(npz_path, allow_pickle=False)
        models_data: dict[str, dict[str, np.ndarray]] = {}

        for model_name in model_names:
            model_params: dict[str, np.ndarray] = {}
            prefix = f"{model_name}/"

            for key in loaded.keys():
                if key.startswith(prefix):
                    # key = "diffusion/input_proj/W" → param_key = "input_proj/W"
                    param_key = key[len(prefix):]
                    model_params[param_key] = loaded[key]

            models_data[model_name] = model_params
            logger.info(
                "[Checkpoint] 已加载 %s: %d 个参数 (新格式)",
                model_name, len(model_params),
            )

        logger.info("[Checkpoint] ✅ checkpoint 加载完成 (step=%d)", step)
        return models_data

    # ------------------------------------------------------------------
    # 恢复到模型
    # ------------------------------------------------------------------

    def restore(self, model: Any, model_name: str, models_data: dict[str, Any]) -> int:
        """将加载的 checkpoint 参数恢复到模型中

        Args:
            model: 模型实例（TemporalUNet1D 等）
            model_name: "diffusion" 或 "aif_gm"
            models_data: load_latest() 的返回值

        Returns:
            int: 成功恢复的参数数量
        """
        params = models_data.get(model_name)
        if not params:
            logger.warning("[Checkpoint] %s: 无 checkpoint 数据", model_name)
            return 0

        restored = _assign_params(model, params)
        logger.info("[Checkpoint] %s: 已恢复 %d 个参数", model_name, restored)
        return restored

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _cleanup_old(self):
        """只保留最近 keep_last 个版本"""
        meta_files = sorted(glob.glob(os.path.join(self.base_dir, "meta_step*.json")))
        if len(meta_files) <= self.keep_last:
            return

        for old_meta in meta_files[:-self.keep_last]:
            with open(old_meta) as f:
                meta = json.load(f)
            step = meta["step"]
            timestamp = meta["timestamp"]

            npz_path = os.path.join(self.base_dir, f"checkpoint_step{step}_{timestamp}.npz")
            for p in (old_meta, npz_path):
                if os.path.exists(p):
                    os.remove(p)
                    logger.debug("[Checkpoint] 清理旧版本: %s", os.path.basename(p))
