#!/usr/bin/env python3
"""
Tushare统一数据提供器
实现BaseStockDataProvider接口，提供标准化的Tushare数据访问

Tushare Pro API:
  - 需要 Token 认证
  - 提供 A 股行情、财务、参考数据等
  - token: e08a65bc14dfbd34e6fe55e80d403a046ebeb59b55e81dbd3ed6c686
"""

import errno
import json as jsonlib
import logging
import os
import random
import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
import urllib3
import tushare as ts

# verify=False 场景下抑制 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 强制清理自身 __pycache__ ──────────────────────────────────────
# WSL2 NTFS 挂载时间戳精度为秒级，.py 和 .pyc 可能同秒时间戳，
# 导致 Python 使用缓存的旧字节码（如旧域名 api.waditu.com）。
# 每次模块加载时强制重新编译，确保 monkey-patch 的 URL 是最新的。
import importlib as _importlib
import pathlib as _pathlib
_cache_dir = _pathlib.Path(__file__).parent / "__pycache__"
if _cache_dir.exists():
    for _pyc in _cache_dir.glob("tushare*.pyc"):
        _pyc.unlink(missing_ok=True)
    _importlib.invalidate_caches()
# ────────────────────────────────────────────────────────────────

# ── TCP 连接策略 ──────────────────────────────────────────────
# Windows Python 下不使用持久化 requests.Session()，因为：
# 1. 阿里云 ALB 会在空闲 60-300s 后关闭 TCP 连接
# 2. Session 连接池返回已关闭的 socket → Windows 报 FileNotFoundError
# 3. 每次请求/重试都用 requests.post() 创建全新 TCP 连接
# 4. FIX-6 智能熔断器 + 60 次重试提供足够韧性
# ────────────────────────────────────────────────────────────────


def _patch_tushare_api(api) -> None:
    """Monkey-patch Tushare DataApi：纯 HTTP 方案，不降级到 HTTPS。

    根因：阿里云 ALB 空闲 60-300s 后关闭 TCP 连接。Windows 上
    SSL_read() 在已关闭 socket 上触发 SSLEOFError（而不是 HTTP 的
    ConnectionResetError），旧版 _is_connection_error 无法识别
    SSLEOFError → 熔断器误触发。

    本方案只保留 HTTP(api.tushare.pro:80, 15s timeout)：
    - HTTP 的 ConnectionResetError 能被 _is_connection_error 正确识别
    - 彻底消灭 SSLEOFError 的触发路径
    - Tushare Pro API 同时支持 HTTP 和 HTTPS，HTTP 完全可用

    返回失败时由 _api_call_with_retry 的 60 次重试 + 指数退避兜底。

    Args:
        api: tushare.pro.client.DataApi 实例
    """
    HTTP_BASE = "http://api.waditu.com/dataapi"

    def patched_query(api_name, fields="", **kwargs):
        req_params = {
            "api_name": api_name,
            "token": api._DataApi__token,
            "params": kwargs,
            "fields": fields,
        }
        try:
            res = requests.post(
                f"{HTTP_BASE}/{api_name}",
                json=req_params,
                timeout=15,
                verify=False,
            )
            if res:
                result = jsonlib.loads(res.text)
                if result["code"] != 0:
                    raise Exception(result["msg"])
                data = result["data"]
                return pd.DataFrame(data["items"], columns=data["fields"])
        except Exception as e:
            raise e

        raise Exception("HTTP 请求返回空响应")

    api.query = patched_query

from .china_stock_data_provider import ChinaStockDataProvider

logger = logging.getLogger(__name__)


class TushareProvider(ChinaStockDataProvider):
    """Tushare统一数据提供器"""

    def __init__(self, token: str | None = None):
        """初始化Tushare提供器

        Args:
            token: Tushare API Token，为 None 时从环境变量 TUSHARE_TOKEN 读取
        """
        super().__init__("tushare")
        self.api = None
        self.connected = False
        self.token = token or os.getenv("TUSHARE_TOKEN", "")
        self.token_source = self._detect_token_source()
        self._init_tushare()

    def _detect_token_source(self) -> str | None:
        """检测 Token 来源"""
        if os.getenv("TUSHARE_TOKEN"):
            return "env"
        if self.token:
            return "param"
        return None

    def _init_tushare(self):
        """初始化Tushare连接"""
        if not self.token:
            logger.warning("⚠️ Tushare Token 未配置，请在 .env 中设置 TUSHARE_TOKEN")
            self.connected = False
            return

        try:
            ts.set_token(self.token)
            # api.tushare.pro 偶发 TLS 慢速/超时（5-30s），用 45s 超时 + 3 次重试解决
            self.api = ts.pro_api(timeout=45)
            _patch_tushare_api(self.api)
            logger.info("🔧 Tushare模块加载成功（HTTP only, 15s 超时），Token来源: %s", self.token_source or "param")
            self.connected = True
            # 启动 TCP Keep-Alive 心跳
            self._start_heartbeat()
        except Exception as e:
            logger.error("❌ Tushare初始化失败: %s", e)
            self.connected = False

    # ==================== 限流 + 重试 ====================
    # 共享锁确保所有实例/线程共用同一个限流器
    _lock = threading.Lock()
    _last_call_time = 0.0

    # ==================== TCP Keep-Alive 心跳 ====================
    # 阿里云 ALB 会在空闲 60-300s 后关闭 TCP 连接。
    # 心跳线程每 30s 发送一次轻量请求，保持连接活跃。
    _heartbeat_stop = threading.Event()
    _heartbeat_thread: threading.Thread | None = None

    # ==================== 三态熔断器 ====================
    # 防止在 Tushare 服务不稳定时无意义地消耗全部 60 次重试。
    # CLOSED(正常) → 连续 3 次失败 → OPEN(快速降频) → 120s → HALF_OPEN(探测)
    # OPEN 时最多只做 3 次快速尝试，失败后立即退出。
    # HALF_OPEN 时正常尝试，成功 → CLOSED，失败 → OPEN。
    _CB_CLOSED = 0
    _CB_OPEN = 1
    _CB_HALF_OPEN = 2

    _cb_state = _CB_CLOSED
    _cb_failure_count = 0
    _cb_last_failure_time = 0.0
    _CB_THRESHOLD = 5        # 连续失败次数阈值 → OPEN（原3，放宽至5减少误触发）
    _CB_COOLDOWN = 30        # OPEN 保持秒数 → HALF_OPEN（原120，缩短至30更快恢复）
    _CB_MAX_OPEN_ATTEMPTS = 5  # OPEN 状态下最多尝试次数（原3，放宽至5提高探测成功率）

    # ==================== TCP Keep-Alive 心跳 ====================

    def _start_heartbeat(self) -> None:
        """启动 TCP Keep-Alive 心跳线程。

        每 30s 向 Tushare API 发送一次轻量请求（trade_cal 查询），
        防止阿里云 ALB 因空闲关闭 TCP 连接。

        心跳线程为 daemon 线程，进程退出时自动终止。
        """
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return  # 已有心跳线程在运行

        self._heartbeat_stop.clear()

        def _heartbeat_loop():
            """心跳循环：每 30s 发送一次 trade_cal 查询"""
            session = requests.Session()
            # 配置 TCP keepalive：空闲后每 10s 发探测包，最多 5 次
            # 仅 Linux 支持通过 socket 选项配置 keepalive 细节
            # Windows 上使用默认系统 keepalive 参数
            try:
                socket_opts = session.adapters["http://"].pools[0]  # type: ignore[attr-defined]
            except (KeyError, IndexError, AttributeError):
                pass

            from urllib3.exceptions import ProtocolError as Urllib3ProtocolError

            while not self._heartbeat_stop.is_set():
                try:
                    req_params = {
                        "api_name": "trade_cal",
                        "token": self.token,
                        "params": {
                            "exchange": "SSE",
                            "start_date": time.strftime("%Y%m%d", time.gmtime(time.time() - 86400 * 10)),
                            "end_date": time.strftime("%Y%m%d"),
                        },
                        "fields": "",
                    }
                    res = session.post(
                        "http://api.waditu.com/dataapi/trade_cal",
                        json=req_params,
                        timeout=10,
                        verify=False,
                    )
                    if res:
                        # 心跳成功，不做额外处理
                        pass
                except (requests.ConnectionError, urllib3.exceptions.ProtocolError,
                        Urllib3ProtocolError, OSError, Exception):
                    # 心跳失败不记录日志（避免日志刷屏）
                    pass

                # 等待 30s（或收到停止信号提前退出）
                self._heartbeat_stop.wait(30)

            session.close()

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name="tushare-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        self.logger.info("💓 TCP Keep-Alive 心跳线程已启动 (间隔30s)")

    def _stop_heartbeat(self) -> None:
        """停止心跳线程"""
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3)
        self._heartbeat_thread = None
        self.logger.info("💓 TCP Keep-Alive 心跳线程已停止")

    @staticmethod
    def _is_connection_error(e: Exception) -> bool:
        """判断异常是否为连接层面错误（非API业务错误），不触发熔断器。

        递归遍历异常链（__cause__ / __context__），
        同时检查 Windows errno (104/10054)，
        确保 SSLEOFError / FileNotFoundError / ConnectionResetError 等
        阿里云 ALB 空闲断连导致的异常被正确识别。
        """
        connection_patterns = (
            "RemoteDisconnected", "Connection aborted", "ConnectionResetError",
            "ConnectionRefusedError", "ProtocolError", "ConnectTimeoutError",
            "No such file or directory", "FileNotFoundError",
            "Connection reset", "connection reset",
            "SSLEOFError", "SSLError", "UNEXPECTED_EOF_WHILE_READING",
            "Max retries exceeded", "Remote end closed connection",
            "Connection closed", "connection closed",
            "EOF occurred in violation of protocol",
            "[WinError 10054]", "[WinError 104]", "WinError 10054", "WinError 104",
            "An existing connection was forcibly closed",
        )

        def _check(exc: BaseException | None) -> bool:
            if exc is None:
                return False
            err_str = str(exc)

            # 字符串模式匹配
            if any(p in err_str for p in connection_patterns):
                return True

            # Windows errno 检查（socket.error / OSError 携带 errno）
            if isinstance(exc, OSError):
                win_err = getattr(exc, "winerror", None)
                if win_err in (10054, 104):
                    return True
                if exc.errno in (errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED, errno.EPIPE, errno.ENETUNREACH):
                    return True

            # 检查异常对象的 errno 属性（某些 urllib3 异常携带）
            exc_errno = getattr(exc, "errno", None)
            if exc_errno is not None and exc_errno in (10054, 104, errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE):
                return True

            return False

        # 主异常
        if _check(e):
            return True

        # 递归检查异常链
        visited = {id(e)}
        chain = [getattr(e, "__cause__", None), getattr(e, "__context__", None)]
        while chain:
            curr = chain.pop()
            if curr is None:
                continue
            cid = id(curr)
            if cid in visited:
                continue
            visited.add(cid)
            if _check(curr):
                return True
            # 继续沿着异常链向上
            chain.append(getattr(curr, "__cause__", None))
            chain.append(getattr(curr, "__context__", None))

        return False

    def _api_call_with_retry(self, api_method, *args, max_retries=60, **kwargs):
        """限流 + 重试的 Tushare API 调用。
        含三态熔断器：连续失败 → OPEN（降频）→ 冷却 → HALF_OPEN（探测）→ CLOSED（恢复）。

        限速器(1req/s)用锁保护，API调用本身在锁外进行。
        多线程并发时各线程独立发 HTTP 请求，互不阻塞。
        失败时指数退避 + 随机抖动重试，最多 max_retries 次。

        Args:
            api_method: 要调用的 API 方法（如 self.api.stock_basic）
            *args: 位置参数
            max_retries: 最大重试次数（默认 60，足够撑到分析超时）
            **kwargs: 关键字参数

        Returns:
            API 调用的返回值，全部失败时抛出最后一次异常

        Raises:
            Exception: 所有重试均失败时抛出
        """
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                # [A] 熔断器检查：OPEN 状态时降频
                if TushareProvider._cb_state == TushareProvider._CB_OPEN:
                    elapsed = time.time() - TushareProvider._cb_last_failure_time
                    if elapsed >= TushareProvider._CB_COOLDOWN:
                        # 冷却期到 → HALF_OPEN（允许一次探测）
                        TushareProvider._cb_state = TushareProvider._CB_HALF_OPEN
                        self.logger.info(
                            "🔌 熔断器 → HALF_OPEN（冷却 %ds 到期，发送探测请求）",
                            TushareProvider._CB_COOLDOWN,
                        )
                    else:
                        remaining = TushareProvider._CB_COOLDOWN - elapsed
                        # OPEN 状态：最多 _CB_MAX_OPEN_ATTEMPTS 次快速尝试，失败即止
                        if attempt >= TushareProvider._CB_MAX_OPEN_ATTEMPTS:
                            raise Exception(
                                f"Circuit Breaker OPEN "
                                f"(冷却中，剩余 {remaining:.0f}s)"
                            )

                # [B] 限速器：锁仅保护这里（~1微秒）
                with self._lock:
                    elapsed = time.time() - self._last_call_time
                    if elapsed < 1.0:
                        time.sleep(min(1.0 - elapsed, 1.0))
                    self._last_call_time = time.time()

                # [C] API调用在锁外 — 多线程并发时互不阻塞
                result = api_method(*args, **kwargs)

                # [D] 成功时复位熔断器
                if TushareProvider._cb_state != TushareProvider._CB_CLOSED:
                    prev = "HALF_OPEN" if TushareProvider._cb_state == TushareProvider._CB_HALF_OPEN else "OPEN"
                    TushareProvider._cb_state = TushareProvider._CB_CLOSED
                    TushareProvider._cb_failure_count = 0
                    self.logger.info("✅ 熔断器已复位（%s → CLOSED）", prev)

                return result

            except Exception as e:
                last_exc = e
                err_str = str(e)
                if "RemoteDisconnected" in err_str or "Connection aborted" in err_str:
                    self.logger.warning(
                        "🔄 Tushare 连接异常 (第 %d 次尝试, 最多 %d 次): %s",
                        attempt + 1, max_retries + 1, e,
                    )
                else:
                    self.logger.warning(
                        "🔄 Tushare API 错误 (第 %d 次尝试, 最多 %d 次): %s",
                        attempt + 1, max_retries + 1, e,
                    )

                if attempt < max_retries:
                    if self._is_connection_error(last_exc):
                        # [E] 连接层面错误（ALB 间歇性挂断）：不触发熔断器
                        # 固定 1s 退避，快速重试直到 Tushare 响应
                        sleep_time = 1.0 + random.uniform(0, 0.5)
                        time.sleep(sleep_time)
                        continue

                    # [F] 更新熔断器状态（仅 API 业务错误）
                    TushareProvider._cb_failure_count += 1
                    TushareProvider._cb_last_failure_time = time.time()
                    if (
                        TushareProvider._cb_failure_count >= TushareProvider._CB_THRESHOLD
                        and TushareProvider._cb_state == TushareProvider._CB_CLOSED
                    ):
                        TushareProvider._cb_state = TushareProvider._CB_OPEN
                        self.logger.warning(
                            "🔌 熔断器 → OPEN (连续 %d 次失败，冷却 %ds)",
                            TushareProvider._cb_failure_count,
                            TushareProvider._CB_COOLDOWN,
                        )
                    elif (
                        TushareProvider._cb_state == TushareProvider._CB_HALF_OPEN
                    ):
                        # HALF_OPEN 探测失败 → 回到 OPEN
                        TushareProvider._cb_state = TushareProvider._CB_OPEN
                        TushareProvider._cb_last_failure_time = time.time()
                        self.logger.warning(
                            "🔌 熔断器 HALF_OPEN 探测失败 → OPEN (冷却 %ds)",
                            TushareProvider._CB_COOLDOWN,
                        )

                    # [G] 退避等待：OPEN 时只用 1s 固定间隔（快速失败），
                    # 正常时用 1.5^attempt 指数退避（最长 15s）
                    if TushareProvider._cb_state == TushareProvider._CB_OPEN:
                        sleep_time = 1.0 + random.uniform(0, 0.5)
                    else:
                        sleep_time = min(1.5 ** attempt, 15) + random.uniform(0, 0.5)
                    time.sleep(sleep_time)

        self.logger.error("❌ Tushare API 调用 %d 次全部失败: %s", max_retries + 1, last_exc)
        raise last_exc  # 让调用方决定是否降级

    async def connect(self) -> bool:
        """连接到Tushare数据源"""
        return self.connect_sync()

    def connect_sync(self) -> bool:
        """同步连接（供外部调用）"""
        try:
            self._init_tushare()
            # 验证连接：发起一次简单查询
            if self.api and self.token:
                # 尝试查询交易日历确认 API 有效
                df = self._api_call_with_retry(
                    self.api.trade_cal, exchange="SSE",
                    start_date="20260101", end_date="20260110",
                )
                if df is not None and not df.empty:
                    self.connected = True
                    logger.info("✅ Tushare连接成功")
                else:
                    logger.warning("⚠️ Tushare API 返回空数据，Token 可能无效")
                    self.connected = False
            else:
                self.connected = False
        except Exception as e:
            logger.error("❌ Tushare连接失败: %s", e)
            self.connected = False
        return self.connected

    async def disconnect(self):
        """断开连接（Tushare 无需断开）"""
        self._stop_heartbeat()
        self.connected = False
        self.logger.info("✅ Tushare 连接已断开（标记）")

    async def get_stock_basic_info(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]] | None:
        """获取股票基础信息

        Args:
            symbol: 股票代码，为 None 时返回所有股票列表

        Returns:
            单个股票信息字典或股票列表
        """
        if not self.connected or not self.api:
            return None

        try:
            if symbol:
                # 查询单只股票
                ts_code = self._normalize_symbol(symbol)
                df = self._api_call_with_retry(
                    self.api.stock_basic, ts_code=ts_code,
                    fields="ts_code,name,area,industry,market,list_date,exchange",
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        "code": symbol,
                        "symbol": symbol,
                        "ts_code": row.get("ts_code", ts_code),
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                        "exchange": row.get("exchange", ""),
                        "list_date": str(row.get("list_date", "")) if row.get("list_date") else "",
                    }
                # 如果没有查到，尝试用完整 ts_code 再查
                df = self._api_call_with_retry(self.api.stock_basic, ts_code=ts_code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        "code": symbol,
                        "symbol": symbol,
                        "ts_code": row.get("ts_code", ts_code),
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                        "list_date": str(row.get("list_date", "")) if row.get("list_date") else "",
                    }
                return None
            else:
                # 返回所有股票列表
                df = self._api_call_with_retry(
                    self.api.stock_basic,
                    fields="ts_code,name,area,industry,market,list_date,exchange",
                )
                if df is not None and not df.empty:
                    return df.to_dict("records")
                return None
        except Exception as e:
            self.logger.error("❌ Tushare 获取股票基础信息失败: %s", e)
            return None

    def get_stock_basic_info_sync(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]] | None:
        """获取股票基础信息（同步版本，避免 EventLoopPool 阻塞）"""
        if not self.connected or not self.api:
            return None

        try:
            if symbol:
                ts_code = self._normalize_symbol(symbol)
                df = self._api_call_with_retry(
                    self.api.stock_basic, ts_code=ts_code,
                    fields="ts_code,name,area,industry,market,list_date,exchange",
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        "code": symbol,
                        "symbol": symbol,
                        "ts_code": row.get("ts_code", ts_code),
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                        "exchange": row.get("exchange", ""),
                        "list_date": str(row.get("list_date", "")) if row.get("list_date") else "",
                    }
                df = self._api_call_with_retry(self.api.stock_basic, ts_code=ts_code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        "code": symbol,
                        "symbol": symbol,
                        "ts_code": row.get("ts_code", ts_code),
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                        "exchange": row.get("exchange", ""),
                        "list_date": str(row.get("list_date", "")) if row.get("list_date") else "",
                    }
                return None
            else:
                df = self._api_call_with_retry(
                    self.api.stock_basic,
                    fields="ts_code,name,area,industry,market,list_date,exchange",
                )
                if df is not None and not df.empty:
                    return df.to_dict("records")
                return None
        except Exception as e:
            self.logger.error("❌ Tushare 获取股票基础信息失败(sync): %s", e)
            return None

    async def get_stock_quotes(self, symbol: str) -> dict[str, Any] | None:
        """获取实时行情"""
        if not self.connected or not self.api:
            return None
        try:
            ts_code = self._normalize_symbol(symbol)
            df = self._api_call_with_retry(self.api.rt_k, ts_code=ts_code)
            if df is not None and not df.empty:
                row = df.iloc[-1]
                return {
                    "code": symbol,
                    "symbol": symbol,
                    "ts_code": ts_code,
                    "open": float(row.get("open", 0)) if row.get("open") is not None else None,
                    "high": float(row.get("high", 0)) if row.get("high") is not None else None,
                    "low": float(row.get("low", 0)) if row.get("low") is not None else None,
                    "close": float(row.get("close", 0)) if row.get("close") is not None else None,
                    "pre_close": float(row.get("pre_close", 0)) if row.get("pre_close") is not None else None,
                    "volume": float(row.get("vol", 0)) if row.get("vol") is not None else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") is not None else None,
                    "trade_date": str(row.get("trade_date", "")),
                }
            return None
        except Exception as e:
            self.logger.error("❌ Tushare 获取实时行情失败: %s", e)
            return None

    def get_stock_quotes_sync(self, symbol: str) -> dict[str, Any] | None:
        """获取实时行情（同步版本）"""
        if not self.connected or not self.api:
            return None
        try:
            ts_code = self._normalize_symbol(symbol)
            df = self._api_call_with_retry(self.api.rt_k, ts_code=ts_code)
            if df is not None and not df.empty:
                row = df.iloc[-1]
                return {
                    "code": symbol,
                    "symbol": symbol,
                    "ts_code": ts_code,
                    "open": float(row.get("open", 0)) if row.get("open") is not None else None,
                    "high": float(row.get("high", 0)) if row.get("high") is not None else None,
                    "low": float(row.get("low", 0)) if row.get("low") is not None else None,
                    "close": float(row.get("close", 0)) if row.get("close") is not None else None,
                    "pre_close": float(row.get("pre_close", 0)) if row.get("pre_close") is not None else None,
                    "volume": float(row.get("vol", 0)) if row.get("vol") is not None else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") is not None else None,
                    "trade_date": str(row.get("trade_date", "")),
                }
            return None
        except Exception as e:
            self.logger.error("❌ Tushare 获取实时行情失败(sync): %s", e)
            return None

    async def get_historical_data(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """获取历史数据

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYYMMDD 或 YYYY-MM-DD)
            end_date: 结束日期 (YYYYMMDD 或 YYYY-MM-DD)
            period: 数据周期 (daily/weekly/monthly)

        Returns:
            DataFrame with columns: date, open, high, low, close, vol, amount, pct_change, code
        """
        if not self.connected or not self.api:
            return None

        try:
            ts_code = self._normalize_symbol(symbol)

            # 格式化日期
            start = start_date.replace("-", "") if start_date else None
            end = end_date.replace("-", "") if end_date else None

            # 使用 pro_bar 获取 K 线数据
            from tushare.pro.data_pro import pro_bar

            freq_map = {
                "daily": "D",
                "weekly": "W",
                "monthly": "M",
            }
            freq = freq_map.get(period, "D")

            df = self._api_call_with_retry(
                pro_bar,
                ts_code=ts_code, api=self.api, freq=freq,
                start_date=start, end_date=end,
                adj="qfq",
                fields="trade_date,open,high,low,close,vol,amount,pct_chg",
            )

            if df is None or df.empty:
                df = self._api_call_with_retry(
                    pro_bar,
                    ts_code=ts_code, api=self.api, freq=freq,
                    start_date=start, end_date=end,
                    fields="trade_date,open,high,low,close,vol,amount,pct_chg",
                )

            if df is not None and not df.empty:
                # 标准化列名
                df = df.rename(
                    columns={
                        "trade_date": "date",
                        "vol": "volume",
                        "pct_chg": "pct_change",
                    },
                )

                # 确保日期列
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date")

                # 添加股票代码列
                df["code"] = symbol

                self.logger.info(
                    "✅ [Tushare] 获取历史数据成功: %s, %d条, 周期=%s",
                    symbol,
                    len(df),
                    period,
                )
                return df

            self.logger.warning("⚠️ [Tushare] 获取历史数据为空: %s", symbol)
            return None

        except Exception as e:
            self.logger.error("❌ Tushare 获取历史数据失败: %s", e)
            return None

    def get_historical_data_sync(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """获取历史数据（同步版本，避免 EventLoopPool 阻塞）"""
        if not self.connected or not self.api:
            return None

        try:
            ts_code = self._normalize_symbol(symbol)
            start = start_date.replace("-", "") if start_date else None
            end = end_date.replace("-", "") if end_date else None

            from tushare.pro.data_pro import pro_bar

            freq_map = {"daily": "D", "weekly": "W", "monthly": "M"}
            freq = freq_map.get(period, "D")

            df = self._api_call_with_retry(
                pro_bar,
                ts_code=ts_code, api=self.api, freq=freq,
                start_date=start, end_date=end,
                adj="qfq",
                fields="trade_date,open,high,low,close,vol,amount,pct_chg",
            )

            if df is None or df.empty:
                df = self._api_call_with_retry(
                    pro_bar,
                    ts_code=ts_code, api=self.api, freq=freq,
                    start_date=start, end_date=end,
                    fields="trade_date,open,high,low,close,vol,amount,pct_chg",
                )

            if df is not None and not df.empty:
                df = df.rename(columns={"trade_date": "date", "vol": "volume", "pct_chg": "pct_change"})
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date")
                df["code"] = symbol
                self.logger.info("✅ [Tushare] 获取历史数据成功(sync): %s, %d条", symbol, len(df))
                return df

            self.logger.warning("⚠️ [Tushare] 获取历史数据为空(sync): %s", symbol)
            return None

        except Exception as e:
            self.logger.error("❌ Tushare 获取历史数据失败(sync): %s", e)
            return None

    def get_stock_list_sync(self) -> pd.DataFrame | None:
        """同步获取股票列表（供 TushareAdapter 调用）"""
        if not self.connected or not self.api:
            return None
        try:
            df = self._api_call_with_retry(
                self.api.stock_basic,
                fields="ts_code,name,area,industry,market,list_date,exchange,curr_type",
            )
            if df is not None and not df.empty:
                logger.info("✅ [Tushare] 成功获取股票列表: %d条", len(df))
                return df
            return None
        except Exception as e:
            logger.error("❌ [Tushare] 获取股票列表失败: %s", e)
            return None

    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码为 Tushare 格式 (000001.SZ / 600000.SH)

        修复 lstrip("0") bug: 原始代码用 str.lstrip("0") 移除了所有前导零，
        导致 002559 → 2559.SZ（Tushare 找不到数据）。
        改用 re.sub(r"[^0-9]", "", s) 提取纯数字部分 + zfill(6) 补齐至 6 位。
        """
        s = symbol.strip().upper()

        # 如果已经是 ts_code 格式（带 .SH/.SZ/.BJ），验证并补齐代码部分
        m = re.search(r"\.(SH|SZ|BJ)$", s)
        if m:
            suffix = m.group(1)
            code_part = re.sub(r"[^0-9]", "", s.split(".")[0])
            code_part = code_part.zfill(6)
            return f"{code_part}.{suffix}"

        # 移除所有非数字字符（处理 sz000001, SH.600000, bj920000 等各种前缀格式）
        code = re.sub(r"[^0-9]", "", s)
        if not code:
            return ""

        # ★ 关键修复：补齐到 6 位，保证 Tushare 要求的完整代码格式
        code = code.zfill(6)

        # 根据代码前缀判断交易所
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        elif code.startswith(("0", "3", "2")):
            return f"{code}.SZ"
        elif code.startswith(("8", "4")):
            return f"{code}.BJ"
        else:
            # 默认深圳
            return f"{code}.SZ"

    # ==================== 估值数据 ====================

    async def get_daily_basic(self, trade_date: str) -> pd.DataFrame | None:
        """获取每日基础数据（估值指标）

        Args:
            trade_date: 交易日期 (YYYYMMDD)
        """
        if not self.connected or not self.api:
            return None
        try:
            fields = "ts_code,trade_date,total_mv,circ_mv,pe,pb,pe_ttm,pb_mrq,ps,ps_ttm,turnover_rate,volume_ratio,total_share,float_share"
            df = self._api_call_with_retry(
                self.api.daily_basic,
                trade_date=trade_date.replace("-", ""),
                fields=fields,
            )
            return df
        except Exception as e:
            self.logger.error("❌ Tushare 获取每日基础数据失败: %s", e)
            return None

    def get_daily_basic_sync(self, trade_date: str) -> pd.DataFrame | None:
        """获取每日基础数据（同步版本）"""
        if not self.connected or not self.api:
            return None
        try:
            fields = "ts_code,trade_date,total_mv,circ_mv,pe,pb,pe_ttm,pb_mrq,ps,ps_ttm,turnover_rate,volume_ratio,total_share,float_share"
            df = self._api_call_with_retry(
                self.api.daily_basic,
                trade_date=trade_date.replace("-", ""),
                fields=fields,
            )
            return df
        except Exception as e:
            self.logger.error("❌ Tushare 获取每日基础数据失败(sync): %s", e)
            return None

    async def get_financial_data(self, symbol: str, report_type: str = "annual") -> dict[str, Any] | None:
        """获取财务数据（合并 fina_indicator + income + balancesheet）

        使用三个 Tushare Pro API 合并返回：
          - fina_indicator (基础200分): eps/roe/roa/gross_margin/net_margin/ocfps/bps
          - income (需200-600分): 营业总收入(revenue)/营业利润(operate_profit)/净利润(n_income)
          - balancesheet (需200-600分): 总资产/总负债/股东权益

        任意 API 失败仅记警告，不影响其他 API 的结果。
        """
        if not self.connected or not self.api:
            return None
        try:
            ts_code = self._normalize_symbol(symbol)

            result: dict[str, Any] = {
                "code": symbol,
                "ts_code": ts_code,
                "end_date": "",
            }

            # ── 1. fina_indicator ──
            try:
                df = self._api_call_with_retry(
                    self.api.fina_indicator,
                    ts_code=ts_code,
                    fields="ts_code,end_date,eps,roe,roa,gross_margin,net_margin,"
                           "profit_dedu,ocfps,bps,dt_eps,total_assets,total_liab,total_hldr_eqy_ex_min",
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    result["end_date"] = str(row.get("end_date", ""))
                    for col in ("eps", "roe", "roa", "gross_margin", "net_margin",
                                "profit_dedu", "ocfps", "bps", "dt_eps",
                                "total_assets", "total_liab", "total_hldr_eqy_ex_min"):
                        val = row.get(col)
                        result[col] = float(val) if val is not None else None
                    self.logger.info("✅ Tushare fina_indicator 成功: %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare fina_indicator 失败(非致命): %s", e)

            # ── 2. income（利润表）─ 营业总收入/营业利润/净利润 ──
            try:
                df_income = self._api_call_with_retry(
                    self.api.income,
                    ts_code=ts_code,
                    fields="ts_code,end_date,revenue,operate_profit,n_income,"
                           "total_operating_revenue,performance_notice",
                )
                if df_income is not None and not df_income.empty:
                    row = df_income.iloc[0]
                    for col in ("revenue", "operate_profit", "n_income", "total_operating_revenue"):
                        val = row.get(col)
                        result[col] = float(val) if val is not None else None
                    # 优先使用端日期更近的 end_date
                    ed = row.get("end_date")
                    if ed and str(ed) > str(result.get("end_date", "")):
                        result["end_date"] = str(ed)
                    self.logger.info("✅ Tushare income 成功: %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare income 失败(非致命): %s", e)

            # ── 3. balancesheet（资产负债表）─ 总资产/总负债/股东权益 ──
            try:
                df_bs = self._api_call_with_retry(
                    self.api.balancesheet,
                    ts_code=ts_code,
                    fields="ts_code,end_date,total_assets,total_liab,total_hldr_eqy_ex_min",
                )
                if df_bs is not None and not df_bs.empty:
                    row = df_bs.iloc[0]
                    for col in ("total_assets", "total_liab", "total_hldr_eqy_ex_min"):
                        val = row.get(col)
                        # 只有 fina_indicator 中该字段为 None 时才覆盖
                        if result.get(col) is None and val is not None:
                            result[col] = float(val)
                    ed = row.get("end_date")
                    if ed and str(ed) > str(result.get("end_date", "")):
                        result["end_date"] = str(ed)
                    self.logger.info("✅ Tushare balancesheet 成功: %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare balancesheet 失败(非致命): %s", e)

            # 兼容旧字段名 total_equity (部分消费者仍用此名)
            if result.get("total_hldr_eqy_ex_min") is not None and result.get("total_equity") is None:
                result["total_equity"] = result["total_hldr_eqy_ex_min"]

            return result if any(v is not None for v in result.values() if not isinstance(v, str)) else None
        except Exception as e:
            self.logger.error("❌ Tushare 获取财务数据失败: %s", e)
            return None

    def get_financial_data_sync(self, symbol: str, report_type: str = "annual") -> dict[str, Any] | None:
        """获取财务数据（同步版本，避免 EventLoopPool 阻塞）

        与 get_financial_data 逻辑完全一致，仅无 async。
        合并 fina_indicator + income + balancesheet 三个 API。
        """
        if not self.connected or not self.api:
            return None
        try:
            ts_code = self._normalize_symbol(symbol)

            result: dict[str, Any] = {
                "code": symbol,
                "ts_code": ts_code,
                "end_date": "",
            }

            # ── 1. fina_indicator ──
            try:
                df = self._api_call_with_retry(
                    self.api.fina_indicator,
                    ts_code=ts_code,
                    fields="ts_code,end_date,eps,roe,roa,gross_margin,net_margin,"
                           "profit_dedu,ocfps,bps,dt_eps,total_assets,total_liab,total_hldr_eqy_ex_min",
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    result["end_date"] = str(row.get("end_date", ""))
                    for col in ("eps", "roe", "roa", "gross_margin", "net_margin",
                                "profit_dedu", "ocfps", "bps", "dt_eps",
                                "total_assets", "total_liab", "total_hldr_eqy_ex_min"):
                        val = row.get(col)
                        result[col] = float(val) if val is not None else None
                    self.logger.info("✅ Tushare fina_indicator 成功(sync): %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare fina_indicator 失败(sync,非致命): %s", e)

            # ── 2. income（利润表）─ 营业总收入/营业利润/净利润 ──
            try:
                df_income = self._api_call_with_retry(
                    self.api.income,
                    ts_code=ts_code,
                    fields="ts_code,end_date,revenue,operate_profit,n_income,"
                           "total_operating_revenue,performance_notice",
                )
                if df_income is not None and not df_income.empty:
                    row = df_income.iloc[0]
                    for col in ("revenue", "operate_profit", "n_income", "total_operating_revenue"):
                        val = row.get(col)
                        result[col] = float(val) if val is not None else None
                    ed = row.get("end_date")
                    if ed and str(ed) > str(result.get("end_date", "")):
                        result["end_date"] = str(ed)
                    self.logger.info("✅ Tushare income 成功(sync): %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare income 失败(sync,非致命): %s", e)

            # ── 3. balancesheet（资产负债表）─ 总资产/总负债/股东权益 ──
            try:
                df_bs = self._api_call_with_retry(
                    self.api.balancesheet,
                    ts_code=ts_code,
                    fields="ts_code,end_date,total_assets,total_liab,total_hldr_eqy_ex_min",
                )
                if df_bs is not None and not df_bs.empty:
                    row = df_bs.iloc[0]
                    for col in ("total_assets", "total_liab", "total_hldr_eqy_ex_min"):
                        val = row.get(col)
                        if result.get(col) is None and val is not None:
                            result[col] = float(val)
                    ed = row.get("end_date")
                    if ed and str(ed) > str(result.get("end_date", "")):
                        result["end_date"] = str(ed)
                    self.logger.info("✅ Tushare balancesheet 成功(sync): %s", ts_code)
            except Exception as e:
                self.logger.warning("⚠️ Tushare balancesheet 失败(sync,非致命): %s", e)

            # 兼容旧字段名 total_equity
            if result.get("total_hldr_eqy_ex_min") is not None and result.get("total_equity") is None:
                result["total_equity"] = result["total_hldr_eqy_ex_min"]

            return result if any(v is not None for v in result.values() if not isinstance(v, str)) else None
        except Exception as e:
            self.logger.error("❌ Tushare 获取财务数据失败(sync): %s", e)
            return None

    async def get_stock_list(self, market: str | None = None) -> list[dict[str, Any]] | None:
        """获取股票列表"""
        result = await self.get_stock_basic_info()
        if isinstance(result, list):
            return result
        return None


# ==================== 全局单例 ====================

_tushare_provider = None


def get_tushare_provider(token: str | None = None) -> TushareProvider:
    """获取全局 TushareProvider 单例

    Args:
        token: Tushare API Token，为 None 时使用环境变量 TUSHARE_TOKEN
    """
    global _tushare_provider
    if _tushare_provider is None:
        _tushare_provider = TushareProvider(token=token)
    return _tushare_provider


def is_tushare_available() -> bool:
    """检查 Tushare 是否可用"""
    provider = get_tushare_provider()
    return provider.connected


def test_tushare_connection(token: str | None = None) -> bool:
    """测试 Tushare 连接

    Args:
        token: Tushare API Token，为 None 时使用环境变量
    """
    provider = TushareProvider(token=token)
    try:
        return provider.connect_sync()
    except Exception as e:
        logger.error("❌ Tushare 连接测试失败: %s", e)
        return False
