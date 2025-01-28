from flask import Blueprint

# 配置 BP
feishu_bp = Blueprint('feishu', __name__, url_prefix='/feishu')

def init_project_feishu(feishu_config):
    from app.feishu.config import (
        update_members,
        sub_approval_event
    )
    # 执行初始化流程
    update_members()
    sub_approval_event()
    # 注册蓝图
    from app.feishu.events import events_bp
    from app.feishu.mini_program import mini_program_bp
    from app.feishu.web import web_bp
    feishu_bp.register_blueprint(events_bp)
    feishu_bp.register_blueprint(mini_program_bp)
    feishu_bp.register_blueprint(web_bp)
    