import os
import __main__

from flask import Flask

from app.database import Database
from scripts.utils import get_project_root
from scripts.utils import load_file
# 创建 Flask 实例
app = Flask("management")

# 配置文件路径
config_path = os.path.join(get_project_root(), "settings.json")
# 加载配置文件
config_data = load_file(config_path)
app.config.update(config_data)
# 解析配置文件
app.config["REDIS_HOST"] = REDIS_HOST = app.config.get('redis').get('host')
app.config["REDIS_PORT"] = REDIS_PORT = app.config.get('redis').get('port')
app.config["REDIS_DB"] = REDIS_DB = app.config.get('redis').get('db')
app.config['CELERY_BROKER_URL'] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
app.config['CELERY_RESULT_BACKEND'] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

# 初始化数据库
database = Database(app.config['mysql'])
