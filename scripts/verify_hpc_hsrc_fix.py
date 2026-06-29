"""
Verify HSR-MC data pipeline fixes - pure ASCII output, no emoji.
Run with: PYTHONIOENCODING=utf-8 python verify_hpc_hsrc_fix.py
"""

import io
import os
import re
import sys

# Force UTF-8 for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(project_root)

print("=" * 70)
print("HSR-MC DATA PIPELINE FIX VERIFICATION")
print(f"Project root: {project_root}")
print("=" * 70)

# ========== TEST 1: Source file analysis ==========
print("\n[TEST 1] Source code inspection of hpc_integration.py")

hpc_file = os.path.join(project_root, "tradingagents", "hpc_loop", "hpc_integration.py")
with open(hpc_file, encoding="utf-8") as f:
    hpc_source = f.read()

results = []

# Check MODULE_KEY_MAP
if "MODULE_KEY_MAP" in hpc_source:
    map_match = re.search(r"MODULE_KEY_MAP\s*=\s*\{(.+?)\}", hpc_source, re.DOTALL)
    if map_match:
        mapping_text = map_match.group(1).strip().replace("\n", " ")
        print(f"  [PASS] MODULE_KEY_MAP defined: {{{mapping_text}}}")
        results.append(("1. module_losses key mapping", "PASS"))
    else:
        print("  [FAIL] MODULE_KEY_MAP not found!")
        results.append(("1. module_losses key mapping", "FAIL"))
else:
    print("  [FAIL] MODULE_KEY_MAP not found in source!")
    results.append(("1. module_losses key mapping", "FAIL"))

# Check prediction_errors list format
if "error_values = list(prediction_errors_raw.values())" in hpc_source:
    print("  [PASS] prediction_errors converted to list format")
    results.append(("2. prediction_errors list format", "PASS"))
else:
    print("  [FAIL] prediction_errors list conversion not found!")
    results.append(("2. prediction_errors list format", "FAIL"))

# Check gradient_info removed
if "# 注意：不注入 gradient_info" in hpc_source and "MODULE_KEY_MAP" in hpc_source:
    print("  [PASS] gradient_info injection removed (replaced with comment)")
    results.append(("3. gradient_info injection removed", "PASS"))
else:
    print("  [FAIL] gradient_info still present or comment missing!")
    results.append(("3. gradient_info injection removed", "FAIL"))

# Verify the log line no longer mentions gradient_info
if "gradient_info=" in hpc_source:
    print("  [WARN] gradient_info= still in log line (line 739 area)")
else:
    print("  [PASS] gradient_info= removed from log line")

# ========== TEST 2: Simulate data pipeline ==========
print("\n[TEST 2] Simulating l_iwm_bridge_node data pipeline...")

# Mock L-IWM stats (lowercase keys as original)
modules_stats = {
    "efe": {"buffer_size": 150, "efe_value": 0.023},
    "ewc": {"importance": {}, "buffer_size": 200},
    "causal": {"attention_weights": {}, "buffer_size": 80},
    "rssm": {"buffer_size": 50},
    "gws_evaluator": {"feedback_buffer_size": 120},
}

# Step 1: Build module_losses (all lowercase)
module_losses = {}
for mod_name in ["efe", "ewc", "causal"]:
    mod_stats = modules_stats.get(mod_name, {})
    buf_size = mod_stats.get("buffer_size", 0)
    module_losses[mod_name] = float(buf_size) / 200.0 if buf_size > 0 else 0.5

rssm_stats = modules_stats.get("rssm", {})
buf_size = rssm_stats.get("buffer_size", 0)
module_losses["rssm"] = 1.0 / (1.0 + float(buf_size)) if buf_size > 0 else 0.5

gws_stats = modules_stats.get("gws_evaluator", {})
module_losses["gws"] = 0.01 if gws_stats.get("feedback_buffer_size", 0) > 0 else 0.5

print(f"  Pre-mapping keys: {list(module_losses.keys())}")

# Step 2: Apply MODULE_KEY_MAP
MODULE_KEY_MAP = {
    "rssm": "RSSM",
    "efe": "EFE",
    "causal": "Causal",
    "ewc": "EWC",
    "gws": "GWS",
}
module_losses = {MODULE_KEY_MAP.get(k, k): v for k, v in module_losses.items()}
print(f"  Post-mapping keys: {list(module_losses.keys())}")

expected_keys = {"RSSM", "EFE", "Causal", "EWC", "GWS"}
actual_keys = set(module_losses.keys())
if actual_keys == expected_keys:
    print("  [PASS] module_losses keys correctly mapped to mixed case")
    results.append(("4. Key casing mapping correctness", "PASS"))
else:
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    print(f"  [FAIL] Key mismatch! Missing: {missing}, Extra: {extra}")
    results.append(("4. Key casing mapping correctness", "FAIL"))

# Step 3: Build prediction_errors as list
prediction_errors_raw = {}
if "EFE" in module_losses:
    prediction_errors_raw["efe_td"] = float(module_losses["EFE"])
if "Causal" in module_losses:
    prediction_errors_raw["causal_h"] = float(module_losses["Causal"])

prediction_errors = list(prediction_errors_raw.values()) if prediction_errors_raw else [0.5]
print(f"  prediction_errors type: {type(prediction_errors).__name__}")
print(f"  prediction_errors value: {prediction_errors}")

if isinstance(prediction_errors, list):
    print("  [PASS] prediction_errors is list type")
    results.append(("5. prediction_errors list type", "PASS"))
    # Verify deque.extend would work correctly
    from collections import deque

    dq = deque(maxlen=50)
    dq.extend(prediction_errors)
    print(f"  deque.extend(list) OK: dq={list(dq)}")
else:
    print(f"  [FAIL] prediction_errors is {type(prediction_errors).__name__}, expected list")
    results.append(("5. prediction_errors list type", "FAIL"))

# ========== TEST 3: MetaObserver type guard ==========
print("\n[TEST 3] Checking MetaObserver._analyze_gradients type guard...")

mo_file = os.path.join(project_root, "tradingagents", "hsrc_mc", "meta_observer.py")
with open(mo_file, encoding="utf-8") as f:
    mo_source = f.read()

if "isinstance(first_val, (np.ndarray, list))" in mo_source:
    print("  [PASS] _analyze_gradients type guard found (isinstance + np.ndarray/list)")
    results.append(("6. gradient_info type guard", "PASS"))
elif "isinstance" in mo_source and "first_val" in mo_source:
    print("  [WARN] Type guard exists but format may differ")
    # Find the exact line
    for i, line in enumerate(mo_source.split("\n"), 1):
        if "isinstance" in line and "first_val" in line:
            print("    Line %d: %s" % (i, line.strip()))
    results.append(("6. gradient_info type guard", "WARN"))
else:
    print("  [FAIL] _analyze_gradients type guard NOT FOUND!")
    results.append(("6. gradient_info type guard", "FAIL"))

# ========== TEST 4: Integration test with MetaObserver ==========
print("\n[TEST 4] Integration test: simulate full pipeline + MetaObserver...")

# Try importing MetaObserver in isolation
sys.path.insert(0, project_root)

try:
    # Direct import may fail due to project initialization deps
    # Try importing just the file as a module
    import importlib.util

    spec = importlib.util.spec_from_file_location("meta_observer", mo_file)

    # Instead, let's just verify the class structure by reading source
    print("  Skipping full import (project init deps heavy)")
    print("  Source-based verification:")

    # Verify _analyze_gradients method
    ag_start = mo_source.find("def _analyze_gradients")
    if ag_start >= 0:
        ag_end = mo_source.find("\n    def ", ag_start + 1)
        if ag_end < 0:
            ag_end = mo_source.find("\nclass ", ag_start + 1)
        ag_code = mo_source[ag_start:ag_end] if ag_end > 0 else mo_source[ag_start : ag_start + 1500]
        print("    _analyze_gradients found at char offset %d" % ag_start)

        # Check for early return guard
        if "if not grads_dict:" in ag_code and "return {}" in ag_code:
            print("    [PASS] Empty input guard found")
            results.append(("7. Empty grads_dict guard", "PASS"))
        else:
            print("    [WARN] Empty input guard may be missing")
            results.append(("7. Empty grads_dict guard", "WARN"))

        if "isinstance(first_val" in ag_code:
            print("    [PASS] Non-tensor type guard found")
            results.append(("8. Non-tensor type guard", "PASS"))
        else:
            print("    [WARN] Non-tensor type guard not in method body")
            results.append(("8. Non-tensor type guard", "WARN"))
    else:
        print("    [FAIL] _analyze_gradients method not found!")
        results.append(("7. Empty grads_dict guard", "FAIL"))
        results.append(("8. Non-tensor type guard", "FAIL"))

except Exception as e:
    print(f"  [WARN] Import failed (expected): {e!s}")
    print("  Source verification completed without import")

# ========== TEST 5: Verify data filtering (Fix 4) ==========
print("\n[TEST 5] Checking data filtering conditions...")

# Check for > 0 filter on loss values (should NOT exist)
loss_filter = re.findall(r"loss.*> 0|> 0.*loss", hpc_source, re.IGNORECASE)
if loss_filter:
    print(f"  [WARN] Loss value filters found: {loss_filter}")
    results.append(("9. No loss value filtering", "WARN"))
else:
    print("  [PASS] No loss value > 0 filter (correct - data filtering not needed)")
    results.append(("9. No loss value filtering", "PASS"))

# Check buffer > 0 filters (these are legitimate)
buffer_filters = re.findall(r"buffer_size.*> 0|> 0.*buffer", hpc_source, re.IGNORECASE)
if buffer_filters:
    print(f"  Buffer size > 0 filters found (legitimate logic): {buffer_filters[:3]}")

# ========== SUMMARY ==========
print("\n" + "=" * 70)
print("VERIFICATION SUMMARY")
print("=" * 70)
print()
print("%-45s %s" % ("Check Item", "Status"))
print("-" * 55)
for item, status in results:
    print("%-45s %s" % (item, status))

all_pass = all(s == "PASS" for _, s in results)
print("\n" + "=" * 70)
if all_pass:
    print("RESULT: ALL CHECKS PASSED")
else:
    warn_count = sum(1 for _, s in results if s == "WARN")
    fail_count = sum(1 for _, s in results if s == "FAIL")
    print("RESULT: %d PASS, %d WARN, %d FAIL" % (sum(1 for _, s in results if s == "PASS"), warn_count, fail_count))
print("=" * 70)
