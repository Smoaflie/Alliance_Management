#!/usr/bin/env python3.12.3
import os
import logging
import requests
from scripts.api.api_client import LarkException, MessageApiClient, SpreadsheetApiClient, ContactApiClient, CloudApiClient, ApprovalApiClient
from scripts.api.api_event import MessageReceiveEvent, UrlVerificationEvent, EventManager, BotMenuClickEvent, CardActionEvent, ApprovalInstanceEvent
from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv, find_dotenv
from scripts.api.api_management import ApiManagement
from scripts.api import api_mysql as mysql
from scripts.api.api_self import DEBUG_OUT
import ujson
from datetime import datetime
import hashlib
import re
import time
import copy
import threading
import sys

app = Flask(__name__)
processed_tokens = set()  # 用于存储已处理的 token

# load env parameters form file named .env
load_dotenv(find_dotenv())
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
approval_api_event = ApprovalApiClient(APP_ID, APP_SECRET, LARK_HOST)
event_manager = EventManager()

def server_init():
    global sql,management,ITEM_SHEET_TOKEN, SHEET_ID_TOTAL, SHEET_ID_ITEM, APPROVAL_CODE,\
          CARD_INFO_JSON, CARD_DISPLAY_JSON, CARD_DISPLAY_REPEAT_ELEMENTS_JSON
    logging.basicConfig(level=logging.INFO)
    with open('settings.json', 'r') as f:
        settings = ujson.loads(f.read())
        # 连接mysql服务器
        sql = mysql.MySql(settings['mysql'])
        ITEM_SHEET_TOKEN = settings.get('sheet').get('token')
        SHEET_ID_TOTAL = settings.get('sheet').get('sheet_id_TOTAL')
        SHEET_ID_ITEM = settings.get('sheet').get('sheet_id_ITEM')

        management = ApiManagement(sql)
        APPROVAL_CODE = settings.get('approval').get('approval_code')

    with open('message_card.json', 'r') as f:
        card_json = ujson.loads(f.read())
        CARD_DISPLAY_JSON = card_json.get('display')
        CARD_DISPLAY_REPEAT_ELEMENTS_JSON = card_json.get('display_repeat_elements')
        CARD_INFO_JSON = card_json.get('info')
server_init()

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
    sender = req_data.event.sender

    process_user_message(user_id, message, sender)    
    return jsonify()

@event_manager.register("application.bot.menu_v6")
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key
    
    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = create_messageInteractive(object_id='0')
        update_messageInteractive(user_id, content)
    elif event_key == 'custom_menu.test':
        content = create_messageInteractive(object_id='2005')
        update_messageInteractive(user_id, content)
        DEBUG_OUT(data=content)
        pass
    return jsonify()

@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    event = req_data.event
    token = event.token
    user_id = event.operator.user_id
    value = event.action.value
    alife_card_id = management.is_alive_card(user_id)
    current_card_id = event.context.open_message_id
    toast = None
    if alife_card_id and alife_card_id!=current_card_id:
        message_api_client.recall(current_card_id)
        toast = {
                'type':'error',
                'content':'Error: 该消息卡片已过期，请使用新卡片'
            }
    else:
        if value.name == 'object.inspect':
            if value.id == '0':#归还
                toast = {
                    'type':'success',
                    'content':'success: 已归还'
                }
        elif value.name == 'object.apply':
            oid = value.id
            if management.apply_item(user_id=user_id, oid=int(oid)) == 'success':
                toast = {
                    'type':'success',
                    'content':'success: 已发送申请'
                }
            else:
                toast = {
                    'type':'error',
                    'content':'Error: 物品不可用'
                }

        thread = threading.Thread(target=card_action_event_task,args=(token,event,user_id,value))
        thread.start()

    request_data = {
        'toast':toast if toast else {},
        "card":{
            "type":"template"
        }
    } 
    return jsonify(request_data)

@event_manager.register("approval_instance")
def approval_instance_event_handler(req_data: ApprovalInstanceEvent):
    instance = approval_api_event.fetch_instance(req_data.event.instance_code)
    status = req_data.event.status
    applicant_user_id = instance.get('data').get('timeline')[0].get('user_id')
    #TODO:同意和拒绝的结构不一样，现在写的是不好的解决办法
    operator_user_id = instance.get('data').get('timeline')[-1].get('user_id') if \
                instance.get('data').get('timeline')[-1].get('user_id') else instance.get('data').get('timeline')[-2].get('user_id')
    if instance.get('data').get('approval_name') == "物品领用":
        if status in ('APPROVED', 'REJECTED','CANCELED','DELETED'): 
            form = ujson.loads(instance.get('data').get('form'))
            params = {}
            #从便于移植的角度看，这里应该使用遍历，但控件中有个fieldList……
            params['do'] = form[0].get('value')
            params['time'] = form[1].get('value')
            params['name'] = form[2].get('value')[0][0].get('value')
            params['num'] = form[2].get('value')[0][1].get('value')
            params['oid'] = form[2].get('value')[0][2].get('value')
            applicant_name = management.get_member(applicant_user_id).get('name')
            if status in ('REJECTED','CANCELED','DELETED'): 
                management.set_item_state(oid=params['oid'],operater_user_id=operator_user_id,operation='MODIFY',\
                                        useable=1,wis=applicant_name,do=params['do'])
            elif status == 'APPROVED':
                management.set_item_state(oid=params['oid'],operater_user_id=operator_user_id,operation='MODIFY',\
                                        useable=0,wis=applicant_name,do=params['do'])
    result = 'success'
    
    return jsonify()

'''
Flask app function
'''
@app.route("/", methods=["POST"])
def callback_event_handler():    
    # 飞书事件回调
    token = request.json.get('header').get('token')
    if token in processed_tokens: #请求已处理，跳过
        logging.info("This request has been handled.")
        return jsonify()
    
    DEBUG_OUT(data=request.json)
    event_handler, event = event_manager.get_handler_with_event(VERIFICATION_TOKEN, ENCRYPT_KEY)
    
    return event_handler(event)

@app.before_first_request
def searchContactToAddMembers():    # 获取飞书通讯录列表并自动填入members表中
    try:
        user_ids = contact_api_client.get_scopes(user_id_type='user_id').get('data').get('user_ids')
        #校验md5值，检测是否有变化
        list_string = ''.join(map(str, user_ids))
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
            items = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id').get('data').get('items')
            user_list = list()
            for item in items:
                user_list.append({
                    'name':item['name'],
                    'user_id':item['user_id']
                })
            management.add_member_batch(user_list)
            sql.update('logs',('do','used to detect changes in the contact.'),{'time':MD5remote})
            sql.commit()
            logging.info("add members from contact.")
        else:
            logging.info("skip add members from contact.")
    except Exception as e:
        raise Exception(f"尝试通过通讯录初始化用户列表失败，请重试\n{e}")

@app.before_first_request
def getItemsBySheets(): #从电子表格中获取物品信息
    #校验修改时间，检测是否有变化
    #TODO:HERE ERROR
    try:
        DocMetadata = cloud_api_client.getDocMetadata([ITEM_SHEET_TOKEN], ['sheet']).get('data').get('metas')        
        if not DocMetadata:
            raise Exception(f"ITEM_SHEET_TOKEN:{ITEM_SHEET_TOKEN} 无法找到")
        
        latest_modify_time_remote = DocMetadata[0].get('latest_modify_time') #取[0]是因为使用token只会搜到一个文件
        latest_modify_time_local = sql.fetchone('logs', 'do', 'used to detect changes in the spreadsheet.')
        if latest_modify_time_local == 'null' or latest_modify_time_local is None:
            sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the spreadsheet.'})
            latest_modify_time_local = '0'
        else: 
            latest_modify_time_local = latest_modify_time_local[1]
        #如果物资表修改过（数据库数据过时），重新初始化物资数据库
        if latest_modify_time_local != latest_modify_time_remote:
            sheet_date =  spreadsheet_api_client.readRange(ITEM_SHEET_TOKEN, f"{SHEET_ID_TOTAL}!A2:D")
            if not sheet_date.get('data'):
                raise Exception(f"SHEET_ID_TOTAL:{SHEET_ID_TOTAL} 无法找到")
            
            item_list = sheet_date.get('data').get('valueRange').get('values')
            logging.info('add item by sheet')
            for item in item_list:
                category_name = item[0]
                item_name = item[1]
                item_num_total = item[2] if item[2] else 1
                item_num_broken = item[3] if item[3] else 0
                management.add_items_until_limit(name=item_name, category_name=category_name, num=item_num_total, num_broken=item_num_broken)
            sql.update('logs',('do','used to detect changes in the spreadsheet.'),{'time':latest_modify_time_remote})
            sql.commit()
        else:
            logging.info('skip add item by sheet')
    except Exception as e:
        raise Exception(f"{e}\n如需通过电子表格初始化数据库，请创建一个电子表格，按格式填入值后，确认`settings.json`中['sheet']:['token']和['sheet_id_TOTAL']是否正确。否则注释掉getItemsBySheets()")

@app.before_first_request
def subApprovalEvent(): #订阅审批事件
    #只能订阅一次，因此第一次初始化后会一直弹subscription existed异常（已捕获）
    #确认订阅成功后，你完全可以注释掉它
    try:
        approval_api_event.subscribe(APPROVAL_CODE)
    except:
        logging.info("subApprovalEvent() 只能订阅一次，因此你完全可以注释掉它")

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

def update_messageInteractive(user_id, content):
    # 如果之前有过消息卡片，先撤回再发送新卡片
    try:
        alive_card_id = management.is_alive_card(user_id)
        if alive_card_id:
            message_api_client.recall(alive_card_id)
            result = message_api_client.send_interactive_with_user_id(user_id, content)

            message_id = result.get('data').get('message_id')
            create_time = result.get('data').get('create_time')
            management.update_card(user_id,message_id,create_time)
    except Exception as e:
        logging.error(f"{e}")

def replace_placeholders(data, values):
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = replace_placeholders(value, values)
    elif isinstance(data, list):
        for index in range(len(data)):
            data[index] = replace_placeholders(data[index], values)
    elif isinstance(data, str):
        for key, value in values.items():
            data = data.replace(f"${{{key}}}", str(value))
    return data

def card_action_event_task(token,event,user_id,value):
    data = None
    if value.name == 'home':
        data = create_messageInteractive(object_id='0')
    elif value.name == 'self':
        data = create_messageInteractive(object_id='-1', user_id=user_id)
    elif value.name == 'object.inspect':
        if value.id == '0':#归还
            management.return_item(user_id,value.object_param_1)
        else:#查看
            data = create_messageInteractive(object_id=value.id)
    elif value.name == 'back':
        data = create_messageInteractive(father_id=value.id)
    elif value.name == 'object.apply':
        oid = value.id
        if management.apply_item(user_id=user_id, oid=int(oid)) == 'success':
            item_info = management.get_item(oid)
            form=[
                {'id':'do','type':'textarea','value':'申请'},
                {'id':'date','type':'date',"value": f"{datetime.fromtimestamp(time.time()).strftime("%Y-%m-%dT%H:%M:%S+08:00")}"},
                {'id':'form','type':'fieldList', 'value':[[ 
                    {'id':'name','type':'input','value':f'{item_info['name']}'},
                    {'id':'num','type':'number','value':'1'},
                    {'id':'oid','type':'number','value':oid}
                ]]},
            ]

            approval_api_event.create(approval_code=APPROVAL_CODE, user_id=user_id,\
                                    form=ujson.dumps(form))
        else:
            pass
        data = create_messageInteractive(object_id=oid)
    message_api_client.update_interactive(token,data)

def create_messageInteractive(object_id=None, father_id=None, user_id=None):
    title_map = {
        '1':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_category', 'title':"物资类型", 'param1':'ID', 'param2':'名称', 'param3':'数量', 'param4':"查看"},
        '2':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_list', 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量', 'param4':"查看"},
        '3':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_info', 'title':"物资仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态', 'param4':"查看"},
        '4':{'CARD_JSON':CARD_INFO_JSON, 'table':'item_info', 'title':"", 'param1':'', 'param2':'', 'param3':'', 'param4':""},
        '0':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_info', 'title':"个人仓库", 'param1':'ID', 'param2':'名称', 'param3':'备注', 'param4':"归还"},
    }
    if object_id:
        object_id = int(object_id)
        _father_id = str(object_id)
        title_id = '0' if object_id=='-1' else ('1' if object_id==0 else ('2' if object_id < 1000 else ('3' if object_id < 1000000 else '4') ) )
        _id = object_id
    elif father_id:
        father_id = int(father_id)
        _father_id = str(int(father_id/1000))
        title_id = '1' if father_id<1000 else ('2' if father_id < 1000000 else '3')
        _id = _father_id
    else:
        raise Exception("参数错误")
    
    if title_id == '0':
        _list = management.get_member_items(user_id)
        object_list =[{'param1': id_, 'param2': name_, 'param3': do_, 'id':'0'} 
                    for id_, name_, do_ in zip(_list['oid'], _list['name'], _list['do'])] if _list else None
    elif title_id == '1':
        _list = management.get_category()
        object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_), 'id':str(id_)} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
    elif title_id == '2':
        _list = management.get_list(father=_id)
        object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_), 'id':str(id_)} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
    elif title_id == '3':
        _list = management.get_items(father=_id)
        object_list =[{'param1': id_, 'param2': name_, 'param3': useable_, 'id':str(id_)} 
                    for id_, name_, useable_ in zip(_list['id'], _list['name'], _list['useable'])] if _list else None
    elif title_id == '4':
        object_list = []
        _item = management.get_item(oid=_id)
        title_map[title_id]['title'] = f"您正在查看 {_item['name']} 详细信息"
        title_map[title_id]['param1'] = str(_item['id'])
        title_map[title_id]['param2'] = _item['useable']
        title_map[title_id]['param3'] = _item['wis']
        title_map[title_id]['param4'] = _item['do']

    values = {
        'title': title_map[title_id]['title'],
        'title_id': title_id,
        'param1': title_map[title_id]['param1'],
        'param2': title_map[title_id]['param2'],
        'param3': title_map[title_id]['param3'],
        'param4': title_map[title_id]['param4'],
        'father_id':str(_father_id),
    }
    json_data = copy.deepcopy(title_map[title_id]['CARD_JSON'])
    result_data = replace_placeholders(json_data, values)

    if object_list:
        for obj in object_list:
            repeat_elements = copy.deepcopy(CARD_DISPLAY_REPEAT_ELEMENTS_JSON)
            result_data['elements'].append(replace_placeholders(repeat_elements, obj))
    return result_data

def process_user_message(user_id, message, sender):
    reply_text = ""
    reply_map = {
        'invald_type':'Error: 赞不支持此类消息',
        'invalid_object':f'Error: 对象错误 %s',
        'invalid_param':f'Error: 参数非法 %s',
        'invalid_command': f'Error: 请按照格式输入指令',
        'unknown_command': f'Error: 未知命令 %s',
        'id_conflict': f'Error: Id冲突',
        'success': f'Success',
        'permission_denied': f'Error: 权限不足',
    }
    # TODO:如果修改了函数名，记得更新此处
    command_map = {
        'add':      {'command':command_add_object,      'needed_root':True},
        'del':      {'command':command_delete_object,   'needed_root':True},
        'help':     {'command':command_get_help,        'needed_root':False},
        'op':       {'command':command_add_op,          'needed_root':True},
        'deop':     {'command':command_delete_op,       'needed_root':True},
        'lsop':     {'command':command_list_op,         'needed_root':False},
        'search':   {'command':command_search_id,       'needed_root':False},
        'return':   {'command':command_return_item,     'needed_root':False},
        'save':     {'command':command_save,            'needed_root':True},
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
            # 匹配命令格式 /operatiom [object] param1=xxx param2=xxx ...
            pattern = r'/(\w+)'
            match = re.match(pattern, text)
            if not match:
                reply_text = reply_map['invalid_command']
            else:
                command = match.group(1)
                if command not in command_map:
                    reply_text = reply_map['unknown_command'] % command
                else:
                    params = None
                    #获取操作[对象]
                    pattern = r'/(\w+)\s+(\S+)'
                    match = re.match(pattern, text)
                    #TODO:是否应该用其他名字表示object？
                    object = match.group(2) if match else None
                    #获取操作[参数]
                    pattern = r'((?:\w+=\S+\s*)+)'
                    match = re.search(pattern, text)
                    if not match:
                        params = None
                    else:
                        key_value_pairs = match.group(1)
                        kv_pattern = r'(\w+)=([^ ]+)'
                        pairs = re.findall(kv_pattern, key_value_pairs)
                        params = {key: value.strip("'") for key, value in pairs}
                    #进行相应操作
                    if (not command_map[command]['needed_root']) or \
                        (command_map[command]['needed_root'] and management.is_user_root(user_id)):
                        reply_text = command_map[command]['command'](reply_map, message, sender, object, params)
                    else:
                        reply_text = reply_map['permission_denied']
    if reply_text not in ('', None) :
        content = {
            'text':reply_text
        }
        message_api_client.send_text_with_user_id(user_id,content)
    return jsonify()

def command_add_object(reply_map, message, sender, object, params):
    necessary_param_map = {
        'item':['name','name_id'],
        'list':['name','category_id','category_name'],
        'category':['category_name',]
    }
    # 提取object [item|list|category]

    if object not in ('item','list','category'):
        return reply_map['invalid_object'] % f"/add {{object}}应为{{item|list|category}}"
    else:
        required_params = necessary_param_map.get(object, [])
        if not params or not any(param in params for param in required_params):
            required_params_str = "'{}'".format("' | '".join(required_params))
            return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")

        else:
            try:
                #TODO:操作执行失败的检测与处理
                if object == 'item':
                    management.add_item(params=params)
                elif object == 'list':
                    management.add_list(params=params)
                elif object == 'category':
                    management.add_category(params=params)
                #TODO决策：自动刷新消息卡片?
                return reply_map['success']
            except Exception as e:
                return f"{e}"
          
def command_delete_object(reply_map, message, sender, object, params):
    necessary_param_map = {
        'item':['id',],
        'list':['id','name'],
        'category':['id','name']
    }
    # 提取键值对
    if object not in ('item','list','category'):
        return reply_map['invalid_object'] % f"/del {{object}}应为{{item|list|category}}"
    else:
        required_params = necessary_param_map.get(object, [])
        if not params or not any(param in params for param in required_params):
            required_params_str = "'{}'".format("' | '".join(required_params))
            return reply_map['invalid_param'] % (f"{{{required_params_str}}}是必需的")

        else:
            try:
                #TODO:操作执行失败的检测与处理
                if object == 'item':
                    management.del_item(params=params)
                elif object == 'list':
                    management.del_list(params=params)
                elif object == 'category':
                    management.del_category(params=params)
            
                return reply_map['success']
            except Exception as e:
                return f"{e}"

def command_add_op(reply_map, message, sender, object, params):
    user_id = None
    if message.mentions:
        for mention in message.mentions:
            if mention.key == object:
                user_id = mention.id.user_id
                break
    
    if not management.get_member(user_id) if user_id else None:
        return reply_map['invalid_object'] % f'无法识别的用户{object}'

    management.set_member_root(user_id)
    return reply_map['success']

def command_delete_op(reply_map, message, sender, object, params):
    user_id = None
    if message.mentions:
        for mention in message.mentions:
            if mention.key == object:
                user_id = mention.id.user_id
                break
    
    if not management.get_member(user_id) if user_id else None:
        return reply_map['invalid_object'] % f'无法识别的用户{object}'
    
    #TODO：id不在表中如何解决？
    management.set_member_unroot(user_id)
    return reply_map['success']

def command_list_op(reply_map, message, sender, object, params):
    result = management.get_members_root()
    return ujson.dumps(result, ensure_ascii=False) if result else '当前暂无管理员'

def command_search_id(reply_map, message, sender, object, params):
    try:
        id = int(object)
    except:
        return reply_map['invalid_object'] % f"/search {{id}}<-int不存在"
    
    try:
        user_id = sender.sender_id.user_id
        content = {
                'type':'template',
                'data':create_messageInteractive(object_id=object)
            }
        update_messageInteractive(user_id, content)
    
        return None
    except Exception as e:
        return f"{e}"

def command_return_item(reply_map, message, sender, object, params):
    try:
        oid = int(object)
    except:
        return reply_map['invalid_object'] % f"/return {{id}}<-int不存在"
    
    user_id = sender.sender_id.user_id
    result = management.return_item(user_id,oid)

    return result

def command_save(reply_map, message, sender, object, params):
    try:
        sheets = spreadsheet_api_client.fetchSheet(ITEM_SHEET_TOKEN).get('data').get('sheets')
        item_sheet = next((sheet for sheet in sheets if sheet.get('sheet_id') == SHEET_ID_TOTAL), None)
        start_line = end_line= 2
        category = management.get_category()
        for category_id,category_name in zip(category['id'],category['name']):
            items_list = management.get_list(category_id)
            values = []
            for name,name_id in zip(items_list['name'],items_list['id']):
                items_info = management.get_items(name_id, name)
                if not items_info:
                    continue
                end_line += len(items_info['id'])
                for oid,useable,wis,do in zip(items_info['id'],items_info['useable'],\
                                                items_info['wis'],items_info['do']):
                    value =[]
                    value.append(oid)
                    value.append(name)
                    value.append(category_name)
                    value.append(useable)
                    value.append(wis)
                    value.append(do)
                    values.append(value)
            spreadsheet_api_client.modifySheet(ITEM_SHEET_TOKEN,SHEET_ID_ITEM,f"A{start_line}:F{end_line-1}",values)
            logging.info(f"已保存 {category_name} 类型的信息到电子表格中，行数{start_line}:{end_line-1}")
            start_line = end_line
        return reply_map['success']
    except Exception as e:
        return f"失败 {e}"

def command_get_help(reply_map, message, sender, object, params):
    margin = 10
    return f'''\
    机器人命令指南：
    格式：/command [options] [param1=value] [param2=value] ...
    当前已实现命令commands，标注*号的需要拥有管理权限:
    {'help':<{margin}} \t查看《机器人命令指南》
    {'*add {{item|list|category}} {{params}}':<{margin}} \t往数据库中插入数据,如父项不存在会自动创建
        {'':<{margin}} item\t 具体物品。params:{{'name'|'name_id'}},['category_name','category_id','num']),
        {'':<{margin}} list\t 物品列表。params:'name',{{'category_name'|'category_id}}),
        {'':<{margin}} category\t 物品类型。params:'category_name'
    {'*del {{item|list|category}} {{params}}':<{margin}} \t删除数据库中某条数据,如子项中存在数据则无法删除
        {'':<{margin}} item\t 具体物品。params:'id',
        {'':<{margin}} list\t 物品列表。params:{{'name'|'id'}},
        {'':<{margin}} category\t 物品类型。params:{{'name'|'id'}}
    {'op {{@user_name}}':<{margin}} \t给予管理员权限
    {'deop {{@user_name}}':<{margin}} \t取消管理员权限
    {'lsop {{@user_name}}':<{margin}} \t列出管理员列表
    {'search {{id}}':<{margin}} \t搜索id对应的项
    {'return {{id}}':<{margin}} \t归还id对应的物品,只能还自己的，管理员可以帮忙归还
    {'save':<{margin}} \t(仅管理员)同步物资情况到指定的电子表格
    '''

def restart_app(interval):
    time.sleep(interval)
    logging.info("restart")
    os.execv(sys.executable, ['python3'] + sys.argv)  # 重启应用
        
if __name__ == "__main__":
    interval = 10800  # 每3小时重启一次
    threading.Thread(target=restart_app, args=(interval,), daemon=True).start()

    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
