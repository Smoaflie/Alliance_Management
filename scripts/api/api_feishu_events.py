#!/usr/bin/env python3.8

import abc
import ujson
import hashlib
import typing as t
from scripts.utils import dict_2_obj
from flask import request
from scripts.decrypt import AESCipher

"""
该模块用于订阅飞书事件/回调.

只需要按步骤添加：
定义接收的事件/回调 class nameEvent(Event)
    格式参考 MessageReceiveEvent
在EventManager._event_list内中添加新事件/回调类名

使用:
import事件/回调对应的类(EventClass)，使用装饰器
@event_manager.register("event.name")
    例子：
    @event_manager.register("im.message.receive_v1")
    def message_receive_event_handler(req_data: MessageReceiveEvent):
"""

class Event(object):
    """事件基类"""
    callback_handler = None

    # event base
    def __init__(self, dict_data, token, encrypt_key):
        # event check and init
        header = dict_data.get("header")
        event = dict_data.get("event")
        if header is not None: # event v2
            self.version = 2
            self.header = dict_2_obj(header)
        else:
            self.version = 1
        self.event = dict_2_obj(event)
        #当未配置Encrypt Key 加密策略时，回调请求头不含X-Lark-Request-Timestamp等内容,将引发错误
        if request.headers.get("X-Lark-Request-Timestamp") and self.version==2:
            self._validate(token, encrypt_key)

    def _validate(self, token, encrypt_key):
        if self.header.token != token:
            raise InvalidEventException("invalid token")
        timestamp = request.headers.get("X-Lark-Request-Timestamp")
        nonce = request.headers.get("X-Lark-Request-Nonce")
        signature = request.headers.get("X-Lark-Signature")
        body = request.data
        bytes_b1 = (timestamp + nonce + encrypt_key).encode("utf-8")
        bytes_b = bytes_b1 + body
        h = hashlib.sha256(bytes_b)
        if signature != h.hexdigest():
            raise InvalidEventException("invalid signature in event")

    @abc.abstractmethod
    def event_type(self):
        return self.header.event_type

class BotMenuClickEvent(Event):
    @staticmethod
    def event_type():
        return "application.bot.menu_v6"
    
class CardActionEvent(Event):
    @staticmethod
    def event_type():
        return "card.action.trigger"

class MessageReceiveEvent(Event):
    @staticmethod
    def event_type():
        return "im.message.receive_v1"

class ApprovalInstanceEvent(Event):
    @staticmethod
    def event_type():
        return "approval_instance"

class UrlVerificationEvent(Event):
    # special event: url verification event
    def __init__(self, dict_data):
        self.event = dict_2_obj(dict_data)

    @staticmethod
    def event_type():
        return "url_verification"

class EventManager(object):
    """事件管理"""

    event_callback_map = dict()
    event_type_map = dict()
    #在这里添加要订阅的 事件/回调 类
    _event_list = [
        MessageReceiveEvent, 
        UrlVerificationEvent, 
        BotMenuClickEvent, 
        CardActionEvent, 
        ApprovalInstanceEvent
    ]

    def __init__(self):
        for event in EventManager._event_list:
            EventManager.event_type_map[event.event_type()] = event

    def register(self, event_type: str) -> t.Callable:
        def decorator(f: t.Callable) -> t.Callable:
            self.register_handler_with_event_type(event_type=event_type, handler=f)
            return f

        return decorator

    @staticmethod
    def register_handler_with_event_type(event_type, handler):
        EventManager.event_callback_map[event_type] = handler

    @staticmethod
    # 监听飞书事件
    def get_handler_with_event(token, encrypt_key):
        dict_data = ujson.loads(request.data)
        dict_data = EventManager._decrypt_data(encrypt_key, dict_data)
        callback_type = dict_data.get("type")
        # only verification data has callback_type, else is event
        if callback_type == "url_verification":
            event = UrlVerificationEvent(dict_data)
            return EventManager.event_callback_map.get(event.event_type()), event

        # get event_type
        schema = dict_data.get("schema")
        if schema is None: # event v1
            #审批事件目前只有v1版本，需对V1版本的事件进行处理
            event_type = dict_data.get('event').get('type')
        else:   # event v2
            event_type = dict_data.get("header").get("event_type")
        # build event
        event = EventManager.event_type_map.get(event_type)(dict_data, token, encrypt_key)
        # get handler
        return EventManager.event_callback_map.get(event_type), event

    @staticmethod
    # 解码飞书事件
    def _decrypt_data(encrypt_key, data):
        encrypt_data = data.get("encrypt")
        if encrypt_key == "" and encrypt_data is None:
            # data haven't been encrypted
            return data
        if encrypt_key == "":
            raise Exception("ENCRYPT_KEY is necessary")
        cipher = AESCipher(encrypt_key)

        return ujson.loads(cipher.decrypt_string(encrypt_data))


class InvalidEventException(Exception):
    def __init__(self, error_info):
        self.error_info = error_info

    def __str__(self) -> str:
        return "Invalid event: {}".format(self.error_info)

    __repr__ = __str__
