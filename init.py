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

def table_exists(cursor, table_name):
    """
    检查表是否已经存在
    """
    cursor.execute("SHOW TABLES LIKE '%s';" % table_name)
    return cursor.fetchone() is not None
def trigger_exists(cursor, trigger_name):
    """
    检查触发器是否已经存在
    """
    cursor.execute("SELECT * FROM information_schema.TRIGGERS WHERE TRIGGER_NAME = '%s';" % trigger_name)
    return cursor.fetchone() is not None

def init_from_feishu():
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
        management = ApiManagement(settings['mysql'])
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
        try:
            user_ids = []
            page_token = None
            while(True):
                result = contact_api_client.fetch_scopes(user_id_type='user_id', page_token=page_token)
                user_ids += result.get('data').get('user_ids')
                page_token = result.get('data').get("page_token")
                if not page_token:
                    break

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
                print("add members from contact.")
            else:
                print("skip add members from contact.")
        except Exception as e:
            print("尝试通过通讯录初始化用户列表失败: %s" % e)

    def get_items_by_sheets():
        """
        (初始化)从电子表格中获取物品数量.

        目标电子表格:   ITEM_SHEET_TOKEN
        目标工作表：    SHEET_ID_TOTAL

        如需通过电子表格初始化数据库，请创建一个电子表格，按格式填入值后，确认
        `settings.json`中['sheet']:['token']和['sheet_id_TOTAL']是否正确。
        否则注释掉该函数
        """
        try:
            #获取文档修改时间，检测是否有变化
            DocMetadata = cloud_api_client.query_docs_metadata([ITEM_SHEET_TOKEN], ['sheet']).get('data').get('metas')        
            if not DocMetadata:
                raise ValueError(f"ITEM_SHEET_TOKEN:{ITEM_SHEET_TOKEN} 无法找到")
            
            latest_modify_time_remote = DocMetadata[0].get('latest_modify_time') #取[0]是因为使用token只会搜到一个文件
            latest_modify_time_local = management.fetch_itemSheet_md5()

            #如果物资表修改过（数据库数据过时），重新初始化物资数据库
            if latest_modify_time_local != latest_modify_time_remote:
                sheet_date =  spreadsheet_api_client.reading_a_single_range(ITEM_SHEET_TOKEN, SHEET_ID_TOTAL, "A2:D")
                if not sheet_date.get('data'):
                    raise ValueError(f"SHEET_ID_TOTAL:{SHEET_ID_TOTAL} 无法找到")
                
                item_list = sheet_date.get('data').get('valueRange').get('values')
                print('add item by sheet')
                for item in item_list:
                    category_name = item[0]
                    item_name = item[1]
                    item_num_total = item[2] if item[2] else 0
                    item_num_broken = item[3] if item[3] else 0
                    management.add_items_until_limit(name=item_name, category_name=category_name, num=item_num_total, num_broken=item_num_broken)
                #虽然函数名是转换成md5，但不转也能直接用
                management.update_itemSheet_md5(latest_modify_time_remote)
            else:
                print('skip add item by sheet')
        except Exception as e:
            print("尝试通过电子表格初始化物资信息失败: %s" % e)

    def sub_approval_event(): 
        """
        (初始化)订阅审批事件

        和其他事件不同，审批需要主动订阅才会反馈数据
            只能订阅一次，因此第一次初始化后会一直弹subscription existed异常
            确认订阅成功后，你可以注释掉它
        """
        try:
            approval_api_event.subscribe(APPROVAL_CODE)
            print("成功订阅审批事件 %s", APPROVAL_CODE)
        except Exception as e:
            print("尝试通过电子表格初始化物资信息失败: %s" % e)

    search_contact_to_add_members()
    get_items_by_sheets()
    sub_approval_event()

if __name__ == '__main__':
    f = open('settings.json', 'r')
    settings = ujson.loads(f.read())
    f.close()

    # 尝试连接MySQL，失败时自动重试，直到最大重试次数。
    attempt = 0
    retries = 30
    while attempt < retries:
        try:
            conn = pymysql.connect(host=settings['mysql']['host'], user=settings['mysql']['user'],
                                password=settings['mysql']['password'])
            print('连接mysql数据库成功')
            break
        except pymysql.MySQLError as e:
            print(f'连接mysql数据库失败，尝试重连 {attempt}/{retries}，错误原因：{e}')
            attempt += 1
            time.sleep(1)
    # 如果达到最大尝试次数后仍未成功连接，则结束程序
    if attempt == retries:
        raise Exception("无法连接到MySQL，超过最大重试次数。")
    

    sql = "CREATE DATABASE IF NOT EXISTS %s" % settings['mysql']['db']
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.close()

    conn = pymysql.connect(host=settings['mysql']['host'], user=settings['mysql']['user'],
                           password=settings['mysql']['password'], db=settings['mysql']['db'],
                           charset='utf8mb4')  # 确保使用 utf8mb4 字符集
    cursor = conn.cursor()
    print("已定位数据库 %s" % settings['mysql']['db'])

    # 修改事务隔离级别
    sql = 'SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;'
    cursor.execute(sql)
    print("已修改事物隔离级别为 READ COMMITTED")
    # 定义所有需要创建的表
    print("正在创建表")
    tables = {
        # logs 用于存储日志，这个表比较混乱 
            # `id` 日志ID  
            # `time` 提交时间  
            # `userId` 操作人id  
            # `operation` 操作内容 
            # `object` 操作对象  
            # `do` 备注  
        'logs': '''CREATE TABLE `logs` (
          `id` int(255) AUTO_INCREMENT PRIMARY KEY,
          `time` text NOT NULL,
          `userId` text NOT NULL,
          `operation` text NOT NULL,
          `object` int(255) DEFAULT NULL,
          `do` text
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        # item_category 用于存储物资分类
            # `id` 分类ID  
            # `name` 分类名称
            # `total` 分类下物资数
        'item_category': '''CREATE TABLE `item_category` (
          `id` int(6) UNSIGNED AUTO_INCREMENT PRIMARY KEY, 
          `name` text NOT NULL,
          `total` int(11) NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  item_list 存储物资列表
            # `id` 6位对象ID，前3位为对应分类ID
            # `father` 对应分类ID(3位)
            # `name` 物资名称
            # `total`  物资总数
            # `free`    空闲物资数
        'item_list': '''CREATE TABLE `item_list` (
          `id` int(10) UNSIGNED NOT NULL PRIMARY KEY,
          `father` int(255) UNSIGNED NOT NULL,
          `name` text NOT NULL,
          `total` int(6) NOT NULL DEFAULT 0,
          `free` int(6) NOT NULL DEFAULT 0,
          `broken` int(6) NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  存储物资详细信息  
            # `id` 11位对象ID，前6位为对应物品ID
            # `father` 对应物品ID  
            # `useable` 是否可用    1可用，0已借出，2维修中，3报废，4申请中
            # `wis` 当前位置  
            # `do` 备注
            # `purpose` 用途
        'item_info': '''CREATE TABLE `item_info` (
          `id` int(10) UNSIGNED NOT NULL PRIMARY KEY,
          `father` int(255) UNSIGNED NOT NULL,
          `useable` int(2) NOT NULL DEFAULT 1,
          `wis` text,
          `do` text,
          `purpose` text,
          FOREIGN KEY (father) REFERENCES item_list(id)
          ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  存储成员信息  
            # `id` 索引
            # `user_id` 飞书user_id  
            # `name` 实名
            # `root` 管理 1是0否   
            # `card_message_id` 用户会话中消息卡片的message_id
            # `card_message_create_time` 用户会话中消息卡片的创建时间
        'members': '''CREATE TABLE `members` (
          `user_id` text NOT NULL,
          `name` text NOT NULL,
          `root` int(1) NOT NULL DEFAULT 0,
          `card_message_id` text,
          `card_message_create_time` text
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  存储工单信息
            # 'id' 索引
            # 'time' 提交时间
            # 'type' 工单类型
            # 'submitter' 提交人
            # 'info' 具体内容
            # 'state' 状态
        # 'issues': '''CREATE TABLE `members` (
        #   `id` text NOT NULL,
        #   `time` text NOT NULL,
        #   `type` text NOT NULL,
        #   `submitter` text NOT NULL,
        #   `info` text,
        #   `state` text NOT NULL
        # ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
    }
    # 逐个检查并创建表
    for table_name, create_sql in tables.items():
        if not table_exists(cursor, table_name):
            cursor.execute(create_sql)
            print(f"表 {table_name} 创建成功")
        else:
            print(f"表 {table_name} 已存在，跳过创建")

    # 定义需要创建的触发器
    print('正在设置触发器')
    triggers = {
        # 当表item_info增删改后触发，更新item_list和item_category的数量值
        'update_item_total_free': '''
            CREATE TRIGGER update_item_total_free
            AFTER INSERT ON item_info
            FOR EACH ROW
            BEGIN
                UPDATE item_list
                SET total = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father),
                    free = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 1),
                    broken = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 3)
                WHERE id = NEW.father;

                UPDATE item_category
                SET total = (SELECT IFNULL(SUM(total), 0) FROM item_list WHERE father = (SELECT father FROM item_list WHERE id = NEW.father))
                WHERE id = (SELECT father FROM item_list WHERE id = NEW.father);
            END;
        ''',
        'update_item_total_free_on_delete': '''
            CREATE TRIGGER update_item_total_free_on_delete
            AFTER DELETE ON item_info
            FOR EACH ROW
            BEGIN
                UPDATE item_list
                SET total = (SELECT COUNT(*) FROM item_info WHERE father = OLD.father),
                    free = (SELECT COUNT(*) FROM item_info WHERE father = OLD.father AND useable = 1),
                    broken = (SELECT COUNT(*) FROM item_info WHERE father = OLD.father AND useable = 3)
                WHERE id = OLD.father;

                UPDATE item_category
                SET total = (SELECT IFNULL(SUM(total), 0) FROM item_list WHERE father = (SELECT father FROM item_list WHERE id = OLD.father))
                WHERE id = (SELECT father FROM item_list WHERE id = OLD.father);
            END;
        ''',
        'update_item_total_free_after_update': '''
            CREATE TRIGGER update_item_total_free_after_update
            AFTER UPDATE ON item_info
            FOR EACH ROW
            BEGIN
                UPDATE item_list
                SET total = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father),
                    free = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 1),
                    broken = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 3)
                WHERE id = NEW.father;

                UPDATE item_category
                SET total = (SELECT IFNULL(SUM(total), 0) FROM item_list WHERE father = (SELECT father FROM item_list WHERE id = NEW.father))
                WHERE id = (SELECT father FROM item_list WHERE id = NEW.father);
            END;
        '''
    }
    # 逐个检查并创建触发器
    for trigger_name, create_sql in triggers.items():
        if not trigger_exists(cursor, trigger_name):
            cursor.execute(create_sql)
            print(f"触发器 {trigger_name} 创建成功")
        else:
            print(f"触发器 {trigger_name} 已存在，跳过创建")

    # 预设一些值
    '''
    inserts = {
        'item_category': {
            'table':'item_category',
            'key':['name'],
            'value':['裁判系统','电机','机械物资','其他']
        },
        'item_list_referee': {
            'table':'item_list',
            'father_table':'item_category',
            'father_name':'裁判系统',
            'key':['name'],
            'value':[
                '主控模块',
                '电源管理',
                '装甲模块',
                '测速模块',
                '灯条模块',
                '场地交互模块',
                '相机图传模块',
                '定位模块',
                '超级电容管理模块',
                '飞镖触发装置',
                '图传接收端',
                '图传供电器',
                '官方航空线'
            ]
        },
        'item_list_motor': {
            'table':'item_list',
            'father_table':'item_category',
            'father_name':'电机',
            'key':['name'],
            'value':[
                'DJI_3508电机',
                'DJI_6020电机',
                'DJI_2006电机'
            ]
        },
        'item_list_mechanical': {
            'table':'item_list',
            'father_table':'item_category',
            'father_name':'机械物资',
            'key':['name'],
            'value':[
                'M3螺丝刀',
                'M2.5螺丝刀',
                'M4螺丝刀',
                'M2螺丝刀',
                '剪刀',
                '水口钳'
            ]
        },  
        'item_list_consumable':{
            'table':'item_list',
            'father_table':'item_category',
            'father_name':'其他',
            'key':['name'],
            'value':['打印料-PLA-白', 
                     '打印料-PLA-灰',
                     'micro数据线',
                     'typeC数据线',
                     '电池架',
                     '达妙板子',
                     'C板',
                     'USB2UART',
                     '达妙USB2CAN',
                     'J-Link',
                     '排插']
        }  
    }
    for key, param in inserts.items():
            print(f"尝试给表 {param['table'].ljust(16)} 添加初值 {key}")

            # 查找父记录
            if param.get('father_table'):
                sql = "SELECT SQL_NO_CACHE * FROM {} WHERE name = %s".format(param['father_table'])
                cursor.execute(sql, (param['father_name']))
                father = cursor.fetchone()
                if not father:
                    print(f"父记录 {param['father_name'].ljust(16)} 未找到，跳过插入")
                    continue
            
            for value in param['value']:
                # 检查是否已经存在记录
                sql = "SELECT * FROM {} WHERE name = %s".format(param['table'])
                cursor.execute(sql, (value,))
                existing_record = cursor.fetchone()
                
                KeyTable = ''
                ValueTable = ''
                if not existing_record:
                    KeyTable = ', '.join(param['key'])
                    ValueTable = ', '.join(['%s'] * len(param['key']))
                    values = [value]
                    if param.get('father_table'):
                        KeyTable += ', father, id'
                        ValueTable += ', %s, %s'
                        values.append(father[0])

                        sql = "SELECT SQL_NO_CACHE * FROM {} WHERE father = %s".format(param['table'])
                        cursor.execute(sql, (father[0]))
                        result = cursor.fetchall()
                        new_id = (1000*father[0]) + (int(result[-1][0])%1000 + 1 if result else 1)
                        values.append(new_id)
                    sql = "INSERT INTO {} ({}) VALUES ({});".format(param['table'], KeyTable, ValueTable)
                    cursor.execute(sql, tuple(values))
                    print(f"\t已插入初值 {value}")
                    conn.commit()
                else:
                    print(f"\t初值 {value:<{16}}\t已存在，跳过")
    '''
            
    conn.commit()
    conn.close()

    print('数据库初始化成功')

    print('尝试从云端初始化数据库')
    init_from_feishu()
