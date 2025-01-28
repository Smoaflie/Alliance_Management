import os
import __main__

from flask import Flask

from app.ext.database import Database
from app.ext.redis import init_redis
from scripts.utils import get_project_root
from scripts.utils import load_file

# 创建 Flask 实例
app = Flask("management")
# 配置文件路径
config_path = os.path.join(get_project_root(), "settings.json")
# 加载配置文件
config_data = load_file(config_path)
app.config.update(config_data)

# 初始化数据库
app.config["database"] = Database(app.config['mysql'])
# 初始化redis
app.config['redis_client'] = init_redis(app.config.get('redis'))

def init_app(app):
    # 初始化database
    app.config["database"].init_database()
    # 初始化子模块
    init_projects(app)
    # 注册蓝图
    register_blueprints(app)

# 初始化子模块
def init_projects(app):
    from app.feishu import init_project_feishu
    init_project_feishu(app.config.get("feishu"))

def register_blueprints(app):
    from app.feishu import feishu_bp
    app.register_blueprint(feishu_bp)