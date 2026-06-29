#!/usr/bin/env python
"""
LLM Provider 路由修复的捕获测试。

测试覆盖：
- Fix A: create_analysis_config() 返回的 config 包含 llm_provider 键
- 环境变量 TRADINGAGENTS_LLM_PROVIDER 生效时 config 中 llm_provider 正确
- 无环境变量时 fallback 值正确（非 "openai"）
"""

import os
from unittest.mock import MagicMock, patch


class TestFixA_LlmProviderInCreateAnalysisConfig:
    """验证 create_analysis_config() 返回的 config 包含 llm_provider 键"""

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_config_contains_llm_provider_key(self, mock_get_provider, mock_config_service):
        """create_analysis_config 返回的字典应包含 llm_provider 键"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config

        # Arrange: mock ConfigService 返回空配置
        mock_config_instance = MagicMock()
        mock_config_instance.get_config.return_value = {}
        mock_config_service.return_value = mock_config_instance

        # mock get_provider_by_model_name_sync 返回 deepseek
        mock_get_provider.return_value = "deepseek"

        # 构造最小 request
        request = SingleAnalysisRequest(stock_code="600519")

        # Act
        config = create_analysis_config(request, "user-1", "task-1")

        # Assert
        assert "llm_provider" in config, (
            f"create_analysis_config 应包含 'llm_provider' 键，实际键: {list(config.keys())}"
        )

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_llm_provider_env_var_takes_priority(self, mock_get_provider, mock_config_service):
        """环境变量 TRADINGAGENTS_LLM_PROVIDER 应覆盖默认值"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config

        # Arrange: 设置环境变量
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "deepseek"}, clear=False):
            mock_config_instance = MagicMock()
            mock_config_instance.get_config.return_value = {}
            mock_config_service.return_value = mock_config_instance
            mock_get_provider.return_value = "deepseek"

            request = SingleAnalysisRequest(stock_code="600519")

            # Act
            config = create_analysis_config(request, "user-1", "task-1")

            # Assert
            assert config.get("llm_provider") == "deepseek", (
                f"环境变量 TRADINGAGENTS_LLM_PROVIDER=deepseek 时，"
                f"config['llm_provider'] 应为 'deepseek'，实际为 '{config.get('llm_provider')}'"
            )

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_llm_provider_fallback_not_openai(self, mock_get_provider, mock_config_service):
        """无环境变量时 llm_provider 的 fallback 不应为 'openai'"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config

        # Arrange: 确保环境变量不存在
        with patch.dict(os.environ, {}, clear=True):
            # 重新导入模块以确保环境变量状态
            # 注意: patch.dict 会临时清空环境变量，包括可能的 TRADINGAGENTS_LLM_PROVIDER
            mock_config_instance = MagicMock()
            mock_config_instance.get_config.return_value = {}
            mock_config_service.return_value = mock_config_instance
            mock_get_provider.return_value = "deepseek"

            request = SingleAnalysisRequest(stock_code="600519")

            # Act
            config = create_analysis_config(request, "user-1", "task-1")

            # Assert: 不应为 "openai"
            assert config.get("llm_provider") != "openai", (
                f"无环境变量时 config['llm_provider'] 不应为 'openai'，实际为 '{config.get('llm_provider')}'"
            )
            # Assert: 应为 "deepseek"（fallback）
            assert config.get("llm_provider") == "deepseek", (
                f"无环境变量时 config['llm_provider'] 应为 'deepseek'，实际为 '{config.get('llm_provider')}'"
            )

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_llm_provider_config_override(self, mock_get_provider, mock_config_service):
        """ConfigService 返回的 config 中 llm_provider 应被识别"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config

        # Arrange: ConfigService 返回的配置包含 llm_provider
        with patch.dict(os.environ, {}, clear=True):
            mock_config_instance = MagicMock()
            mock_config_instance.get_config.return_value = {"llm_provider": "qwen"}
            mock_config_service.return_value = mock_config_instance
            mock_get_provider.return_value = "siliconflow"

            request = SingleAnalysisRequest(stock_code="600519")

            # Act
            config = create_analysis_config(request, "user-1", "task-1")

            # Assert: ConfigService 中的 llm_provider 被保留（因为无环境变量覆盖）
            # ConfigService 返回 "qwen"，所以 llm_provider 应为 "qwen"
            assert config.get("llm_provider") == "qwen", (
                f"ConfigService 返回 llm_provider=qwen 时，"
                f"config['llm_provider'] 应为 'qwen'，实际为 '{config.get('llm_provider')}'"
            )

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_env_var_overrides_config(self, mock_get_provider, mock_config_service):
        """环境变量应覆盖 ConfigService 返回的 llm_provider"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config

        # Arrange: 环境变量和 ConfigService 同时提供
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "deepseek"}, clear=False):
            mock_config_instance = MagicMock()
            mock_config_instance.get_config.return_value = {
                "llm_provider": "openai",  # ConfigService 说是 openai
            }
            mock_config_service.return_value = mock_config_instance
            mock_get_provider.return_value = "siliconflow"

            request = SingleAnalysisRequest(stock_code="600519")

            # Act
            config = create_analysis_config(request, "user-1", "task-1")

            # Assert: 环境变量优先
            assert config.get("llm_provider") == "deepseek", (
                f"环境变量 TRADINGAGENTS_LLM_PROVIDER=deepseek 应覆盖 "
                f"ConfigService 的 llm_provider=openai，"
                f"实际为 '{config.get('llm_provider')}'"
            )

    @patch("app.services.simple_analysis_service.ConfigService")
    @patch("app.services.simple_analysis_service.get_provider_by_model_name_sync")
    def test_llm_provider_in_merged_config(self, mock_get_provider, mock_config_service):
        """create_analysis_config 返回的 llm_provider 在 _get_trading_graph 合并后应保留"""
        from app.models.analysis import SingleAnalysisRequest
        from app.services.simple_analysis_service import create_analysis_config
        from tradingagents.default_config import DEFAULT_CONFIG

        # Arrange
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "deepseek"}, clear=False):
            mock_config_instance = MagicMock()
            mock_config_instance.get_config.return_value = {}
            mock_config_service.return_value = mock_config_instance
            mock_get_provider.return_value = "deepseek"

            request = SingleAnalysisRequest(stock_code="600519")

            # Act: 模拟 _get_trading_graph 的合并逻辑
            config = create_analysis_config(request, "user-1", "task-1")
            merged_config = {**DEFAULT_CONFIG, **config}

            # Assert: 合并后 llm_provider 应为 config 中的值
            # 注意: Fix B 在 .env 中添加了 TRADINGAGENTS_LLM_PROVIDER=deepseek，
            # 因此 DEFAULT_CONFIG 加载时也读取了该值。但核心验证点是：
            # config 中的 llm_provider 能正确传递到 merged_config
            assert merged_config["llm_provider"] == "deepseek", (
                f"合并后 merged_config['llm_provider'] 应为 'deepseek'，"
                f"实际为 '{merged_config.get('llm_provider')}'。"
                f"config 的键: {list(config.keys())}"
            )
            # 验证 config 确实包含了 llm_provider 键（Fix A 的成果）
            assert "llm_provider" in config, (
                f"create_analysis_config 应包含 'llm_provider' 键，实际键: {list(config.keys())}"
            )
