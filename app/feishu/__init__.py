from flask import Blueprint

# 配置 BP
feishu_bp = Blueprint('feishu', __name__, url_prefix='/feishu')

def init_project_feishu(feishu_config):
    from .commands.init import (
        update_members,
        sub_approval_event,
        traverse_threads_and_create_inventories
    )
    # 执行初始化流程
    update_members()
    sub_approval_event()
    traverse_threads_and_create_inventories()

    test_func()
    # 注册蓝图
    from .events import events_bp
    from .web import web_bp
    feishu_bp.register_blueprint(events_bp)
    feishu_bp.register_blueprint(web_bp)

def test_func():
    import copy
    from .config import FEISHU_CONFIG as _fs
    from scripts.utils import DEBUG_OUT
    from .commands.projects_group import delete_all_inventories
    admin_config = _fs.admin_config
    def send_to_admin(context):
        chat_id = admin_config.chat_id
        _fs.api.message.send(
            receive_id=chat_id,
            receive_id_type='chat_id',
            msg_type='text',
            content = {
                "text": context
            }
        )
    user_id_list = admin_config.user_id_list
    # api_message = copy.deepcopy(_fs.api.message).set_identity
    chat_id=admin_config.chat_id
    # resp = _fs.api.message.list(container_id_type='chat',container_id='oc_e373c228a55f34a70af85dce94d96e23')
    # DEBUG_OUT(resp)