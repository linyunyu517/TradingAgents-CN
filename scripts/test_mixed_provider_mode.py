"""
测试混合供应商模式
验证快速模型和深度模型可以来自不同厂家
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("测试混合供应商模式")
print("=" * 80)

# 测试配置
test_cases = [
    {
        "name": "阿里百炼 + Google",
        "quick_model": "qwen-plus",
        "deep_model": "gemini-2.5-flash",
        "expected_quick_provider": "dashscope",
        "expected_deep_provider": "google",
    },
    {
        "name": "DeepSeek + 阿里百炼",
        "quick_model": "deepseek-chat",
        "deep_model": "qwen-max",
        "expected_quick_provider": "deepseek",
        "expected_deep_provider": "dashscope",
    },
    {
        "name": "同一厂家（阿里百炼）",
        "quick_model": "qwen-plus",
        "deep_model": "qwen-max",
        "expected_quick_provider": "dashscope",
        "expected_deep_provider": "dashscope",
    },
]

# 导入查询函数
from app.services.simple_analysis_service import get_provider_and_url_by_model_sync

for i, test_case in enumerate(test_cases, 1):
    print(f"\n{'=' * 80}")
    print(f"测试 {i}: {test_case['name']}")
    print(f"{'=' * 80}")

    quick_model = test_case["quick_model"]
    deep_model = test_case["deep_model"]

    print("\n📝 配置:")
    print(f"   快速模型: {quick_model}")
    print(f"   深度模型: {deep_model}")

    try:
        # 查询快速模型
        print("\n🔍 查询快速模型配置...")
        quick_info = get_provider_and_url_by_model_sync(quick_model)
        quick_provider = quick_info["provider"]
        quick_url = quick_info["backend_url"]

        print("✅ 快速模型:")
        print(f"   供应商: {quick_provider}")
        print(f"   API URL: {quick_url}")

        # 查询深度模型
        print("\n🔍 查询深度模型配置...")
        deep_info = get_provider_and_url_by_model_sync(deep_model)
        deep_provider = deep_info["provider"]
        deep_url = deep_info["backend_url"]

        print("✅ 深度模型:")
        print(f"   供应商: {deep_provider}")
        print(f"   API URL: {deep_url}")

        # 验证结果
        print("\n🧪 验证结果:")

        if quick_provider == test_case["expected_quick_provider"]:
            print(f"   ✅ 快速模型供应商正确: {quick_provider}")
        else:
            print(f"   ❌ 快速模型供应商错误: 期望 {test_case['expected_quick_provider']}, 实际 {quick_provider}")

        if deep_provider == test_case["expected_deep_provider"]:
            print(f"   ✅ 深度模型供应商正确: {deep_provider}")
        else:
            print(f"   ❌ 深度模型供应商错误: 期望 {test_case['expected_deep_provider']}, 实际 {deep_provider}")

        # 检查是否为混合模式
        if quick_provider != deep_provider:
            print("\n🔀 [混合模式] 检测到不同厂家的模型组合")
            print(f"   快速模型: {quick_model} ({quick_provider})")
            print(f"   深度模型: {deep_model} ({deep_provider})")
        else:
            print(f"\n✅ [统一模式] 两个模型来自同一厂家: {quick_provider}")

        print(f"\n✅ 测试 {i} 通过!")

    except Exception as e:
        print(f"\n❌ 测试 {i} 失败: {e}")
        import traceback

        traceback.print_exc()

print(f"\n{'=' * 80}")
print("所有测试完成!")
print(f"{'=' * 80}")

# 测试 TradingGraph 混合模式
print(f"\n{'=' * 80}")
print("测试 TradingGraph 混合模式初始化")
print(f"{'=' * 80}")

try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    # 测试混合模式配置
    config = {
        "llm_provider": "dashscope",  # 主要供应商（向后兼容）
        "quick_think_llm": "qwen-plus",
        "deep_think_llm": "gemini-2.5-flash",
        "quick_provider": "dashscope",
        "deep_provider": "google",
        "quick_backend_url": "https://dashscope.aliyuncs.com/api/v1",
        "deep_backend_url": "https://generativelanguage.googleapis.com/v1",
        "backend_url": "https://dashscope.aliyuncs.com/api/v1",  # 向后兼容
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "memory_enabled": False,  # 禁用内存以加快测试
        "project_dir": str(project_root),
    }

    print("\n📝 创建 TradingGraph 实例...")
    print(f"   快速模型: {config['quick_think_llm']} ({config['quick_provider']})")
    print(f"   深度模型: {config['deep_think_llm']} ({config['deep_provider']})")

    graph = TradingAgentsGraph(selected_analysts=["market"], config=config)

    print("\n✅ TradingGraph 创建成功!")
    print(f"   快速模型类型: {type(graph.quick_thinking_llm).__name__}")
    print(f"   深度模型类型: {type(graph.deep_thinking_llm).__name__}")

    # 验证模型类型
    if "DashScope" in type(graph.quick_thinking_llm).__name__:
        print("   ✅ 快速模型使用阿里百炼适配器")
    else:
        print(f"   ⚠️ 快速模型类型: {type(graph.quick_thinking_llm).__name__}")

    if "Google" in type(graph.deep_thinking_llm).__name__:
        print("   ✅ 深度模型使用 Google 适配器")
    else:
        print(f"   ⚠️ 深度模型类型: {type(graph.deep_thinking_llm).__name__}")

    print("\n✅ 混合模式测试通过!")

except Exception as e:
    print(f"\n❌ TradingGraph 测试失败: {e}")
    import traceback

    traceback.print_exc()

print(f"\n{'=' * 80}")
print("✅ 所有测试完成!")
print(f"{'=' * 80}")
