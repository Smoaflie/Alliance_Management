import logging

from celery import Celery
from app import app

logger = logging.getLogger(__name__)
# 用于记录警告是否已显示
logger_shown = False

# 创建 Celery 实例，使用 Flask 配置

def init_celery():
    REDIS_HOST = app.config.get("redis").get("host", "localhost")
    REDIS_PORT = app.config.get("redis").get("port", 6379)
    REDIS_DB = app.config.get("redis").get("db", 0)
    app.config["CELERY_BROKER_URL"] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
    app.config["CELERY_RESULT_BACKEND"] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
init_celery()
app.config['CELERY_INCLUDE'] = ['app.feishu.commands']  # 确保 include 使用旧格式
celery = Celery(app.import_name, broker=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')) # 不知道为什么必须手动指定 broker
celery.conf.update(app.config)  # 更新 Celery 配置


def is_celery_running():
    """检查 Celery 服务是否运行"""
    celery_status = False
    try:
        # 发送 ping 指令，检测是否有活跃的 worker
        response = celery.control.ping(timeout=1)
        celery_status = len(response) > 0  # 如果有 worker 响应，则服务正常
    except (TimeoutError, IOError):
        pass
    except Exception as e:
        logger.error(f"Error in is_celery_running: {str(e)}")

    global logger_shown
    if not logger_shown:
        logger_shown = True
        if not celery_status:
            logger.warning("Celery 服务未运行，这可能会导致某些功能无法正常工作。")
        else:
            logger.info("Celery 服务正常运行。")
    return celery_status

