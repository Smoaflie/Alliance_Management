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
from scripts.api.api_self import DEBUG_OUT
import ujson
import datetime
import hashlib
import re

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


'''
event handler function
'''
@event_manager.register("url_verification")
def request_url_verify_handler(req_data: UrlVerificationEvent):
    # url verification, just need return challenge
    if req_data.event.token != VERIFICATION_TOKEN:
        raise Exception("VERIFICATION_TOKEN is invalid")
    return jsonify({"challenge": req_data.event.challenge})

@event_manager.register("im.message.receive_v1")
def message_receive_event_handler(req_data: MessageReceiveEvent):
    user_id = req_data.event.sender.sender_id.user_id
    message = req_data.event.message

    process_user_message(user_id, message)    
    return jsonify()

@event_manager.register("application.bot.menu_v6")
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key
    
    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = {
            'type':'template',
            'data':create_messageInteractive(object_id='0')
        }
        message_api_client.send_interactive_with_user_id(user_id, content)
    elif event_key == 'custom_menu.test':
        # TODO:调试用，记得删
        content = {
            'type':'template',
            'data':create_messageInteractive(object_id='1001001')
        }
        content['data']['template_variable']['param1'] = str(content['data']['template_variable']['param1'])
        message_api_client.send_interactive_with_user_id(user_id, content)
        
        # return jsonify()
    return jsonify()

@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    event = req_data.event
    user_id = event.operator.user_id
    value = event.action.value
    toast=None
    data=None

    if value.name == 'object.inspect':
        data = create_messageInteractive(object_id=value.id)
    elif value.name == 'back':
        data = create_messageInteractive(father_id=value.id)
    elif value.name == 'object.apply':
        oid = value.id
        management.apply_item(user_id=user_id, oid=int(oid))

    request_data = {
        'toast':toast if toast else {},
        "card":{
            "type":"template",
            "data": data
        }
    } if data else {}

    return jsonify(request_data)

'''
Flask app function
'''
@app.route("/", methods=["POST"])
def callback_event_handler():    
    # 飞书事件回调
    # DEBUG_OUT(data=request.json)
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
        #TODO： id指向空物品处理  
    else:
        abort(400)

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

    #TODO:应处理特殊字符而非抛出错误
    is_valid(info['name'], errors)
    is_valid(info['do'], errors)
    if not errors:
        sql.insert('logs', info)
    else:
        return jsonify({'result': 'success','error': errors})
        

    msg = ''
    #TODO: info['name'] = name = sql.fetchone('members', 'openid', info['openid'])[1]
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
    pass
    #TODO注释
    # # 获取飞书通讯录列表并自动填入members表中
    # user_ids = contact_api_client.get_scopes(user_id_type='user_id').get('data').get('user_ids')
    # items = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id').get('data').get('items')
    # user_list = list()
    # for item in items:
    #     user_list.append({
    #         'name':item['name'],
    #         'user_id':item['user_id']
    #     })
    # #校验md5值，检测是否有变化
    # list_string = ''.join(map(str, user_list))
    # MD5remote = hashlib.md5()
    # MD5remote.update(list_string.encode('utf-8'))
    # MD5remote = MD5remote.hexdigest()

    # MD5local = sql.fetchone('logs', 'do', 'used to detect changes in the contact.')

    # if MD5local == 'null' or MD5local is None:
    #     sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the contact.'})
    #     MD5local = '0'
    # else:
    #     MD5local = MD5local[1]

    # if MD5local != MD5remote:
    #     management.add_member_batch(user_list)
    #     sql.update('logs',('do','used to detect changes in the contact.'),{'time':MD5remote})
    #     sql.commit()

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

@app.errorhandler
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response

'''
private function
'''
def is_valid(sstr, errors):
    voidc = ["'", '"', '\\', '<', '>', '(', ')', '.', '=']
    for ccc in voidc:
        if ccc in str(sstr):
            errors.append(f'parameters error:\n"{sstr}" is not valid')

def create_messageInteractive(object_id=None, father_id=None):
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
        
def process_user_message(user_id, message):
    reply_text = ""
    reply_map = {
        'invald_type':'Error: 赞不支持此类消息',
        'invalid_object':f'Error: 对象错误 %s',
        'invalid_param':f'Error: 参数非法 %s',
        'invalid_command': f'Error: 请按照格式输入指令',
        'unknown_command': f'Error: 未知命令 %s',
        'id_conflict': f'Error: Id冲突',
        'success': f'Success'
    }
    # TODO:如果修改了函数名，记得更新此处
    command_map = {
        'add': command_add_object,
        'del': command_delete_object,
        'help': command_get_help
    }
    #目前只能识别文字信息
    if message.message_type != 'text':
        reply_text = reply_map['invald_type']
    else:
        text = ujson.loads(message.content).get('text')
        if text[0] != '/':
            #输入的不是指令，不进行操作
            pass
        else:
            # 匹配命令格式 /operatiom param1=xxx param2=xxx ...
            pattern = r'/(\w+)'
            match = re.match(pattern, text)
            if not match:
                reply_text = reply_map['invalid_command']
            else:
                command = match.group(1)
                if command not in command_map:
                    reply_text = reply_map['unknown_command'] % command
                else:
                    reply_text = command_map[command](reply_map, text)

    if reply_text != "":
        content = {
            'text':reply_text
        }
        message_api_client.send_text_with_user_id(user_id,content)
    return jsonify()

def command_add_object(reply_map, text):
    necessary_param_map = {
        'item':['name','father','list_id'],
        'list':['category','father','category_id'],
        'category':['name']
    }
    # 提取object_type [item|list|category]
    pattern = r'/(\w+)\s+(\w+)'
    match = re.match(pattern, text)
    object_type = match.group(2) if match else None
    if object_type not in ('item','list','category'):
        return reply_map['invalid_object'] % f"/add {{object}}应为{{item|list|category}}"
    else:
        # 将结果转换为字典
        pattern = r'((?:\w+=\S+\s*)+)'
        match = re.search(pattern, text)
        print(match)
        if not match:
            required_params = necessary_param_map.get(object_type, [])
            required_params_str = "'{}'".format("' | '".join(required_params))
            return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")
        key_value_pairs = match.group(1)
         #提取键值对
        kv_pattern = r'(\w+)=([^ ]+)'
        pairs = re.findall(kv_pattern, key_value_pairs)
        data = {key: value.strip("'") for key, value in pairs}
        
        params = {
            'name':data.get('name'),
            'father':data.get('father') if data.get('father') else \
                data.get('list_id') if object_type=='list' else \
                (data.get('list_id') if object_type=='category' else None),
            'category_name':data.get('category'),
            'category_id':data.get("category_id"),
            'num':data.get('num')
        }
        _name = data.get('name')
        _father = data.get('father') if data.get('father') else \
                data.get('list_id') if object_type=='list' else \
                (data.get('list_id') if object_type=='category' else None)
        _category_name = data.get('category')
        _category_id = data.get("category_id")
        _num = data.get('num')

        for type,params in necessary_param_map:
            if object_type == type:
                required_params = necessary_param_map.get(object_type, [])
                if not any(params[param] for param in required_params):
                    required_params_str = "'{}'".format("' | '".join(required_params))
                    return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")
        else:
            #TODO:操作执行失败的检测与处理
            if object_type == 'item':
                management.add_item(father=_father,father_name=_name,
                                category_name=_category_name,num=_num,category_id=_category_id)
            elif object_type == 'list':
                management.add_list(father=_father,father_name=_category_name,name=_name)
            elif object_type == 'category':
                management.add_category(name=_name)
            
            return reply_map['success']
            
def command_delete_object(reply_map, text):
    necessary_param_map = {
        'item':['id'],
        'list':['id','name'],
        'category':['id','name']
    }
    # 提取键值对
    pattern = r'/(\w+)\s+(\w+)'
    match = re.match(pattern, text)
    object_type = match.group(2) if match else None
    if object_type not in ('item','list','category'):
        return reply_map['invalid_object'] % f"/del {{object}}应为{{item|list|category}}"
    else:
        # 将结果转换为字典
        pattern = r'((?:\w+=\S+\s*)+)'
        match = re.search(pattern, text)
        if not match:
            required_params = necessary_param_map.get(object_type, [])
            required_params_str = "'{}'".format("' | '".join(required_params))
            return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")
        key_value_pairs = match.group(1)
         #提取键值对
        kv_pattern = r'(\w+)=([^ ]+)'
        pairs = re.findall(kv_pattern, key_value_pairs)
        data = {key: value.strip("'") for key, value in pairs}
        
        params = {
            'name':data.get('name'),
            'id':data.get('id')
        }

        for type,params in necessary_param_map:
            if object_type == type:
                required_params = necessary_param_map.get(object_type, [])
                if not any(params[param] for param in required_params):
                    required_params_str = "'{}'".format("' | '".join(required_params))
                    return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")
        else:
            #TODO:操作执行失败的检测与处理
            if object_type == 'item':
                management.del_item(params=params)
            elif object_type == 'list':
                management.del_list(params=params)
            elif object_type == 'category':
                management.del_category(params=params)
            
            return reply_map['success']

def command_get_help(reply_map, text):
    margin = 10
    return f'''\
    机器人命令指南：
    格式：/command [options] [param1=value] [param2=value] ...
    当前已实现命令commands，标注*号的需要拥有管理权限:
    {'help':<{margin}} \t查看《机器人命令指南》
    {'*add {{item|list|category}} {{params}}':<{margin}} \t往数据库中插入数据,如父项不存在会自动创建
        {'':<{margin}} item\t 具体物品。params:{{'name'|'father'|'list_id'}},['category','category_id','num']),
        {'':<{margin}} list\t 物品列表。params:'name',{{'category'|'father'|'category_id}}),
        {'':<{margin}} category\t 物品类型。params:'name'
    {'*del {{item|list|category}} {{params}}':<{margin}} \t删除数据库中某条数据,如子项中存在数据则无法删除
        {'':<{margin}} item\t 具体物品。params:'id',
        {'':<{margin}} list\t 物品列表。params:{{'name'|'id'}},
        {'':<{margin}} category\t 物品类型。params:{{'name'|'id'}}
    '''
if __name__ == "__main__":
    # 连接mysql服务器
    with open('settings.json', 'r') as f:
        settings = ujson.loads(f.read())
        sql = mysql.MySql(settings['mysql'])
        ITEM_SHEET_TOKEN = settings['sheet']['token']
        management = ApiManagement(sql)
    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
