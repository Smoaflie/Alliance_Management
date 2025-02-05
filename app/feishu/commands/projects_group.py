import logging
import ujson
from ..config import FEISHU_CONFIG as _fs
from scripts.utils import safe_get

logger = logging.getLogger(__name__)

ADMIN_CONFIG = _fs.admin_config
PROJECT_CHAT_ID = _fs.projects_management.chat_id


def _get_all_threads():
    """获取所有主题"""
    page_token = None
    thread_list = []
    while True:
        resp = _fs.api.message.list(
            container_id_type="chat",
            container_id=PROJECT_CHAT_ID,
            page_size=50,
            page_token=page_token,
        )
        _list = safe_get(resp, "data", "items")
        if _list:
            thread_list.extend(_list)
        page_token = safe_get(resp, "data", "page_token")
        if not page_token:
            break
    return thread_list


def _get_all_chat_members(member_id_type: str = "user_id"):
    """获取群组成员列表"""
    chat_member_list = []
    page_token = None
    while True:
        resp = _fs.api.chat.get_members(
            chat_id=PROJECT_CHAT_ID,
            member_id_type=member_id_type,
            page_size=50,
            page_token=page_token,
        )
        page_token = safe_get(resp, "data", "page_token")
        chat_member_list.extend(safe_get(resp, "data", "items"))
        if not page_token:
            break
    return chat_member_list


def _get_all_inventories():
    """获取所有任务清单"""
    page_token = None
    inventory_list = []
    while True:
        resp = _fs.api.task.get_inventory_list()
        _list = safe_get(resp, "data", "items")
        if _list:
            inventory_list.extend(_list)
        page_token = safe_get(resp, "data", "page_token")
        if not page_token:
            break
    return inventory_list


def delete_all_inventories():
    """!危险 删除所有任务清单"""
    inventory_list = _get_all_inventories()
    for item in inventory_list:
        _fs.api.task.delete_task_inventory(item["guid"])


def traverse_threads_and_create_inventories():
    """(初始化)遍历话题群消息，建立相对应的任务清单"""

    # 获取群组成员user_id列表
    chat_member_list = _get_all_chat_members(member_id_type="user_id")
    chat_members_user_id_list = [member["member_id"] for member in chat_member_list]

    # 获取管理员user_id列表
    admin_user_id_list = _fs.admin_config.user_id_list

    # 获取所有主题
    thread_list = _get_all_threads()

    # 获取已存在的所有任务清单名
    inventory_list = _get_all_inventories()
    existed_inventory_name = [item["name"] for item in inventory_list]

    # 创建任务清单,设置全体话题群成员为编辑者
    for thread in thread_list:
        try:
            content = ujson.loads(thread["body"]["content"])
            creator_open_id = thread["sender"]["id"]
            inventory_name = safe_get(content, "content", 0, 0, "text")

            if inventory_name != None and inventory_name not in existed_inventory_name:
                resp = _fs.api.task.create_inventory(
                    name=inventory_name,
                    members=[
                        {"id": user_id, "role": "viewer"}
                        for user_id in chat_members_user_id_list
                    ]
                    + [
                        {"id": user_id, "role": "editor"}
                        for user_id in admin_user_id_list
                    ],
                )
                _fs.api.task.add_inventory_member(
                    guid=safe_get(resp, "data", "tasklist", "guid"),
                    members=[{"id": creator_open_id, "role": "editor"}],
                    user_id_type="open_id",
                )
                logger.info("add task inventory %s" % inventory_name)
        except ujson.JSONDecodeError:
            pass


def new_thread_in_project_group_callback(message: str):
    """
    检测到话题群内新建话题时触发，新建任务
    """
    # 获取群组成员user_id列表
    chat_member_list = _get_all_chat_members(member_id_type="user_id")
    chat_members_user_id_list = [member["member_id"] for member in chat_member_list]

    # 创建任务清单,设置全体话题群成员为编辑者
    content = ujson.loads(message["content"])
    inventory_name = safe_get(content, "content", 0, 0, "text")
    if inventory_name != None:
        resp = _fs.api.task.create_inventory(
            name=inventory_name,
            members=[
                {"id": user_id, "role": "editor"}
                for user_id in chat_members_user_id_list
            ],
        )
        logger.info("add task inventory %s" % inventory_name)
