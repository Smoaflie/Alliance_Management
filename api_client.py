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
    def send_text_with_open_id(self, open_id, content):
        self.send("open_id", open_id, "text", content)
    def send_text_with_user_id(self, user_id, content):
        self.send("user_id", user_id, "text", content)
    def send_interactive_with_user_id(self, user_id, content):
        self.send("user_id", user_id, "interactive", content)

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
            "content": content,
            "msg_type": msg_type,
        }
    
        resp = requests.post(url=url, headers=headers, json=req_body)
        self._check_error_response(resp)

class SpreadsheetApiClient(ApiClient):
    def modifySheets(self, spreadsheetToken, sheetId, range, values):
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

class LarkException(Exception):
    def __init__(self, code=0, msg=None):
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return "{}:{}".format(self.code, self.msg)

    __repr__ = __str__
