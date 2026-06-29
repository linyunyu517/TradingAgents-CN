"""
自选股管理API路由
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.favorites_service import favorites_service

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/favorites", tags=["自选股管理"])

# ==================== 超时常量 ====================
SYNC_REALTIME_TIMEOUT = 20  # 实时行情同步超时（秒）
MAX_SYNC_STOCKS = 50  # 单次同步最大股票数量


class AddFavoriteRequest(BaseModel):
    """添加自选股请求"""

    stock_code: str
    stock_name: str
    market: str = "A股"
    tags: list[str] = []
    notes: str = ""
    alert_price_high: float | None = None
    alert_price_low: float | None = None


class UpdateFavoriteRequest(BaseModel):
    """更新自选股请求"""

    tags: list[str] | None = None
    notes: str | None = None
    alert_price_high: float | None = None
    alert_price_low: float | None = None


class FavoriteStockResponse(BaseModel):
    """自选股响应"""

    stock_code: str
    stock_name: str
    market: str
    added_at: str
    tags: list[str]
    notes: str
    alert_price_high: float | None
    alert_price_low: float | None
    # 实时数据
    current_price: float | None = None
    change_percent: float | None = None
    volume: int | None = None


@router.get("/", response_model=dict)
async def get_favorites(current_user: dict = Depends(get_current_user)):
    """获取用户自选股列表"""
    try:
        favorites = await favorites_service.get_user_favorites(current_user["id"])
        return ok(favorites)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取自选股失败: {e!s}")


@router.post("/", response_model=dict)
async def add_favorite(request: AddFavoriteRequest, current_user: dict = Depends(get_current_user)):
    """添加股票到自选股"""
    import logging

    logger = logging.getLogger("webapi")

    try:
        logger.info(
            f"📝 添加自选股请求: user_id={current_user['id']}, stock_code={request.stock_code}, stock_name={request.stock_name}",
        )

        # 检查是否已存在
        is_fav = await favorites_service.is_favorite(current_user["id"], request.stock_code)
        logger.info(f"🔍 检查是否已存在: {is_fav}")

        if is_fav:
            logger.warning(f"⚠️ 股票已在自选股中: {request.stock_code}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该股票已在自选股中")

        # 添加到自选股
        logger.info("➕ 开始添加自选股...")
        success = await favorites_service.add_favorite(
            user_id=current_user["id"],
            stock_code=request.stock_code,
            stock_name=request.stock_name,
            market=request.market,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low,
        )

        logger.info(f"✅ 添加结果: success={success}")

        if success:
            return ok({"stock_code": request.stock_code}, "添加成功")
        logger.error("❌ 添加失败: success=False")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="添加失败")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 添加自选股异常: {type(e).__name__}: {e!s}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"添加自选股失败: {e!s}")


@router.put("/{stock_code}", response_model=dict)
async def update_favorite(
    stock_code: str, request: UpdateFavoriteRequest, current_user: dict = Depends(get_current_user),
):
    """更新自选股信息"""
    try:
        success = await favorites_service.update_favorite(
            user_id=current_user["id"],
            stock_code=stock_code,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low,
        )

        if success:
            return ok({"stock_code": stock_code}, "更新成功")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自选股不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新自选股失败: {e!s}")


@router.delete("/{stock_code}", response_model=dict)
async def remove_favorite(stock_code: str, current_user: dict = Depends(get_current_user)):
    """从自选股中移除股票"""
    try:
        success = await favorites_service.remove_favorite(current_user["id"], stock_code)

        if success:
            return ok({"stock_code": stock_code}, "移除成功")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自选股不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"移除自选股失败: {e!s}")


@router.get("/check/{stock_code}", response_model=dict)
async def check_favorite(stock_code: str, current_user: dict = Depends(get_current_user)):
    """检查股票是否在自选股中"""
    try:
        is_favorite = await favorites_service.is_favorite(current_user["id"], stock_code)
        return ok({"stock_code": stock_code, "is_favorite": is_favorite})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"检查自选股状态失败: {e!s}")


@router.get("/tags", response_model=dict)
async def get_user_tags(current_user: dict = Depends(get_current_user)):
    """获取用户使用的所有标签"""
    try:
        tags = await favorites_service.get_user_tags(current_user["id"])
        return ok(tags)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取标签失败: {e!s}")


class SyncFavoritesRequest(BaseModel):
    """同步自选股实时行情请求"""

    data_source: str = "tushare"  # tushare/akshare


@router.post("/sync-realtime", response_model=dict)
async def sync_favorites_realtime(request: SyncFavoritesRequest, current_user: dict = Depends(get_current_user)):
    """
    同步自选股实时行情（带超时保护）

    - **data_source**: 数据源（tushare/akshare）
    """
    # 预先声明变量，确保异常处理块中可访问
    symbol_count = 0

    try:
        logger.info(f"📊 开始同步自选股实时行情: user_id={current_user['id']}, data_source={request.data_source}")

        # 获取用户自选股列表
        favorites = await favorites_service.get_user_favorites(current_user["id"])

        if not favorites:
            logger.info("⚠️ 用户没有自选股")
            return ok({"total": 0, "success_count": 0, "failed_count": 0, "message": "没有自选股需要同步"})

        # 提取股票代码列表，限制最大数量以防超时
        symbols = [fav.get("stock_code") or fav.get("symbol") for fav in favorites]
        symbols = [s for s in symbols if s]  # 过滤空值
        symbol_count = len(symbols)

        # 🔥 限制同步股票数量，防止超时
        if symbol_count > MAX_SYNC_STOCKS:
            logger.warning(f"⚠️ 自选股数量 {symbol_count} 超过限制 {MAX_SYNC_STOCKS}，仅同步前 {MAX_SYNC_STOCKS} 只")
            symbols = symbols[:MAX_SYNC_STOCKS]

        logger.info(f"🎯 需要同步的股票: {len(symbols)} 只")

        # 根据数据源选择同步服务
        if request.data_source == "tushare":
            from app.worker.tushare_sync_service import get_tushare_sync_service

            service = await get_tushare_sync_service()
        elif request.data_source == "akshare":
            from app.worker.akshare_sync_service import get_akshare_sync_service

            service = await get_akshare_sync_service()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的数据源: {request.data_source}",
            )

        if not service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{request.data_source} 服务不可用",
            )

        # 🔥 添加超时保护：同步实时行情最长等待 SYNC_REALTIME_TIMEOUT 秒
        sync_result = await asyncio.wait_for(
            service.sync_realtime_quotes(
                symbols=symbols,
                force=True,  # 强制执行，跳过交易时间检查
            ),
            timeout=SYNC_REALTIME_TIMEOUT,
        )

        success_count = sync_result.get("success_count", 0)
        failed_count = sync_result.get("failed_count", 0)

        logger.info(f"✅ 自选股实时行情同步完成: 成功 {success_count}/{len(symbols)} 只")

        return ok(
            {
                "total": len(symbols),
                "success_count": success_count,
                "failed_count": failed_count,
                "symbols": symbols,
                "data_source": request.data_source,
                "message": f"同步完成: 成功 {success_count} 只，失败 {failed_count} 只",
            },
        )

    except asyncio.TimeoutError:
        logger.warning(f"⚠️ 自选股实时行情同步超时 (>{SYNC_REALTIME_TIMEOUT}s)")
        return ok(
            {
                "total": symbol_count,
                "success_count": 0,
                "failed_count": 0,
                "timeout": True,
                "message": f"同步超时（>{SYNC_REALTIME_TIMEOUT}秒），部分数据可能未同步完成",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 同步自选股实时行情失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"同步失败: {e!s}")
