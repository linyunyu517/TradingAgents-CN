#!/usr/bin/env python3
"""
多周期数据同步API
提供日线、周线、月线数据的同步管理接口
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-period-sync", tags=["多周期同步"])


class MultiPeriodSyncRequest(BaseModel):
    """多周期同步请求"""

    symbols: list[str] | None = Field(None, description="股票代码列表，None表示所有股票")
    periods: list[str] | None = Field(["daily"], description="周期列表 (daily/weekly/monthly)")
    data_sources: list[str] | None = Field(["tushare"], description="数据源列表")
    start_date: str | None = Field(None, description="开始日期 (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="结束日期 (YYYY-MM-DD)")
    all_history: bool | None = Field(False, description="是否同步所有历史数据（忽略时间范围）")


class MultiPeriodSyncResponse(BaseModel):
    """多周期同步响应"""

    success: bool
    message: str
    data: dict[str, Any] | None = None


@router.post("/start", response_model=MultiPeriodSyncResponse)
async def start_multi_period_sync(request: MultiPeriodSyncRequest, background_tasks: BackgroundTasks):
    """
    启动多周期数据同步
    """
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/start-daily", response_model=MultiPeriodSyncResponse)
async def start_daily_sync(
    background_tasks: BackgroundTasks, symbols: list[str] | None = None, data_sources: list[str] | None = None,
):
    """启动日线数据同步"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/start-weekly", response_model=MultiPeriodSyncResponse)
async def start_weekly_sync(
    background_tasks: BackgroundTasks, symbols: list[str] | None = None, data_sources: list[str] | None = None,
):
    """启动周线数据同步"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/start-monthly", response_model=MultiPeriodSyncResponse)
async def start_monthly_sync(
    background_tasks: BackgroundTasks, symbols: list[str] | None = None, data_sources: list[str] | None = None,
):
    """启动月线数据同步"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/start-all-history", response_model=MultiPeriodSyncResponse)
async def start_all_history_sync(
    background_tasks: BackgroundTasks,
    symbols: list[str] | None = None,
    periods: list[str] | None = None,
    data_sources: list[str] | None = None,
):
    """启动全历史数据同步（从1990年开始）"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.post("/start-incremental", response_model=MultiPeriodSyncResponse)
async def start_incremental_sync(
    background_tasks: BackgroundTasks,
    symbols: list[str] | None = None,
    periods: list[str] | None = None,
    data_sources: list[str] | None = None,
    days_back: int | None = 30,
):
    """启动增量数据同步（最近N天）"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.get("/statistics")
async def get_sync_statistics():
    """获取多周期同步统计信息"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")


@router.get("/period-comparison/{symbol}")
async def compare_period_data(symbol: str, trade_date: str, data_source: str = "tushare"):
    """
    对比同一股票不同周期的数据
    """
    try:
        from app.services.historical_data_service import get_historical_data_service

        service = await get_historical_data_service()

        periods = ["daily", "weekly", "monthly"]
        comparison = {}

        for period in periods:
            results = await service.get_historical_data(
                symbol=symbol,
                start_date=trade_date,
                end_date=trade_date,
                data_source=data_source,
                period=period,
                limit=1,
            )

            if results:
                comparison[period] = results[0]
            else:
                comparison[period] = None

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "trade_date": trade_date,
                "data_source": data_source,
                "comparison": comparison,
                "available_periods": [k for k, v in comparison.items() if v is not None],
            },
            "message": "周期数据对比完成",
        }

    except Exception as e:
        logger.error(f"周期数据对比失败 {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"周期数据对比失败: {e}")


@router.get("/supported-periods")
async def get_supported_periods():
    """获取支持的数据周期"""
    return {
        "success": True,
        "data": {
            "periods": [
                {
                    "code": "daily",
                    "name": "日线",
                    "description": "每日交易数据",
                    "supported_sources": ["tushare"],
                },
                {
                    "code": "weekly",
                    "name": "周线",
                    "description": "每周交易数据",
                    "supported_sources": ["tushare"],
                },
                {
                    "code": "monthly",
                    "name": "月线",
                    "description": "每月交易数据",
                    "supported_sources": ["tushare"],
                },
            ],
            "data_sources": [
                {
                    "code": "tushare",
                    "name": "Tushare",
                    "description": "专业金融数据服务",
                    "supported_periods": ["daily", "weekly", "monthly"],
                },
            ],
        },
        "message": "支持的周期信息获取成功",
    }


@router.get("/health")
async def health_check():
    """健康检查"""
    raise HTTPException(status_code=410, detail="多周期同步功能已移除（仅保留 Tushare 数据源）")
