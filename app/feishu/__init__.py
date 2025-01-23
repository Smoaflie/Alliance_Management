from flask import Blueprint
from app.feishu.config import (
    update_members,
    sub_approval_event
)
# 配置 BP
feishu_bp = Blueprint('feishu', __name__, url_prefix='/feishu')

# 执行初始化流程
update_members()
sub_approval_event()