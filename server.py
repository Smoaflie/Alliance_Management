#!/usr/bin/env python3.12.3

import os
import logging
import requests
import re
import ast
from api_client import MessageApiClient
from api_client import SpreadsheetApiClient
from event import MessageReceiveEvent, UrlVerificationEvent, EventManager, BotMenuClickEvent, CardActionEvent
from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv, find_dotenv
from api_management import ApiManagement
import api_mysql as mysql
import ujson
import datetime
import json

# load env parameters form file named .env
load_dotenv(find_dotenv())

app = Flask(__name__)

# load from env
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
VERIFICATION_TOKEN = os.getenv("VERIFICATION_TOKEN")
ENCRYPT_KEY = os.getenv("ENCRYPT_KEY")
LARK_HOST = os.getenv("LARK_HOST")

# init service
spreadsheet_api_client = SpreadsheetApiClient(APP_ID, APP_SECRET, LARK_HOST)
message_api_client = MessageApiClient(APP_ID, APP_SECRET, LARK_HOST)
event_manager = EventManager()

@event_manager.register("url_verification")
def request_url_verify_handler(req_data: UrlVerificationEvent):
    # url verification, just need return challenge
    if req_data.event.token != VERIFICATION_TOKEN:
        raise Exception("VERIFICATION_TOKEN is invalid")
    return jsonify({"challenge": req_data.event.challenge})


@event_manager.register("im.message.receive_v1")
def message_receive_event_handler(req_data: MessageReceiveEvent):
    sender_id = req_data.event.sender.sender_id
    message = req_data.event.message
    if message.message_type != "text":
        logging.warn("Other types of messages have not been processed yet")
        return jsonify()
        # get open_id and text_content
    open_id = sender_id.open_id
    text_content = message.content
    # echo text message
    message_api_client.send_text_with_open_id(open_id, text_content)
    return jsonify()

@event_manager.register("application.bot.menu_v6")
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    operator_name = req_data.event.operator.operator_name
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key
    
    #添加用户信息到表
    management.add_member(user_id, operator_name)
    #获取全部物品类型，配置映射
    category = management.get_category()
    event_map = {f'custom_menu.inspect.{name}': id_ for id_, name in zip(category['id'], category['name'])}
    category_name = category['name']

    category_id = event_map.get(event_key)
    if category_id is not None:
        item_list = management.get_list(category_id)
        object_list = [{'category': category_name[father_-1], 'name': name_, 'num': str(total_)} 
                        for father_, name_, total_ in zip(item_list['father'], item_list['name'], item_list['total'])]
        data = {
            'type':'template',
            'data':{
                'template_id':'AAq7rfpwDmKrO',
                'template_variable':{
                    'object_list_1':object_list
                }
            }
        }

    json_string = ujson.dumps(data)
    message_api_client.send_interactive_with_user_id(user_id, json_string)
    return jsonify()

@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    user_id = req_data.event.operator.operator_id.user_id
    value = req_data.event.action.value

@app.errorhandler
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response


@app.route("/", methods=["POST"])
def callback_event_handler():
    # 获取 JSON 数据
    json_data = request.get_json()
    if json_data is not None:
        # 将 JSON 数据写入 'request.json' 文件
        with open('request.json', 'w') as f:
            json_str = ujson.dumps(json_data, indent=4)  # 格式化写入 JSON 文件
            f.write(json_str)
    # 飞书事件回调
    event_handler, event = event_manager.get_handler_with_event(VERIFICATION_TOKEN, ENCRYPT_KEY)

    return event_handler(event)

@app.route('/operation/get_materials')
def get_materials():
    if request.args.get('param') == 'category':   #获取物资分组
        return management.get_category()
    elif request.args.get('param') == 'materials':      #获取物资信息
        oid = request.args.get('id')
        if oid is None: #如id为空，则获取某组物资或全部物资
            father = request.args.get('father')
            if father:  #获取某组物资信息
                return management.get_list(father)
            else:   #获取全部物资信息
                return management.get_all()        
        else:   #如id不为空，则获取对应物资
            return management.get_item(oid)
        #todo： id指向空物品处理  
    else:
        abort(400)

def is_valid(sstr, errors):
    voidc = ["'", '"', '\\', '<', '>', '(', ')', '.', '=']
    for ccc in voidc:
        if ccc in str(sstr):
            errors.append(f'parameters error:\n"{sstr}" is not valid')
@app.route('/operation/submit', methods=['POST'])
def o_submit():
    info = {
            'time': "%s" % (datetime.datetime.now()),
            'openid': request.form.get('openid'),
            'operation': request.form.get('op'),
            'object': request.form.get('oid'),
            'name': request.form.get('name'),
            'num': request.form.get('num'),
            'do': request.form.get('do'),
            'wis': request.form.get('where'),
            'verify': 0
            }
    if info['operation'] == 'use':
        info['wis'] = request.form.get('pwhere')
    if info['do'] == '':
        info['do'] = None

    errors = []

    #todo:应处理特殊字符而非抛出错误
    is_valid(info['name'], errors)
    is_valid(info['do'], errors)
    if not errors:
        sql.insert('logs', info)
    else:
        return jsonify({'result': 'success','error': errors})
        

    msg = ''
    #todo: info['name'] = name = sql.fetchone('members', 'openid', info['openid'])[1]
    # name = sql.fetchone('members', 'openid', info['openid'])[1]
    name = info[name]
    if info['operation'] == 'in':
        sql.update('item_info', ['useable', 1, 'wis', info['wis'], 'do', info['do']], ['id', info['object']])
        obj = sql.fetchone('item_list', 'id', int(str(info['object'])[:6]))[2]
        msg = "%s 还入 %s %s 到 %s 仓库" % (name, obj, str(info['object']), info['wis'])
    elif info['operation'] == 'out':
        sql.update('item_info', ['useable', 0, 'wis', info['name'], 'do', info['do']], ['id', info['object']])
        obj = sql.fetchone('item_list', 'id', int(str(info['object'])[:6]))[2]
        msg = "%s 借出 %s %s" % (name, obj, str(info['object']))
    elif info['operation'] == 'use':
        sql.update('item_info', ['useable', 0, 'wis', info['wis'], 'do', info['do']], ['id', info['object']])
        obj = sql.fetchone('main', 'id', int(str(info['object'])[:6]))[1]
        msg = "%s 在 %s 使用 %s %s" % (name, info['wis'], obj, str(info['object']))
    # elif info['operation'] == 'create':
    #     sql.update('item_info', ['useable', 'id'], [1, info['object']])
    #     sql.update('item_info', ['wis', 'id'], [info['wis'], info['object']])
    #     sql.update('item_info', ['do', 'id'], [info['do'], info['object']])
    #     use = sql.fetchone('main', 'id', int(str(info['object'])[:6]))[3] + 1
    #     sql.update('main', ['useable', 'id'], [use, int(str(info['object'])[:6])])
    # elif info['operation'] == 'cbf':
    #     sql.update('item_info', ['useable', 'id'], [1, info['object']])
    #     use = sql.fetchone('main', 'id', int(str(info['object'])[:6]))[3] + 1
    #     sql.update('item_info', ['useable', 'id'], [use, int(str(info['object'])[:6])])
    # elif info['operation'] == 'bf':
    #     sql.update('item_info', ['useable', 'id'], [3, info['object']])
    #     use = sql.fetchone('main', 'id', int(str(info['object'])[:6]))[3] - 1
    #     sql.update('main', ['useable', 'id'], [use, int(str(info['object'])[:6])])
    #     sql.update('item_info', ['do', 'id'], [info['do'], info['object']])
    # elif info['operation'] == 're':
    #     sql.update('item_info', ['useable', 'id'], [2, info['object']])
    #     use = sql.fetchone('main', 'id', int(str(info['object'])[:6]))[3] - 1
    #     sql.update('main', ['useable', 'id'], [use, int(str(info['object'])[:6])])
    #     sql.update('item_info', ['do', 'id'], [info['do'], info['object']])
    #     sql.update('item_info', ['wis', 'id'], ['送修中', info['object']])
    elif info['operation'] == 'add_category':
        last = sql.getall('item_category')[-1][0]
        inf = {
            'id': last + 1,
            'name': info['do'],
        }
        sql.insert('item_category', inf)
    elif info['operation'] == 'add_item':
        i = sql.fetchall('item_info', 'father', info['object'])
        if i != ():
            i = i[-1][0] + 1
        else:
            i = int(info['object']) * 1000 + 1
        for j in range(int(info['num'])):
            ins = {
                'id': i + j,
                'father': i,
                'wis': info['wis'],
                'do': info['do']
            }
            sql.insert('item_info', ins)
    sql.commit()
    return jsonify({'result': 'success', 'msg': msg})


@app.route('/verify/list')
def ve_list():
    r = sql.fetchall('logs', 'verify', 0)
    if r == ():
        return '{"暂无需要确认操作":""}'
    info = {
        'ID': [],
        '时间': [],
        '申请人': [],
        '操作类型': [],
        '操作对象': [],
        '位置': [],
        '备注': []
    }
    for it in r:
        info['ID'].append(str(it[0]))
        info['时间'].append(str(it[1]))
        if it[3] == 'in':
            info['操作类型'].append('还入')
        elif it[3] == 'use':
            info['操作类型'].append('使用')
        elif it[3] == 'register':
            info['操作类型'].append('注册')
        elif it[3] == 'leave':
            info['操作类型'].append('请假')
        else:
            info['操作类型'].append('借出')
        if it[3] == 'register':
            info['申请人'].append(sql.fetchone('logs', 'id', it[0])[5])
        else:
            info['申请人'].append(sql.fetchone('members', 'openid', it[2])[1])
        info['操作对象'].append(str(it[4]))
        info['位置'].append(str(it[9]))
        info['备注'].append(str(it[8]))
    return ujson.dumps(info)

if __name__ == "__main__":
    # 连接mysql服务器
    f = open('settings.json', 'r')
    settings = ujson.loads(f.read())
    f.close()
    sql = mysql.MySql(settings['mysql'])
    management = ApiManagement(sql)

    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
