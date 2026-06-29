# 变异测试: _route_aif_observe + 条件边界变异 (<=↔<, ==↔!=)
# 原始文件: setup.py
import logging
import sys

logger = logging.getLogger(__name__)

sys.path.insert(0, r"D:\AI-Projects\TradingAgents-CN_v1.0.1")


# 模拟原始模块上下文（减少导入错误）
def _route_aif_observe(state) -> str:
    """AIF_Observe 条件路由，解决双静态出边导致的 InvalidUpdateError (Bug-New-006)

    AIF_Observe 在 Fusion 模式中可能被两条路径同时访问:
    - 首次通过 (Section B, _aif_iteration_count == 0): HPC_PredictionError → AIF_Observe → AIF_UpdateBelief
    - 迭代循环 (Section C, _aif_iteration_count > 0): AIF_UpdateBelief → AIF_Observe → AIF_LLMPrior

    两条静态出边会导致 LangGraph 在同一 superstep 中并行写入 aif_state，
    从而触发 "Can receive only one value per step" 错误。

    此条件边确保同一时间只有一条出边生效，完全串行化 AIF_Observe 的出边。

    Returns:
        str: "AIF_UpdateBelief" (首次通过) 或 "AIF_LLMPrior" (迭代循环)
    """
    _aif_iter = state.get("_aif_iteration_count", 0)
    if _aif_iter != 0:
        logger.info("[AIF Route] AIF_Observe 首次通过路径 → AIF_UpdateBelief")
        return "AIF_UpdateBelief"
    logger.info(f"[AIF Route] AIF_Observe 迭代循环路径 (iter={_aif_iter}) → AIF_LLMPrior")
    return "AIF_LLMPrior"


# 简短的自检
if not callable(_route_aif_observe):
    raise TypeError("变异函数不可调用")
