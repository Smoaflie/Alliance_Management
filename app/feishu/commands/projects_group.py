from ..config import FEISHU_CONFIG as _fs

ADMIN_CONFIG = _fs.admin_config

def update_task_inventory(
    mode: int | str,
    task_name: str | None = None,
    task_id: str | None = None,
):
    """
    更新任务清单
    """
    mode_map = {
        0: 'add',
        1: 'remove',
    }
    if type(mode) is int:
        if mode not in mode_map:
            raise ValueError("mode value error.")
        mode = mode_map[mode]
    
    admin_user_id_list = ADMIN_CONFIG["user_id_list"]
    if mode == 'add':
        _fs.api.task.create_inventory(summary=task_name, members=[{"id":user_id} for user_id in admin_user_id_list])
    pass