import re
import ujson
import logging
import copy
import time
from datetime import datetime

from app.ext.celery import celery
from app.decorators import celery_task
from app.feishu.config import database
from app.feishu.config import (
    ITEM_SHEET_TOKEN,
    SHEET_ID_ITEM,
    APPROVAL_CODE,
    CARD_DISPLAY_JSON,
    CARD_DISPLAY_REPEAT_ELEMENTS_JSON,
    BUTTON_CONFIRM_JSON,
    FORM_JSON,
    message_api_client,
    spreadsheet_api_client,
    approval_api_event,
    LarkException
)
from scripts.utils import (
    can_convert_to_int,
    format_with_margin,
    load_file,
    replace_placeholders,
    safe_get
)

logger = logging.getLogger(__name__)

'''
private function
'''
@celery_task
def _update_message_card(
    token: str, 
    object_id: int | None = None, 
    user_id: str | None = None, 
    target: str | None = None, 
    selectedObjectList: list | None = None
):
    """
    更新消息卡片
    """
    data = _create_message_card_date(object_id, user_id, 
                                      target, selectedObjectList)
    if data:
        logger.info("更新卡片token: %s" % token)
        message_api_client.delay_update_message_card(token, data)

@celery_task
def send_a_new_message_card(user_id: str, content: dict):
    """
    发送新消息卡片

    如果之前该用户已有消息卡片，先撤回再发送新卡片
    """
    try:
        alive_card_id = database.is_alive_card(user_id)
        if alive_card_id:
            logger.info("撤回与 %s 的消息卡片 %s" % (user_id,alive_card_id))
            database.update_card(user_id)
            message_api_client.recall(alive_card_id)

        resp = message_api_client.send_interactive_with_user_id(user_id, content)
        result = resp.json()
        message_id = safe_get(result,'data','message_id')
        create_time = safe_get(result,'data','create_time')
        logger.info("向 %s 发送新消息卡片 %s" % (user_id,message_id))
        database.update_card(user_id,message_id,create_time)
    except LarkException as e:
        logger.error("发送消息失败: %s" % e)

def _create_message_card_date(
        object_id: int, 
        user_id: str | None = None, 
        target: str | None = None, 
        selectedObjectList: dict[str, list] | None = None
    ):
    """
    生成消息卡片数据
    """
    title_map = {
        '0':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"个人仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态'},
        '1':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物资类型", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '2':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
        '3':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物资仓库", 'param1':'ID', 'param2':'名称', 'param3':'状态'},
        '4':{'CARD_JSON':CARD_DISPLAY_JSON, 'title':"物品总览", 'param1':'ID', 'param2':'名称', 'param3':'数量'},
    }
    # 获取对应的表格式id
    if object_id == -2:
        title_id = '4'
    elif object_id == -1:
        title_id = '0'
    elif object_id == 0:
        title_id = '1'
    elif object_id < 1000:
        title_id = '2'
    else:
        title_id = '3'
    _father_id = str(object_id if object_id > 0 else 0)
    _id = object_id

    # 如果不存在物品选择列表，则初始化
    if not selectedObjectList:
        selectedObjectList = {
            'name':[],
            'oid':[]
        }
    # 开始构建卡片
    # 标题和列名
    values = {
        'title': title_map[title_id]['title'],
        'father_id':_father_id
    }
    title_text = (
        f"       "
        f"<font color=blue>{format_with_margin(title_map[title_id]['param1'],10)}</font> "
        f"<font color=red>{format_with_margin(title_map[title_id]['param3'],8)}</font> "
        f"<font color=green>{format_with_margin(title_map[title_id]['param2'],20)}</font>"
    )
    values['title_text']=title_text
    json_data = copy.deepcopy(title_map[title_id]['CARD_JSON'])
    result_data = replace_placeholders(json_data, values)
    # 将已选中物品数据加入到按钮返回值内
    result_data['elements'][0]['columns'][1]['elements'][0]['behaviors'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][0]['columns'][2]['elements'][0]['behaviors'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][0]['columns'][3]['elements'][0]['value']['selectedObjectList'] = selectedObjectList
    result_data['elements'][1]['actions'][0]['value']['selectedObjectList'] = selectedObjectList
    # 查找相关数据
    _list = None
    display_target = 'list' #默认以列表方式呈现，可选为['list','object']
    try:
        if title_id == '0': #个人页
            _list = database.get_items(user_id=user_id)
            display_target = 'object'
        elif title_id == '1': #仓库（所有物品类型）
            _list = database.get_categories()
        elif title_id == '2': #仓库（某类型的所有物品名）
            _list = database.get_list(category_id=_id)
        elif title_id == '3': #仓库（某名字的所有物品信息）
            _list = database.get_items(name_id=_id)
            display_target = 'object'
        elif title_id == '4': #仓库(搜索页)
            #尝试将字符串作为id进行搜索
            if can_convert_to_int(target) and int(target)>0: #id
                try:
                    if int(target)>1000000:  #oid
                        _list = database.get_item(oid=target)
                        display_target = 'object' #仅对搜索具体oid的操作以对象方式呈现
                    elif int(target)>1000: #name_id
                        _list = database.get_list(name_id=target)
                except Exception as e:
                    logger.error("%s" % e)
            #同时按名称搜索相关物品
            if display_target == 'list':
                if not _list:
                    _list = database.get_list(name=target)
                else:
                    try:
                        _list.update(database.get_list(name=target))
                    except Exception as e:
                        logger.error("%s" % e)
        #构建参数列表
        #TODO:zip最大支持5个列表，无法显示purpose属性
        if display_target == 'list':
            object_list =[{'param1': id_, 'param2': name_, 'param3': str(total_)} 
                    for id_, name_, total_ in zip(_list['id'], _list['name'], _list['total'])] if _list else None
        elif display_target == 'object':
            object_list =[{'param1': id_, 'param2': name_, 'param3': useable_,'oid': id_, 'name': name_, 'useable': useable_, 'do': do_, 'wis':wis_} 
                    for id_, name_, useable_, do_,wis_ in zip(_list['id'], _list['name'], _list['useable'], _list['do'],_list['wis'])] if _list else None
        
        if object_list: #如有相关数据-展示循环容器-勾选器
            for obj in object_list:
                checker_text = (
                    f"<font color=blue>{format_with_margin(obj['param1'],10)}</font>"
                    f"<font color=red>{format_with_margin(obj['param3'],8)}</font>"
                    f"<font color=green>{format_with_margin(obj['param2'],12)}</font>"
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
                        confirm_data['text']['content'] = (
                            f"{obj['name']} oid:{obj['oid']}\n"
                            f"当前位置:{obj['wis']}\t当前状态:{obj['useable']}\n"
                            f"备注：{obj['do']}\n")
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
            raise ValueError(f"Error:找不到相关物品")
    except ValueError as e:
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
    form_json['elements'][1]['content'] = "\n".join(
        f"{format_with_margin(name,margin=20)}{oid}"
        for name, oid in zip(selectedObjectList["name"], selectedObjectList["oid"])
    ) 
    #返回选中的物品列表
    form_json['elements'][3]['value']['selectedObjectList'] = selectedObjectList
    #添加表单容器    
    result_data['elements'].append(form_json)
    return result_data

@celery_task
def create_approval_about_apply_items(
    user_id: str, 
    selectedObjectList: dict, 
    purpose: str = 'null'
):
    """
    创建物品审批实例

    创建APPROVAL_CODE对应的审批实例
    审批定义应按照`配置指南`在控制台创造,特别是审批定义名和自定义id
    """
    for oid in selectedObjectList['oid']:
        database.apply_item(user_id=user_id, oid=int(oid), purpose=purpose)
    form=[
        {'id':'do','type':'textarea','value':purpose if purpose else "None"},
        {'id':'date','type':'date',"value": 
         f"{datetime.fromtimestamp(time.time()).strftime("%Y-%m-%dT%H:%M:%S+08:00")}"},
        {'id':'objectList','type':'textarea', 
         'value':ujson.dumps(selectedObjectList,indent=2,ensure_ascii=False)}
    ]

    approval_api_event.create_instance(approval_code=APPROVAL_CODE, 
                                       user_id=user_id, form=ujson.dumps(form))
    logger.info("发送审批,%s 申请 {selectedObjectList['oid']}" % user_id)


'''
user commands
'''
@celery_task
def create_command_message_response(
    user_id: str,
    message: dict,
    sender_id: dict
):
    """
    生成命令消息的回复

    该函数会对传入的消息进行判断，如果为文本消息且开头是'/'则判断为指令
    接收到指令消息后,该函数会读取出指令的object和params数据,并交给对应的处理函数处理
    处理函数的返回值会作为消息发送给用户

    支持的命令放在command_map内
        key: 指令名，如命令"/add item ...",对应key='add'
        value: 该指令的一些参数，比如处理函数，是否需要管理权限
    """
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
    # 如果修改了函数名，记得更新此处
    command_map = {
        'add':      {'command':_command_add_object,      'needed_root':True},
        'del':      {'command':_command_delete_object,   'needed_root':True},
        'help':     {'command':_command_get_help,        'needed_root':False},
        'op':       {'command':_command_add_op,          'needed_root':True},
        'deop':     {'command':_command_delete_op,       'needed_root':True},
        'lsop':     {'command':_command_list_op,         'needed_root':True},
        'search':   {'command':_command_search_id,       'needed_root':False},
        'return':   {'command':_command_return_item,     'needed_root':False},
        'save':     {'command':_command_save,            'needed_root':True},
        'load':     {'command':_command_load,            'needed_root':True},
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
                    if not command_map[command]['needed_root'] or database.is_user_root(user_id):
                        reply_text = command_map[command]['command'](reply_map, message, sender_id, object, params)
                    else:
                        reply_text = reply_map['permission_denied']
    if reply_text not in ('', None) :
        message_api_client.send_text_with_user_id(user_id,reply_text)
        logger.info('向 %s 发送消息 %s' % (user_id,reply_text))

def _command_add_object(reply_map, message, sender_id, object, params):
    """
    (指令)添加物品

    指令参数参考`_command_get_help`
    """
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
            #TODO:操作执行失败的检测与处理
            if object == 'item':
                database.add_item(params=params)
            elif object == 'list':
                database.add_list(params=params)
            elif object == 'category':
                database.add_category(params=params)
            return reply_map['success']
        
def _command_delete_object(reply_map, message, sender_id, object, params):
    """
    (指令)删除物品

    指令参数参考`_command_get_help`
    TODO:目前有点问题，尝试删除不存在的项并不会报错
    """
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
            #TODO:操作执行失败的检测与处理
            if object == 'item':
                database.del_item(params=params)
            elif object == 'list':
                database.del_list(params=params)
            elif object == 'category':
                database.del_category(params=params)
        
            return reply_map['success']

def _command_add_op(reply_map, message, sender_id, object, params):
    """
    (指令)设置管理员

    指令参数参考`_command_get_help`
    """
    user_id = None
    if message.get('mentions'):
        for mention in message['mentions']:
            if mention.get('key') == object:
                user_id = mention['id']['user_id']
                object =  mention['name']
                break
        
    if not user_id or not database.get_member(user_id):
        return reply_map['invalid_object'] % f'无法识别的用户{object}'

    database.set_member_root(user_id)
    return reply_map['success']

def _command_delete_op(reply_map, message, sender_id, object, params):
    """
    (指令)删除管理员

    指令参数参考`_command_get_help`
    """
    user_id = None
    if message.get('mentions'):
        for mention in message['mentions']:
            if mention['key'] == object:
                user_id = mention['id']['user_id']
                break
    
    if not user_id or not database.get_member(user_id):
        return reply_map['invalid_object'] % f'无法识别的用户{object}'
    
    #TODO：id不在表中如何解决？
    database.set_member_unroot(user_id)
    return reply_map['success']

def _command_list_op(reply_map, message, sender_id, object, params):
    """
    (指令)列出管理员名单

    指令参数参考`_command_get_help`
    """
    result = database.get_members_root()
    return ujson.dumps(result, ensure_ascii=False) if result else '当前暂无管理员'

def _command_search_id(reply_map, message, sender_id, object, params):
    """
    (指令)搜索id

    指令参数参考`_command_get_help`
    """
    if not can_convert_to_int(object):
        return reply_map['invalid_object'] % f"/search {{id}}<-int不存在"
    
    #TODO:异常处理
    try:
        user_id = sender_id['user_id']
        content = _create_message_card_date(object_id=int(object))
        send_a_new_message_card(user_id, content)
    
        return None
    except Exception as e:
        return f"失败 {e}"

def _command_return_item(reply_map, message, sender_id, object, params):
    """
    (指令)归还物品

    指令参数参考`_command_get_help`
    """
    if not can_convert_to_int(object):
        return reply_map['invalid_object'] % f"/return {{id}}<-int不存在"
    
    #TODO:异常处理
    try:
        user_id = sender_id['user_id']
        result = database.return_item(user_id,int(object))

        return result
    except Exception as e:
        return f"失败 {e}"

def _command_save(reply_map, message, sender_id, object, params):
    """
    (指令)存储当前数据库中的物资(详细)信息到电子表格中.
    """
    try:
        #先删除旧记录
        spreadsheet_api_client.delete_rows_or_columns(
            ITEM_SHEET_TOKEN,SHEET_ID_ITEM,"COLUMNS",1,6)
        #批量保存
        start_line = end_line= 2
        category = database.get_categories()
        for category_id,category_name in zip(
            category['id'],category['name']
        ):
            items_list = database.get_list(category_id)
            values = []
            for name,name_id in zip(
                items_list['name'],items_list['id']
            ):
                items_info = database.get_items(name_id, name)
                if not items_info:
                    continue
                end_line += len(items_info['id'])
                for oid,useable,wis,do,purpose in zip(
                    items_info['id'],items_info['useable'],
                    items_info['wis'],items_info['do'],items_info['purpose']
                ):
                    value =[]
                    value.append(oid)
                    value.append(name)
                    value.append(category_name)
                    value.append(useable)
                    value.append(wis)
                    value.append(do)
                    value.append(purpose)
                    values.append(value)
            spreadsheet_api_client.write_date_to_a_single_range(
                ITEM_SHEET_TOKEN,SHEET_ID_ITEM,f"A{start_line}:G{end_line-1}",values)
            logger.info(
                "已保存 %s 类型的信息到电子表格中，行数%d:%d" %
                (category_name,start_line, end_line-1))
            start_line = end_line
        return reply_map['success']
    except Exception as e:
        #TODO:异常处理
        return f"失败 {e}"

def _command_load(reply_map, message, sender_id, object, params):
    """
    (指令)从设定的电子表格中读取物资(详细)信息存储当前数据库中.
    """
    try:
        sheet_date =  spreadsheet_api_client.reading_a_single_range(ITEM_SHEET_TOKEN, SHEET_ID_ITEM, "A2:G").json()
        items_info = sheet_date['data']['valueRange']['values']
        database.del_all()
        for item_info in items_info:
            database.add_item(oid=item_info[0],
                                name=item_info[1],
                                category_name=item_info[2],
                                useable=item_info[3],
                                wis=item_info[4],
                                do=item_info[5],
                                purpose=item_info[6]
                                )
        return reply_map['success']
    except Exception as e:
        return f"失败 {e}"

def _command_get_help(reply_map, message, sender_id, object, params):
    """返回指令帮助菜单."""
    margin = 10
    return (
        "机器人命令指南：\n"
        "格式：/command [options] [param1=value] [param2=value] ...\n"
        "当前已实现命令commands，标注*号的需要拥有管理权限:\n"
        f"{'help':<{margin}} \t查看《机器人命令指南》\n"
        f"{'*add {{item|list|category}} {{params}}':<{margin}} \t往数据库中插入数据,如父项不存在会自动创建\n"
            f"{'':<{margin}} item\t 具体物品。params:{{'name'|'name_id'}},['category_name','category_id','num']),\n"
            f"{'':<{margin}} list\t 物品列表。params:'name',{{'category_name'|'category_id}}),\n"
            f"{'':<{margin}} category\t 物品类型。params:'category_name'\n"
        f"{'*del {{item|list|category}} {{params}}':<{margin}} \t删除数据库中某条数据,如子项中存在数据则无法删除\n"
            f"{'':<{margin}} item\t 具体物品。params:'id',\n"
            f"{'':<{margin}} list\t 物品列表。params:{{'name'|'id'}},\n"
            f"{'':<{margin}} category\t 物品类型。params:{{'name'|'id'}}\n"
        f"{'op {{@user_name}}':<{margin}} \t给予管理员权限\n"
        f"{'deop {{@user_name}}':<{margin}} \t取消管理员权限\n"
        f"{'lsop {{@user_name}}':<{margin}} \t列出管理员列表\n"
        f"{'search {{id}}':<{margin}} \t搜索id对应的项\n"
        f"{'return {{id}}':<{margin}} \t归还id对应的物品,只能还自己的，管理员可以帮忙归还\n"
        f"{'save':<{margin}} \t(仅管理员)同步物资情况到指定的电子表格\n"
        f"{'load':<{margin}} \t(仅管理员)同步电子表格中物资情况到数据库\n"
    )
