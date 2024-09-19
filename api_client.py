#! /usr/bin/env python3.8
import os
import logging
import requests
import json

APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")

# const
TENANT_ACCESS_TOKEN_URI = "/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URI = "/open-apis/im/v1/messages"

class ApiClient(object):
    def __init__(self, app_id, app_secret, lark_host):
        self._app_id = app_id
        self._app_secret = app_secret
        self._lark_host = lark_host
        self._tenant_access_token = ""

    @property
    def tenant_access_token(self):
        return self._tenant_access_token
    
    def _authorize_tenant_access_token(self):
        # get tenant_access_token and set, implemented based on Feishu open api capability. doc link: https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/tenant_access_token_internal
        url = "{}{}".format(self._lark_host, TENANT_ACCESS_TOKEN_URI)
        req_body = {"app_id": self._app_id, "app_secret": self._app_secret}
        response = requests.post(url, req_body)
        self._check_error_response(response)
        self._tenant_access_token = response.json().get("tenant_access_token")

    @staticmethod
    def _check_error_response(resp):
        # check if the response contains error information
        if resp.status_code != 200:
            resp.raise_for_status()
        response_dict = resp.json()
        code = response_dict.get("code", -1)
        if code != 0:
            logging.error(response_dict)
            raise LarkException(code=code, msg=response_dict.get("msg"))

class MessageApiClient(ApiClient):
    def __init__(self, app_id, app_secret, lark_host):
        super().__init__(app_id, app_secret, lark_host)
        # self.sent_message_dict = {}

    #消息api
    def send_text_with_open_id(self, open_id, content):
        return self.send("open_id", open_id, "text", content)
    def send_text_with_user_id(self, user_id, content):
        return self.send("user_id", user_id, "text", content)
    def send_interactive_with_user_id(self, user_id, content):
        return self.send("user_id", user_id, "interactive", content)

    def send(self, receive_id_type, receive_id, msg_type, content):
        # send message to user, implemented based on Feishu open api capability. doc link: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create
        self._authorize_tenant_access_token()
        url = "{}{}?receive_id_type={}".format(
            self._lark_host, MESSAGE_URI, receive_id_type
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content
        }
    
        resp = requests.post(url=url, headers=headers, json=req_body)
        self._check_error_response(resp)
        return resp.json()

        #todo:如使用open_id等，需修改
        #todo:分析需求，目前获取messageid只是为了修改卡片内容，但卡片交互时会发送messageid，似乎没必要自己维护消息列表
        # user_id = receive_id
        # self.add_sent_message_into_dict(message_request, user_id)
        # message_request = resp.json()

        # return message_request

    # def add_sent_message_into_dict(self, message_request, user_id):
    #     message = {
    #         message_request.get('data').get('message_id'):{
    #             'msg_type': message_request.get('data').get('msg_type'),
    #             'chat_id': message_request.get('data').get('chat_id'),
    #             'create_time': message_request.get('data').get('create_time'),
    #             'update_time': message_request.get('data').get('update_time'),
    #             'updated': message_request.get('data').get('updated')
    #         }
    #     }
    #     if self.sent_message_dict.get(user_id) and \
    #         self.sent_message_dict.get(user_id).get(message.keys[0]): 
    #         return
    #     else: 
    #         self.sent_message_dict[user_id] = {
    #             message_request
    #         }

class SpreadsheetApiClient(ApiClient):
    #电子表格api
    def fetchSheet(self, spreadsheet_token):
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v3/spreadsheets/{}/sheets/query".format(self._lark_host, spreadsheet_token)
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
        }
        resp = requests.get(url=url, headers=headers, params=req_body)
        self._check_error_response(resp)

        return resp.json()

    def readRange(self, spreadsheet_token, range):
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(self._lark_host, spreadsheet_token, range)
        
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
            'Content-Type': "application/json; charset=utf-8"
        }

        req_body = {

        }
        resp = requests.get(url=url, headers=headers, params=req_body)
        self._check_error_response(resp)
        return resp.json()

    def modifySheet(self, spreadsheetToken, sheetId, range, values):
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v2/spreadsheets/{}/values".format(self._lark_host, spreadsheetToken)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            "valueRange": {
                "range": f"{sheetId}!{range}",
                "values": values
            }
        }
        resp = requests.put(url=url, headers=headers, data=json.dumps(req_body))
        self._check_error_response(resp)

class ContactApiClient(ApiClient):
    #通讯录api
    def get_scopes(self, user_id_type='open_id', department_id_type='open_department_id'):
        #获取通讯录授权范围
        self._authorize_tenant_access_token()
        url = "{}/open-apis/contact/v3/scopes".format(self._lark_host)
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            'user_id_type': user_id_type,
            'department_id_type': department_id_type,
        }
        resp = requests.get(url=url, headers=headers, params=req_body)
        self._check_error_response(resp)
        return resp.json()
    
    def get_users_batch(self, user_ids, user_id_type = 'open_id'):
        #批量获取用户信息
        self._authorize_tenant_access_token()
        url = "{}/open-apis/contact/v3/users/batch".format(self._lark_host)
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            'user_ids': user_ids,
            'user_id_type': user_id_type,
        }
        resp = requests.get(url=url, headers=headers, params=req_body)
        self._check_error_response(resp)
        return resp.json()

class CloudApiClient(ApiClient):
    #云空间api
    def searchDocs(self, search_key, count=50, offset=0, owner_ids=[], chat_ids=[], docs_types=[]):
        self._authorize_tenant_access_token()
        url = "{}/open-apis/suite/docs-api/search/object".format(self._lark_host)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            'search_key': search_key,
            'count': count,
            'offset': offset,
            'owner_ids': owner_ids,
            'chat_ids': chat_ids,
            'docs_types': docs_types
        }
    
        resp = requests.post(url=url, headers=headers, json=req_body)
        self._check_error_response(resp)
        return resp.json()

class LarkException(Exception):
    def __init__(self, code=0, msg=None):
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return "{}:{}".format(self.code, self.msg)

    __repr__ = __str__
