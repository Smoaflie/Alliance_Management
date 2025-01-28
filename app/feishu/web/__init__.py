#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import time
import hashlib
import requests
from .auth import Auth
from flask import Blueprint
from flask import request, jsonify, render_template
from app.feishu.config import APP_ID, APP_SECRET, FEISHU_HOST
# const
# 随机字符串，用于签名生成加密使用
NONCE_STR = "14oEviLbrTo458A3NjrOwS70oTOXVOAm"
# 初始化 flask 蓝图
web_bp = Blueprint("feishu_web", __name__, 
                   static_url_path="/public", 
                   static_folder="./public",
                   template_folder="./templates")

# 应用出现错误时，实用flask的errorhandler装饰器实现应用错误处理
# @web_bp.errorhandler(Exception)
# def auth_error_handler(ex):
#     response = jsonify(message=str(ex))
#     response.status_code = (
#         ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
#     )
#     return response

# 用获取的环境变量初始化Auth类，由APP ID和APP SECRET获取access token，进而获取jsapi_ticket
auth = Auth(FEISHU_HOST, APP_ID, APP_SECRET)

# 默认的主页路径
@web_bp.route("/", methods=["GET"])
def get_home():
    # 打开本网页应用执行的第一个函数
    # 展示主页
    return render_template("index.html")

# 获取并返回接入方前端将要调用的config接口所需的参数
@web_bp.route("/get_config_parameters", methods=["GET"])
def get_config_parameters():    
    # 接入方前端传来的需要鉴权的网页url
    url = request.args.get("url")
    # 初始化Auth类时获取的jsapi_ticket
    ticket = auth.get_ticket()
    # 当前时间戳，毫秒级
    timestamp = int(time.time()) * 1000
    # 拼接成字符串 
    verify_str = "jsapi_ticket={}&noncestr={}&timestamp={}&url={}".format(
        ticket, NONCE_STR, timestamp, url
    )
    # 对字符串做sha1加密，得到签名signature
    signature = hashlib.sha1(verify_str.encode("utf-8")).hexdigest()
    # 将鉴权所需参数返回给前端
    return jsonify(
        {
            "appid": APP_ID,
            "signature": signature,
            "noncestr": NONCE_STR,
            "timestamp": timestamp,
        }
    )
