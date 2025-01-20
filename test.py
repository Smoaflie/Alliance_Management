import hashlib
import os
import pymysql
import time
import ujson

from dotenv import load_dotenv, find_dotenv

from scripts.api.api_management import ApiManagement
from scripts.api.api_feishu_clients import MessageApiClient
from scripts.api.api_feishu_clients import SpreadsheetApiClient
from scripts.api.api_feishu_clients import ContactApiClient
from scripts.api.api_feishu_clients import CloudApiClient
from scripts.api.api_feishu_clients import ApprovalApiClient
from scripts.api.api_feishu_events import EventManager

#以下内容直接从server搬过来的，没进行优化
# load env parameters form file named .env
load_dotenv(find_dotenv())
# load from env
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
VERIFICATION_TOKEN = os.getenv("VERIFICATION_TOKEN")
ENCRYPT_KEY = os.getenv("ENCRYPT_KEY")
LARK_HOST = os.getenv("LARK_HOST")
with open('settings.json', 'r') as f:
    settings = ujson.loads(f.read())
    ITEM_SHEET_TOKEN = settings.get('sheet').get('token')
    SHEET_ID_TOTAL = settings.get('sheet').get('sheet_id_TOTAL')
    APPROVAL_CODE = settings.get('approval').get('approval_code')

    spreadsheet_api_client = SpreadsheetApiClient(APP_ID, APP_SECRET, LARK_HOST)
    contact_api_client = ContactApiClient(APP_ID, APP_SECRET, LARK_HOST)
    cloud_api_client = CloudApiClient(APP_ID, APP_SECRET, LARK_HOST)
    approval_api_event = ApprovalApiClient(APP_ID, APP_SECRET, LARK_HOST)

def search_contact_to_add_members():
    """
    (初始化)通过通讯录获取用户列表并将用户信息装入数据库members表中

    使用`获取通讯录授权范围`api获取用户列表    
        该api只能获取直属于组织的用户列表，因此需要调整组织架构让目标用户直属于组织;
        或者 加点代码递归搜索组织下各部门的用户列表
    """
    user_ids = []
    page_token = None
    while(True):
        result = contact_api_client.fetch_scopes(user_id_type='user_id', page_token=page_token)
        user_ids += result.get('data').get('user_ids')
        page_token = result.get('data').get("page_token")
        if not page_token:
            break

    with open("test.json", 'w') as f:
        json_str = ujson.dumps(user_ids, indent=4, ensure_ascii=False) 
        f.write(json_str)
        print("写入成功")
    #校验md5值，检测是否有变化
    # list_string = ''.join(map(str, user_ids))
    # MD5remote = hashlib.md5()
    # MD5remote.update(list_string.encode('utf-8'))
    # MD5remote = MD5remote.hexdigest()

    # MD5local = management.fetch_contact_md5()

    # if MD5local != MD5remote:
    #     items = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id').get('data').get('items')
    #     user_list = list()
    #     for item in items:
    #         user_list.append({
    #             'name':item['name'],
    #             'user_id':item['user_id']
    #         })
    #     management.add_member_batch(user_list)
    #     management.update_contact_md5(MD5remote)
    #     print("add members from contact.")
    # else:
    #     print("skip add members from contact.")

if __name__ == "__main__":
    search_contact_to_add_members()