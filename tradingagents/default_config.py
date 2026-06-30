import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var to config-key overrides. To expose
# a new config key for environment-based override, add a row here -- no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM": "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM": "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL": "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER": "benchmark_ticker",
    # CN-specific overrides
    "TRADINGAGENTS_RESULTS_DIR": "results_dir",
    "TRADINGAGENTS_DATA_DIR": "data_dir",
    "TRADINGAGENTS_CACHE_DIR": "cache_dir",
    "TRADINGAGENTS_LOG_LEVEL": "log_level",
    "TRADINGAGENTS_LOG_DIR": "log_dir",
    "TRADINGAGENTS_MONGODB_URI": "mongodb_uri",
    "TRADINGAGENTS_DATABASE_NAME": "database_name",
    "TRADINGAGENTS_MONGODB_ENABLED": "mongodb_enabled",
    "TRADINGAGENTS_MAX_TOOL_ARGS_LENGTH": "max_tool_args_length",
    "TRADINGAGENTS_MAX_CONTENT_LENGTH": "max_content_length",
    "TRADINGAGENTS_MAX_DISPLAY_MESSAGES": "max_display_messages",
    "TRADINGAGENTS_REFRESH_RATE": "refresh_rate_per_second",
    "TRADINGAGENTS_MEMORY_LOG_PATH": "memory_log_path",
    "TRADINGAGENTS_MEMORY_LOG_MAX_ENTRIES": "memory_log_max_entries",
    "TRADINGAGENTS_DEEPSEEK_ENABLED": "deepseek_enabled",
    "TRADINGAGENTS_DEEPSEEK_MODEL": "deepseek_model",
    "TRADINGAGENTS_DEEPSEEK_THINKING_MODE": "deepseek_thinking_mode",
    "TRADINGAGENTS_DEEPSEEK_THINKING_EFFORT": "deepseek_thinking_effort",
    "TRADINGAGENTS_DEEPSEEK_ADAPTER_TYPE": "deepseek_adapter_type",
    "TRADINGAGENTS_DASHSCOPE_ENABLED": "dashscope_enabled",
    "TRADINGAGENTS_DASHSCOPE_MODEL": "dashscope_model",
    # === 三轮改造 (HPC-Loop / L-IWM / HSR-MC) 环境变量覆盖 ===
    "TRADINGAGENTS_HPC_LOOP_ENABLED": "hpc_loop_enabled",
    "TRADINGAGENTS_HPC_PARALLEL_ANALYSTS": "hpc_parallel_analysts",
    "TRADINGAGENTS_HPC_GWS_ENABLED": "hpc_gws_enabled",
    "TRADINGAGENTS_HPC_MEMORY_WINDOW_SIZE": "hpc_memory_window_size",
    "TRADINGAGENTS_HPC_CAUSAL_MAX_HYPOTHESES": "hpc_causal_max_hypotheses",
    "TRADINGAGENTS_HPC_PREDICTION_ERROR_THRESHOLD": "hpc_prediction_error_threshold",
    "TRADINGAGENTS_HPC_PREDICTION_ERROR_RATE": "hpc_prediction_error_rate",
    "TRADINGAGENTS_L_IWM_ENABLED": "l_iwm_enabled",
    "TRADINGAGENTS_HSRC_MC_ENABLED": "hsrc_mc_enabled",
    # ========== AIF (Active Inference Framework) 环境变量覆盖 ==========
    "TRADINGAGENTS_USE_AIF_ENGINE": "use_aif_engine",
    "TRADINGAGENTS_AIF_LATENT_DIM": "aif_latent_dim",
    "TRADINGAGENTS_AIF_N_SAMPLES": "aif_n_samples",
    "TRADINGAGENTS_AIF_LEARNING_RATE": "aif_learning_rate",
    "TRADINGAGENTS_AIF_EFE_TEMPERATURE": "aif_efe_temperature",
    # ========== 分层生成模型 + 元学习器 环境变量覆盖 ==========
    "TRADINGAGENTS_USE_HIERARCHICAL_MODEL": "use_hierarchical_model",
    "TRADINGAGENTS_META_CYCLE_INTERVAL": "meta_cycle_interval",
    "TRADINGAGENTS_META_WINDOW_SIZE": "meta_window_size",
    "TRADINGAGENTS_META_LEARNING_RATE": "meta_learning_rate",
    "TRADINGAGENTS_META_CUSUM_THRESHOLD": "meta_cusum_threshold",
    "TRADINGAGENTS_ONLINE_TOOLS": "online_tools",
    "TRADINGAGENTS_SAMPLING_TEMPERATURE": "sampling_temperature",
    # API keys (loaded from env, not stored in config dict as plain values)
    "DASHSCOPE_API_KEY": "dashscope_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "FINNHUB_API_KEY": "finnhub_api_key",
    # ========== 扩散模块 (Diffusion) 环境变量覆盖 ==========
    "TRADINGAGENTS_DIFFUSION_ENABLED": "diffusion_enabled",
    "TRADINGAGENTS_DIFFUSION_WEIGHT": "diffusion_weight",
    "TRADINGAGENTS_DIFFUSION_NUM_TIMESTEPS": "diffusion_num_timesteps",
    "TRADINGAGENTS_DIFFUSION_CSDI_ENABLED": "diffusion_csdi_enabled",
    "TRADINGAGENTS_DIFFUSION_GENERATIVE_ENABLED": "diffusion_generative_enabled",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


# RUNTIME-012: 修正 project_dir 指向项目根目录而非 tradingagents/ 子目录
# __file__ = tradingagents/default_config.py → 父目录的父目录为项目根
_default_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG = _apply_env_overrides(
    {
        "project_dir": os.getenv("TRADINGAGENTS_PROJECT_DIR", _default_project_root),
        "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "data_dir": os.getenv(
            "TRADINGAGENTS_DATA_DIR", os.path.join(os.path.expanduser("~"), "Documents", "TradingAgents", "data"),
        ),
        "data_cache_dir": os.getenv(
            "TRADINGAGENTS_CACHE_DIR",
            os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
                "dataflows/data_cache",
            ),
        ),
        "cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
        "memory_log_path": os.getenv(
            "TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md"),
        ),
        # Optional cap on the number of resolved memory log entries. When set,
        # the oldest resolved entries are pruned once this limit is exceeded.
        # Pending entries are never pruned. None disables rotation entirely.
        "memory_log_max_entries": None,
        # LLM settings - v1.0.1 uses OpenAI by default
        "llm_provider": "openai",
        "deep_think_llm": "o4-mini",
        "quick_think_llm": "gpt-4o-mini",
        "deep_think_max_tokens": 8192,
        "quick_think_max_tokens": 4096,
        "backend_url": "https://api.openai.com/v1",
        # Provider-specific thinking configuration
        "google_thinking_level": None,  # "high", "minimal", etc.
        "openai_reasoning_effort": None,  # "medium", "high", "low"
        "anthropic_effort": None,  # "high", "medium", "low"
        # Sampling temperature
        "sampling_temperature": 0.1,
        # Checkpoint/resume: when True, LangGraph saves state after each node
        # so a crashed run can resume from the last successful step.
        "checkpoint_enabled": False,
        # Output language for analyst reports and final decision
        # Internal agent debate stays in English for reasoning quality
        "output_language": "Chinese",
        # Debate and discussion settings
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 2,
        "max_recur_limit": 100,
        # Tool settings - 从环境变量读取，提供默认值
        "online_tools": os.getenv("ONLINE_TOOLS_ENABLED", "false").lower() == "true",
        "online_news": os.getenv("ONLINE_NEWS_ENABLED", "true").lower() == "true",
        "realtime_data": os.getenv("REALTIME_DATA_ENABLED", "false").lower() == "true",
        # News / data fetching parameters
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "global_news_lookback_days": 7,
        "global_news_queries": [
            "Federal Reserve interest rates inflation",
            "S&P 500 earnings GDP economic outlook",
            "geopolitical risk trade war sanctions",
            "ECB Bank of England BOJ central bank policy",
            "oil commodities supply chain energy",
        ],
        # Data vendor configuration
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        },
        "tool_vendors": {},
        # Benchmark configuration
        "benchmark_ticker": None,
        "benchmark_map": {
            ".NS": "^NSEI",  # NSE India (Nifty 50)
            ".BO": "^BSESN",  # BSE India (Sensex)
            ".T": "^N225",  # Tokyo (Nikkei 225)
            ".HK": "^HSI",  # Hong Kong (Hang Seng)
            ".L": "^FTSE",  # London (FTSE 100)
            ".TO": "^GSPTSE",  # Toronto (TSX Composite)
            ".AX": "^AXJO",  # Australia (ASX 200)
            ".SS": "000300.SS",  # Shanghai (CSI 300)
            ".SZ": "399001.SZ",  # Shenzhen (SZSE Component)
            "": "SPY",  # default for US-listed tickers
        },
        # ========== CN-specific local configuration ==========
        # Logging
        "log_level": "INFO",
        "log_dir": "./logs",
        # MongoDB
        "mongodb_uri": "mongodb://localhost:27017",
        "database_name": "tradingagents",
        "mongodb_enabled": False,
        # UI display limits
        "max_tool_args_length": 1000,
        "max_content_length": 4000,
        "max_display_messages": 50,
        "refresh_rate_per_second": 5,
        # ========== DeepSeek support ==========
        "deepseek_enabled": True,
        "deepseek_model": "deepseek-v4-flash",
        "deepseek_thinking_mode": "enabled",
        "deepseek_thinking_effort": "max",
        "deepseek_adapter_type": "direct",
        # ========== DashScope / Ali BaiLian support (CN LLM provider) ==========
        "dashscope_enabled": True,
        "dashscope_model": "qwen-plus-latest",
        # ========== API keys (loaded from environment) ==========
        "deepseek_api_key": "",
        "dashscope_api_key": "",
        "openai_api_key": "",
        "google_api_key": "",
        "anthropic_api_key": "",
        "finnhub_api_key": "",
        # ========== Graph/Progress configuration ==========
        "default_estimated_duration": 2400,  # [Bug 4 修复] 默认预估分析时长(秒)，供进度条估算剩余时间
        # ========== HPC-Loop configuration ==========
        "hpc_loop_enabled": True,
        "hpc_config": {},
        "hpc_prediction_error_threshold": 1.5,
        "hpc_prediction_error_rate": 0.15,
        "hpc_gws_enabled": True,
        "hpc_memory_window_size": 150,
        "hpc_parallel_analysts": True,
        "hpc_causal_max_hypotheses": 30,
        # ========== L-IWM configuration ==========
        "l_iwm_enabled": True,
        "l_iwm_config": {},
        # L-IWM real data sources (China market data sources)
        "l_iwm_real_data_sources": ["tushare"],
        # ========== HSR-MC configuration ==========
        "hsrc_mc_enabled": True,
        "hsrc_mc_config": {},
        # ========== AIF (Active Inference Framework) configuration ==========
        "use_aif_engine": True,
        "aif_latent_dim": 120,
        "aif_n_samples": 200,
        "aif_learning_rate": 0.005,
        "aif_efe_temperature": 1.2,
        # ========== 融合架构 (Fusion) configuration ==========
        "fusion_mode": "unified",  # "unified" | "legacy" | "aif_only" | "hpc_only"
        # ========== 扩散模块 (Diffusion) configuration ==========
        "diffusion_enabled": True,
        "diffusion_weight": 0.4,  # 融合权重 w_diff
        "diffusion_num_timesteps": 20,  # [优化 2026-06-22] DDIM 采样步数 (原 100，配合渐进式采样降至 20)
        "diffusion_csdi_enabled": True,  # CSDI 数据补全默认关闭（性能考虑）
        "diffusion_generative_enabled": True,  # 扩散生成模型默认关闭（预留）
        # ========== 分层生成模型 + 元学习器 configuration ==========
        "use_hierarchical_model": True,
        "meta_cycle_interval": 30,
        "meta_window_size": 75,
        "meta_learning_rate": 0.003,
        "meta_cusum_threshold": 3.0,
    },
)
