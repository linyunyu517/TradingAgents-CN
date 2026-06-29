# 扩散模型集成改造 — 变更清单

## 概述

本项目将扩散模型（Diffusion Models）集成到 TradingAgents-CN 量化交易系统中，提供了六大核心模块：扩散生成模型（A）、交易决策扩散（B）、风险情景生成（C）、CSDI 数据补全（D）、DDIM 采样器（E）、以及扩散管理器与退化机制（F）。通过 **Graph 工作流**、**配置系统**、**数据接口**实现无缝集成。

---

## 新增文件（11 个）

| # | 文件路径 | 模块 | 说明 |
|---|---------|------|------|
| 1 | `tradingagents/diffusion/__init__.py` | 包入口 | 公开 API 导出（所有模块符号） |
| 2 | `tradingagents/diffusion/config.py` | E | `DiffusionConfig`：扩散模型配置（时间步数、噪声调度、隐藏维度、CFG 缩放等） |
| 3 | `tradingagents/diffusion/ddim_sampler.py` | E | `DDIMSampler` / `ddim_step` / `ddim_sampling_loop`：去噪扩散隐式采样 |
| 4 | `tradingagents/diffusion/score_network.py` | E | `TemporalUNet1D` / `ScoreTable`：时态 U-Net 分数网络 |
| 5 | `tradingagents/diffusion/uniform_prior.py` | F | `uniform_prior` / `is_uniform_prior_applicable`：均匀先验退化机制 |
| 6 | `tradingagents/diffusion/diffusion_manager.py` | F | `DiffusionManager` / `get_diffusion_manager`：全局管理器，模型注册/采样/不确定性量化 |
| 7 | `tradingagents/diffusion/diffusion_generative_model.py` | A | `DiffusionGenerativeModel`：扩散生成模型（市场分布预测） |
| 8 | `tradingagents/diffusion/diffusion_portfolio_optimizer.py` | A-ext | `DiffusionPortfolioOptimizer`：基于扩散的投资组合优化 |
| 9 | `tradingagents/diffusion/diffusion_imputer.py` | D | `CSDIImputer` / `EulerMaruyamaSDE`：CSDI 条件扩散缺失值补全 |
| 10 | `tradingagents/diffusion/diffusion_trader.py` | B | `TradingDecisionDiffuser`：交易决策扩散（专家对抗/融合） |
| 11 | `tradingagents/diffusion/diffusion_scenario.py` | C | `DiffusionScenarioGenerator`：扩散情景生成器（VaR/CVaR/压力测试） |

---

## 修改文件（6 个）

| # | 文件路径 | 修改内容 |
|---|---------|---------|
| 1 | `tradingagents/__init__.py` | 添加 `from .diffusion import DiffusionManager, get_diffusion_manager` |
| 2 | `tradingagents/default_config.py` | 添加扩散相关配置项：`diffusion_enabled`、`diffusion_weight`、`diffusion_num_timesteps`、`diffusion_csdi_enabled`、`diffusion_generative_enabled` |
| 3 | `tradingagents/dataflows/interface.py` | 添加 `_maybe_csdi_impute()` 函数，根据配置条件调用 CSDI 补全 |
| 4 | `tradingagents/graph/setup.py` | 添加 `diffusion_advisor_node`、`fusion_node` 两个 LangGraph 节点，按配置动态集成到交易工作流 |
| 5 | `tradingagents/hpc_loop/hpc_state.py` | 在 `HPCState` 中添加 `diffusion_decision` 字段 |
| 6 | `tradingagents/hpc_loop/__init__.py` | 添加扩散符号重导出 |

---

## 架构图

```
src/tradingagents/
├── diffusion/                          # [NEW] 扩散模块包
│   ├── __init__.py                     # 公开 API
│   ├── config.py                       # DiffusionConfig
│   ├── ddim_sampler.py                 # DDIMSampler
│   ├── score_network.py                # TemporalUNet1D
│   ├── uniform_prior.py                # 均匀先验退化
│   ├── diffusion_manager.py            # [F] 单例管理器
│   ├── diffusion_generative_model.py   # [A] 生成模型
│   ├── diffusion_portfolio_optimizer.py# [A-ext] 投资组合优化
│   ├── diffusion_imputer.py            # [D] CSDI 补全
│   ├── diffusion_trader.py             # [B] 决策扩散
│   └── diffusion_scenario.py           # [C] 情景生成
├── default_config.py                   # [MODIFIED] 扩散配置键
├── dataflows/interface.py              # [MODIFIED] CSDI 集成
├── graph/setup.py                      # [MODIFIED] Graph 节点
└── hpc_loop/                           # [MODIFIED] HPC 状态集成
```

## 集成点清单

| 集成点 | 类型 | 文件 | 触发条件 |
|--------|------|------|---------|
| 配置开关 | 静态 | `default_config.py` | `diffusion_enabled=True` |
| CSDI 补全 | 动态调用 | `interface.py` → `diffusion_imputer.py` | `diffusion_csdi_enabled=True` 且数据有 NaN |
| Graph Advisor | LangGraph 节点 | `setup.py` → `diffusion_trader.py` | `diffusion_enabled=True` |
| 决策融合 | 融合节点 | `setup.py` | 权重 `diffusion_weight` 控制 |
| HPC 状态 | 类型字段 | `hpc_state.py` | `diffusion_decision` 字段 |
| 全局管理器 | 单例 | `diffusion_manager.py` | 任意调用 `get_diffusion_manager()` |
| 退化机制 | 异常安全 | `diffusion_manager.py` | 模型未注册 → `uniform_prior` |

## 配置项

```python
DEFAULT_CONFIG = {
    "diffusion_enabled": True,            # 全局开关
    "diffusion_weight": 0.3,             # 决策融合权重
    "diffusion_num_timesteps": 50,       # DDIM 采样步数
    "diffusion_csdi_enabled": False,     # CSDI 补全（性能敏感）
    "diffusion_generative_enabled": False, # 生成模型（预留）
}
```

## 依赖

- `numpy` — 所有模块的基础数值计算
- 无深度学习框架依赖（纯 NumPy 实现，可后续迁移至 PyTorch）

---

*生成时间: 2026-06-08*
