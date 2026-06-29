# TradingAgents/hpc_loop/causal_counterfactual.py
"""
因果反事实引擎 (Causal Counterfactual Engine)

实现基于 Pearl 结构因果模型 (SCM) 的因果推理与反事实推理框架。
区分"相关"和"因果"，回答"如果我做了X会怎样"的反事实问题。

理论基础:
    - Pearl 结构因果模型 (SCM) 与 do-calculus
    - Judea Pearl 因果推理三层次: 关联 → 干预 → 反事实
    - 因果效应分解: 直接效应 + 间接效应 + 混杂效应
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from .hpc_config import HPCLoopConfig


@dataclass
class CausalNode:
    """因果图节点"""

    name: str
    """节点名称"""
    description: str
    """节点描述"""
    value: float
    """当前值"""
    type: str = "observable"
    """节点类型: observable, latent, action, outcome"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "value": self.value,
            "type": self.type,
        }


@dataclass
class CausalEdge:
    """因果图边"""

    source: str
    """源节点"""
    target: str
    """目标节点"""
    strength: float
    """因果强度 (路径系数)"""
    confidence: float = 0.5
    """置信度"""
    direction: str = "positive"
    """方向: positive, negative"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "strength": self.strength,
            "confidence": self.confidence,
            "direction": self.direction,
        }


@dataclass
class CounterfactualResult:
    """
    反事实推理结果

    三步推理: Abduction → Action → Prediction
    """

    query: str
    """反事实查询描述"""

    factual_outcome: float
    """事实结果"""

    counterfactual_outcome: float
    """反事实结果"""

    effect: float
    """因果效应 (反事实 - 事实)"""

    intervention_description: str
    """干预描述"""

    abduction_posterior: dict[str, float]
    """反绎后验 P(U|E=e)"""

    confidence: float = 0.5
    """推理置信度"""

    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "factual_outcome": self.factual_outcome,
            "counterfactual_outcome": self.counterfactual_outcome,
            "effect": self.effect,
            "intervention_description": self.intervention_description,
            "confidence": self.confidence,
        }


@dataclass
class EffectDecomposition:
    """
    因果效应分解

    总效应 = 直接效应 + 间接效应 + 混杂效应
    """

    total_effect: float
    """总效应"""

    direct_effect: float
    """直接效应 (X → Y)"""

    indirect_effect: float
    """间接效应 (X → M → Y)"""

    confounding_effect: float
    """混杂效应 (X ← C → Y)"""

    effects: dict[str, float] = field(default_factory=dict)
    """详细效应分解"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_effect": self.total_effect,
            "direct_effect": self.direct_effect,
            "indirect_effect": self.indirect_effect,
            "confounding_effect": self.confounding_effect,
        }


@dataclass
class FilteredCorrelation:
    """基于因果图过滤后的相关性"""

    original_correlation: float
    """原始相关系数"""

    filtered_correlation: float
    """过滤虚假相关后的相关系数"""

    spurious_ratio: float
    """虚假相关比例"""

    confounding_variables: list[str]
    """混杂变量列表"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original_correlation,
            "filtered": self.filtered_correlation,
            "spurious_ratio": self.spurious_ratio,
            "confounders": self.confounding_variables,
        }


class CausalCounterfactualEngine:
    """
    因果反事实引擎

    核心功能:
    1. build_causal_graph(): 构建市场因果图 (DAG)
    2. compute_intervention_effect(): 使用 do-calculus 计算干预效应
    3. counterfactual_query(): 三步反事实推理
    4. decompose_effect(): 分解总效应
    5. filter_spurious_correlation(): 基于因果图过滤虚假相关

    使用流程:
        engine = CausalCounterfactualEngine()
        effect = engine.compute_intervention_effect("买入", "收益率", data)
        cf = engine.counterfactual_query("买入", "收益率", {"price": 100})
    """

    def __init__(self, config: HPCLoopConfig | None = None):
        self.config = config or HPCLoopConfig()

        # 因果图结构
        self._nodes: dict[str, CausalNode] = {}
        self._edges: list[CausalEdge] = []
        self._adjacency: dict[str, list[str]] = defaultdict(list)  # parent → children
        self._parents: dict[str, list[str]] = defaultdict(list)  # child → parents

        # 初始化默认因果图
        self._build_default_causal_graph()

        # 外生变量的后验分布 (用于反事实推理)
        self._exogenous_posteriors: dict[str, float] = {}

    def _build_default_causal_graph(self) -> None:
        """构建默认市场因果图"""
        # 注意: 这是一个简化的默认因果图。
        # 实际应用中应从数据中学习或由领域专家定义。

        # 定义节点
        nodes = [
            CausalNode("macro_economy", "宏观经济 (GDP/利率/通胀)", 0.0, "latent"),
            CausalNode("market_sentiment", "市场情绪", 0.0, "latent"),
            CausalNode("industry_trend", "行业趋势", 0.0, "latent"),
            CausalNode("fundamentals", "公司基本面", 0.0, "observable"),
            CausalNode("technical_indicators", "技术指标", 0.0, "observable"),
            CausalNode("news_events", "新闻事件", 0.0, "observable"),
            CausalNode("price_movement", "股价变动", 0.0, "outcome"),
            CausalNode("volatility", "波动率", 0.0, "outcome"),
            CausalNode("trading_action", "交易行动", 0.0, "action"),
            CausalNode("trading_return", "交易收益", 0.0, "outcome"),
        ]
        for node in nodes:
            self.add_node(node)

        # 定义边 (因果路径)
        edges = [
            # 宏观经济 → 行业 → 基本面 → 价格
            CausalEdge("macro_economy", "industry_trend", 0.6, 0.5, "positive"),
            CausalEdge("industry_trend", "fundamentals", 0.4, 0.5, "positive"),
            CausalEdge("fundamentals", "price_movement", 0.3, 0.4, "positive"),
            # 市场情绪 → 价格
            CausalEdge("market_sentiment", "price_movement", 0.3, 0.3, "positive"),
            # 新闻 → 情绪 → 价格
            CausalEdge("news_events", "market_sentiment", 0.5, 0.6, "positive"),
            CausalEdge("news_events", "price_movement", 0.2, 0.3, "positive"),
            # 技术指标 → 价格 (较弱)
            CausalEdge("technical_indicators", "price_movement", 0.1, 0.2, "positive"),
            # 宏观经济 → 波动率
            CausalEdge("macro_economy", "volatility", -0.4, 0.4, "negative"),
            CausalEdge("market_sentiment", "volatility", -0.3, 0.3, "negative"),
            # 交易行动 → 收益
            CausalEdge("trading_action", "trading_return", 0.5, 0.5, "positive"),
            CausalEdge("price_movement", "trading_return", 0.8, 0.7, "positive"),
            # 价格 → 技术指标 (反馈)
            CausalEdge("price_movement", "technical_indicators", 0.7, 0.6, "positive"),
            # 宏观 → 情绪
            CausalEdge("macro_economy", "market_sentiment", 0.3, 0.3, "positive"),
        ]
        for edge in edges:
            self.add_edge(edge)

    def add_node(self, node: CausalNode) -> None:
        """添加因果图节点"""
        self._nodes[node.name] = node

    def add_edge(self, edge: CausalEdge) -> None:
        """添加因果图边"""
        if edge.source in self._nodes and edge.target in self._nodes:
            self._edges.append(edge)
            self._adjacency[edge.source].append(edge.target)
            self._parents[edge.target].append(edge.source)

    def build_causal_graph(self, market_variables: dict[str, Any]) -> None:
        """
        从市场变量构建/更新因果图

        Args:
            market_variables: 市场变量字典
        """
        for name, value in market_variables.items():
            if name in self._nodes:
                self._nodes[name].value = value
            else:
                # 添加新的观测节点
                self.add_node(CausalNode(name, name, value, "observable"))

    def compute_intervention_effect(
        self,
        action: str,
        target_variable: str,
        data: dict[str, list[float]] | None = None,
    ) -> float:
        """
        使用 do-calculus 计算干预效应 ATE

        ATE = E[Y | do(X=x)] - E[Y | do(X=x')]

        当数据不可用时，使用因果图中的路径系数近似估计。

        Args:
            action: 行动节点名称
            target_variable: 目标变量名称
            data: 观测数据 (可选)

        Returns:
            float: 平均处理效应 (ATE)
        """
        if action not in self._nodes or target_variable not in self._nodes:
            return 0.0

        # 找到 action 到 target_variable 的所有路径
        paths = self._find_all_paths(action, target_variable)

        if not paths:
            return 0.0

        # 计算每条路径的效应
        total_effect = 0.0
        for path in paths:
            path_effect = 1.0
            for i in range(len(path) - 1):
                source, target = path[i], path[i + 1]
                # 查找边权重
                for edge in self._edges:
                    if edge.source == source and edge.target == target:
                        path_effect *= edge.strength
                        break
            total_effect += path_effect

        return total_effect

    def counterfactual_query(
        self,
        action: str,
        outcome: str,
        evidence: dict[str, Any],
    ) -> CounterfactualResult:
        """
        反事实推理三步骤: Abduction → Action → Prediction

        回答: "给定已观察到的证据 E=e,
              如果执行了 do(Action=a'),
              目标变量 Outcome 的值会是多少?"

        Args:
            action: 干预的行动
            outcome: 目标结果变量
            evidence: 已观察到的证据 {变量名: 值}

        Returns:
            CounterfactualResult: 反事实推理结果
        """
        # Step 1: Abduction - 基于观测推断外生变量后验
        abduction_posterior = self._abduction(evidence)

        # Step 2: Action - 应用干预 do(Action=a')
        # 在因果图中将 action 节点从其父节点断开, 固定为指定值
        action_value = evidence.get(action, 1.0)

        # Step 3: Prediction - 预测反事实结果
        factual = self._predict(outcome, evidence, do_intervention=None)
        counterfactual = self._predict(
            outcome,
            {**evidence, action: action_value},
            do_intervention=(action, action_value),
        )

        effect = counterfactual - factual

        # 估计置信度
        confidence = self._estimate_cf_confidence(action, outcome, evidence)

        return CounterfactualResult(
            query=f"如果 {action} 的值为 {action_value:.2f}，{outcome} 会怎样？",
            factual_outcome=factual,
            counterfactual_outcome=counterfactual,
            effect=effect,
            intervention_description=f"do({action} = {action_value:.2f})",
            abduction_posterior=abduction_posterior,
            confidence=confidence,
            timestamp=datetime.now().isoformat(),
        )

    def decompose_effect(
        self,
        total_effect: dict[str, float],
        treatment: str,
        mediator: str,
        outcome: str,
    ) -> EffectDecomposition:
        """
        分解总效应

        使用因果路径分析分解：
        - 直接效应 (Direct Effect)
        - 间接效应 (Indirect Effect via mediator)
        - 混杂效应 (Confounding Effect)

        Args:
            total_effect: 总效应字典
            treatment: 处理变量
            mediator: 中介变量
            outcome: 结果变量

        Returns:
            EffectDecomposition: 效应分解
        """
        # 查找路径
        direct_paths = []
        indirect_paths = []
        for edge in self._edges:
            if edge.source == treatment and edge.target == outcome:
                direct_paths.append(edge)
            if edge.source == treatment and edge.target == mediator:
                for e2 in self._edges:
                    if e2.source == mediator and e2.target == outcome:
                        indirect_paths.append((edge, e2))

        # 直接效应
        direct_effect = sum(e.strength for e in direct_paths) if direct_paths else 0.0

        # 间接效应
        indirect_effect = sum(e1.strength * e2.strength for e1, e2 in indirect_paths) if indirect_paths else 0.0

        # 混杂效应 (总效应 - 直接 - 间接)
        total = sum(total_effect.values()) if isinstance(total_effect, dict) else total_effect
        confounding_effect = total - direct_effect - indirect_effect

        return EffectDecomposition(
            total_effect=total,
            direct_effect=direct_effect,
            indirect_effect=indirect_effect,
            confounding_effect=max(0, confounding_effect),
            effects={
                "direct": direct_effect,
                "indirect": indirect_effect,
                "confounding": max(0, confounding_effect),
            },
        )

    def filter_spurious_correlation(
        self,
        x: str,
        y: str,
        correlation: float,
    ) -> FilteredCorrelation:
        """
        基于因果图过滤虚假相关

        使用因果图识别 x 和 y 之间的混杂路径，
        通过调整策略去除虚假相关。

        Args:
            x: 变量 X 名称
            y: 变量 Y 名称
            correlation: 观测到的相关系数

        Returns:
            FilteredCorrelation: 过滤结果
        """
        # 查找 X 和 Y 之间的后门路径
        backdoor_paths = self._find_backdoor_paths(x, y)

        # 识别需要调整的混杂变量
        confounding_vars = set()
        for path in backdoor_paths:
            if len(path) >= 2:
                # 后门路径上的第一个中介变量
                confounding_vars.add(path[1])

        # 估算虚假相关比例
        spurious_ratio = 0.0
        for var in confounding_vars:
            if var in self._nodes:
                # 每个混杂变量的贡献
                paths_to_y = self._find_all_paths(var, y)
                paths_from_x = self._find_all_paths(var, x)
                var_effect = 0.0
                for p in paths_to_y:
                    for p2 in paths_from_x:
                        effect = 1.0
                        all_edges = p + p2[1:]
                        for i in range(len(all_edges) - 1):
                            for edge in self._edges:
                                if edge.source == all_edges[i] and edge.target == all_edges[i + 1]:
                                    effect *= edge.strength
                                    break
                        var_effect += effect
                spurious_ratio += abs(var_effect)

        spurious_ratio = min(1.0, spurious_ratio)

        # 过滤后的相关
        filtered_correlation = correlation * (1.0 - spurious_ratio)

        return FilteredCorrelation(
            original_correlation=correlation,
            filtered_correlation=filtered_correlation,
            spurious_ratio=spurious_ratio,
            confounding_variables=list(confounding_vars),
        )

    @property
    def causal_graph(self) -> dict[str, Any]:
        """获取因果图结构 (Dict 格式, 用于外部访问)"""
        return {
            "nodes": list(self._nodes.keys()),
            "edges": [{"source": e.source, "target": e.target, "strength": e.strength} for e in self._edges],
        }

    def get_causal_graph_summary(self) -> str:
        """
        获取因果图摘要 (用于 LLM Prompt)

        Returns:
            str: 因果图描述
        """
        lines = ["因果模型结构 (DAG):"]
        lines.append(f"  节点数: {len(self._nodes)}")
        lines.append(f"  边数: {len(self._edges)}")

        # 按层级组织
        latent_nodes = [n for n in self._nodes.values() if n.type == "latent"]
        observable_nodes = [n for n in self._nodes.values() if n.type == "observable"]
        action_nodes = [n for n in self._nodes.values() if n.type == "action"]
        outcome_nodes = [n for n in self._nodes.values() if n.type == "outcome"]

        lines.append(f"\n  潜变量层 (Latent): {[n.name for n in latent_nodes]}")
        lines.append(f"  观测变量层 (Observable): {[n.name for n in observable_nodes]}")
        lines.append(f"  行动变量层 (Action): {[n.name for n in action_nodes]}")
        lines.append(f"  结果变量层 (Outcome): {[n.name for n in outcome_nodes]}")

        lines.append("\n  因果路径:")
        for edge in self._edges[:10]:  # 最多显示10条
            direction_mark = "+" if edge.direction == "positive" else "-"
            lines.append(
                f"    {edge.source} → {edge.target} "
                f"(强度={edge.strength:.2f}{direction_mark}, "
                f"置信度={edge.confidence:.2f})",
            )

        return "\n".join(lines)

    # ==================== 内部方法 ====================

    def _find_all_paths(
        self,
        source: str,
        target: str,
        visited: set[str] | None = None,
    ) -> list[list[str]]:
        """找到 source 到 target 的所有路径"""
        if visited is None:
            visited = set()

        if source == target:
            return [[source]]

        if source in visited:
            return []

        visited = visited | {source}
        paths = []

        for neighbor in self._adjacency.get(source, []):
            if neighbor not in visited:
                sub_paths = self._find_all_paths(neighbor, target, visited)
                for sub_path in sub_paths:
                    paths.append([source, *sub_path])

        return paths

    def _find_backdoor_paths(
        self,
        x: str,
        y: str,
        visited: set[str] | None = None,
    ) -> list[list[str]]:
        """找到 X → ... → Y 的后门路径 (从父节点出发)"""
        if visited is None:
            visited = set()

        if x == y:
            return [[x]]

        if x in visited:
            return []

        visited = visited | {x}
        paths = []

        # 从 X 的父节点出发 (后门路径)
        for parent in self._parents.get(x, []):
            if parent not in visited:
                sub_paths = self._find_backdoor_paths(parent, y, visited)
                for sub_path in sub_paths:
                    if y in sub_path:
                        paths.append([x, *sub_path])

        # 从 X 的子节点出发
        for child in self._adjacency.get(x, []):
            if child not in visited:
                sub_paths = self._find_backdoor_paths(child, y, visited)
                for sub_path in sub_paths:
                    paths.append([x, *sub_path])

        return paths

    def _abduction(self, evidence: dict[str, Any]) -> dict[str, float]:
        """
        反绎推理: 基于观测推断外生变量后验

        在简化实现中，使用因果图节点当前值的加权组合作为后验估计。
        """
        posteriors = {}

        for node_name, node in self._nodes.items():
            if node.type == "latent":
                # 从该隐变量指向的观测节点收集证据
                child_evidence = []
                for child in self._adjacency.get(node_name, []):
                    if child in evidence:
                        for edge in self._edges:
                            if edge.source == node_name and edge.target == child:
                                child_evidence.append(evidence[child] * edge.strength * edge.confidence)

                if child_evidence:
                    posteriors[node_name] = np.mean(child_evidence)
                else:
                    posteriors[node_name] = node.value

        return posteriors

    def _predict(
        self,
        target: str,
        evidence: dict[str, Any],
        do_intervention: tuple[str, float] | None = None,
    ) -> float:
        """
        预测目标变量的值

        在简化实现中，使用因果图中的线性路径系数进行预测。
        """
        if target in evidence and do_intervention is None:
            return evidence[target]

        # 找到所有指向 target 的父节点
        parents = self._parents.get(target, [])

        if not parents:
            return evidence.get(target, self._nodes.get(target, CausalNode("", "", 0.0)).value)

        # 线性预测: Y = sum(w_i * X_i) + noise
        prediction = 0.0
        total_strength = 0.0

        for parent in parents:
            # 检查是否被干预
            if do_intervention and parent == do_intervention[0]:
                parent_value = do_intervention[1]
            else:
                parent_value = evidence.get(parent, self._nodes.get(parent, CausalNode("", "", 0.0)).value)

            for edge in self._edges:
                if edge.source == parent and edge.target == target:
                    contribution = edge.strength * parent_value
                    prediction += contribution
                    total_strength += abs(edge.strength)
                    break

        return prediction / max(total_strength, 1e-8)

    def _estimate_cf_confidence(
        self,
        action: str,
        outcome: str,
        evidence: dict[str, Any],
    ) -> float:
        """估计反事实推理的置信度"""
        # 基于证据的完整性和因果路径的强度
        evidence_coverage = len(evidence) / max(len(self._nodes), 1)

        # 找到 action 到 outcome 的路径强度
        paths = self._find_all_paths(action, outcome)
        path_strength = 0.0
        for path in paths:
            strength = 1.0
            for i in range(len(path) - 1):
                for edge in self._edges:
                    if edge.source == path[i] and edge.target == path[i + 1]:
                        strength *= edge.strength * edge.confidence
                        break
            path_strength += strength

        return min(1.0, (evidence_coverage * 0.3 + path_strength * 0.7))

    def reset(self) -> None:
        """重置因果引擎"""
        self._nodes.clear()
        self._edges.clear()
        self._adjacency.clear()
        self._parents.clear()
        self._exogenous_posteriors.clear()
        self._build_default_causal_graph()
