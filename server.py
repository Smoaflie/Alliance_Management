#!/usr/bin/env python3.12.3

import os
import logging
import requests
from scripts.api.api_client import MessageApiClient, SpreadsheetApiClient, ContactApiClient, CloudApiClient
from scripts.api.api_event import MessageReceiveEvent, UrlVerificationEvent, EventManager, BotMenuClickEvent, CardActionEvent
from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv, find_dotenv
from scripts.api.api_management import ApiManagement
from scripts.api import api_mysql as mysql
from scripts.api.api_self import debug
import ujson
import datetime
import hashlib

# from scripts.api import debug

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
contact_api_client = ContactApiClient(APP_ID, APP_SECRET, LARK_HOST)
cloud_api_client = CloudApiClient(APP_ID, APP_SECRET, LARK_HOST)
event_manager = EventManager()


@app.errorhandler
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response

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
    # message_api_client.send_text_with_open_id(open_id, text_content)
    return jsonify()

@event_manager.register("application.bot.menu_v6")
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key
    
    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = {
            'type':'template',
            'data':create_card(object_id='0')
        }
        message_api_client.send_interactive_with_user_id(user_id, ujson.dumps(content))
    elif event_key == 'custom_menu.test':
        #todo:调试用，记得删
        content = {
            'type':'template',
            'data':create_card(object_id='1001001')
        }
        content['data']['template_variable']['param1'] = str(content['data']['template_variable']['param1'])
        message_api_client.send_interactive_with_user_id(user_id, ujson.dumps(content))
        
        # return jsonify()
    return jsonify()
def create_card(object_id=None, father_id=None):
    title_map = {
        '1':{'template_id':'AAq7rfpwDmKrO', 'table':'item_category', 'title':"物资类型", 'param1':'ID', 'param2':'名称', 'param3':'数量', 'param4':""},
        '2':{'template_id':'AAq7rfpwDmKrO', 'table':'item_list', 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量', 'param4':""},
        '3':{'template_id':'AAq7rfpwDmKrO', 'table':'item_info', 'title':"物资仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态', 'param4':""},
        '4':{'template_id':'AAq7gOddRQSIf', 'table':'item_info', 'title':"", 'param1':'', 'param2':'', 'param3':'', 'param4':""}
    }
    if object_id:
        object_id = int(object_id)
        _father_id = str(object_id)
        title_id = '1' if object_id==0 else ('2' if object_id < 1000 else ('3' if object_id < 1000000 else '4') )
        _id = object_id
    elif father_id:
        father_id = int(father_id)
        _father_id = str(int(father_id/1000))
        title_id = '1' if father_id<1000 else ('2' if father_id < 1000000 else '3')
        _id = _father_id
    else:
        raise Exception("参数错误")
    
    if title_id == '1':
        _list = management.get_category()
        object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_), 'id':id_} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])]
    elif title_id == '2':
        _list = management.get_list(father=_id)
        object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_), 'id':id_} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])]
    elif title_id == '3':
        _list = management.get_items(father=_id)
        object_list =[{'param1': id_, 'param2': name_, 'param3': useable_, 'id':id_} 
                    for id_, name_, useable_ in zip(_list['id'], _list['name'], _list['useable'])]
    else:
        object_list = []
        _item = management.get_item(oid=_id)
        title_map[title_id]['title'] = f"您正在查看 {_item['name']} 详细信息"
        title_map[title_id]['param1'] = str(_item['id'])
        title_map[title_id]['param2'] = _item['useable']
        title_map[title_id]['param3'] = _item['wis']
        title_map[title_id]['param4'] = _item['do']

    data = {
        'template_id':title_map[title_id]['template_id'],
        'template_variable':{
            'title': title_map[title_id]['title'],
            'title_id': title_id,
            'object_list':object_list,
            'param1': title_map[title_id]['param1'],
            'param2': title_map[title_id]['param2'],
            'param3': title_map[title_id]['param3'],
            'param4': title_map[title_id]['param4'],
            'father_id':_father_id
        }
    }
    return data
        
@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    user_id = req_data.event.operator.user_id
    action = req_data.event.action
    token = req_data.event.token
    toast=None
    data=None

    if action.value.name == 'object.inspect':
        data = create_card(object_id=action.value.id)
    elif action.value.name == 'back':
        data = create_card(father_id=action.value.id)
    elif action.value.name == 'object.apply':
        member = management.get_member(user_id)
        print(member)
    request_data = {
        'toast':toast if toast else {},
        "card":{
            "type":"template",
            "data": data
        }
    } if data else {}

    return jsonify(request_data)

@app.route("/", methods=["POST"])
def callback_event_handler():    
    # 飞书事件回调
    with open('request.json', 'r+') as f:
            json_str = ujson.dumps(request.json, indent=4)# 格式化写入 JSON 文件
            f.write(str(json_str))
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

@app.before_first_request
def searchContactToAddMembers():
    # 获取飞书通讯录列表并自动填入members表中
    user_ids = contact_api_client.get_scopes(user_id_type='user_id').get('data').get('user_ids')
    items = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id').get('data').get('items')
    user_list = list()
    for item in items:
        user_list.append({
            'name':item['name'],
            'user_id':item['user_id']
        })
    #校验md5值，检测是否有变化
    list_string = ''.join(map(str, user_list))
    MD5remote = hashlib.md5()
    MD5remote.update(list_string.encode('utf-8'))
    MD5remote = MD5remote.hexdigest()

    MD5local = sql.fetchone('logs', 'do', 'used to detect changes in the contact.')

    if MD5local == 'null' or MD5local is None:
        sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the contact.'})
        MD5local = '0'
    else:
        MD5local = MD5local[1]

    if MD5local != MD5remote:
        management.add_member_batch(user_list)
        sql.update('logs',('do','used to detect changes in the contact.'),{'time':MD5remote})
        sql.commit()

@app.before_first_request
def getItemsBySheets():
    #校验修改时间，检测是否有变化
    latest_modify_time_remote = cloud_api_client.getDocMetadata([ITEM_SHEET_TOKEN], ['sheet']).get('data').get('metas')[0].get('latest_modify_time')
    latest_modify_time_local = sql.fetchone('logs', 'do', 'used to detect changes in the spreadsheet.')
    if latest_modify_time_local == 'null' or latest_modify_time_local is None:
        sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the spreadsheet.'})
        latest_modify_time_local = '0'
    else: 
        latest_modify_time_local = latest_modify_time_local[1]
    
    if latest_modify_time_local != latest_modify_time_remote:
        item_sheet = spreadsheet_api_client.fetchSheet(ITEM_SHEET_TOKEN).get('data').get('sheets')[0]
        item_list = spreadsheet_api_client.readRange(ITEM_SHEET_TOKEN, f"{item_sheet.get('sheet_id')}!A2:D").get('data').get('valueRange').get('values')
        print('add item by sheet')
        for item in item_list:
            category_name = item[0]
            item_name = item[1]
            item_num_total = item[2] if item[2] else 1
            item_num_broken = item[3] if item[3] else 0
            management.add_items_until_limit(father_name=item_name, category_name=category_name, num=item_num_total, num_broken=item_num_broken)
        sql.update('logs',('do','used to detect changes in the spreadsheet.'),{'time':latest_modify_time_remote})
        sql.commit()

if __name__ == "__main__":
    # 连接mysql服务器
    with open('settings.json', 'r') as f:
        settings = ujson.loads(f.read())
        sql = mysql.MySql(settings['mysql'])
        ITEM_SHEET_TOKEN = settings['sheet']['token']
        management = ApiManagement(sql)
    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
