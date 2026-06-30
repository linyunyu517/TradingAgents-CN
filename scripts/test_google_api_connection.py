"""
测试 Google API 连接
直接调用 .env 中的 GOOGLE_API_KEY，测试 gemini-2.5-flash 模型
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("测试 Google API 连接")
print("=" * 80)

# 1. 检查 API Key
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    print("❌ 未找到 GOOGLE_API_KEY 环境变量")
    print("请在 .env 文件中设置：GOOGLE_API_KEY=your-api-key")
    sys.exit(1)

print(f"✅ 找到 GOOGLE_API_KEY: {google_api_key[:10]}...{google_api_key[-4:]}")

# 2. 测试网络连接
print("\n" + "=" * 80)
print("测试网络连接")
print("=" * 80)

import socket
import time


def test_connection(host, port=443, timeout=5):
    """测试 TCP 连接"""
    try:
        start_time = time.time()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        elapsed = time.time() - start_time
        return True, elapsed
    except Exception as e:
        return False, str(e)


# 测试 Google API 域名
hosts = ["generativelanguage.googleapis.com", "www.google.com", "googleapis.com"]

for host in hosts:
    success, result = test_connection(host)
    if success:
        print(f"✅ {host}: 连接成功 ({result:.2f}秒)")
    else:
        print(f"❌ {host}: 连接失败 - {result}")

# 3. 测试 Google AI API
print("\n" + "=" * 80)
print("测试 Google AI API (gemini-2.5-flash)")
print("=" * 80)

try:
    from langchain_google_genai import ChatGoogleGenerativeAI

    print("📝 创建 ChatGoogleGenerativeAI 实例...")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=google_api_key,
        temperature=0.7,
        max_tokens=100,
        timeout=30,  # 30秒超时
    )

    print("✅ LLM 实例创建成功")
    print(f"   模型: {llm.model}")

    # 发送测试消息
    print("\n📤 发送测试消息: '你好，请用一句话介绍你自己'")
    start_time = time.time()

    response = llm.invoke("你好，请用一句话介绍你自己")

    elapsed = time.time() - start_time

    print(f"✅ API 调用成功！耗时: {elapsed:.2f}秒")
    print("\n📥 响应内容:")
    print(f"   {response.content}")

    # 测试工具调用
    print("\n" + "=" * 80)
    print("测试工具调用功能")
    print("=" * 80)

    from langchain_core.tools import tool

    @tool
    def get_weather(city: str) -> str:
        """获取指定城市的天气信息"""
        return f"{city}的天气是晴天，温度25度"

    llm_with_tools = llm.bind_tools([get_weather])

    print("📤 发送测试消息: '北京的天气怎么样？'")
    start_time = time.time()

    response = llm_with_tools.invoke("北京的天气怎么样？")

    elapsed = time.time() - start_time

    print(f"✅ 工具调用测试成功！耗时: {elapsed:.2f}秒")

    if hasattr(response, "tool_calls") and response.tool_calls:
        print("\n🔧 检测到工具调用:")
        for i, tool_call in enumerate(response.tool_calls, 1):
            print(f"   {i}. 工具: {tool_call.get('name')}")
            print(f"      参数: {tool_call.get('args')}")
    else:
        print("\n📥 直接响应:")
        print(f"   {response.content}")

    print("\n" + "=" * 80)
    print("✅ 所有测试通过！Google API 连接正常")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    print("\n详细错误信息:")
    import traceback

    traceback.print_exc()

    print("\n" + "=" * 80)
    print("可能的原因:")
    print("=" * 80)
    print("1. API Key 无效或已过期")
    print("2. 网络连接问题（需要科学上网）")
    print("3. 防火墙阻止了连接")
    print("4. API 配额已用完")
    print("\n建议:")
    print("- 检查 .env 文件中的 GOOGLE_API_KEY 是否正确")
    print("- 确认是否需要配置代理")
    print("- 访问 https://aistudio.google.com/app/apikey 检查 API Key 状态")
