#!/usr/bin/env python3
"""Round 3 Phase 4 — A2: Import smoke test for all modified modules.

验证 Round 3 修改的所有模块可正常导入。
注意：部分类名与源码一致（aif_engine.py 中核心类为 ActiveInference）。
"""

import importlib
import sys
import traceback

# (模块名, 要检查的类名或None只检查模块)
modules = [
    ("tradingagents.hpc_loop.aif_engine", "ActiveInference"),
    ("tradingagents.hpc_loop.aif_integration", None),  # 节点工厂函数
    ("tradingagents.config.database_manager", "DatabaseManager"),
    ("tradingagents.hpc_loop.hpc_config", "HPCLoopConfig"),
    ("tradingagents.hpc_loop.generative_model", "MarketGenerativeModel"),
]

all_pass = True
for mod_name, cls_name in modules:
    try:
        mod = importlib.import_module(mod_name)
        if cls_name:
            getattr(mod, cls_name)  # verify class exists
        label = f"{mod_name}" + (f".{cls_name}" if cls_name else "")
        print(f"✅ 成功导入 {label}")
    except Exception:
        label = f"{mod_name}" + (f".{cls_name}" if cls_name else "")
        print(f"❌ 导入失败 {label}")
        traceback.print_exc()
        all_pass = False

print()
if all_pass:
    print("🎯 A2 导入检查：全部通过")
else:
    print("⚠️ A2 导入检查：存在失败项")
    sys.exit(1)
