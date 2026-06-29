"""
Redis客户端配置和连接管理
"""

import logging

import redis.asyncio as redis

from .config import settings

logger = logging.getLogger(__name__)

# 全局Redis连接池
redis_pool: redis.ConnectionPool | None = None
redis_client: redis.Redis | None = None


async def init_redis():
    """初始化Redis连接（支持无密码降级）"""
    global redis_pool, redis_client

    try:
        # 创建连接池
        redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,  # 使用配置文件中的值
            retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
            decode_responses=True,
            socket_timeout=5,  # 操作超时（5秒）
            socket_connect_timeout=5,  # 连接超时（5秒）
            socket_keepalive=True,  # 启用 TCP keepalive
            socket_keepalive_options={
                1: 60,  # TCP_KEEPIDLE: 60秒后开始发送keepalive探测
                2: 10,  # TCP_KEEPINTVL: 每10秒发送一次探测
                3: 3,  # TCP_KEEPCNT: 最多发送3次探测
            },
            health_check_interval=30,  # 每30秒检查一次连接健康状态
        )

        # 创建Redis客户端
        redis_client = redis.Redis(connection_pool=redis_pool)

        # 测试连接
        await redis_client.ping()
        logger.info(f"✅ Redis连接成功建立 (max_connections={settings.REDIS_MAX_CONNECTIONS})")

    except redis.AuthenticationError:
        # BUG #2: Redis AUTH 失败时自动降级为无密码连接
        logger.warning("⚠️ Redis AUTH 失败（密码不匹配），尝试无密码连接...")
        await _init_redis_no_auth()

    except Exception as e:
        logger.error(f"❌ Redis连接失败: {e}")
        raise


async def _init_redis_no_auth():
    """降级初始化：使用无密码 Redis 连接"""
    global redis_pool, redis_client

    try:
        # 清理旧连接
        if redis_client:
            await redis_client.close()
        if redis_pool:
            await redis_pool.disconnect()

        no_auth_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

        redis_pool = redis.ConnectionPool.from_url(
            no_auth_url,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            socket_keepalive_options={
                1: 60,
                2: 10,
                3: 3,
            },
            health_check_interval=30,
        )

        redis_client = redis.Redis(connection_pool=redis_pool)

        await redis_client.ping()
        logger.info(f"✅ Redis无密码连接成功建立（降级模式, max_connections={settings.REDIS_MAX_CONNECTIONS})")

    except Exception as e:
        logger.error(f"❌ Redis无密码降级连接也失败: {e}")
        raise


async def close_redis():
    """关闭Redis连接"""
    global redis_pool, redis_client

    try:
        if redis_client:
            await redis_client.close()
        if redis_pool:
            await redis_pool.disconnect()
        logger.info("✅ Redis连接已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭Redis连接时出错: {e}")


def get_redis() -> redis.Redis | None:
    """获取Redis客户端实例（Redis不可用时返回None，不抛异常）

    Returns:
        Redis客户端实例，如果Redis未初始化则返回None
    """
    if redis_client is None:
        logger.warning("⚠️ [BUG-009] Redis客户端未初始化，返回None（降级模式）")
        return None
    return redis_client


class RedisKeys:
    """Redis键名常量"""

    # 队列相关
    USER_PENDING_QUEUE = "user:{user_id}:pending"
    USER_PROCESSING_SET = "user:{user_id}:processing"
    GLOBAL_PENDING_QUEUE = "global:pending"
    GLOBAL_PROCESSING_SET = "global:processing"

    # 任务相关
    TASK_PROGRESS = "task:{task_id}:progress"
    TASK_RESULT = "task:{task_id}:result"
    TASK_LOCK = "task:{task_id}:lock"

    # 批次相关
    BATCH_PROGRESS = "batch:{batch_id}:progress"
    BATCH_TASKS = "batch:{batch_id}:tasks"
    BATCH_LOCK = "batch:{batch_id}:lock"

    # 用户相关
    USER_SESSION = "session:{session_id}"
    USER_RATE_LIMIT = "rate_limit:{user_id}:{endpoint}"
    USER_DAILY_QUOTA = "quota:{user_id}:{date}"

    # 系统相关
    QUEUE_STATS = "queue:stats"
    SYSTEM_CONFIG = "system:config"
    WORKER_HEARTBEAT = "worker:{worker_id}:heartbeat"

    # 缓存相关
    SCREENING_CACHE = "screening:{cache_key}"
    ANALYSIS_CACHE = "analysis:{cache_key}"


class RedisService:
    """Redis服务封装类（当Redis不可用时所有方法自动降级）"""

    def __init__(self):
        """初始化Redis服务，Redis不可用时self.redis为None"""
        self.redis = get_redis()
        if self.redis is None:
            logger.warning("⚠️ [BUG-009] RedisService运行在降级模式（Redis不可用）")

    async def set_with_ttl(self, key: str, value: str, ttl: int = 3600):
        """设置带TTL的键值"""
        if self.redis is None:
            return
        try:
            await self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis set_with_ttl 失败（降级跳过）: {e}")

    async def get_json(self, key: str):
        """获取JSON格式的值"""
        if self.redis is None:
            return None
        try:
            import json

            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis get_json 失败（降级跳过）: {e}")
            return None

    async def set_json(self, key: str, value: dict, ttl: int | None = None):
        """设置JSON格式的值"""
        if self.redis is None:
            return
        try:
            import json

            json_str = json.dumps(value, ensure_ascii=False)
            if ttl:
                await self.redis.setex(key, ttl, json_str)
            else:
                await self.redis.set(key, json_str)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis set_json 失败（降级跳过）: {e}")

    async def increment_with_ttl(self, key: str, ttl: int = 3600):
        """递增计数器并设置TTL"""
        if self.redis is None:
            return 0
        try:
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl)
            results = await pipe.execute()
            return results[0]
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis increment_with_ttl 失败（降级跳过）: {e}")
            return 0

    async def add_to_queue(self, queue_key: str, item: dict):
        """添加项目到队列"""
        if self.redis is None:
            return
        try:
            import json

            await self.redis.lpush(queue_key, json.dumps(item, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis add_to_queue 失败（降级跳过）: {e}")

    async def pop_from_queue(self, queue_key: str, timeout: int = 1):
        """从队列弹出项目"""
        if self.redis is None:
            return None
        try:
            import json

            result = await self.redis.brpop(queue_key, timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis pop_from_queue 失败（降级跳过）: {e}")
            return None

    async def get_queue_length(self, queue_key: str):
        """获取队列长度"""
        if self.redis is None:
            return 0
        try:
            return await self.redis.llen(queue_key)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis get_queue_length 失败（降级跳过）: {e}")
            return 0

    async def add_to_set(self, set_key: str, value: str):
        """添加到集合"""
        if self.redis is None:
            return
        try:
            await self.redis.sadd(set_key, value)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis add_to_set 失败（降级跳过）: {e}")

    async def remove_from_set(self, set_key: str, value: str):
        """从集合移除"""
        if self.redis is None:
            return
        try:
            await self.redis.srem(set_key, value)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis remove_from_set 失败（降级跳过）: {e}")

    async def is_in_set(self, set_key: str, value: str):
        """检查是否在集合中"""
        if self.redis is None:
            return False
        try:
            return await self.redis.sismember(set_key, value)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis is_in_set 失败（降级跳过）: {e}")
            return False

    async def get_set_size(self, set_key: str):
        """获取集合大小"""
        if self.redis is None:
            return 0
        try:
            return await self.redis.scard(set_key)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis get_set_size 失败（降级跳过）: {e}")
            return 0

    async def acquire_lock(self, lock_key: str, timeout: int = 30):
        """获取分布式锁"""
        if self.redis is None:
            return None
        try:
            import uuid

            lock_value = str(uuid.uuid4())
            acquired = await self.redis.set(lock_key, lock_value, nx=True, ex=timeout)
            if acquired:
                return lock_value
            return None
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis acquire_lock 失败（降级跳过）: {e}")
            return None

    async def release_lock(self, lock_key: str, lock_value: str):
        """释放分布式锁"""
        if self.redis is None:
            return 0
        try:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            return await self.redis.eval(lua_script, 1, lock_key, lock_value)
        except Exception as e:
            logger.warning(f"⚠️ [BUG-009] Redis release_lock 失败（降级跳过）: {e}")
            return 0


# 全局Redis服务实例
redis_service: RedisService | None = None


def get_redis_service() -> RedisService:
    """获取Redis服务实例（Redis不可用时返回降级实例，不抛异常）"""
    global redis_service
    if redis_service is None:
        redis_service = RedisService()
    return redis_service
