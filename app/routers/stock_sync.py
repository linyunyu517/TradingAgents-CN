"""
股票数据同步API路由
支持单个股票或批量股票的历史数据和财务数据同步
"""

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.worker.tushare_sync_service import get_tushare_sync_service

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/stock-sync", tags=["股票数据同步"])


async def _sync_latest_to_market_quotes(symbol: str) -> None:
    """
    将 stock_daily_quotes 中的最新数据同步到 market_quotes

    智能判断逻辑：
    - 如果 market_quotes 中已有更新的数据（trade_date 更新），则不覆盖
    - 如果 market_quotes 中没有数据或数据较旧，则更新

    Args:
        symbol: 股票代码（6位）
    """
    db = get_mongo_db()
    symbol6 = str(symbol).zfill(6)

    # 从 stock_daily_quotes 获取最新数据
    latest_doc = await db.stock_daily_quotes.find_one({"symbol": symbol6}, sort=[("trade_date", -1)])

    if not latest_doc:
        logger.warning(f"⚠️ {symbol6}: stock_daily_quotes 中没有数据")
        return

    historical_trade_date = latest_doc.get("trade_date")

    # 🔥 检查 market_quotes 中是否已有更新的数据
    existing_quote = await db.market_quotes.find_one({"code": symbol6})

    if existing_quote:
        existing_trade_date = existing_quote.get("trade_date")

        # 如果 market_quotes 中的数据日期更新或相同，则不覆盖
        if existing_trade_date and historical_trade_date:
            # 比较日期字符串（格式：YYYY-MM-DD 或 YYYYMMDD）
            existing_date_str = str(existing_trade_date).replace("-", "")
            historical_date_str = str(historical_trade_date).replace("-", "")

            if existing_date_str >= historical_date_str:
                # 🔥 日期相同或更新时，都不覆盖（避免用历史数据覆盖实时数据）
                logger.info(
                    f"⏭️ {symbol6}: market_quotes 中的数据日期 >= 历史数据日期 "
                    f"(market_quotes: {existing_trade_date}, historical: {historical_trade_date})，跳过覆盖",
                )
                return

    # 提取需要的字段
    quote_data = {
        "code": symbol6,
        "symbol": symbol6,
        "close": latest_doc.get("close"),
        "open": latest_doc.get("open"),
        "high": latest_doc.get("high"),
        "low": latest_doc.get("low"),
        "volume": latest_doc.get("volume"),  # 已经转换过单位
        "amount": latest_doc.get("amount"),  # 已经转换过单位
        "pct_chg": latest_doc.get("pct_chg"),
        "pre_close": latest_doc.get("pre_close"),
        "trade_date": latest_doc.get("trade_date"),
        "updated_at": datetime.utcnow(),
    }

    # 🔥 日志：记录同步的成交量
    logger.info(
        f"📊 [同步到market_quotes] {symbol6} - "
        f"volume={quote_data['volume']}, amount={quote_data['amount']}, trade_date={quote_data['trade_date']}",
    )

    # 更新 market_quotes
    await db.market_quotes.update_one({"code": symbol6}, {"$set": quote_data}, upsert=True)


class SingleStockSyncRequest(BaseModel):
    """单股票同步请求"""

    symbol: str = Field(..., description="股票代码（6位）")
    sync_realtime: bool = Field(False, description="是否同步实时行情")
    sync_historical: bool = Field(True, description="是否同步历史数据")
    sync_financial: bool = Field(True, description="是否同步财务数据")
    sync_basic: bool = Field(False, description="是否同步基础数据")
    data_source: str = Field("tushare", description="数据源: tushare")
    days: int = Field(30, description="历史数据天数", ge=1, le=3650)


class BatchStockSyncRequest(BaseModel):
    """批量股票同步请求"""

    symbols: list[str] = Field(..., description="股票代码列表")
    sync_historical: bool = Field(True, description="是否同步历史数据")
    sync_financial: bool = Field(True, description="是否同步财务数据")
    sync_basic: bool = Field(False, description="是否同步基础数据")
    data_source: str = Field("tushare", description="数据源: tushare")
    days: int = Field(30, description="历史数据天数", ge=1, le=3650)


@router.post("/single")
async def sync_single_stock(
    request: SingleStockSyncRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user),
):
    """
    同步单个股票的历史数据、财务数据和实时行情

    - **symbol**: 股票代码（6位）
    - **sync_realtime**: 是否同步实时行情
    - **sync_historical**: 是否同步历史数据
    - **sync_financial**: 是否同步财务数据
    - **data_source**: 数据源（tushare）
    - **days**: 历史数据天数
    """
    try:
        logger.info(f"📊 开始同步单个股票: {request.symbol} (数据源: {request.data_source})")

        result = {
            "symbol": request.symbol,
            "realtime_sync": None,
            "historical_sync": None,
            "financial_sync": None,
            "basic_sync": None,
        }

        # 同步实时行情
        if request.sync_realtime:
            try:
                realtime_debug = {
                    "requested_data_source": request.data_source,
                    "data_source_used": None,
                    "attempted_sources": [],
                    "primary_stats": None,
                    "fallback_stats": None,
                    "primary_error": None,
                    "fallback_error": None,
                }

                # 单个股票实时行情同步：使用 Tushare 数据源
                actual_data_source = request.data_source
                realtime_debug["data_source_used"] = actual_data_source
                realtime_debug["attempted_sources"].append(actual_data_source)

                service = await get_tushare_sync_service()

                # 同步实时行情（只同步指定的股票）
                realtime_result = await service.sync_realtime_quotes(
                    symbols=[request.symbol],
                    force=True,  # 强制执行，跳过交易时间检查
                )
                realtime_debug["primary_stats"] = realtime_result
                if realtime_result.get("errors"):
                    realtime_debug["primary_error"] = realtime_result["errors"][0]



                success = realtime_result.get("success_count", 0) > 0

                message = f"实时行情同步{'成功' if success else '失败'}"

                db = get_mongo_db()
                latest_quote = await db.market_quotes.find_one(
                    {"code": str(request.symbol).zfill(6)},
                    {"_id": 0, "code": 1, "trade_date": 1, "updated_at": 1, "close": 1},
                )

                result["realtime_sync"] = {
                    "success": success,
                    "message": message,
                    "data_source_used": actual_data_source,  # 🔥 返回实际使用的数据源
                    "attempted_sources": realtime_debug["attempted_sources"],
                    "primary_error": realtime_debug["primary_error"],
                    "fallback_error": realtime_debug["fallback_error"],
                    "market_quote_available": latest_quote is not None,
                    "market_quote_snapshot": latest_quote,
                }
                logger.info(f"✅ {request.symbol} 实时行情同步完成: {success}")
                logger.info(
                    "📋 %s 实时行情同步详情: requested=%s, used=%s, attempted=%s, primary_error=%s, fallback_error=%s, market_quote_available=%s",
                    request.symbol,
                    request.data_source,
                    actual_data_source,
                    realtime_debug["attempted_sources"],
                    realtime_debug["primary_error"],
                    realtime_debug["fallback_error"],
                    latest_quote is not None,
                )

            except Exception as e:
                logger.error(f"❌ {request.symbol} 实时行情同步失败: {e}")
                result["realtime_sync"] = {"success": False, "error": str(e)}

        # 同步历史数据
        if request.sync_historical:
            try:
                if request.data_source == "tushare":
                    service = await get_tushare_sync_service()
                else:
                    raise ValueError(f"不支持的数据源: {request.data_source}")

                # 计算日期范围
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=request.days)).strftime("%Y-%m-%d")

                # 同步历史数据
                hist_result = await service.sync_historical_data(
                    symbols=[request.symbol], start_date=start_date, end_date=end_date, incremental=False,
                )

                result["historical_sync"] = {
                    "success": hist_result.get("success_count", 0) > 0,
                    "records": hist_result.get("total_records", 0),
                    "message": f"同步了 {hist_result.get('total_records', 0)} 条历史记录",
                }
                logger.info(f"✅ {request.symbol} 历史数据同步完成: {hist_result.get('total_records', 0)} 条记录")

                # 🔥 同步最新历史数据到 market_quotes
                if hist_result.get("success_count", 0) > 0:
                    try:
                        await _sync_latest_to_market_quotes(request.symbol)
                        logger.info(f"✅ {request.symbol} 最新数据已同步到 market_quotes")
                    except Exception as e:
                        logger.warning(f"⚠️ {request.symbol} 同步到 market_quotes 失败: {e}")

                # 🔥 【已禁用】如果没有勾选实时行情，但在交易时间内，自动同步实时行情
                # 用户反馈：不希望自动同步实时行情，应该严格按照用户的选择
                # if not request.sync_realtime:
                #     from app.utils.trading_time import is_trading_time
                #     if is_trading_time():
                #         logger.info(f"📊 {request.symbol} 当前在交易时间内，自动同步实时行情")
                #         try:
                #             realtime_result = await service.sync_realtime_quotes(
                #                 symbols=[request.symbol],
                #                 force=True
                #             )
                #             if realtime_result.get("success_count", 0) > 0:
                #                 logger.info(f"✅ {request.symbol} 实时行情自动同步成功")
                #                 result["realtime_sync"] = {
                #                     "success": True,
                #                     "message": "实时行情自动同步成功（交易时间内）"
                #                 }
                #         except Exception as e:
                #             logger.warning(f"⚠️ {request.symbol} 实时行情自动同步失败: {e}")

            except Exception as e:
                logger.error(f"❌ {request.symbol} 历史数据同步失败: {e}")
                result["historical_sync"] = {"success": False, "error": str(e)}

        # 同步财务数据 - 已移除（仅保留 Tushare 数据源）
        if request.sync_financial:
            result["financial_sync"] = {"success": False, "message": "财务数据同步功能已移除（仅保留 Tushare 数据源）"}

        # 同步基础数据
        if request.sync_basic:
            try:
                # 🔥 同步单个股票的基础数据
                # 参考 basics_sync_service 的实现逻辑
                if request.data_source == "tushare":
                    from app.services.basics_sync import (
                        fetch_daily_basic_mv_map,
                        fetch_latest_roe_map,
                        fetch_stock_basic_df,
                        find_latest_trade_date,
                    )

                    db = get_mongo_db()
                    symbol6 = str(request.symbol).zfill(6)

                    # Step 1: 获取股票基础信息
                    stock_df = await asyncio.to_thread(fetch_stock_basic_df)
                    if stock_df is None or stock_df.empty:
                        result["basic_sync"] = {"success": False, "error": "Tushare 返回空数据"}
                    else:
                        # 筛选出目标股票
                        stock_row = None
                        for _, row in stock_df.iterrows():
                            ts_code = row.get("ts_code", "")
                            if isinstance(ts_code, str) and ts_code.startswith(symbol6):
                                stock_row = row
                                break

                        if stock_row is None:
                            result["basic_sync"] = {"success": False, "error": f"未找到股票 {symbol6} 的基础信息"}
                        else:
                            # Step 2: 获取最新交易日和财务指标
                            latest_trade_date = await asyncio.to_thread(find_latest_trade_date)
                            daily_data_map = await asyncio.to_thread(fetch_daily_basic_mv_map, latest_trade_date)
                            roe_map = await asyncio.to_thread(fetch_latest_roe_map)

                            # Step 3: 构建文档（参考 basics_sync_service 的逻辑）
                            # 🔥 先获取当前时间，避免作用域问题
                            now_iso = datetime.utcnow().isoformat()

                            name = stock_row.get("name") or ""
                            area = stock_row.get("area") or ""
                            industry = stock_row.get("industry") or ""
                            market = stock_row.get("market") or ""
                            list_date = stock_row.get("list_date") or ""
                            ts_code = stock_row.get("ts_code") or ""

                            # 提取6位代码
                            code = ts_code.split(".")[0] if isinstance(ts_code, str) and "." in ts_code else symbol6

                            # 判断交易所
                            if isinstance(ts_code, str):
                                if ts_code.endswith(".SH"):
                                    sse = "上海证券交易所"
                                elif ts_code.endswith(".SZ"):
                                    sse = "深圳证券交易所"
                                elif ts_code.endswith(".BJ"):
                                    sse = "北京证券交易所"
                                else:
                                    sse = "未知"
                            else:
                                sse = "未知"

                            # 生成 full_symbol
                            full_symbol = ts_code

                            # 提取财务指标
                            daily_metrics = {}
                            if isinstance(ts_code, str) and ts_code in daily_data_map:
                                daily_metrics = daily_data_map[ts_code]

                            # 市值转换（万元 -> 亿元）
                            total_mv_yi = None
                            circ_mv_yi = None
                            if "total_mv" in daily_metrics:
                                try:
                                    total_mv_yi = float(daily_metrics["total_mv"]) / 10000.0
                                except Exception:
                                    logger.debug("总市值转换失败，跳过该字段")
                            if "circ_mv" in daily_metrics:
                                try:
                                    circ_mv_yi = float(daily_metrics["circ_mv"]) / 10000.0
                                except Exception:
                                    logger.debug("流通市值转换失败，跳过该字段")

                            # 构建文档
                            doc = {
                                "code": code,
                                "symbol": code,
                                "name": name,
                                "area": area,
                                "industry": industry,
                                "market": market,
                                "list_date": list_date,
                                "sse": sse,
                                "sec": "stock_cn",
                                "source": "tushare",
                                "updated_at": now_iso,
                                "full_symbol": full_symbol,
                            }

                            # 添加市值
                            if total_mv_yi is not None:
                                doc["total_mv"] = total_mv_yi
                            if circ_mv_yi is not None:
                                doc["circ_mv"] = circ_mv_yi

                            # 添加估值指标
                            for field in ["pe", "pb", "ps", "pe_ttm", "pb_mrq", "ps_ttm"]:
                                if field in daily_metrics:
                                    doc[field] = daily_metrics[field]

                            # 添加 ROE
                            if isinstance(ts_code, str) and ts_code in roe_map:
                                roe_val = roe_map[ts_code].get("roe")
                                if roe_val is not None:
                                    doc["roe"] = roe_val

                            # 添加交易指标
                            for field in ["turnover_rate", "volume_ratio"]:
                                if field in daily_metrics:
                                    doc[field] = daily_metrics[field]

                            # 添加股本信息
                            for field in ["total_share", "float_share"]:
                                if field in daily_metrics:
                                    doc[field] = daily_metrics[field]

                            # Step 4: 更新数据库
                            await db.stock_basic_info.update_one(
                                {"code": code, "source": "tushare"}, {"$set": doc}, upsert=True,
                            )

                            result["basic_sync"] = {"success": True, "message": "基础数据同步成功"}
                            logger.info(f"✅ {request.symbol} 基础数据同步完成")

                else:
                    result["basic_sync"] = {
                        "success": False,
                        "error": f"基础数据同步仅支持 Tushare 数据源，当前数据源: {request.data_source}",
                    }

            except Exception as e:
                logger.error(f"❌ {request.symbol} 基础数据同步失败: {e}")
                result["basic_sync"] = {"success": False, "error": str(e)}

        # 判断整体是否成功
        overall_success = (
            (not request.sync_realtime or result["realtime_sync"].get("success", False))
            and (not request.sync_historical or result["historical_sync"].get("success", False))
            and (not request.sync_financial or result["financial_sync"].get("success", False))
            and (not request.sync_basic or result["basic_sync"].get("success", False))
        )

        # 添加整体成功标志到结果中
        result["overall_success"] = overall_success

        logger.info("📋 单股同步汇总 %s: %s", request.symbol, result)

        return ok(data=result, message=f"股票 {request.symbol} 数据同步{'成功' if overall_success else '部分失败'}")

    except Exception as e:
        logger.error(f"❌ 同步单个股票失败: {e}")
        raise HTTPException(status_code=500, detail=f"同步失败: {e!s}")


@router.post("/batch")
async def sync_batch_stocks(
    request: BatchStockSyncRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user),
):
    """
    批量同步多个股票的历史数据和财务数据

    - **symbols**: 股票代码列表
    - **sync_historical**: 是否同步历史数据
    - **sync_financial**: 是否同步财务数据
    - **data_source**: 数据源（tushare）
    - **days**: 历史数据天数
    """
    try:
        logger.info(f"📊 开始批量同步 {len(request.symbols)} 只股票 (数据源: {request.data_source})")

        result = {
            "total": len(request.symbols),
            "symbols": request.symbols,
            "historical_sync": None,
            "financial_sync": None,
            "basic_sync": None,
        }

        # 同步历史数据
        if request.sync_historical:
            try:
                if request.data_source == "tushare":
                    service = await get_tushare_sync_service()
                else:
                    raise ValueError(f"不支持的数据源: {request.data_source}")

                # 计算日期范围
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=request.days)).strftime("%Y-%m-%d")

                # 批量同步历史数据
                hist_result = await service.sync_historical_data(
                    symbols=request.symbols, start_date=start_date, end_date=end_date, incremental=False,
                )

                result["historical_sync"] = {
                    "success_count": hist_result.get("success_count", 0),
                    "error_count": hist_result.get("error_count", 0),
                    "total_records": hist_result.get("total_records", 0),
                    "message": f"成功同步 {hist_result.get('success_count', 0)}/{len(request.symbols)} 只股票，共 {hist_result.get('total_records', 0)} 条记录",
                }
                logger.info(f"✅ 批量历史数据同步完成: {hist_result.get('success_count', 0)}/{len(request.symbols)}")

            except Exception as e:
                logger.error(f"❌ 批量历史数据同步失败: {e}")
                result["historical_sync"] = {"success_count": 0, "error_count": len(request.symbols), "error": str(e)}

        # 同步财务数据 - 已移除（仅保留 Tushare 数据源）
        if request.sync_financial:
            result["financial_sync"] = {"success_count": 0, "error_count": len(request.symbols), "message": "财务数据同步功能已移除（仅保留 Tushare 数据源）"}

        # 同步基础数据
        if request.sync_basic:
            try:
                # 🔥 批量同步基础数据
                # 注意：基础数据同步服务目前只支持 Tushare 数据源
                if request.data_source == "tushare":
                    try:
                        from tradingagents.dataflows.providers.china.tushare import TushareProvider
                    except ImportError:
                        raise RuntimeError(
                            "Tushare 数据源模块已移除",
                        )

                    tushare_provider = TushareProvider()
                    if tushare_provider.is_available():
                        success_count = 0
                        error_count = 0

                        for symbol in request.symbols:
                            try:
                                basic_info = await tushare_provider.get_stock_basic_info(symbol)

                                if basic_info:
                                    # 保存到 MongoDB
                                    db = get_mongo_db()
                                    symbol6 = str(symbol).zfill(6)

                                    # 添加必要字段
                                    basic_info["code"] = symbol6
                                    basic_info["source"] = "tushare"
                                    basic_info["updated_at"] = datetime.utcnow()

                                    await db.stock_basic_info.update_one(
                                        {"code": symbol6, "source": "tushare"}, {"$set": basic_info}, upsert=True,
                                    )

                                    success_count += 1
                                    logger.info(f"✅ {symbol} 基础数据同步成功")
                                else:
                                    error_count += 1
                                    logger.warning(f"⚠️ {symbol} 未获取到基础数据")
                            except Exception as e:
                                error_count += 1
                                logger.error(f"❌ {symbol} 基础数据同步失败: {e}")

                        result["basic_sync"] = {
                            "success_count": success_count,
                            "error_count": error_count,
                            "total_symbols": len(request.symbols),
                            "message": f"成功同步 {success_count}/{len(request.symbols)} 只股票的基础数据",
                        }
                        logger.info(f"✅ 批量基础数据同步完成: {success_count}/{len(request.symbols)}")
                    else:
                        result["basic_sync"] = {
                            "success_count": 0,
                            "error_count": len(request.symbols),
                            "error": "Tushare 数据源不可用",
                        }
                else:
                    result["basic_sync"] = {
                        "success_count": 0,
                        "error_count": len(request.symbols),
                        "error": f"基础数据同步仅支持 Tushare 数据源，当前数据源: {request.data_source}",
                    }

            except Exception as e:
                logger.error(f"❌ 批量基础数据同步失败: {e}")
                result["basic_sync"] = {"success_count": 0, "error_count": len(request.symbols), "error": str(e)}

        # 判断整体是否成功
        hist_success = result["historical_sync"].get("success_count", 0) if request.sync_historical else 0
        fin_success = result["financial_sync"].get("success_count", 0) if request.sync_financial else 0
        basic_success = result["basic_sync"].get("success_count", 0) if request.sync_basic else 0
        total_success = max(hist_success, fin_success, basic_success)

        # 添加统计信息到结果中
        result["total_success"] = total_success
        result["total_symbols"] = len(request.symbols)

        return ok(data=result, message=f"批量同步完成: {total_success}/{len(request.symbols)} 只股票成功")

    except Exception as e:
        logger.error(f"❌ 批量同步失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量同步失败: {e!s}")


@router.get("/status/{symbol}")
async def get_sync_status(symbol: str, current_user: dict = Depends(get_current_user)):
    """
    获取股票的同步状态

    返回最后同步时间、数据条数等信息
    """
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()

        # 查询历史数据最后同步时间
        hist_doc = await db.historical_data.find_one({"symbol": symbol}, sort=[("date", -1)])

        # 查询财务数据最后同步时间
        fin_doc = await db.stock_financial_data.find_one({"symbol": symbol}, sort=[("updated_at", -1)])

        # 统计历史数据条数
        hist_count = await db.historical_data.count_documents({"symbol": symbol})

        # 统计财务数据条数
        fin_count = await db.stock_financial_data.count_documents({"symbol": symbol})

        return ok(
            data={
                "symbol": symbol,
                "historical_data": {
                    "last_sync": hist_doc.get("updated_at") if hist_doc else None,
                    "last_date": hist_doc.get("date") if hist_doc else None,
                    "total_records": hist_count,
                },
                "financial_data": {
                    "last_sync": fin_doc.get("updated_at") if fin_doc else None,
                    "last_report_period": fin_doc.get("report_period") if fin_doc else None,
                    "total_records": fin_count,
                },
            },
        )

    except Exception as e:
        logger.error(f"❌ 获取同步状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取同步状态失败: {e!s}")
