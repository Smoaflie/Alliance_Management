import hashlib
import logging
from scripts.api.feishu import LarkException
from ..config import FEISHU_CONFIG as _fs,database,redis_client
logger = logging.getLogger(__name__)
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
            resp = _fs.api.contact.get_scopes(user_id_type='user_id', page_token=page_token)
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
            resp = _fs.api.contact.get_users_batch(user_ids=user_ids, user_id_type='user_id')
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
        logger.error("failed to update members from contact: %s" % e)

def sub_approval_event(): 
    """
    (初始化)订阅物品审批定义

    和其他事件不同，审批需要主动订阅才会反馈数据
    只能订阅一次，多次订阅会触发subscription existed异常
    """
    APPROVAL_CODE = _fs.approval.approval_code
    try:
        _fs.api.approval.subscribe(APPROVAL_CODE)
        logger.info("成功订阅审批定义 %s", APPROVAL_CODE)
    except LarkException as e:
        if e.code == 1390007:
            logger.info("已订阅审批定义 %s" % APPROVAL_CODE)
        else:
            logger.error("尝试订阅审批定义 %s 失败: %s" % (APPROVAL_CODE,e))
