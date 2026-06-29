#!/usr/bin/env python3
"""
Phase 3: 属性基测试 (Property-Based Testing)
对数据标准化方法进行属性基测试
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Try to use hypothesis, fallback to random testing
HYPOTHESIS_AVAILABLE = False
try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    pass

import random


class TestStandardizationInvariants(unittest.TestCase):
    """测试 standardized_basic_info 和 standardize_quotes 的不变性"""

    @classmethod
    def setUpClass(cls):
        from tradingagents.dataflows.providers.base_provider import BaseStockDataProvider

        class TestProvider(BaseStockDataProvider):
            async def connect(self):
                return True

            async def get_stock_basic_info(self, symbol=None):
                return {}

            async def get_stock_quotes(self, symbol):
                return {}

            async def get_historical_data(self, symbol, start_date, end_date=None):
                return None

        cls.provider = TestProvider("test")

    def _check_basic_info_invariants(self, result):
        """验证 basic_info 输出的不变性条件"""
        self.assertIsInstance(result, dict, "输出必须是 dict")
        self.assertIn("code", result, "必须包含 code")
        self.assertIn("name", result, "必须包含 name")
        self.assertIn("symbol", result, "必须包含 symbol")
        # code 必须是字符串
        self.assertIsInstance(result["code"], str)
        self.assertIsInstance(result["name"], str)
        self.assertIsInstance(result["symbol"], str)

    def _check_quotes_invariants(self, result):
        """验证 quotes 输出的不变性条件"""
        self.assertIsInstance(result, dict, "输出必须是 dict")
        self.assertIn("code", result, "必须包含 code")
        if result.get("price") is not None:
            self.assertIsInstance(result["price"], (int, float))

    # ---- Hypothesis-based tests (if available) ----

    @unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis 未安装，跳过")
    def test_basic_info_with_hypothesis(self):
        """使用 hypothesis 随机测试 basic_info 标准化"""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        @given(
            st.dictionaries(
                keys=st.sampled_from(
                    ["code", "symbol", "name", "ts_code", "industry", "area", "list_date", "full_symbol"],
                ),
                values=st.one_of(st.none(), st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False)),
                min_size=0,
                max_size=20,
            ),
        )
        @settings(max_examples=100)
        def test(raw_data):
            result = self.provider.standardize_basic_info(raw_data)
            self._check_basic_info_invariants(result)

        test()

    @unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis 未安装，跳过")
    def test_quotes_with_hypothesis(self):
        """使用 hypothesis 随机测试 quotes 标准化"""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        @given(
            st.dictionaries(
                keys=st.sampled_from(
                    [
                        "code",
                        "name",
                        "symbol",
                        "price",
                        "open",
                        "high",
                        "low",
                        "volume",
                        "amount",
                        "change",
                        "pct_change",
                        "turnover",
                    ],
                ),
                values=st.one_of(
                    st.none(),
                    st.text(),
                    st.integers(min_value=-1e9, max_value=1e9),
                    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
                ),
                min_size=0,
                max_size=20,
            ),
        )
        @settings(max_examples=100)
        def test(raw_data):
            result = self.provider.standardize_quotes(raw_data)
            self._check_quotes_invariants(result)

        test()

    # ---- Random testing (fallback) ----

    def _generate_random_dict(self, keys_pool, max_items=15):
        """生成随机字典用于测试"""
        n = random.randint(0, max_items)
        result = {}
        for _ in range(n):
            key = random.choice(keys_pool)
            value_type = random.randint(0, 4)
            if value_type == 0:
                value = None
            elif value_type == 1:
                value = ""
            elif value_type == 2:
                value = str(random.randint(1, 999999))
            elif value_type == 3:
                value = random.random() * 1000
            else:
                value = "test_value"
            result[key] = value
        return result

    def test_basic_info_random_100(self):
        """随机生成 100 组输入测试 basic_info 标准化"""
        keys = [
            "code",
            "symbol",
            "name",
            "ts_code",
            "industry",
            "area",
            "list_date",
            "full_symbol",
            "unknown_key",
            None,
        ]
        for _i in range(100):
            raw = self._generate_random_dict(keys)
            result = self.provider.standardize_basic_info(raw)
            self._check_basic_info_invariants(result)

    def test_quotes_random_100(self):
        """随机生成 100 组输入测试 quotes 标准化"""
        keys = [
            "code",
            "name",
            "symbol",
            "price",
            "open",
            "high",
            "low",
            "volume",
            "amount",
            "change",
            "pct_change",
            "turnover",
            None,
        ]
        for _i in range(100):
            raw = self._generate_random_dict(keys)
            result = self.provider.standardize_quotes(raw)
            self._check_quotes_invariants(result)

    def test_extreme_values(self):
        """测试极端值情况"""
        extremes = [
            {"code": "", "name": "", "symbol": ""},
            {"code": "a" * 1000, "name": "b" * 1000},
            {"code": "000001", "name": "测试" * 500},
            {"code": "000001", "name": "Test", "price": float("inf")},
            {"code": "000001", "name": "Test", "price": float("-inf")},
            {"code": "000001", "name": "Test", "price": float("nan")},
        ]
        for raw in extremes:
            result = self.provider.standardize_basic_info(raw)
            self._check_basic_info_invariants(result)
            result2 = self.provider.standardize_quotes(raw)
            self._check_quotes_invariants(result2)

    def test_none_input(self):
        """测试 None 输入（如果发生）"""
        # 模拟函数调用时的类型错误
        with self.assertRaises((TypeError, AttributeError)):
            self.provider.standardize_basic_info(None)
        with self.assertRaises((TypeError, AttributeError)):
            self.provider.standardize_quotes(None)

    def test_list_input(self):
        """测试列表输入（错误类型）"""
        with self.assertRaises((TypeError, AttributeError)):
            self.provider.standardize_basic_info(["a", "b"])
        with self.assertRaises((TypeError, AttributeError)):
            self.provider.standardize_quotes(["a", "b"])

    def test_too_many_fields(self):
        """测试超多字段输入"""
        big_dict = {f"key_{i}": f"value_{i}" for i in range(1000)}
        big_dict["code"] = "000001"
        big_dict["name"] = "Test"
        result = self.provider.standardize_basic_info(big_dict)
        self._check_basic_info_invariants(result)


class TestEfinanceStandardizationConsistency(unittest.TestCase):
    """测试 EfinanceProvider 的标准化一致性"""

    @classmethod
    def setUpClass(cls):
        try:
            from tradingagents.dataflows.providers.china.efinance import EfinanceProvider

            cls.provider = EfinanceProvider()
        except Exception as e:
            raise unittest.SkipTest(f"efinance provider 导入失败: {e}")

    def test_standardize_methods_match_base(self):
        """验证 EfinanceProvider 的标准化方法与基类签名一致"""
        import inspect

        base_sig = inspect.signature(self.provider.standardize_basic_info)
        # 至少接受一个位置参数
        params = list(base_sig.parameters.keys())
        self.assertGreaterEqual(len(params), 1)

    def test_basic_info_output_structure(self):
        """验证基本输出结构"""
        result = self.provider.standardize_basic_info({"code": "000001", "name": "平安银行"})
        self.assertIn("code", result)
        self.assertIn("name", result)
        self.assertIn("symbol", result)
        self.assertIn("market_info", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
