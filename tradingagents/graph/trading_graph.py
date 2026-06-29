# TradingAgents/graph/trading_graph.py

import json
import os
import time
from pathlib import Path
from typing import Any

from langgraph.errors import InvalidUpdateError
from langgraph.prebuilt import ToolNode

from tradingagents.agents import Toolkit
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_utils import reset_data_fetch_failed  # [PR #2] ContextVar 重置
from tradingagents.default_config import DEFAULT_CONFIG

# RUNTIME-041: 循环导入风险——create_llm_client 来自 __init__.py 的延迟导入包装器，
# 该包装器内部使用 from .factory import create_llm_client，避免在模块加载时触发
# tradingagents.llm_clients → tradingagents.factory → ... 的循环依赖链。
# 保留此导入模式，不改为直接 from .factory 导入以维持解环效果。
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.provider_keys import env_key_for_provider, normalize_provider_key

# RUNTIME-040: 统一日志导入——仅保留 logging_manager 版本，删除重复的 logging_init 导入
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")
from tradingagents.dataflows.interface import set_config
from tradingagents.hpc_loop.aif_integration import AIFEngineManager

# ========== 三轮改造 (HPC-Loop / AIF) 导入 ==========
from tradingagents.hpc_loop.hpc_integration import HPCLoopManager

from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .reflection import Reflector
from .setup import GraphSetup
from .signal_processing import SignalProcessor


def create_llm_by_provider(
    provider: str,
    model: str,
    backend_url: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    api_key: str | None = None,
    **extra_kwargs,
) -> Any:
    """
    根据 provider 创建对应的 LLM 实例

    Args:
        provider: 供应商名称 (google, dashscope, deepseek, openai, etc.)
        model: 模型名称
        backend_url: API 地址
        temperature: 温度参数
        max_tokens: 最大 token 数
        timeout: 超时时间
        api_key: API Key（可选，如果未提供则从环境变量读取）

    Returns:
        LLM 实例
    """
    logger.info(f"🔧 [创建LLM] provider={provider}, model={model}, url={backend_url}")
    logger.debug(f"🔑 [API Key] 来源: {'数据库配置' if api_key else '环境变量'}")

    normalized_provider = normalize_provider_key(provider)

    if normalized_provider in {
        "openai",
        "siliconflow",
        "openrouter",
        "aihubmix",
        "ollama",
        "deepseek",
        "qwen",
        "glm",
        "custom_openai",
        "qianfan",
    }:
        if not api_key:
            if normalized_provider == "siliconflow":
                api_key = os.getenv("SILICONFLOW_API_KEY")
            elif normalized_provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            elif normalized_provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
            else:
                env_key = env_key_for_provider(normalized_provider)
                if env_key:
                    api_key = os.getenv(env_key)

        factory_provider = "openai" if normalized_provider == "siliconflow" else normalized_provider
        client = create_llm_client(
            provider=factory_provider,
            model=model,
            base_url=backend_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **extra_kwargs,
        )
        return client.get_llm()

    if normalized_provider == "google":
        # 优先使用传入的 API Key，否则从环境变量读取
        google_api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError("使用Google需要设置GOOGLE_API_KEY环境变量或在数据库中配置API Key")

        client = create_llm_client(
            provider="google",
            model=model,
            base_url=backend_url or None,
            api_key=google_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **extra_kwargs,
        )
        return client.get_llm()

    if normalized_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            base_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **extra_kwargs,
        )

    # 🔧 自定义厂家：使用 OpenAI 兼容模式
    logger.info(f"🔧 使用 OpenAI 兼容模式处理自定义厂家: {provider}")

    # 尝试从环境变量获取 API Key（支持多种命名格式）
    api_key_candidates = [
        f"{provider.upper()}_API_KEY",  # 例如: KYX_API_KEY
        f"{provider}_API_KEY",  # 例如: kyx_API_KEY
        "CUSTOM_OPENAI_API_KEY",  # 通用环境变量
    ]

    custom_api_key = None
    for env_var in api_key_candidates:
        custom_api_key = os.getenv(env_var)
        if custom_api_key:
            logger.info(f"✅ 从环境变量 {env_var} 获取到 API Key")
            break

    if not custom_api_key:
        logger.warning(f"⚠️ 未找到自定义厂家 {provider} 的 API Key，尝试使用默认配置")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        base_url=backend_url,
        api_key=custom_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _create_provider_pair(
    provider: str,
    config: dict[str, Any],
    quick_temperature: float,
    quick_max_tokens: int,
    quick_timeout: int,
    deep_temperature: float,
    deep_max_tokens: int,
    deep_timeout: int,
    backend_url: str | None = None,
    api_key: str | None = None,
    quick_extra_kwargs: dict[str, Any] | None = None,
    deep_extra_kwargs: dict[str, Any] | None = None,
) -> tuple[Any, Any]:
    resolved_backend_url = backend_url if backend_url is not None else config.get("backend_url", "")
    shared_api_key = api_key or config.get("quick_api_key") or config.get("deep_api_key")
    quick_extra_kwargs = quick_extra_kwargs or {}
    deep_extra_kwargs = deep_extra_kwargs or {}

    # 🐛 [BUG-035 Fix C] 添加 max_retries=2 默认值，防止 API 认证失败时 httpx 无限重试
    if "max_retries" not in quick_extra_kwargs:
        quick_extra_kwargs["max_retries"] = 2
    if "max_retries" not in deep_extra_kwargs:
        deep_extra_kwargs["max_retries"] = 2

    deep_llm = create_llm_by_provider(
        provider=provider,
        model=config["deep_think_llm"],
        backend_url=resolved_backend_url,
        temperature=deep_temperature,
        max_tokens=deep_max_tokens,
        timeout=deep_timeout,
        api_key=shared_api_key,
        **deep_extra_kwargs,
    )
    quick_llm = create_llm_by_provider(
        provider=provider,
        model=config["quick_think_llm"],
        backend_url=resolved_backend_url,
        temperature=quick_temperature,
        max_tokens=quick_max_tokens,
        timeout=quick_timeout,
        api_key=shared_api_key,
        **quick_extra_kwargs,
    )
    return deep_llm, quick_llm


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=None,
        debug=False,
        config: dict[str, Any] | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
        """
        if not selected_analysts:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        self.debug = debug
        self.config = {**DEFAULT_CONFIG, **config} if config else DEFAULT_CONFIG

        # 🔒 [P1-2] 必需键验证：检查关键配置项是否存在，缺失时打印错误并回退到 DEFAULT_CONFIG
        _required_keys = ["project_dir", "llm_provider", "quick_think_llm", "deep_think_llm", "backend_url"]
        for _key in _required_keys:
            if _key not in self.config or not self.config.get(_key):
                logger.warning(f"🔒 配置键 '{_key}' 缺失或为空，使用 DEFAULT_CONFIG 回退值")
                self.config[_key] = DEFAULT_CONFIG.get(_key)

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config.get("project_dir", DEFAULT_CONFIG.get("project_dir", "")), "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs
        # 🔧 从配置中读取模型参数（优先使用用户配置，否则使用默认值）
        quick_config = self.config.get("quick_model_config", {})
        deep_config = self.config.get("deep_model_config", {})

        # 读取快速模型参数
        quick_max_tokens = quick_config.get("max_tokens", 4000)
        quick_temperature = quick_config.get("temperature", 0.7)
        quick_timeout = quick_config.get("timeout", 180)

        # 读取深度模型参数
        deep_max_tokens = deep_config.get("max_tokens", 4000)
        deep_temperature = deep_config.get("temperature", 0.7)
        deep_timeout = deep_config.get("timeout", 900)

        # 🔧 检查是否为混合模式（快速模型和深度模型来自不同厂家）
        quick_provider = self.config.get("quick_provider")
        deep_provider = self.config.get("deep_provider")
        normalized_quick_provider = normalize_provider_key(quick_provider) if quick_provider else None
        normalized_deep_provider = normalize_provider_key(deep_provider) if deep_provider else None
        quick_backend_url = self.config.get("quick_backend_url")
        deep_backend_url = self.config.get("deep_backend_url")
        normalized_provider = normalize_provider_key(
            self.config.get("llm_provider", DEFAULT_CONFIG.get("llm_provider", "")),
        )

        if (
            normalized_quick_provider
            and normalized_deep_provider
            and normalized_quick_provider != normalized_deep_provider
        ):
            # 混合模式：快速模型和深度模型来自不同厂家
            logger.info("🔀 [混合模式] 检测到不同厂家的模型组合")
            logger.info(
                f"   快速模型: {self.config.get('quick_think_llm', DEFAULT_CONFIG.get('quick_think_llm', ''))} ({normalized_quick_provider})",
            )
            logger.info(
                f"   深度模型: {self.config.get('deep_think_llm', DEFAULT_CONFIG.get('deep_think_llm', ''))} ({normalized_deep_provider})",
            )

            # 使用统一的函数创建 LLM 实例
            self.quick_thinking_llm = create_llm_by_provider(
                provider=normalized_quick_provider,
                model=self.config.get("quick_think_llm", DEFAULT_CONFIG.get("quick_think_llm", "")),
                backend_url=quick_backend_url or self.config.get("backend_url", ""),
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                api_key=self.config.get("quick_api_key"),  # 🔥 传递 API Key
            )

            self.deep_thinking_llm = create_llm_by_provider(
                provider=normalized_deep_provider,
                model=self.config.get("deep_think_llm", DEFAULT_CONFIG.get("deep_think_llm", "")),
                backend_url=deep_backend_url or self.config.get("backend_url", ""),
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                api_key=self.config.get("deep_api_key"),  # 🔥 传递 API Key
            )

            logger.info("✅ [混合模式] LLM 实例创建成功")

        elif normalized_provider in {"openai", "siliconflow", "openrouter", "aihubmix", "ollama"}:
            provider = normalized_provider
            logger.info(
                f"🔧 [{provider}-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [{provider}-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )

            api_key = None
            if provider == "siliconflow":
                api_key = os.getenv("SILICONFLOW_API_KEY")
                if not api_key:
                    raise ValueError("使用SiliconFlow需要设置SILICONFLOW_API_KEY环境变量")
            elif provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("使用OpenRouter需要设置OPENROUTER_API_KEY或OPENAI_API_KEY环境变量")
            elif provider == "aihubmix":
                api_key = os.getenv("AIHUBMIX_API_KEY")
                if not api_key:
                    raise ValueError("使用AiHubMix需要设置AIHUBMIX_API_KEY环境变量")

            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider=provider,
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=self.config.get("backend_url", DEFAULT_CONFIG.get("backend_url", "")),
                api_key=api_key,
            )
        elif normalized_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            logger.info(
                f"🔧 [Anthropic-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [Anthropic-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )

            self.deep_thinking_llm = ChatAnthropic(
                model=self.config.get("deep_think_llm", DEFAULT_CONFIG.get("deep_think_llm", "")),
                base_url=self.config.get("backend_url", DEFAULT_CONFIG.get("backend_url", "")),
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
            )
            self.quick_thinking_llm = ChatAnthropic(
                model=self.config.get("quick_think_llm", DEFAULT_CONFIG.get("quick_think_llm", "")),
                base_url=self.config.get("backend_url", DEFAULT_CONFIG.get("backend_url", "")),
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
            )
        elif normalized_provider == "google":
            # 使用统一 llm_clients 入口，但底层仍返回 ChatGoogleOpenAI 兼容适配器
            logger.info("🔧 使用统一 llm_clients 路径初始化 Google AI（保留工具调用兼容行为）")

            # 🔥 优先使用数据库配置的 API Key，否则从环境变量读取
            google_api_key = (
                self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv("GOOGLE_API_KEY")
            )
            if not google_api_key:
                raise ValueError("使用Google AI需要在数据库中配置API Key或设置GOOGLE_API_KEY环境变量")

            logger.debug(
                f"🔑 [Google AI] API Key 来源: {'数据库配置' if self.config.get('quick_api_key') or self.config.get('deep_api_key') else '环境变量'}",
            )

            logger.info(
                f"🔧 [Google-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [Google-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )

            # 获取 backend_url（如果配置中有的话）
            backend_url = self.config.get("backend_url")
            if backend_url:
                logger.info(f"🔧 [Google AI] 使用配置的 backend_url: {backend_url}")
            else:
                logger.info("🔧 [Google AI] 未配置 backend_url，使用默认端点")

            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="google",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=backend_url or None,
                api_key=google_api_key,
                quick_extra_kwargs={"transport": "rest"},
            )

            logger.info("✅ [Google AI] 已启用优化的工具调用和内容格式处理并应用用户配置的模型参数")
        elif normalized_provider == "qwen":
            logger.info("🔧 使用统一 llm_clients 路径初始化阿里百炼/通义千问")
            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="qwen",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=self.config.get("backend_url"),
            )
            logger.info("✅ [阿里百炼] 已通过 llm_clients 初始化成功并应用用户配置的模型参数")
        elif normalized_provider == "deepseek":
            deepseek_api_key = (
                self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv("DEEPSEEK_API_KEY")
            )
            if not deepseek_api_key:
                raise ValueError("使用DeepSeek需要设置DEEPSEEK_API_KEY环境变量")

            deepseek_base_url = self.config.get("backend_url") or os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com",
            )
            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="deepseek",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=deepseek_base_url,
                api_key=deepseek_api_key,
            )
            logger.info("✅ [DeepSeek] 已通过 llm_clients 初始化成功并应用用户配置的模型参数")
        elif normalized_provider == "custom_openai":
            custom_api_key = os.getenv("CUSTOM_OPENAI_API_KEY")
            if not custom_api_key:
                raise ValueError("使用自定义OpenAI端点需要设置CUSTOM_OPENAI_API_KEY环境变量")

            custom_base_url = self.config.get("custom_openai_base_url", "https://api.openai.com/v1")
            logger.info(f"🔧 [自定义OpenAI] 使用端点: {custom_base_url}")
            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="custom_openai",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=custom_base_url,
                api_key=custom_api_key,
            )
            logger.info("✅ [自定义OpenAI] 已通过 llm_clients 初始化成功并应用用户配置的模型参数")
        elif normalized_provider == "qianfan":
            # 百度千帆（文心一言）配置 - 统一由适配器内部读取与校验 QIANFAN_API_KEY
            logger.info(
                f"🔧 [千帆-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [千帆-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )
            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="qianfan",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
            )
            logger.info("✅ [千帆] 文心一言适配器已配置成功并应用用户配置的模型参数")
        elif normalized_provider == "glm":
            # 🔥 优先使用数据库配置的 API Key，否则从环境变量读取
            zhipu_api_key = (
                self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv("ZHIPU_API_KEY")
            )
            logger.debug(
                f"🔑 [智谱AI] API Key 来源: {'数据库配置' if self.config.get('quick_api_key') or self.config.get('deep_api_key') else '环境变量'}",
            )

            if not zhipu_api_key:
                raise ValueError("使用智谱AI需要在数据库中配置API Key或设置ZHIPU_API_KEY环境变量")

            # 🔧 从配置中读取模型参数（优先使用用户配置，否则使用默认值）
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 600)

            logger.info(
                f"🔧 [智谱AI-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [智谱AI-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )

            # 获取 backend_url（如果配置中有的话）
            backend_url = self.config.get("backend_url")
            if backend_url:
                logger.info(f"🔧 [智谱AI] 使用配置的 backend_url: {backend_url}")
            else:
                logger.info("🔧 [智谱AI] 未配置 backend_url，使用默认端点")
            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="glm",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=backend_url,
                api_key=zhipu_api_key,
            )

            logger.info("✅ [智谱AI] 已通过 llm_clients 初始化成功并应用用户配置的模型参数")
        else:
            provider_name = self.config.get("llm_provider", DEFAULT_CONFIG.get("llm_provider", ""))
            logger.info(f"🔧 使用统一 llm_clients 路径处理自定义厂家: {provider_name}")
            api_key_candidates = [
                f"{provider_name.upper()}_API_KEY",  # 例如: KYX_API_KEY
                f"{provider_name}_API_KEY",  # 例如: kyx_API_KEY
                "CUSTOM_OPENAI_API_KEY",  # 通用环境变量
            ]

            custom_api_key = None
            for env_var in api_key_candidates:
                custom_api_key = os.getenv(env_var)
                if custom_api_key:
                    logger.info(f"✅ 从环境变量 {env_var} 获取到 API Key")
                    break

            if not custom_api_key:
                raise ValueError(
                    f"使用自定义厂家 {provider_name} 需要设置以下环境变量之一:\n"
                    f"  - {provider_name.upper()}_API_KEY\n"
                    f"  - CUSTOM_OPENAI_API_KEY",
                )

            # 获取 backend_url（从配置中获取）
            backend_url = self.config.get("backend_url")
            if not backend_url:
                raise ValueError(f"使用自定义厂家 {provider_name} 需要在数据库配置中设置 default_base_url")

            logger.info(f"🔧 [自定义厂家 {provider_name}] 使用端点: {backend_url}")

            # 🔧 从配置中读取模型参数
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 600)

            logger.info(
                f"🔧 [{provider_name}-快速模型] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s",
            )
            logger.info(
                f"🔧 [{provider_name}-深度模型] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s",
            )

            self.deep_thinking_llm, self.quick_thinking_llm = _create_provider_pair(
                provider="custom_openai",
                config=self.config,
                quick_temperature=quick_temperature,
                quick_max_tokens=quick_max_tokens,
                quick_timeout=quick_timeout,
                deep_temperature=deep_temperature,
                deep_max_tokens=deep_max_tokens,
                deep_timeout=deep_timeout,
                backend_url=backend_url,
                api_key=custom_api_key,
            )

            logger.info(f"✅ [自定义厂家 {provider_name}] 已配置自定义端点并应用用户配置的模型参数")

        self.toolkit = Toolkit(config=self.config)

        # Initialize memories (如果启用)
        memory_enabled = self.config.get("memory_enabled", True)
        if memory_enabled:
            # 使用单例ChromaDB管理器，避免并发创建冲突
            self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
            self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
            self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
            self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
            self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)
        else:
            # 创建空的内存对象
            self.bull_memory = None
            self.bear_memory = None
            self.trader_memory = None
            self.invest_judge_memory = None
            self.risk_manager_memory = None

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # ========== 三轮改造: 初始化 HPC-Loop 管理器 ==========
        self.hpc_loop = HPCLoopManager(config=self.config)
        if self.hpc_loop.enabled:
            logger.info("[HPC] HPC-Loop enabled")

        # ========== AIF 引擎初始化 ==========
        self.aif_engine = None
        if self.config.get("use_aif_engine", True):
            try:
                self.aif_engine = AIFEngineManager(config=self.config)
                if self.aif_engine.enabled:
                    logger.info("[AIF] AIF engine enabled")
            except Exception as e:
                logger.warning(f"[AIF] AIF engine init failed: {e}")
                self.aif_engine = None

        # Initialize components
        # 🔥 [修复] 从配置中读取辩论轮次参数
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1),
        )
        logger.info("🔧 [ConditionalLogic] 初始化完成:")
        logger.info(f"   - max_debate_rounds: {self.conditional_logic.max_debate_rounds}")
        logger.info(f"   - max_risk_discuss_rounds: {self.conditional_logic.max_risk_discuss_rounds}")

        # ========== 融合架构 (Fusion) 模式检测 ==========
        fusion_mode = self.config.get("fusion_mode", "unified")
        self.use_fusion_mode = fusion_mode == "unified"
        if self.use_fusion_mode:
            logger.info("[Fusion] 🚀 启用 HPC+AIF 统一融合执行路径")
        elif fusion_mode == "aif_only":
            logger.info("[Fusion] AIF-only 模式 (legacy)")
        elif fusion_mode == "hpc_only":
            logger.info("[Fusion] HPC-only 模式 (legacy)")
        else:
            logger.info("[Fusion] 传统模式 (legacy)")

        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.toolkit,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
            self.config,
            getattr(self, "react_llm", None),
            hpc_loop_manager=self.hpc_loop,
            aif_engine_manager=self.aif_engine,
            use_fusion_mode=self.use_fusion_mode,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        # 🆕 [子任务F] 启用 DeepSeek JSON Mode (response_format=json_object)
        # SignalProcessor 内部使用 _invoke_json_mode() 自动尝试 JSON Mode，
        # 并保留现有 5 层 JSON 修复作为 fallback
        # RUNTIME-043: 为 quick_thinking_llm 添加 None 守卫，避免 SignalProcessor 接收 None 导致的崩溃
        _signal_llm = self.quick_thinking_llm
        if _signal_llm is None:
            logger.warning("[RUNTIME-043] quick_thinking_llm 为 None，使用 deep_thinking_llm 作为 SignalProcessor 回退")
            _signal_llm = self.deep_thinking_llm
        self.signal_processor = SignalProcessor(_signal_llm, use_json_mode=True)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    @staticmethod
    def _wrap_tool_safe(tool):
        """安全兼容 LangChain invoke 签名差异（Wrapper 模式，不碰 Pydantic 字段）

        使用 object.__setattr__ 绕过 Pydantic v2 的 __setattr__ 限制，
        用实例属性覆盖类方法，确保新旧两种 invoke 签名都可工作。
        """
        orig = tool.invoke
        def _safe_invoke(*args, **kwargs):
            try:
                return orig(*args, **kwargs)
            except TypeError as e:
                if "missing 1 required positional argument: 'input'" in str(e):
                    if not args and "input" in kwargs:
                        return orig(kwargs.pop("input"), **kwargs)
                    if args:
                        return orig(args[0], *args[1:], **kwargs)
                    # LangGraph 内部以 **tool_call_dict 方式展开调用
                    if "args" in kwargs:
                        return orig(kwargs["args"], **kwargs)
                    if kwargs:
                        return orig(list(kwargs.values())[0], **kwargs)
                raise
        object.__setattr__(tool, 'invoke', _safe_invoke)
        return tool

    def _create_tool_nodes(self) -> dict[str, ToolNode]:
        """通过 Toolkit 注册表创建分类 ToolNode。

        每个分类的工具列表由 Toolkit.get_tools(category) 从注册表获取，
        无需硬编码 self.toolkit.XXX 属性引用。缺失的工具自动跳过，
        不会引发 AttributeError（原 _safe_list 的缺陷）。

        ToolNode 包含所有已注册的工具，LLM 通过提示词绑定来选择调用。
        """
        # [H14 Fix] Wrapper 模式兼容 LangChain 新旧 invoke 签名
        def _safe_list(tools):
            return ToolNode([self._wrap_tool_safe(t) for t in tools])

        return {
            "market": _safe_list(Toolkit.get_tools("market")),
            "social": _safe_list(Toolkit.get_tools("social")),
            "news": _safe_list(Toolkit.get_tools("news")),
            "fundamentals": _safe_list(Toolkit.get_tools("fundamentals")),
        }

    # RUNTIME-042: propagate() 内部存在三重代码副本（debug/progress/none 三个分支）。
    # 提取共用逻辑为 _process_stream_chunk() 以减少重复，同时保持各分支的独特行为
    # （debug 有 trace + pretty_print、progress 有额外日志、none 最简）。
    def _process_stream_chunk(
        self,
        chunk,
        node_timings,
        current_node_name,
        current_node_start,
        total_start_time,
        init_agent_state,
        final_state,
        trace,
        args,
        progress_callback=None,
        send_progress=True,
        append_trace=True,
    ):
        """处理单个 stream chunk：记录节点计时、累积状态、发送进度。

        由 propagate() 的三个分支共用，消除 RUNTIME-042 的三重代码副本。

        支持两种 stream_mode:
        - updates: chunk = {node_name: {key: value, ...}}  (per-node 状态 diff)
        - values: chunk = {key: value, ...}               (全状态快照)
        """
        # ========== 检测 stream_mode 类型 ==========
        # 🔧 [BUG-FIX] 直接读取 stream_mode 参数，不再使用启发式检测
        # 启发式检测会误判 updates-mode chunk 为 values-mode，
        # 导致 final_state = chunk 覆盖所有已累积的报告字段 (market_report 等)
        # 参考: https://langchain-ai.github.io/langgraph/concepts/streaming/
        _is_values_mode = (args.get("stream_mode") == "values")

        # ========== values 模式: chunk 是全状态快照 ==========
        if _is_values_mode:
            # 节点计时: values 模式下无法从 chunk 结构推断节点名，跳过
            logger.debug(f"[方案C values] 全状态快照到达，键={list(chunk.keys())}")
            # 发送进度
            if send_progress and progress_callback:
                self._send_progress_update(chunk, progress_callback)
            # values 模式下，每个 chunk 包含完整 state，直接取最后一个作为 final_state
            if append_trace:
                if len(chunk.get("messages", [])) > 0:
                    chunk["messages"][-1].pretty_print()
                trace.append(chunk)
            final_state = chunk
            return current_node_name, current_node_start, final_state

        # ========== updates 模式: chunk = {node_name: {key: value}} ==========
        # 记录节点计时
        for node_name in chunk:
            if not node_name.startswith("__"):
                if current_node_name and current_node_start:
                    elapsed = time.time() - current_node_start
                    node_timings[current_node_name] = elapsed
                    logger.info(f"⏱️ [{current_node_name}] 耗时: {elapsed:.2f}秒")
                current_node_name = node_name
                current_node_start = time.time()
                break

        # 发送进度更新（updates 模式下）
        if send_progress and progress_callback:
            self._send_progress_update(chunk, progress_callback)

        # 累积状态更新
        if final_state is None:
            final_state = init_agent_state.copy()
        for node_name, node_update in chunk.items():
            if not node_name.startswith("__"):
                if node_update is not None and isinstance(node_update, dict):
                    if any(k in str(node_name).lower() for k in ["hsrc", "l_iwm", "hpc", "diffusion"]):
                        logger.info(
                            f"[PROPAGATE-DIAG] 节点 {node_name} 添加到 final_state 的键: {list(node_update.keys())}",
                        )
                    # ✅ [Bug Fix] 使用 reducer-aware 合并：字符串字段 last-write-wins，字典字段深度合并
                    for key, value in node_update.items():
                        if key in final_state and isinstance(final_state[key], dict) and isinstance(value, dict):
                            # 字典字段: 深度合并（与 _dict_merge_reducer 语义一致）
                            merged = {**final_state[key], **value}
                            final_state[key] = merged
                        elif key in final_state and key.endswith("_tool_call_count"):
                            # 计数器字段: max 语义（与 _counter_reducer 一致）
                            final_state[key] = max(final_state[key], value)
                        else:
                            # 字符串/其他字段: last-write-wins
                            # [MoA-Fix] 报告类型字符串字段的空值保护（与 _report_reducer 语义一致）
                            _PROTECTED_REPORT_KEYS = frozenset({
                                "market_report", "sentiment_report",
                                "news_report", "fundamentals_report",
                                "investment_plan", "trader_investment_plan",
                            })
                            if isinstance(value, str) and not value.strip() and key in _PROTECTED_REPORT_KEYS:
                                logger.debug(
                                    f"[PROPAGATE-PROTECT] 跳过空字符串写入 '{key}' (保护已存在值)",
                                )
                                continue
                            final_state[key] = value
                elif node_update is None:
                    logger.debug(f"[PROPAGATE-DIAG] 节点 {node_name} 返回了 None 更新 (stream_mode=updates)")
                else:
                    logger.debug(f"[PROPAGATE] 节点 {node_name} 返回了非dict更新: {type(node_update).__name__}, 跳过")

        # updates 模式下追加到 trace
        if append_trace and len(chunk.get("messages", [])) > 0:
            chunk["messages"][-1].pretty_print()
            trace.append(chunk)
            final_state = chunk

        return current_node_name, current_node_start, final_state

    def propagate(
        self, company_name, trade_date, progress_callback=None, task_id=None, stock_code=None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run the trading agents graph for a company on a specific date.

        Args:
            company_name: Company name or stock symbol
            trade_date: Date for analysis
            progress_callback: Optional callback function for progress updates
            task_id: Optional task ID for tracking performance data
            stock_code: Original stock code (e.g. "601636"), used for market identification
        """

        # [PR #2] 重置数据源故障 ContextVar（确保新分析不受上次运行影响）
        reset_data_fetch_failed()

        # 添加详细的接收日志
        logger.debug("🔍 [GRAPH DEBUG] ===== TradingAgentsGraph.propagate 接收参数 =====")
        logger.debug(f"🔍 [GRAPH DEBUG] 接收到的company_name: '{company_name}' (类型: {type(company_name)})")
        logger.debug(f"🔍 [GRAPH DEBUG] 接收到的trade_date: '{trade_date}' (类型: {type(trade_date)})")
        logger.debug(f"🔍 [GRAPH DEBUG] 接收到的task_id: '{task_id}'")
        logger.debug(f"🔍 [GRAPH DEBUG] 接收到的stock_code: '{stock_code}' (类型: {type(stock_code)})")

        # 🔥 [Bug D 修复] 优先使用 stock_code 作为 ticker，确保市场识别正确
        self.ticker = stock_code or company_name
        logger.debug(
            f"🔍 [GRAPH DEBUG] 设置self.ticker: '{self.ticker}' (来源: {'stock_code' if stock_code else 'company_name'})",
        )

        # Initialize state
        logger.debug(
            f"🔍 [GRAPH DEBUG] 创建初始状态，传递参数: company_name='{company_name}', trade_date='{trade_date}', stock_code='{stock_code}'",
        )
        init_agent_state = self.propagator.create_initial_state(company_name, trade_date, stock_code=stock_code)
        logger.debug(
            f"🔍 [GRAPH DEBUG] 初始状态中的company_of_interest: '{init_agent_state.get('company_of_interest', 'NOT_FOUND')}'",
        )
        logger.debug(f"🔍 [GRAPH DEBUG] 初始状态中的trade_date: '{init_agent_state.get('trade_date', 'NOT_FOUND')}'")
        logger.debug(f"🔍 [GRAPH DEBUG] 初始状态中的stock_code: '{init_agent_state.get('stock_code', 'NOT_FOUND')}'")
        logger.debug(f"🔍 [GRAPH DEBUG] 初始状态中的market_type: '{init_agent_state.get('market_type', 'NOT_FOUND')}'")

        # ========== [PR#1-C1] 数据源预检查: 如果所有数据源均不可用，立即终止 ==========
        pre_check = self.propagator.pre_check_data_sources(self.ticker)
        if pre_check and not pre_check.get("available", True):
            logger.error(
                f"⏹️ [PR#1-C1] 数据源预检查失败: {self.ticker} 所有数据源均不可用，终止分析。"
                f"原因: {pre_check.get('reason', '未知')}"
            )
            init_agent_state["data_source_failure"] = True
            decision = {
                "decision": "分析终止",
                "confidence": 0.0,
                "reasoning": f"所有数据源均不可用，无法获取实时数据。{pre_check.get('reason', '')}",
                "data_source_failure": True,
            }
            return init_agent_state, decision

        # ========== 三轮改造: 注入 HPC-Loop 初始状态 ==========
        if self.hpc_loop and self.hpc_loop.enabled:
            try:
                hpc_initial = self.hpc_loop.get_initial_hpc_state()
                init_agent_state["hpc_state"] = hpc_initial.to_dict()
                logger.info("[HPC] initial HPC state injected")
            except Exception as e:
                logger.warning(f"[HPC] initialize HPC state failed: {e}")

        # ========== AIF: 注入 AIF 初始状态 ==========
        use_aif = self.aif_engine is not None and self.aif_engine.enabled
        if use_aif:
            try:
                aif_initial = self.aif_engine.get_initial_aif_state()
                init_agent_state["aif_state"] = aif_initial.to_dict()
                logger.info("[AIF] initial AIF state injected")
            except Exception as e:
                logger.warning(f"[AIF] initialize AIF state failed: {e}")

        # ========== AIF 推理迭代循环: 注入迭代状态 ==========
        if getattr(self, "use_fusion_mode", False) and use_aif:
            try:
                max_iter = int(os.environ.get("TRADINGAGENTS_AIF_MAX_ITERATIONS", "3"))
                init_agent_state["_aif_iteration_count"] = 0
                init_agent_state["_aif_max_iterations"] = max(1, max_iter)
                logger.info(f"[AIF Loop] 迭代循环已启用 (max_iterations={max(max_iter, 1)})")
            except Exception as e:
                logger.warning(f"[AIF Loop] 初始化迭代状态失败: {e}")
                init_agent_state["_aif_iteration_count"] = 0
                init_agent_state["_aif_max_iterations"] = 3

        # ========== Fusion: 注入融合模式标记到 state ==========
        if getattr(self, "use_fusion_mode", False):
            init_agent_state["fusion_mode"] = "unified"
            logger.info("[Fusion] unified mode flag injected into state")

        # ========== [C4] 注入 diffusion_weight 到 state ==========
        # fusion_node 从 state 中读取此值，不再使用硬编码 W_DIFF 全局变量
        init_agent_state["diffusion_weight"] = self.config.get("diffusion_weight", 0.4)

        # 初始化计时器
        node_timings = {}  # 记录每个节点的执行时间
        total_start_time = time.time()  # 总体开始时间
        current_node_start = None  # 当前节点开始时间
        current_node_name = None  # 当前节点名称

        # [Bug 1 修复] 记录总体开始时间，用于进度计算中的 elapsed_time
        self.start_time = total_start_time

        # 保存task_id用于后续保存性能数据
        self._current_task_id = task_id

        # 根据是否有进度回调选择不同的stream_mode
        # 🐛 [P0 Fix] 提取 graph 总体超时时间，从 deep_model_config.timeout 获取
        # 如果未配置则默认为 900s（15 分钟），防止 graph 因单个节点阻塞而无限挂起
        _deep_config = self.config.get("deep_model_config", {})
        _graph_timeout = _deep_config.get("timeout", 900)
        args = self.propagator.get_graph_args(
            use_progress_callback=bool(progress_callback),
            timeout=_graph_timeout,
        )

        # BUG-NEW-006 修复: 为所有三个分支添加指数退避重试机制
        # 当 LLM 调用因网络抖动/临时限流返回 5xx 时，自动重试
        # 重试策略: 1s → 3s → 6s，最多 3 次
        max_retries = 3
        retry_delays = [1, 3, 6]

        # RUNTIME-042 修复: 三合一 — 统一使用 _run_stream 消除三重代码副本
        def _run_stream(stream_callback, log_label: str):
            _trace: list[dict[str, Any]] = []
            _final_state: dict[str, Any] | None = None
            _last_exception: BaseException | None = None
            for attempt in range(max_retries):
                try:
                    for chunk in self.graph.stream(init_agent_state, **args):
                        result = stream_callback(chunk, _trace, _final_state)
                        if result is not None:
                            _final_state = result
                    break
                except InvalidUpdateError as _invalid_err:
                    logger.warning(
                        f"🔄 [方案C] 捕获 InvalidUpdateError (stream_mode=updates 通道冲突)，"
                        f"回退到 stream_mode=values: {_invalid_err}",
                    )
                    args["stream_mode"] = "values"
                    continue
                except Exception as e:
                    _last_exception = e
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.debug(
                            f"🔍 [R2 Fix L3] LangGraph stream {log_label} 原始异常详情 "
                            f"(尝试 {attempt + 1}/{max_retries})",
                            exc_info=True,
                        )
                        logger.warning(
                            f"🔄 [BUG-NEW-006] LangGraph stream {log_label} 执行异常 "
                            f"(尝试 {attempt + 1}/{max_retries}): {e}，{delay}s 后重试",
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"❌ [BUG-NEW-006] LangGraph stream {log_label} 执行异常 "
                            f"({max_retries}次重试均失败): {e}",
                            exc_info=True,
                        )
                        if _last_exception:
                            raise _last_exception
                        raise
            else:
                if _last_exception:
                    raise _last_exception
            return _trace, _final_state

        if self.debug:
            def _debug_cb(chunk, _trace, _final_state):
                nonlocal current_node_name, current_node_start
                cn, cs, fs = self._process_stream_chunk(
                    chunk, node_timings, current_node_name, current_node_start,
                    total_start_time, init_agent_state, _final_state, _trace, args,
                    progress_callback=progress_callback,
                    send_progress=bool(progress_callback and args.get("stream_mode") == "updates"),
                    append_trace=(not (progress_callback and args.get("stream_mode") == "updates")),
                )
                current_node_name, current_node_start = cn, cs
                return fs
            trace, final_state = _run_stream(_debug_cb, "(debug)")
            if not trace and final_state:
                pass
            elif trace:
                final_state = trace[-1]
        elif progress_callback:
            def _prog_cb(chunk, _trace, _final_state):
                nonlocal current_node_name, current_node_start
                cn, cs, fs = self._process_stream_chunk(
                    chunk, node_timings, current_node_name, current_node_start,
                    total_start_time, init_agent_state, _final_state, _trace, args,
                    progress_callback=progress_callback,
                    send_progress=True,
                    append_trace=False,
                )
                current_node_name, current_node_start = cn, cs
                return fs
            trace, final_state = _run_stream(_prog_cb, "")
        else:
            logger.info("⏱️ 使用 invoke 模式执行分析（无进度回调）")
            def _invoke_cb(chunk, _trace, _final_state):
                nonlocal current_node_name, current_node_start
                cn, cs, fs = self._process_stream_chunk(
                    chunk, node_timings, current_node_name, current_node_start,
                    total_start_time, init_agent_state, _final_state, _trace, args,
                    progress_callback=None,
                    send_progress=False,
                    append_trace=False,
                )
                current_node_name, current_node_start = cn, cs
                return fs
            trace, final_state = _run_stream(_invoke_cb, "invoke")

        # 记录最后一个节点的时间
        if current_node_name and current_node_start:
            elapsed = time.time() - current_node_start
            node_timings[current_node_name] = elapsed
            logger.info(f"⏱️ [{current_node_name}] 耗时: {elapsed:.2f}秒")

        # 计算总时间
        total_elapsed = time.time() - total_start_time

        # 调试日志
        logger.info(f"🔍 [TIMING DEBUG] 节点计时数量: {len(node_timings)}")
        logger.info(f"🔍 [TIMING DEBUG] 总耗时: {total_elapsed:.2f}秒")
        logger.info(f"🔍 [TIMING DEBUG] 节点列表: {list(node_timings.keys())}")

        # 打印详细的时间统计
        logger.info("🔍 [TIMING DEBUG] 准备调用 _print_timing_summary")
        self._print_timing_summary(node_timings, total_elapsed)
        logger.info("🔍 [TIMING DEBUG] _print_timing_summary 调用完成")

        # 构建性能数据
        performance_data = self._build_performance_data(node_timings, total_elapsed)

        # 将性能数据添加到状态中
        final_state["performance_metrics"] = performance_data

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # 获取模型信息
        model_info = ""
        try:
            if hasattr(self.deep_thinking_llm, "model_name"):
                model_info = f"{self.deep_thinking_llm.__class__.__name__}:{self.deep_thinking_llm.model_name}"
            else:
                model_info = self.deep_thinking_llm.__class__.__name__
        except Exception:
            model_info = "Unknown"

        # --- 累加 token 使用量（从各个 NormalizedChatOpenAI 实例读取） ---
        total_tokens = 0
        token_detail = {}
        for llm_ref, label in [
            (getattr(self, "deep_thinking_llm", None), "deep"),
            (getattr(self, "quick_thinking_llm", None), "quick"),
        ]:
            if llm_ref is not None:
                inp = getattr(llm_ref, "_total_input_tokens", 0) or 0
                out = getattr(llm_ref, "_total_output_tokens", 0) or 0
                subtotal = inp + out
                total_tokens += subtotal
                if subtotal > 0:
                    token_detail[label] = {"input_tokens": inp, "output_tokens": out, "total": subtotal}

        # 处理决策并添加模型信息
        decision = self.process_signal(final_state.get("final_trade_decision", ""), company_name, final_state)
        decision["model_info"] = model_info
        decision["tokens_used"] = total_tokens
        if token_detail:
            decision["token_detail"] = token_detail

        # 同时写入 final_state 供上游读取
        final_state["tokens_used"] = total_tokens
        final_state["token_detail"] = token_detail

        # Return decision and processed signal
        return final_state, decision

    def _send_progress_update(self, chunk, progress_callback):
        """发送进度更新到回调函数

        LangGraph stream 返回的 chunk 格式：{node_name: {...}}
        节点名称示例：
        - "Market Analyst", "Fundamentals Analyst", "News Analyst", "Social Analyst"
        - "tools_market", "tools_fundamentals", "tools_news", "tools_social"
        - "Msg Clear Market", "Msg Clear Fundamentals", etc.
        - "Bull Researcher", "Bear Researcher", "Research Manager"
        - "Trader"
        - "Risky Analyst", "Safe Analyst", "Neutral Analyst", "Risk Judge"

        ⚠️ [Bug 1 修复] 发送结构化进度字典而非纯文本字符串。
        进度字典格式：
        {
            "status": "running" | "completed",
            "message": "📊 市场分析师",
            "elapsed_time": 12.5,
            "remaining_time": 25.0,
            "estimated_total_time": 2400,
            "progress_percentage": 33.3,
        }
        """
        try:
            # 从chunk中提取当前执行的节点信息
            if not isinstance(chunk, dict):
                return

            # 获取第一个非特殊键作为节点名
            node_name = None
            for key in chunk:
                if not key.startswith("__"):
                    node_name = key
                    break

            if not node_name:
                return

            logger.info(f"🔍 [Progress] 节点名称: {node_name}")

            # 计算已用时间
            elapsed_time = time.time() - getattr(self, "start_time", time.time())

            # 获取估计总时长（从 config 中读取，默认 2400 秒 = 40 分钟）
            estimated_total_time = self.config.get("estimated_duration", 2400)

            # 计算进度百分比（限制在 0~95% 之间，剩余 5% 留给报告生成）
            progress_percentage = min(elapsed_time / estimated_total_time * 100, 95)

            # 计算剩余时间
            remaining_time = max(estimated_total_time - elapsed_time, 0)

            # 构建基础进度字典
            progress_data = {
                "status": "running",
                "elapsed_time": round(elapsed_time, 1),
                "remaining_time": round(remaining_time, 1),
                "estimated_total_time": estimated_total_time,
                "progress_percentage": round(progress_percentage, 1),
            }

            # 检查是否为结束节点
            if "__end__" in chunk:
                logger.info("📊 [Progress] 检测到__end__节点")
                # [Bug 1 修复] 发送结束进度字典，状态标记为 completed
                progress_data["status"] = "completed"
                progress_data["message"] = "📊 生成报告"
                progress_data["progress_percentage"] = 100.0
                progress_callback(progress_data)
                return

            # 节点名称映射表（匹配 LangGraph 实际节点名）
            node_mapping = {
                # 分析师节点
                "Market Analyst": "📊 市场分析师",
                "Fundamentals Analyst": "💼 基本面分析师",
                "News Analyst": "📰 新闻分析师",
                "Social Analyst": "💬 社交媒体分析师",
                # 工具节点（不发送进度更新，避免重复）
                "tools_market": None,
                "tools_fundamentals": None,
                "tools_news": None,
                "tools_social": None,
                # 消息清理节点（不发送进度更新）
                "Msg Clear Market": None,
                "Msg Clear Fundamentals": None,
                "Msg Clear News": None,
                "Msg Clear Social": None,
                # 研究员节点
                "Bull Researcher": "🐂 看涨研究员",
                "Bear Researcher": "🐻 看跌研究员",
                "Research Manager": "👔 研究经理",
                # 交易员节点
                "Trader": "💼 交易员决策",
                # 风险评估节点
                "Risky Analyst": "🔥 激进风险评估",
                "Safe Analyst": "🛡️ 保守风险评估",
                "Neutral Analyst": "⚖️ 中性风险评估",
                "Risk Judge": "🎯 风险经理",
            }

            # ========== Fusion / AIF / HPC 节点映射表 (P1 H12 修复) ==========
            # [FIX] 2026-06-18: Fix 2.7b - 补充缺失节点 HPC_MarketInfo、L-IWM 子节点
            fusion_mapping = {
                # HPC 节点
                "HPC_Predict": "🔮 HPC 预测",
                "HPC_MarketInfo": "📊 HPC 市场数据",  # L-IWM 真实数据管道
                "HPC_GWS_Broadcast": "🌐 HPC 全局工作空间广播",
                "HPC_PredictionError": "📉 HPC 预测误差",
                "HPC_ActiveInference": "🧠 HPC 主动推理",
                "HPC_CausalReasoning": "🔗 HPC 因果推理",
                "HPC_MemoryStore": "💾 HPC 记忆存储",
                "HPC_LIWMBridge": "🔌 L-IWM 桥接",
                # HSR-MC 节点
                "hsrc_observe": "👁️ HSR-MC 观察",
                "hsrc_adjust": "⚙️ HSR-MC 调整",
                "hsrc_reflect": "🪞 HSR-MC 反思",
                "hsrc_meta_update": "🔄 HSR-MC 元更新",
                # AIF 节点
                "AIF_Predict": "🔮 AIF 预测",
                "AIF_LLMPrior": "🧠 AIF LLM 先验",
                "AIF_Observe": "👁️ AIF 观测",
                "AIF_UpdateBelief": "🔄 AIF 信念更新",
                "AIF_SelectAction": "🎯 AIF 行动选择",
                "AIF_SelectAction_Evaluate": "🎯 AIF 行动评估",
                "AIF_Learn": "📚 AIF 学习",
                "AIF_MetaCycle": "🔄 AIF 元循环",
                # 扩散/融合节点
                "DiffusionAdvisor": "⚡ 扩散顾问",
                "FusionNode": "🔀 融合节点",
            }

            # 先查标准映射，再查 fusion 映射
            message = node_mapping.get(node_name) or fusion_mapping.get(node_name)

            if message is None:
                # None 表示跳过（工具节点、消息清理节点）
                logger.debug(f"⏭️ [Progress] 跳过节点: {node_name}")
                return

            if message:
                # [Bug 1 修复] 发送结构化进度字典，包含状态和时间信息
                progress_data["message"] = message
                logger.info(f"📤 [Progress] 发送进度更新: {message}")
                progress_callback(progress_data)
            else:
                # 未知节点，使用节点名称（不影响进度跟踪）
                # [FIX] 2026-06-18: Fix 2.7b - 给出更清晰的未知节点日志，帮助后续补充映射
                logger.warning(
                    f"⚠️ [Progress] 未注册节点: '{node_name}' — 请开发者在 "
                    f"trading_graph.py node_mapping/fusion_mapping 中添加映射条目",
                )
                progress_data["message"] = f"🔍 {node_name}"
                progress_callback(progress_data)

        except Exception as e:
            logger.error(f"❌ 进度更新失败: {e}", exc_info=True)

    def _build_performance_data(self, node_timings: dict[str, float], total_elapsed: float) -> dict[str, Any]:
        """构建性能数据结构

        Args:
            node_timings: 每个节点的执行时间字典
            total_elapsed: 总执行时间

        Returns:
            性能数据字典
        """
        # 节点分类（注意：风险管理节点要先于分析师节点判断，因为它们也包含'Analyst'）
        analyst_nodes = {}
        tool_nodes = {}
        msg_clear_nodes = {}
        research_nodes = {}
        trader_nodes = {}
        risk_nodes = {}
        other_nodes = {}

        for node_name, elapsed in node_timings.items():
            # 优先匹配风险管理团队（因为它们也包含'Analyst'）
            if "Risky" in node_name or "Safe" in node_name or "Neutral" in node_name or "Risk Judge" in node_name:
                risk_nodes[node_name] = elapsed
            # 然后匹配分析师团队
            elif "Analyst" in node_name:
                analyst_nodes[node_name] = elapsed
            # 工具节点
            elif node_name.startswith("tools_"):
                tool_nodes[node_name] = elapsed
            # 消息清理节点
            elif node_name.startswith("Msg Clear"):
                msg_clear_nodes[node_name] = elapsed
            # 研究团队
            elif "Researcher" in node_name or "Research Manager" in node_name:
                research_nodes[node_name] = elapsed
            # 交易团队
            elif "Trader" in node_name:
                trader_nodes[node_name] = elapsed
            # 其他节点
            else:
                other_nodes[node_name] = elapsed

        # 计算统计数据
        slowest_node = max(node_timings.items(), key=lambda x: x[1]) if node_timings else (None, 0)
        fastest_node = min(node_timings.items(), key=lambda x: x[1]) if node_timings else (None, 0)
        avg_time = sum(node_timings.values()) / len(node_timings) if node_timings else 0

        return {
            "total_time": round(total_elapsed, 2),
            "total_time_minutes": round(total_elapsed / 60, 2),
            "node_count": len(node_timings),
            "average_node_time": round(avg_time, 2),
            "slowest_node": {"name": slowest_node[0], "time": round(slowest_node[1], 2)} if slowest_node[0] else None,
            "fastest_node": {"name": fastest_node[0], "time": round(fastest_node[1], 2)} if fastest_node[0] else None,
            "node_timings": {k: round(v, 2) for k, v in node_timings.items()},
            "category_timings": {
                "analyst_team": {
                    "nodes": {k: round(v, 2) for k, v in analyst_nodes.items()},
                    "total": round(sum(analyst_nodes.values()), 2),
                    "percentage": round(sum(analyst_nodes.values()) / total_elapsed * 100, 1)
                    if total_elapsed > 0
                    else 0,
                },
                "tool_calls": {
                    "nodes": {k: round(v, 2) for k, v in tool_nodes.items()},
                    "total": round(sum(tool_nodes.values()), 2),
                    "percentage": round(sum(tool_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0,
                },
                "message_clearing": {
                    "nodes": {k: round(v, 2) for k, v in msg_clear_nodes.items()},
                    "total": round(sum(msg_clear_nodes.values()), 2),
                    "percentage": round(sum(msg_clear_nodes.values()) / total_elapsed * 100, 1)
                    if total_elapsed > 0
                    else 0,
                },
                "research_team": {
                    "nodes": {k: round(v, 2) for k, v in research_nodes.items()},
                    "total": round(sum(research_nodes.values()), 2),
                    "percentage": round(sum(research_nodes.values()) / total_elapsed * 100, 1)
                    if total_elapsed > 0
                    else 0,
                },
                "trader_team": {
                    "nodes": {k: round(v, 2) for k, v in trader_nodes.items()},
                    "total": round(sum(trader_nodes.values()), 2),
                    "percentage": round(sum(trader_nodes.values()) / total_elapsed * 100, 1)
                    if total_elapsed > 0
                    else 0,
                },
                "risk_management_team": {
                    "nodes": {k: round(v, 2) for k, v in risk_nodes.items()},
                    "total": round(sum(risk_nodes.values()), 2),
                    "percentage": round(sum(risk_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0,
                },
                "other": {
                    "nodes": {k: round(v, 2) for k, v in other_nodes.items()},
                    "total": round(sum(other_nodes.values()), 2),
                    "percentage": round(sum(other_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0,
                },
            },
            "llm_config": {
                "provider": self.config.get("llm_provider", "unknown"),
                "deep_think_model": self.config.get("deep_think_llm", "unknown"),
                "quick_think_model": self.config.get("quick_think_llm", "unknown"),
            },
        }

    def _print_timing_summary(self, node_timings: dict[str, float], total_elapsed: float):
        """打印详细的时间统计报告

        Args:
            node_timings: 每个节点的执行时间字典
            total_elapsed: 总执行时间
        """
        logger.info("🔍 [_print_timing_summary] 方法被调用")
        logger.info("🔍 [_print_timing_summary] node_timings 数量: " + str(len(node_timings)))
        logger.info("🔍 [_print_timing_summary] total_elapsed: " + str(total_elapsed))

        logger.info("=" * 80)
        logger.info("⏱️  分析性能统计报告")
        logger.info("=" * 80)

        # 节点分类（注意：风险管理节点要先于分析师节点判断，因为它们也包含'Analyst'）
        analyst_nodes = []
        tool_nodes = []
        msg_clear_nodes = []
        research_nodes = []
        trader_nodes = []
        risk_nodes = []
        other_nodes = []

        for node_name, elapsed in node_timings.items():
            # 优先匹配风险管理团队（因为它们也包含'Analyst'）
            if "Risky" in node_name or "Safe" in node_name or "Neutral" in node_name or "Risk Judge" in node_name:
                risk_nodes.append((node_name, elapsed))
            # 然后匹配分析师团队
            elif "Analyst" in node_name:
                analyst_nodes.append((node_name, elapsed))
            # 工具节点
            elif node_name.startswith("tools_"):
                tool_nodes.append((node_name, elapsed))
            # 消息清理节点
            elif node_name.startswith("Msg Clear"):
                msg_clear_nodes.append((node_name, elapsed))
            # 研究团队
            elif "Researcher" in node_name or "Research Manager" in node_name:
                research_nodes.append((node_name, elapsed))
            # 交易团队
            elif "Trader" in node_name:
                trader_nodes.append((node_name, elapsed))
            # 其他节点
            else:
                other_nodes.append((node_name, elapsed))

        # 打印分类统计
        def print_category(title: str, nodes: list[tuple[str, float]]):
            if not nodes:
                return
            logger.info(f"\n📊 {title}")
            logger.info("-" * 80)
            total_category_time = sum(t for _, t in nodes)
            for node_name, elapsed in sorted(nodes, key=lambda x: x[1], reverse=True):
                percentage = (elapsed / total_elapsed * 100) if total_elapsed > 0 else 0
                logger.info(f"  • {node_name:40s} {elapsed:8.2f}秒  ({percentage:5.1f}%)")
            logger.info(
                f"  {'小计':40s} {total_category_time:8.2f}秒  ({total_category_time / total_elapsed * 100:5.1f}%)",
            )

        print_category("分析师团队", analyst_nodes)
        print_category("工具调用", tool_nodes)
        print_category("消息清理", msg_clear_nodes)
        print_category("研究团队", research_nodes)
        print_category("交易团队", trader_nodes)
        print_category("风险管理团队", risk_nodes)
        print_category("其他节点", other_nodes)

        # 打印总体统计
        logger.info("\n" + "=" * 80)
        logger.info(f"🎯 总执行时间: {total_elapsed:.2f}秒 ({total_elapsed / 60:.2f}分钟)")
        logger.info(f"📈 节点总数: {len(node_timings)}")
        if node_timings:
            avg_time = sum(node_timings.values()) / len(node_timings)
            logger.info(f"⏱️  平均节点耗时: {avg_time:.2f}秒")
            slowest_node = max(node_timings.items(), key=lambda x: x[1])
            logger.info(f"🐌 最慢节点: {slowest_node[0]} ({slowest_node[1]:.2f}秒)")
            fastest_node = min(node_timings.items(), key=lambda x: x[1])
            logger.info(f"⚡ 最快节点: {fastest_node[0]} ({fastest_node[1]:.2f}秒)")

        # 打印LLM配置信息
        logger.info("\n🤖 LLM配置:")
        logger.info(f"  • 提供商: {self.config.get('llm_provider', 'unknown')}")
        logger.info(f"  • 深度思考模型: {self.config.get('deep_think_llm', 'unknown')}")
        logger.info(f"  • 快速思考模型: {self.config.get('quick_think_llm', 'unknown')}")
        logger.info("=" * 80)

    def _safe_serialize(self, value: Any) -> Any:
        """[Bug 5 修复] 递归安全序列化：将不可 JSON 序列化的对象转换为字符串"""
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [self._safe_serialize(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self._safe_serialize(v) for k, v in value.items()}
        # numpy / jax / 自定义对象 → 字符串
        try:
            return str(value)
        except Exception:
            return ""

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        # 判断当前是否使用 AIF 引擎
        _use_aif = self.aif_engine is not None and self.aif_engine.enabled

        # 安全获取投资辩论状态
        debate_state = final_state.get("investment_debate_state", {}) or {}
        log_entry = {
            "company_of_interest": str(final_state.get("company_of_interest", "")),
            "trade_date": final_state.get("trade_date", str(trade_date)),
            "market_report": self._safe_serialize(final_state.get("market_report", "")),
            "sentiment_report": self._safe_serialize(final_state.get("sentiment_report", "")),
            "news_report": self._safe_serialize(final_state.get("news_report", "")),
            "fundamentals_report": self._safe_serialize(final_state.get("fundamentals_report", "")),
            "investment_debate_state": {
                "bull_history": str(debate_state.get("bull_history", "")),
                "bear_history": str(debate_state.get("bear_history", "")),
                "history": str(debate_state.get("history", "")),
                "current_response": str(debate_state.get("current_response", "")),
                "judge_decision": str(debate_state.get("judge_decision", "")),
            },
            "trader_investment_decision": str(final_state.get("trader_investment_plan", "")),
            "risk_debate_state": {},
            "investment_plan": str(final_state.get("investment_plan", "")),
            "final_trade_decision": str(final_state.get("final_trade_decision", "")),
        }

        # 安全获取风险讨论状态
        risk_state = final_state.get("risk_debate_state", {}) or {}
        log_entry["risk_debate_state"] = {
            "risky_history": str(risk_state.get("risky_history", "")),
            "safe_history": str(risk_state.get("safe_history", "")),
            "neutral_history": str(risk_state.get("neutral_history", "")),
            "history": str(risk_state.get("history", "")),
            "judge_decision": str(risk_state.get("judge_decision", "")),
        }

        # ========== 三轮改造: HPC-Loop 状态日志 ==========
        if self.hpc_loop and self.hpc_loop.enabled and final_state.get("hpc_state"):
            try:
                hs = final_state["hpc_state"]
                # 兼容 HPCState 对象和 dict 两种形式
                if hasattr(hs, "to_dict"):
                    hs_dict = hs.to_dict()
                elif isinstance(hs, dict):
                    hs_dict = hs
                else:
                    hs_dict = {}
                log_entry["hpc_state"] = {
                    "market_regime": self._safe_serialize(hs_dict.get("latent_state", {}).get("market_regime_probs")),
                    "total_uncertainty": self._safe_serialize(hs_dict.get("latent_state", {}).get("total_uncertainty")),
                    "selected_action": str(hs_dict.get("selected_action", "")),
                    "prediction_error": self._safe_serialize(
                        (hs_dict.get("last_prediction_error") or {}).get("total_error"),
                    ),
                    "step_counter": hs_dict.get("step_counter"),
                }
            except Exception as e:
                logger.warning(f"记录 HPC-Loop 状态日志时出错: {e}", exc_info=True)

        # ========== AIF: AIF 引擎状态日志 ==========
        if _use_aif and final_state.get("aif_state"):
            try:
                aif_s = final_state["aif_state"]
                if hasattr(aif_s, "to_dict"):
                    aif_dict = aif_s.to_dict()
                elif isinstance(aif_s, dict):
                    aif_dict = aif_s
                else:
                    aif_dict = {}
                # 构建 AIF 状态，AIF 引擎未执行时从 HPC meta_data 兜底
                _aif_fields = {
                    "market_regime_probs": self._safe_serialize(
                        aif_dict.get("latent_state", {}).get("market_regime_probs"),
                    ),
                    "total_uncertainty": self._safe_serialize(
                        aif_dict.get("latent_state", {}).get("total_uncertainty"),
                    ),
                    "selected_action": str(aif_dict.get("selected_action", "")),
                    "efe_values": self._safe_serialize(aif_dict.get("efe_values")),
                    "selected_action_efe": self._safe_serialize(aif_dict.get("selected_action_efe")),
                    "learning_step": aif_dict.get("step_counter", aif_dict.get("learning_step")),
                }
                # 如果 AIF 全部为空，尝试从 HPC meta_data 恢复
                if not any(v for v in _aif_fields.values() if v):
                    _hpc = final_state.get("hpc_state", {}) or {}
                    if isinstance(_hpc, dict):
                        _meta = _hpc.get("meta_data", {}) or {}
                        _aif_fields["efe_values"] = self._safe_serialize(
                            str(_meta.get("aif_meta_free_energy", ""))
                        )
                        _aif_fields["learning_step"] = _meta.get("aif_meta_cycle_count")
                        _aif_fields["market_regime_probs"] = self._safe_serialize(
                            str(_meta.get("aif_meta_diagnostics", ""))
                        )
                log_entry["aif_state"] = _aif_fields
            except Exception as e:
                logger.warning(f"记录 AIF 引擎状态日志时出错: {e}", exc_info=True)

        self.log_states_dict[str(trade_date)] = log_entry

        # 保存到文件（添加错误处理防止局部故障影响整体流程）
        try:
            directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
            directory.mkdir(parents=True, exist_ok=True)

            with open(
                f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log.json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(self.log_states_dict, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存状态日志文件失败: {e}", exc_info=True)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(self.curr_state, returns_losses, self.bull_memory)
        self.reflector.reflect_bear_researcher(self.curr_state, returns_losses, self.bear_memory)
        self.reflector.reflect_trader(self.curr_state, returns_losses, self.trader_memory)
        self.reflector.reflect_invest_judge(self.curr_state, returns_losses, self.invest_judge_memory)
        self.reflector.reflect_risk_manager(self.curr_state, returns_losses, self.risk_manager_memory)

    def process_signal(self, full_signal, stock_symbol=None, state=None) -> dict[str, Any]:
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal, stock_symbol, state)
