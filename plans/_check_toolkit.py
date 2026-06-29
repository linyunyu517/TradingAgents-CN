import os
import sys

sys.path.insert(0, r"D:\AI-Projects\TradingAgents-CN_v1.0.1")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-d6efb2f03c334db28bdb6dca77e5db91")

# 检查 tradingagents.agents.Toolkit
from tradingagents.agents import Toolkit

print(f"Toolkit class: {Toolkit}")
print(f"Toolkit type: {type(Toolkit)}")

# 检查 tradingagents.agents 模块内容
import tradingagents.agents

print(f"agents module file: {tradingagents.agents.__file__}")
keys = [k for k in dir(tradingagents.agents) if not k.startswith("_")]
print(f"agents module exports: {keys}")
