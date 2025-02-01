from flask import Blueprint

# 配置 BP
feishu_bp = Blueprint('feishu', __name__, url_prefix='/feishu')

def init_project_feishu(feishu_config):
    from .commands.init import (
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
    import ujson
    from scripts.utils import DEBUG_OUT,safe_get
    from .config import FEISHU_CONFIG as _fs
    from .config import database as _db
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
    resp = _fs.api.task.get_inventory_list()
    inventory_list = safe_get(resp,"data","items")
    
    # for i in range(3):
    #     resp = _fs.api.task.create_inventory(name="a"+str(i), members=[{'id':user_id} for user_id in user_id_list])

    for item in inventory_list:
        guid = item.get('guid')
        _fs.api.task.delete_task_inventory(guid)
    # 建立与话题群内话题相对应的任务清单
    resp = _fs.api.message.list(container_id_type='chat',container_id='oc_e373c228a55f34a70af85dce94d96e23')
    thread_list = safe_get(resp,"data","items")
    for thread in thread_list:
        try:
            content = ujson.loads(thread['body']['content'])
            text = safe_get(content,'content',0,0,'text')
            if text != None:
                thread_id = thread.get('thread_id')
                creator_open_id = safe_get(thread,"sender","id")
                message_id = thread.get('message_id')
                create_time = thread.get('create_time')
                update_time = thread.get('update_time')
                deleted = thread.get('deleted')

                # if _db.fetchone(table='projects', key='thread_id', value=thread_id):
                #     _db.insert(table='projects', data={
                #         "creator_open_id":creator_open_id,
                #         "thread_id":thread_id,
                #         "message_id":message_id,
                #         "create_time":create_time,
                #         "update_time":update_time,
                #         "deleted":1 if deleted else 0
                #     })
                #     _fs.api.task.create_inventory(name=text, members=[{'id':user_id, 'role':'editor'} for user_id in user_id_list])
        except ujson.JSONDecodeError:
            pass

    # resp = _fs.api.message.list(container_id_type='chat',container_id='oc_e373c228a55f34a70af85dce94d96e23')
    DEBUG_OUT(resp)