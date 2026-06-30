#!/usr/bin/env python3
"""
财务数据API路由
提供财务数据查询和同步管理接口
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.response import ok
from app.services.financial_data_service import get_financial_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financial-data", tags=["财务数据"])


# ==================== 请求模型 ====================


class FinancialSyncRequest(BaseModel):
    """财务数据同步请求"""

    symbols: list[str] | None = Field(None, description="股票代码列表，为空则同步所有股票")
    data_sources: list[str] | None = Field(["tushare"], description="数据源列表")
    report_types: list[str] | None = Field(["quarterly"], description="报告类型列表 (quarterly/annual)")
    batch_size: int = Field(50, description="批处理大小", ge=1, le=200)
    delay_seconds: float = Field(1.0, description="API调用延迟秒数", ge=0.1, le=10.0)


class SingleStockSyncRequest(BaseModel):
    """单股票财务数据同步请求"""

    symbol: str = Field(..., description="股票代码")
    data_sources: list[str] | None = Field(["tushare"], description="数据源列表")


# ==================== 超时常量 ====================
SINGLE_SYNC_TIMEOUT = 30  # 单股票同步超时（秒）
BATCH_SYNC_TIMEOUT = 120  # 批量同步超时（秒）


# ==================== API端点 ====================


@router.get("/query/{symbol}", summary="查询股票财务数据")
async def query_financial_data(
    symbol: str,
    report_period: str | None = Query(None, description="报告期筛选 (YYYYMMDD)"),
    data_source: str | None = Query(None, description="数据源筛选"),
    report_type: str | None = Query(None, description="报告类型筛选"),
    limit: int | None = Query(10, description="限制返回数量", ge=1, le=100),
) -> dict:
    """
    查询股票财务数据

    - **symbol**: 股票代码 (必填)
    - **report_period**: 报告期筛选，格式YYYYMMDD
    - **data_source**: 数据源筛选 (tushare)
    - **report_type**: 报告类型筛选 (quarterly/annual)
    - **limit**: 限制返回数量，默认10条
    """
    try:
        service = await get_financial_data_service()

        results = await service.get_financial_data(
            symbol=symbol, report_period=report_period, data_source=data_source, report_type=report_type, limit=limit,
        )

        return ok(
            data={"symbol": symbol, "count": len(results), "financial_data": results},
            message=f"查询到 {len(results)} 条财务数据",
        )

    except Exception as e:
        logger.error(f"❌ 查询财务数据失败 {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"查询财务数据失败: {e!s}")


@router.get("/latest/{symbol}", summary="获取最新财务数据")
async def get_latest_financial_data(
    symbol: str, data_source: str | None = Query(None, description="数据源筛选"),
) -> dict:
    """
    获取股票最新财务数据

    - **symbol**: 股票代码 (必填)
    - **data_source**: 数据源筛选 (tushare)
    """
    try:
        service = await get_financial_data_service()

        result = await service.get_latest_financial_data(symbol=symbol, data_source=data_source)

        if result:
            return ok(data=result, message="获取最新财务数据成功")
        return {"success": False, "data": None, "message": "未找到财务数据"}

    except Exception as e:
        logger.error(f"❌ 获取最新财务数据失败 {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"获取最新财务数据失败: {e!s}")


@router.get("/statistics", summary="获取财务数据统计")
async def get_financial_statistics() -> dict:
    """
    获取财务数据统计信息

    返回各数据源的财务数据统计，包括：
    - 总记录数
    - 总股票数
    - 按数据源和报告类型分组的统计
    """
    try:
        service = await get_financial_data_service()

        stats = await service.get_financial_statistics()

        return ok(data=stats, message="获取财务数据统计成功")

    except Exception as e:
        logger.error(f"❌ 获取财务数据统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取财务数据统计失败: {e!s}")


@router.post("/sync/start", summary="启动财务数据同步")
async def start_financial_sync(request: FinancialSyncRequest, background_tasks: BackgroundTasks) -> dict:
    """
    启动财务数据同步任务

    支持配置：
    - 股票代码列表（为空则同步所有股票）
    - 数据源选择
    - 报告类型选择
    - 批处理大小和延迟设置
    """
    raise HTTPException(status_code=410, detail="财务数据同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/sync/single", summary="同步单只股票财务数据")
async def sync_single_stock_financial(request: SingleStockSyncRequest) -> dict:
    """
    同步单只股票的财务数据（带超时保护）

    - **symbol**: 股票代码 (必填)
    - **data_sources**: 数据源列表，默认使用所有数据源
    """
    raise HTTPException(status_code=410, detail="财务数据同步功能已移除（仅保留 Tushare 数据源）")


@router.get("/sync/statistics", summary="获取同步统计信息")
async def get_sync_statistics() -> dict:
    """
    获取财务数据同步统计信息

    返回各数据源的同步统计，包括记录数、股票数等
    """
    raise HTTPException(status_code=410, detail="财务数据同步功能已移除（仅保留 Tushare 数据源）")


@router.get("/health", summary="财务数据服务健康检查")
async def health_check() -> dict:
    """
    财务数据服务健康检查

    检查服务状态和数据库连接
    """
    try:
        # 检查服务初始化状态
        service = await get_financial_data_service()

        # 简单的数据库连接测试
        stats = await service.get_financial_statistics()

        return ok(
            data={
                "service_status": "healthy",
                "database_connected": True,
                "total_records": stats.get("total_records", 0),
                "total_symbols": stats.get("total_symbols", 0),
            },
            message="财务数据服务运行正常",
        )

    except Exception as e:
        logger.error(f"❌ 财务数据服务健康检查失败: {e}")
        return ok(success=False, data={"service_status": "unhealthy", "error": str(e)}, message="财务数据服务异常")


# 导入datetime用于时间戳
