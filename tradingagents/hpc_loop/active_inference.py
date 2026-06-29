# TradingAgents/hpc_loop/active_inference.py
"""
主动推理引擎 (Active Inference Engine)

实现基于期望自由能 (Expected Free Energy, EFE) 的行动选择框架。
每个候选交易动作的 EFE 分解为认知价值 (Epistemic Value) 和实用价值 (Pragmatic Value)，
系统选择最小化 EFE 的行动，天然实现探索-利用平衡。

理论基础:
    - Friston Active Inference (2010, 2013)
    - Expected Free Energy: G(π) = Epistemic Value + Pragmatic Value
    - 探索-利用权衡的信息论形式化
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .hpc_config import HPCLoopConfig
from .hpc_state import MarketPrediction


@dataclass
class EFEDecomposition:
    """
    期望自由能分解

    G(π) = Epistemic Value + Pragmatic Value

    其中:
    - Epistemic Value = E[D_KL(Q(s|o,π) || Q(s|π))]  (信息增益)
    - Pragmatic Value = -E[ln P(o|C)]  (预期效用)
    """

    action_id: str
    """行动标识符"""

    action_description: str
    """行动描述"""

    expected_free_energy: float
    """总期望自由能 (越小越好)"""

    epistemic_value: float
    """认知价值 (信息增益, 越大越好)"""

    pragmatic_value: float
    """实用价值 (预期效用, 越大越好)"""

    exploration_bonus: float = 0.0
    """探索奖励附加项"""

    confidence: float = 0.0
    """对该行动评估的置信度"""

    components: dict[str, float] = field(default_factory=dict)
    """额外分解分量"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_description": self.action_description,
            "expected_free_energy": self.expected_free_energy,
            "epistemic_value": self.epistemic_value,
            "pragmatic_value": self.pragmatic_value,
            "exploration_bonus": self.exploration_bonus,
            "confidence": self.confidence,
        }


@dataclass
class ActionSelection:
    """
    行动选择结果

    包含选中的行动及其 EFE 分解，
    以及所有候选行动的排名。
    """

    selected_action: EFEDecomposition
    """选中的行动"""

    all_evaluations: list[EFEDecomposition]
    """所有候选行动的评估"""

    selection_reason: str
    """选择理由"""

    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_action": self.selected_action.to_dict(),
            "num_candidates": len(self.all_evaluations),
            "selection_reason": self.selection_reason,
            "timestamp": self.timestamp,
        }


class ActiveInferenceEngine:
    """
    [DEPRECATED 2026-06-26] 旧版主动推理引擎

    !!! 此文件已废弃，由 aif_engine.py 的 ActiveInference 替代 !!!
    保留仅用于 hpc_integration.py 的后向兼容。

    旧版引擎使用启发式计算 epistemic/pragmatic value（硬编码系数），
    而新版 ActiveInference 使用真正的 Monte Carlo 采样 + 高斯KL闭式解。

    替换时间线:
    - Phase 1: 标记废弃，保留文件
    - Phase 2: 删除所有引用
    - Phase 3: 删除此文件

    核心功能:
    1. evaluate_action(): 计算单个行动的 EFE 分解 (启发式)
    2. compute_epistemic_value(): 信息增益 (硬编码系数)
    3. compute_pragmatic_value(): 预期效用 (固定风险溢价)
    4. select_action(): 选择最小化 EFE 的行动
    5. exploration_bonus(): 基于状态新颖性的探索奖励

    使用流程 (已废弃，请使用 aif_engine.ActiveInference):
        engine = ActiveInferenceEngine()  # ❌ 旧引擎
        from .aif_engine import ActiveInference  # ✅ 新引擎
    """

    def __init__(self, config: HPCLoopConfig | None = None):
        self.config = config or HPCLoopConfig()

        # 行动历史 (用于探索奖励)
        self._action_history: dict[str, int] = {}
        """行动执行计数"""

        self._state_visitation: dict[str, int] = {}
        """状态访问计数"""

        # 探索相关
        self._exploration_rate = 1.0
        """当前探索率"""

        self._total_steps = 0
        """总步数"""

    def evaluate_action(
        self,
        action: str,
        current_state: dict[str, Any],
        generative_model: object | None = None,
        prediction: MarketPrediction | None = None,
    ) -> EFEDecomposition:
        """
        评估一个行动的期望自由能

        G(π) = -Epistemic Value - Pragmatic Value

        注意: 优化方向是最小化 G(π)，所以认知价值和实用价值取负号。

        Args:
            action: 行动名称 (如 "买入", "持有", "卖出")
            current_state: 当前市场状态字典
            generative_model: 生成模型实例 (用于计算信息增益)
            prediction: 市场预测 (可选)

        Returns:
            EFEDecomposition: 行动的期望自由能分解
        """
        # === 计算认知价值 (信息增益) ===
        epistemic_value = self.compute_epistemic_value(action, current_state, generative_model)

        # === 计算实用价值 (预期效用) ===
        pragmatic_value = self.compute_pragmatic_value(action, current_state, prediction)

        # === 计算探索奖励 ===
        exploration_bonus = self.exploration_bonus(action, current_state)

        # === 计算总 EFE ===
        # G(π) = - (w_e * Epistemic + w_p * Pragmatic + w_x * Exploration)
        w_e = self.config.epistemic_weight
        w_p = self.config.pragmatic_weight

        total_efe = -(w_e * epistemic_value + w_p * pragmatic_value + exploration_bonus)

        # === 评估置信度 ===
        confidence = self._estimate_confidence(action, current_state)

        efe = EFEDecomposition(
            action_id=action,
            action_description=self._get_action_description(action),
            expected_free_energy=total_efe,
            epistemic_value=epistemic_value,
            pragmatic_value=pragmatic_value,
            exploration_bonus=exploration_bonus,
            confidence=confidence,
            components={
                "uncertainty_reduction": epistemic_value,
                "expected_return": pragmatic_value,
            },
        )

        return efe

    def compute_epistemic_value(
        self,
        action: str,
        current_state: dict[str, Any],
        generative_model: object | None = None,
    ) -> float:
        """
        计算认知价值 (信息增益)

        评估一个行动能减少多少关于市场状态的不确定性。
        E[D_KL(Q(s|o,π) || Q(s|π))]

        Args:
            action: 行动名称
            current_state: 当前市场状态
            generative_model: 生成模型 (可选)

        Returns:
            float: 认知价值 (越大越好)
        """
        # 获取当前不确定性
        current_uncertainty = current_state.get("uncertainty", 0.5)
        current_entropy = current_state.get("entropy", 1.0)

        # === 估算执行行动后的不确定性减少 ===

        # 不同行动的信息增益不同:
        # - "买入"/"卖出" 提供价格反馈，减少价格不确定性
        # - "持有" 不提供新信息，信息增益为0
        # - "收集数据" 提供最大信息增益

        action_lower = action.lower()

        if "买入" in action_lower or "buy" in action_lower:
            # 买入行动: 提供价格执行反馈
            info_gain = 0.3 * current_uncertainty * (1 - current_entropy * 0.1)
        elif "卖出" in action_lower or "sell" in action_lower:
            # 卖出行动: 类似买入
            info_gain = 0.3 * current_uncertainty * (1 - current_entropy * 0.1)
        elif "数据" in action_lower or "data" in action_lower or "收集" in action_lower:
            # 数据收集: 最大信息增益
            info_gain = 0.6 * current_uncertainty
        elif "持有" in action_lower or "hold" in action_lower:
            # 持有: 几乎无新信息
            info_gain = 0.05 * current_uncertainty
        else:
            # 默认: 中等信息增益
            info_gain = 0.2 * current_uncertainty

        # 确保非负
        return max(0.0, min(1.0, info_gain))

    def compute_pragmatic_value(
        self,
        action: str,
        current_state: dict[str, Any],
        prediction: MarketPrediction | None = None,
    ) -> float:
        """
        计算实用价值 (预期效用)

        评估一个行动的预期风险调整后收益。
        E[U(action|state)]

        Args:
            action: 行动名称
            current_state: 当前市场状态
            prediction: 市场预测 (可选)

        Returns:
            float: 实用价值 (越大越好)
        """
        current_state.get("price", 100.0)
        volatility = current_state.get("volatility", 0.02)

        # 获取价格预测
        predicted_return = 0.0
        if prediction and prediction.price_prediction:
            predicted_return = prediction.price_prediction.get("mean", 0.0)

        action_lower = action.lower()

        # === 计算每个行动的预期效用 ===

        if "买入" in action_lower or "buy" in action_lower:
            # 买入: 预期收益 = 预测回报 - 风险溢价
            expected_return = predicted_return
            risk_penalty = 0.5 * volatility * volatility  # 方差惩罚
            pragmatic_value = expected_return - risk_penalty

        elif "卖出" in action_lower or "sell" in action_lower:
            # 卖出: 预期收益 = -预测回报 - 风险溢价
            expected_return = -predicted_return
            risk_penalty = 0.5 * volatility * volatility
            pragmatic_value = expected_return - risk_penalty

        elif "持有" in action_lower or "hold" in action_lower:
            # 持有: 无交易成本，但可能错过机会
            pragmatic_value = -0.01 * abs(predicted_return)  # 机会成本

        else:
            pragmatic_value = 0.0

        # 归一化到 [-1, 1]
        pragmatic_value = max(-1.0, min(1.0, pragmatic_value))

        # 转换为 [0, 1] 范围的实用价值 (越高越好)
        return (pragmatic_value + 1.0) / 2.0

    def select_action(
        self,
        candidate_actions: list[str],
        current_state: dict[str, Any],
        generative_model: object | None = None,
        prediction: MarketPrediction | None = None,
    ) -> ActionSelection:
        """
        选择最小化 EFE 的行动

        评估所有候选行动的 EFE，选择最优者。

        Args:
            candidate_actions: 候选行动列表
            current_state: 当前市场状态
            generative_model: 生成模型 (可选)
            prediction: 市场预测 (可选)

        Returns:
            ActionSelection: 选择结果
        """
        # 评估所有候选行动
        evaluations = []
        for action in candidate_actions:
            efe = self.evaluate_action(action, current_state, generative_model, prediction)
            evaluations.append(efe)

        # 按总 EFE 排序 (越小越好)
        evaluations.sort(key=lambda e: e.expected_free_energy)

        if not evaluations:
            return ActionSelection(
                selected_action=None,
                all_evaluations=[],
                selection_reason="无候选行动",
                timestamp=datetime.now().isoformat(),
            )

        # 选择 EFE 最小的行动
        selected = evaluations[0]

        # 生成选择理由
        reasons = []
        reasons.append(f"EFE={selected.expected_free_energy:.3f} (最小)")
        reasons.append(f"认知价值={selected.epistemic_value:.3f}")
        reasons.append(f"实用价值={selected.pragmatic_value:.3f}")
        if selected.exploration_bonus > 0.01:
            reasons.append(f"探索奖励={selected.exploration_bonus:.3f}")
        selection_reason = "; ".join(reasons)

        # 更新内部统计
        self._total_steps += 1
        self._action_history[selected.action_id] = self._action_history.get(selected.action_id, 0) + 1
        self._exploration_rate *= self.config.exploration_decay
        self._exploration_rate = max(self.config.min_exploration_bonus, self._exploration_rate)

        return ActionSelection(
            selected_action=selected,
            all_evaluations=evaluations,
            selection_reason=selection_reason,
            timestamp=datetime.now().isoformat(),
        )

    def exploration_bonus(
        self,
        action: str,
        state: dict[str, Any],
    ) -> float:
        """
        计算探索奖励

        基于状态新颖性和行动历史的多样性。
        已频繁访问的状态/行动组合获得较低探索奖励。

        Args:
            action: 行动名称
            state: 当前市场状态

        Returns:
            float: 探索奖励附加项
        """
        # 状态签名
        state_signature = self._state_signature(state)

        # 访问次数
        state_visits = self._state_visitation.get(state_signature, 0)
        action_count = self._action_history.get(action, 0)

        # 探索奖励 = exploration_rate * (1 / (1 + visits))
        state_bonus = 1.0 / (1.0 + state_visits)
        action_bonus = 1.0 / (1.0 + action_count)

        bonus = self._exploration_rate * (0.6 * state_bonus + 0.4 * action_bonus)

        return max(0.0, bonus)

    def _state_signature(self, state: dict[str, Any]) -> str:
        """生成状态签名用于访问计数"""
        price = state.get("price", 0)
        volatility = state.get("volatility", 0)
        regime = state.get("regime", "unknown")
        # 离散化到桶
        price_bucket = round(price / 10) * 10
        vol_bucket = round(volatility * 10) / 10
        return f"{price_bucket}_{vol_bucket}_{regime}"

    def _estimate_confidence(self, action: str, state: dict[str, Any]) -> float:
        """估计评估置信度"""
        # 更熟悉的状态/行动组合 → 更高置信度
        state_signature = self._state_signature(state)
        state_visits = self._state_visitation.get(state_signature, 0)
        action_count = self._action_history.get(action, 0)
        return min(1.0, (state_visits + action_count) * 0.1 + 0.3)

    def _get_action_description(self, action: str) -> str:
        """获取行动的中文描述"""
        descriptions = {
            "买入": "执行买入操作，建立多头仓位",
            "卖出": "执行卖出操作，建立空头仓位或平仓",
            "持有": "保持当前仓位不变，不执行交易",
            "buy": "Execute buy order, establish long position",
            "sell": "Execute sell order, establish short position or close",
            "hold": "Maintain current position, no trade",
        }
        return descriptions.get(action, action)

    @property
    def action_history(self) -> dict[str, int]:
        """获取行动历史"""
        return dict(self._action_history)

    def get_action_history(self) -> dict[str, int]:
        """获取行动历史统计"""
        return dict(self._action_history)

    def get_exploration_rate(self) -> float:
        """获取当前探索率"""
        return self._exploration_rate

    def reset(self) -> None:
        """重置引擎状态"""
        self._action_history.clear()
        self._state_visitation.clear()
        self._exploration_rate = 1.0
        self._total_steps = 0
