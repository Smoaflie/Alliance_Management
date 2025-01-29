import logging
import sys

import redis

logger = logging.getLogger(__name__)

def init_redis(redis_config):
    try:
        redis_client = redis.Redis(
            host=redis_config.get("host", "localhost"),
            port=redis_config.get("port", 6379),
            db=redis_config.get("db", 0)
        )
        redis_path = f'redis://{redis_client.connection_pool.connection_kwargs["host"]}:{redis_client.connection_pool.connection_kwargs["port"]}/{redis_client.connection_pool.connection_kwargs["db"]}'
        # 验证连接
        if redis_client.ping():
            logger.info(f"Redis {redis_path}: 连接成功")
        else:
            logger.error(f"Redis {redis_path}: 连接失败")
        return redis_client
    except redis.ConnectionError as e:
        sys.exit(f"Redis {redis_path} 连接错误: {e}"
                 "请检查配置")
