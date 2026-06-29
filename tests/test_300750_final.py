#!/usr/bin/env python3
"""
测试更新后的统一基本面分析函数
验证300750的估值指标是否正确显示
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG


def test_300750_fundamentals():
    """测试300750的基本面分析"""
    print("🔍 测试300750基本面分析...")

    # 设置研究深度
    config = DEFAULT_CONFIG.copy()
    config["research_depth"] = "标准"

    # 创建Toolkit实例
    toolkit = Toolkit(config=config)

    # 测试300750（不带后缀）
    ticker = "300750"
    print(f"\n📊 分析股票: {ticker}")

    try:
        result = toolkit.get_stock_fundamentals_unified(ticker)
        print("✅ 成功获取基本面数据")

        # 检查是否包含估值指标
        if "PE" in result or "市盈率" in result:
            print("✅ 发现PE估值指标")
        else:
            print("❌ 未发现PE估值指标")

        if "PB" in result or "市净率" in result:
            print("✅ 发现PB估值指标")
        else:
            print("❌ 未发现PB估值指标")

        # 打印完整的分析结果
        print("\n" + "=" * 80)
        print("📋 完整分析结果:")
        print("=" * 80)
        print(result)
        print("=" * 80)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_300750_fundamentals()
