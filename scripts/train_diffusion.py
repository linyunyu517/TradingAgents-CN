#!/usr/bin/env python3
"""
扩散模型训练脚本

从 Tushare 下载历史数据，训练扩散模型的 ScoreNetwork。
训练后的参数保存为 checkpoint，供交易系统启动时自动加载。

用法:
    python scripts/train_diffusion.py                          # 默认配置
    python scripts/train_diffusion.py --epochs 20 --batch 128   # 自定义
    python scripts/train_diffusion.py --symbols 000001 600519   # 指定股票

参考:
    - TimeGrad (Rasul+ 2021): Autoregressive Denoising Diffusion Models
    - CSDI (Tashiro+ 2021): Conditional Score-based Diffusion Models
"""

import argparse
import logging
import os
import re
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.diffusion.score_network import TemporalUNet1D
from tradingagents.diffusion.config import DiffusionConfig
from tradingagents.diffusion.train_diffusion import DiffusionTrainer, build_market_dataset
from tradingagents.utils.checkpoint_manager import CheckpointManager

# ====================================================================
# [FIX 2026-06-26] RD-Agent 超参数同步器
#
# 在 --rd-mode 模式下，读取 RD-Agent 的 DiffusionConfig 并提取超参数。
# 使用正则解析，不依赖 import / PyTorch，无副作用。
#
# 同步的参数:
#   learning_rate  → --lr
#   batch_size     → --batch
#   num_epochs     → --epochs
#   num_timesteps  → --timesteps  (训练扩散步数)
#   ddim_steps     → config.num_timesteps  (推理DDIM步数)
#   cfg_scale      → config.cfg_scale  (可选同步)
# ====================================================================

_RD_AGENT_CONFIG_CANDIDATES = [
    "/root/RD-Agent/rdagent/core/diffusion/config.py",
    "/mnt/d/RD_Agent/RD-Agent/rdagent/core/diffusion/config.py",
]


def _read_rd_agent_config() -> str | None:
    """读取 RD-Agent 配置文件内容

    遍历候选路径列表，返回第一个成功读取的文件内容。
    所有路径都不存在时返回 None。

    Returns:
        str | None: 文件内容或 None
    """
    for path in _RD_AGENT_CONFIG_CANDIDATES:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                _log = logging.getLogger("train_diffusion")
                _log.info("[RD-Sync] 读取配置: %s (%d bytes)", path, len(content))
                return content
            except (OSError, PermissionError) as e:
                _log = logging.getLogger("train_diffusion")
                _log.warning("[RD-Sync] 读取 %s 失败: %s", path, e)
                continue
    return None


def _extract_params(content: str) -> dict[str, float | int]:
    """从 RD-Agent 的 dataclass 定义中提取数值参数字段

    匹配缩进 level 为 4 空格、带 int/float 类型注解的字段定义。
    只提取数值，跳过字符串、元组、表达式。

    Args:
        content: config.py 的文本内容

    Returns:
        字典: {字段名: 数值}
    """
    params: dict[str, float | int] = {}
    # 精确匹配: 4空格缩进 + field_name: int|float = value
    for m in re.finditer(r'^\s{4}(\w+)\s*:\s*(?:int|float)\s*=\s*([^#\n]+)', content, re.MULTILINE):
        name = m.group(1)
        raw = m.group(2).strip().rstrip(",")
        try:
            if "." in raw or "e" in raw.lower():
                params[name] = float(raw)
            else:
                params[name] = int(raw)
        except ValueError:
            continue
    return params


def _sync_rd_agent_params() -> dict[str, float | int]:
    """主入口：读取 RD-Agent 配置并返回可同步的参数

    Returns:
        参数字典（失败时返回空 dict）
    """
    content = _read_rd_agent_config()
    if content is None:
        _log = logging.getLogger("train_diffusion")
        _log.warning("[RD-Sync] ⚠️ 未找到 RD-Agent 配置，使用默认超参数")
        return {}

    params = _extract_params(content)
    _log = logging.getLogger("train_diffusion")
    _log.info("[RD-Sync] 提取到 %d 个可同步参数", len(params))
    return params


def main():
    parser = argparse.ArgumentParser(description="训练扩散模型")
    parser.add_argument("--epochs", type=int, default=5, help="训练轮数")
    parser.add_argument("--batch", type=int, default=64, help="批次大小")
    parser.add_argument("--symbols", type=str, nargs="+", default=None, help="股票代码列表")
    parser.add_argument("--years", type=int, default=3, help="历史数据年数")
    parser.add_argument("--seq-len", type=int, default=20, help="序列长度")
    parser.add_argument("--feat-dim", type=int, default=16, help="特征维度")
    parser.add_argument("--lr", type=float, default=1e-4, help="学习率")
    parser.add_argument("--timesteps", type=int, default=100, help="扩散步数")
    parser.add_argument("--save-every", type=int, default=100, help="保存间隔")

    # RD-Agent 同步参数
    parser.add_argument("--rd-mode", action="store_true",
                        help="从 RD-Agent 同步超参数 (learning_rate/batch_size/num_epochs/num_timesteps/ddim_steps)")
    parser.add_argument("--rd-skip-cfg", action="store_true",
                        help="--rd-mode 时不同步 cfg_scale，保留脚本默认值")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("train_diffusion")

    # ===== RD-Agent 超参数同步 (在 parse_args 之后、使用 args 之前) =====
    _rd_params: dict[str, float | int] = {}
    if args.rd_mode:
        _rd_params = _sync_rd_agent_params()
        if _rd_params:
            # 参数映射表: RD-Agent 字段名 → (我们的属性名, 类型转换)
            _FIELD_MAP = {
                "learning_rate": ("lr", float),
                "batch_size": ("batch", int),
                "num_epochs": ("epochs", int),
                "num_timesteps": ("timesteps", int),
            }
            _synced: list[str] = []
            for rd_key, (our_attr, cast) in _FIELD_MAP.items():
                if rd_key in _rd_params:
                    setattr(args, our_attr, cast(_rd_params[rd_key]))
                    _synced.append(f"--{our_attr}={cast(_rd_params[rd_key])}")
            if _synced:
                logger.info("[RD-Sync] ✅ 已同步 %d 个超参数: %s", len(_synced), ", ".join(_synced))
            else:
                logger.warning("[RD-Sync] ⚠️ 参数同步结果为空")
        else:
            logger.warning("[RD-Sync] ⚠️ 参数同步失败，使用脚本默认值")

    # ===== 构建数据集 =====
    logger.info("=" * 60)
    logger.info("扩散模型训练开始")
    logger.info(f"  股票池: {args.symbols or '默认蓝筹'}")
    logger.info(f"  数据年数: {args.years}")
    logger.info(f"  序列长度: {args.seq_len}")
    logger.info(f"  特征维度: {args.feat_dim}")
    logger.info(f"  训练轮数: {args.epochs}")
    logger.info(f"  批次大小: {args.batch}")
    logger.info(f"  学习率: {args.lr}")
    logger.info(f"  训练扩散步数: {args.timesteps}")
    if args.rd_mode and _rd_params:
        logger.info(f"  [RD-Sync] 以上 4 个参数已从 RD-Agent 同步")
        if "ddim_steps" in _rd_params:
            logger.info(f"  [RD-Sync] 推理 DDIM 步数: {int(_rd_params['ddim_steps'])} (来自 RD-Agent)")
    logger.info("=" * 60)

    samples, targets = build_market_dataset(
        symbols=args.symbols or [
            "000001", "000002", "000333", "000651", "000858",
            "002415", "300750", "600036", "600519", "600887",
        ],
        years=args.years,
        seq_len=args.seq_len,
        feat_dim=args.feat_dim,
    )

    logger.info(f"数据集大小: {len(samples)} 样本")

    # ===== 初始化模型 =====
    # hidden_dim 和 cond_dim 必须与 diffusion_trader.py 的 DiffusionConfig 默认值一致
    # diffusion_trader.py 使用默认 config (hidden_dim=128, cond_dim=32)
    # 推理 DDIM 步数: --rd-mode 时优先使用 RD-Agent 的 ddim_steps(20)
    _infer_steps = args.timesteps
    if args.rd_mode and "ddim_steps" in _rd_params:
        _infer_steps = int(_rd_params["ddim_steps"])
        logger.info("[RD-Sync] ℹ️ DDIM 推理步数: %d (来自 RD-Agent ddim_steps=%d)", _infer_steps, int(_rd_params["ddim_steps"]))

    config = DiffusionConfig(
        num_timesteps=_infer_steps,
        hidden_dim=128,  # 必须与 DiffusionConfig 默认值一致 (默认128)
        cond_dim=32,     # 必须与 DiffusionConfig 默认值一致 (默认32)
    )

    # [可选] 同步 cfg_scale
    if args.rd_mode and not args.rd_skip_cfg and "cfg_scale" in _rd_params:
        config.cfg_scale = float(_rd_params["cfg_scale"])
        logger.info("[RD-Sync] ℹ️ CFG 引导强度: %.1f (来自 RD-Agent)", config.cfg_scale)

    model = TemporalUNet1D(
        config=config,
        in_channels=args.feat_dim,
        out_channels=args.feat_dim,
    )

    # ===== 训练 =====
    checkpoint_mgr = CheckpointManager(
        base_dir="checkpoints",
        keep_last=3,
    )

    trainer = DiffusionTrainer(
        model=model,
        num_timesteps=args.timesteps,
        lr=args.lr,
    )

    # 加载已有数据
    trainer.samples = samples
    trainer.targets = targets
    trainer.seq_len = args.seq_len
    trainer.feat_dim = args.feat_dim

    # 执行训练
    history = trainer.train(
        epochs=args.epochs,
        batch_size=args.batch,
        save_every=args.save_every,
        checkpoint_mgr=checkpoint_mgr,
    )

    logger.info("=" * 60)
    logger.info("训练完成!")
    logger.info(f"  最终 loss: {history['loss'][-1]:.6f}" if history['loss'] else "  无损失记录")
    logger.info(f"  Checkpoint 已保存到: {os.path.abspath('checkpoints')}")
    logger.info("=" * 60)

    # 验证加载
    loaded = checkpoint_mgr.load_latest()
    if loaded:
        logger.info(f"✅ 验证: checkpoint 加载成功，包含 {list(loaded.keys())}")
    else:
        logger.warning("⚠️ 验证: checkpoint 加载失败")


if __name__ == "__main__":
    main()
