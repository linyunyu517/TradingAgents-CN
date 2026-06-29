"""Analysis service subpackage.

This package contains utilities split out from the monolithic analysis_service.py
without changing the public API of AnalysisService.
"""

import logging

logger = logging.getLogger("app.services.analysis")


async def get_provider_by_model_name(model_name: str) -> str:
    """根据模型名称获取提供器名称（async 版本）

    使用 simple_analysis_service 中的同步规则函数完成模型→供应商映射，
    避免同步包装器中因 ImportError 导致的静默降级。
    """
    from app.services.simple_analysis_service import _get_default_provider_by_model

    provider = _get_default_provider_by_model(model_name)
    logger.debug(f"[analysis] 模型 {model_name} → 供应商 {provider}")
    return provider
