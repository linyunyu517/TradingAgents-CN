"""
股票分析API路由
增强版本，支持优先级、进度跟踪、任务管理等功能
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.models.analysis import (
    BatchAnalysisRequest,
    SingleAnalysisRequest,
)
from app.routers.auth_db import get_current_user
from app.services.queue_service import QueueService, get_queue_service
from app.services.simple_analysis_service import _extract_hpc_reports, get_simple_analysis_service
from app.services.websocket_manager import get_websocket_manager

router = APIRouter()
logger = logging.getLogger("webapi")

# 🐛 [BUG-018] asyncio.Semaphore 作为协程层第一道防线
# 限制 /single 端点的最大并发分析任务数，配合 BoundedSemaphore 双层防护
single_analysis_semaphore = asyncio.Semaphore(10)


# 兼容性：保留原有的请求模型
class SingleAnalyzeRequest(BaseModel):
    symbol: str
    parameters: dict = Field(default_factory=dict)


class BatchAnalyzeRequest(BaseModel):
    symbols: list[str]
    parameters: dict = Field(default_factory=dict)
    title: str = Field(default="批量分析", description="批次标题")
    description: str | None = Field(None, description="批次描述")


# 新版API端点
@router.post("/single", response_model=dict[str, Any])
async def submit_single_analysis(
    request: SingleAnalysisRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user),
):
    """提交单股分析任务 - 使用 BackgroundTasks 异步执行"""
    try:
        logger.info("🎯 收到单股分析请求")
        logger.info(f"👤 用户信息: {user}")
        logger.info(f"📊 请求数据: {request}")

        # 立即创建任务记录并返回，不等待执行完成
        analysis_service = get_simple_analysis_service()
        result = await analysis_service.create_analysis_task(user["id"], request)

        # 提取变量，避免闭包问题
        task_id = result["task_id"]
        user_id = user["id"]

        # 定义一个包装函数来运行异步任务
        async def run_analysis_task():
            """包装函数：在后台运行分析任务"""
            # 🐛 [BUG-018] asyncio.Semaphore 保护：超出10个并发时排队等待
            async with single_analysis_semaphore:
                try:
                    logger.info(f"🚀 [BackgroundTask] 开始执行分析任务: {task_id}")
                    logger.info(f"📝 [BackgroundTask] task_id={task_id}, user_id={user_id}")
                    logger.info(f"📝 [BackgroundTask] request={request}")

                    # 重新获取服务实例，确保在正确的上下文中
                    logger.info("🔧 [BackgroundTask] 正在获取服务实例...")
                    service = get_simple_analysis_service()
                    logger.info(f"✅ [BackgroundTask] 服务实例获取成功: {id(service)}")

                    logger.info("🚀 [BackgroundTask] 准备调用 execute_analysis_background...")
                    # ========== BUG-010 修复: 单分析任务添加超时控制（3600秒），避免任务永久阻塞 ==========
                    # [FIX] 2026-06-18: 超时从 1800s 延长至 3600s，避免 HPC-Loop 等长流程任务超时截断
                    await asyncio.wait_for(
                        service.execute_analysis_background(task_id, user_id, request),
                        timeout=3600,  # 60分钟超时，与常量 ANALYSIS_TIMEOUT 保持一致
                    )
                    logger.info(f"✅ [BackgroundTask] 分析任务完成: {task_id}")
                except asyncio.TimeoutError:
                    logger.error(f"❌ [BackgroundTask] 单分析任务超时: {task_id} (3600s)")
                except Exception as e:
                    logger.error(f"❌ [BackgroundTask] 分析任务失败: {task_id}, 错误: {e}", exc_info=True)

        # 使用 BackgroundTasks 执行异步任务
        background_tasks.add_task(run_analysis_task)

        logger.info(f"✅ 分析任务已在后台启动: {result}")

        return {"success": True, "data": result, "message": "分析任务已在后台启动"}
    except Exception as e:
        logger.error(f"❌ 提交单股分析任务失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# 测试路由 - 验证路由是否被正确注册
@router.get("/test-route")
async def test_route():
    """测试路由是否工作"""
    logger.info("🧪 测试路由被调用了！")
    return {"message": "测试路由工作正常", "timestamp": time.time()}


@router.get("/tasks/{task_id}/status", response_model=dict[str, Any])
async def get_task_status_new(task_id: str, user: dict = Depends(get_current_user)):
    """获取分析任务状态（新版异步实现）"""
    try:
        logger.info(f"🔍 [NEW ROUTE] 进入新版状态查询路由: {task_id}")
        logger.info(f"👤 [NEW ROUTE] 用户: {user}")

        analysis_service = get_simple_analysis_service()
        logger.info(f"🔧 [NEW ROUTE] 获取分析服务实例: {id(analysis_service)}")

        result = await analysis_service.get_task_status(task_id)
        logger.info(f"📊 [NEW ROUTE] 查询结果: {result is not None}")

        if result:
            return {"success": True, "data": result, "message": "任务状态获取成功"}
        # 内存中没有找到，尝试从MongoDB中查找
        logger.info(f"📊 [STATUS] 内存中未找到，尝试从MongoDB查找: {task_id}")

        from app.core.database import get_mongo_db

        db = get_mongo_db()

        # 首先从analysis_tasks集合中查找（正在进行的任务）
        task_result = await db.analysis_tasks.find_one({"task_id": task_id})

        if task_result:
            logger.info(f"✅ [STATUS] 从analysis_tasks找到任务: {task_id}")

            # 构造状态响应（正在进行的任务）
            status = task_result.get("status", "pending")
            progress = task_result.get("progress", 0)

            # 计算时间信息
            start_time = task_result.get("started_at") or task_result.get("created_at")
            current_time = datetime.utcnow()
            elapsed_time = 0
            if start_time:
                elapsed_time = (current_time - start_time).total_seconds()

            # 🐛 [BUG-031 RC2] 构造 progress_msg 用于前端 fallback 链
            progress_msg = task_result.get("message") or task_result.get("progress_message") or ""
            # 🐛 [BUG-031 RC2] current_step_name 从 MongoDB 获取，fallback 到 status
            current_step_name = task_result.get("current_step_name") or task_result.get("current_step") or status

            status_data = {
                "task_id": task_id,
                "status": status,
                "progress": progress,
                # 🐛 [BUG-031 RC5] 使用实际进度消息替代硬编码
                "progress_msg": progress_msg,  # 🐛 [BUG-031 RC2] 新增字段，供前端 fallback
                "message": progress_msg or f"任务{status}中...",
                "current_step": current_step_name,  # 兼容旧字段
                "current_step_name": current_step_name,  # 🦕 前端期望字段名
                "current_step_description": task_result.get("current_step_description") or "",
                "start_time": start_time,
                "end_time": task_result.get("completed_at"),
                "elapsed_time": elapsed_time,
                "remaining_time": 0,  # 无法准确估算
                "estimated_total_time": 0,
                "symbol": task_result.get("symbol") or task_result.get("stock_code"),
                "stock_code": task_result.get("symbol") or task_result.get("stock_code"),  # 兼容字段
                "stock_symbol": task_result.get("symbol") or task_result.get("stock_code"),
                "source": "mongodb_tasks",  # 标记数据来源
            }

            return {"success": True, "data": status_data, "message": "任务状态获取成功（从任务记录恢复）"}

        # 如果analysis_tasks中没有找到，再从analysis_reports集合中查找（已完成的任务）
        mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

        if mongo_result:
            logger.info(f"✅ [STATUS] 从analysis_reports找到任务: {task_id}")

            # 构造状态响应（模拟已完成的任务）
            # 计算已完成任务的时间信息
            start_time = mongo_result.get("created_at")
            end_time = mongo_result.get("updated_at")
            elapsed_time = 0
            if start_time and end_time:
                elapsed_time = (end_time - start_time).total_seconds()

            status_data = {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "message": "分析完成（从历史记录恢复）",
                "current_step": "completed",
                "start_time": start_time,
                "end_time": end_time,
                "elapsed_time": elapsed_time,
                "remaining_time": 0,
                "estimated_total_time": elapsed_time,  # 已完成任务的总时长就是已用时间
                "stock_code": mongo_result.get("stock_symbol"),
                "stock_symbol": mongo_result.get("stock_symbol"),
                "analysts": mongo_result.get("analysts", []),
                "research_depth": mongo_result.get("research_depth", "快速"),
                "source": "mongodb_reports",  # 标记数据来源
            }

            return {"success": True, "data": status_data, "message": "任务状态获取成功（从历史记录恢复）"}
        logger.warning(f"❌ [STATUS] MongoDB中也未找到: {task_id} trace={task_id}")
        raise HTTPException(status_code=404, detail="任务不存在")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/result", response_model=dict[str, Any])
async def get_task_result(task_id: str, user: dict = Depends(get_current_user)):
    """获取分析任务结果"""
    try:
        logger.info(f"🔍 [RESULT] 获取任务结果: {task_id}")
        logger.info(f"👤 [RESULT] 用户: {user}")

        analysis_service = get_simple_analysis_service()
        task_status = await analysis_service.get_task_status(task_id)

        result_data = None

        if task_status and task_status.get("status") == "completed":
            # 从内存中获取结果数据
            result_data = task_status.get("result_data")
            logger.info("📊 [RESULT] 从内存中获取到结果数据")

            # 🔍 调试：检查内存中的数据结构
            if result_data:
                logger.info(f"📊 [RESULT] 内存数据键: {list(result_data.keys())}")
                logger.info(f"📊 [RESULT] 内存中有decision字段: {bool(result_data.get('decision'))}")
                logger.info(f"📊 [RESULT] 内存中summary长度: {len(result_data.get('summary', ''))}")
                logger.info(f"📊 [RESULT] 内存中recommendation长度: {len(result_data.get('recommendation', ''))}")
                if result_data.get("decision"):
                    decision = result_data["decision"]
                    logger.info(
                        f"📊 [RESULT] 内存decision内容: action={decision.get('action')}, target_price={decision.get('target_price')}",
                    )
            else:
                logger.warning("⚠️ [RESULT] 内存中result_data为空")

        if not result_data:
            # 内存中没有找到，尝试从MongoDB中查找
            logger.info(f"📊 [RESULT] 内存中未找到，尝试从MongoDB查找: {task_id}")

            from app.core.database import get_mongo_db

            db = get_mongo_db()

            # 从analysis_reports集合中查找（优先使用 task_id 匹配）
            mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

            if not mongo_result:
                # 兼容旧数据：旧记录可能没有 task_id，但 analysis_id 存在于 analysis_tasks.result
                tasks_doc_for_id = await db.analysis_tasks.find_one({"task_id": task_id}, {"result.analysis_id": 1})
                analysis_id = tasks_doc_for_id.get("result", {}).get("analysis_id") if tasks_doc_for_id else None
                if analysis_id:
                    logger.info(f"🔎 [RESULT] 按analysis_id兜底查询 analysis_reports: {analysis_id}")
                    mongo_result = await db.analysis_reports.find_one({"analysis_id": analysis_id})

            if mongo_result:
                logger.info(f"✅ [RESULT] 从MongoDB找到结果: {task_id}")

                # 直接使用MongoDB中的数据结构（与web目录保持一致）
                result_data = {
                    "analysis_id": mongo_result.get("analysis_id"),
                    "stock_symbol": mongo_result.get("stock_symbol"),
                    "stock_code": mongo_result.get("stock_symbol"),  # 兼容性
                    "stock_name": mongo_result.get("stock_name", mongo_result.get("stock_symbol")),
                    "analysis_date": mongo_result.get("analysis_date"),
                    "summary": mongo_result.get("summary", ""),
                    "recommendation": mongo_result.get("recommendation", ""),
                    "confidence_score": mongo_result.get("confidence_score", 0.0),
                    "risk_level": mongo_result.get("risk_level", "中等"),
                    "key_points": mongo_result.get("key_points", []),
                    "execution_time": mongo_result.get("execution_time", 0),
                    "tokens_used": mongo_result.get("tokens_used", 0),
                    "analysts": mongo_result.get("analysts", []),
                    "research_depth": mongo_result.get("research_depth", "快速"),
                    "reports": mongo_result.get("reports", {}),
                    "created_at": mongo_result.get("created_at"),
                    "updated_at": mongo_result.get("updated_at"),
                    "status": mongo_result.get("status", "completed"),
                    "decision": mongo_result.get("decision", {}),
                    "source": "mongodb",  # 标记数据来源
                }

                # 🐛 [Fix 2026-06-27] 兼容历史数据：analysis_reports 文档中可能没有 decision 字段
                # 从独立字段重组 decision 字典
                if not result_data["decision"]:
                    result_data["decision"] = {
                        "action": mongo_result.get("action", "持有"),
                        "confidence": mongo_result.get("confidence", 0.0),
                        "risk_score": 0.3,
                        "target_price": mongo_result.get("target_price"),
                        "reasoning": mongo_result.get("reasoning", ""),
                    }
                    logger.info(
                        "📊 [RESULT] 已从独立字段重组 decision: "
                        f"action={result_data['decision']['action']}, "
                        f"confidence={result_data['decision']['confidence']}",
                    )

                # 添加调试信息
                logger.info(f"📊 [RESULT] MongoDB数据结构: {list(result_data.keys())}")
                logger.info(f"📊 [RESULT] MongoDB summary长度: {len(result_data['summary'])}")
                logger.info(f"📊 [RESULT] MongoDB recommendation长度: {len(result_data['recommendation'])}")
                logger.info(f"📊 [RESULT] MongoDB decision字段: {bool(result_data.get('decision'))}")
                if result_data.get("decision"):
                    decision = result_data["decision"]
                    logger.info(
                        f"📊 [RESULT] MongoDB decision内容: action={decision.get('action')}, target_price={decision.get('target_price')}, confidence={decision.get('confidence')}",
                    )

                # 🐛 [Fix 2026-06-27] 如果重组后仍没有有效 action，降级到 analysis_tasks 集合
                if not result_data.get("decision", {}).get("action"):
                    logger.warning("📊 [RESULT] Path B decision 无效，降级到 analysis_tasks")
                    tasks_doc = await db.analysis_tasks.find_one(
                        {"task_id": task_id},
                        {"result": 1, "symbol": 1, "stock_code": 1},
                    )
                    if tasks_doc and tasks_doc.get("result"):
                        r = tasks_doc["result"] or {}
                        task_decision = r.get("decision", {})
                        if task_decision and task_decision.get("action"):
                            result_data["decision"] = task_decision
                            result_data["source"] = "analysis_tasks_fallback"
                            logger.info(
                                "📊 [RESULT] 从 analysis_tasks 获取到 decision: "
                                f"action={task_decision.get('action')}",
                            )
            else:
                # 兜底：analysis_tasks 集合中的 result 字段
                tasks_doc = await db.analysis_tasks.find_one(
                    {"task_id": task_id},
                    {"result": 1, "symbol": 1, "stock_code": 1, "created_at": 1, "completed_at": 1},
                )
                if tasks_doc and tasks_doc.get("result"):
                    r = tasks_doc["result"] or {}
                    logger.info("✅ [RESULT] 从analysis_tasks.result 找到结果")
                    # 获取股票代码 (优先使用symbol)
                    symbol = (
                        tasks_doc.get("symbol")
                        or tasks_doc.get("stock_code")
                        or r.get("stock_symbol")
                        or r.get("stock_code")
                    )
                    result_data = {
                        "analysis_id": r.get("analysis_id"),
                        "stock_symbol": symbol,
                        "stock_code": symbol,  # 兼容字段
                        "stock_name": r.get("stock_name", symbol),
                        "analysis_date": r.get("analysis_date"),
                        "summary": r.get("summary", ""),
                        "recommendation": r.get("recommendation", ""),
                        "confidence_score": r.get("confidence_score", 0.0),
                        "risk_level": r.get("risk_level", "中等"),
                        "key_points": r.get("key_points", []),
                        "execution_time": r.get("execution_time", 0),
                        "tokens_used": r.get("tokens_used", 0),
                        "analysts": r.get("analysts", []),
                        "research_depth": r.get("research_depth", "快速"),
                        "reports": r.get("reports", {}),
                        "state": r.get("state", {}),
                        "detailed_analysis": r.get("detailed_analysis", {}),
                        "created_at": tasks_doc.get("created_at"),
                        "updated_at": tasks_doc.get("completed_at"),
                        "status": r.get("status", "completed"),
                        "decision": r.get("decision", {}),
                        "source": "analysis_tasks",  # 数据来源标记
                    }

            # [修复 Bug #6] 所有 fallback 均失败时返回明确错误状态
            if not result_data:
                logger.warning(f"❌ [RESULT] 所有数据源都未找到结果: {task_id}")
                return {
                    "success": False,
                    "status": "not_found",
                    "message": "分析结果尚未生成或已过期",
                    "task_id": task_id,
                }

        if not result_data:
            raise HTTPException(status_code=404, detail="分析结果不存在")

        # 处理reports字段 - 如果没有reports字段，优先尝试从文件系统加载，其次从state中提取
        if "reports" not in result_data or not result_data["reports"]:
            import os
            from pathlib import Path

            stock_symbol = result_data.get("stock_symbol") or result_data.get("stock_code")
            # analysis_date 可能是日期或时间戳字符串，这里只取日期部分
            analysis_date_raw = result_data.get("analysis_date")
            analysis_date = str(analysis_date_raw)[:10] if analysis_date_raw else None

            loaded_reports = {}
            try:
                # 1) 尝试从环境变量 TRADINGAGENTS_RESULTS_DIR 指定的位置读取
                base_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
                project_root = Path.cwd()
                if base_env:
                    base_path = Path(base_env)
                    if not base_path.is_absolute():
                        base_path = project_root / base_env
                else:
                    base_path = project_root / "results"

                candidate_dirs = []
                if stock_symbol and analysis_date:
                    candidate_dirs.append(base_path / stock_symbol / analysis_date / "reports")
                # 2) 兼容其他保存路径
                if stock_symbol and analysis_date:
                    candidate_dirs.append(
                        project_root / "data" / "analysis_results" / stock_symbol / analysis_date / "reports",
                    )
                    candidate_dirs.append(
                        project_root
                        / "data"
                        / "analysis_results"
                        / "detailed"
                        / stock_symbol
                        / analysis_date
                        / "reports",
                    )

                for d in candidate_dirs:
                    if d.exists() and d.is_dir():
                        for f in d.glob("*.md"):
                            try:
                                content = f.read_text(encoding="utf-8")
                                if content and content.strip():
                                    loaded_reports[f.stem] = content.strip()
                            except Exception:
                                logger.warning("加载报告文件失败，跳过", exc_info=True)
                if loaded_reports:
                    result_data["reports"] = loaded_reports
                    # 若 summary / recommendation 缺失，尝试从同名报告补全
                    if not result_data.get("summary") and loaded_reports.get("summary"):
                        result_data["summary"] = loaded_reports.get("summary")
                    if not result_data.get("recommendation") and loaded_reports.get("recommendation"):
                        result_data["recommendation"] = loaded_reports.get("recommendation")
                    logger.info(
                        f"📁 [RESULT] 从文件系统加载到 {len(loaded_reports)} 个报告: {list(loaded_reports.keys())}",
                    )
            except Exception as fs_err:
                logger.warning(f"⚠️ [RESULT] 从文件系统加载报告失败: {fs_err}")

            # [HPC-DIAG] 诊断：reports为空时的 fallback 提取路径
            if "reports" not in result_data or not result_data["reports"]:
                logger.info("📊 [RESULT] reports字段缺失，尝试从state中提取")
                logger.info(
                    f"[HPC-DIAG] result_data keys={list(result_data.keys())}, source={result_data.get('source', 'N/A')}",
                )
                logger.info(f"[HPC-DIAG] result_data含state字段={'state' in result_data}")
                logger.info(
                    f"[HPC-DIAG] mongo_result has reports keys: {list(result_data.get('reports', {}).keys()) if result_data.get('reports') else 'NO_REPORTS'}",
                )

                # 从state中提取报告内容
                reports = {}
                state = result_data.get("state", {})
                logger.info(
                    f"[HPC-DIAG] state type={type(state).__name__}, is_dict={isinstance(state, dict)}, len keys={len(state) if isinstance(state, dict) else 'N/A'}",
                )
                if isinstance(state, dict):
                    logger.info(f"[HPC-DIAG] state keys={list(state.keys())}")
                    logger.info(f"[HPC-DIAG] state含hpc_state={'hpc_state' in state}")
                    if "hpc_state" in state:
                        hs = state["hpc_state"]
                        logger.info(
                            f"[HPC-DIAG] state['hpc_state'] type={type(hs).__name__}, has_to_dict={hasattr(hs, 'to_dict')}",
                        )
                elif hasattr(state, "hpc_state"):
                    logger.info("[HPC-DIAG] state对象含hpc_state属性")

                if isinstance(state, dict):
                    # 定义所有可能的报告字段
                    report_fields = [
                        "market_report",
                        "sentiment_report",
                        "news_report",
                        "fundamentals_report",
                        "investment_plan",
                        "trader_investment_plan",
                        "final_trade_decision",
                    ]

                    # 从state中提取报告内容
                    for field in report_fields:
                        value = state.get(field, "")
                        if isinstance(value, str) and len(value.strip()) > 10:
                            reports[field] = value.strip()

                    # 处理研究团队辩论状态报告
                    investment_debate_state = state.get("investment_debate_state", {})
                    if isinstance(investment_debate_state, dict):
                        # 提取多头研究员历史
                        bull_content = investment_debate_state.get("bull_history", "")
                        if isinstance(bull_content, str) and len(bull_content.strip()) > 10:
                            reports["bull_researcher"] = bull_content.strip()

                        # 提取空头研究员历史
                        bear_content = investment_debate_state.get("bear_history", "")
                        if isinstance(bear_content, str) and len(bear_content.strip()) > 10:
                            reports["bear_researcher"] = bear_content.strip()

                        # 提取研究经理决策
                        judge_decision = investment_debate_state.get("judge_decision", "")
                        if isinstance(judge_decision, str) and len(judge_decision.strip()) > 10:
                            reports["research_team_decision"] = judge_decision.strip()

                    # 处理风险管理团队辩论状态报告
                    risk_debate_state = state.get("risk_debate_state", {})
                    if isinstance(risk_debate_state, dict):
                        # 提取激进分析师历史
                        risky_content = risk_debate_state.get("risky_history", "")
                        if isinstance(risky_content, str) and len(risky_content.strip()) > 10:
                            reports["risky_analyst"] = risky_content.strip()

                        # 提取保守分析师历史
                        safe_content = risk_debate_state.get("safe_history", "")
                        if isinstance(safe_content, str) and len(safe_content.strip()) > 10:
                            reports["safe_analyst"] = safe_content.strip()

                        # 提取中性分析师历史
                        neutral_content = risk_debate_state.get("neutral_history", "")
                        if isinstance(neutral_content, str) and len(neutral_content.strip()) > 10:
                            reports["neutral_analyst"] = neutral_content.strip()

                        # 提取投资组合经理决策
                        risk_decision = risk_debate_state.get("judge_decision", "")
                        if isinstance(risk_decision, str) and len(risk_decision.strip()) > 10:
                            reports["risk_management_decision"] = risk_decision.strip()
                    # 🔄 HPC-Loop 三轮改造报告提取
                    hpc_reports = _extract_hpc_reports(state)
                    if hpc_reports:
                        reports.update(hpc_reports)
                        logger.info(f"🔄 [HPC] 合并了 {len(hpc_reports)} 个HPC报告到reports")

                    logger.info(f"📊 [RESULT] 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")
                    result_data["reports"] = reports
                else:
                    logger.warning(f"⚠️ [RESULT] state字段不是字典类型: {type(state)}")

        # 确保reports字段中的所有内容都是字符串类型
        if result_data.get("reports"):
            reports = result_data["reports"]
            if isinstance(reports, dict):
                # 确保每个报告内容都是字符串且不为空
                cleaned_reports = {}
                for key, value in reports.items():
                    if isinstance(value, str) and value.strip():
                        # 确保字符串不为空
                        cleaned_reports[key] = value.strip()
                    elif value is not None:
                        # 如果不是字符串，转换为字符串
                        str_value = str(value).strip()
                        if str_value:  # 只保存非空字符串
                            cleaned_reports[key] = str_value
                    # 如果value为None或空字符串，则跳过该报告

                result_data["reports"] = cleaned_reports
                logger.info(f"📊 [RESULT] 清理reports字段，包含 {len(cleaned_reports)} 个有效报告")

                # 如果清理后没有有效报告，设置为空字典
                if not cleaned_reports:
                    logger.warning("⚠️ [RESULT] 清理后没有有效报告")
                    result_data["reports"] = {}
            else:
                logger.warning(f"⚠️ [RESULT] reports字段不是字典类型: {type(reports)}")
                result_data["reports"] = {}

        # 补全关键字段：recommendation/summary/key_points
        try:
            reports = result_data.get("reports", {}) or {}
            decision = result_data.get("decision", {}) or {}

            # recommendation 优先使用决策摘要或报告中的决策
            if not result_data.get("recommendation"):
                rec_candidates = []
                if isinstance(decision, dict) and decision.get("action"):
                    parts = [
                        f"操作: {decision.get('action')}",
                        f"目标价: {decision.get('target_price')}" if decision.get("target_price") else None,
                        f"置信度: {decision.get('confidence')}" if decision.get("confidence") is not None else None,
                    ]
                    rec_candidates.append("；".join([p for p in parts if p]))
                # 从报告中兜底
                for k in ["final_trade_decision", "investment_plan"]:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 10:
                        rec_candidates.append(v.strip())
                if rec_candidates:
                    # 取最有信息量的一条（最长）
                    result_data["recommendation"] = max(rec_candidates, key=len)[:2000]

            # summary 从若干报告拼接生成
            if not result_data.get("summary"):
                sum_candidates = []
                for k in ["market_report", "fundamentals_report", "sentiment_report", "news_report"]:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 50:
                        sum_candidates.append(v.strip())
                if sum_candidates:
                    result_data["summary"] = ("\n\n".join(sum_candidates))[:3000]

            # key_points 兜底
            if not result_data.get("key_points"):
                kp = []
                if isinstance(decision, dict):
                    if decision.get("action"):
                        kp.append(f"操作建议: {decision.get('action')}")
                    if decision.get("target_price"):
                        kp.append(f"目标价: {decision.get('target_price')}")
                    if decision.get("confidence") is not None:
                        kp.append(f"置信度: {decision.get('confidence')}")
                # 从reports中截取前几句作为要点
                for k in ["investment_plan", "final_trade_decision"]:
                    v = reports.get(k)
                    if isinstance(v, str) and len(v.strip()) > 10:
                        kp.append(v.strip()[:120])
                if kp:
                    result_data["key_points"] = kp[:5]
        except Exception as fill_err:
            logger.warning(f"⚠️ [RESULT] 补全关键字段时出错: {fill_err}")

        # 进一步兜底：从 detailed_analysis 推断并补全
        try:
            if (
                not result_data.get("summary")
                or not result_data.get("recommendation")
                or not result_data.get("reports")
            ):
                da = result_data.get("detailed_analysis")
                # 若reports仍为空，放入一份原始详细分析，便于前端“查看报告详情”
                if (not result_data.get("reports")) and isinstance(da, str) and len(da.strip()) > 20:
                    result_data["reports"] = {"detailed_analysis": da.strip()}
                elif (not result_data.get("reports")) and isinstance(da, dict) and da:
                    # 将字典的长文本项放入reports
                    extracted = {}
                    for k, v in da.items():
                        if isinstance(v, str) and len(v.strip()) > 20:
                            extracted[k] = v.strip()
                    if extracted:
                        result_data["reports"] = extracted

                # 补 summary
                if not result_data.get("summary"):
                    if isinstance(da, str) and da.strip():
                        result_data["summary"] = da.strip()[:3000]
                    elif isinstance(da, dict) and da:
                        # 取最长的文本作为摘要
                        texts = [v.strip() for v in da.values() if isinstance(v, str) and v.strip()]
                        if texts:
                            result_data["summary"] = max(texts, key=len)[:3000]

                # 补 recommendation
                if not result_data.get("recommendation"):
                    rec = None
                    if isinstance(da, str):
                        # 简单基于关键字提取包含“建议”的段落
                        import re

                        m = re.search(r"(投资建议|建议|结论)[:：]?\s*(.+)", da)
                        if m:
                            rec = m.group(0)
                    elif isinstance(da, dict):
                        for key in ["final_trade_decision", "investment_plan", "结论", "建议"]:
                            v = da.get(key)
                            if isinstance(v, str) and len(v.strip()) > 10:
                                rec = v.strip()
                                break
                    if rec:
                        result_data["recommendation"] = rec[:2000]
        except Exception as da_err:
            logger.warning(f"⚠️ [RESULT] 从detailed_analysis补全失败: {da_err}")

        # 严格的数据格式化和验证
        def safe_string(value, default=""):
            """安全地转换为字符串"""
            if value is None:
                return default
            if isinstance(value, str):
                return value
            return str(value)

        def safe_number(value, default=0):
            """安全地转换为数字"""
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return value
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_list(value, default=None):
            """安全地转换为列表"""
            if default is None:
                default = []
            if value is None:
                return default
            if isinstance(value, list):
                return value
            return default

        def safe_dict(value, default=None):
            """安全地转换为字典"""
            if default is None:
                default = {}
            if value is None:
                return default
            if isinstance(value, dict):
                return value
            return default

        # 🔍 调试：检查最终构建前的result_data
        logger.info(f"🔍 [FINAL] 构建最终结果前，result_data键: {list(result_data.keys())}")
        logger.info(f"🔍 [FINAL] result_data中有decision: {bool(result_data.get('decision'))}")
        if result_data.get("decision"):
            logger.info(f"🔍 [FINAL] decision内容: {result_data['decision']}")

        # 构建严格验证的结果数据
        final_result_data = {
            "analysis_id": safe_string(result_data.get("analysis_id"), "unknown"),
            "stock_symbol": safe_string(result_data.get("stock_symbol"), "UNKNOWN"),
            "stock_code": safe_string(result_data.get("stock_code"), "UNKNOWN"),
            "stock_name": safe_string(
                result_data.get("stock_name"), safe_string(result_data.get("stock_symbol"), "UNKNOWN"),
            ),
            "analysis_date": safe_string(result_data.get("analysis_date"), "2025-08-20"),
            "summary": safe_string(result_data.get("summary"), "分析摘要暂无"),
            "recommendation": safe_string(result_data.get("recommendation"), "投资建议暂无"),
            "confidence_score": safe_number(result_data.get("confidence_score"), 0.0),
            "risk_level": safe_string(result_data.get("risk_level"), "中等"),
            "key_points": safe_list(result_data.get("key_points")),
            "execution_time": safe_number(result_data.get("execution_time"), 0),
            "tokens_used": safe_number(result_data.get("tokens_used"), 0),
            "analysts": safe_list(result_data.get("analysts")),
            "research_depth": safe_string(result_data.get("research_depth"), "快速"),
            "detailed_analysis": safe_dict(result_data.get("detailed_analysis")),
            "state": safe_dict(result_data.get("state")),
            # 🔥 关键修复：添加decision字段！
            "decision": safe_dict(result_data.get("decision")),
        }

        # 特别处理reports字段 - 确保每个报告都是有效字符串
        reports_data = safe_dict(result_data.get("reports"))
        validated_reports = {}

        for report_key, report_content in reports_data.items():
            # 确保报告键是字符串
            safe_key = safe_string(report_key, "unknown_report")

            # 确保报告内容是非空字符串
            if report_content is None:
                validated_content = "报告内容暂无"
            elif isinstance(report_content, str):
                validated_content = report_content.strip() if report_content.strip() else "报告内容为空"
            else:
                validated_content = str(report_content).strip() if str(report_content).strip() else "报告内容格式错误"

            validated_reports[safe_key] = validated_content

        final_result_data["reports"] = validated_reports

        # ===== 三轮改造启用状态标记 =====
        hpc_reports = validated_reports

        # 🔧 [Bug Fix] 从 state.hpc_state.enabled_features 获取实际模块启用状态
        # 此前仅依赖报告键存在性判断，但分析未执行到特定模块时报告键不存在，
        # 导致 modules_enabled 显示为 false，与实际配置值不符。
        try:
            state = result_data.get("state", {})
            ef = {}
            if isinstance(state, dict):
                hs = state.get("hpc_state")
                if hs is not None:
                    if isinstance(hs, dict):
                        ef = hs.get("enabled_features", {})
                    elif hasattr(hs, "enabled_features"):
                        ef = getattr(hs, "enabled_features", {})
        except Exception:
            ef = {}

        logger.info(f"[HPC] modules_enabled - hpc_reports keys: {list(hpc_reports.keys())}")
        logger.info(f"[HPC] modules_enabled - enabled_features: {ef}")

        final_result_data["modules_enabled"] = {
            # hpc_loop: 有HPC报告 或 enabled_features 非空
            "hpc_loop": any(k.startswith("hpc_") for k in hpc_reports) or bool(ef),
            # l_iwm: 有报告 或 enabled_features 中有 l_iwm 相关标记
            "l_iwm": "l_iwm_report" in hpc_reports or ef.get("l_iwm_enabled", False) or ef.get("l_iwm_rssm", False),
            # hsrc_mc: 有报告 或 enabled_features 中有 hsrc_mc 标记
            "hsrc_mc": "hsrc_mc_report" in hpc_reports
            or ef.get("hsrc_mc_enabled", False)
            or ef.get("hsrc_mc_initialized", False),
            # aif_engine: 有报告 或 enabled_features 中有 aif 标记
            "aif_engine": "aif_report" in hpc_reports or ef.get("aif_engine", False),
            # diffusion: 独立模块，使用报告键检测 + state顶层字段检测
            "diffusion": "diffusion_report" in hpc_reports or bool(ef.get("diffusion", False)),
        }

        # 融合模式标记
        try:
            state = result_data.get("state", {})
            if isinstance(state, dict):
                final_result_data["fusion_mode"] = bool(state.get("fusion_mode", False))
            else:
                final_result_data["fusion_mode"] = False
        except Exception:
            final_result_data["fusion_mode"] = False

        # 性能统计
        try:
            state = result_data.get("state", {})
            if isinstance(state, dict) and "performance_metrics" in state:
                perf_metrics = state["performance_metrics"]
                final_result_data["performance_summary"] = {
                    "total_nodes": len(perf_metrics) if isinstance(perf_metrics, (dict, list)) else 0,
                    "node_times": perf_metrics,
                }
        except Exception as e:
            logger.warning(f"[RESULT] 性能指标提取失败: {e}")

        # ===== 模块贡献度分析 =====
        try:
            state = result_data.get("state", {})
            fused = state.get("fused_decision", {}) if isinstance(state, dict) else {}
            diff_decision = state.get("diffusion_decision", {}) if isinstance(state, dict) else {}
            trader_plan = state.get("trader_investment_plan", "") if isinstance(state, dict) else ""
            hpc_reports_exist = any(k.startswith("hpc_") for k in final_result_data.get("reports", {}))
            aif_reports_exist = "aif_report" in final_result_data.get("reports", {})
            diff_confidence = diff_decision.get("confidence", 0.0) if isinstance(diff_decision, dict) else 0.0
            diff_weight = diff_decision.get("weight", 0.0) if isinstance(diff_decision, dict) else 0.0
            fusion_weight = fused.get("fusion_weight", 0.0) if isinstance(fused, dict) else 0.0
            fusion_source = fused.get("source", "unknown") if isinstance(fused, dict) else "unknown"
            final_result_data["module_contributions"] = {
                "trader": {"active": bool(trader_plan), "contribution": 1.0 - fusion_weight,
                           "source": "bull_bear_debate"},
                "diffusion": {"active": diff_confidence > 0, "contribution": fusion_weight,
                              "confidence": diff_confidence, "source": diff_decision.get("source", "unknown")},
                "hpc_loop": {"active": hpc_reports_exist, "contribution": 0.0 if not hpc_reports_exist else 0.1,
                             "source": "rssm_world_model"},
                "aif_engine": {"active": aif_reports_exist, "contribution": 0.0 if not aif_reports_exist else 0.1,
                               "source": "active_inference"},
                "fusion_mode": fusion_source,
            }
        except Exception as e:
            logger.warning(f"[RESULT] 模块贡献度分析失败: {e}")
            final_result_data["module_contributions"] = {}

        logger.info(f"✅ [RESULT] 成功获取任务结果: {task_id}")
        logger.info(f"📊 [RESULT] 最终返回 {len(final_result_data.get('reports', {}))} 个报告")

        # 🔍 调试：检查最终返回的数据
        logger.info(f"🔍 [FINAL] 最终返回数据键: {list(final_result_data.keys())}")
        logger.info(f"🔍 [FINAL] 最终返回中有decision: {bool(final_result_data.get('decision'))}")
        if final_result_data.get("decision"):
            logger.info(f"🔍 [FINAL] 最终decision内容: {final_result_data['decision']}")

        return {"success": True, "data": final_result_data, "message": "分析结果获取成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [RESULT] 获取任务结果失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/all", response_model=dict[str, Any])
async def list_all_tasks(
    user: dict = Depends(get_current_user),
    status: str | None = Query(None, description="任务状态过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取所有任务列表（不限用户）"""
    try:
        logger.info("📋 查询所有任务列表")

        tasks = await get_simple_analysis_service().list_all_tasks(status_filter=status, limit=limit, skip=offset)

        return {
            "success": True,
            "data": {"tasks": tasks, "total": len(tasks), "limit": limit, "offset": offset},
            "message": "任务列表获取成功",
        }

    except Exception as e:
        logger.error(f"❌ 获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", response_model=dict[str, Any])
async def list_user_tasks(
    user: dict = Depends(get_current_user),
    status: str | None = Query(None, description="任务状态过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取用户的任务列表"""
    try:
        logger.info(f"📋 查询用户任务列表: {user['id']}")

        tasks = await get_simple_analysis_service().list_user_tasks(
            user_id=user["id"], status_filter=status, limit=limit, skip=offset,
        )

        return {
            "success": True,
            "data": {"tasks": tasks, "total": len(tasks), "limit": limit, "offset": offset},
            "message": "任务列表获取成功",
        }

    except Exception as e:
        logger.error(f"❌ 获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=dict[str, Any])
async def submit_batch_analysis(request: BatchAnalysisRequest, user: dict = Depends(get_current_user)):
    """提交批量分析任务（真正的并发执行）

    ⚠️ 注意：不使用 BackgroundTasks，因为它是串行执行的！
    改用 asyncio.create_task 实现真正的并发执行。
    """
    try:
        logger.info(f"🎯 [批量分析] 收到批量分析请求: title={request.title}")

        simple_service = get_simple_analysis_service()
        batch_id = str(uuid.uuid4())
        task_ids: list[str] = []
        mapping: list[dict[str, str]] = []

        # 获取股票代码列表 (兼容旧字段)
        stock_symbols = request.get_symbols()
        logger.info(f"📊 [批量分析] 股票代码列表: {stock_symbols}")

        # 验证股票代码列表
        if not stock_symbols:
            raise ValueError("股票代码列表不能为空")

        # 🔧 限制批量分析的股票数量（最多10个）
        MAX_BATCH_SIZE = 10
        if len(stock_symbols) > MAX_BATCH_SIZE:
            raise ValueError(f"批量分析最多支持 {MAX_BATCH_SIZE} 个股票，当前提交了 {len(stock_symbols)} 个")

        # 为每只股票创建单股分析任务
        for i, symbol in enumerate(stock_symbols):
            logger.info(f"📝 [批量分析] 正在创建第 {i + 1}/{len(stock_symbols)} 个任务: {symbol}")

            single_req = SingleAnalysisRequest(
                symbol=symbol,
                stock_code=symbol,  # 兼容字段
                parameters=request.parameters,
            )

            try:
                create_res = await simple_service.create_analysis_task(user["id"], single_req)
                task_id = create_res.get("task_id")
                if not task_id:
                    raise RuntimeError(f"创建任务失败：未返回task_id (symbol={symbol})")
                task_ids.append(task_id)
                mapping.append({"symbol": symbol, "stock_code": symbol, "task_id": task_id})
                logger.info(f"✅ [批量分析] 已创建任务: {task_id} - {symbol}")
            except Exception as create_error:
                logger.error(f"❌ [批量分析] 创建任务失败: {symbol}, 错误: {create_error}", exc_info=True)
                raise

        # 🔧 使用 asyncio.Semaphore 限制并发数（最多10个并发），避免线程池队列积压和 MongoDB/Redis 连接池耗尽
        # 🐛 [BUG-018] 从 3 提升至 10，与 _thread_pool max_workers 一致
        semaphore = asyncio.Semaphore(10)

        # 🔧 使用 asyncio.create_task 实现真正的并发执行
        # 不使用 BackgroundTasks，因为它是串行执行的
        async def run_concurrent_analysis():
            """并发执行所有分析任务（受 Semaphore 限制）"""
            tasks = []
            for i, symbol in enumerate(stock_symbols):
                task_id = task_ids[i]
                single_req = SingleAnalysisRequest(symbol=symbol, stock_code=symbol, parameters=request.parameters)

                # 创建异步任务，使用 Semaphore 限制并发
                async def run_single_analysis(tid: str, req: SingleAnalysisRequest, uid: str):
                    async with semaphore:
                        try:
                            logger.info(f"🚀 [并发任务] 开始执行: {tid} - {req.stock_code}")
                            # [FIX] 2026-06-18: 超时从 1800s 延长至 3600s，与常量 ANALYSIS_TIMEOUT 保持一致
                            await asyncio.wait_for(
                                simple_service.execute_analysis_background(tid, uid, req),
                                timeout=3600,  # 60分钟总超时，防止单个任务卡死
                            )
                            logger.info(f"✅ [并发任务] 执行完成: {tid}")
                        except asyncio.TimeoutError:
                            logger.error(f"❌ [并发任务] 执行超时: {tid} (3600s)")
                        except Exception as e:
                            logger.error(f"❌ [并发任务] 执行失败: {tid}, 错误: {e}", exc_info=True)

                # 添加到任务列表
                task = asyncio.create_task(run_single_analysis(task_id, single_req, user["id"]))
                tasks.append(task)
                logger.info(f"✅ [批量分析] 已创建并发任务: {task_id} - {symbol}")

            # 等待所有任务完成（不阻塞响应）
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"🎉 [批量分析] 所有任务执行完成: batch_id={batch_id}")

        # 在后台启动并发任务（不等待完成）
        asyncio.create_task(run_concurrent_analysis())
        logger.info(f"🚀 [批量分析] 已启动 {len(task_ids)} 个并发任务")

        return {
            "success": True,
            "data": {
                "batch_id": batch_id,
                "total_tasks": len(task_ids),
                "task_ids": task_ids,
                "mapping": mapping,
                "status": "submitted",
            },
            "message": f"批量分析任务已提交，共{len(task_ids)}个股票，正在并发执行",
        }
    except Exception as e:
        logger.error(f"❌ [批量分析] 提交失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


# 兼容性：保留原有端点
@router.post("/analyze")
async def analyze_single(
    req: SingleAnalyzeRequest, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service),
):
    """单股分析（兼容性端点）"""
    try:
        task_id = await svc.enqueue_task(user_id=user["id"], symbol=req.symbol, params=req.parameters)
        return {"task_id": task_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analyze/batch")
async def analyze_batch(
    req: BatchAnalyzeRequest, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service),
):
    """批量分析（兼容性端点）"""
    try:
        batch_id, submitted = await svc.create_batch(user_id=user["id"], symbols=req.symbols, params=req.parameters)
        return {"batch_id": batch_id, "submitted": submitted}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service),
):
    b = await svc.get_batch(batch_id)
    if not b or b.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="batch not found")
    return b


# 任务和批次查询端点
# 注意：这个路由被移到了 /tasks/{task_id}/status 之后，避免路由冲突
# @router.get("/tasks/{task_id}")
# async def get_task(
#     task_id: str,
#     user: dict = Depends(get_current_user),
#     svc: QueueService = Depends(get_queue_service)
# ):
#     """获取任务详情"""
#     t = await svc.get_task(task_id)
#     if not t or t.get("user") != user["id"]:
#         raise HTTPException(status_code=404, detail="任务不存在")
#     return t

# 原有的路由已被新的异步实现替代
# @router.get("/tasks/{task_id}/status")
# async def get_task_status_old(
#     task_id: str,
#     user: dict = Depends(get_current_user)
# ):
#     """获取任务状态和进度（旧版实现）"""
#     try:
#         status = await get_analysis_service().get_task_status(task_id)
#         if not status:
#             raise HTTPException(status_code=404, detail="任务不存在")
#         return {
#             "success": True,
#             "data": status
#         }
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, user: dict = Depends(get_current_user)):
    """取消任务（使用 SimpleAnalysisService 的线程安全取消机制）"""
    try:
        # 使用 SimpleAnalysisService 的取消机制
        svc = get_simple_analysis_service()

        # 验证任务所有权
        task = await svc.get_task_status(task_id)
        if not task or task.get("user_id") != user["id"]:
            raise HTTPException(status_code=404, detail="任务不存在")

        success = await svc.cancel_task(task_id)
        if success:
            return {"success": True, "message": "任务已取消"}
        raise HTTPException(status_code=400, detail="取消任务失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user/queue-status")
async def get_user_queue_status(user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    """获取用户队列状态"""
    try:
        status = await svc.get_user_queue_status(user["id"])
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user/history")
async def get_user_analysis_history(
    user: dict = Depends(get_current_user),
    status: str | None = Query(None, description="任务状态过滤"),
    start_date: str | None = Query(None, description="开始日期，YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期，YYYY-MM-DD"),
    symbol: str | None = Query(None, description="股票代码"),
    stock_code: str | None = Query(None, description="股票代码(已废弃,使用symbol)"),
    market_type: str | None = Query(None, description="市场类型"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
):
    """获取用户分析历史（支持基础筛选与分页）"""
    try:
        # 先获取用户任务列表（内存优先，MongoDB兜底）
        raw_tasks = await get_simple_analysis_service().list_user_tasks(
            user_id=user["id"], status_filter=status, limit=page_size, offset=(page - 1) * page_size,
        )

        # 进行基础筛选
        from datetime import datetime

        def in_date_range(t: str | None) -> bool:
            if not t:
                return True
            try:
                dt = datetime.fromisoformat(t.replace("Z", "+00:00")) if "Z" in t else datetime.fromisoformat(t)
            except Exception:
                return True
            ok = True
            if start_date:
                try:
                    ok = ok and (dt.date() >= datetime.fromisoformat(start_date).date())
                except Exception:
                    logger.debug("日期过滤解析失败，不应用该条件")
            if end_date:
                try:
                    ok = ok and (dt.date() <= datetime.fromisoformat(end_date).date())
                except Exception:
                    logger.debug("日期过滤解析失败，不应用该条件")
            return ok

        # 获取查询的股票代码 (兼容旧字段)
        query_symbol = symbol or stock_code

        filtered = []
        for x in raw_tasks:
            if query_symbol:
                task_symbol = x.get("symbol") or x.get("stock_code") or x.get("stock_symbol")
                if task_symbol not in [query_symbol]:
                    continue
            # 市场类型暂时从参数内判断（如有）
            if market_type:
                params = x.get("parameters") or {}
                if params.get("market_type") != market_type:
                    continue
            # 时间范围（使用 start_time 或 created_at）
            t = x.get("start_time") or x.get("created_at")
            if not in_date_range(t):
                continue
            filtered.append(x)

        return {
            "success": True,
            "data": {"tasks": filtered, "total": len(filtered), "page": page, "page_size": page_size},
            "message": "历史查询成功",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# WebSocket 端点
@router.websocket("/ws/task/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str, token: str = Query(...)):
    """WebSocket 端点：实时获取任务进度

    [BUG-2 FIX] 添加 JWT token 验证
    客户端连接: ws://localhost:8000/api/analysis/ws/task/<task_id>?token=<jwt_token>
    """
    import asyncio
    import json

    from app.services.auth_service import AuthService

    websocket_manager = get_websocket_manager()

    # ✋ [BUG-2 FIX] 验证 JWT token
    token_data = AuthService.verify_token(token)
    if not token_data:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    async def heartbeat_sender():
        """🐛 Bug #20: 定时发送心跳 ping，检测连接存活"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒发送一次心跳
                if not await websocket_manager.send_ping(websocket):
                    logger.warning(f"⚠️ WebSocket 心跳发送失败: {task_id}")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"⚠️ WebSocket 心跳异常: {e}")
                break

    try:
        await websocket_manager.connect(websocket, task_id)

        # 发送连接确认消息
        await websocket.send_text(
            json.dumps({"type": "connection_established", "task_id": task_id, "message": "WebSocket 连接已建立"}),
        )

        # 🐛 Bug #20: 启动后台心跳发送任务
        heartbeat_task = asyncio.create_task(heartbeat_sender())

        try:
            # 保持连接活跃
            while True:
                try:
                    # 接收客户端消息（包括 pong 响应）
                    data = await websocket.receive_text()
                    msg = json.loads(data)
                    # 🐛 Bug #20: 处理客户端 pong 响应
                    if msg.get("type") == "pong":
                        logger.debug(f"📡 收到 WebSocket pong: {task_id}")
                    else:
                        logger.debug(f"📡 收到 WebSocket 消息: {data[:100]}")
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.warning(f"⚠️ WebSocket 消息处理错误: {e}")
                    break
        finally:
            # 🐛 Bug #20: 取消心跳任务
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                logger.debug("心跳任务已取消（正常清理）")

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 客户端断开连接: {task_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket 连接错误: {e}")
    finally:
        await websocket_manager.disconnect(websocket, task_id)


# 任务详情查询路由（放在最后避免与 /tasks/{task_id}/status 冲突）
@router.get("/tasks/{task_id}/details")
async def get_task_details(
    task_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service),
):
    """获取任务详情（使用不同的路径避免冲突）"""
    t = await svc.get_task(task_id)
    if not t or t.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    return t


# ==================== 僵尸任务管理 ====================


@router.get("/admin/zombie-tasks")
async def get_zombie_tasks(
    max_running_hours: int = Query(default=2, ge=1, le=72, description="最大运行时长（小时）"),
    user: dict = Depends(get_current_user),
):
    """获取僵尸任务列表（仅管理员）

    僵尸任务：长时间处于 processing/running/pending 状态的任务
    """
    # 检查管理员权限
    if user.get("username") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    try:
        svc = get_simple_analysis_service()
        zombie_tasks = await svc.get_zombie_tasks(max_running_hours)

        return {
            "success": True,
            "data": zombie_tasks,
            "total": len(zombie_tasks),
            "max_running_hours": max_running_hours,
        }
    except Exception as e:
        logger.error(f"❌ 获取僵尸任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取僵尸任务失败: {e!s}")


@router.post("/admin/cleanup-zombie-tasks")
async def cleanup_zombie_tasks(
    max_running_hours: int = Query(default=2, ge=1, le=72, description="最大运行时长（小时）"),
    user: dict = Depends(get_current_user),
):
    """清理僵尸任务（仅管理员）

    将长时间处于 processing/running/pending 状态的任务标记为失败
    """
    # 检查管理员权限
    if user.get("username") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    try:
        svc = get_simple_analysis_service()
        result = await svc.cleanup_zombie_tasks(max_running_hours)

        return {"success": True, "data": result, "message": f"已清理 {result.get('total_cleaned', 0)} 个僵尸任务"}
    except Exception as e:
        logger.error(f"❌ 清理僵尸任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理僵尸任务失败: {e!s}")


@router.post("/tasks/{task_id}/mark-failed")
async def mark_task_as_failed(task_id: str, user: dict = Depends(get_current_user)):
    """将指定任务标记为失败

    用于手动清理卡住的任务
    """
    try:
        svc = get_simple_analysis_service()

        # 更新内存中的任务状态
        from app.services.memory_state_manager import TaskStatus

        await svc.memory_manager.update_task_status(
            task_id=task_id, status=TaskStatus.FAILED, message="手动标记为失败", error_message="用户手动标记为失败",
        )

        # 更新 MongoDB 中的任务状态
        from datetime import datetime

        from app.core.database import get_mongo_db

        db = get_mongo_db()

        result = await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "failed",
                    "last_error": "用户手动标记为失败",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            },
        )

        if result.modified_count > 0:
            logger.info(f"✅ 任务 {task_id} 已标记为失败")
            return {"success": True, "message": "任务已标记为失败"}
        logger.warning(f"⚠️ 任务 {task_id} 未找到或已是失败状态")
        return {"success": True, "message": "任务未找到或已是失败状态"}
    except Exception as e:
        logger.error(f"❌ 标记任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"标记任务失败: {e!s}")


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    """删除指定任务

    从内存和数据库中删除任务记录
    """
    try:
        svc = get_simple_analysis_service()

        # 从内存中删除任务
        await svc.memory_manager.remove_task(task_id)

        # 从 MongoDB 中删除任务
        from app.core.database import get_mongo_db

        db = get_mongo_db()

        result = await db.analysis_tasks.delete_one({"task_id": task_id})

        if result.deleted_count > 0:
            logger.info(f"✅ 任务 {task_id} 已删除")
            return {"success": True, "message": "任务已删除"}
        logger.warning(f"⚠️ 任务 {task_id} 未找到")
        return {"success": True, "message": "任务未找到"}
    except Exception as e:
        logger.error(f"❌ 删除任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {e!s}")
