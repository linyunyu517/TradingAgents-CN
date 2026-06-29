#!/usr/bin/env python3
"""
Round 3 Phase 3 — 属性基测试 (Property-Based Testing)

使用 Hypothesis 框架验证以下函数的数学属性：
  1. [`GenerativeModel._adapt_s_t_dim()`](tradingagents/hpc_loop/aif_engine.py:514)  — 维度适配的代数属性
  2. [`MarketLatentState.from_latent_vector()`](tradingagents/hpc_loop/aif_engine.py:246) — 隐状态重建的不变量
  3. [`DatabaseManager._detect_redis()`](tradingagents/config/database_manager.py:125) — Redis AUTH 回退的健壮性

运行方式:
    cd D:\\AI-Projects\\TradingAgents-CN_v1.0.1
    python -m pytest tests/test_round3_property_based.py -v --hypothesis-show-statistics
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# 禁用非必要的日志输出
logging.disable(logging.CRITICAL)

# ──────────────────────────────────────────────────────────────
# 策略 (Strategies)
# ──────────────────────────────────────────────────────────────

# 维度策略: 0 ~ 32 (包含边界情况 0 和 >8)
dim_strategy = st.integers(min_value=0, max_value=32)

# 短向量策略: 1~7 维 (用于 from_latent_vector 填充测试)
# 注意: from_latent_vector 对 momentum (z[6]) 和 sentiment (z[7]) 进行 [-1,1] 裁剪，
#       因此策略值限制在 [-1.0, 1.0] 以避免裁剪导致的 roundtrip 不匹配。
short_vector_strategy = st.lists(
    st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=7,
).map(lambda lst: np.array(lst, dtype=np.float32))


# ──────────────────────────────────────────────────────────────
# Helper: 检查数组是否全零 (容忍舍入误差)
# ──────────────────────────────────────────────────────────────
def _is_all_zero(arr: np.ndarray, tol: float = 1e-8) -> bool:
    return bool(np.all(np.abs(arr) < tol))


# ==============================================================
# 测试组 1: GenerativeModel._adapt_s_t_dim()
# ==============================================================

TARGET_LATENT_DIM = 8  # DEFAULT_LATENT_DIM

# 尝试导入 JAX 和 GenerativeModel
try:
    import jax.numpy as jnp

    from tradingagents.hpc_loop.aif_engine import (
        GenerativeModel,
        MarketLatentState,
    )

    _CAN_TEST_GENMODEL = True
except Exception as exc:
    _CAN_TEST_GENMODEL = False
    _GENMODEL_SKIP_REASON = str(exc)


def _make_generative_model() -> GenerativeModel:
    """创建 GenerativeModel 实例用于测试"""
    return GenerativeModel(latent_dim=TARGET_LATENT_DIM)


class TestAdaptSTDim:
    """
    属性基测试: [`GenerativeModel._adapt_s_t_dim()`](tradingagents/hpc_loop/aif_engine.py:514)

    被测方法行为:
        - 输入维度 < latent_dim → zero-pad 到 latent_dim
        - 输入维度 > latent_dim → truncate 到 latent_dim
        - 输入维度 == latent_dim → 不变
        - 非数组 / 降级模式 → 返回原值
    """

    @classmethod
    def setup_class(cls):
        if not _CAN_TEST_GENMODEL:
            import pytest

            pytest.skip(f"GenerativeModel 不可用，跳过 _adapt_s_t_dim 测试: {_GENMODEL_SKIP_REASON}")

    # ── 属性 1: 长度保持 ──────────────────────────────────────
    @given(dim=dim_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop1_length_preservation(self, dim: int):
        """
        属性1（长度保持）：任意维度输入被适配后，
        前 min(input_dim, target_dim) 个元素必须不变。
        """
        gm = _make_generative_model()
        target = gm.A.shape[1]  # = TARGET_LATENT_DIM
        s_t = jnp.ones((dim,), dtype=jnp.float32) * 3.14  # 填充 π 便于检测截断
        adapted = gm._adapt_s_t_dim(s_t, caller_name="test")
        n_keep = min(dim, target)
        # 前 n_keep 个元素不变
        assert jnp.allclose(adapted[:n_keep], s_t[:n_keep]), f"dim={dim}, target={target}: 前 {n_keep} 个元素改变"

    # ── 属性 2: 输出维度 ──────────────────────────────────────
    @given(dim=dim_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop2_output_dim(self, dim: int):
        """
        属性2（输出维度）：输出必须恰好为 target_dim (= self.A.shape[1])。
        """
        gm = _make_generative_model()
        target = gm.A.shape[1]
        s_t = jnp.ones((dim,), dtype=jnp.float32)
        adapted = gm._adapt_s_t_dim(s_t, caller_name="test")
        assert adapted.shape[0] == target, f"dim={dim}: 预期输出维度 {target}，实际 {adapted.shape[0]}"

    # ── 属性 3: 幂等性 ────────────────────────────────────────
    @given(dim=dim_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop3_idempotent(self, dim: int):
        """
        属性3（幂等性）：对同一输入连续调用两次，结果相同。
        """
        gm = _make_generative_model()
        s_t = jnp.ones((dim,), dtype=jnp.float32) * 0.5
        first = gm._adapt_s_t_dim(s_t, caller_name="test")
        second = gm._adapt_s_t_dim(first, caller_name="test")
        assert jnp.allclose(first, second), f"dim={dim}: 幂等性不成立"

    # ── 属性 4: 零向量保持 ────────────────────────────────────
    @given(dim=dim_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop4_zero_vector(self, dim: int):
        """
        属性4（零向量保持）：全零向量适配后前 min(dim, target_dim) 个元素仍为零。
        """
        gm = _make_generative_model()
        target = gm.A.shape[1]
        s_t = jnp.zeros((dim,), dtype=jnp.float32)
        adapted = gm._adapt_s_t_dim(s_t, caller_name="test")
        n_keep = min(dim, target)
        assert _is_all_zero(np.asarray(adapted[:n_keep])), f"dim={dim}: 零向量前 {n_keep} 个元素非零"

    # ── 边界: 非数组输入 ──────────────────────────────────────
    def test_non_array_input(self):
        """非数组输入应返回零向量（当 JAX 可用且未降级时）"""
        gm = _make_generative_model()
        result = gm._adapt_s_t_dim(None, caller_name="test")
        assert result.shape[0] == TARGET_LATENT_DIM

    # ── 边界: 降级模式 ────────────────────────────────────────
    def test_degraded_mode(self):
        """降级模式下应直接返回输入"""
        gm = _make_generative_model()
        gm._degraded = True
        s_t = jnp.ones((3,), dtype=jnp.float32)
        result = gm._adapt_s_t_dim(s_t, caller_name="test")
        # 降级模式直接返回，不做维度适配
        assert result.shape[0] == 3


# ==============================================================
# 测试组 2: MarketLatentState.from_latent_vector()
# ==============================================================


class TestFromLatentVector:
    """
    属性基测试: [`MarketLatentState.from_latent_vector()`](tradingagents/hpc_loop/aif_engine.py:246)

    注意: `to_latent_vector()` 对前 4 维 (regime_logits) 应用 softmax 得到 regime_probs，
    因此 roundtrip 对元素 0-3 不是恒等映射。属性5 验证元素 [4..n) 保持原值。
    """

    # ── 属性 5: 短向量零填充 ──────────────────────────────────
    @given(z=short_vector_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop5_short_vector_padding(self, z: np.ndarray):
        """
        属性5（短向量零填充）：1-7D 短向量自动填充到 8D，
        且元素 [4..n)（volatility/trend/momentum/sentiment 等）不变。
        """
        assume(z.shape[0] >= 1)
        n = z.shape[0]
        z_jax = jnp.array(z)
        state = MarketLatentState.from_latent_vector(z_jax, temperature=1.0)
        reconstructed = state.to_latent_vector()
        # 输出维度固定为 8
        assert reconstructed.shape[0] == 8, f"输入维度 {n}: 输出应为 8D，实际 {reconstructed.shape[0]}D"
        # 前 4 维经过 softmax → to_latent_vector 使用 regime_probs，不直接保持
        # 验证元素 [4..n) 保持原值（volatility_mu, trend_mu, momentum, sentiment）
        if n > 4:
            assert jnp.allclose(reconstructed[4:n], z_jax[4:n], atol=1e-6), f"输入维度 {n}: 元素 [4..{n}) 改变"
        # 如果 n < 8: 填充部分为 [n..8)
        # 注意: 当 n <= 4 时，元素 [n..4) 被 softmax 变换（logits→probs），
        #       但元素 [4..8) 是零填充的 volatility/trend/momentum/sentiment，必须为零
        if n < 8:
            pad_start = max(n, 4)
            assert _is_all_zero(np.asarray(reconstructed[pad_start:])), (
                f"输入维度 {n}: 填充部分 [4..8) 非零，实际 {reconstructed[pad_start:]}"
            )

    # ── 属性 6: 非负方差 ──────────────────────────────────────
    @given(z=short_vector_strategy)
    @settings(max_examples=200, deadline=None)
    def test_prop6_non_negative_variance(self, z: np.ndarray):
        """
        属性6（非负方差）：reconstructed covariance 对角线必须非负。
        [`MarketLatentState`](tradingagents/hpc_loop/aif_engine.py:118) 的
        `volatility_sigma`/`trend_sigma` 代表隐状态分布的标准差，必须 ≥ 0。
        """
        assume(z.shape[0] >= 1)
        z_jax = jnp.array(z)
        state = MarketLatentState.from_latent_vector(z_jax, temperature=1.0)
        # 这些 sigma 值代表分布的标准差，必须非负
        assert state.volatility_sigma >= 0, f"volatility_sigma={state.volatility_sigma} < 0"
        assert state.trend_sigma >= 0, f"trend_sigma={state.trend_sigma} < 0"

    # ── 边界: 全零向量 ────────────────────────────────────────
    def test_zero_vector_8d(self):
        """
        全零向量：regime_logits=[0,0,0,0] → softmax → regime_probs=[0.25,0.25,0.25,0.25]，
        其余元素保持零。输出应为 [0.25, 0.25, 0.25, 0.25, 0, 0, 0, 0]。
        """
        z = jnp.zeros(8, dtype=jnp.float32)
        state = MarketLatentState.from_latent_vector(z, temperature=1.0)
        reconstructed = state.to_latent_vector()
        assert reconstructed.shape[0] == 8
        # 前 4 维: uniform regime_probs (softmax of zeros)
        expected_first4 = jnp.ones(4, dtype=jnp.float32) * 0.25
        assert jnp.allclose(reconstructed[:4], expected_first4, atol=1e-6), (
            f"regime_probs 应为 uniform 0.25，实际 {reconstructed[:4]}"
        )
        # 后 4 维: 保持零
        assert _is_all_zero(np.asarray(reconstructed[4:])), f"后 4 维应全零，实际 {reconstructed[4:]}"

    # ── 边界: temperature 参数 ────────────────────────────────
    @given(temp=st.floats(min_value=0.1, max_value=10.0, allow_nan=False))
    @settings(max_examples=20, deadline=None)
    def test_temperature_parameter(self, temp: float):
        """temperature 应在合理范围内不影响维度"""
        z = jnp.array([1.0, -1.0, 0.5, -0.5, 0.02, 0.01, 0.3, -0.2], dtype=jnp.float32)
        state = MarketLatentState.from_latent_vector(z, temperature=temp)
        reconstructed = state.to_latent_vector()
        assert reconstructed.shape[0] == 8


# ==============================================================
# 测试组 3: DatabaseManager._detect_redis()
# ==============================================================

try:
    from tradingagents.config.database_manager import DatabaseManager

    _CAN_TEST_DB = True
except Exception as exc:
    _CAN_TEST_DB = False
    _DB_SKIP_REASON = str(exc)


class TestDetectRedis:
    """
    属性基测试: [`DatabaseManager._detect_redis()`](tradingagents/config/database_manager.py:125)

    使用 mock Redis 客户端模拟不同场景，测试 AUTH 回退逻辑的正确性。
    """

    @classmethod
    def setup_class(cls):
        if not _CAN_TEST_DB:
            import pytest

            pytest.skip(f"DatabaseManager 不可用，跳过 _detect_redis 测试: {_DB_SKIP_REASON}")

    def _make_db_manager(self, redis_enabled: bool = True, password: str = "test_pwd") -> DatabaseManager:
        """创建 DatabaseManager 实例，绕过真实的数据库检测和连接初始化"""
        with patch.object(DatabaseManager, "_detect_databases", return_value=None):
            with patch.object(DatabaseManager, "_initialize_connections", return_value=None):
                db = DatabaseManager()
        db.redis_enabled = redis_enabled
        db.redis_config = {
            "host": "127.0.0.1",
            "port": 6379,
            "password": password,
            "db": 0,
            "timeout": 1,
        }
        return db

    # ── 属性 7: 连接状态 ──────────────────────────────────────
    @given(should_succeed=st.booleans())
    @settings(max_examples=20, deadline=None)
    def test_prop7_connection_status(self, should_succeed: bool):
        """
        属性7（连接状态）：无论 AUTH 成功或回退，方法必须返回明确的 bool 值。
        """
        db = self._make_db_manager()

        mock_redis = MagicMock()
        if should_succeed:
            mock_redis.ping.return_value = True
        else:
            mock_redis.ping.side_effect = Exception("AUTH failed")

        # 模拟无密码客户端同样行为
        mock_redis_noauth = MagicMock()
        mock_redis_noauth.ping.return_value = True

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_cls.side_effect = [mock_redis, mock_redis_noauth]
            result = db._detect_redis()

        # 结果必须是 (bool, str) 元组
        assert isinstance(result, tuple), f"返回值应为 tuple，实际 {type(result)}"
        assert len(result) == 2, f"返回值长度应为 2，实际 {len(result)}"
        assert isinstance(result[0], bool), f"第一个元素应为 bool，实际 {type(result[0])}"

    # ── 属性 8: 无密码回退不抛异常 ────────────────────────────
    def test_prop8_no_auth_fallback_no_exception(self):
        """
        属性8（无密码回退）：如果 AUTH 失败且触发回退逻辑，不应抛出异常。
        """
        db = self._make_db_manager()
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("NOAUTH Authentication required")
        mock_redis_noauth = MagicMock()
        mock_redis_noauth.ping.return_value = True

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_cls.side_effect = [mock_redis, mock_redis_noauth]
            result = db._detect_redis()

        assert result[0] is True, f"AUTH 回退应该成功连接: {result}"
        assert "连接成功" in result[1], f"返回消息应指示成功: {result}"

    # ── Redis 未启用 ──────────────────────────────────────────
    def test_redis_disabled(self):
        """Redis 未启用时应直接返回 False"""
        db = self._make_db_manager(redis_enabled=False)
        result = db._detect_redis()
        assert result[0] is False
        assert "未启用" in result[1]

    # ── AUTH 回退后仍失败 ────────────────────────────────────
    def test_auth_fallback_still_fails(self):
        """即使回退后仍连接失败，应返回 False 而非异常"""
        db = self._make_db_manager()
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("NOAUTH Authentication required")
        mock_redis_noauth = MagicMock()
        mock_redis_noauth.ping.side_effect = Exception("Connection refused")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_cls.side_effect = [mock_redis, mock_redis_noauth]
            result = db._detect_redis()

        assert result[0] is False, f"回退也失败时应返回 False: {result}"
        assert isinstance(result[1], str)


# ==============================================================
# 入口
# ==============================================================

if __name__ == "__main__":
    # 直接运行模式 (不依赖 pytest)
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--hypothesis-show-statistics"]))
