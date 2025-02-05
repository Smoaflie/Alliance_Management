import os
from flask import Blueprint
from flask import request, jsonify, render_template

# 获取当前模块的目录
bp_dir = os.path.abspath(os.path.dirname(__file__))

# 配置 BP
web_bp = Blueprint(
    "web",
    __name__,
    static_url_path="/public",
    static_folder=os.path.join(bp_dir, "public"),
    template_folder=os.path.join(bp_dir, "templates"),
)


# 默认的主页路径
@web_bp.route("/", methods=["GET"])
def get_home():
    # 展示主页
    return render_template("app/index.html")
