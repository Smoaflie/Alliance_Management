import logging
import ujson
from datetime import datetime
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from scripts.utils import DEBUG_OUT

mini_program_bp = Blueprint('feishu_mini_program_bp', __name__)

@mini_program_bp.route("/fetch", methods=["GET"])
def fetch():
    oid = request.args.get("oid")
    try:
        from app import database
        result = database.get_item(int(oid))
        return jsonify(result)
    except ValueError:
        abort(404, description=f"Item with oid:{oid} not found")
        
@mini_program_bp.route("/operate", methods=["POST"])
def operate():
    DEBUG_OUT(data = request.json)
    object = request.json.get("object")
    operation = request.json.get("operation")
    operator = request.json.get("operatorName")
    purpose = request.json.get("purpose")
    msg = request.json.get("msg")
    try:
        from app import database
        operator_user_id = database.get_member(user_name=operator).get('user_id') 
        if operation == 'apply':
            error_message = None
            item_info = database.get_item(int(object['oid']))
            if item_info['useable'][0] != '可用':
                error_message = f'Error: 物品不可用,oid: {object['oid']}'
            if not error_message:
                from app.feishu.commands import create_approval_about_apply_items
                create_approval_about_apply_items(user_id=operator_user_id,
                    selectedObjectList={"name":[object['name']], "oid":[object['oid']]},purpose=purpose)
                return jsonify('success: 已发送申请')
            else:
                return abort(500, description=f"Error: {error_message}")
        elif operation == 'return':
            result = database.return_item(oid=object['oid'], user_id=operator_user_id)
            return jsonify(result)
        elif operation == 'report':
            msg = f"{operator} 报告物品 {object} 存在问题： {msg}"
            from app.feishu.config import message_api_client
            from app.feishu.config import ADMIN_USER_ID
            message_api_client.send_text_with_user_id(ADMIN_USER_ID,msg)
            return jsonify()
    except ValueError as e:
        return abort(500, description=f"Error: {e}")