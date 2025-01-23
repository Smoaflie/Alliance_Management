
import ujson
import logging

from flask import jsonify,request,Blueprint
from requests import HTTPError

from app import database
from app.extensions import rate_limit,celery_task,redis_client
from app.feishu.config import (
    VERIFICATION_TOKEN,
    ENCRYPT_KEY,
    APPROVAL_CODE,
    spreadsheet_api_client,
    message_api_client,
    contact_api_client,
    cloud_api_client,
    approval_api_event,
    event_manager,
)
from scripts.utils import (
    obj_2_dict,
    DEBUG_OUT,
)
from scripts.api.feishu_api import (
    MessageReceiveEvent,
    UrlVerificationEvent,
    BotMenuClickEvent,
    CardActionEvent,
    ApprovalInstanceEvent,
)
from app.feishu.commands import (
    create_command_message_response,
    _create_message_card_date,
    send_a_new_message_card,
    _update_message_card,
    create_approval_about_apply_items
)

'''
init
'''
# 蓝图
events_bp = Blueprint('feishu_events', __name__)

# 日志
class FeishuLogger():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
logger = FeishuLogger()

'''
Flask app function
'''
@events_bp.route("/", methods=["POST"], strict_slashes=False)
def callback_event_handler():    
    """
    处理飞书的事件/回调
    
    在开发者后台配置请求地址后(可按需调整route地址)，飞书会将请求发来，由该函数处理。

    该函数会提取事件/回调的唯一标识id:
        假如redis内有重复id的事件/回调,认为该请求已处理,返回200空响应
        假如redis中没相应数据,存储,并跳转到event_manager获取到事件/回调对应的处理函数
    """
    requests = request.json
    DEBUG_OUT(requests)
    if requests.get('uuid'):  #回调
        logger.info("fetch request,uuid:%s" % requests['uuid'])
    elif requests.get("event"): #事件
        event_id = requests.get('header').get('event_id')
        create_time = requests.get('header').get('create_time')
        logger.info("fetch event,event_id:%s" % event_id)
        #使用redis监测重复请求
        if redis_client.exists(event_id): #请求已处理，跳过
            logger.error("This event has been handled. event_id:%s" % event_id)
            return jsonify()
        else:
            redis_client.set(event_id, create_time, ex=3600)
    event_handler, event = event_manager.get_handler_with_event(VERIFICATION_TOKEN, ENCRYPT_KEY)
    # 运行协程并返回响应
    return event_handler(event)

@events_bp.errorhandler
def msg_error_handler(ex):
    """错误讯息处理"""
    logger.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, HTTPError) else 500
    )
    return response

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
    """事件 接收消息-`im.message.receive_v1`的具体处理"""
    user_id = req_data.event.sender.sender_id.user_id
    message = obj_2_dict(req_data.event.message)
    sender_id = obj_2_dict(req_data.event.sender.sender_id)
    logger.info("user_id:%s, message:%s" % (user_id, message))
    create_command_message_response(user_id=user_id,message=message,sender_id=sender_id)

    return jsonify()

@event_manager.register("application.bot.menu_v6")
@rate_limit("application.bot.menu_v6")    
def bot_mene_click_event_handler(req_data: BotMenuClickEvent):
    """
    事件 机器人菜单-`application.bot.menu_v6`的具体处理
    """
    user_id = req_data.event.operator.operator_id.user_id
    event_key = req_data.event.event_key
    logger.info("user_id:%s, event_key:%s" % (user_id, event_key))
    if event_key == 'custom_menu.inspect.items':
    #获取全部物品类型，配置映射
        content = _create_message_card_date(object_id=0)
        send_a_new_message_card(user_id, content)
    return jsonify()

@event_manager.register("card.action.trigger")
def card_action_event_handler(req_data: CardActionEvent):
    """
    事件 卡片交互-`card.action.trigger`的具体处理.
    """
    event = req_data.event
    token = event.token
    user_id = event.operator.user_id
    alife_card_id = database.is_alive_card(user_id)
    current_card_id = event.context.open_message_id
    toast = None
    logger.info("user_id:%s, alife_card_id:%s, current_card_id:%s" % (user_id, alife_card_id, current_card_id))

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
                            item_info = database.get_item(oid)
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
                        create_approval_about_apply_items(user_id, selectedObjectList, event.action.form_value.Input_value)
                        #清空选中物品列表
                        selectedObjectList = None
                        toast = {
                                'type':'success',
                                'content':'success: 已发送申请'
                            }                    
                    _update_message_card(token, object_id=0, selectedObjectList=selectedObjectList)
            else:
                if value.name == 'home':
                    _update_message_card(token, object_id=0, selectedObjectList=selectedObjectList)
                elif value.name == 'self':
                    _update_message_card(token, object_id=-1, user_id=user_id, selectedObjectList=selectedObjectList)
                elif value.name == 'object.inspect':
                    _update_message_card(token, object_id=int(value.id), selectedObjectList=selectedObjectList)
                elif value.name == 'back':
                    if int(value.id) != 0: #主页时的返回按钮不可用
                        _update_message_card(token, object_id=int(value.id)//1000, selectedObjectList=selectedObjectList)                        
                elif value.name == 'object.return':
                    toast = {
                        'type':'success',
                        'content':'success: 已归还'
                    }
                    database.return_item(user_id,value.object_param_1)
                    _update_message_card(token, object_id=-1, user_id=user_id, selectedObjectList=selectedObjectList)
        elif event.action.tag == 'input':
            input_value = event.action.input_value
            selectedObjectList = event.action.value.selectedObjectList.__dict__
            
            if event.action.name == "input.search":
                _update_message_card(token, object_id=-2, target=input_value, selectedObjectList=selectedObjectList)
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
            _update_message_card(token, object_id=int(event.action.value.oid)//1000, selectedObjectList=selectedObjectList)


    request_data = {
        'toast':toast if toast else {}
    }
    return jsonify(request_data)

@event_manager.register("approval_instance")
def approval_instance_event_handler(req_data: ApprovalInstanceEvent):
    """回调 审批实例状态变化-`approval_instance`的具体处理"""
    event = req_data.event
    approval_code = event.approval_code
    status = event.status

    logger.info("approval_code:%s" % approval_code)

    if approval_code == APPROVAL_CODE:
        instance = approval_api_event.fetch_instance(event.instance_code).json()
        applicant_user_id = instance.get('data').get('timeline')[0].get('user_id')
        #TODO:同意和拒绝的结构不一样，现在写的是不好的解决办法
        operator_user_id = (instance.get('data').get('timeline')[-1].get('user_id')
                            if instance.get('data').get('timeline')[-1].get('user_id') 
                            else instance.get('data').get('timeline')[-2].get('user_id'))
        if status in ('APPROVED', 'REJECTED','CANCELED','DELETED'): 
            form = ujson.loads(instance.get('data').get('form'))
            params = {}
            params['do'] = form[0].get('value')
            params['time'] = form[1].get('value')
            params['objectList'] = ujson.loads(form[2].get('value'))
            applicant_name = database.get_member(applicant_user_id).get('name')
            if status in ('REJECTED','CANCELED','DELETED'): 
                for oid in params['objectList']['oid']:
                    database.set_item_state(oid=oid,operater_user_id=operator_user_id,
                                                operation=status,useable=1,wis="仓库",do=params['do'])
                logger.info("审批：%s拒绝对 %s 的申请" % (
                                operator_user_id, params['objectList']['oid']))
            elif status == 'APPROVED':
                for oid in params['objectList']['oid']:
                    database.set_item_state(oid=oid,operater_user_id=operator_user_id,
                                                operation=status,useable=0,wis=applicant_name,do=params['do'])
                logger.info("审批：%s同意对 %s 的申请" % (
                                operator_user_id, params['objectList']['oid']))


    return jsonify()

