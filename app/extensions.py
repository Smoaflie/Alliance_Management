import logging
from time import time
from functools import wraps

import redis
from flask import request, jsonify
from celery import Celery

logger = logging.getLogger(__name__)
# 用于记录警告是否已显示
logger_shown = False

redis_client = None
celery = None

# 限制请求频率
REQUEST_LIMIT = 1  # 限制的请求次数
TIME_WINDOW = 3  # 时间窗口，单位为秒

def init_redis(app):
    global redis_client
    redis_client = redis.Redis(
        host=app.config.get("REDIS_HOST", "localhost"),
        port=app.config.get("REDIS_PORT", 6379),
        db=app.config.get("REDIS_DB", 0)
    )

def init_celery(app):
    global celery
    celery = Celery(app.name, broker=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'))
    celery.conf.update(app.config)

def is_celery_running():
    """检查 Celery 服务是否运行"""
    global logger_shown
    try:
        # 发送 ping 指令，检测是否有活跃的 worker
        response = celery.control.ping(timeout=1)
        celery_status = len(response) > 0  # 如果有 worker 响应，则服务正常
    except (TimeoutError, IOError):
        celery_status = False
    if not logger_shown:
        logger_shown = True
        if not celery_status:
            logger.warning("Celery 服务未运行，这可能会导致某些功能无法正常工作。")
        else:
            logger.info("Celery 服务正常运行。")
    return celery_status
    
'''
wraps
'''
def celery_task(func):
    """
    装饰器：如果 Celery 服务运行，则将函数作为 Celery 任务。
    否则，直接同步调用函数。
    """
    # 使用 Celery 的 task 装饰器来装饰函数
    if is_celery_running():
        task = celery.task(func)
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 通过 Celery 异步执行
            return task.apply_async(args=args, kwargs=kwargs)
    else:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 同步直接执行函数
            return func(*args, **kwargs)
    return wrapper

def rate_limit(event_type):
    """用于限制请求频率的装饰器."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_id = request.json.get('event').get('operator').get('user_id')
            current_time = time()

            # 生成唯一键
            key = f"{user_id}:{event_type}"

            # 获取当前请求次数
            request_count = redis_client.zcard(key)

            # 检查是否超过限制
            if request_count >= REQUEST_LIMIT:
                return jsonify({"error": "请求频率过高"}), 403

            # 添加当前请求时间
            redis_client.zadd(key, {current_time: current_time})

            # 设置过期时间，确保在时间窗口结束后自动删除键
            redis_client.expire(key, TIME_WINDOW)

            return func(*args, **kwargs)
        return wrapper
    return decorator
