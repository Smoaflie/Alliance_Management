import logging
import os
import requests
import time
import ujson

APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")

TENANT_ACCESS_TOKEN_URI = "/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URI = "/open-apis/im/v1/messages"

class ApiClient(object):
    """飞书Api基类."""

    def __init__(
        self,
        app_id: str, 
        app_secret: str, 
        lark_host: str, 
        max_retries: int = 3, 
        retry_delay: int = 2
    ):
        """初始化函数."""
        self._app_id = app_id
        self._app_secret = app_secret
        self._lark_host = lark_host
        self._tenant_access_token = ""
        self._max_retries = max_retries  # 最大重试次数
        self._retry_delay = retry_delay    # 重试间隔（秒）

    def _send_with_retries(self, method, *args, **kwargs):
        """用于调用api时失败后自动重试的装饰器"""
        for attempt in range(self._max_retries):
            try:
                return method(*args, **kwargs)
            except LarkException as e:
                logging.warning(f"请求失败，尝试重试 {attempt + 1}/"
                                f"{self._max_retries}，错误信息: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)  # 等待一段时间再重试
                else:
                    raise  # 超过最大重试次数，抛出异常

    @property
    def tenant_access_token(self):
        """应用的tenant_access_token"""
        return self._tenant_access_token
    
    def _authorize_tenant_access_token(self):
        """
        通过此接口获取 tenant_access_token.
        
        doc link: 
            https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/tenant_access_token_internal
        """ 
        url = "{}{}".format(self._lark_host, TENANT_ACCESS_TOKEN_URI)
        req_body = {"app_id": self._app_id, "app_secret": self._app_secret}
        response = requests.post(url, req_body)
        self._check_error_response(response)
        self._tenant_access_token = response.json().get("tenant_access_token")

    @staticmethod
    def _check_error_response(resp):
        """检查响应是否包含错误信息."""
        # 因调用飞书API接口错误时会传回非200状态码，故不采用状态码判断
        # if resp.status_code != 200:
        #     resp.raise_for_status()
        response_dict = resp.json()
        code = response_dict.get("code", -1)
        if code != 0:
            logging.error(response_dict)
            raise LarkException(code=code, msg=response_dict.get("msg"))

class MessageApiClient(ApiClient):
    """消息 客户端API."""

    def send_text_with_user_id(self, user_id: str, content: dict) -> dict:
        """通过user_id向用户发送文本."""
        content = {
            'text':content
        }
        return self.send("user_id", user_id, "text", content)

    def send_interactive_with_user_id(self, user_id: str, content: dict) -> dict:
        """通过user_id向用户发送消息卡片."""
        return self.send("user_id", user_id, "interactive", content)
    
    def send(
        self, 
        receive_id_type: str, 
        receive_id: str, 
        msg_type: str, 
        content: dict
    ) -> dict:
        """
        发送消息.
        
        调用该接口向指定用户或者群聊发送消息。支持发送的消息类型包括文本、富文本、
        卡片、群名片、个人名片、图片、视频、音频、文件以及表情包等。

        doc link:
            https://open.feishu.cn/document/server-docs/im-v1/message/create
        """
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
            "content": ujson.dumps(content)
        }
        resp = self._send_with_retries(
            requests.post,url=url, 
            headers=headers, 
            json=req_body)

        self._check_error_response(resp)
        return resp.json()

    def recall(self, message_id: str) -> dict:
        """
        撤回消息.

        doc link:
            https://open.feishu.cn/document/server-docs/im-v1/message/delete
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/im/v1/messages/{}".format(
            self._lark_host, message_id
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        resp = self._send_with_retries(
            requests.delete,
            url=url, 
            headers=headers)

        self._check_error_response(resp)
        return resp.json()
    
    def delay_update_message_card(self, token: str, card: dict) -> dict:
        """
        延时更新消息卡片.

        用户与卡片进行交互后，飞书服务器会发送卡片回传交互回调，服务器需要在接收回调
        的 3 秒内以 HTTP 200 状态码响应该回调，在响应时设置 HTTP Body 为 "{}" 
        或者返回自定义 Toast 结构体，详情参考配置卡片交互。

        延时更新卡片必须在响应回调之后进行，并行执行或提前执行会出现更新失败的情况。

        延时更新所需的 token 有效期为 30 分钟，超时则无法更新卡片，且同一个 token 
        只能使用 2 次，超过使用次数则无法更新卡片。

        其余信息请参考文档

        doc link:
            https://open.feishu.cn/document/server-docs/im-v1/message-card/delay-update-message-card
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/interactive/v1/card/update".format(
            self._lark_host
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
            "Content-Type": "application/json; charset=utf-8",
        }

        req_body = {
            'token': token,
            'card': card
        }
        resp = self._send_with_retries(
            requests.delete,
            url=url, 
            headers=headers, 
            json=req_body)

        self._check_error_response(resp)
        return resp.json()
    
class SpreadsheetApiClient(ApiClient):
    """电子表格 客户端API."""

    def query(self, spreadsheet_token: str) -> dict:
        """
        获取电子表格信息.
        
        根据电子表格 token 获取表格中所有工作表及其属性信息，包括
        工作表 ID、标题、索引位置、是否被隐藏等。

        doc link:
            https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/query
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v3/spreadsheets/{}/sheets/query".format(
            self._lark_host, spreadsheet_token
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        resp = self._send_with_retries(
            requests.get,
            url=url, 
            headers=headers)

        self._check_error_response(resp)
        return resp.json()

    def reading_a_single_range(
            self, 
            spreadsheetToken: str, 
            sheetId: str,
            range: str
        ) -> dict:
        """
        读取电子表格中单个指定范围的数据.

        Args:
            spreadsheetToken: 电子表格token
            sheetId:  工作表ID
            range: 查询范围。格式为"<开始位置>:<结束位置>"。其中：
                <开始位置>:<结束位置> 为工作表中单元格的范围，数字表示行索引，
                字母表示列索引。如 A2:B2 表示该工作表第 2 行的 A 列到 B 列。
                range支持四种写法，详情参考电子表格概述

        doc link:
            https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/reading-a-single-range
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(
            self._lark_host, spreadsheetToken, f"{sheetId}!{range}"
        )
        
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
            'Content-Type': "application/json; charset=utf-8"
        }

        resp = self._send_with_retries(
            requests.get,
            url=url, 
            headers=headers)

        self._check_error_response(resp)
        return resp.json()

    def write_date_to_a_single_range(
            self, 
            spreadsheetToken: str, 
            sheetId: str, 
            range: str, 
            values: list
        ) -> dict:
        """
        向单个范围写入数据.

        向电子表格某个工作表的单个指定范围中写入数据。
        若指定范围已内有数据，将被新写入的数据覆盖。

        Args:
            spreadsheetToken: 电子表格token
            sheetId:  工作表ID
            range: 查询范围。格式为"<开始位置>:<结束位置>"。其中：
                <开始位置>:<结束位置> 为工作表中单元格的范围，数字表示行索引，
                字母表示列索引。如 A2:B2 表示该工作表第 2 行的 A 列到 B 列。
                range支持四种写法，详情参考电子表格概述
            values: 写入的数据

        doc link:
            https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/write-data-to-a-single-range
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v2/spreadsheets/{}/values".format(
            self._lark_host, spreadsheetToken
        )
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
        resp = self._send_with_retries(
            requests.put,
            url=url, 
            headers=headers, 
            data=ujson.dumps(req_body)
        )

        self._check_error_response(resp)
        return resp.json()

    def delete_rows_or_columns(
            self, 
            spreadsheetToken: str, 
            sheetId: str, 
            majorDimension: str, 
            startIndex: int, 
            endIndex: int
        ) -> dict:
        """
        删除电子表格中的指定行或列.

        doc link:
            https://open.feishu.cn/document/server-docs/docs/sheets-v3/sheet-rowcol/-delete-rows-or-columns
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/sheets/v2/spreadsheets/{}/dimension_range".format(
            self._lark_host, spreadsheetToken
        )
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        req_body = {
            "dimension": {
                "sheetId": sheetId,
                "majorDimension":majorDimension,
                "startIndex":startIndex,
                "endIndex":endIndex
            }
        }
        resp = self._send_with_retries(
            requests.delete,
            url=url, 
            headers=headers, 
            data=ujson.dumps(req_body)
        )

        self._check_error_response(resp)
        return resp.json()

class ContactApiClient(ApiClient):
    """通讯录 客户端API."""

    def fetch_scopes(
            self, 
            user_id_type: str = 'open_id', 
            department_id_type: str = 'open_department_id'
        ) -> dict:
        """
        获取通讯录授权范围.
        
        调用该接口获取当前应用被授权可访问的通讯录范围，包括
        可访问的部门列表、用户列表和用户组列表。

        doc link:
            https://open.feishu.cn/document/server-docs/contact-v3/scope/list
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/contact/v3/scopes".format(self._lark_host)
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        params = {
            'user_id_type': user_id_type,
            'department_id_type': department_id_type,
        }
        resp = self._send_with_retries(
            requests.get,
            url=url, 
            headers=headers, 
            params=params)

        self._check_error_response(resp)
        return resp.json()
    
    def get_users_batch(
            self, 
            user_ids: list, 
            user_id_type: str = 'open_id'
        ) -> dict:
        """
        批量获取用户信息.

        调用该接口获取通讯录内一个或多个用户的信息，包括用户 ID、
        名称、邮箱、手机号、状态以及所属部门等信息。

        doc link:
            https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/user/batch
        """
        #批量获取用户信息
        self._authorize_tenant_access_token()
        url = "{}/open-apis/contact/v3/users/batch".format(
            self._lark_host
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        params = {
            'user_ids': user_ids,
            'user_id_type': user_id_type,
        }
        resp = self._send_with_retries(
            requests.get,
            url=url, 
            headers=headers, 
            params=params)

        self._check_error_response(resp)
        return resp.json()

class CloudApiClient(ApiClient):
    """云空间 客户端API"""

    def search_docs(
            self, 
            search_key: str, 
            count: int = 50, 
            offset: int = 0, 
            owner_ids: list[str] = [], 
            chat_ids: list[str] = [], 
            docs_types: list[str] = []
        ) -> dict:
        """
        搜索云文档.

        doc link:
            https://open.feishu.cn/document/server-docs/docs/drive-v1/search/document-search
        """
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
    
        resp = self._send_with_retries(
            requests.post,
            url=url, 
            headers=headers, 
            json=req_body)

        self._check_error_response(resp)
        return resp.json()

    def query_docs_metadata(
            self, 
            doc_token: list[str], 
            doc_type: list[str], 
            user_id_type: str = 'open_id',
            with_url: bool = False
        ) -> dict:
        """
        获取文件元数据.
        
        该接口用于根据文件 token 获取其元数据，包括标题、
        所有者、创建时间、密级、访问链接等数据。

        doc link:
            https://open.feishu.cn/document/server-docs/docs/drive-v1/file/batch_query
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/drive/v1/metas/batch_query".format(self._lark_host)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.tenant_access_token,
        }
        params = {
            'user_id_type':user_id_type
        }
        request_docs = []
        for token,type in zip(doc_token,doc_type):
            request_docs.append({
                'doc_token':token,
                'doc_type':type,
                'with_url':with_url
            })
        req_body = {
            'request_docs':request_docs
        }
    
        resp = self._send_with_retries(
            requests.post,
            url=url, 
            headers=headers, 
            json=req_body, 
            params=params)
        
        self._check_error_response(resp)
        return resp.json()

class ApprovalApiClient(ApiClient):
    """审批 客户端API"""

    def create_instance(
            self, 
            approval_code: str, 
            form: str, 
            user_id: str
        ) -> dict:
        """
        创建审批实例.

        doc link:
            https://open.feishu.cn/document/server-docs/approval-v4/instance/create
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/approval/v4/instances".format(self._lark_host)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.tenant_access_token,
        }
        
        req_body = {
            'approval_code':approval_code,
            'user_id':user_id,
            'form':form
        }
    
        resp = self._send_with_retries(
            requests.post,
            url=url, 
            headers=headers, 
            json=req_body)

        self._check_error_response(resp)
        return resp.json()

    def subscribe(self, approval_code: str) -> dict:
        """
        订阅审批事件.

        应用订阅 approval_code 后，该应用就可以收到该审批定义对应实例的事件通知。
        同一应用只需要订阅一次，无需重复订阅。

        doc link:
            https://open.feishu.cn/document/server-docs/approval-v4/event/event-interface/subscribe
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/approval/v4/approvals/{}/subscribe".format(
            self._lark_host,approval_code
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        resp = self._send_with_retries(
            requests.post,
            url=url, 
            headers=headers)

        self._check_error_response(resp)
        return resp.json()

    def fetch_instance(self, instance_id: str) -> dict:
        """
        获取单个审批实例详情.

        doc link:
            https://open.feishu.cn/document/server-docs/approval-v4/instance/get
        """
        self._authorize_tenant_access_token()
        url = "{}/open-apis/approval/v4/instances/{}".format(
            self._lark_host,instance_id
        )
        headers = {
            "Authorization": "Bearer " + self.tenant_access_token,
        }

        resp = self._send_with_retries(
            requests.get,
            url=url, 
            headers=headers)

        self._check_error_response(resp)
        return resp.json()


class LarkException(Exception):
    """自定义飞书异常."""
    
    def __init__(self, code=0, msg=None):
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return "{}:{}".format(self.code, self.msg)

    __repr__ = __str__
