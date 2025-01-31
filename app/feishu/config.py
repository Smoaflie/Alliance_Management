import hashlib
import logging
from app import app
from scripts.api.feishu_api import (
    MessageApiClient,
    SpreadsheetApiClient,
    ContactApiClient,
    CloudApiClient,
    ApprovalApiClient,
    TaskApiClient,
    EventManager,
    LarkException
)
from scripts.utils import load_file

logger = logging.getLogger(__name__)

database = app.config.get("database")
redis_client = app.config.get('redis_client')

feishu_config = app.config.get("feishu")
# 飞书后台配置
FEISHU_HOST = "https://open.feishu.cn"

env = feishu_config.get('env')
APP_ID = env.get("APP_ID")
APP_SECRET = env.get("APP_SECRET")
VERIFICATION_TOKEN = env.get("VERIFICATION_TOKEN")
ENCRYPT_KEY = env.get("ENCRYPT_KEY")
LARK_HOST = env.get("LARK_HOST")
# 审批参数
APPROVAL_CODE = feishu_config.get('approval').get('approval_code')
# 消息卡片数据
card_json = load_file("message_card.json")
CARD_DISPLAY_JSON = card_json.get('display')
CARD_DISPLAY_REPEAT_ELEMENTS_JSON = card_json.get('display_repeat_elements')
BUTTON_CONFIRM_JSON = card_json.get('button_confirm')
FORM_JSON = card_json.get('form')
# 云文档参数
ITEM_SHEET_TOKEN = feishu_config.get('sheet').get('token')
SHEET_ID_TOTAL = feishu_config.get('sheet').get('sheet_id_TOTAL')
SHEET_ID_ITEM = feishu_config.get('sheet').get('sheet_id_ITEM')
# 管理员ID
ADMIN_USER_ID = feishu_config.get('management').get('admin_user_id')

# init service
spreadsheet_api_client = SpreadsheetApiClient(APP_ID, APP_SECRET, LARK_HOST)
message_api_client = MessageApiClient(APP_ID, APP_SECRET, LARK_HOST)
contact_api_client = ContactApiClient(APP_ID, APP_SECRET, LARK_HOST)
cloud_api_client = CloudApiClient(APP_ID, APP_SECRET, LARK_HOST)
approval_api_event = ApprovalApiClient(APP_ID, APP_SECRET, LARK_HOST)
task_api_client = TaskApiClient(APP_ID, APP_SECRET, LARK_HOST)
event_manager = EventManager()

def update_members():
    """更新成员列表.
    使用`获取通讯录授权范围`api获取用户列表    
        该api只能获取直属于组织的用户列表，因此需要调整组织架构让目标用户直属于组织;
        或者 加点代码递归搜索组织下各部门的用户列表
    """
    try:
        user_ids = []
        page_token = None
        while(True):
            resp = contact_api_client.fetch_scopes(user_id_type='user_id', page_token=page_token)
            result = resp
            user_ids += result.get('data').get('user_ids')
            page_token = result.get('data').get("page_token")
            if not page_token:
                break

        #校验md5值，检测是否有变化
        list_string = ''.join(map(str, user_ids))
        MD5remote = hashlib.md5()
        MD5remote.update(list_string.encode('utf-8'))
        MD5remote = MD5remote.hexdigest()

        MD5local = database.fetch_contact_md5()

        if MD5local != MD5remote:
            resp = contact_api_client.get_users_batch(user_ids=user_ids, user_id_type='user_id')
            items = resp.get('data').get('items')
            user_list = list()
            for item in items:
                user_list.append({
                    'name':item['name'],
                    'user_id':item['user_id']
                })
            database.add_member_batch(user_list)
            database.update_contact_md5(MD5remote)
            logger.info("success update members from contact.")
        else:
            logger.info("skip add members from contact.")
    except LarkException as e:
        logger.error("尝试通过通讯录初始化用户列表失败: %s" % e)
def sub_approval_event(): 
    """
    (初始化)订阅物品审批定义

    和其他事件不同，审批需要主动订阅才会反馈数据
    只能订阅一次，多次订阅会触发subscription existed异常
    """
    try:
        approval_api_event.subscribe(APPROVAL_CODE)
        logger.info("成功订阅审批定义 %s", APPROVAL_CODE)
    except LarkException as e:
        if e.code == 1390007:
            logger.info("已订阅审批定义 %s" % APPROVAL_CODE)
        else:
            logger.error("尝试订阅审批定义 %s 失败: %s" % (APPROVAL_CODE,e))
