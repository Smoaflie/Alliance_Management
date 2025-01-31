from flask import Blueprint

# 配置 BP
feishu_bp = Blueprint('feishu', __name__, url_prefix='/feishu')

def init_project_feishu(feishu_config):
    from .config import (
        update_members,
        sub_approval_event
    )
    # 执行初始化流程
    update_members()
    sub_approval_event()
    test_func()
    # 注册蓝图
    from .events import events_bp
    from .web import web_bp
    feishu_bp.register_blueprint(events_bp)
    feishu_bp.register_blueprint(web_bp)

def test_func():
    from .config import task_api_client
    from scripts.utils import DEBUG_OUT
    resp = \
        task_api_client.fetch_task_detail('5f80a679-84ba-40a0-96be-b022d5176165')
    DEBUG_OUT(resp)
    
    resp = task_api_client.delete_task_lists('5f80a679-84ba-40a0-96be-b022d5176165')
    DEBUG_OUT(resp)
