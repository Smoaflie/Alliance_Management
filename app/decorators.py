from time import time
from functools import wraps
from flask import request, jsonify
from app import app
from app.ext.celery import is_celery_running, celery

# 限制请求频率
REQUEST_LIMIT = 1  # 限制的请求次数
TIME_WINDOW = 3  # 时间窗口，单位为秒

def celery_task(func):
    """
    装饰器：如果 Celery 服务运行，则将函数作为 Celery 任务。
    否则，直接同步调用函数。
    """
    # 使用 Celery 的 task 装饰器来装饰函数
    task = celery.task(func)
    @wraps(func)
    def wrapper(*args, **kwargs):
        if is_celery_running():
            # 通过 Celery 异步执行
            return task.apply_async(args=args, kwargs=kwargs)
        else:
            # 同步直接执行函数
            return func(*args, **kwargs)
    return wrapper

def rate_limit(event_type):
    """基于redis, 用于限制请求频率的装饰器."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            redis_client = app.config.get('redis_client')
            if redis_client:
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
