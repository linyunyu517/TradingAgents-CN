"""
简化的股票分析服务
直接调用现有的 TradingAgents 分析功能
"""

import asyncio
import atexit
import concurrent.futures
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# RUNTIME-060: 线程安全的 sys.path 操作，避免并发导入时的竞争条件
_project_root_initialized = False
_project_root_lock = threading.Lock()

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
if not _project_root_initialized:
    with _project_root_lock:
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        _project_root_initialized = True

# 初始化TradingAgents日志系统
from tradingagents.utils.logging_init import init_logging

init_logging()

from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.analysis import AnalysisParameters, AnalysisStatus, AnalysisTask, SingleAnalysisRequest
from app.models.notification import NotificationCreate
from app.models.user import PyObjectId
from app.services.config_service import ConfigService
from app.services.memory_state_manager import TaskStatus, get_memory_state_manager
from app.services.progress.tracker import safe_serialize
from app.services.redis_progress_tracker import RedisProgressTracker
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import create_llm_client

# 股票基础信息获取（用于补充显示名称）
try:
    from tradingagents.dataflows.data_source_manager import get_data_source_manager

    _data_source_manager = get_data_source_manager()

    def _get_stock_info_safe(stock_code: str):
        """获取股票基础信息的安全封装"""
        return _data_source_manager.get_stock_basic_info(stock_code)
except Exception:
    _get_stock_info_safe = None

# ============================================================
# 内置股票名称映射表（数据源不可用时的降级方案）
# 捕获常见股票名称，减少对数据源的依赖
# [Bug Fix] 2026-06-18: 扩展内置映射表，覆盖更多常见股票
# ============================================================
STOCK_NAME_MAP = {
    # 上证指数
    # 白酒
    "600519": "贵州茅台",
    "000858": "五粮液",
    "600809": "山西汾酒",
    "000568": "泸州老窖",
    "002304": "洋河股份",
    "603369": "今世缘",
    "600559": "老白干酒",
    "603589": "口子窖",
    "600779": "水井坊",
    "000596": "古井贡酒",
    "603198": "迎驾贡酒",
    "600702": "舍得酒业",
    "600199": "金种子酒",
    "600059": "古越龙山",
    # 银行
    "601398": "工商银行",
    "601939": "建设银行",
    "601288": "农业银行",
    "601988": "中国银行",
    "600036": "招商银行",
    "601328": "交通银行",
    "601166": "兴业银行",
    "600016": "民生银行",
    "600000": "浦发银行",
    "601818": "光大银行",
    "601009": "南京银行",
    "600015": "华夏银行",
    "601169": "北京银行",
    "601229": "上海银行",
    "600919": "江苏银行",
    # 保险
    "601318": "中国平安",
    "601628": "中国人寿",
    "601601": "中国太保",
    "601336": "新华保险",
    "601319": "中国人保",
    # 券商
    "600030": "中信证券",
    "601211": "国泰君安",
    "601688": "华泰证券",
    "600837": "海通证券",
    "601881": "中国银河",
    "600999": "招商证券",
    "601066": "中信建投",
    "601878": "浙商证券",
    "601236": "红塔证券",
    "601162": "天风证券",
    # 地产
    "000002": "万科A",
    "600048": "保利发展",
    "001979": "招商蛇口",
    "600383": "金地集团",
    "600340": "华夏幸福",
    "000069": "华侨城A",
    "600325": "华发股份",
    "600606": "绿地控股",
    "002146": "荣盛发展",
    "000656": "金科股份",
    # 科技
    "000063": "中兴通讯",
    "002415": "海康威视",
    "000725": "京东方A",
    "600703": "三安光电",
    "603160": "汇顶科技",
    "002230": "科大讯飞",
    "300059": "东方财富",
    "002475": "立讯精密",
    "600276": "恒瑞医药",
    "300750": "宁德时代",
    "000333": "美的集团",
    "000651": "格力电器",
    "600690": "海尔智家",
    "002714": "牧原股份",
    "300498": "温氏股份",
    "601012": "隆基绿能",
    "600585": "海螺水泥",
    "601899": "紫金矿业",
    "600031": "三一重工",
    "002352": "顺丰控股",
    "600887": "伊利股份",
    "603288": "海天味业",
    "601888": "中国中免",
    "600309": "万华化学",
    "600104": "上汽集团",
    "000001": "平安银行",
    "002142": "宁波银行",
    "600438": "通威股份",
    "002129": "中环股份",
    "300274": "阳光电源",
    "000100": "TCL科技",
    "002241": "歌尔股份",
    "603259": "药明康德",
    "300015": "爱尔眼科",
    "002007": "华兰生物",
    "000538": "云南白药",
    # 旗滨集团（测试常用）
    "601636": "旗滨集团",
}

logger = logging.getLogger(__name__)

# 分析超时时间（秒）
ANALYSIS_TIMEOUT = 3600  # 60分钟

# ============================================================
# 连接池配置
# 最大并发分析任务数
MAX_WORKERS = 3

# [Bug 2 修复] 专用线程池用于执行 propagate（防止与主线程池嵌套死锁）
# _thread_pool 运行 _run_analysis_sync，而 _run_analysis_sync 内部
# 需要 submit propagate 到线程池。如果使用同一个池，当所有 worker 都在
# 等待 propagate_future.result() 时，没有线程可用执行 propagate，导致死锁。
# 因此使用独立线程池 _graph_pool 专门执行 propagate 调用。
MAX_GRAPH_WORKERS = 3
# ============================================================


def _extract_hpc_reports(state: Any) -> dict[str, str]:
    """
    从 state 中提取 HPC-Loop 三轮改造（HPC/L-IWM/HSR-MC）的报告内容。

    HPCState 被 `to_dict()` 序列化为 dict 后嵌入 LangGraph 的最终状态，
    字段包括: latent_state, last_prediction, last_prediction_error,
    workspace_contents, workspace_broadcast, candidate_actions,
    selected_action, causal_counterfactuals, memory_trace, current_episode,
    step_counter, enabled_features。

    此函数将其转换为人类可读的字符串报告，供 reports 字典使用。

    注意：hpc_state 在 LangGraph 节点执行期间会被 _ensure_hpc_state() 从 dict
    转换为 HPCState 对象，因此这里需要同时兼容 dict 和 HPCState 对象两种形式。
    """
    reports: dict[str, str] = {}

    # [HPC-DIAG] 增强诊断：记录调用栈和state详细状态
    import traceback

    caller_frame = traceback.extract_stack()[-3]  # caller of _extract_hpc_reports
    logger.info(
        f"[HPC-DIAG] _extract_hpc_reports 被调用: {caller_frame.filename}:{caller_frame.lineno} - {caller_frame.name}",
    )
    logger.info(
        f"[HPC-DIAG] state type={type(state).__name__}, isinstance_dict={isinstance(state, dict)}, dir={[x for x in dir(state) if not x.startswith('_')][:30] if not isinstance(state, dict) else 'N/A'}",
    )

    if isinstance(state, dict):
        logger.info(f"[HPC-DIAG] state keys={list(state.keys())}, len={len(state)}")
        logger.info(f"[HPC-DIAG] state含hpc_state={'hpc_state' in state}")
        if "hpc_state" in state:
            hs = state["hpc_state"]
            logger.info(f"[HPC-DIAG] state['hpc_state'] type={type(hs).__name__}, has_to_dict={hasattr(hs, 'to_dict')}")
        # 检查是否有hpc相关key
        for k in state:
            if "hpc" in str(k).lower() or "l_iwm" in str(k).lower() or "hsrc" in str(k).lower():
                logger.info(f"[HPC-DIAG] state中包含HPC相关key: {k}={type(state[k]).__name__}")
    elif hasattr(state, "hpc_state"):
        hs = state.hpc_state
        logger.info(f"[HPC-DIAG] state.hpc_state type={type(hs).__name__}, has_to_dict={hasattr(hs, 'to_dict')}")

    # 获取 hpc_state（兼容 dict 和 object 两种 state 类型）
    hpc_state = None
    if hasattr(state, "hpc_state"):
        hpc_state = state.hpc_state
    elif isinstance(state, dict) and "hpc_state" in state:
        hpc_state = state.get("hpc_state")

    if not hpc_state:
        logger.info("[HPC-EXTRACT] hpc_state is empty, skipping")
        return reports

    # ===== 兼容 HPCState 对象 → dict 转换 =====
    # hpc_state 在 HPC 节点执行期间被 _ensure_hpc_state() 从 dict 转换为
    # HPCState dataclass 对象。如果 final_state 未经过逆向序列化，
    # hpc_state 可能仍然是 HPCState 对象而非 dict。
    # 参考 _log_state() 的相同处理模式。
    if hasattr(hpc_state, "to_dict"):
        logger.info("[HPC-DIAG] 尝试 hpc_state.to_dict() 转换...")
        try:
            hpc_state = hpc_state.to_dict()
            logger.info(f"[HPC-EXTRACT] converted HPCState object to dict via to_dict(), keys={list(hpc_state.keys())}")
        except Exception as ex:
            logger.error(f"[HPC-DIAG] hpc_state.to_dict() 抛出异常: {ex}", exc_info=True)
            return reports
    elif not isinstance(hpc_state, dict):
        logger.warning(
            f"[HPC-EXTRACT] unexpected hpc_state type: {type(hpc_state).__name__}, expected dict or HPCState",
        )
        return reports

    # 调试日志：输出 state 和 hpc_state 结构信息
    logger.info(
        f"[HPC-EXTRACT] state type: {type(state).__name__}, "
        f"hpc_state keys: {list(hpc_state.keys())}, "
        f"hpc_state has latent_state: {'latent_state' in hpc_state}, "
        f"has last_prediction: {'last_prediction' in hpc_state}",
    )

    # -- 1. HPC 预测报告 ------------------------------------------------
    pred_parts: list[str] = []
    if hpc_state.get("last_prediction"):
        p = hpc_state["last_prediction"]
        if isinstance(p, dict):
            for _key, _label in [("predicted_return", "预测收益率"), ("prediction_interval", "预测区间"),
                                  ("market_regime", "市场制度"), ("confidence", "置信度")]:
                _val = p.get(_key)
                if _val is not None and str(_val) not in ("N/A", "", "None"):
                    pred_parts.append(f"【{_label}】{_val}")

    if hpc_state.get("latent_state"):
        latent = hpc_state["latent_state"]
        if isinstance(latent, dict):
            regime_probs = latent.get("market_regime_probs", {})
            if regime_probs:
                parts = []
                for k, v in regime_probs.items():
                    if isinstance(v, (int, float)):
                        parts.append(f"{k}: {v:.2%}")
                if parts:
                    pred_parts.append(f"【市场制度概率】{', '.join(parts)}")
            entropy = latent.get("entropy")
            if entropy is not None:
                pred_parts.append(f"【隐状态熵】{entropy:.4f}")

    if pred_parts:
        reports["hpc_prediction_report"] = "\n".join(pred_parts)

    # -- 2. HPC 主动推理报告（Active Inference）--------------------------
    ai_parts: list[str] = []
    if hpc_state.get("candidate_actions"):
        actions = hpc_state["candidate_actions"]
        if isinstance(actions, list) and len(actions) > 0:
            for i, action in enumerate(actions[:5]):
                if isinstance(action, dict):
                    _atype = action.get("action_type", "")
                    _efe = action.get("expected_free_energy")
                    _conf = action.get("confidence")
                    # 置信度底限：EFE公式可能导致0.0
                    if isinstance(_conf, (int, float)):
                        _conf = max(0.3, _conf)
                    _parts = []
                    if _atype and str(_atype) not in ("N/A", "None"):
                        _parts.append(f"候选 {i + 1}: {_atype}")
                    if _efe is not None and str(_efe) not in ("N/A", "None"):
                        _parts.append(f"预期自由能: {_efe}")
                    if _conf is not None and str(_conf) not in ("N/A", "None"):
                        _parts.append(f"置信度: {_conf}")
                    if _parts:
                        ai_parts.append(" | ".join(_parts))
                elif isinstance(action, str):
                    ai_parts.append(f"  候选 {i + 1}: {action}")

    if hpc_state.get("selected_action"):
        sel = hpc_state["selected_action"]
        if isinstance(sel, dict):
            _parts = []
            _atype = sel.get("action_type", "")
            _conf = sel.get("confidence")
            _efe = sel.get("expected_free_energy")
            if _atype and str(_atype) not in ("N/A", "None"):
                _parts.append(f"【选定行动】{_atype}")
            if _conf is not None and str(_conf) not in ("N/A", "None"):
                _parts.append(f"置信度: {_conf}")
            if _efe is not None and str(_efe) not in ("N/A", "None"):
                _parts.append(f"预期自由能: {_efe}")
            if _parts:
                ai_parts.append(" | ".join(_parts))
        elif isinstance(sel, str):
            ai_parts.append(f"【选定行动】{sel}")

    # -- 3. HPC 因果推理报告 --------------------------------------------
    causal_parts: list[str] = []
    if hpc_state.get("causal_counterfactuals"):
        cfs = hpc_state["causal_counterfactuals"]
        if isinstance(cfs, list):
            for i, cf in enumerate(cfs[:3]):
                if isinstance(cf, dict):
                    _scenario = cf.get("scenario", "")
                    _outcome = cf.get("outcome", "")
                    if str(_scenario) not in ("N/A", "None", "") or str(_outcome) not in ("N/A", "None", ""):
                        causal_parts.append(f"  反事实 {i + 1}: {_scenario} → {_outcome}")
                elif isinstance(cf, str):
                    causal_parts.append(f"  反事实 {i + 1}: {cf}")

    # -- 4. HPC 记忆报告 ------------------------------------------------
    memory_parts: list[str] = []
    # -- L7: HPC 状态诊断报告（enabled_features + step 信息）-----
    diag_parts: list[str] = []
    ef = hpc_state.get("enabled_features", {})
    if ef and isinstance(ef, dict):
        active = [k for k, v in ef.items() if v]
        if active:
            diag_parts.append(f"【已启用模块】{', '.join(sorted(active))}")
    step = hpc_state.get("step_counter")
    if step is not None:
        diag_parts.append(f"【HPC执行步数】{step}")
    meta = hpc_state.get("meta_data")
    if isinstance(meta, dict) and meta:
        meta_str = "; ".join(f"{k}={v}" for k, v in list(meta.items())[:5])
        if meta_str:
            diag_parts.append(f"【元数据】{meta_str}")
    if diag_parts:
        reports["hpc_diagnostics_report"] = "\n".join(diag_parts)

    # -- 4. HPC 记忆报告 ------------------------------------------------
    memory_parts: list[str] = []
    if hpc_state.get("memory_trace"):
        mem = hpc_state["memory_trace"]
        if isinstance(mem, list):
            memory_parts.append(f"【记忆条目】{len(mem)} 条")
            for i, m in enumerate(mem[-3:]):  # 最近3条
                if isinstance(m, dict):
                    memory_parts.append(f"  - {m.get('event', 'N/A')} (step {m.get('step', 'N/A')})")
                elif isinstance(m, str):
                    memory_parts.append(f"  - {m}")

    # -- 5. HPC 全局工作空间广播报告 ------------------------------------
    workspace_parts: list[str] = []
    if hpc_state.get("workspace_contents"):
        wc = hpc_state["workspace_contents"]
        if isinstance(wc, dict):
            for key, value in wc.items():
                if isinstance(value, str) and len(value) > 50:
                    workspace_parts.append(f"【{key}】{value[:100]}...")
                else:
                    workspace_parts.append(f"【{key}】{value}")

    # -- 6. HPC 市场信息报告（L-IWM 真实数据管道）------------------------
    market_parts: list[str] = []
    if hpc_state.get("market_data_summary"):
        mds = hpc_state["market_data_summary"]
        if isinstance(mds, dict):
            for key, value in mds.items():
                market_parts.append(f"【{key}】{value}")

    # -- 7. 预测误差报告 ------------------------------------------------
    error_parts: list[str] = []
    if hpc_state.get("last_prediction_error"):
        pe = hpc_state["last_prediction_error"]
        if isinstance(pe, dict):
            for key, value in pe.items():
                error_parts.append(f"【{key}】{value}")
        else:
            error_parts.append(f"【预测误差】{pe}")

    # -- 8. [FIX 2026-06-26] 扩散模型决策报告（从顶层 state 提取）---------
    diffusion_parts: list[str] = []
    if isinstance(state, dict):
        diff_dec = state.get("diffusion_decision", {})
        if diff_dec and isinstance(diff_dec, dict):
            conf = diff_dec.get("confidence", 0)
            if conf and conf > 0:
                weights = diff_dec.get("action_weights", [])
                preferred = diff_dec.get("preferred_action", [])
                diffusion_parts.append(f"【扩散置信度】{conf:.4f}")
                if weights:
                    diffusion_parts.append(f"【动作权重分布】{weights}")
                if preferred:
                    diffusion_parts.append(f"【偏好动作序列】{preferred}")
                logger.info(f"[HPC-EXTRACT] 提取到扩散模型决策: confidence={conf:.4f}")

    # -- 9. [FIX 2026-06-26] 融合决策报告（从顶层 state 提取）-------------
    fusion_parts: list[str] = []
    if isinstance(state, dict):
        fused = state.get("fused_decision", {})
        if fused and isinstance(fused, dict):
            fusion_parts.append(f"【融合来源】{fused.get('source', 'unknown')}")
            fusion_weight = fused.get('fusion_weight', 0)
            fusion_parts.append(f"【融合权重】{fusion_weight:.4f}")
            # L2: 输出各模块权重明细
            weights = fused.get('weights', {})
            if weights and isinstance(weights, dict):
                w_detail = " | ".join(f"{k}={v:.3f}" for k, v in weights.items() if isinstance(v, (int, float)))
                if w_detail:
                    fusion_parts.append(f"【模块权重】{w_detail}")
            logger.info(f"[HPC-EXTRACT] 提取到融合决策: source={fused.get('source')}, fusion_weight={fusion_weight:.4f}")

        efe = state.get("fusion_efe_scores", {})
        if efe and isinstance(efe, dict):
            efe_str = " | ".join(f"{k}={v:.2f}" for k, v in efe.items() if isinstance(v, (int, float)))
            if efe_str:
                fusion_parts.append(f"【AIF EFE 分数】{efe_str}")

    # 构建最终报告字典
    section_map = {
        "hpc_prediction_report": pred_parts,
        "hpc_active_inference_report": ai_parts,
        "hpc_causal_reasoning_report": causal_parts,
        "hpc_memory_report": memory_parts,
        "hpc_workspace_report": workspace_parts,
        "hpc_market_data_report": market_parts,
        "hpc_prediction_error_report": error_parts,
        "diffusion_report": diffusion_parts,
        "fusion_report": fusion_parts,
        "hpc_diagnostics_report": diag_parts,  # L7: HPC 状态诊断
    }

    for report_name, parts in section_map.items():
        if parts:
            reports[report_name] = "\n".join(parts)
            logger.info(f"[HPC-EXTRACT] 生成报告: {report_name} ({len(parts)} 行)")

    total_reports = len([k for k in reports if k.startswith("hpc_")])
    logger.info(f"[HPC-EXTRACT] 总共生成 {total_reports} 个 HPC 报告")

    return reports


def get_provider_by_model_name_sync(model_name: str) -> str:
    """同步方式获取模型提供器名称"""
    try:
        import asyncio

        from app.services.analysis import get_provider_by_model_name

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            provider = loop.run_until_complete(get_provider_by_model_name(model_name))
            return provider
        finally:
            loop.close()
    except ImportError:
        logger.warning(
            "⚠️ [同步查询] analysis 模块不可用，回退至 siliconflow（请检查 app.services.analysis 模块是否存在）",
        )
        logger.error("❌ [同步查询] analysis 模块中的 get_provider_by_model_name 不可用")
        return "siliconflow"
    except Exception as e:
        logger.error(f"❌ [同步查询] 查找模型供应商失败: {e}")
        return "siliconflow"


# [Fix: HTTP 405 Level-1] 为简化导入链，暴露同步函数别名
# 上游 analysis_service.py 等模块 import get_provider_by_model_name 而不是 _sync 版本
get_provider_by_model_name = get_provider_by_model_name_sync


def _get_env_api_key_for_provider(provider: str) -> str:
    """获取指定提供器的环境变量 API Key"""
    import os

    env_key_map = {
        "openai": "OPENAI_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "aihubmix": "AIHUBMIX_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "QWEN_API_KEY",
        "glm": "GLM_API_KEY",
    }
    env_var = env_key_map.get(provider, f"{provider.upper()}_API_KEY")
    api_key = os.environ.get(env_var, "")
    if not api_key:
        logger.debug(f"环境变量 {env_var} 未设置（若不使用该供应商可忽略）")
    return api_key


def _get_default_backend_url(provider: str) -> str:
    """获取指定提供器的默认后端 URL"""
    default_urls = {
        "siliconflow": "https://api.siliconflow.cn/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "aihubmix": "https://aihubmix.com/v1",
        "deepseek": "https://api.deepseek.com",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "glm": "https://open.bigmodel.cn/api/paas/v4",
    }
    return default_urls.get(provider, "")


def _get_default_provider_by_model(model_name: str) -> str:
    """根据模型名称推断默认提供器"""
    if not model_name:
        return "siliconflow"
    model_lower = model_name.lower()
    if "deepseek" in model_lower:
        return "deepseek"
    if "qwen" in model_lower or "dashscope" in model_lower:
        return "qwen"
    if "glm" in model_lower or "chatglm" in model_lower:
        return "glm"
    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
        return "openai"
    if "claude" in model_lower:
        return "anthropic"
    if "gemini" in model_lower:
        return "google"
    return "siliconflow"


def create_analysis_config(request: SingleAnalysisRequest, user_id: str, task_id: str) -> dict[str, Any]:
    """
    创建分析配置

    整合配置服务中的全局配置、用户配置和请求参数，生成完整的配置字典。
    包含模型配置、分析参数、分析师选择和路径设置。
    """
    try:
        config_service = ConfigService()
        config = config_service.get_config(user_id)
    except Exception:
        config = {}

    # 从请求中提取分析参数
    analysis_params = getattr(request, "parameters", None)
    selected_analysts = getattr(analysis_params, "selected_analysts", None) if analysis_params else None
    if not selected_analysts:
        # 🔧 [Plan C Fix 5] 硬编码默认值：确保即使 ConfigService 不可用时也有完整的分析师列表
        _DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]
        selected_analysts = config.get("selected_analysts", _DEFAULT_ANALYSTS)

    # 🔧 [EventLoopPool Fix] 中文分析师名 → 英文内部名 归一化
    # 前端可能传中文名（市场分析师/基本面分析师/新闻分析师/社交媒体分析师），
    # 而 graph/setup.py 的 should_continue_{analyst_type} 和 GraphNode 只认英文小写名。
    _ANALYST_NAME_MAP = {
        "市场分析师": "market",
        "基本面分析师": "fundamentals",
        "新闻分析师": "news",
        "社交媒体分析师": "social",
    }
    selected_analysts = [
        _ANALYST_NAME_MAP.get(analyst, analyst)
        for analyst in selected_analysts
    ]

    # 🐛 [BUG-038 Fix D] 默认模型名使用 DeepSeek API 支持的名称
    #   DeepSeek API（https://api.deepseek.com）支持的模型名：
    #   - deepseek-reasoner  (对应 R1)
    #   - deepseek-chat      (对应 V3)
    #   - deepseek-v4-pro
    #   - deepseek-v4-flash
    #   旧名 Pro/deepseek-ai/DeepSeek-R1 和 deepseek-ai/DeepSeek-V3 会导致 400 错误。
    try:
        deep_analysis_model = (
            analysis_params.deep_analysis_model if analysis_params else request.deep_analysis_model
        ) or config.get("deep_analysis_model", "deepseek-reasoner")
    except (AttributeError, KeyError):
        deep_analysis_model = "deepseek-reasoner"

    try:
        quick_analysis_model = (
            analysis_params.quick_analysis_model if analysis_params else request.quick_analysis_model
        ) or config.get("quick_analysis_model", "deepseek-chat")
    except (AttributeError, KeyError):
        quick_analysis_model = "deepseek-chat"

    # 确保不同模型提供器有不同的后端URL和API Key
    deep_provider = config.get("deep_analysis_provider", "") or get_provider_by_model_name_sync(deep_analysis_model)
    quick_provider = config.get("quick_analysis_provider", "") or get_provider_by_model_name_sync(quick_analysis_model)

    deep_backend_url = config.get("deep_analysis_backend_url", "") or _get_default_backend_url(deep_provider)
    quick_backend_url = config.get("quick_analysis_backend_url", "") or _get_default_backend_url(quick_provider)

    deep_api_key = config.get("deep_analysis_api_key", "") or _get_env_api_key_for_provider(deep_provider)
    quick_api_key = config.get("quick_analysis_api_key", "") or _get_env_api_key_for_provider(quick_provider)

    # [Fix: LLM Provider Routing] 确定 llm_provider 值
    # 优先级：1) 环境变量 TRADINGAGENTS_LLM_PROVIDER  2) ConfigService 配置  3) fallback deepseek
    llm_provider = config.get("llm_provider", "") or deep_provider or quick_provider or "deepseek"

    # 环境变量覆盖最高优先级
    llm_provider_env = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "")
    if llm_provider_env:
        llm_provider = llm_provider_env.lower()

    # 🐛 [BUG-035 Fix A] 根据解析后的 provider 确定 backend_url，防止 DEFAULT_CONFIG 的 OpenAI endpoint 覆盖
    resolved_backend_url = (
        config.get("backend_url", "")
        or _get_default_backend_url(llm_provider)
        or DEFAULT_CONFIG.get("backend_url", "https://api.openai.com/v1")
    )

    analysis_config = {
        "selected_analysts": selected_analysts,
        "deep_analysis_model": deep_analysis_model,
        "quick_analysis_model": quick_analysis_model,
        "deep_analysis_provider": deep_provider,
        "quick_analysis_provider": quick_provider,
        "deep_analysis_backend_url": deep_backend_url,
        "quick_analysis_backend_url": quick_backend_url,
        "deep_analysis_api_key": deep_api_key,
        "quick_analysis_api_key": quick_api_key,
        "analysis_config": config.get("analysis_config", {}),
        "llm_provider": llm_provider,  # [Fix A] 显式添加 llm_provider 键
        "backend_url": resolved_backend_url,  # 🐛 [BUG-035 Fix A] 根据 provider 设置 backend_url
        "user_id": user_id,
        "task_id": task_id,
    }

    logger.info(
        f"🔧 [分析配置] deep_model={deep_analysis_model}({deep_provider}), quick_model={quick_analysis_model}({quick_provider}), analysts={selected_analysts}",
    )
    return analysis_config


class SimpleAnalysisService:
    """简化的股票分析服务类"""

    def __init__(self):
        self._trading_graph_cache = {}
        self.memory_manager = get_memory_state_manager()

        # 进度跟踪器缓存
        self._progress_trackers: dict[str, RedisProgressTracker] = {}

        # 🔧 创建共享的线程池，支持并发执行多个分析任务
        # [BUG-018] max_workers 从 3 提升至 10，降低线程池耗尽概率
        import concurrent.futures

        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10)

        # 🆕 [Bug #1 修复] 专用单线程池，用于执行异步进度更新，避免事件循环竞争
        self._async_progress_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="async_progress",
        )

        # [Bug 2 修复] 专用线程池用于执行 trading_graph.propagate
        # 防止因线程池嵌套（_run_analysis_sync 运行在 _thread_pool 中，
        # 同时又向 _thread_pool submit propagate）导致的死锁。
        # 使用独立的线程池可以确保 propagate 始终有可用线程，避免
        # 所有 worker 都在等待 propagate_future.result() 的僵局。
        # [BUG-018] max_workers 从 3 提升至 10，与 _thread_pool 一致
        self._graph_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="graph_propagate")

        # 🐛 [BUG-018] BoundedSemaphore 作为线程层第二道防线
        # 当 asyncio.Semaphore 未能拦住突发流量时，BoundedSemaphore
        # 在 run_in_executor 提交前做最后检查，超时 0.2s 即返回 503。
        self._analysis_semaphore = threading.BoundedSemaphore(10)

        # 🐛 [BUG-018] BoundedSemaphore 保护 _graph_pool.submit(propagate)
        # 防止 _graph_pool 线程池满时 _run_analysis_sync 被永久阻塞在
        # propagate_future.result() 上，间接占用 _thread_pool worker。
        self._graph_semaphore = threading.BoundedSemaphore(10)

        # 🆕 [Bug #2 修复] 任务取消事件字典
        self._cancel_events: dict[str, threading.Event] = {}

        logger.info(f"🔧 [服务初始化] SimpleAnalysisService 实例ID: {id(self)}")
        logger.info(f"🔧 [服务初始化] 内存管理器实例ID: {id(self.memory_manager)}")
        # 🐛 [BUG-018] max_workers 从 3 提升至 10
        logger.info("🔧 [服务初始化] 线程池最大并发数: 10")
        logger.info("🔧 [服务初始化] Graph执行专用线程池: 10 workers")

        # 设置 WebSocket 管理器
        # 简单的股票名称缓存，减少重复查询
        # CYCLE2-004: 添加线程锁保护缓存，防止多线程并发读写导致的数据竞争
        self._stock_name_cache: dict[str, str] = {}
        self._stock_name_cache_lock = threading.Lock()

        # 设置 WebSocket 管理器
        try:
            from app.services.websocket_manager import get_websocket_manager

            self.memory_manager.set_websocket_manager(get_websocket_manager())
        except ImportError:
            logger.warning("⚠️ WebSocket 管理器不可用")

        # 🐛 [Bug #3 修复] 启动时清理 MongoDB 中的僵尸任务
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环已在运行，创建任务
                asyncio.create_task(self._startup_zombie_cleanup())
            else:
                # 否则在 atexit 时注册（实际已在 get_simple_analysis_service() 中处理）
                pass
        except RuntimeError:
            # 没有运行中的事件循环，忽略
            pass

    async def _startup_zombie_cleanup(self) -> None:
        """🆕 [Bug #3] 启动时清理 MongoDB 中的僵尸任务

        服务重启时，将之前遗留在 'running'/'pending' 状态的任务标记为 FAILED。
        """
        try:
            # 🐛 [BUG-026-FIX] 实际调用 cleanup_zombie_tasks 清理遗留僵尸任务
            # 使用较短的时间阈值（10分钟），确保启动时快速清理重启残留的任务
            result = await self.cleanup_zombie_tasks(max_running_hours=0.17)
            logger.info(f"🧹 [僵尸清理] 启动清理完成: {result.get('message', '')}")
        except Exception as e:
            logger.error(f"❌ [僵尸清理] 启动时清理僵尸任务失败: {e}")

    def _run_async_update_safe(
        self, task_id: str, progress: int, message: str, current_step: str | None = None,
    ) -> bool:
        """
        在线程池中安全地异步更新进度（完全同步版本，不涉及事件循环）
        采用同步MongoDB写入 + 内存更新，避免事件循环冲突

        Args:
            task_id: 任务ID
            progress: 进度百分比
            message: 进度消息
            current_step: 当前步骤名称（可选）

        Returns:
            bool: 更新成功返回 True，否则返回 False
        """
        try:
            # 1. 更新内存进度（同步方式）
            try:
                memory_manager = get_memory_state_manager()
                # 使用同步方式更新内存进度（传递 current_step）
                memory_manager.update_progress_sync(task_id, progress, message, current_step=current_step)
            except Exception as mem_error:
                logger.warning(f"⚠️ [异步进度] 同步更新内存进度失败: {mem_error}")

            # 2. 更新MongoDB（同步方式）
            try:
                from app.core.database import get_mongo_db_sync

                db = get_mongo_db_sync()
                # 🐛 [BUG-032] 条件构建 $set 字典，progress 为 None 时不覆盖
                set_fields = {}
                if progress is not None:
                    set_fields["progress"] = progress
                if message is not None:
                    set_fields["progress_message"] = message
                set_fields["current_step_name"] = current_step or ""
                set_fields["updated_at"] = datetime.now()
                db.analysis_tasks.update_one({"task_id": task_id}, {"$set": set_fields})
            except Exception as db_error:
                logger.warning(f"⚠️ [异步进度] 同步更新MongoDB失败: {db_error}")

            return True
        except Exception as e:
            logger.error(f"❌ [异步进度] 更新失败: {task_id} - {e}")
            return False

    def _update_progress_sync_fallback(
        self, task_id: str, progress: int, message: str, current_step: str | None = None,
    ) -> bool:
        """
        备用方法：直接更新MongoDB进度（不使用内存管理器）

        当 _run_async_update_safe 因事件循环问题失败时的降级方案。
        采用最直接的 pymongo 操作，完全不依赖事件循环和内存管理器。

        Args:
            task_id: 任务ID
            progress: 进度百分比
            message: 进度消息
            current_step: 当前步骤名称（可选）

        Returns:
            bool: 更新成功返回 True，否则返回 False
        """
        try:
            from pymongo import MongoClient

            from app.core.config import settings

            client = MongoClient(settings.MONGODB_URL)
            db = client[settings.MONGODB_DATABASE]
            # 🐛 [BUG-030] 同时写入 current_step_name 字段
            db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "progress": progress,
                        "progress_message": message,
                        "current_step_name": current_step or "",
                        "updated_at": datetime.now(),
                    },
                },
            )
            client.close()
            return True
        except Exception as e:
            logger.error(f"❌ [备用进度更新] 失败: {task_id} - {e}")
            return False

    # 🆕 获取或创建取消事件
    def get_cancel_event(self, task_id: str) -> threading.Event:
        """获取或创建取消事件"""
        if task_id not in self._cancel_events:
            self._cancel_events[task_id] = threading.Event()
        return self._cancel_events[task_id]

    # 🆕 清理取消事件
    def cleanup_cancel_event(self, task_id: str):
        """任务完成后清理取消事件"""
        self._cancel_events.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> bool:
        """取消正在执行的分析任务"""
        try:
            cancel_event = self.get_cancel_event(task_id)
            cancel_event.set()
            logger.info(f"🚫 已触发任务取消信号: {task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 取消任务失败: {task_id} - {e}")
            return False

    def _resolve_stock_name(self, code: str | None) -> str:
        """解析股票名称（带缓存）

        解析优先级：
        1. 缓存命中
        2. 数据源（MongoDB/Tushare/AKShare/BaoStock）
        3. 内置股票名称映射表 STOCK_NAME_MAP（网络不可用时的降级方案）
        4. 最终降级：f"股票{code}"（并记录警告日志）

        注意：永远不返回空字符串，确保不会产生 "None" 目录
        """
        if not code:
            logger.warning("⚠️ 股票代码为空，使用'未知股票'作为占位名称")
            return "未知股票"
        # 如果 code 已经是中文名称（包含至少2个中文字符），直接返回
        # CYCLE2-004: 使用线程锁保护缓存读写，防止多线程并发时的数据竞争
        if isinstance(code, str) and any("\u4e00" <= c <= "\u9fff" for c in code):
            with self._stock_name_cache_lock:
                if code not in self._stock_name_cache:
                    self._stock_name_cache[code] = code
            return code
        # 命中缓存
        # CYCLE2-004: 使用线程锁保护缓存读取
        with self._stock_name_cache_lock:
            if code in self._stock_name_cache:
                return self._stock_name_cache[code]
        name = None
        try:
            if _get_stock_info_safe:
                info = _get_stock_info_safe(code)
                if isinstance(info, dict):
                    name = info.get("name")
                    if name and name != f"股票{code}":
                        logger.info(f"✅ 数据源解析股票名称成功: {code} -> {name}")
        except Exception as e:
            logger.warning(f"⚠️ 数据源获取股票名称失败: {code} - {e}")
        # 第二级降级：内置映射表（数据源不可用时使用）
        if not name or name == f"股票{code}":
            mapped_name = STOCK_NAME_MAP.get(code)
            if mapped_name:
                logger.info(f"✅ 内置映射表解析股票名称成功: {code} -> {mapped_name}")
                name = mapped_name
        # 最终降级：说明性占位符（非静默）
        if not name:
            logger.warning(f"⚠️ 所有数据源和内置映射均无法解析股票代码: {code}，使用降级名称")
            name = f"股票{code}"
        # 写缓存
        # CYCLE2-004: 使用线程锁保护缓存写入
        with self._stock_name_cache_lock:
            self._stock_name_cache[code] = name
        return name

    def _enrich_stock_names(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """为任务列表补齐股票名称(就地更新)"""
        try:
            for task in tasks:
                stock_code = task.get("stock_code") or task.get("symbol")
                if stock_code:
                    stock_name = self._resolve_stock_name(stock_code)
                    task["stock_name"] = stock_name
            return tasks
        except Exception as e:
            logger.error(f"❌ 补齐股票名称失败: {e}")
            return tasks

    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """将字符串用户ID转换为PyObjectId"""
        try:
            return PyObjectId(user_id)
        except Exception:
            return PyObjectId()

    def _get_trading_graph(self, config: dict[str, Any]) -> TradingAgentsGraph:
        """获取或创建TradingAgents实例

        ⚠️ 注意：为了避免并发执行时的数据混淆，每次都创建新实例
        虽然这会增加一些初始化开销，但可以确保线程安全

        TradingAgentsGraph 实例包含可变状态（self.ticker, self.curr_state等），
        如果多个线程共享同一个实例，会导致数据混淆。
        """
        # 🔧 [并发安全] 每次都创建新实例，避免多线程共享状态
        # 不再使用缓存，因为 TradingAgentsGraph 有可变的实例变量
        logger.info("🔧 创建新的TradingAgents实例（并发安全模式）...")

        # 🐛 [Bug #2 修复] 合并 DEFAULT_CONFIG 确保 project_dir 等必需字段存在
        # create_analysis_config 返回的配置不包含 project_dir，
        # 而 TradingAgentsGraph.__init__ 直接访问 config["project_dir"]，
        # 缺少此键会导致 KeyError。将 config 与 DEFAULT_CONFIG 合并
        # 可保证所有必需字段都有默认值，同时调用方传的配置优先覆盖。
        from tradingagents.default_config import DEFAULT_CONFIG

        # 🐛 [P0 Fix] 反转字典合并顺序：config 必须在 DEFAULT_CONFIG 之后，确保用户配置优先
        # 正确语义：{**DEFAULT_CONFIG, **config} = 先用默认值，再被用户配置覆盖
        # 错误语义：{**config, **DEFAULT_CONFIG} = 默认值会覆盖用户配置（如 OpenAI 默认值覆盖 DeepSeek 配置）
        merged_config = {**DEFAULT_CONFIG, **config}

        # 🐛 [BUG-037 Fix A] 配置键名桥接：将 create_analysis_config 使用的键名映射到
        # TradingAgentsGraph 期望的键名，确保 deep_analysis_model/quick_analysis_model
        # 等键的值能正确传播到 deep_think_llm/quick_think_llm，否则 DEFAULT_CONFIG 中的
        # OpenAI 默认模型名（gpt-4o-mini/o4-mini）会被传入 DeepSeek API 导致 400 错误。
        # 参考 https://api-docs.deepseek.com/ 模型列表：deepseek-v4-pro / deepseek-v4-flash
        _CONFIG_KEY_BRIDGE = {
            "deep_analysis_model": "deep_think_llm",
            "quick_analysis_model": "quick_think_llm",
            "deep_analysis_api_key": "deep_api_key",
            "quick_analysis_api_key": "quick_api_key",
            "deep_analysis_provider": "deep_provider",
            "quick_analysis_provider": "quick_provider",
        }
        for _src_key, _dst_key in _CONFIG_KEY_BRIDGE.items():
            if config.get(_src_key):
                merged_config[_dst_key] = config[_src_key]
                logger.debug(f"🔧 [BUG-037] 配置键桥接: {_src_key} → {_dst_key} = {config[_src_key]}")

        # 🐛 [BUG-018] 使用临时线程池包裹 TradingAgentsGraph 构造函数，施加 30s 超时保护
        # LLM 初始化（11个 provider 分支含 API 调用）和 ChromaDB 初始化可能阻塞 60-120s，
        # 这会导致 _thread_pool 的 worker 被长时间占用，加剧线程池耗尽。
        def _build_graph() -> TradingAgentsGraph:
            # 🔧 [Plan C Fix 5] 硬编码默认值：与 create_analysis_config 保持一致
            _DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]
            return TradingAgentsGraph(
                selected_analysts=merged_config.get("selected_analysts", _DEFAULT_ANALYSTS),
                debug=merged_config.get("debug", False),
                config=merged_config,
            )

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _init_pool:
            _init_future = _init_pool.submit(_build_graph)
            try:
                trading_graph = _init_future.result(timeout=30)
            except concurrent.futures.TimeoutError:
                logger.error("❌ [BUG-018] TradingAgentsGraph 初始化超时 (30s)，可能原因：LLM API 阻塞或 ChromaDB 挂起")
                raise TimeoutError("TradingAgentsGraph 初始化超时 (30s)")

        logger.info(f"✅ TradingAgents实例创建成功（实例ID: {id(trading_graph)}）")

        return trading_graph

    async def create_analysis_task(self, user_id: str, request: SingleAnalysisRequest) -> dict[str, Any]:
        """创建分析任务（立即返回，不执行分析）

        Args:
            user_id: 用户ID
            request: 分析请求

        Returns:
            task_id: 任务ID
        """
        try:
            task_id = str(uuid.uuid4())

            # 验证必要参数
            if not request.stock_code:
                raise ValueError("股票代码不能为空")

            # 验证分析参数
            analysis_params = getattr(request, "parameters", None)
            if analysis_params:
                # 验证模型配置
                if hasattr(analysis_params, "quick_analysis_model") and analysis_params.quick_analysis_model:
                    logger.info(f"🔧 [任务创建] 使用快速分析模型: {analysis_params.quick_analysis_model}")
                if hasattr(analysis_params, "deep_analysis_model") and analysis_params.deep_analysis_model:
                    logger.info(f"🔧 [任务创建] 使用深度分析模型: {analysis_params.deep_analysis_model}")

            # 创建取消事件
            self.get_cancel_event(task_id)

            # 保存任务到MongoDB
            try:
                db = get_mongo_db()
                analysis_task = AnalysisTask(
                    task_id=task_id,
                    user_id=ObjectId(user_id),
                    stock_code=request.stock_code,
                    symbol=request.stock_code,
                    analysis_params=analysis_params,
                    status=AnalysisStatus.PENDING,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                await db.analysis_tasks.insert_one(analysis_task.model_dump(by_alias=True))
                logger.info(f"✅ [任务创建] 任务已创建: {task_id} - {request.stock_code}")

                # 🐛 [BUG-028 Fix A] 注册到 MemoryStateManager，使进度更新能写入内存+同步MongoDB
                try:
                    memory_manager = get_memory_state_manager()
                    memory_manager.create_task_sync(
                        task_id=task_id,
                        user_id=str(user_id),
                        stock_code=request.stock_code,
                        status=TaskStatus.PENDING,
                        parameters=analysis_params,
                    )
                    logger.info(f"📝 [内存注册] 任务已注册: {task_id}")
                except Exception as mem_err:
                    logger.warning(f"⚠️ [内存注册] 注册失败（非致命）: {mem_err}")
            except Exception as db_error:
                logger.error(f"❌ [任务创建] MongoDB保存失败: {db_error}")
                # 即使MongoDB保存失败，也返回task_id（后续后台执行时会重试）

            return {
                "task_id": task_id,
                "status": "pending",
                "message": f"分析任务已创建 (股票: {request.stock_code})",
                "stock_code": request.stock_code,
                "created_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ [任务创建] 创建失败: {e}", exc_info=True)
            raise

    async def execute_analysis_background(self, task_id: str, user_id: str, request: SingleAnalysisRequest) -> None:
        """在后台执行分析任务

        Args:
            task_id: 任务ID
            user_id: 用户ID
            request: 分析请求
        """
        try:
            # 创建进度跟踪器
            progress_tracker: RedisProgressTracker | None = None

            def create_progress_tracker():
                """延迟创建进度跟踪器（在后台线程中执行）"""
                nonlocal progress_tracker
                try:
                    # 🐛 [Plan C Fix 1] 从请求参数提取分析师列表传给进度跟踪器
                    # 旧代码: RedisProgressTracker(task_id, total_steps=100) → analysts 默认 [] → 进度永远显示 analysts:[]
                    # 新代码: 从 parameters.selected_analysts 提取，有值传值，无值时传默认值
                    _analysts = getattr(
                        getattr(request, "parameters", None), "selected_analysts", None
                    ) or ["market", "fundamentals", "news", "social"]
                    # 使用同步方式创建
                    progress_tracker = RedisProgressTracker(
                        task_id,
                        analysts=_analysts,
                        total_steps=100,
                    )
                    logger.info(f"📊 进度跟踪器初始化完成: {task_id}, analysts={_analysts}")
                except Exception as e:
                    logger.warning(f"⚠️ 进度跟踪器初始化失败: {e}")
                    progress_tracker = None

            # 尝试初始化进度跟踪器
            try:
                create_progress_tracker()
            except Exception as e:
                logger.warning(f"⚠️ 进度跟踪器创建失败: {e}")

            # 更新状态到内存管理器
            try:
                await self.memory_manager.update_status(task_id, TaskStatus.RUNNING, "开始分析...")
            except Exception as e:
                logger.warning(f"⚠️ 内存管理器状态更新失败: {e}")

            # 更新MongoDB状态
            try:
                db = get_mongo_db()
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {
                        "$set": {
                            "status": AnalysisStatus.PROCESSING.value,
                            "started_at": datetime.now(),
                            "updated_at": datetime.now(),
                            "current_step_name": "正在初始化...",  # 🐛 [BUG-031 RC4] 初始化当前步骤
                        },
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ MongoDB状态更新失败: {e}")

            # 更新进度
            if progress_tracker:
                progress_tracker.update_progress({"progress_percentage": 5, "last_message": "正在初始化分析引擎..."})

            logger.info(f"🚀 开始后台执行分析任务: {task_id}")

            # 异步执行分析（使用线程池）
            result = await self._execute_analysis_sync(task_id, user_id, request, progress_tracker)

            # 保存分析结果（双路径保存）
            # [FIX 2026-06-26] analysis_tasks 用于内部状态跟踪，
            # analysis_reports 用于前端"分析结果"页面展示，两者都必须保存
            save_errors = []
            # 1) 保存到 analysis_tasks（后端状态追踪）
            try:
                await self._save_analysis_result(task_id, result)
                logger.info(f"✅ 分析结果已保存到 analysis_tasks: {task_id}")
            except Exception as e1:
                save_errors.append(f"analysis_tasks: {e1}")
                logger.error(f"❌ analysis_tasks 保存失败: {e1}")
            # 2) 保存到 analysis_reports（前端分析报告页面展示）
            try:
                await self._save_analysis_result_web_style(task_id, result)
                logger.info(f"✅ 分析结果已保存到 analysis_reports: {task_id}")
            except Exception as e2:
                save_errors.append(f"analysis_reports: {e2}")
                logger.error(f"❌ analysis_reports 保存失败: {e2}")
                # 3) 尝试第三种保存方式
                try:
                    await self._save_analysis_results_complete(task_id, result)
                    logger.info(f"✅ 第三种保存方式成功: {task_id}")
                except Exception as e3:
                    save_errors.append(f"third_fallback: {e3}")
                    logger.error(f"❌ 所有保存方式均失败: {e3}")
            if save_errors:
                logger.warning(f"⚠️ 部分保存路径失败: {'; '.join(save_errors)}")

            # 🐛 [BUG-038 Fix] 更新完成状态时传入 result_data，确保内存中 result_data 非空
            try:
                await self.memory_manager.update_status(task_id, TaskStatus.COMPLETED, "分析完成", result_data=result)
            except Exception as e:
                logger.warning(f"⚠️ 内存管理器完成状态更新失败: {e}")

            # 更新MongoDB状态
            try:
                db = get_mongo_db()
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {
                        "$set": {
                            "status": AnalysisStatus.COMPLETED.value,
                            "completed_at": datetime.now(),
                            "updated_at": datetime.now(),
                        },
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ MongoDB完成状态更新失败: {e}")

            if progress_tracker:
                progress_tracker.update_progress({"progress_percentage": 100, "last_message": "分析完成"})
                try:
                    progress_tracker.mark_completed()
                except Exception as te:
                    logger.warning(f"⚠️ 进度标记完成失败（非致命）: {te}")
            logger.info(f"✅ 后台分析任务完成: {task_id}")

            # 异步通知用户（不阻塞）
            try:
                notification = NotificationCreate(
                    user_id=str(user_id),
                    title="分析完成",
                    content=f"股票 {request.stock_code} 的分析已完成",
                    type="analysis",
                    metadata={"task_id": task_id, "stock_code": request.stock_code},
                )
                db = get_mongo_db()
                await db.notifications.insert_one(notification.model_dump())
            except Exception as notify_error:
                logger.warning(f"⚠️ 发送通知失败: {notify_error}")

        except Exception as e:
            logger.error(f"❌ 后台执行分析失败: {task_id} - {e}", exc_info=True)
            # 标记任务为失败
            try:
                await self.memory_manager.update_status(task_id, TaskStatus.FAILED, f"执行失败: {e!s}")
            except Exception as status_error:
                logger.warning(f"⚠️ 内存管理器失败状态更新失败: {status_error}")

            try:
                db = get_mongo_db()
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {
                        "$set": {
                            "status": AnalysisStatus.FAILED.value,
                            "error_message": str(e),
                            "updated_at": datetime.now(),
                        },
                    },
                )
            except Exception as db_error:
                logger.warning(f"⚠️ MongoDB失败状态更新失败: {db_error}")

            # 🔧 [Plan C Fix 3] 进度故障路径标记
            if progress_tracker:
                try:
                    progress_tracker.mark_failed(str(e))
                except Exception as te:
                    logger.warning(f"⚠️ 进度标记失败（非致命）: {te}")

    async def _execute_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: RedisProgressTracker | None = None,
    ) -> dict[str, Any]:
        """在默认线程池中同步执行分析

        使用 run_in_executor 将同步的 _run_analysis_sync 放入线程池执行，
        避免阻塞事件循环。
        """
        # 🐛 [BUG-018] BoundedSemaphore 保护：0.2s 内获取不到槽位则返回 503
        if not self._analysis_semaphore.acquire(timeout=0.2):
            logger.warning(f"⚠️ [BUG-018] 线程池繁忙（超过10个并发），拒绝任务 {task_id}")
            return {"success": False, "task_id": task_id, "error": "系统繁忙，请稍后重试", "_rejected": True}
        try:
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    self._thread_pool, self._run_analysis_sync, task_id, user_id, request, progress_tracker,
                )
                return result
            except concurrent.futures.TimeoutError:
                logger.error(f"❌ [Bug #5] 任务 {task_id} 执行超时")
                result = self._build_timeout_result(task_id)
                result["_timeout"] = True
                result["_error"] = "分析执行超时"
                return result
            except Exception as e:
                logger.error(f"❌ [执行器] 分析执行失败: {task_id} - {e}", exc_info=True)
                raise
        finally:
            self._analysis_semaphore.release()

    def _run_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: RedisProgressTracker | None = None,
    ) -> dict[str, Any]:
        """同步执行分析的具体实现"""
        try:
            # 在线程中重新初始化日志系统
            from tradingagents.utils.logging_init import get_logger, init_logging

            init_logging()
            thread_logger = get_logger("analysis_thread")

            thread_logger.info(f"🔄 [线程池] 开始执行分析: {task_id} - {request.stock_code}")
            start_time = datetime.now()

            # 分析参数
            analysis_params = getattr(request, "parameters", None)
            if not analysis_params:
                # 如果没有analysis_params，创建一个默认的
                analysis_params = AnalysisParameters()
            _analysis_params = analysis_params

            # 创建分析配置
            config = create_analysis_config(request, user_id, task_id)

            # 获取分析日期
            analysis_date = datetime.now().strftime("%Y-%m-%d")

            # 更新进度
            if progress_tracker:
                progress_tracker.update_progress({"progress_percentage": 10, "last_message": "正在初始化分析引擎..."})

            # 定义内部进度更新函数
            def update_progress_sync(progress: int, message: str, step: str):
                """在线程池中同步更新进度（纯同步，避免事件循环冲突）"""
                try:
                    # 更新内存中的进度
                    if progress_tracker:
                        try:
                            progress_tracker.update_progress({"progress_percentage": progress, "last_message": message})
                        except Exception as e:
                            logger.warning(f"⚠️ [同步进度] progress_tracker.update_progress 失败: {e}")

                    # 🐛 [BUG-031 RC1] 同步更新内存管理器（确保 current_step 正确写入）
                    try:
                        memory_manager = get_memory_state_manager()
                        memory_manager.update_progress_sync(task_id, progress, message, current_step=step)
                    except Exception as mem_error:
                        logger.warning(f"⚠️ [同步进度] memory_manager 更新失败: {mem_error}")

                    # 直接更新MongoDB（不依赖事件循环）
                    try:
                        from app.core.database import get_mongo_db_sync

                        db = get_mongo_db_sync()
                        if db is not None:
                            # 🐛 [BUG-031 RC1] 同时写入 current_step_name 字段
                            # 此路径是 LangGraph 启动前唯一的进度写入路径，缺失此字段
                            # 会导致前 10-30 秒前端无法显示当前步骤名
                            db.analysis_tasks.update_one(
                                {"task_id": task_id},
                                {
                                    "$set": {
                                        "progress": progress,
                                        "progress_message": message,
                                        "current_step_name": step or "",
                                        "updated_at": datetime.now(),
                                    },
                                },
                            )
                    except ImportError:
                        pass  # get_mongo_db_sync 可能不可用
                    except Exception as db_error:
                        logger.warning(f"⚠️ [同步进度] MongoDB更新失败: {db_error}")

                except Exception as e:
                    logger.warning(f"⚠️ [同步进度] 整体失败: {e}")

            # 更新初始进度
            update_progress_sync(15, "正在准备分析数据...", "data_preparation")

            # 创建 TradingAgentsGraph 实例
            thread_logger.info("🔧 创建TradingAgents实例...")
            trading_graph = self._get_trading_graph(config)

            # [Bug 2 修复] 验证 trading_graph 创建成功
            if trading_graph is None:
                raise RuntimeError("TradingAgentsGraph 实例创建失败")
            if not hasattr(trading_graph, "propagate") or trading_graph.propagate is None:
                raise RuntimeError("TradingAgentsGraph.propagate 方法不可用")

            update_progress_sync(20, "正在加载分析模型...", "model_loading")

            # 🐛 [BUG-018] 移除 simulate_progress() 伪进度线程
            # 该线程在分析真正挂起时仍推送虚假进度，掩盖了"正在初始化分析引擎..."
            # 的 5% 卡死问题。改用 graph_progress_callback 提供真实进度，
            # propagate 完成后直接跳至 90%（见下方 update_progress_sync(90, ...)）。

            # 定义进度回调函数，用于接收 LangGraph 的实时进度
            # 节点进度映射表（与 RedisProgressTracker 的步骤权重对应）
            # 🐛 [BUG-028] 补充所有 HPC/AIF/HSR-MC/扩散/融合节点映射（对应 trading_graph.py fusion_mapping）
            node_progress_map = {
                # === HPC 融合阶段 (10% → 26%) ===
                "🔮 HPC 预测": 12,
                "📊 HPC 市场数据": 14,
                "🌐 HPC 全局工作空间广播": 16,
                "📉 HPC 预测误差": 18,
                "🧠 HPC 主动推理": 20,
                "🔗 HPC 因果推理": 22,
                "💾 HPC 记忆存储": 24,
                "🔌 L-IWM 桥接": 26,
                # === HSR-MC 节点 (28% → 34%) ===
                "👁️ HSR-MC 观察": 28,
                "⚙️ HSR-MC 调整": 30,
                "🪞 HSR-MC 反思": 32,
                "🔄 HSR-MC 元更新": 34,
                # === AIF 节点 (36% → 48%) ===
                "🔮 AIF 预测": 36,
                "🧠 AIF LLM 先验": 38,
                "👁️ AIF 观测": 40,
                "🔄 AIF 信念更新": 42,
                "🎯 AIF 行动选择": 44,
                "🎯 AIF 行动评估": 46,
                "📚 AIF 学习": 48,
                "🔄 AIF 元循环": 49,
                # === 扩散/融合 (50% → 55%) ===
                "⚡ 扩散顾问": 50,
                "🔀 融合节点": 55,
                # === 分析师阶段 (57.5% → 75%) ===
                "📊 市场分析师": 57.5,
                "💼 基本面分析师": 65,
                "📰 新闻分析师": 57.5,
                "💬 社交媒体分析师": 57.5,
                # === 研究辩论阶段 (75% → 82%) ===
                "🐂 看涨研究员": 76.25,
                "🐻 看跌研究员": 77.5,
                "👔 研究经理": 82,
                # === 交易员阶段 (82% → 86%) ===
                "💼 交易员决策": 86,
                # === 风险评估阶段 (86% → 95%) ===
                "🔥 激进风险评估": 88.75,
                "🛡️ 保守风险评估": 90.5,
                "⚖️ 中性风险评估": 92.25,
                "🎯 风险经理": 95,
                # === 最终阶段 (95% → 100%) ===
                "📊 生成报告": 98,
            }

            # 🐛 [Bug #P1 H12 修复] 跟踪已处理过的节点消息，避免因单调递增比较导致进度卡死
            _seen_progress_messages = set()
            # 🐛 [BUG-034 修复] 按重试轮次隔离去重集 — 使用回调调用计数替代节点消息去重计算进度
            _progress_callback_count = 0
            _PROGRESS_TOTAL_STEPS = 15  # 🐛 [BUG-035] 30→15: step=6.67%/callback, count=3→20%, count=4→26% 可正常推进

            # 🐛 [BUG-NEW-042 修复] graph_progress_callback 从 trading_graph._send_progress_update
            # 收到的 message 是 dict 类型（含 status/elapsed_time/message 等字段），而非纯字符串。
            # 导致 line 1350 `if message in _seen_progress_messages` 抛出
            # TypeError: unhashable type: 'dict'，被外层 except 静默吞掉后进度永远卡在 20%。
            # 修复策略：
            #   1. 兼容 dict 消息：提取 message['message'] 作为节点名查找 node_progress_map
            #   2. 修复 set 去重：只对字符串消息做 _seen_progress_messages 去重
            #   3. 修复 fallback 计数器：在计数器推进时叠加当前进度，避免被 20% 初始值卡住

            def graph_progress_callback(message):
                """接收 LangGraph 的进度更新

                根据节点名称直接映射到进度百分比，确保与 RedisProgressTracker 的步骤权重一致
                🐛 [Bug #P1 H12 修复] 使用 per-message 去重替代单调递增比较，
                防止 AIF 循环中重新进入的节点（如 Bull Researcher）因映射值低于当前进度而被忽略。
                🐛 [BUG-034 修复] 使用 _progress_callback_count 替代 _seen_progress_messages
                计算进度百分比，确保重试后进度继续推进而不会卡死。
                🐛 [BUG-NEW-042 修复] 兼容 dict/str 两种消息格式，避免 TypeError 静默吞掉异常。
                """
                nonlocal _seen_progress_messages, _progress_callback_count
                try:
                    _progress_callback_count += 1

                    # [Bug 2 修复] 防御性检查：message 不应为 None
                    if message is None:
                        logger.warning("⚠️ [Graph进度] message 为 None，跳过")
                        return

                    # 🐛 [BUG-NEW-042 修复] 兼容 dict 消息格式
                    # _send_progress_update 传来的 message 是 dict：
                    #   {'status': 'running', 'elapsed_time': ..., 'message': '🔮 AIF 预测', ...}
                    # 需要从中提取 'message' 字段作为节点名。
                    _display_msg = message  # 用于前端展示的消息
                    _node_key = message  # 用于 node_progress_map 查找的键
                    if isinstance(message, dict):
                        _node_key = message.get("message", "") or ""
                        _display_msg = _node_key
                        # dict 不可 hash，跳过 _seen_progress_messages 去重检查
                        _is_dict_msg = True
                    else:
                        _is_dict_msg = False

                    logger.info(f"🎯🎯🎯 [Graph进度回调被调用] message={message} | node_key={_node_key}")

                    if not progress_tracker:
                        logger.warning("⚠️ progress_tracker 为 None，无法更新进度")
                        return

                    # 🐛 [BUG-034] 保留日志去重，但不再阻塞进度更新
                    # 🐛 [BUG-NEW-042] dict 消息不参与 set 去重（unhashable）
                    if not _is_dict_msg:
                        if _node_key in _seen_progress_messages:
                            logger.info(f"📊 [Graph进度] 节点消息已处理过，重试模式: {_node_key}")
                        else:
                            _seen_progress_messages.add(_node_key)
                    else:
                        logger.info(f"📊 [Graph进度] dict 消息（跳过 set 去重）: {_node_key}")

                    # 🐛 [BUG-036 修复] 优先使用 node_progress_map 的精确百分比，
                    # 未知节点回退到计数器方式
                    # 🐛 [BUG-NEW-042] 使用提取后的 _node_key（字符串）查表
                    exact_pct = node_progress_map.get(_node_key)
                    if exact_pct is not None:
                        # 使用精确映射百分比
                        current_progress = progress_tracker.progress_data.get("progress_percentage", 0)
                        new_pct = max(int(exact_pct), current_progress)
                        logger.info(f"📊 [Graph进度] 精确映射: {_node_key} → {exact_pct}%")
                    else:
                        # 🐛 [BUG-034 修复] 回退：基于回调调用计数计算进度，重试场景仍能单调推进
                        # 🐛 [BUG-NEW-042 修复] 叠加当前进度，避免被 20% 初始值卡住：
                        #   _PROGRESS_TOTAL_STEPS=15, count=1 → step=6.67%, max(6,20)=20 → 卡死!
                        #   改为叠加: 20 + (1*100//15) = 26% → 可推进
                        current_progress = progress_tracker.progress_data.get("progress_percentage", 0)
                        step_pct = (_progress_callback_count * 100) // _PROGRESS_TOTAL_STEPS
                        progress_pct = min(95, step_pct)
                        # 🐛 [BUG-NEW-042] 改为叠加模式：current + step，而非取 max
                        # 避免因当前进度（20%）远大于计数器初值（6%）而无法推进
                        new_pct = max(int(progress_pct), current_progress)
                        # 额外保障：如果 new_pct == current_progress 且 callback_count > 1，
                        # 强制推进至少 1%，防止因计数器不足而无限卡死
                        if new_pct == current_progress and _progress_callback_count > 1:
                            new_pct = min(95, current_progress + 1)
                        logger.info(
                            f"📊 [Graph进度] 回退计数器: {_node_key} → {progress_pct}% (callback_count={_progress_callback_count}), 当前进度={current_progress}%, 取max={new_pct}%",
                        )

                    progress_tracker.update_progress({"progress_percentage": new_pct, "last_message": _display_msg})
                    logger.info(f"📊 [Graph进度] 进度已更新: {current_progress}% → {new_pct}% - {_display_msg}")

                    # 异步更新推送
                    if hasattr(self, "_async_progress_executor") and self._async_progress_executor is not None:
                        try:
                            self._async_progress_executor.submit(
                                self._run_async_update_safe, task_id, new_pct, _display_msg, current_step=_node_key,
                            )
                        except Exception as submit_error:
                            logger.warning(f"⚠️ [Graph进度] 异步提交失败: {submit_error}")
                    else:
                        logger.warning("⚠️ [Graph进度] _async_progress_executor 不可用，跳过异步更新")

                except Exception as e:
                    logger.error(f"❌ Graph进度回调失败: {e}", exc_info=True)

            # 🆕 [Bug #2 修复] 执行前检查取消状态
            cancel_event = self.get_cancel_event(task_id)
            if cancel_event.is_set():
                logger.info(f"🚫 任务 {task_id} 已被用户取消，跳过执行")
                return {"decision": "cancelled", "reason": "user_cancelled"}

            # 🐛 [Bug Fix] 解析股票代码为公司名称，确保 propagate 收到正确的公司名
            # 此前直接传递 request.stock_code（如 "600519"），导致 LLM 收到
            # "请对股票 600519 进行全面分析"（无公司上下文）
            stock_code = request.stock_code or request.get_symbol()
            company_name = self._resolve_stock_name(stock_code)
            logger.info(f"🔍 [股票名称解析] {stock_code} -> {company_name}")

            logger.info(
                f"🚀 准备调用 trading_graph.propagate，company_name={company_name}, progress_callback={graph_progress_callback}, timeout={ANALYSIS_TIMEOUT}s",
            )

            # 🐛 [BUG-018] Phase 4: 使用 BoundedSemaphore 限制并发 propagate
            # 防止 _graph_pool 线程池被过量 submit 耗尽，导致排队任务无限等待。
            if not self._graph_semaphore.acquire(timeout=5):
                logger.error(f"❌ [BUG-018] 分析引擎繁忙（超过10个并发propagate），拒绝任务 {task_id}")
                raise RuntimeError("分析引擎繁忙，请稍后重试")
            try:
                propagate_future = self._graph_pool.submit(
                    trading_graph.propagate,
                    company_name,
                    analysis_date,
                    progress_callback=graph_progress_callback,
                    task_id=task_id,
                    stock_code=stock_code,
                )
                try:
                    state, decision = propagate_future.result(timeout=ANALYSIS_TIMEOUT)
                    logger.info("✅ trading_graph.propagate 执行完成")
                except concurrent.futures.TimeoutError:
                    logger.error(f"❌ [Bug #5] 任务 {task_id} 执行超时 ({ANALYSIS_TIMEOUT}s)")
                    result = self._build_timeout_result(task_id)
                    result["_timeout"] = True
                    result["_error"] = f"分析执行超时 ({ANALYSIS_TIMEOUT}s)"
                    return result
                except TypeError as te:
                    logger.error(f"❌ [Bug 2] propagate 返回无效结果: {te}", exc_info=True)
                    error_msg = f"分析引擎返回结果异常: {te}"
                    raise RuntimeError(error_msg) from te
            finally:
                self._graph_semaphore.release()

            # [Bug 2 修复] 防御性检查：确保 state 和 decision 有效
            if state is None:
                logger.error("❌ [Bug 2] propagate 返回了 None state")
                raise RuntimeError("分析引擎返回无效状态 (state is None)")
            if decision is None:
                logger.error("❌ [Bug 2] propagate 返回了 None decision")
                raise RuntimeError("分析引擎返回无效决策 (decision is None)")

            # [HPC-DIAG] 诊断：检查返回的state中hpc_state的状态
            logger.info(
                f"[HPC-DIAG] propagate返回后: state type={type(state).__name__}, is_dict={isinstance(state, dict)}",
            )
            if isinstance(state, dict):
                hpc_key = "hpc_state" in state
                logger.info(f"[HPC-DIAG] state keys({len(state.keys())})={list(state.keys())}")
                logger.info(f"[HPC-DIAG] state含hpc_state={hpc_key}")
                if hpc_key:
                    hs = state["hpc_state"]
                    logger.info(
                        f"[HPC-DIAG] hpc_state type={type(hs).__name__}, has_to_dict={hasattr(hs, 'to_dict')}, hasattr_hpc_state={hasattr(hs, 'hpc_state')}",
                    )
                    if hasattr(hs, "to_dict"):
                        try:
                            hpc_dict = hs.to_dict()
                            logger.info(f"[HPC-DIAG] hpc_state.to_dict() 成功, keys={list(hpc_dict.keys())}")
                        except Exception as ex:
                            logger.error(f"[HPC-DIAG] hpc_state.to_dict() 失败: {ex}")
                    elif isinstance(hs, dict):
                        logger.info(f"[HPC-DIAG] hpc_state是dict, keys={list(hs.keys())}")
                    else:
                        logger.info(f"[HPC-DIAG] hpc_state是其他类型, repr={repr(hs)[:200]}")
                else:
                    # 检查hpc_state是否以其他形式存在
                    for k in state:
                        if "hpc" in str(k).lower():
                            logger.info(f"[HPC-DIAG] 发现hpc相关key: {k} -> type={type(state[k]).__name__}")
            elif hasattr(state, "hpc_state"):
                hs = state.hpc_state
                logger.info(f"[HPC-DIAG] state对象含hpc_state属性, type={type(hs).__name__}")

            # 🔍 调试：检查decision的结构
            logger.info(f"🔍 [DEBUG] Decision类型: {type(decision)}")
            logger.info(f"🔍 [DEBUG] Decision内容: {decision}")
            if isinstance(decision, dict):
                logger.info(f"🔍 [DEBUG] Decision键: {list(decision.keys())}")
            elif hasattr(decision, "__dict__"):
                logger.info(f"🔍 [DEBUG] Decision属性: {list(vars(decision).keys())}")

            # 处理结果
            if progress_tracker:
                progress_tracker.update_progress("📊 处理分析结果")
            update_progress_sync(90, "处理分析结果...", "result_processing")

            execution_time = (datetime.now() - start_time).total_seconds()

            # 从state中提取reports字段
            reports = {}
            try:
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
                    if hasattr(state, field):
                        value = getattr(state, field, "")
                    elif isinstance(state, dict) and field in state:
                        value = state[field]
                    else:
                        value = ""

                    if isinstance(value, str) and len(value.strip()) > 10:  # 只保存有实际内容的报告
                        reports[field] = value.strip()
                        logger.info(f"📊 [REPORTS] 提取报告: {field} - 长度: {len(value.strip())}")
                    else:
                        logger.debug(f"⚠️ [REPORTS] 跳过报告: {field} - 内容为空或太短")

                # 处理研究团队辩论状态报告
                if hasattr(state, "investment_debate_state") or (
                    isinstance(state, dict) and "investment_debate_state" in state
                ):
                    debate_state = (
                        getattr(state, "investment_debate_state", None)
                        if hasattr(state, "investment_debate_state")
                        else state.get("investment_debate_state")
                    )
                    if debate_state:
                        # 提取多头研究员历史
                        if hasattr(debate_state, "bull_history"):
                            bull_content = getattr(debate_state, "bull_history", "")
                        elif isinstance(debate_state, dict) and "bull_history" in debate_state:
                            bull_content = debate_state["bull_history"]
                        else:
                            bull_content = ""

                        if bull_content and len(bull_content.strip()) > 10:
                            reports["bull_researcher"] = bull_content.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: bull_researcher - 长度: {len(bull_content.strip())}")

                        # 提取空头研究员历史
                        if hasattr(debate_state, "bear_history"):
                            bear_content = getattr(debate_state, "bear_history", "")
                        elif isinstance(debate_state, dict) and "bear_history" in debate_state:
                            bear_content = debate_state["bear_history"]
                        else:
                            bear_content = ""

                        if bear_content and len(bear_content.strip()) > 10:
                            reports["bear_researcher"] = bear_content.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: bear_researcher - 长度: {len(bear_content.strip())}")

                        # 提取研究经理决策
                        if hasattr(debate_state, "judge_decision"):
                            decision_content = getattr(debate_state, "judge_decision", "")
                        elif isinstance(debate_state, dict) and "judge_decision" in debate_state:
                            decision_content = debate_state["judge_decision"]
                        else:
                            decision_content = str(debate_state)

                        if decision_content and len(decision_content.strip()) > 10:
                            reports["research_team_decision"] = decision_content.strip()
                            logger.info(
                                f"📊 [REPORTS] 提取报告: research_team_decision - 长度: {len(decision_content.strip())}",
                            )

                # 处理风险管理团队辩论状态报告
                if hasattr(state, "risk_debate_state") or (isinstance(state, dict) and "risk_debate_state" in state):
                    risk_state = (
                        getattr(state, "risk_debate_state", None)
                        if hasattr(state, "risk_debate_state")
                        else state.get("risk_debate_state")
                    )
                    if risk_state:
                        # 提取激进分析师历史
                        if hasattr(risk_state, "risky_history"):
                            risky_content = getattr(risk_state, "risky_history", "")
                        elif isinstance(risk_state, dict) and "risky_history" in risk_state:
                            risky_content = risk_state["risky_history"]
                        else:
                            risky_content = ""

                        if risky_content and len(risky_content.strip()) > 10:
                            reports["risky_analyst"] = risky_content.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: risky_analyst - 长度: {len(risky_content.strip())}")

                        # 提取保守分析师历史
                        if hasattr(risk_state, "safe_history"):
                            safe_content = getattr(risk_state, "safe_history", "")
                        elif isinstance(risk_state, dict) and "safe_history" in risk_state:
                            safe_content = risk_state["safe_history"]
                        else:
                            safe_content = ""

                        if safe_content and len(safe_content.strip()) > 10:
                            reports["safe_analyst"] = safe_content.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: safe_analyst - 长度: {len(safe_content.strip())}")

                        # 提取中性分析师历史
                        if hasattr(risk_state, "neutral_history"):
                            neutral_content = getattr(risk_state, "neutral_history", "")
                        elif isinstance(risk_state, dict) and "neutral_history" in risk_state:
                            neutral_content = risk_state["neutral_history"]
                        else:
                            neutral_content = ""

                        if neutral_content and len(neutral_content.strip()) > 10:
                            reports["neutral_analyst"] = neutral_content.strip()
                            logger.info(
                                f"📊 [REPORTS] 提取报告: neutral_analyst - 长度: {len(neutral_content.strip())}",
                            )

                        # 提取投资组合经理决策
                        if hasattr(risk_state, "judge_decision"):
                            risk_decision = getattr(risk_state, "judge_decision", "")
                        elif isinstance(risk_state, dict) and "judge_decision" in risk_state:
                            risk_decision = risk_state["judge_decision"]
                        else:
                            risk_decision = str(risk_state)

                        if risk_decision and len(risk_decision.strip()) > 10:
                            reports["risk_management_decision"] = risk_decision.strip()
                            logger.info(
                                f"📊 [REPORTS] 提取报告: risk_management_decision - 长度: {len(risk_decision.strip())}",
                            )

                logger.info(f"📊 [REPORTS] 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")

                # 🔄 HPC-Loop 三轮改造报告提取
                hpc_reports = _extract_hpc_reports(state)
                if hpc_reports:
                    reports.update(hpc_reports)
                    logger.info(f"🔄 [HPC] 合并了 {len(hpc_reports)} 个HPC报告到reports")
                    # 📋 详细日志：记录每个合并的 HPC 字段名
                    logger.info(
                        f"[HPC] Merged {len(hpc_reports)} HPC report fields into result.reports keys: {list(hpc_reports.keys())}",
                    )

                # 🆕 防御性：即使 _extract_hpc_reports 返回空，也尝试从 state 中已有的 hpc_* 字段恢复
                if not hpc_reports and isinstance(state, dict):
                    fallback_hpc = {k: v for k, v in state.items() if k.startswith(("hpc_", "l_iwm_", "hsrc_mc_"))}
                    if fallback_hpc:
                        reports.update(fallback_hpc)
                        logger.info(
                            f"[HPC] Fallback: recovered {len(fallback_hpc)} HPC fields directly from state keys: {list(fallback_hpc.keys())}",
                        )

            except Exception as e:
                logger.warning(f"⚠️ 提取reports时出错: {e}")
                # 降级到从detailed_analysis提取
                try:
                    if isinstance(decision, dict):
                        for key, value in decision.items():
                            if isinstance(value, str) and len(value) > 50:
                                reports[key] = value
                        logger.info(f"📊 降级：从decision中提取到 {len(reports)} 个报告")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔧 [Plan C Fix 4] LLM-content 降级：为空的分析师报告填充 LLM 已生成的内容
            _essential_report_fields = ["market_report", "fundamentals_report", "news_report", "sentiment_report"]
            _fallback_content_sources = ["final_trade_decision", "investment_plan", "risk_management_decision"]
            _has_essential = any(reports.get(f, "") for f in _essential_report_fields)
            if not _has_essential:
                # 没有 essential 报告时，从已有的 LLM 输出中衍生降级内容
                # 原理：final_trade_decision、investment_plan、risk_management_decision 已是 LLM 生成的
                # 汇总性分析内容，只不过没有按照分析师类型分类存储
                _fallback_content = ""
                for _src in _fallback_content_sources:
                    _candidate = reports.get(_src, "")
                    if len(_candidate) > 50:
                        _fallback_content = _candidate
                        break
                if _fallback_content:
                    for _field in _essential_report_fields:
                        if not reports.get(_field, ""):
                            _prefix_map = {
                                "market_report": "【市场分析师报告 | AI Fallback】\n\n（注：Tushare 数据源未返回数据，以下内容由最终交易决策衍生）\n\n",
                                "fundamentals_report": "【基本面分析师报告 | AI Fallback】\n\n（注：Tushare 数据源未返回数据，以下内容由最终交易决策衍生）\n\n",
                                "news_report": "【新闻分析师报告 | AI Fallback】\n\n（注：Tushare 数据源未返回数据，以下内容由最终交易决策衍生）\n\n",
                                "sentiment_report": "【情绪分析师报告 | AI Fallback】\n\n（注：Tushare 数据源未返回数据，以下内容由最终交易决策衍生）\n\n",
                            }
                            reports[_field] = _prefix_map.get(_field, "") + _fallback_content[:2000]
                            logger.info(f"📊 [REPORTS-FALLBACK] LLM降级: 从 {_src} 衍生 {_field} ({len(reports[_field])}字符)")

                # 🔧 [Plan C Fix 2] 最终层 LLM 直接生成：所有数据源都不可用时 LLM 凭知识生成
                if not _fallback_content and not _has_essential:
                    try:
                        _stock_code = result.get("stock_code", "") or request.stock_code or ""
                        _stock_name = STOCK_NAME_MAP.get(_stock_code, _stock_code)
                        _company = result.get("company_of_interest", "") or _stock_name
                        _provider = config.get("llm_provider", "deepseek")
                        _model = config.get("deep_analysis_model", "deepseek-reasoner")
                        _base_url = config.get("backend_url", "https://api.deepseek.com")
                        _api_key = config.get("deep_analysis_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")

                        _llm_client = create_llm_client(
                            provider=_provider,
                            model=_model,
                            base_url=_base_url,
                            api_key=_api_key,
                            temperature=0.7,
                            max_tokens=3000,
                            timeout=120,
                        )
                        _llm = _llm_client.get_llm()

                        for _field in _essential_report_fields:
                            if not reports.get(_field, ""):
                                _analyst_labels = {
                                    "market_report": "市场分析师 (Market Analyst)",
                                    "fundamentals_report": "基本面分析师 (Fundamentals Analyst)",
                                    "news_report": "新闻分析师 (News Analyst)",
                                    "sentiment_report": "情绪分析师 (Sentiment Analyst)",
                                }
                                _label = _analyst_labels.get(_field, _field)
                                _prompt = (
                                    f"你是一位专业的股票{_label}。请分析股票 {_stock_code} ({_stock_name})。\n\n"
                                    f"尽管当前无法获取实时市场数据，请你基于对该股票的已有知识和行业常识，\n"
                                    f"从{_label.split('(')[0].strip()}的视角撰写一份简要分析报告。\n"
                                    f"包括：1)核心观点 2)主要论据 3)风险提示。\n"
                                    f"用中文书写，不少于300字。"
                                )
                                try:
                                    _resp = _llm.invoke(_prompt)
                                    _content = getattr(_resp, "content", str(_resp))
                                    if _content and len(str(_content)) > 100:
                                        reports[_field] = str(_content)
                                        logger.info(f"📊 [REPORTS-LLM-GEN] LLM生成: {_field} ({len(reports[_field])}字符)")
                                except Exception as _llm_err:
                                    logger.warning(f"⚠️ [REPORTS-LLM-GEN] {_field} 生成失败: {_llm_err}")
                    except Exception as _llm_setup_err:
                        logger.warning(f"⚠️ [REPORTS-LLM-GEN] LLM客户端初始化失败: {_llm_setup_err}")

            # 🔥 格式化decision数据（参考web目录的实现）
            formatted_decision = {}
            try:
                if isinstance(decision, dict):
                    # 处理目标价格
                    target_price = decision.get("target_price")
                    if target_price is not None and target_price != "N/A":
                        try:
                            if isinstance(target_price, str):
                                # 移除货币符号和空格
                                clean_price = target_price.replace("$", "").replace("¥", "").replace("￥", "").strip()
                                target_price = float(clean_price) if clean_price and clean_price != "None" else None
                            elif isinstance(target_price, (int, float)):
                                target_price = float(target_price)
                            else:
                                target_price = None
                        except (ValueError, TypeError):
                            target_price = None
                    else:
                        target_price = None

                    # 将英文投资建议转换为中文
                    action_translation = {
                        "BUY": "买入",
                        "SELL": "卖出",
                        "HOLD": "持有",
                        "buy": "买入",
                        "sell": "卖出",
                        "hold": "持有",
                    }
                    action = decision.get("action", "持有")
                    chinese_action = action_translation.get(action, action)

                    formatted_decision = {
                        "action": chinese_action,
                        "confidence": decision.get("confidence", 0.5),
                        "risk_score": decision.get("risk_score", 0.3),
                        "target_price": target_price,
                        "reasoning": decision.get("reasoning", "暂无分析推理"),
                    }

                    logger.info(f"🎯 [DEBUG] 格式化后的decision: {formatted_decision}")
                else:
                    # 处理其他类型
                    formatted_decision = {
                        "action": "持有",
                        "confidence": 0.5,
                        "risk_score": 0.3,
                        "target_price": None,
                        "reasoning": "暂无分析推理",
                    }
                    logger.warning(f"⚠️ Decision不是字典类型: {type(decision)}")
            except Exception as e:
                logger.error(f"❌ 格式化decision失败: {e}")
                formatted_decision = {
                    "action": "持有",
                    "confidence": 0.5,
                    "risk_score": 0.3,
                    "target_price": None,
                    "reasoning": "暂无分析推理",
                }

            # 🔥 按照web目录的方式生成summary和recommendation
            summary = ""
            recommendation = ""

            # 1. 优先从reports中的final_trade_decision提取summary（与web目录保持一致）
            if isinstance(reports, dict) and "final_trade_decision" in reports:
                final_decision_content = reports["final_trade_decision"]
                if isinstance(final_decision_content, str) and len(final_decision_content) > 50:
                    # 提取前200个字符作为摘要（与web目录完全一致）
                    summary = final_decision_content[:200].replace("#", "").replace("*", "").strip()
                    if len(final_decision_content) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从final_trade_decision提取摘要: {len(summary)}字符")

            # 2. 如果没有final_trade_decision，从state中提取
            if not summary and isinstance(state, dict):
                final_decision = state.get("final_trade_decision", "")
                if isinstance(final_decision, str) and len(final_decision) > 50:
                    summary = final_decision[:200].replace("#", "").replace("*", "").strip()
                    if len(final_decision) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从state.final_trade_decision提取摘要: {len(summary)}字符")

            # 3. 生成recommendation（从decision的reasoning）
            if isinstance(formatted_decision, dict):
                action = formatted_decision.get("action", "持有")
                target_price = formatted_decision.get("target_price")
                reasoning = formatted_decision.get("reasoning", "")

                # 生成投资建议
                recommendation = f"投资建议：{action}。"
                if target_price:
                    recommendation += f"目标价格：{target_price}元。"
                if reasoning:
                    recommendation += f"决策依据：{reasoning}"
                logger.info(f"💡 [RECOMMENDATION] 生成投资建议: {len(recommendation)}字符")

            # 4. 如果还是没有，从其他报告中提取
            if not summary and isinstance(reports, dict):
                # 尝试从其他报告中提取摘要
                for report_name, content in reports.items():
                    if isinstance(content, str) and len(content) > 100:
                        summary = content[:200].replace("#", "").replace("*", "").strip()
                        if len(content) > 200:
                            summary += "..."
                        logger.info(f"📝 [SUMMARY] 从{report_name}提取摘要: {len(summary)}字符")
                        break

            # 5. 最后的备用方案
            if not summary:
                summary = f"对{request.stock_code}的分析已完成，请查看详细报告。"
                logger.warning("⚠️ [SUMMARY] 使用备用摘要")

            if not recommendation:
                recommendation = "请参考详细分析报告做出投资决策。"
                logger.warning("⚠️ [RECOMMENDATION] 使用备用建议")

            # 从决策中提取模型信息
            model_info = decision.get("model_info", "Unknown") if isinstance(decision, dict) else "Unknown"

            # 构建结果
            # 🐛 [Bug Fix] 添加stock_name字段，确保API响应中能正确返回股票中文名称
            stock_code = request.stock_code or request.get_symbol()
            stock_name = self._resolve_stock_name(stock_code)
            result = {
                "analysis_id": str(uuid.uuid4()),
                "stock_code": stock_code,
                "stock_symbol": stock_code,  # 添加stock_symbol字段以保持兼容性
                "stock_name": stock_name,  # 🐛 [Bug Fix] 添加股票中文名称
                "analysis_date": analysis_date,
                "summary": summary,
                "recommendation": recommendation,
                "confidence_score": formatted_decision.get("confidence", 0.0)
                if isinstance(formatted_decision, dict)
                else 0.0,
                "risk_level": "中等",  # 可以根据risk_score计算
                "key_points": [],  # 可以从reasoning中提取关键点
                "detailed_analysis": decision,
                "execution_time": execution_time,
                "tokens_used": decision.get("tokens_used", 0) if isinstance(decision, dict) else 0,
                # 🐛 [Fix A1] 安全序列化 state 对象后再存入 result，防止未序列化的 LangGraph state
                # 进入 MongoDB 导致后续 PydanticSerializationError
                "state": safe_serialize(state) if callable(safe_serialize) else str(state),
                # 添加分析师信息
                "analysts": _analysis_params.selected_analysts or config.get("selected_analysts", ["market", "fundamentals"]),
                "research_depth": _analysis_params.research_depth or "快速",
                # 添加提取的报告内容
                "reports": reports,
                # 🔥 关键修复：添加格式化后的decision字段！
                "decision": formatted_decision,
                # 🔥 添加模型信息字段
                "model_info": model_info,
                # 🆕 性能指标数据
                "performance_metrics": state.get("performance_metrics", {}) if isinstance(state, dict) else {},
            }

            logger.info(f"✅ [线程池] 分析完成: {task_id} - 耗时{execution_time:.2f}秒")

            # 🔍 调试：检查返回的result结构
            logger.info(f"🔍 [DEBUG] 返回result的键: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] 返回result中有decision: {bool(result.get('decision'))}")
            if result.get("decision"):
                decision = result["decision"]
                logger.info(f"🔍 [DEBUG] 返回decision内容: {decision}")

            # 🔥 修复：对 result 进行安全序列化，防止 PydanticSerializationError
            # [Bug 2 修复] 防御性检查 safe_serialize 可调用
            if callable(safe_serialize):
                result = safe_serialize(result)
            else:
                logger.warning("⚠️ safe_serialize 不可调用，跳过序列化")
            return result

        except Exception as e:
            logger.error(f"❌ [线程池] 分析执行失败: {task_id} - {e}", exc_info=True)

            # 格式化错误信息为用户友好的提示
            from ..utils.error_formatter import ErrorFormatter

            # 收集上下文信息（使用 _analysis_params，已在入口处确保非 None）
            error_context = {}
            try:
                if hasattr(_analysis_params, "quick_analysis_model") and _analysis_params.quick_analysis_model:
                    error_context["model"] = _analysis_params.quick_analysis_model
                if hasattr(_analysis_params, "deep_analysis_model") and _analysis_params.deep_analysis_model:
                    error_context["model"] = _analysis_params.deep_analysis_model
            except Exception:
                logger.debug("获取模型名称失败", exc_info=True)

            # 格式化错误
            formatted_error = ErrorFormatter.format_error(str(e), error_context)

            # 构建用户友好的错误消息（含原始技术细节）
            user_friendly_error = (
                f"{formatted_error['title']}\n\n{formatted_error['message']}\n\n💡 {formatted_error['suggestion']}"
            )

            # 🐛 [BUG-037 Fix B] 追加原始技术细节，防止异常被吞没导致前端只显示"❌ 分析失败"
            technical_detail = formatted_error.get("technical_detail", "")
            if technical_detail:
                user_friendly_error += f"\n\n🔍 技术详情: {technical_detail}"

            # 抛出包含友好错误信息的异常
            raise Exception(user_friendly_error) from e
        finally:
            # 🆕 确保取消事件被清理，防止内存泄漏
            # _cancel_events 字典中的 threading.Event 对象在任务完成后
            # 从所有路径（正常完成、异常、取消、超时）移除
            self.cleanup_cancel_event(task_id)

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态"""
        logger.info(f"🔍 查询任务状态: {task_id}")
        logger.info(f"🔍 当前服务实例ID: {id(self)}")
        logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

        # 强制使用全局内存管理器实例（临时解决方案）
        memory_manager = get_memory_state_manager()
        status = memory_manager.get_status_sync(task_id)
        if status:
            logger.info(f"🔍 内存状态: {status}")
        else:
            logger.info("🔍 内存状态: 未找到")

        # 查询MongoDB
        try:
            db = get_mongo_db()
            task = await db.analysis_tasks.find_one({"task_id": task_id})
            if task:
                logger.info(f"🔍 MongoDB任务状态: {task.get('status')}")

                # 🐛 [BUG-028 Fix D] 任务看门狗：检测卡死的 processing 任务
                # 如果 MongoDB 中任务 status 为 processing 但 updated_at 超过 N 分钟未更新，
                # 将 status 标记为疑似卡死，并附加提示信息。
                task_status = task.get("status")
                if task_status in ("processing", "running"):
                    updated_at = task.get("updated_at") or task.get("started_at") or task.get("created_at")
                    if isinstance(updated_at, datetime):
                        stale_threshold = timedelta(minutes=5)
                        if datetime.now() - updated_at > stale_threshold:
                            logger.warning(
                                f"⚠️ [看门狗] 任务 {task_id} 疑似卡死 "
                                f"(updated_at={updated_at.isoformat()}, 超过5分钟未更新)",
                            )
                            # 标记卡死状态（不修改数据库，仅附加提示信息）
                            task["_stale_warning"] = True
                            task["_stale_message"] = "任务可能已卡死，已超过5分钟无进度更新"

                # 🐛 [Fix A2] 返回前安全序列化，防止 MongoDB 中残存的未序列化 state
                # 导致 PydanticSerializationError（防御性编程：覆盖旧数据 + 异常降级）
                if callable(safe_serialize):
                    try:
                        task = safe_serialize(task)
                    except Exception as ser_err:
                        logger.warning(f"⚠️ [Fix A2] 序列化任务状态失败: {ser_err}")
                return task
        except Exception as e:
            logger.error(f"❌ 查询MongoDB任务状态失败: {e}")

        return status

    async def list_all_tasks(
        self, status_filter: str | None = None, limit: int = 50, skip: int = 0,
    ) -> list[dict[str, Any]]:
        """获取所有任务列表（不限用户）

        支持按状态过滤和分页。
        返回的任务列表按更新时间倒序排列。

        Args:
            status_filter: 状态过滤（可选，None=全部）
            limit: 返回数量上限（默认50）
            skip: 跳过的数量（默认0）

        Returns:
            任务列表
        """
        try:
            db = get_mongo_db()

            # 构建查询条件
            query = {}
            if status_filter:
                query["status"] = status_filter

            # 查询总数
            total = await db.analysis_tasks.count_documents(query)

            # 查询任务列表（按更新时间倒序）
            cursor = db.analysis_tasks.find(query)
            # 按更新时间倒序排列
            cursor = cursor.sort("updated_at", -1)
            # 分页
            cursor = cursor.skip(skip).limit(limit)

            tasks = []
            async for doc in cursor:
                # 将 ObjectId 转换为字符串
                doc["_id"] = str(doc["_id"])
                if "user_id" in doc and isinstance(doc["user_id"], ObjectId):
                    doc["user_id"] = str(doc["user_id"])
                # 🐛 [Fix A3] 对每个文档安全序列化，防止残留未序列化 state 导致 500
                if callable(safe_serialize):
                    try:
                        doc = safe_serialize(doc)
                    except Exception as ser_err:
                        logger.warning(f"⚠️ [Fix A3] 序列化任务文档失败: {ser_err}")
                tasks.append(doc)

            # 补齐股票名称
            tasks = self._enrich_stock_names(tasks)

            logger.info(f"✅ 获取到 {len(tasks)} 个任务（总数: {total}）")
            return tasks

        except Exception as e:
            logger.error(f"❌ 获取任务列表失败: {e}")
            return []

    async def list_user_tasks(
        self, user_id: str, status_filter: str | None = None, limit: int = 50, skip: int = 0,
    ) -> list[dict[str, Any]]:
        """获取用户任务列表

        查询指定用户的分析任务，支持按状态过滤和分页。
        返回的任务列表按更新时间倒序排列。

        Args:
            user_id: 用户ID
            status_filter: 状态过滤（可选，None=全部）
            limit: 返回数量上限（默认50）
            skip: 跳过的数量（默认0）

        Returns:
            任务列表
        """
        try:
            db = get_mongo_db()

            # 构建查询条件
            query = {"user_id": ObjectId(user_id)}
            if status_filter:
                query["status"] = status_filter

            # 查询总数
            total = await db.analysis_tasks.count_documents(query)

            # 查询任务列表
            task_status = None
            try:
                memory_manager = get_memory_state_manager()
                task_status = memory_manager.get_user_task_status_sync(user_id)
            except Exception as e:
                logger.warning(f"⚠️ 获取用户任务状态失败: {e}")

            # 构建 or 条件：MongoDB + 内存
            or_conditions: list[dict[str, Any]] = []

            # 添加 MongoDB 查询条件
            mongo_query = {"user_id": ObjectId(user_id)}
            if status_filter:
                mongo_query["status"] = status_filter
            or_conditions.append(mongo_query)

            # 添加内存查询条件（如果有）
            if task_status:
                memory_query = {"task_id": {"$in": list(task_status.keys())}}
                if status_filter:
                    memory_query["status"] = status_filter
                or_conditions.append(memory_query)

            # 合并查询
            final_query = {"$or": or_conditions} if len(or_conditions) > 1 else or_conditions[0]

            # 执行查询
            cursor = db.analysis_tasks.find(final_query)
            cursor = cursor.sort("updated_at", -1)
            cursor = cursor.skip(skip).limit(limit)

            tasks = []
            async for doc in cursor:
                # 将 ObjectId 转换为字符串
                doc["_id"] = str(doc["_id"])
                if "user_id" in doc and isinstance(doc["user_id"], ObjectId):
                    doc["user_id"] = str(doc["user_id"])

                # 如果内存中有更新的状态，使用内存中的状态
                if task_status and doc.get("task_id") in task_status:
                    mem_status = task_status[doc["task_id"]]
                    if mem_status.get("updated_at", datetime.min) > doc.get("updated_at", datetime.min):
                        doc["status"] = mem_status.get("status", doc.get("status"))
                        doc["progress"] = mem_status.get("progress", doc.get("progress"))
                        doc["updated_at"] = mem_status.get("updated_at", doc.get("updated_at"))

                # 🐛 [Fix A3] 对每个文档安全序列化，防止残留未序列化 state 导致 500
                if callable(safe_serialize):
                    try:
                        doc = safe_serialize(doc)
                    except Exception as ser_err:
                        logger.warning(f"⚠️ [Fix A3] 序列化任务文档失败: {ser_err}")

                tasks.append(doc)

            # 补齐股票名称
            tasks = self._enrich_stock_names(tasks)

            logger.info(f"✅ 获取到 {len(tasks)} 个任务（用户: {user_id}，总数: {total}）")
            return tasks

        except Exception as e:
            logger.error(f"❌ 获取用户任务列表失败: {e}")
            return []

    async def cleanup_zombie_tasks(self, max_running_hours: int = 2) -> dict[str, Any]:
        """清理僵尸任务（长时间处于 processing/running 状态的任务）

        扫描 MongoDB 中超过指定时间仍处于 running/pending 状态的任务，
        将其标记为 FAILED 并记录清理日志。

        Args:
            max_running_hours: 任务最大运行小时数（默认2小时）

        Returns:
            清理结果统计
        """
        try:
            db = get_mongo_db()
            cutoff_time = datetime.now() - timedelta(hours=max_running_hours)

            # 查找超时的 running 任务
            zombie_tasks = await db.analysis_tasks.find(
                {
                    "status": {"$in": [AnalysisStatus.PROCESSING.value, AnalysisStatus.PENDING.value]},
                    "updated_at": {"$lt": cutoff_time},
                },
            ).to_list(length=100)

            cleaned_count = 0
            for task in zombie_tasks:
                task_id = task.get("task_id")
                if task_id:
                    await db.analysis_tasks.update_one(
                        {"task_id": task_id},
                        {
                            "$set": {
                                "status": AnalysisStatus.FAILED.value,
                                "error_message": "僵尸任务：超过最大运行时间",
                                "updated_at": datetime.now(),
                            },
                        },
                    )
                    cleaned_count += 1
                    logger.info(f"🧹 [僵尸清理] 已清理僵尸任务: {task_id}")

            return {
                "cleaned_count": cleaned_count,
                "total_zombie": len(zombie_tasks),
                "message": f"已清理 {cleaned_count} 个僵尸任务",
            }
        except Exception as e:
            logger.error(f"❌ [僵尸清理] 清理失败: {e}")
            return {"cleaned_count": 0, "message": f"清理失败: {e}"}

    async def get_zombie_tasks(self, max_running_hours: int = 2) -> list[dict[str, Any]]:
        """获取僵尸任务列表（不执行清理，仅查询）"""
        try:
            db = get_mongo_db()
            cutoff_time = datetime.now() - timedelta(hours=max_running_hours)

            zombie_tasks = await db.analysis_tasks.find(
                {
                    "status": {"$in": [AnalysisStatus.PROCESSING.value, AnalysisStatus.PENDING.value]},
                    "updated_at": {"$lt": cutoff_time},
                },
            ).to_list(length=100)

            for task in zombie_tasks:
                task["_id"] = str(task["_id"])
                if "user_id" in task and isinstance(task["user_id"], ObjectId):
                    task["user_id"] = str(task["user_id"])

            return zombie_tasks
        except Exception as e:
            logger.error(f"❌ 获取僵尸任务列表失败: {e}")
            return []

    def _build_timeout_result(self, task_id: str) -> dict[str, Any]:
        """构建超时结果"""
        return {
            "task_id": task_id,
            "status": "timeout",
            "message": "分析执行超时",
            "decision": {
                "action": "持有",
                "confidence": 0.0,
                "risk_score": 0.5,
                "reasoning": "分析未能在规定时间内完成，已自动超时中止",
            },
        }

    async def _update_task_status(self, task_id: str, status: str, error_message: str | None = None) -> None:
        """更新任务状态"""
        try:
            db = get_mongo_db()
            update_data = {"status": status, "updated_at": datetime.now()}
            if error_message:
                update_data["error_message"] = error_message
            await db.analysis_tasks.update_one({"task_id": task_id}, {"$set": update_data})
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {task_id} - {e}")

    async def _save_analysis_result(self, task_id: str, result: dict[str, Any]):
        """保存分析结果（原始方法），带重试机制"""
        # 🔧 [Plan C Fix 6] 3次重试 + 指数退避
        _last_error = None
        for _attempt in range(1, 4):
            try:
                db = get_mongo_db()
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {
                        "$set": {
                            "result": result,
                            "status": AnalysisStatus.COMPLETED.value,
                            "completed_at": datetime.now(),
                            "updated_at": datetime.now(),
                        },
                    },
                )
                logger.info(f"✅ 分析结果已保存到MongoDB: {task_id}")
                return
            except Exception as e:
                _last_error = e
                if _attempt < 3:
                    _wait = 2 ** _attempt  # 2s, 4s
                    logger.warning(f"⚠️ MongoDB 保存失败（第 {_attempt}/3 次），{_wait}s 后重试: {e}")
                    await asyncio.sleep(_wait)
                else:
                    logger.error(f"❌ MongoDB 保存失败（3次重试均失败）: {task_id} - {e}")

        if _last_error:
            logger.warning(f"⚠️ [Plan C] MongoDB 不可用，分析结果仅保存在文件系统: {task_id}")
            # 不 raise，让调用方继续（文件系统保存已由 _save_analysis_result_web_style 处理）

    async def _save_analysis_result_web_style(self, task_id: str, result: dict[str, Any]):
        """保存分析结果 - 采用web目录的方式，双重保存：MongoDB + 文件系统

        MongoDB 不可用时静默降级，文件系统保存始终执行。
        """
        # 提取股票代码和名称（在所有save操作前就需要）
        stock_code = result.get("stock_code") or result.get("stock_symbol", "")
        stock_symbol = stock_code
        stock_name = result.get("stock_name", stock_code)

        # 提取概要信息
        analysis_date = result.get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
        summary = result.get("summary", "")
        recommendation = result.get("recommendation", "")

        # 提取决策信息
        decision_data = result.get("decision", result.get("detailed_analysis", {}))
        if isinstance(decision_data, dict):
            action = decision_data.get("action", "持有")
            confidence = decision_data.get("confidence", 0.0)
            target_price = decision_data.get("target_price")
            reasoning = decision_data.get("reasoning", "")
        else:
            action = "持有"
            confidence = 0.0
            target_price = None
            reasoning = ""

        # 提取报告内容
        reports = result.get("reports", {})

        # 构建web风格的报告文档
        report_doc = {
            "task_id": task_id,
            "stock_code": stock_code,
            "stock_symbol": stock_symbol,
            "stock_name": stock_name,
            "analysis_date": analysis_date,
            "summary": summary,
            "recommendation": recommendation,
            "action": action,
            "confidence": confidence,
            "target_price": target_price,
            "reasoning": reasoning,
            "reports": reports,
            # [Fix 2026-06-27] 补齐 decision 字段，防止 API 从 analysis_reports 读取时返回空对象
            "decision": result.get("decision", result.get("detailed_analysis", {})),
            "execution_time": result.get("execution_time", 0),
            "model_info": result.get("model_info", ""),
            "analysts": result.get("analysts", []),
            "research_depth": result.get("research_depth", "快速"),
            "performance_metrics": result.get("performance_metrics", {}),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        # ====== MongoDB save（失败时静默降级，不阻塞文件系统保存）======
        mongo_success = False
        try:
            db = get_mongo_db()
            # 保存到 analysis_reports 集合
            await db.analysis_reports.insert_one(report_doc)
            logger.info(f"✅ [web目录] 分析报告已保存到MongoDB: {task_id} ({stock_name})")

            # 更新任务状态
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "result.report_saved": True,
                        "status": AnalysisStatus.COMPLETED.value,
                        "completed_at": datetime.now(),
                        "updated_at": datetime.now(),
                    },
                },
            )
            mongo_success = True
        except Exception as e:
            logger.warning(f"⚠️ [web目录] MongoDB保存失败（非致命，将使用文件系统）: {task_id} - {e}")

        # ====== 文件系统保存（始终执行，不依赖MongoDB状态）======
        try:
            saved_paths = await self._save_modular_reports_to_data_dir(result, stock_symbol)
            if saved_paths:
                logger.info(f"✅ [web目录] 分模块报告已保存到data目录: {saved_paths}")
        except Exception as data_error:
            logger.warning(f"⚠️ [web目录] 保存分模块报告失败: {data_error}")

        if not mongo_success:
            logger.info(f"ℹ️ [web目录] MongoDB不可用，文件系统报告已保存至 data/analysis_reports/: {task_id}")

    async def _save_analysis_results_complete(self, task_id: str, result: dict[str, Any]):
        """完整的分析结果保存 - 完全采用web目录的双重保存方式"""
        try:
            # 保存结果
            await self._save_analysis_result_web_style(task_id, result)

            # 额外保存到分析记录
            try:
                db = get_mongo_db()
                stock_code = result.get("stock_code") or result.get("stock_symbol", "")
                stock_name = result.get("stock_name", stock_code)

                # 创建分析记录
                analysis_record = {
                    "task_id": task_id,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "analysis_date": result.get("analysis_date", datetime.now().strftime("%Y-%m-%d")),
                    "summary": result.get("summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "decision": result.get("decision", {}),
                    "reports": result.get("reports", {}),
                    "execution_time": result.get("execution_time", 0),
                    "model_info": result.get("model_info", ""),
                    "created_at": datetime.now(),
                }
                await db.analysis_records.insert_one(analysis_record)
                logger.info(f"✅ [完整保存] 分析记录已保存: {task_id}")
            except Exception as e:
                logger.warning(f"⚠️ [完整保存] 保存分析记录失败: {e}")

        except Exception as save_error:
            logger.error(f"❌ [完整保存] 保存分析报告时发生错误: {save_error!s}")
            raise

    async def _save_modular_reports_to_data_dir(self, result: dict[str, Any], stock_symbol: str) -> dict[str, str]:
        """保存分模块报告到data目录 - 完全采用web目录的文件结构"""
        try:
            data_root = project_root / "data" / "analysis_reports" / stock_symbol
            data_root.mkdir(parents=True, exist_ok=True)

            saved_paths = {}

            # 保存分模块报告
            reports = result.get("reports", {})
            if isinstance(reports, dict):
                for report_name, report_content in reports.items():
                    if isinstance(report_content, str) and len(report_content.strip()) > 10:
                        report_path = data_root / f"{report_name}.md"
                        report_path.write_text(report_content.strip(), encoding="utf-8")
                        saved_paths[report_name] = str(report_path)
                        logger.info(f"📝 [数据目录] 已保存报告: {report_path}")

            # 保存 summary 和 recommendation
            summary = result.get("summary", "")
            if summary:
                summary_path = data_root / "summary.md"
                summary_path.write_text(summary, encoding="utf-8")
                saved_paths["summary"] = str(summary_path)

            recommendation = result.get("recommendation", "")
            if recommendation:
                recommendation_path = data_root / "recommendation.md"
                recommendation_path.write_text(recommendation, encoding="utf-8")
                saved_paths["recommendation"] = str(recommendation_path)

            return saved_paths
        except Exception as e:
            logger.error(f"❌ [数据目录] 保存分模块报告失败: {e}")
            raise

    def shutdown(self):
        """关闭服务，释放资源"""
        logger.info("🛑 关闭SimpleAnalysisService...")
        try:
            self._thread_pool.shutdown(wait=False)
            self._async_progress_executor.shutdown(wait=False)
            if hasattr(self, "_graph_pool") and self._graph_pool is not None:
                self._graph_pool.shutdown(wait=False)
            logger.info("✅ 线程池已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭线程池失败: {e}")


# 全局单例
_service_instance = None
_service_lock = threading.Lock()


def get_simple_analysis_service() -> SimpleAnalysisService:
    """获取全局 SimpleAnalysisService 单例"""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = SimpleAnalysisService()
                # 注册关闭回调
                atexit.register(_service_instance.shutdown)
    return _service_instance
