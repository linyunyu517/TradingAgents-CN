"""
TradingAgents-CN v1.0.1 Bug Fix Focused Smoke Test
直接验证修改后的 3 个文件的核心逻辑
"""

import sys
import traceback

PASS = 0
FAIL = 0
ERRORS = []


def test(name: str, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✅ {name}")
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, str(e), traceback.format_exc()))
        print(f"  ❌ {name}: {e}")


print("=" * 60)
print("🔬 TradingAgents-CN v1.0.1 修复冒烟测试")
print("=" * 60)

# ---- 1. DEFAULT_CONFIG 直接验证 ----
print("\n📦 DEFAULT_CONFIG 验证...")


def test_config_baostock():
    from tradingagents.default_config import DEFAULT_CONFIG

    sources = DEFAULT_CONFIG["l_iwm_real_data_sources"]
    assert "baostock" in sources, f"baostock 不在数据源列表中: {sources}"
    assert sources == ["akshare", "baostock"], f"数据源列表异常: {sources}"
    print(f"    ✓ l_iwm_real_data_sources = {sources}")


test("baostock 已添加到数据源配置", test_config_baostock)

# ---- 2. TypedDict 模拟 AgentState ----
print("\n📝 AgentState aif_free_energy_history 防护模式验证...")


def test_typeddict_or_pattern():
    """使用 TypedDict 模拟测试 (state.get() or []) 防御模式"""
    from typing import TypedDict

    class MockAgentState(TypedDict, total=False):
        aif_free_energy_history: list[float] | None
        messages: list
        report: str
        analyst_role: str

    # 场景 1: None（模拟原始bug）
    state1 = MockAgentState(messages=[], report="", analyst_role="test", aif_free_energy_history=None)
    r1 = (state1.get("aif_free_energy_history") or []) + [1.0]
    assert r1 == [1.0], f"场景1(None写入)失败: {r1}"
    print(f"    ✓ 场景1: None + [1.0] = {r1}")

    # 场景 2: 已有数据追加
    state2 = MockAgentState(messages=[], report="", analyst_role="test", aif_free_energy_history=None)
    state2["aif_free_energy_history"] = (state2.get("aif_free_energy_history") or []) + [0.5]
    state2["aif_free_energy_history"] = (state2.get("aif_free_energy_history") or []) + [0.6]
    assert state2["aif_free_energy_history"] == [0.5, 0.6], f"场景2(二次追加)失败: {state2['aif_free_energy_history']}"
    print(f"    ✓ 场景2: 二次追加 = {state2['aif_free_energy_history']}")

    # 场景 3: key不存在
    state3: MockAgentState = {"messages": [], "report": "", "analyst_role": "test"}
    r3 = (state3.get("aif_free_energy_history") or []) + [1.0]
    assert r3 == [1.0], f"场景3(key不存在)失败: {r3}"
    print(f"    ✓ 场景3: key不存在 + [1.0] = {r3}")

    # 场景 4: 读取（模拟 L865）
    state4 = MockAgentState(messages=[], report="", analyst_role="test", aif_free_energy_history=[0.1, 0.2])
    r4_read = state4.get("aif_free_energy_history") or []
    assert r4_read == [0.1, 0.2], f"场景4(读取)失败: {r4_read}"
    print(f"    ✓ 场景4: 读取 = {r4_read}")

    # 场景 5: 读取 None（模拟之前 bug 的 L865）
    state5 = MockAgentState(messages=[], report="", analyst_role="test", aif_free_energy_history=None)
    r5_read = state5.get("aif_free_energy_history") or []
    assert r5_read == [], f"场景5(None读取)失败: {r5_read}"
    print(f"    ✓ 场景5: None读取 = {r5_read}")


test("(state.get() or []) 防御模式全覆盖验证", test_typeddict_or_pattern)

# ---- 3. aif_integration.py 修改文件解析验证 ----
print("\n📄 aif_integration.py 修改验证...")


def test_aif_integration_patch():
    """验证文件中的代码已正确修改"""

    with open(
        r"D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\hpc_loop\aif_integration.py", encoding="utf-8",
    ) as f:
        source = f.read()

    # 验证 L588: 使用 or [] 而不是 , []
    assert 'state.get("aif_free_energy_history", [])' not in source, "L588 仍使用旧模式 (state.get(key, []))"
    assert (
        '(state.get("aif_free_energy_history") or []) + [free_energy]' in source
        or "(state.get('aif_free_energy_history') or []) + [free_energy]" in source
    ), "L588 未找到 or [] 模式"
    print("    ✓ L588 已使用 or [] 防御模式")

    # 验证 L865: 使用 or [] 而不是裸 get
    lines = source.split("\n")
    # 找到第865行附近
    for i, line in enumerate(lines, 1):
        if "aif_free_energy_history" in line and "state.get" in line and i > 850:
            assert "or []" in line or "or []" in line, f"L{i} 未使用 or [] 防御模式: {line.strip()}"
            print(f"    ✓ L{i} 已使用 or [] 防御模式: {line.strip()}")
            break


test("aif_integration.py 修改验证", test_aif_integration_patch)

# ---- 4. default_config.py 修改验证 ----
print("\n📄 default_config.py 修改验证...")


def test_default_config_patch():
    with open(r"D:\AI-Projects\TradingAgents-CN_v1.0.1\tradingagents\default_config.py", encoding="utf-8") as f:
        source = f.read()
    assert '"l_iwm_real_data_sources": ["akshare", "baostock"]' in source, "default_config.py 中未找到 baostock 配置"
    print("    ✓ l_iwm_real_data_sources 已包含 baostock")


test("default_config.py 修改验证", test_default_config_patch)

# ---- 5. 结果汇总 ----
print("\n" + "=" * 60)
print(f"📊 冒烟测试结果: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("\n❌ 失败详情:")
    for name, err, _tb in ERRORS:
        print(f"  - {name}: {err}")
else:
    print("🎉 全部通过！")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
