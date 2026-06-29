#!/usr/bin/env python3
"""
TradingAgents-CN v1.0.1 定向变异测试 (阶段8) - 简化版
=====================================================
使用 monkey-patch 直接替换 _get_data_source_priority_for_sync,
验证 e2e 测试能否捕获每种变异。

变异 (5 个):
  M1: 移除 'efinance'
  M2: 'efinance' 移到最后
  M3: 移除 'baostock'
  M4: 反转整个列表
  M5: 返回空列表
"""

import json
import os
import sys
import time

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
FAIL = 0
ERRORS = []

MUTATIONS = [
    ("M1_remove_efinance", "移除 'efinance'", lambda sc: ["tushare", "akshare", "baostock"]),
    ("M2_efinance_last", "'efinance' 移到最后", lambda sc: ["tushare", "akshare", "baostock", "efinance"]),
    ("M3_remove_baostock", "移除 'baostock'", lambda sc: ["tushare", "efinance", "akshare"]),
    ("M4_reverse_order", "反转优先级顺序", lambda sc: ["baostock", "akshare", "efinance", "tushare"]),
    ("M5_empty_list", "返回空列表", lambda sc: []),
]


def main():
    global PASS, FAIL

    print("=" * 70)
    print("  🧬 TradingAgents-CN v1.0.1 定向变异测试 (阶段8)")
    print("  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)

    # 导入原始 StockValidator
    print("\n📦 导入 StockValidator...")
    from tradingagents.utils.stock_validator import StockValidator

    # 获取原始方法的引用 (保存 baseline)
    original_method = StockValidator._get_data_source_priority_for_sync

    # Baseline 验证
    validator = StockValidator()
    baseline = original_method(validator, "000001.SZ")
    print(f"   baseline 优先级: {baseline}")
    assert "efinance" in baseline, f"efinance 不在 baseline 中: {baseline}"
    assert baseline.index("efinance") <= 1, f"efinance 位置不对: {baseline}"
    print(f"   ✅ baseline 通过 (efinance @ idx={baseline.index('efinance')})")
    print()

    results = []

    for mut_id, desc, factory in MUTATIONS:
        print(f"  🧬 {mut_id}: {desc}")
        try:
            # monkey-patch: 替换目标函数
            StockValidator._get_data_source_priority_for_sync = lambda self, sc, f=factory: f(sc)

            # 运行 e2e 相同的断言
            priority = StockValidator()._get_data_source_priority_for_sync("000001.SZ")
            assert isinstance(priority, list), f"类型: {type(priority)}"
            assert "efinance" in priority, "efinance 缺失"
            idx = priority.index("efinance")
            assert idx <= 1, f"efinance @ {idx}"
            # 如果变异后仍然通过断言 → 变异 SURVIVED
            killed = False
            msg = f"通过: efinance @ idx={idx}, list={priority}"
        except AssertionError as e:
            killed = True
            msg = f"捕获: {e}"
        except Exception as e:
            killed = True
            msg = f"异常捕获: {type(e).__name__}: {e}"

        status = "💀 KILLED" if killed else "🧟 SURVIVED"
        print(f"     {status}: {msg}")
        results.append(
            {
                "mutation": mut_id,
                "description": desc,
                "killed": killed,
                "message": msg,
            },
        )
        if killed:
            PASS += 1
        else:
            FAIL += 1

    # 恢复原始方法
    StockValidator._get_data_source_priority_for_sync = original_method

    # ── 汇总 ──
    print("\n" + "=" * 70)
    print(f"  📊 变异测试结果: {PASS} killed, {FAIL} survived")
    for r in results:
        icon = "💀" if r["killed"] else "🧟"
        print(f"     {icon} {r['mutation']}: {r['description']}")

    kill_rate = PASS / len(MUTATIONS) * 100
    print(f"\n  🎯 杀灭率: {kill_rate:.0f}% ({PASS}/{len(MUTATIONS)})")
    if kill_rate >= 80:
        print("  ✅ 测试套件对 P0 修复的防护质量良好")
    elif kill_rate >= 50:
        print("  ⚠️ 中等防护, 部分变异未被捕获")
    else:
        print("  ❌ 防护不足, 测试套件需要增强")
    print("=" * 70)

    # 保存报告
    report_path = os.path.join(PROJECT_ROOT, "_phase8_mutation_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "phase": "8",
                "name": "manual targeted mutation testing",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target": "stock_validator._get_data_source_priority_for_sync",
                "mutations_count": len(MUTATIONS),
                "killed": PASS,
                "survived": FAIL,
                "kill_rate_pct": round(kill_rate, 1),
                "details": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n  报告已保存: {report_path}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
