#!/usr/bin/env python3
"""
数据源管理器
统一管理中国股票数据源的选择和切换
主数据源：Tushare Pro（专业A股数据）
"""

import atexit
import logging
import os
import time
import warnings
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

# 导入统一数据源编码
import concurrent.futures

# 多源主动探测（Plan 3 Fix B）
from .data_source_prober import MultiSourceProber, init_default_probes

# 导入数据库管理器
from tradingagents.config.database_manager import get_database_manager
from tradingagents.constants import DataSourceCode

# 导入共享事件循环池
from .providers.event_loop_pool import get_event_loop_pool
from .providers.provider_registry import get_provider_registry


class ChinaDataSource(Enum):
    """
    中国股票数据源枚举

    注意：这个枚举与 tradingagents.constants.DataSourceCode 保持同步
    值使用统一的数据源编码

    主数据源：Tushare Pro
    """

    MONGODB = DataSourceCode.MONGODB  # MongoDB数据库缓存（最高优先级）
    TUSHARE = DataSourceCode.TUSHARE  # Tushare Pro（主数据源）


class DataSourceManager:
    """数据源管理器"""

    def __init__(self):
        """初始化数据源管理器"""
        # [Loop3-H1] 构造函数只做轻量配置加载，将数据库连接延迟到首次使用（lazy init）
        self.use_mongodb_cache = self._check_mongodb_enabled()

        # 可用数据源列表初始为 None，首次访问时通过 property 懒加载
        self._available_sources = None

        self.default_source = self._get_default_source()
        self.current_source = self.default_source


        # [Plan 3 Fix B] 多源主动探测管理器
        self._prober: MultiSourceProber | None = None

        # 初始化统一缓存管理器
        self.cache_manager = None
        self.cache_enabled = False
        try:
            from .cache import get_cache

            self.cache_manager = get_cache()
            self.cache_enabled = True
            logger.info("✅ 统一缓存管理器已启用")
        except Exception as e:
            logger.warning(f"⚠️ 统一缓存管理器初始化失败: {e}", exc_info=True)

        # 🆕 Bug #15: 共享线程池执行器，避免每次调用创建新线程
        self._async_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ds_async")

        logger.info("📊 数据源管理器初始化完成（Tushare Pro 主数据源）")
        logger.info(f"   MongoDB缓存: {'✅ 已启用' if self.use_mongodb_cache else '❌ 未启用'}")
        logger.info(f"   统一缓存: {'✅ 已启用' if self.cache_enabled else '❌ 未启用'}")
        logger.info(f"   默认数据源: {self.default_source.value}")

    # [Loop3-H1] 使用 property 实现 lazy init，避免构造函数中连接 MongoDB
    @property
    def available_sources(self) -> list[ChinaDataSource]:
        """可用数据源列表（懒加载，首次访问时执行检查）"""
        if self._available_sources is None:
            try:
                self._available_sources = self._check_available_sources()
            except Exception as e:
                logger.error(f"❌ 检查可用数据源时发生异常: {e}", exc_info=True)
                self._available_sources = []
        return self._available_sources  # type: ignore[no-any-return]

    @available_sources.setter
    def available_sources(self, value: list[ChinaDataSource]):
        """设置可用数据源列表"""
        self._available_sources = value

    def shutdown(self):
        """优雅关闭，释放线程池资源"""
        if hasattr(self, "_async_executor") and self._async_executor is not None:
            self._async_executor.shutdown(wait=True)
            # [FIX P1] 保护 logging 调用，防止 I/O 关闭后写入导致 ValueError
            from contextlib import suppress

            with suppress(ValueError, RuntimeError):
                logger.info("✅ DataSourceManager 线程池已关闭")

    def _check_mongodb_enabled(self) -> bool:
        """检查是否启用MongoDB缓存"""
        from tradingagents.config.runtime_settings import use_app_cache_enabled

        return use_app_cache_enabled()

    def _get_data_source_priority_order(self, symbol: str | None = None) -> list[ChinaDataSource]:
        """
        获取数据源优先级顺序（使用 ProviderRegistry）

        Args:
            symbol: 股票代码，用于识别市场类型

        Returns:
            按优先级排序的数据源列表
        """
        get_provider_registry()
        available = self.available_sources

        # 按注册表优先级排序可用数据源
        priority_map = {
            ChinaDataSource.MONGODB: 100,
            ChinaDataSource.TUSHARE: 90,  # Tushare 主数据源
        }

        sorted_sources = sorted(available, key=lambda s: priority_map.get(s, 0), reverse=True)
        return sorted_sources

    def _identify_market_category(self, symbol: str | None) -> str | None:
        """
        识别股票代码所属的市场分类

        Args:
            symbol: 股票代码

        Returns:
            市场分类ID（a_shares/us_stocks/hk_stocks），如果无法识别则返回None
        """
        if not symbol:
            return None

        try:
            from tradingagents.utils.stock_utils import StockMarket, StockUtils

            market = StockUtils.identify_stock_market(symbol)

            # 映射到市场分类ID
            market_mapping = {
                StockMarket.CHINA_A: "a_shares",
                StockMarket.US: "us_stocks",
                StockMarket.HONG_KONG: "hk_stocks",
            }

            category = market_mapping.get(market)
            if category:
                logger.debug(f"🔍 [市场识别] {symbol} → {category}")
            return category
        except Exception as e:
            logger.warning(f"⚠️ [市场识别] 识别失败: {e}", exc_info=True)
            return None

    def _get_prober(self) -> MultiSourceProber:
        """获取多源探测管理器（延迟初始化，首次访问时探测）"""
        if self._prober is None:
            self._prober = init_default_probes()
        return self._prober

    def probe_sources(self) -> list[str]:
        """主动探测所有数据源，返回按评分排序的列表

        Returns:
            数据源名称列表，按评分从高到低
        """
        prober = self._get_prober()
        return prober.get_ranked()

    def _get_default_source(self) -> ChinaDataSource:
        """获取默认数据源

        优先级：
        1. Tushare Pro（如果 Token 已配置）
        2. MongoDB 缓存（如果启用）
        """
        # Tushare 是主数据源，Token 已配置时优先使用
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            logger.info("✅ [默认数据源] Tushare Pro（Token已配置）")
            return ChinaDataSource.TUSHARE

        # 如果启用MongoDB缓存，MongoDB作为次选数据源
        if self.use_mongodb_cache:
            logger.info("✅ [默认数据源] MongoDB缓存（Tushare Token未配置）")
            return ChinaDataSource.MONGODB

        logger.info("✅ [默认数据源] Tushare Pro")
        return ChinaDataSource.TUSHARE

    def get_fundamentals_data(self, symbol: str) -> str:
        """
        获取基本面数据
        优先级：MongoDB → BaoStock → 生成分析

        Args:
            symbol: 股票代码

        Returns:
            str: 基本面分析报告
        """
        logger.info(
            f"📊 [数据来源: {self.current_source.value}] 开始获取基本面数据: {symbol}",
            extra={
                "symbol": symbol,
                "data_source": self.current_source.value,
                "event_type": "fundamentals_fetch_start",
            },
        )

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_fundamentals(symbol)
            else:
                result = self._generate_fundamentals_analysis(symbol)

            # 检查结果
            duration = time.time() - start_time
            result_length = len(result) if result else 0

            if result and "❌" not in result:
                logger.info(
                    f"✅ [数据来源: {self.current_source.value}] 成功获取基本面数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                    extra={
                        "symbol": symbol,
                        "data_source": self.current_source.value,
                        "duration": duration,
                        "result_length": result_length,
                        "event_type": "fundamentals_fetch_success",
                    },
                )
                return result
            logger.warning(
                f"⚠️ [数据来源: {self.current_source.value}失败] 基本面数据质量异常，尝试降级: {symbol}",
                extra={
                    "symbol": symbol,
                    "data_source": self.current_source.value,
                    "event_type": "fundamentals_fetch_fallback",
                },
            )
            return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"❌ [数据来源: {self.current_source.value}异常] 获取基本面数据失败: {symbol} - {e}",
                extra={
                    "symbol": symbol,
                    "data_source": self.current_source.value,
                    "duration": duration,
                    "error": str(e),
                    "event_type": "fundamentals_fetch_exception",
                },
                exc_info=True,
            )
            return self._try_fallback_fundamentals(symbol)

    def get_news_data(self, symbol: str | None = None, hours_back: int = 24, limit: int = 20) -> list[dict[str, Any]]:
        """
        获取新闻数据的统一接口
        优先级：MongoDB（暂不支持其他数据源）

        Args:
            symbol: 股票代码，为空则获取市场新闻
            hours_back: 回溯小时数
            limit: 返回数量限制

        Returns:
            List[Dict]: 新闻数据列表
        """
        logger.info(
            f"📰 [数据来源: {self.current_source.value}] 开始获取新闻数据: {symbol or '市场新闻'}, 回溯{hours_back}小时",
            extra={
                "symbol": symbol,
                "hours_back": hours_back,
                "limit": limit,
                "data_source": self.current_source.value,
                "event_type": "news_fetch_start",
            },
        )

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_news(symbol, hours_back, limit)  # type: ignore[arg-type]
            else:
                # 当前数据源暂不支持新闻数据
                logger.warning(f"⚠️ 数据源 {self.current_source.value} 不支持新闻数据")
                result = []

            # 检查结果
            duration = time.time() - start_time
            result_count = len(result) if result else 0

            if result and result_count > 0:
                logger.info(
                    f"✅ [数据来源: {self.current_source.value}] 成功获取新闻数据: {symbol or '市场新闻'} ({result_count}条, 耗时{duration:.2f}秒)",
                    extra={
                        "symbol": symbol,
                        "data_source": self.current_source.value,
                        "news_count": result_count,
                        "duration": duration,
                        "event_type": "news_fetch_success",
                    },
                )
                return result
            logger.warning(
                f"⚠️ [数据来源: {self.current_source.value}] 未获取到新闻数据: {symbol or '市场新闻'}，尝试降级",
                extra={
                    "symbol": symbol,
                    "data_source": self.current_source.value,
                    "duration": duration,
                    "event_type": "news_fetch_fallback",
                },
            )
            return self._try_fallback_news(symbol, hours_back, limit)  # type: ignore[arg-type]

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"❌ [数据来源: {self.current_source.value}异常] 获取新闻数据失败: {symbol or '市场新闻'} - {e}",
                extra={
                    "symbol": symbol,
                    "data_source": self.current_source.value,
                    "duration": duration,
                    "error": str(e),
                    "event_type": "news_fetch_exception",
                },
                exc_info=True,
            )
            return self._try_fallback_news(symbol, hours_back, limit)  # type: ignore[arg-type]

    def _check_available_sources(self) -> list[ChinaDataSource]:
        """
        检查可用的数据源

        主数据源：Tushare Pro

        Returns:
            可用且已启用的数据源列表
        """
        available = []

        # 🔥 从数据库读取数据源配置，获取启用状态
        enabled_sources_in_db = set()
        try:
            from app.core.database import get_mongo_db_sync

            db = get_mongo_db_sync()
            config_collection = db.system_configs

            # 获取最新的激活配置
            config_data = config_collection.find_one({"is_active": True}, sort=[("version", -1)])

            if config_data and config_data.get("data_source_configs"):
                data_source_configs = config_data.get("data_source_configs", [])

                # 提取已启用的数据源类型
                for ds in data_source_configs:
                    if ds.get("enabled", True):
                        ds_type = ds.get("type", "").lower()
                        enabled_sources_in_db.add(ds_type)

                logger.info(f"✅ [数据源配置] 从数据库读取到已启用的数据源: {enabled_sources_in_db}")
            else:
                logger.warning("⚠️ [数据源配置] 数据库中没有数据源配置，仅检查 Tushare 和 MongoDB")
                # 如果数据库中没有配置，默认检查 tushare 和 mongodb
                enabled_sources_in_db = {"tushare", "mongodb"}
        except Exception as e:
            logger.warning(f"⚠️ [数据源配置] 从数据库读取失败: {e}，仅检查 Tushare", exc_info=True)
            enabled_sources_in_db = {"tushare", "mongodb"}

        # 检查MongoDB（最高优先级）— 带真实 ping 测试
        if self.use_mongodb_cache and "mongodb" in enabled_sources_in_db:
            try:
                from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

                adapter = get_mongodb_cache_adapter()
                # [FIX P0] 添加真实连通性验证（ping），而非仅检查 adapter.db is not None
                if adapter.use_app_cache and adapter.db is not None:
                    adapter.db.command("ping")  # 真实 ping 测试
                    available.append(ChinaDataSource.MONGODB)
                    logger.info("✅ MongoDB数据源可用且已启用（ping通过）")
                else:
                    logger.warning("⚠️ MongoDB数据源不可用: 数据库未连接")
            except Exception as e:
                logger.warning(f"⚠️ MongoDB数据源不可用: {e}", exc_info=True)
        elif self.use_mongodb_cache and "mongodb" not in enabled_sources_in_db:
            logger.info("ℹ️ MongoDB数据源已在数据库中禁用")

        # 从数据库读取数据源配置
        self._get_datasource_configs_from_db()

        # 检查 Tushare（主数据源）
        # 策略: Token 已配置时始终可用，不受 DB 配置限制
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            try:
                import tushare as ts

                available.append(ChinaDataSource.TUSHARE)
                logger.info("✅ Tushare数据源可用（Token已配置，主数据源）")
            except ImportError:
                logger.warning("⚠️ Tushare数据源不可用: tushare库未安装，请执行 pip install tushare", exc_info=True)
        elif "tushare" in enabled_sources_in_db:
            logger.warning("⚠️ Tushare数据源已在数据库中启用但 Token 未配置")
        else:
            logger.info("ℹ️ Tushare数据源: Token 未配置且数据库未启用")

        # BaoStock and ZZShare providers have been removed
        pass

        return available

    def _get_datasource_configs_from_db(self) -> dict:
        """从数据库读取数据源配置（包括 API Key）"""
        try:
            from app.core.database import get_mongo_db_sync

            db = get_mongo_db_sync()

            # 从 system_configs 集合读取激活的配置
            config = db.system_configs.find_one({"is_active": True})
            if not config:
                return {}

            # 提取数据源配置
            datasource_configs = config.get("data_source_configs", [])

            # 构建配置字典 {数据源名称: {api_key, api_secret, ...}}
            result = {}
            for ds_config in datasource_configs:
                name = ds_config.get("name", "").lower()
                result[name] = {
                    "api_key": ds_config.get("api_key", ""),
                    "api_secret": ds_config.get("api_secret", ""),
                    "config_params": ds_config.get("config_params", {}),
                }

            return result
        except Exception as e:
            logger.warning(f"⚠️ 从数据库读取数据源配置失败: {e}", exc_info=True)
            return {}

    def get_current_source(self) -> ChinaDataSource:
        """获取当前数据源"""
        return self.current_source  # type: ignore[no-any-return]

    def set_current_source(self, source: ChinaDataSource) -> bool:
        """设置当前数据源"""
        if source in self.available_sources:
            self.current_source = source
            logger.info(f"✅ 数据源已切换到: {source.value}")
            return True
        logger.error(f"❌ 数据源不可用: {source.value}")
        return False

    def get_data_adapter(self):
        """获取当前数据源的适配器"""
        if self.current_source == ChinaDataSource.MONGODB:
            return self._get_mongodb_adapter()
        if self.current_source == ChinaDataSource.TUSHARE:
            return self._get_tushare_adapter()
        raise ValueError(f"不支持的数据源: {self.current_source}")

    def _get_mongodb_adapter(self):
        """获取MongoDB适配器"""
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            return get_mongodb_cache_adapter()
        except ImportError as e:
            logger.error(f"❌ MongoDB适配器导入失败: {e}", exc_info=True)
            return None

    def _get_tushare_adapter(self):
        """获取Tushare适配器"""
        try:
            from .providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            # 确保连接
            provider.connect_sync()
            return provider
        except ImportError as e:
            logger.error(f"❌ Tushare适配器导入失败: {e}", exc_info=True)
            return None

    def _get_cached_data(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None, max_age_hours: int = 24,
    ) -> pd.DataFrame | None:
        """
        从缓存获取数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            max_age_hours: 最大缓存时间（小时）

        Returns:
            DataFrame: 缓存的数据，如果没有则返回None
        """
        if not self.cache_enabled or not self.cache_manager:
            return None

        try:
            cache_key = self.cache_manager.find_cached_stock_data(
                symbol=symbol, start_date=start_date, end_date=end_date, max_age_hours=max_age_hours,
            )

            if cache_key:
                cached_data = self.cache_manager.load_stock_data(cache_key)
                if cached_data is not None and hasattr(cached_data, "empty") and not cached_data.empty:
                    logger.debug(f"📦 从缓存获取{symbol}数据: {len(cached_data)}条")
                    return cached_data  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"⚠️ 从缓存读取数据失败: {e}", exc_info=True)

        return None

    def _save_to_cache(
        self, symbol: str, data: pd.DataFrame, start_date: str | None = None, end_date: str | None = None,
    ):
        """
        保存数据到缓存

        Args:
            symbol: 股票代码
            data: 数据
            start_date: 开始日期
            end_date: 结束日期
        """
        if not self.cache_enabled or not self.cache_manager:
            return

        try:
            if data is not None and hasattr(data, "empty") and not data.empty:
                self.cache_manager.save_stock_data(symbol, data, start_date, end_date)
                logger.debug(f"💾 保存{symbol}数据到缓存: {len(data)}条")
        except Exception as e:
            logger.warning(f"⚠️ 保存数据到缓存失败: {e}", exc_info=True)

    def _format_stock_data_response(
        self, data: pd.DataFrame, symbol: str, stock_name: str, start_date: str, end_date: str,
    ) -> str:
        """
        格式化股票数据响应（包含技术指标）

        Args:
            data: 股票数据DataFrame
            symbol: 股票代码
            stock_name: 股票名称
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 格式化的数据报告（包含技术指标）
        """
        try:
            original_data_count = len(data)
            logger.info(f"📊 [技术指标] 开始计算技术指标，原始数据: {original_data_count}条")

            # 🔧 计算技术指标（使用完整数据）
            # 确保数据按日期排序
            if "date" in data.columns:
                data = data.sort_values("date")

            # 计算移动平均线
            data["ma5"] = data["close"].rolling(window=5, min_periods=1).mean()
            data["ma10"] = data["close"].rolling(window=10, min_periods=1).mean()
            data["ma20"] = data["close"].rolling(window=20, min_periods=1).mean()
            data["ma60"] = data["close"].rolling(window=60, min_periods=1).mean()

            # 计算RSI（相对强弱指标）- 同花顺风格：使用中国式SMA（EMA with adjust=True）
            # 参考：https://blog.csdn.net/u011218867/article/details/117427927
            # 同花顺/通达信的RSI使用SMA函数，等价于pandas的ewm(com=N-1, adjust=True)
            delta = data["close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # RSI6 - 使用中国式SMA
            avg_gain6 = gain.ewm(com=5, adjust=True).mean()  # com = N - 1
            avg_loss6 = loss.ewm(com=5, adjust=True).mean()
            rs6 = avg_gain6 / avg_loss6.replace(0, np.nan)
            data["rsi6"] = 100 - (100 / (1 + rs6))

            # RSI12 - 使用中国式SMA
            avg_gain12 = gain.ewm(com=11, adjust=True).mean()
            avg_loss12 = loss.ewm(com=11, adjust=True).mean()
            rs12 = avg_gain12 / avg_loss12.replace(0, np.nan)
            data["rsi12"] = 100 - (100 / (1 + rs12))

            # RSI24 - 使用中国式SMA
            avg_gain24 = gain.ewm(com=23, adjust=True).mean()
            avg_loss24 = loss.ewm(com=23, adjust=True).mean()
            rs24 = avg_gain24 / avg_loss24.replace(0, np.nan)
            data["rsi24"] = 100 - (100 / (1 + rs24))

            # 保留RSI14作为国际标准参考（使用简单移动平均）
            gain14 = gain.rolling(window=14, min_periods=1).mean()
            loss14 = loss.rolling(window=14, min_periods=1).mean()
            rs14 = gain14 / loss14.replace(0, np.nan)
            data["rsi14"] = 100 - (100 / (1 + rs14))

            # 计算MACD
            ema12 = data["close"].ewm(span=12, adjust=False).mean()
            ema26 = data["close"].ewm(span=26, adjust=False).mean()
            data["macd_dif"] = ema12 - ema26
            data["macd_dea"] = data["macd_dif"].ewm(span=9, adjust=False).mean()
            data["macd"] = (data["macd_dif"] - data["macd_dea"]) * 2

            # 计算布林带
            data["boll_mid"] = data["close"].rolling(window=20, min_periods=1).mean()
            std = data["close"].rolling(window=20, min_periods=1).std()
            data["boll_upper"] = data["boll_mid"] + 2 * std
            data["boll_lower"] = data["boll_mid"] - 2 * std

            logger.info("✅ [技术指标] 技术指标计算完成")

            # 🔧 只保留最后3-5天的数据用于展示（减少token消耗）
            display_rows = min(5, len(data))
            display_data = data.tail(display_rows)
            latest_data = data.iloc[-1]

            # 🔍 [调试日志] 打印最近5天的原始数据和技术指标
            logger.info(f"🔍 [技术指标详情] ===== 最近{display_rows}个交易日数据 =====")
            for i, (_idx, row) in enumerate(display_data.iterrows(), 1):
                logger.info(f"🔍 [技术指标详情] 第{i}天 ({row.get('date', 'N/A')}):")
                logger.info(
                    f"   价格: 开={row.get('open', 0):.2f}, 高={row.get('high', 0):.2f}, 低={row.get('low', 0):.2f}, 收={row.get('close', 0):.2f}",
                )
                logger.info(
                    f"   MA: MA5={row.get('ma5', 0):.2f}, MA10={row.get('ma10', 0):.2f}, MA20={row.get('ma20', 0):.2f}, MA60={row.get('ma60', 0):.2f}",
                )
                logger.info(
                    f"   MACD: DIF={row.get('macd_dif', 0):.4f}, DEA={row.get('macd_dea', 0):.4f}, MACD={row.get('macd', 0):.4f}",
                )
                logger.info(
                    f"   RSI: RSI6={row.get('rsi6', 0):.2f}, RSI12={row.get('rsi12', 0):.2f}, RSI24={row.get('rsi24', 0):.2f} (同花顺风格)",
                )
                logger.info(f"   RSI14: {row.get('rsi14', 0):.2f} (国际标准)")
                logger.info(
                    f"   BOLL: 上={row.get('boll_upper', 0):.2f}, 中={row.get('boll_mid', 0):.2f}, 下={row.get('boll_lower', 0):.2f}",
                )

            logger.info("🔍 [技术指标详情] ===== 数据详情结束 =====")

            # 计算最新价格和涨跌幅
            latest_price = latest_data.get("close", 0)
            prev_close = data.iloc[-2].get("close", latest_price) if len(data) > 1 else latest_price
            change = latest_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0

            # 格式化数据报告
            result = f"📊 {stock_name}({symbol}) - 技术分析数据\n"
            result += f"数据期间: {start_date} 至 {end_date}\n"
            result += f"数据条数: {original_data_count}条 (展示最近{display_rows}个交易日)\n\n"

            result += f"💰 最新价格: ¥{latest_price:.2f}\n"
            result += f"📈 涨跌额: {change:+.2f} ({change_pct:+.2f}%)\n\n"

            # 添加技术指标
            result += "📊 移动平均线 (MA):\n"
            result += f"   MA5:  ¥{latest_data['ma5']:.2f}"
            if latest_price > latest_data["ma5"]:
                result += " (价格在MA5上方 ↑)\n"
            else:
                result += " (价格在MA5下方 ↓)\n"

            result += f"   MA10: ¥{latest_data['ma10']:.2f}"
            if latest_price > latest_data["ma10"]:
                result += " (价格在MA10上方 ↑)\n"
            else:
                result += " (价格在MA10下方 ↓)\n"

            result += f"   MA20: ¥{latest_data['ma20']:.2f}"
            if latest_price > latest_data["ma20"]:
                result += " (价格在MA20上方 ↑)\n"
            else:
                result += " (价格在MA20下方 ↓)\n"

            result += f"   MA60: ¥{latest_data['ma60']:.2f}"
            if latest_price > latest_data["ma60"]:
                result += " (价格在MA60上方 ↑)\n\n"
            else:
                result += " (价格在MA60下方 ↓)\n\n"

            # MACD指标
            result += "📈 MACD指标:\n"
            result += f"   DIF:  {latest_data['macd_dif']:.3f}\n"
            result += f"   DEA:  {latest_data['macd_dea']:.3f}\n"
            result += f"   MACD: {latest_data['macd']:.3f}"
            if latest_data["macd"] > 0:
                result += " (多头 ↑)\n"
            else:
                result += " (空头 ↓)\n"

            # 判断金叉/死叉
            if len(data) > 1:
                prev_dif = data.iloc[-2]["macd_dif"]
                prev_dea = data.iloc[-2]["macd_dea"]
                curr_dif = latest_data["macd_dif"]
                curr_dea = latest_data["macd_dea"]

                if prev_dif <= prev_dea and curr_dif > curr_dea:
                    result += "   ⚠️ MACD金叉信号（DIF上穿DEA）\n\n"
                elif prev_dif >= prev_dea and curr_dif < curr_dea:
                    result += "   ⚠️ MACD死叉信号（DIF下穿DEA）\n\n"
                else:
                    result += "\n"
            else:
                result += "\n"

            # RSI指标 - 同花顺风格 (6, 12, 24)
            rsi6 = latest_data["rsi6"]
            rsi12 = latest_data["rsi12"]
            rsi24 = latest_data["rsi24"]
            result += "📉 RSI指标 (同花顺风格):\n"
            result += f"   RSI6:  {rsi6:.2f}"
            if rsi6 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi6 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            result += f"   RSI12: {rsi12:.2f}"
            if rsi12 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi12 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            result += f"   RSI24: {rsi24:.2f}"
            if rsi24 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi24 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            # 判断RSI趋势
            if rsi6 > rsi12 > rsi24:
                result += "   趋势: 多头排列 ↑\n\n"
            elif rsi6 < rsi12 < rsi24:
                result += "   趋势: 空头排列 ↓\n\n"
            else:
                result += "   趋势: 震荡整理 ↔\n\n"

            # 布林带
            result += "📊 布林带 (BOLL):\n"
            result += f"   上轨: ¥{latest_data['boll_upper']:.2f}\n"
            result += f"   中轨: ¥{latest_data['boll_mid']:.2f}\n"
            result += f"   下轨: ¥{latest_data['boll_lower']:.2f}\n"

            # 判断价格在布林带的位置
            boll_position = (
                (latest_price - latest_data["boll_lower"])
                / (latest_data["boll_upper"] - latest_data["boll_lower"])
                * 100
            )
            result += f"   价格位置: {boll_position:.1f}%"
            if boll_position >= 80:
                result += " (接近上轨，可能超买 ⚠️)\n\n"
            elif boll_position <= 20:
                result += " (接近下轨，可能超卖 ⚠️)\n\n"
            else:
                result += " (中性区域)\n\n"

            # 价格统计
            result += f"📊 价格统计 (最近{display_rows}个交易日):\n"
            result += f"   最高价: ¥{display_data['high'].max():.2f}\n"
            result += f"   最低价: ¥{display_data['low'].min():.2f}\n"
            result += f"   平均价: ¥{display_data['close'].mean():.2f}\n"

            # 防御性获取成交量数据
            volume_value = self._get_volume_safely(display_data)
            result += f"   平均成交量: {volume_value:,.0f}股\n"

            return result

        except Exception as e:
            logger.error(f"❌ 格式化数据响应失败: {e}", exc_info=True)
            return f"❌ 格式化{symbol}数据失败: {e}"

    @staticmethod
    def _safe_float(value: Any) -> float:
        """安全转换为浮点数"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def get_stock_dataframe(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None, period: str = "daily",
    ) -> pd.DataFrame:
        """
        获取股票数据的 DataFrame 接口，支持多数据源和自动降级

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 数据周期（daily/weekly/monthly），默认为daily

        Returns:
            pd.DataFrame: 股票数据 DataFrame，列标准：open, high, low, close, vol, amount, date
        """
        logger.info(f"📊 [DataFrame接口] 获取股票数据: {symbol} ({start_date} 到 {end_date})")

        try:
            # 尝试当前数据源
            df = None
            if self.current_source == ChinaDataSource.MONGODB:
                from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

                adapter = get_mongodb_cache_adapter()
                df = adapter.get_historical_data(symbol, start_date, end_date, period=period)
            elif self.current_source == ChinaDataSource.TUSHARE:
                from .providers.china.tushare import get_tushare_provider

                provider = get_tushare_provider()
                provider.connect_sync()
                df = self._run_async_in_new_loop(provider.get_historical_data(symbol, start_date, end_date, period=period))  # type: ignore[arg-type]

            if df is not None and not df.empty:
                logger.info(f"✅ [DataFrame接口] 从 {self.current_source.value} 获取成功: {len(df)}条")
                return self._standardize_dataframe(df)

            # 降级到其他数据源
            logger.warning(f"⚠️ [DataFrame接口] {self.current_source.value} 失败，尝试降级")
            for source in self.available_sources:
                if source == self.current_source:
                    continue
                try:
                    if source == ChinaDataSource.MONGODB:
                        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

                        adapter = get_mongodb_cache_adapter()
                        df = adapter.get_historical_data(symbol, start_date, end_date, period=period)
                    elif source == ChinaDataSource.TUSHARE:
                        from .providers.china.tushare import get_tushare_provider

                        provider = get_tushare_provider()
                        provider.connect_sync()
                        df = self._run_async_in_new_loop(provider.get_historical_data(symbol, start_date, end_date, period=period))  # type: ignore[arg-type]

                    if df is not None and not df.empty:
                        logger.info(f"✅ [DataFrame接口] 降级到 {source.value} 成功: {len(df)}条")
                        return self._standardize_dataframe(df)
                except Exception as e:
                    logger.warning(f"⚠️ [DataFrame接口] {source.value} 失败: {e}", exc_info=True)
                    continue

            logger.error(f"❌ [DataFrame接口] 所有数据源都失败: {symbol}", exc_info=True)
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ [DataFrame接口] 获取失败: {e}", exc_info=True)
            return pd.DataFrame()

    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化 DataFrame 列名和格式

        Args:
            df: 原始 DataFrame

        Returns:
            pd.DataFrame: 标准化后的 DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        out = df.copy()

        # 列名映射
        colmap = {
            # English
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "vol",
            "Amount": "amount",
            "symbol": "code",
            "Symbol": "code",
            # Already lower
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "vol",
            "volume": "vol",
            "amount": "amount",
            "code": "code",
            "date": "date",
            "trade_date": "date",
            # Chinese column names — OHLC
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "vol",
            "成交额": "amount",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            # 🔴 P0 FIX: 新增缺失的中文列名映射
            "最新价": "close",  # efinance 实时价格列
            "当前价": "close",  # 备选实时价格列名
            "开盘价": "open",  # 开盘价中文全称
            "收盘价": "close",  # 收盘价中文全称
            "最高价": "high",  # 最高价中文全称
            "最低价": "low",  # 最低价中文全称
            "昨收": "pre_close",  # 昨收价
            "昨收价": "pre_close",  # 昨收价备选
            "前收盘": "pre_close",  # 前收盘
            "换手率": "turnover",  # 换手率
            "交易状态": "trade_status",  # 交易状态
            "股票名称": "name",  # 股票名称
            "名称": "name",  # 股票名称简写
            "代码": "code",  # 股票代码
            "时间": "datetime",  # 时间列
            "price": "close",  # 通用价格列
        }
        out = out.rename(columns={c: colmap.get(c, c) for c in out.columns})

        # 确保日期排序
        if "date" in out.columns:
            try:
                out["date"] = pd.to_datetime(out["date"])
                out = out.sort_values("date")
            except Exception:
                logger.warning("数据源加载失败，跳过", exc_info=True)

        # 计算涨跌幅（如果缺失）
        if "pct_change" not in out.columns and "close" in out.columns:
            out["pct_change"] = out["close"].pct_change() * 100.0

        return out  # type: ignore[no-any-return]

    def get_stock_data(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None, period: str = "daily",
    ) -> str:
        """
        获取股票数据的统一接口，支持多周期数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 数据周期（daily/weekly/monthly），默认为daily

        Returns:
            str: 格式化的股票数据
        """
        # 记录详细的输入参数
        logger.info(
            f"📊 [数据来源: {self.current_source.value}] 开始获取{period}数据: {symbol}",
            extra={
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "period": period,
                "data_source": self.current_source.value,
                "event_type": "data_fetch_start",
            },
        )

        # 添加详细的股票代码追踪日志
        logger.info(
            f"🔍 [股票代码追踪] DataSourceManager.get_stock_data 接收到的股票代码: '{symbol}' (类型: {type(symbol)})",
        )
        logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(symbol))}")
        logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(symbol))}")
        logger.info(f"🔍 [股票代码追踪] 当前数据源: {self.current_source.value}")

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            actual_source = None  # 实际使用的数据源

            if self.current_source == ChinaDataSource.MONGODB:
                result, actual_source = self._get_mongodb_data(symbol, start_date, end_date, period)  # type: ignore[arg-type]
            elif self.current_source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_data(symbol, start_date, end_date, period)  # type: ignore[arg-type]
                actual_source = "tushare"
            # TDX 已移除
            else:
                result = f"❌ 不支持的数据源: {self.current_source.value}"
                actual_source = None

            # 记录详细的输出结果
            duration = time.time() - start_time
            result_length = len(result) if result else 0
            is_success = result and "❌" not in result and "错误" not in result

            # 使用实际数据源名称，如果没有则使用 current_source
            display_source = actual_source or self.current_source.value

            if is_success:
                logger.info(
                    f"✅ [数据来源: {display_source}] 成功获取股票数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                    extra={
                        "symbol": symbol,
                        "start_date": start_date,
                        "end_date": end_date,
                        "data_source": display_source,
                        "actual_source": actual_source,
                        "requested_source": self.current_source.value,
                        "duration": duration,
                        "result_length": result_length,
                        "result_preview": result[:200] + "..." if result_length > 200 else result,
                        "event_type": "data_fetch_success",
                    },
                )
                return result
            logger.warning(
                f"⚠️ [数据来源: {self.current_source.value}失败] 数据质量异常，尝试降级到其他数据源: {symbol}",
                extra={
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "data_source": self.current_source.value,
                    "duration": duration,
                    "result_length": result_length,
                    "result_preview": result[:200] + "..." if result_length > 200 else result,
                    "event_type": "data_fetch_warning",
                },
            )

            # 数据质量异常时也尝试降级到其他数据源
            fallback_result, _ = self._try_fallback_sources(symbol, start_date, end_date)  # type: ignore[arg-type]
            if fallback_result and "❌" not in fallback_result and "错误" not in fallback_result:
                logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取数据: {symbol}")
                return fallback_result
            logger.error(f"❌ [数据来源: 所有数据源失败] 所有数据源都无法获取有效数据: {symbol}")
            return result  # 返回原始结果（包含错误信息）

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"❌ [数据获取] 异常失败: {e}",
                extra={
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "data_source": self.current_source.value,
                    "duration": duration,
                    "error": str(e),
                    "event_type": "data_fetch_exception",
                },
                exc_info=True,
            )
            fallback_result, _ = self._try_fallback_sources(symbol, start_date, end_date)  # type: ignore[arg-type]
            return fallback_result

    def _get_mongodb_data(
        self, symbol: str, start_date: str, end_date: str, period: str = "daily",
    ) -> tuple[str, str | None]:
        """
        从MongoDB获取多周期数据 - 包含技术指标计算

        Returns:
            tuple[str, str | None]: (结果字符串, 实际使用的数据源名称)
        """
        logger.debug(
            f"📊 [MongoDB] 调用参数: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}",
        )

        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()

            # 从MongoDB获取指定周期的历史数据
            df = adapter.get_historical_data(symbol, start_date, end_date, period=period)

            if df is not None and not df.empty:
                logger.info(f"✅ [数据来源: MongoDB缓存] 成功获取{period}数据: {symbol} ({len(df)}条记录)")

                # 🔧 修复：使用统一的格式化方法，包含技术指标计算
                # 获取股票名称（从DataFrame中提取或使用默认值）
                stock_name = f"股票{symbol}"
                if "name" in df.columns and not df["name"].empty:
                    stock_name = df["name"].iloc[0]

                # 调用统一的格式化方法（包含技术指标计算）
                result = self._format_stock_data_response(df, symbol, stock_name, start_date, end_date)

                logger.info("✅ [MongoDB] 已计算技术指标: MA5/10/20/60, MACD, RSI, BOLL")
                return result, "mongodb"
            # MongoDB没有数据（adapter内部已记录详细的数据源信息），降级到其他数据源
            logger.info(f"🔄 [MongoDB] 未找到{period}数据: {symbol}，开始尝试备用数据源")
            return self._try_fallback_sources(symbol, start_date, end_date, period)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB异常] 获取{period}数据失败: {symbol}, 错误: {e}", exc_info=True)
            # MongoDB异常，降级到其他数据源
            return self._try_fallback_sources(symbol, start_date, end_date, period)

    def _run_async_in_new_loop(self, coro, timeout=45):
        """
        在共享事件循环池中运行异步协程并同步等待结果
        替代旧的临时 new_event_loop 方案，解决线程泄漏问题

        Args:
            coro: 要执行的协程对象
            timeout: 超时秒数（默认 45s，与 TushareProvider 一致）

        Returns:
            协程的返回值，超时或失败返回 None
        """
        pool = get_event_loop_pool()
        try:
            return pool.run_coroutine(coro, timeout=timeout)
        except Exception as e:
            logger.error(f"❌ [EventLoopPool] 协程执行超时/失败 ({timeout}s): {e}")
            return None

    def _get_tushare_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """使用 Tushare 获取多周期数据 - 包含技术指标计算"""
        # 熔断器由 tushare.py 的类级别三态熔断器统一管理
        try:
            from .providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            if not provider.connected:
                provider.connect_sync()
            if not provider.connected:
                logger.warning(f"⚠️ [Tushare] 连接失败: {symbol}")
                return f"❌ Tushare连接失败: {symbol}"

            # 获取历史数据
            data = self._run_async_in_new_loop(
                provider.get_historical_data(symbol, start_date, end_date, period),
            )

            if data is not None and not data.empty:
                # 获取股票基本信息
                try:
                    stock_info = self._run_async_in_new_loop(provider.get_stock_basic_info(symbol))
                    stock_name = stock_info.get("name", f"股票{symbol}") if stock_info else f"股票{symbol}"
                except Exception as e:
                    logger.warning(f"⚠️ [Tushare] 获取股票信息失败: {e}")
                    stock_name = f"股票{symbol}"

                # 调用统一的格式化方法（包含技术指标计算）
                result = self._format_stock_data_response(data, symbol, stock_name, start_date, end_date)
                logger.info("✅ [Tushare] 成功获取数据并计算技术指标: %s", symbol)
                return result
            else:
                logger.warning(f"⚠️ [Tushare] 数据为空: {symbol}")

            return f"❌ 未能获取{symbol}的股票数据"

        except ImportError as e:
            logger.error(f"❌ [Tushare] 库未安装: {e}")
            return f"❌ tushare 未安装: {e}"
        except Exception as e:
            logger.error(f"❌ [Tushare] 获取数据失败: {e}", exc_info=True)
            return f"❌ Tushare获取数据失败: {e}"



    def _get_volume_safely(self, data) -> float:
        """安全地获取成交量数据，支持多种列名"""
        try:
            # 支持多种可能的成交量列名
            volume_columns = ["volume", "vol", "turnover", "trade_volume"]

            for col in volume_columns:
                if col in data.columns:
                    logger.info(f"✅ 找到成交量列: {col}")
                    return data[col].sum()  # type: ignore[no-any-return]

            # 如果都没找到，记录警告并返回0
            logger.warning(f"⚠️ 未找到成交量列，可用列: {list(data.columns)}")
            return 0

        except Exception as e:
            logger.error(f"❌ 获取成交量失败: {e}", exc_info=True)
            return 0

    def _try_fallback_sources(
        self, symbol: str, start_date: str, end_date: str, period: str = "daily",
    ) -> tuple[str, str | None]:
        """
        尝试备用数据源 - 优先级：Tushare → AkShare → MongoDB

        Returns:
            tuple[str, str | None]: (结果字符串, 实际使用的数据源名称)
        """
        logger.info(f"🔄 [{self.current_source.value}] 失败，尝试备用数据源获取{period}数据: {symbol}")

        # 按优先级降级
        for source in self._get_data_source_priority_order():
            if source == ChinaDataSource.MONGODB:
                continue  # MongoDB 由 _get_mongodb_data 处理
            if source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_data(symbol, start_date, end_date, period)
                if result and "❌" not in result:
                    logger.info(f"✅ [备用数据源-Tushare] 成功获取{period}数据: {symbol}")
                    return result, "tushare"
                continue

        # 🔁 Tushare 和 MongoDB 均不可用 → 尝试 AkShare 直连
        akshare_enabled = os.getenv("AKSHARE_UNIFIED_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        if akshare_enabled:
            try:
                result = self._get_akshare_data(symbol, start_date, end_date, period)
                if result and "❌" not in result:
                    logger.info(f"✅ [备用数据源-AkShare] 成功获取{period}数据: {symbol}")
                    return result, "akshare"
            except Exception as e:
                logger.warning(f"⚠️ [备用数据源-AkShare] 失败: {e}", exc_info=True)

        logger.warning(f"❌ [所有数据源失败] 无法获取{period}数据: {symbol}")
        logger.warning("所有数据源不可用，使用模拟数据，分析结果仅供参考")
        return f"❌ 所有数据源都无法获取{symbol}的{period}数据", None

    def _get_akshare_data(
        self, symbol: str, start_date: str, end_date: str, period: str = "daily",
    ) -> str:
        """使用 AkShare 直连获取 A 股历史数据（兜底方案）

        AkShare 是开源免费的 A 股数据源，无需 Token，
        作为 Tushare 熔断时的最终兜底方案。
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error("❌ [AkShare] akshare 库未安装，请执行 pip install akshare")
            return f"❌ akshare 未安装: {symbol}"

        try:
            # 提取纯数字代码
            import re as _re
            code = _re.sub(r"[^0-9]", "", symbol)
            if not code:
                return f"❌ 无效股票代码: {symbol}"
            code = code.zfill(6)

            # 格式化日期
            s_date = start_date.replace("-", "") if start_date else "20200101"
            e_date = end_date.replace("-", "") if end_date else time.strftime("%Y%m%d")

            # 根据代码前缀判断市场
            if code.startswith(("6", "9")):
                full_symbol = f"{code}"  # 上海交易所
            else:
                full_symbol = f"{code}"  # 深圳交易所

            # 调用 AkShare 获取历史数据
            # stock_zh_a_hist: 返回 columns=['日期','开盘','收盘','最高','最低','成交量','成交额','振幅','涨跌幅','涨跌额','换手率']
            timeout = int(os.getenv("AKSHARE_TIMEOUT", "15"))
            df = ak.stock_zh_a_hist(
                symbol=full_symbol,
                period=period.lower() if period in ("daily", "weekly", "monthly") else "daily",
                start_date=s_date,
                end_date=e_date,
                adjust="qfq",
            )

            if df is None or df.empty:
                return f"❌ AkShare 返回空数据: {symbol}"

            # 标准化列名
            colmap = {
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnover",
                "振幅": "amplitude",
            }
            df = df.rename(columns={c: colmap.get(c, c) for c in df.columns})

            # 确保日期列
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date")

            df["code"] = symbol

            # 使用统一的格式化方法（含技术指标）
            stock_name = f"股票{symbol}"
            result = self._format_stock_data_response(df, symbol, stock_name, start_date, end_date)
            logger.info("✅ [AkShare] 成功获取数据并计算技术指标: %s (%d条)", symbol, len(df))
            return result

        except Exception as e:
            logger.error("❌ [AkShare] 获取数据失败: %s - %s", symbol, e, exc_info=True)
            return f"❌ AkShare获取数据失败: {symbol} ({e})"

    def get_stock_info(self, symbol: str) -> dict:
        """
        获取股票基本信息，支持多数据源和自动降级
        优先级：MongoDB 缓存 → Tushare
        """
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取股票信息: {symbol}")

        # 优先使用 App Mongo 缓存（当 ta_use_app_cache=True）
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled

            use_cache = use_app_cache_enabled(False)
            logger.info(f"🔧 [配置检查] use_app_cache_enabled() 返回值: {use_cache}")
        except Exception as e:
            logger.error(f"❌ [配置检查] use_app_cache_enabled() 调用失败: {e}", exc_info=True)
            use_cache = False

        logger.info(f"🔧 [配置] ta_use_app_cache={use_cache}, current_source={self.current_source.value}")

        if use_cache:
            try:
                from .cache.app_adapter import get_basics_from_cache, get_market_quote_dataframe

                doc = get_basics_from_cache(symbol)
                if doc:
                    name = doc.get("name") or doc.get("stock_name") or ""  # type: ignore[union-attr]
                    # 规范化行业与板块（避免把“中小板/创业板”等板块值误作行业）
                    board_labels = {"主板", "中小板", "创业板", "科创板"}
                    raw_industry = (doc.get("industry") or doc.get("industry_name") or "").strip()  # type: ignore[union-attr]
                    sec_or_cat = (doc.get("sec") or doc.get("category") or "").strip()  # type: ignore[union-attr]
                    market_val = (doc.get("market") or "").strip()  # type: ignore[union-attr]
                    industry_val = raw_industry or sec_or_cat or "未知"
                    changed = False
                    if raw_industry in board_labels:
                        # 若industry是板块名，则将其用于market；industry改用更细分类（sec/category）
                        if not market_val:
                            market_val = raw_industry
                            changed = True
                        if sec_or_cat:
                            industry_val = sec_or_cat
                            changed = True
                    if changed:
                        try:
                            logger.debug(
                                f"🔧 [字段归一化] industry原值='{raw_industry}' → 行业='{industry_val}', 市场/板块='{market_val or doc.get('market', '未知')}'",
                            )  # type: ignore[union-attr]
                        except Exception:
                            logger.warning("数据源卸载失败，跳过", exc_info=True)

                    result = {
                        "symbol": symbol,
                        "name": name or f"股票{symbol}",
                        "area": doc.get("area", "未知"),  # type: ignore[union-attr]
                        "industry": industry_val or "未知",
                        "market": market_val or doc.get("market", "未知"),  # type: ignore[union-attr]
                        "list_date": doc.get("list_date", "未知"),  # type: ignore[union-attr]
                        "source": "app_cache",
                    }
                    # 追加快照行情（若存在）
                    try:
                        df = get_market_quote_dataframe(symbol)
                        if df is not None and not df.empty:
                            row = df.iloc[-1]
                            result["current_price"] = row.get("close")
                            result["change_pct"] = row.get("pct_chg")
                            result["volume"] = row.get("volume")
                            result["quote_date"] = row.get("date")
                            result["quote_source"] = "market_quotes"
                            logger.info(
                                f"✅ [股票信息] 附加行情 | price={result['current_price']} pct={result['change_pct']} vol={result['volume']} code={symbol}",
                            )
                    except Exception as _e:
                        logger.debug(f"附加行情失败（忽略）：{_e}")

                    if name:
                        logger.info(f"✅ [数据来源: MongoDB-stock_basic_info] 成功获取: {symbol}")
                        return result
                    logger.warning(f"⚠️ [数据来源: MongoDB] 未找到有效名称: {symbol}，降级到其他数据源")
            except Exception as e:
                logger.error(f"❌ [数据来源: MongoDB异常] 获取股票信息失败: {e}", exc_info=True)

        # 直接通过兼容路径获取股票信息
        # 注：仅 US/HK provider 有同步 get_stock_info()，China provider 统一走此路径
        result = self._try_fallback_stock_info(symbol)
        if result.get("name") and result["name"] != f"股票{symbol}":
            logger.info(f"✅ [数据来源: {result.get('source', self.current_source.value)}-股票信息] 成功获取: {symbol}")
            return result

        logger.warning(f"⚠️ [数据来源: 所有数据源] 获取股票信息失败: {symbol}")
        return result

    def get_stock_basic_info(self, stock_code: str | None = None) -> dict[str, Any] | None:
        """
        获取股票基础信息（兼容 stock_data_service 接口）

        Args:
            stock_code: 股票代码，如果为 None 则返回所有股票列表

        Returns:
            Dict: 股票信息字典，或包含 error 字段的错误字典
        """
        if stock_code is None:
            # 返回所有股票列表
            logger.info("📊 获取所有股票列表")
            try:
                # 尝试从 MongoDB 获取
                from tradingagents.config.database_manager import get_database_manager

                db_manager = get_database_manager()
                if db_manager and db_manager.is_mongodb_available():
                    collection = db_manager.get_mongodb_db()["stock_basic_info"]
                    stocks = list(collection.find({}, {"_id": 0}))
                    if stocks:
                        logger.info(f"✅ 从MongoDB获取所有股票: {len(stocks)}条")
                        return stocks  # type: ignore[return-value]
            except Exception as e:
                logger.warning(f"⚠️ 从MongoDB获取所有股票失败: {e}", exc_info=True)

            # 降级：返回空列表
            return []  # type: ignore[return-value]

        # 获取单个股票信息
        try:
            result = self.get_stock_info(stock_code)
            if result and result.get("name"):
                return result
            return {"error": f"未找到股票 {stock_code} 的信息"}
        except Exception as e:
            logger.error(f"❌ 获取股票信息失败: {e}", exc_info=True)
            return {"error": str(e)}

    def get_stock_data_with_fallback(self, stock_code: str, start_date: str, end_date: str) -> str:
        """
        获取股票数据（兼容 stock_data_service 接口）

        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 格式化的股票数据报告
        """
        logger.info(f"📊 获取股票数据: {stock_code} ({start_date} 到 {end_date})")

        try:
            # 使用统一的数据获取接口
            return self.get_stock_data(stock_code, start_date, end_date)
        except Exception as e:
            logger.error(f"❌ 获取股票数据失败: {e}", exc_info=True)
            return (
                f"❌ 获取股票数据失败: {e!s}\n\n💡 建议：\n1. 检查网络连接\n2. 确认股票代码格式正确\n3. 检查数据源配置"
            )

    def _try_fallback_stock_info(self, symbol: str) -> dict:
        """备用数据源获取股票基本信息"""
        # 首先尝试 Tushare
        try:
            from .providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            if not provider.connected:
                provider.connect_sync()
            if provider.connected:
                result = self._run_async_in_new_loop(provider.get_stock_basic_info(symbol))
                if result and result.get("name") and result["name"] != f"股票{symbol}":
                    logger.info(f"✅ [数据来源: Tushare] 降级成功获取股票信息: {symbol}")
                    return result  # type: ignore[return-value]
        except Exception as e:
            logger.warning(f"⚠️ Tushare 获取股票信息失败: {e}")

        logger.error(f"❌ 所有数据源都无法获取{symbol}的股票信息", exc_info=True)
        return {"symbol": symbol, "name": f"股票{symbol}", "source": "unknown"}

    def _parse_stock_info_string(self, info_str: str, symbol: str) -> dict:
        """解析股票信息字符串为字典"""
        try:
            info = {"symbol": symbol, "source": self.current_source.value}
            lines = info_str.split("\n")

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if "股票名称" in key:
                        info["name"] = value
                    elif "所属行业" in key:
                        info["industry"] = value
                    elif "所属地区" in key:
                        info["area"] = value
                    elif "上市市场" in key:
                        info["market"] = value
                    elif "上市日期" in key:
                        info["list_date"] = value

            return info

        except Exception as e:
            logger.error(f"⚠️ 解析股票信息失败: {e}", exc_info=True)
            return {"symbol": symbol, "name": f"股票{symbol}", "source": self.current_source.value}

    # ==================== 基本面数据获取方法 ====================

    def _get_mongodb_fundamentals(self, symbol: str) -> str:
        """从 MongoDB 获取财务数据"""
        logger.debug(f"📊 [MongoDB] 调用参数: symbol={symbol}")

        try:
            import pandas as pd

            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()

            # 从 MongoDB 获取财务数据
            financial_data = adapter.get_financial_data(symbol)

            # 检查数据类型和内容
            if financial_data is not None:
                # 如果是 DataFrame，转换为字典列表
                if isinstance(financial_data, pd.DataFrame):
                    if not financial_data.empty:
                        logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                        # 转换为字典列表
                        financial_dict_list = financial_data.to_dict("records")
                        # 格式化财务数据为报告
                        return self._format_financial_data(symbol, financial_dict_list)
                    logger.warning(f"⚠️ [数据来源: MongoDB] 财务数据为空: {symbol}，降级到其他数据源")
                    return self._try_fallback_fundamentals(symbol)
                # 如果是列表
                if isinstance(financial_data, list) and len(financial_data) > 0:
                    logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                    return self._format_financial_data(symbol, financial_data)
                # 如果是单个字典（这是MongoDB实际返回的格式）
                if isinstance(financial_data, dict):
                    logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} (单条记录)")
                    # 将单个字典包装成列表
                    financial_dict_list = [financial_data]
                    return self._format_financial_data(symbol, financial_dict_list)
                logger.warning(f"⚠️ [数据来源: MongoDB] 未找到财务数据: {symbol}，降级到其他数据源")
                return self._try_fallback_fundamentals(symbol)
            logger.warning(f"⚠️ [数据来源: MongoDB] 未找到财务数据: {symbol}，降级到其他数据源")
            # MongoDB 没有数据，降级到其他数据源
            return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB异常] 获取财务数据失败: {e}", exc_info=True)
            # MongoDB 异常，降级到其他数据源
            return self._try_fallback_fundamentals(symbol)

    def _get_valuation_indicators(self, symbol: str) -> dict:
        """从stock_basic_info集合获取估值指标"""
        try:
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                return {}

            client = db_manager.get_mongodb_client()
            db = client[db_manager.config.mongodb_config.database_name]  # type: ignore[attr-defined]

            # 从stock_basic_info集合获取估值指标
            collection = db["stock_basic_info"]
            result = collection.find_one({"ts_code": symbol})

            if result:
                return {
                    "pe": result.get("pe"),
                    "pb": result.get("pb"),
                    "pe_ttm": result.get("pe_ttm"),
                    "total_mv": result.get("total_mv"),
                    "circ_mv": result.get("circ_mv"),
                }
            return {}

        except Exception as e:
            logger.error(f"获取{symbol}估值指标失败: {e}", exc_info=True)
            return {}

    def _format_financial_data(self, symbol: str, financial_data: list[dict]) -> str:
        """格式化财务数据为报告"""
        try:
            if not financial_data or len(financial_data) == 0:
                return f"❌ 未找到{symbol}的财务数据"

            # 获取最新的财务数据
            latest = financial_data[0]

            # 构建报告
            report = f"📊 {symbol} 基本面数据（来自MongoDB）\n\n"

            # 基本信息
            report += f"📅 报告期: {latest.get('report_period', latest.get('end_date', '未知'))}\n"
            report += "📈 数据来源: MongoDB财务数据库\n\n"

            # 财务指标
            report += "💰 财务指标:\n"
            revenue = latest.get("revenue") or latest.get("total_revenue")
            if revenue is not None:
                report += f"   营业总收入: {revenue:,.2f}\n"

            net_profit = latest.get("net_profit") or latest.get("net_income")
            if net_profit is not None:
                report += f"   净利润: {net_profit:,.2f}\n"

            total_assets = latest.get("total_assets")
            if total_assets is not None:
                report += f"   总资产: {total_assets:,.2f}\n"

            total_liab = latest.get("total_liab")
            if total_liab is not None:
                report += f"   总负债: {total_liab:,.2f}\n"

            total_equity = latest.get("total_equity")
            if total_equity is not None:
                report += f"   股东权益: {total_equity:,.2f}\n"

            # 估值指标 - 从stock_basic_info集合获取
            report += "\n📊 估值指标:\n"
            valuation_data = self._get_valuation_indicators(symbol)
            if valuation_data:
                pe = valuation_data.get("pe")
                if pe is not None:
                    report += f"   市盈率(PE): {pe:.2f}\n"

                pb = valuation_data.get("pb")
                if pb is not None:
                    report += f"   市净率(PB): {pb:.2f}\n"

                pe_ttm = valuation_data.get("pe_ttm")
                if pe_ttm is not None:
                    report += f"   市盈率TTM(PE_TTM): {pe_ttm:.2f}\n"

                total_mv = valuation_data.get("total_mv")
                if total_mv is not None:
                    report += f"   总市值: {total_mv:.2f}亿元\n"

                circ_mv = valuation_data.get("circ_mv")
                if circ_mv is not None:
                    report += f"   流通市值: {circ_mv:.2f}亿元\n"
            else:
                # 如果无法从stock_basic_info获取，尝试从财务数据计算
                pe = latest.get("pe")
                if pe is not None:
                    report += f"   市盈率(PE): {pe:.2f}\n"

                pb = latest.get("pb")
                if pb is not None:
                    report += f"   市净率(PB): {pb:.2f}\n"

                ps = latest.get("ps")
                if ps is not None:
                    report += f"   市销率(PS): {ps:.2f}\n"

            # 盈利能力
            report += "\n💹 盈利能力:\n"
            roe = latest.get("roe")
            if roe is not None:
                report += f"   净资产收益率(ROE): {roe:.2f}%\n"

            roa = latest.get("roa")
            if roa is not None:
                report += f"   总资产收益率(ROA): {roa:.2f}%\n"

            gross_margin = latest.get("gross_margin")
            if gross_margin is not None:
                report += f"   毛利率: {gross_margin:.2f}%\n"

            netprofit_margin = latest.get("netprofit_margin") or latest.get("net_margin")
            if netprofit_margin is not None:
                report += f"   净利率: {netprofit_margin:.2f}%\n"

            # 现金流
            n_cashflow_act = latest.get("n_cashflow_act")
            if n_cashflow_act is not None:
                report += "\n💰 现金流:\n"
                report += f"   经营活动现金流: {n_cashflow_act:,.2f}\n"

                n_cashflow_inv_act = latest.get("n_cashflow_inv_act")
                if n_cashflow_inv_act is not None:
                    report += f"   投资活动现金流: {n_cashflow_inv_act:,.2f}\n"

                c_cash_equ_end_period = latest.get("c_cash_equ_end_period")
                if c_cash_equ_end_period is not None:
                    report += f"   期末现金及等价物: {c_cash_equ_end_period:,.2f}\n"

            report += f"\n📝 共有 {len(financial_data)} 期财务数据\n"

            return report

        except Exception as e:
            logger.error(f"❌ 格式化财务数据失败: {e}", exc_info=True)
            return f"❌ 格式化{symbol}财务数据失败: {e}"

    def _generate_fundamentals_analysis(self, symbol: str) -> str:
        """生成基本的基本面分析"""
        try:
            # 获取股票基本信息
            stock_info = self.get_stock_info(symbol)

            report = f"📊 {symbol} 基本面分析（生成）\n\n"
            report += f"📈 股票名称: {stock_info.get('name', '未知')}\n"
            report += f"🏢 所属行业: {stock_info.get('industry', '未知')}\n"
            report += f"📍 所属地区: {stock_info.get('area', '未知')}\n"
            report += f"📅 上市日期: {stock_info.get('list_date', '未知')}\n"
            report += f"🏛️ 交易所: {stock_info.get('exchange', '未知')}\n\n"

            report += "⚠️ 注意: 详细财务数据需要从数据源获取\n"
            report += "💡 建议: 启用MongoDB缓存以获取完整的财务数据\n"

            return report

        except Exception as e:
            logger.error(f"❌ 生成基本面分析失败: {e}", exc_info=True)
            return f"❌ 生成{symbol}基本面分析失败: {e}"

    def _try_fallback_fundamentals(self, symbol: str) -> str:
        """基本面数据降级处理"""
        try:
            from .providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            if not provider.connected:
                provider.connect_sync()
            if provider.connected:
                fin_data = self._run_async_in_new_loop(provider.get_financial_data(symbol))
                if fin_data:
                    logger.info(f"✅ [数据来源: Tushare] 获取财务数据成功: {symbol}")
                    return self._generate_fundamentals_analysis(symbol)
        except Exception as e:
            logger.warning(f"⚠️ Tushare 获取财务数据失败: {e}")

        logger.warning(f"⚠️ 无法获取详细的财务数据，使用生成分析: {symbol}")
        return self._generate_fundamentals_analysis(symbol)

    def _get_mongodb_news(self, symbol: str, hours_back: int, limit: int) -> list[dict[str, Any]]:
        """从MongoDB获取新闻数据"""
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()

            # 从MongoDB获取新闻数据
            news_data = adapter.get_news_data(symbol, hours_back=hours_back, limit=limit)

            if news_data and len(news_data) > 0:
                logger.info(f"✅ [数据来源: MongoDB-新闻] 成功获取: {symbol or '市场新闻'} ({len(news_data)}条)")
                return news_data
            logger.warning(f"⚠️ [数据来源: MongoDB] 未找到新闻: {symbol or '市场新闻'}，降级到其他数据源")
            return self._try_fallback_news(symbol, hours_back, limit)

        except Exception as e:
            # [FIX] 2026-06-18: Fix 2.7c - 区分连接失败和数据为空两种场景
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["connection", "timeout", "network", "server", "auth"]):
                logger.error(f"❌ [数据来源: MongoDB] 新闻连接失败（将降级到其他数据源）: {e}", exc_info=True)
            else:
                logger.error(f"❌ [数据来源: MongoDB] 获取新闻失败（将降级到其他数据源）: {e}", exc_info=True)

            return self._try_fallback_news(symbol, hours_back, limit)

    # [FIX] 2026-06-18: 新增 MongoDB 新闻获取占位符

    def _try_fallback_news(self, symbol: str, hours_back: int, limit: int) -> list[dict[str, Any]]:
        """新闻数据降级处理"""
        # Tushare 也没有专门的新闻 API（有 major_news 接口但需要付费）
        logger.warning(f"⚠️ [数据来源: 所有数据源] 当前数据源不提供新闻数据: {symbol or '市场新闻'}")
        return []


def get_china_stock_data_unified(symbol: str, start_date: str, end_date: str) -> str:
    """
    统一的中国股票数据获取接口
    自动使用配置的数据源，支持备用数据源

    Args:
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的股票数据
    """

    # 添加详细的股票代码追踪日志
    logger.info(
        f"🔍 [股票代码追踪] data_source_manager.get_china_stock_data_unified 接收到的股票代码: '{symbol}' (类型: {type(symbol)})",
    )
    logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(symbol))}")
    logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(symbol))}")

    manager = get_data_source_manager()
    logger.info(
        f"🔍 [股票代码追踪] 调用 manager.get_stock_data，传入参数: symbol='{symbol}', start_date='{start_date}', end_date='{end_date}'",
    )
    result = manager.get_stock_data(symbol, start_date, end_date)
    # 分析返回结果的详细信息
    # 类型保护：处理各种可能的返回类型
    lines = []
    data_lines = []
    if isinstance(result, str) and result and not result.startswith("❌"):
        lines = result.split("\n")
        data_lines = [line for line in lines if "2025-" in line and symbol in line]
    elif isinstance(result, tuple):
        # 处理 tuple 类型的返回值
        text = str(result[0]) if result[0] and not str(result[0]).startswith("❌") else ""
        lines = text.split("\n") if text else []
        data_lines = [line for line in lines if "2025-" in line and symbol in line]
        result = text  # 修正 result 为字符串
    elif result is None:
        pass  # lines/data_lines 保持空列表
    else:
        logger.warning(f"⚠️ [股票代码追踪] 意外的返回类型: {type(result)}")

    if lines:
        logger.info(
            f"🔍 [股票代码追踪] 返回结果统计: 总行数={len(lines)}, 数据行数={len(data_lines)}, 结果长度={len(result)}字符",
        )
        logger.info(f"🔍 [股票代码追踪] 返回结果前500字符: {result[:500]}")
        if len(data_lines) > 0:
            logger.info(
                f"🔍 [股票代码追踪] 数据行示例: 第1行='{data_lines[0][:100]}', 最后1行='{data_lines[-1][:100]}'",
            )
    else:
        logger.info("🔍 [股票代码追踪] 返回结果: None")
    return result


def get_china_stock_info_unified(symbol: str) -> dict:
    """
    统一的中国股票信息获取接口

    Args:
        symbol: 股票代码

    Returns:
        Dict: 股票基本信息
    """
    manager = get_data_source_manager()
    return manager.get_stock_info(symbol)


# 全局数据源管理器实例
_data_source_manager = None


def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
        atexit.register(_data_source_manager.shutdown)
    return _data_source_manager


# ==================== 兼容性接口 ====================
# 为了兼容 stock_data_service，提供相同的接口


def get_stock_data_service() -> DataSourceManager:
    """
    获取股票数据服务实例（兼容 stock_data_service 接口）

    ⚠️ 此函数为兼容性接口，实际返回 DataSourceManager 实例
    推荐直接使用 get_data_source_manager()
    """
    return get_data_source_manager()


# US data source manager has been removed
