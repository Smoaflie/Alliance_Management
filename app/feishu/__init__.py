from flask import Blueprint

# 配置 BP
feishu_bp = Blueprint("feishu", __name__, url_prefix="/feishu")


def init_project_feishu(feishu_config):
    from .commands.init import (
        update_members,
        sub_approval_event,
        traverse_threads_and_create_inventories,
        check_bitables,
    )

    # 执行初始化流程
    update_members()
    sub_approval_event()
    traverse_threads_and_create_inventories()
    check_bitables()

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
    import os
    # delete_all_inventories()
