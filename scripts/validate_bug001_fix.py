#!/usr/bin/env python
"""
BUG-001 验证脚本：DeepSeek reasoning_content 回传修复验证

测试策略：
1. 单元测试 _get_request_payload 发送侧注入逻辑（mock 父类行为）
2. 单元测试 _create_chat_result 接收侧提取逻辑（mock 原始响应）
3. 验证 NormalizedChatOpenAI 类结构正确
4. 验证 import 链无断裂

使用方式：
  python scripts/validate_bug001_fix.py

预期输出：
  ✅ 所有测试通过，或明确显示失败项
"""

import os
import sys

# 将项目根目录加入 path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0


def test_case(name: str, func):
    """运行一个测试用例并计数"""
    global PASS, FAIL
    try:
        func()
        PASS += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAIL += 1
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        FAIL += 1
        print(f"  ❌ {name}: 异常 — {type(e).__name__}: {e}")


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"期望 {expected!r}, 实际 {actual!r}. {msg}")


# =============================================================
# 测试组 1：import 和类结构验证
# =============================================================
def test_import_and_class_structure():
    """验证 NormalizedChatOpenAI 存在且继承自 ChatOpenAI"""
    from langchain_openai import ChatOpenAI

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    assert issubclass(NormalizedChatOpenAI, ChatOpenAI), "NormalizedChatOpenAI 必须继承 ChatOpenAI"
    assert hasattr(NormalizedChatOpenAI, "_get_request_payload"), "必须重写 _get_request_payload"
    assert hasattr(NormalizedChatOpenAI, "_create_chat_result"), "必须重写 _create_chat_result"


def test_aimessage_imported():
    """验证 AIMessage 导入可用"""
    from langchain_core.messages import AIMessage as AI

    msg = AI(content="test", additional_kwargs={"reasoning_content": "thinking..."})
    assert msg.additional_kwargs["reasoning_content"] == "thinking..."


# =============================================================
# 测试组 2：_get_request_payload 发送侧注入逻辑
# =============================================================
def test_get_request_payload_injects_reasoning_content():
    """
    构造一个包含 reasoning_content 的 AIMessage 历史，
    验证 _get_request_payload 将其注入 API 请求字典。
    """
    from unittest.mock import MagicMock, patch

    from langchain_core.messages import AIMessage, HumanMessage

    # 动态 import 目标类
    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    # 构造一个 NormalizedChatOpenAI 实例（避免真正的 API key）
    NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    # 模拟父类的 _get_request_payload 返回基础 payload
    with patch.object(
        NormalizedChatOpenAI,
        "_convert_input",
        return_value=MagicMock(
            to_messages=lambda: [
                HumanMessage(content="hello"),
                AIMessage(content="response", additional_kwargs={"reasoning_content": "step by step"}),
                HumanMessage(content="continue"),
            ],
        ),
    ):
        # 构造一个模拟 payload（父类正常会返回这个）
        with patch.object(
            NormalizedChatOpenAI,
            "_get_request_payload",
            # 先调用父类逻辑 — 但为了测试，我们直接构造
            return_value={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "response"},
                    {"role": "user", "content": "continue"},
                ],
            },
        ):
            # 但我们需要真正测试我们的方法，所以不 mock 自己
            # 改用真实调用的方式测试
            pass

    # 更直接的测试：通过调用 super 来验证
    # 由于父类 _get_request_payload 需要 API key 等，我们用 mock 方式
    from unittest.mock import patch

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm2 = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    # Mock _convert_input 和父类的 _get_request_payload
    mock_input = MagicMock()
    mock_input.to_messages.return_value = [
        HumanMessage(content="hello"),
        AIMessage(content="response", additional_kwargs={"reasoning_content": "step by step reasoning"}),
    ]

    parent_payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "response"},
        ],
    }

    with (
        patch.object(NormalizedChatOpenAI, "_convert_input", return_value=mock_input),
        patch("langchain_openai.chat_models.base.BaseChatOpenAI._get_request_payload", return_value=parent_payload),
    ):
        payload = llm2._get_request_payload(mock_input)

    # 验证 reasoning_content 被注入到 assistant 消息中
    assistant_msgs = [m for m in payload["messages"] if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 1, "应该有 assistant 消息"
    assert assistant_msgs[0].get("reasoning_content") == "step by step reasoning", (
        f"reasoning_content 应被注入, 实际: {assistant_msgs[0]}"
    )


def test_get_request_payload_no_reasoning_skips():
    """验证如果没有 reasoning_content，payload 不会被修改"""
    from unittest.mock import MagicMock, patch

    from langchain_core.messages import AIMessage, HumanMessage

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    mock_input = MagicMock()
    mock_input.to_messages.return_value = [
        HumanMessage(content="hello"),
        AIMessage(content="response"),  # 无 reasoning_content
    ]

    parent_payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "response"},
        ],
    }

    with (
        patch.object(NormalizedChatOpenAI, "_convert_input", return_value=mock_input),
        patch("langchain_openai.chat_models.base.BaseChatOpenAI._get_request_payload", return_value=parent_payload),
    ):
        payload = llm._get_request_payload(mock_input)

    # 验证没有 reasoning_content 字段被添加
    for m in payload["messages"]:
        assert "reasoning_content" not in m, "不应注入 reasoning_content"


# =============================================================
# 测试组 3：_create_chat_result 接收侧提取逻辑
# =============================================================
def test_create_chat_result_extracts_reasoning_content():
    """验证 _create_chat_result 从响应中提取 reasoning_content 到 additional_kwargs"""
    from unittest.mock import patch

    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    # 构造一个模拟的原始 API 响应
    mock_response = {
        "id": "chatcmpl-test",
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "这是分析结果", "reasoning_content": "这是思考过程..."},
                "finish_reason": "stop",
            },
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    # Mock 父类的 _create_chat_result 返回基础 ChatResult
    # 注意：父类返回的 AIMessage 不会有 reasoning_content
    base_msg = AIMessage(content="这是分析结果")
    base_result = ChatResult(
        generations=[ChatGeneration(message=base_msg)], llm_output={"token_usage": mock_response["usage"]},
    )

    with patch("langchain_openai.chat_models.base.BaseChatOpenAI._create_chat_result", return_value=base_result):
        result = llm._create_chat_result(mock_response)

    # 验证 reasoning_content 被提取到 additional_kwargs
    assert len(result.generations) > 0
    msg = result.generations[0].message
    assert isinstance(msg, AIMessage)
    assert msg.additional_kwargs.get("reasoning_content") == "这是思考过程...", (
        f"reasoning_content 应被提取, 实际: {msg.additional_kwargs}"
    )


def test_create_chat_result_no_reasoning_skips():
    """验证如果没有 reasoning_content，不会被添加"""
    from unittest.mock import patch

    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    mock_response = {
        "id": "chatcmpl-test",
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "这是分析结果",
                },
                "finish_reason": "stop",
            },
        ],
        "usage": {},
    }

    base_msg = AIMessage(content="这是分析结果")
    base_result = ChatResult(generations=[ChatGeneration(message=base_msg)], llm_output={})

    with patch("langchain_openai.chat_models.base.BaseChatOpenAI._create_chat_result", return_value=base_result):
        result = llm._create_chat_result(mock_response)

    msg = result.generations[0].message
    assert "reasoning_content" not in msg.additional_kwargs


def test_create_chat_result_invalid_response_graceful():
    """验证无效响应不会抛出异常"""
    from unittest.mock import patch

    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    base_msg = AIMessage(content="test")
    base_result = ChatResult(generations=[ChatGeneration(message=base_msg)])

    with patch("langchain_openai.chat_models.base.BaseChatOpenAI._create_chat_result", return_value=base_result):
        # 传递一个没有 choices 的响应
        result = llm._create_chat_result({"id": "test"})

    # 应该优雅地返回父类结果
    assert result is base_result


# =============================================================
# 测试组 4：端到端集成验证（Mock 完整调用链）
# =============================================================
def test_full_roundtrip_reasoning_content_preserved():
    """
    模拟完整一轮 LLM 调用：
    1. API 返回 reasoning_content
    2. _create_chat_result 提取到 additional_kwargs
    3. 下一轮 _get_request_payload 注入到 API 请求
    """
    from unittest.mock import MagicMock, patch

    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    llm = NormalizedChatOpenAI(
        model="deepseek-chat",
        openai_api_key="sk-test",
        openai_api_base="https://api.deepseek.com",
    )

    # --- 第一轮：接收侧 ---
    response1 = {
        "id": "1",
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "分析1", "reasoning_content": "思考1"},
                "finish_reason": "stop",
            },
        ],
        "usage": {},
    }

    base_msg1 = AIMessage(content="分析1")
    base_result1 = ChatResult(generations=[ChatGeneration(message=base_msg1)])

    with patch("langchain_openai.chat_models.base.BaseChatOpenAI._create_chat_result", return_value=base_result1):
        result1 = llm._create_chat_result(response1)

    msg1 = result1.generations[0].message
    assert msg1.additional_kwargs.get("reasoning_content") == "思考1", "第一轮应提取 reasoning_content"

    # --- 第二轮：发送侧（包含第一轮的 response）---
    mock_input = MagicMock()
    mock_input.to_messages.return_value = [
        HumanMessage(content="继续"),
        AIMessage(content="分析1", additional_kwargs={"reasoning_content": "思考1"}),
    ]

    parent_payload2 = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "继续"},
            {"role": "assistant", "content": "分析1"},
        ],
    }

    with (
        patch.object(NormalizedChatOpenAI, "_convert_input", return_value=mock_input),
        patch("langchain_openai.chat_models.base.BaseChatOpenAI._get_request_payload", return_value=parent_payload2),
    ):
        payload2 = llm._get_request_payload(mock_input)

    # 验证 reasoning_content 被注入到第二轮请求
    assistant_msgs = [m for m in payload2["messages"] if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 1
    assert assistant_msgs[0].get("reasoning_content") == "思考1", (
        f"第二轮应回传 reasoning_content, 实际: {assistant_msgs[0]}"
    )

    print("      ↪ 完整轮转验证通过：接收→存储→回传")


# =============================================================
# 主入口
# =============================================================
def main():
    global PASS, FAIL
    print("=" * 60)
    print("  BUG-001: DeepSeek reasoning_content 回传修复验证")
    print("=" * 60)
    print()

    # 测试组 1：类结构
    print("[组 1] 类结构验证")
    test_case("NormalizedChatOpenAI 继承自 ChatOpenAI", test_import_and_class_structure)
    test_case("AIMessage additional_kwargs 可用", test_aimessage_imported)
    print()

    # 测试组 2：发送侧
    print("[组 2] 发送侧 — _get_request_payload 注入逻辑")
    test_case("有 reasoning_content 时注入", test_get_request_payload_injects_reasoning_content)
    test_case("无 reasoning_content 时不注入", test_get_request_payload_no_reasoning_skips)
    print()

    # 测试组 3：接收侧
    print("[组 3] 接收侧 — _create_chat_result 提取逻辑")
    test_case("有 reasoning_content 时提取", test_create_chat_result_extracts_reasoning_content)
    test_case("无 reasoning_content 时不添加", test_create_chat_result_no_reasoning_skips)
    test_case("无效响应优雅处理", test_create_chat_result_invalid_response_graceful)
    print()

    # 测试组 4：集成
    print("[组 4] 端到端集成")
    test_case("完整轮转（接收→存储→回传）", test_full_roundtrip_reasoning_content_preserved)
    print()

    # 结果汇总
    print("=" * 60)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"  🎉 全部 {PASS}/{total} 测试通过")
        print("=" * 60)
        return 0
    print(f"  ❌ {PASS}/{total} 通过, {FAIL} 失败")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
