import logging
import os
from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)


# ========== BUG-007 修复: API Key 脱敏工具函数 ==========
def mask_api_key(key: str | None) -> str:
    """脱敏 API Key，仅保留前 4 位和后 4 位，中间替换为 ****"""
    if not key:
        return "None"
    key_str = str(key)
    if len(key_str) <= 12:
        return key_str[:4] + "****" + key_str[-4:] if len(key_str) > 8 else "****"
    return key_str[:4] + "****" + key_str[-4:]


# Token tracking — used by NormalizedChatOpenAI to record LLM token consumption
try:
    from tradingagents.config.config_manager import token_tracker

    TOKEN_TRACKING_AVAILABLE = True
except ImportError:
    TOKEN_TRACKING_AVAILABLE = False


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI wrapper that normalizes typed content blocks to text
    and tracks token usage via TokenTracker.
    """

    def __init__(self, **kwargs):
        # Pop custom arg before passing the rest to ChatOpenAI
        provider = kwargs.pop("_provider", "openai")
        super().__init__(**kwargs)
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._provider = provider

    def invoke(self, input, config=None, **kwargs):
        # RUNTIME-051: 分离 LLM 调用异常与 token 统计异常，避免吞掉真正的调用失败
        result = super().invoke(input, config, **kwargs)
        normalized = normalize_content(result)

        # --- Token tracking (独立 try，不影响 LLM 异常传播) ---
        input_tokens = 0
        output_tokens = 0

        try:
            # 1) response_metadata.token_usage (langchain-openai standard)
            if hasattr(normalized, "response_metadata") and normalized.response_metadata:
                token_usage = normalized.response_metadata.get("token_usage", {}) or {}
                if token_usage:
                    input_tokens = token_usage.get("prompt_tokens", 0) or 0
                    output_tokens = token_usage.get("completion_tokens", 0) or 0

            # 2) usage_metadata (langchain-openai >= 0.3)
            if input_tokens == 0 and output_tokens == 0:
                if hasattr(normalized, "usage_metadata") and normalized.usage_metadata:
                    u = normalized.usage_metadata
                    input_tokens = u.get("input_tokens", 0) or u.get("prompt_tokens", 0) or 0
                    output_tokens = u.get("output_tokens", 0) or u.get("completion_tokens", 0) or 0
        except Exception as token_extract_err:
            logger.warning("Token 元数据解析异常，不影响请求 (%s)", token_extract_err)

        # RUNTIME-052: 即使元数据解析失败，token 累加仍应执行
        try:
            if input_tokens > 0 or output_tokens > 0:
                self._total_input_tokens += input_tokens
                self._total_output_tokens += output_tokens

                # Persist through the global TokenTracker
                if TOKEN_TRACKING_AVAILABLE:
                    try:
                        token_tracker.track_usage(
                            provider=self._provider,
                            model_name=self.model_name,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            session_id="graph_execution",
                            analysis_type="llm_inference",
                        )
                    except Exception as track_err:
                        logger.warning("LLM 分析指标记录失败，不影响请求 (%s)", track_err)
        except Exception as token_acc_err:
            logger.warning("Token 累加异常 (%s)", token_acc_err)

        return normalized

    # ========== BUG-001 修复: DeepSeek reasoning_content 回传错误 ==========
    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        """发送侧修复：将历史 AIMessage 中的 reasoning_content 注入 API 请求字典。

        DeepSeek 在 thinking mode 下要求 assistant 消息中的 reasoning_content
        必须在后续请求中原样回传，否则返回 400 错误。
        LangChain 的 _convert_message_to_dict 不识别 reasoning_content，
        必须在此手动注入。
        """
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        try:
            messages_payload = payload.get("messages", [])
            messages_input = self._convert_input(input_).to_messages()
            for msg, api_msg in zip(messages_input, messages_payload, strict=False):
                if isinstance(msg, AIMessage) and api_msg.get("role") == "assistant":
                    rc = msg.additional_kwargs.get("reasoning_content")
                    if rc:
                        api_msg["reasoning_content"] = rc
        except Exception as exc:
            logger.warning("reasoning_content 回传注入失败，不影响请求 (%s)", exc)

        # ========== BUG-P0 修复: 剥离空 tool_calls 数组，防止 DeepSeek API 400 ==========
        try:
            for api_msg in payload.get("messages", []):
                if api_msg.get("role") == "assistant":
                    if "tool_calls" in api_msg and not api_msg["tool_calls"]:
                        del api_msg["tool_calls"]
        except Exception as exc:
            logger.warning("tool_calls 空数组剥离失败，不影响请求 (%s)", exc)

        return payload

    def _create_chat_result(self, response, generation_info=None):
        """接收侧修复：从原始 API 响应中提取 reasoning_content 存入 additional_kwargs。

        LangChain 的 _convert_dict_to_message 在解析 DeepSeek 响应时
        会丢弃 reasoning_content 字段，导致后续轮次无法回传。
        此处从原始响应中捕获该字段并存入 additional_kwargs 以持久化。
        """
        result = super()._create_chat_result(response, generation_info)
        try:
            response_dict = response if isinstance(response, dict) else response.model_dump()
            for choice, gen in zip(response_dict.get("choices", []), result.generations, strict=False):
                rc = choice.get("message", {}).get("reasoning_content")
                if rc and isinstance(gen.message, AIMessage):
                    gen.message.additional_kwargs["reasoning_content"] = rc
        except Exception as exc:
            logger.warning("reasoning_content 提取失败，不影响请求 (%s)", exc)
        return result


# [FIX] 2026-06-18: Fix 2.3 - DeepSeek 不支持 model_kwargs，运行时过滤
_DEEPSEEK_SKIP_KWARGS = {
    "model_kwargs",
}

# [FIX] 2026-06-18: Fix 2.3 - 已知不支持 model_kwargs 的提供器集合
_PROVIDERS_SKIP_MODEL_KWARGS = frozenset({"deepseek"})

_PASSTHROUGH_KWARGS = (
    "temperature",
    "max_tokens",
    "timeout",
    "max_retries",
    "callbacks",
    "http_client",
    "http_async_client",
    "model_kwargs",
)

_PROVIDER_CONFIG = {
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4/", "ZHIPU_API_KEY"),
    "qianfan": ("https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "aihubmix": ("https://aihubmix.com/v1", "AIHUBMIX_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "custom_openai": (None, "CUSTOM_OPENAI_API_KEY"),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI and OpenAI-compatible providers."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider: str = provider.lower()

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.provider in _PROVIDER_CONFIG:
            default_base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or default_base_url
            if api_key_env:
                api_key = self.kwargs.get("api_key") or os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url
            api_key = self.kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key

        # [FIX] 2026-06-18: Fix 2.3 - 对不支持 model_kwargs 的提供器过滤掉该参数
        skip_keys = _DEEPSEEK_SKIP_KWARGS if self.provider in _PROVIDERS_SKIP_MODEL_KWARGS else set()
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs and key not in skip_keys:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatOpenAI(_provider=self.provider, **llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
