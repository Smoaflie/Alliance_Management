#!/usr/bin/env python3.12.3
import os
import logging
import requests
from scripts.api.api_client import MessageApiClient, SpreadsheetApiClient, ContactApiClient, CloudApiClient, ApprovalApiClient
from scripts.api.api_event import MessageReceiveEvent, UrlVerificationEvent, EventManager, BotMenuClickEvent, CardActionEvent, ApprovalInstanceEvent
from flask import Flask, jsonify, request
from dotenv import load_dotenv, find_dotenv
from scripts.api.api_management import ApiManagement
from scripts.api import mysql_connector as mysql
from scripts.api.api_self import DEBUG_OUT,format_with_margin,can_convert_to_int,replace_placeholders
import ujson
from datetime import datetime
import re
import time
import copy
import threading
import hashlib
from functools import wraps
from celery import Celery
import redis

'''
init
'''
app = Flask(__name__)
def server_init():
    global management,ITEM_SHEET_TOKEN, SHEET_ID_TOTAL, SHEET_ID_ITEM, APPROVAL_CODE,\
          CARD_DISPLAY_JSON, CARD_DISPLAY_REPEAT_ELEMENTS_JSON,BUTTON_CONFIRM_JSON,\
        FORM_JSON,REDIS_HOST,REDIS_PORT,REDIS_DB
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
        REDIS_HOST = settings.get('redis').get('host')
        REDIS_PORT = settings.get('redis').get('port')
        REDIS_DB = settings.get('redis').get('db')
        
    with open('message_card.json', 'r') as f:
        card_json = ujson.loads(f.read())
        CARD_DISPLAY_JSON = card_json.get('display')
        CARD_DISPLAY_REPEAT_ELEMENTS_JSON = card_json.get('display_repeat_elements')
        BUTTON_CONFIRM_JSON = card_json.get('button_confirm')
        FORM_JSON = card_json.get('form')
server_init()
# 配置 Redis
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
# 限制请求频率
REQUEST_LIMIT = 1  # 限制的请求次数
TIME_WINDOW = 3  # 时间窗口，单位为秒
# 配置 Celery
app.config['CELERY_BROKER_URL'] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
app.config['CELERY_RESULT_BACKEND'] = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)
        

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
wraps
'''
def celery_task(func): #与celery.task装饰器配合,使函数被调用时始终作为后台任务
    # 使用 Celery 的 task 装饰器来装饰函数
    task = celery.task(func)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return task.apply_async(args=args, kwargs=kwargs)
    return wrapper

def rate_limit(event_type): #限制请求频率
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_id = request.json.get('event').get('operator').get('user_id')
            current_time = time.time()

            # 生成唯一键
            key = f"{user_id}:{event_type}"

            # 获取当前请求次数
            request_count = r.zcard(key)

            # 检查是否超过限制
            if request_count >= REQUEST_LIMIT:
                return jsonify({"error": "请求频率过高"}), 403

            # 添加当前请求时间
            r.zadd(key, {current_time: current_time})

            # 设置过期时间，确保在时间窗口结束后自动删除键
            r.expire(key, TIME_WINDOW)

            return func(*args, **kwargs)
        return wrapper
    return decorator

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
    message = req_data.event.message.__dict__
    sender = req_data.event.sender.__dict__

    create_messageResponse(user_id=user_id,message=message,sender=sender)

    return jsonify()

@event_manager.register("application.bot.menu_v6")
@rate_limit("application.bot.menu_v6")    
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key

    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = create_messageInteractive(object_id='0')
        update_messageInteractive(user_id, content)
    elif event_key == 'custom_menu.test':
        # DocMetadata = cloud_api_client.getDocMetadata([ITEM_SHEET_TOKEN], ['sheet']).get('data').get('metas')        
        # DEBUG_OUT(DocMetadata)
        # content = create_messageInteractive(object_id='0')
        # update_messageInteractive(user_id, content)
        pass
    
    return jsonify()

@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    event = req_data.event
    token = event.token
    user_id = event.operator.user_id
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
        if event.action.tag == 'button':
            value = event.action.value
            selectedObjectList=value.selectedObjectList.__dict__
            #将表单按钮与其余按钮进行区分
            if hasattr(event.action,"name") and event.action.name == "form_button":
                #判断是否选中物品
                if not selectedObjectList['oid']:
                    toast = {
                            'type':'error',
                            'content':f'Error: 未选中物品'
                        }
                else:
                    #判断物品是否可用
                    unuseableObjectOid = []
                    for oid in selectedObjectList['oid']:
                            item_info = management.get_item(oid)
                            if item_info['useable'][0] != '可用':
                                unuseableObjectOid.append(oid)
                                #删除该物品
                                index = selectedObjectList['oid'].index(oid)
                                del selectedObjectList['name'][index]
                                del selectedObjectList['oid'][index]
                    
                    if unuseableObjectOid:#存在不可用的物品，告诉用户
                            toast = {
                                'type':'error',
                                'content':f'Error: 物品不可用,oid{unuseableObjectOid}'
                            }

                    else: #发送审批申请
                        create_approvalObject(user_id, selectedObjectList, event.action.form_value.Input_value)
                        #清空选中物品列表
                        selectedObjectList = None
                        toast = {
                                'type':'success',
                                'content':'success: 已发送申请'
                            }                    
                    update_card(token, object_id='0', selectedObjectList=selectedObjectList)
            else:
                if value.name == 'home':
                    update_card(token, object_id='0', selectedObjectList=selectedObjectList)
                elif value.name == 'self':
                    update_card(token, object_id='-1', user_id=user_id, selectedObjectList=selectedObjectList)
                elif value.name == 'object.inspect':
                    update_card(token, object_id=value.id, selectedObjectList=selectedObjectList)
                elif value.name == 'back':
                    if int(value.id) != 0: #主页时的返回按钮不可用
                        update_card(token, object_id=int(value.id)/1000, selectedObjectList=selectedObjectList)                        
                elif value.name == 'object.return':
                    toast = {
                        'type':'success',
                        'content':'success: 已归还'
                    }
                    management.return_item(user_id,value.object_param_1)
                    update_card(token, object_id=-1, user_id=user_id, selectedObjectList=selectedObjectList)
        elif event.action.tag == 'input':
            input_value = event.action.input_value
            selectedObjectList = event.action.value.selectedObjectList.__dict__
            
            if event.action.name == "input.search":
                update_card(token, object_id=-2, target=input_value, selectedObjectList=selectedObjectList)
        elif event.action.tag == 'checker':
            checked = event.action.checked
            selectedObjectList = event.action.value.selectedObjectList.__dict__
            if checked:
                selectedObjectList['name'].append(event.action.value.name)
                selectedObjectList['oid'].append(event.action.value.oid)
            else:
                try:
                    index = selectedObjectList['oid'].index(event.action.value.oid)
                    del selectedObjectList['name'][index]
                    del selectedObjectList['oid'][index]
                except ValueError:
                    pass
            update_card(token, object_id=int(event.action.value.oid)/1000, selectedObjectList=selectedObjectList)


    request_data = {
        'toast':toast if toast else {}
    }
    return jsonify(request_data)

@event_manager.register("approval_instance")
def approval_instance_event_handler(req_data: ApprovalInstanceEvent):
    event = req_data.event
    
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
            params['do'] = form[0].get('value')
            params['time'] = form[1].get('value')
            params['objectList'] = ujson.loads(form[2].get('value'))
            applicant_name = management.get_member(applicant_user_id).get('name')
            if status in ('REJECTED','CANCELED','DELETED'): 
                for oid in params['objectList']['oid']:
                    management.set_item_state(oid=oid,operater_user_id=operator_user_id,operation=status,\
                                            useable=1,wis="仓库",do=params['do'])
                logging.info(f"审批：{operator_user_id}拒绝对{params['objectList']['oid']}的申请")
            elif status == 'APPROVED':
                for oid in params['objectList']['oid']:
                    management.set_item_state(oid=oid,operater_user_id=operator_user_id,operation=status,\
                                            useable=0,wis=applicant_name,do=params['do'])
                logging.info(f"审批：{operator_user_id}同意对{params['objectList']['oid']}的申请")


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
    elif requests.get("event"): #事件
        event_id = requests.get('header').get('event_id')
        create_time = requests.get('header').get('create_time')
        #使用redis监测重复请求
        if r.exists(event_id): #请求已处理，跳过
            logging.error(f"This request has been handled. event_id:{event_id}")
            return jsonify()
        else:
            r.set(event_id, create_time, ex=3600)
            logging.info(f"fetch request,event_id:{event_id}")
            management.insert_request(event_id,create_time)
    else:
        logging.info(f"request={requests}")

    event_handler, event = event_manager.get_handler_with_event(VERIFICATION_TOKEN, ENCRYPT_KEY)
    # 运行协程并返回响应
    return event_handler(event)

@app.errorhandler
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response

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
def getItemsBySheets(): #从电子表格中获取物品数量
    #校验修改时间，检测是否有变化
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
                item_num_total = item[2] if item[2] else 0
                item_num_broken = item[3] if item[3] else 0
                management.add_items_until_limit(name=item_name, category_name=category_name, num=item_num_total, num_broken=item_num_broken)
            #虽然函数名是转换成md5，但不转也能直接用
            management.update_itemSheet_md5(latest_modify_time_remote)
        else:
            logging.info('skip add item by sheet')
    except Exception as e:
        raise Exception(f"{e}\n如需通过电子表格初始化数据库，请创建一个电子表格，按格式填入值后，确认`settings.json`中['sheet']:['token']和['sheet_id_TOTAL']是否正确。否则注释掉getItemsBySheets()")

@app.before_first_request
def subApprovalEvent(): #订阅审批事件
    # 只能订阅一次，因此第一次初始化后会一直弹subscription existed异常（已捕获）
    # 确认订阅成功后，你完全可以注释掉它
    try:
        approval_api_event.subscribe(APPROVAL_CODE)
        logging.info(f"成功订阅审批事件{APPROVAL_CODE}")
    except:
        logging.info("subApprovalEvent() 只能订阅一次，因此你完全可以注释掉它")

'''
private function
'''
@celery_task
def update_card(token, object_id=None, user_id=None, target=None, selectedObjectList=None):
    data = create_messageInteractive(object_id, user_id, target, selectedObjectList)
    if data:
        logging.info(f"更新卡片token:{token}")
        message_api_client.update_interactive(token, data)

@celery_task
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

def create_messageInteractive(object_id=None, user_id=None, target=None, selectedObjectList=None):
    title_map = {
        '0':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"个人仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态'},
        '1':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物资类型", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '2':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '3':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物资仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态'},
        '4':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
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
    
    if not selectedObjectList:
        #初始化选择列表
        selectedObjectList = {
            'name':[],
            'oid':[]
        }
    #开始构建卡片
    #标题和列名
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
    result_data = replace_placeholders(json_data, values)
    #已选中物品数据加入到按钮返回值内
    result_data['elements'][0]['columns'][1]['elements'][0]['behaviors'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][0]['columns'][2]['elements'][0]['behaviors'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][0]['columns'][3]['elements'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][1]['actions'][0]['value']['selectedObjectList'] = selectedObjectList

    #查找相关数据
    _list = None
    display_target = 'list' #默认以列表方式呈现，可选为['list','object']
    try:
        if title_id == '0': #个人页
            _list = management.get_member_items(user_id)
            display_target = 'object'
        elif title_id == '1': #仓库（所有物品类型）
            _list = management.get_category()
        elif title_id == '2': #仓库（某类型的所有物品名）
            _list = management.get_list(category_id=_id)
        elif title_id == '3': #仓库（某名字的所有物品信息）
            _list = management.get_items(name_id=_id)
            display_target = 'object'
        elif title_id == '4': #仓库(搜索页)
            #尝试将字符串作为id进行搜索
            if can_convert_to_int(target) and int(target)>0: #id
                try:
                    if int(target)>1000000:  #oid
                        _list = management.get_item(oid=target)
                        display_target = 'object' #仅对搜索具体oid的操作以对象方式呈现
                    elif int(target)>1000: #name_id
                        _list = management.get_list(name_id=target)
                except Exception:
                    pass
            #同时按名称搜索相关物品
            if display_target == 'list':
                if not _list:
                    _list = management.get_list(name=target)
                else:
                    try:
                        _list.update(management.get_list(name=target))
                    except Exception:
                        pass
        #构建参数列表
        if display_target == 'list':
            object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_)} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
        elif display_target == 'object':
            object_list =[{'param1': id_, 'param2': name_, 'param3': useable_,'oid': id_, 'name': name_, 'useable': useable_, 'do': do_, 'wis':wis_} 
                    for id_, name_, useable_, do_,wis_ in zip(_list['id'], _list['name'], _list['useable'], _list['do'],_list['wis'])] if _list else None
        
        if object_list: #如有相关数据-展示循环容器-勾选器
            for obj in object_list:
                checker_text = (
                    f"<font color=blue>{format_with_margin(obj['param1'],10)}</font>  "
                    f"<font color=red>{format_with_margin(obj['param3'],10)}</font>  "
                    f"<font color=green>{format_with_margin(obj['param2'],20,6)}</font>"
                )
                obj['checker_text'] = checker_text
                repeat_elements = copy.deepcopy(CARD_DISPLAY_REPEAT_ELEMENTS_JSON)
                
                if display_target == 'object': #如展示的是物品对象 
                    #额外添加二次确认弹窗-
                    confirm_data = copy.deepcopy(BUTTON_CONFIRM_JSON)
                    if title_id == '0': #归还操作-设置按键值
                        confirm_data['text']['content'] = f"你是否要归还{obj['name']} oid:{obj['oid']}"
                        repeat_elements['button_area']['buttons'][0]['value']['name']="object.return"
                    else:   #展示物品详细信息-修改按键值为空
                        confirm_data['text']['content'] = f"{obj['name']} oid:{obj['oid']}\
                            当前位置:{obj['wis']}\t当前状态:{obj['useable']}\n备注：{obj['do']}"
                        repeat_elements['button_area']['buttons'][0]['value']['name']="none"
                    repeat_elements['button_area']['buttons'][0]['confirm']=confirm_data
                    #同时开启勾选器允许勾选
                    if obj['useable'] == '可用':
                        repeat_elements['disabled']=False
                    #根据已选中物品信息设置勾选器状态
                    if str(obj['oid']) in selectedObjectList['oid']:
                        repeat_elements['checked'] = True
                #将已选中物品加入到返回值内
                repeat_elements['button_area']['buttons'][0]['value']['selectedObjectList'] = selectedObjectList
                repeat_elements['behaviors'][0]['value']['selectedObjectList'] = selectedObjectList
                #添加一行勾选器
                result_data['elements'].append(replace_placeholders(repeat_elements, obj))
        else:   #如无相关数据-提示用户
            raise Exception(f"Error:找不到相关物品")
    except Exception as e:
        result_data['elements'].append({
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"{e}",
                }
            })
    #设置表单容器
    form_json = copy.deepcopy(FORM_JSON)
    #显示已选中物品
    form_json['elements'][1]['content'] = "\n".join(f"{format_with_margin(name,margin=20)}{oid}" \
        for name, oid in zip(selectedObjectList["name"], selectedObjectList["oid"])) 
    #返回选中的物品列表
    form_json['elements'][3]['value']['selectedObjectList'] = selectedObjectList
    #添加表单容器    
    result_data['elements'].append(form_json)
    return result_data

@celery_task
def create_approvalObject(user_id, selectedObjectList, do): #创建物品审批
    for oid in selectedObjectList['oid']:
        management.apply_item(user_id=user_id, oid=int(oid), do=do)
    form=[
        {'id':'do','type':'textarea','value':do if do else "None"},
        {'id':'date','type':'date',"value": f"{datetime.fromtimestamp(time.time()).strftime("%Y-%m-%dT%H:%M:%S+08:00")}"},
        {'id':'objectList','type':'textarea', 'value':ujson.dumps(selectedObjectList,indent=2,ensure_ascii=False)}
        # {'id':'objectList','type':'textarea', 'value':"\n".join(f"{format_with_margin(name,margin=20)}{oid}" \
        #         for name, oid in zip(selectedObjectList["name"], selectedObjectList["oid"])) }
    ]

    approval_api_event.create(approval_code=APPROVAL_CODE, user_id=user_id,\
                            form=ujson.dumps(form))
    logging.info(f"发送审批,{user_id} 申请 {selectedObjectList['oid']}")

'''
user commands
'''
@celery_task
def create_messageResponse(user_id,message,sender):
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
        'load':     {'command':command_load,            'needed_root':True},
    }
    #目前只能识别文字信息
    if message.get('message_type') != 'text':
        reply_text = reply_map['invald_type']
    else:
        text = ujson.loads(message['content']).get('text')
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
    for mention in message['mentions']:
        if mention.get('key') == object:
            user_id = mention['id']['user_id']
            break
    
    if not management.get_member(user_id) if user_id else None:
        return reply_map['invalid_object'] % f'无法识别的用户{object}'

    management.set_member_root(user_id)
    return reply_map['success']

def command_delete_op(reply_map, message, sender, object, params):
    user_id = None
    for mention in message['mentions']:
        if mention['key'] == object:
            user_id = mention['id']['user_id']
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
        user_id = sender['sender_id']['user_id']
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
    
    user_id = sender['sender_id']['user_id']
    result = management.return_item(user_id,oid)

    return result

def command_save(reply_map, message, sender, object, params):
    try:
        #先删除旧记录
        spreadsheet_api_client.dimensionRange(ITEM_SHEET_TOKEN,SHEET_ID_ITEM,"COLUMNS",1,6)
        #批量保存
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

def command_load(reply_map, message, sender, object, params):
    try:
        sheet_date =  spreadsheet_api_client.readRange(ITEM_SHEET_TOKEN, f"{SHEET_ID_ITEM}!A2:F")
        items_info = sheet_date['data']['valueRange']['values']
        management.del_all()
        for item_info in items_info:
            management.add_item(oid=item_info[0],
                                name=item_info[1],
                                category_name=item_info[2],
                                useable=item_info[3],
                                wis=item_info[4],
                                do=item_info[5])
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
    {'load':<{margin}} \t(仅管理员)同步电子表格中物资情况到数据库
    '''

if __name__ == "__main__":
    # 启动服务
    app.run(host="0.0.0.0", port=3000, debug=True)
