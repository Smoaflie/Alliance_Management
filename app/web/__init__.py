from flask import Blueprint
from flask import request, jsonify, render_template

# 配置 BP
web_bp = Blueprint("web", __name__, 
                   static_url_path="/public", 
                   static_folder="./public",
                   template_folder="./templates")

# 默认的主页路径
@web_bp.route("/", methods=["GET"])
def get_home():
    # 打开本网页应用执行的第一个函数
    # 展示主页
    return render_template("index.html")