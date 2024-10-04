#!/usr/bin/env python3.12.3
import os
import logging
import requests
from scripts.api.api_client import MessageApiClient, SpreadsheetApiClient, ContactApiClient, CloudApiClient, ApprovalApiClient
from scripts.api.api_event import MessageReceiveEvent, UrlVerificationEvent, EventManager, BotMenuClickEvent, CardActionEvent, ApprovalInstanceEvent
from flask import Flask, jsonify, request
from dotenv import load_dotenv, find_dotenv
from scripts.api.api_management import ApiManagement
from scripts.api import api_mysql as mysql
from scripts.api.api_self import DEBUG_OUT
import ujson
from datetime import datetime
import re
import time
import copy
from collections import defaultdict
import threading
import hashlib
import asyncio
'''
init
'''
app = Flask(__name__)
def server_init():
    global management,ITEM_SHEET_TOKEN, SHEET_ID_TOTAL, SHEET_ID_ITEM, APPROVAL_CODE,\
          CARD_DISPLAY_JSON, CARD_DISPLAY_REPEAT_ELEMENTS_JSON,BUTTON_CONFIRM_JSON,FORM_JSON
    logging.basicConfig(level=logging.INFO)
    with open('settings.json', 'r') as f:
        settings = ujson.loads(f.read())
        # 连接mysql服务器
        sql = mysql.MySql(settings['mysql'])
        management = ApiManagement(sql)
        ITEM_SHEET_TOKEN = settings.get('sheet').get('token')
        SHEET_ID_TOTAL = settings.get('sheet').get('sheet_id_TOTAL')
        SHEET_ID_ITEM = settings.get('sheet').get('sheet_id_ITEM')

        APPROVAL_CODE = settings.get('approval').get('approval_code')
        
    with open('message_card.json', 'r') as f:
        card_json = ujson.loads(f.read())
        CARD_DISPLAY_JSON = card_json.get('display')
        CARD_DISPLAY_REPEAT_ELEMENTS_JSON = card_json.get('display_repeat_elements')
        BUTTON_CONFIRM_JSON = card_json.get('button_confirm')
        FORM_JSON = card_json.get('form')
server_init()

# 存储请求时间的字典
request_times = defaultdict(list)
# 限制参数
REQUEST_LIMIT = 5  # 限制的请求次数
TIME_WINDOW = 60  # 时间窗口，单位为秒

def restart_app(interval):
    time.sleep(interval)
    management.clean_requests()
    logging.info("delete requests logs.")
        

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

'''
event handler function
'''
#TODO:未验证
def rate_limit(event_type): #限制请求频率
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_id = request.json.get('event').get('operator').get('user_id')
            current_time = time.time()

            # 生成唯一键
            key = f"{user_id}:{event_type}"

            # 清理超出时间窗口的请求
            request_times[key] = [timestamp for timestamp in request_times[key] if current_time - timestamp < TIME_WINDOW]

            # 检查是否超过限制
            if len(request_times[key]) >= REQUEST_LIMIT:
                return jsonify({"error": "请求频率过高"}), 429

            # 添加当前请求时间
            request_times[key].append(current_time)

            return func(*args, **kwargs)
        return wrapper
    return decorator

@event_manager.register("url_verification")
def request_url_verify_handler(req_data: UrlVerificationEvent):
    # url verification, just need return challenge
    if req_data.event.token != VERIFICATION_TOKEN:
        raise Exception("VERIFICATION_TOKEN is invalid")
    return jsonify({"challenge": req_data.event.challenge})

@event_manager.register("im.message.receive_v1")
async def message_receive_event_handler(req_data: MessageReceiveEvent):
    user_id = req_data.event.sender.sender_id.user_id
    message = req_data.event.message
    sender = req_data.event.sender

    asyncio.create_task(handle_user_message(user_id, message, sender))

    return jsonify()

@event_manager.register("application.bot.menu_v6")
@rate_limit("application.bot.menu_v6")    
async def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key

    asyncio.create_task(handle_bot_menu_click(user_id,event_key))
    
    return jsonify()

@event_manager.register("card.action.trigger")
async def card_action_event_handler(req_data: CardActionEvent):
    event = req_data.event
    token = event.token
    user_id = event.operator.user_id
    alife_card_id = management.is_alive_card(user_id)
    current_card_id = event.context.open_message_id
    toast = None
    data = None
    result_queue = asyncio.Queue() #用于在异步任务间安全地传递结果

    if alife_card_id and alife_card_id!=current_card_id:
        message_api_client.recall(current_card_id)
        toast = {
                'type':'error',
                'content':'Error: 该消息卡片已过期，请使用新卡片'
            }
    else:
        asyncio.create_task(card_action_event_task(token, event.action, user_id, result_queue))
        try: #尝试在2秒内做出响应
            toast, data = await asyncio.wait_for(result_queue.get(), timeout=2) 
            #对有toast和data数据的，先响应toast，再处理data
            if isinstance(data,str) and data == 'placeholder':
                data = None
                # 启动一个异步任务来更新卡片
                asyncio.create_task(update_card(token, result_queue))  # 传递result_queue
        except asyncio.TimeoutError:
            # 超时后，启动一个异步任务来更新卡片
            asyncio.create_task(update_card(token, result_queue))  # 传递result_queue
        except Exception as e:
            toast = {'type': 'error', 'content': f'Error: {e}'}
    
    request_data = {
        'toast':toast if toast else {},
        "card":{
            "type":"template",
            "data":data
        } if data else {}
    }
    return jsonify(request_data)

@event_manager.register("approval_instance")
async def approval_instance_event_handler(req_data: ApprovalInstanceEvent):
    event = req_data.event
    
    asyncio.create_task(handle_approval_instance(event))

    return jsonify()

'''
Flask app function
'''
@app.route("/", methods=["POST"])
def callback_event_handler():    
    # 飞书事件回调
    requests = request.json
    DEBUG_OUT(data=requests)
    if requests.get('uuid'):  #回调
        logging.info(f"fetch request,uuid:{requests['uuid']}")
    elif requests: #事件
        event_id = requests.get('header').get('event_id')
        create_time = requests.get('header').get('create_time')
        if management.fetch_request(event_id): #请求已处理，跳过
            logging.info(f"This request has been handled. event_id:{event_id}")
            return jsonify()
        else:
            logging.info(f"fetch request,event_id:{event_id}")
            management.insert_request(event_id,create_time)
    else:
        logging.error(f"request={requests}")

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

        MD5local = management.fetch_contact_md5()

        if MD5local != MD5remote:
            items = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id').get('data').get('items')
            user_list = list()
            for item in items:
                user_list.append({
                    'name':item['name'],
                    'user_id':item['user_id']
                })
            management.add_member_batch(user_list)
            management.update_contact_md5(MD5remote)
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
        latest_modify_time_local = management.fetch_itemSheet_md5()

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
            itemSheet_md5 = hashlib.md5().update(latest_modify_time_remote.encode('utf-8'))
            management.update_itemSheet_md5(itemSheet_md5)
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
handle function
'''
def handle_bot_menu_click(user_id, event_key):
    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = create_messageInteractive(object_id='0')
        update_messageInteractive(user_id, content)
    elif event_key == 'custom_menu.test':
        # content = create_messageInteractive(object_id='0')
        # update_messageInteractive(user_id, content)
        pass

def handle_approval_instance(event):
    instance = approval_api_event.fetch_instance(event.instance_code)
    status = event.status
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
                logging.info(f"审批：{operator_user_id}拒绝对{params['oid']}的申请")
            elif status == 'APPROVED':
                management.set_item_state(oid=params['oid'],operater_user_id=operator_user_id,operation='MODIFY',\
                                        useable=0,wis=applicant_name,do=params['do'])
                logging.info(f"审批：{operator_user_id}同意对{params['oid']}的申请")

def handle_user_message(user_id, message, sender):
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


'''
private function
'''
def get_display_width(s):
    """计算字符串的显示宽度，中文字符占2个单位，英文字符、数字和全角空格占1个单位"""
    full_width = 0
    half_width = 0
    for char in s:
        if ord(char) > 255 or char == '\u3000':  # 中文字符and全角空格
            full_width += 1
        else:  # 英文字符和数字
            half_width += 1
    return full_width, half_width

def format_with_margin(s, margin, assign_full_width_num=None):
    """根据给定的宽度格式化字符串"""
    s = str(s)
    full_width, half_width = get_display_width(s)
    if full_width*2+half_width >= margin:
        return s  # 如果字符串已经超过了margin，返回原字符串
    
    if not assign_full_width_num:
        full_width_num = 0
        half_width_num = margin - (full_width*2+half_width)
    else:
        full_width_num = assign_full_width_num - full_width if assign_full_width_num>full_width else 0
        half_width_num = margin-((full_width_num+full_width)*2+half_width) if margin>(full_width_num+full_width)*2+half_width else 0
    # 使用全角空格+半角空格填充
    return s + '\u3000' * full_width_num + " " * half_width_num

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
            logging.info(f"撤回与 {user_id} 的消息卡片{alive_card_id}")
            management.update_card(user_id)
            message_api_client.recall(alive_card_id)

        result = message_api_client.send_interactive_with_user_id(user_id, content)
        message_id = result.get('data').get('message_id')
        create_time = result.get('data').get('create_time')
        logging.info(f"向 {user_id} 发送新消息卡片{message_id}")
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

async def card_action_event_task(token,action,user_id,result_queue):
    data = 'placeholder'
    if action.tag == 'button':
        value = action.value
        if value.name == 'home':
            data = create_messageInteractive(object_id='0')
        elif value.name == 'self':
            data = create_messageInteractive(object_id='-1', user_id=user_id)
        elif value.name == 'object.inspect':
            data = create_messageInteractive(object_id=value.id)
        elif value.name == 'back':
            data = create_messageInteractive(object_id=int(value.id)/1000)
        elif value.name == 'object.apply':
            oid = value.id
            if management.apply_item(user_id=user_id, oid=int(oid)) == 'success':
                toast = {
                    'type':'success',
                    'content':'success: 已发送申请'
                }
                await result_queue.put((toast, data)) #对有toast的数据先行返回
                
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
                logging.info(f"发送审批,{user_id} 申请 {oid}")
                data = create_messageInteractive(object_id=int(oid)/1000)
            else:
                toast = {
                    'type':'error',
                    'content':'Error: 物品不可用'
                }
                data = None
        elif value.name == 'object.return':
            toast = {
                'type':'success',
                'content':'success: 已归还'
            }
            management.return_item(user_id,value.object_param_1)
            await result_queue.put((toast, data)) #对有toast的数据先行返回
            data = create_messageInteractive(object_id=-1, user_id=user_id)
    elif action.tag == 'input':
        input_value = action.input_value
        if action.name == "input.search":
            data = create_messageInteractive(object_id=-2, target=input_value)
        
    await result_queue.put((toast, data))

async def update_card(token, result_queue):
    # 等待获取结果
    toast, data = await result_queue.get()
    if data:
        logging.info(f"更新卡片token:{token}")
        await message_api_client.update_interactive(token, data)

def can_convert_to_int(a):
    try:
        int(a)
        return True
    except (ValueError, TypeError):
        return False

def create_messageInteractive(object_id=None, user_id=None, target=None):
    title_map = {
        '0':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_info', 'title':"个人仓库", 'param1':'ID', 'param2':'名称', 'param3':'备注'},
        '1':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_category', 'title':"物资类型", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '2':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_list', 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '3':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_info', 'title':"物资仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态'},
        '4':{'CARD_JSON':CARD_DISPLAY_JSON, 'table':'item_list', 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
    }
    action_map = {
        '0':{'name':'归还','action':'object.return'},
        '3':{'name':'申请','action':'object.apply'},
        '4':{'name':'申请','action':'object.apply'},
    }
    if object_id:
        object_id = int(object_id)
        _father_id = str(object_id)
        title_id = '4' if object_id==-2 else \
            ('0' if object_id==-1 else \
            ('1' if object_id==0 else \
             ('2' if object_id < 1000 else \
              ('3' ) ) ) )
        _id = object_id
    else:
        raise Exception("参数错误")
    try:
        if title_id == '0': #个人页
            _list = management.get_member_items(user_id)
            object_list =[{'param1': id_, 'param2': name_, 'param3': do_, 'do': do_} 
                        for id_, name_, do_ in zip(_list['oid'], _list['name'], _list['do'])] if _list else None
        elif title_id == '1': #仓库（所有物品类型）
            _list = management.get_category()
            object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_)} 
                        for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
        elif title_id == '2': #仓库（某类型的所有物品名）
            _list = management.get_list(category_id=_id)
            object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_)} 
                        for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
        elif title_id == '3': #仓库（某名字的所有物品信息）
            _list = management.get_items(name_id=_id)
            object_list =[{'param1': id_, 'param2': name_, 'param3': useable_, 'do': do_} 
                        for id_, name_, useable_, do_ in zip(_list['id'], _list['name'], _list['useable'], _list['do'])] if _list else None
        elif title_id == '4': #仓库(搜索页)
            display_target = 'list' #默认以列表方式呈现
            if can_convert_to_int(target) and int(target)>0: #id
                if int(target)>1000000:  #oid
                    _list = management.get_item(oid=target)
                    display_target = 'object' #仅对搜索具体oid的操作以对象方式呈现
                elif int(target)>1000: #name_id
                    _list = management.get_items(name_id=target)
                else: #category_id
                    _list = management.get_list(category_id=target)
            else: #名称
                _list = management.get_items(name=target)
            
            if display_target == 'list':
                object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_)} 
                        for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
            else:
                object_list =[{'param1': id_, 'param2': name_, 'param3': useable_, 'do': do_} 
                        for id_, name_, useable_, do_ in zip(_list['id'], _list['name'], _list['useable'], _list['do'])] if _list else None
        
        values = {
            'title': title_map[title_id]['title'],
            'father_id':str(_father_id)
        }
        title_text = (
            f"       "
            f"<font color=blue>{format_with_margin(title_map[title_id]['param1'],10)}</font>  "
            f"<font color=red>{format_with_margin(title_map[title_id]['param3'],10)}</font>  "
            f"<font color=green>{format_with_margin(title_map[title_id]['param2'],19,6)}</font>"
        )
        values['title_text']=title_text

        json_data = copy.deepcopy(title_map[title_id]['CARD_JSON'])
        #标题和列名
        result_data = replace_placeholders(json_data, values)
        #循环容器-勾选器
        if object_list:
            for obj in object_list:
                checker_text = (
                    f"<font color=blue>{format_with_margin(obj['param1'],10)}</font>  "
                    f"<font color=red>{format_with_margin(obj['param3'],10)}</font>  "
                    f"<font color=green>{format_with_margin(obj['param2'],20,6)}</font>"
                )
                obj['checker_text'] = checker_text
                repeat_elements = copy.deepcopy(CARD_DISPLAY_REPEAT_ELEMENTS_JSON)
                
                #对(申请/归还)操作
                if title_id in ('3','0'):
                    #添加二次确认弹窗+修改按键动作值
                    confirm_data = copy.deepcopy(BUTTON_CONFIRM_JSON)
                    action_name = action_map[title_id].get('name')
                    action = action_map[title_id].get('action')
                    confirm_data['text']['content'] = confirm_data['text']['content'].replace(f"${{action}}", action_name)
                    confirm_data = replace_placeholders(confirm_data,obj)
                    repeat_elements['button_area']['buttons'][0]['confirm']=confirm_data
                    repeat_elements['button_area']['buttons'][0]['value']['name']=action

                result_data['elements'].append(replace_placeholders(repeat_elements, obj))
            #表单容器
            result_data['elements'].append(FORM_JSON)
        else:
            # result_data['elements'].append({
            #     #TEXT:未找到对应物品
            # })
            pass
        return result_data
    except Exception as e:
        logging.error(f"Error while create card: {e}")

'''
user commands
'''
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

if __name__ == "__main__":
    interval = 10800  # 每3小时重启一次
    threading.Thread(target=restart_app,args=(interval,)) 

    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
