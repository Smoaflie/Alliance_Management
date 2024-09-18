import pymysql
import ujson
import time

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

    # 定义所有需要创建的表
    print("正在创建表")
    tables = {
        # logs 用于存储审批记录，这个表比较混乱 
            # `id` 申请ID  
            # `time` 申请提交时间  
            # `openid` 提交人openid  
            # `operation` 操作类型  
            # `object` 操作对象  
            # `name` 提交人
            # `num` 操作数目  
            # `do` 备注  
            # `verify` 审批状态(0为不需要审核,1为通过,2为退回,3为待审
            # `wis` 位置  
            # `approver` 审批人
        'logs': '''CREATE TABLE `logs` (
          `id` int(255) AUTO_INCREMENT PRIMARY KEY,
          `time` text NOT NULL,
          `openid` text NOT NULL,
          `operation` text NOT NULL,
          `object` int(255) DEFAULT NULL,
          `name` text,
          `num` int(11) DEFAULT NULL,
          `do` text,
          `verify` int(255) DEFAULT NULL,
          `wis` text,
          `approver` text
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
          `free` int(6) NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  存储物资详细信息  
            # `id` 11位对象ID，前6位为对应物品ID
            # `father` 对应物品ID  
            # `useable` 是否可用    1可用，0已借出，2维修中，3报废，4申请中
            # `wis` 当前位置  
            # `do` 备注
        'item_info': '''CREATE TABLE `item_info` (
          `id` int(10) UNSIGNED NOT NULL PRIMARY KEY,
          `father` int(255) UNSIGNED NOT NULL,
          `useable` int(2) NOT NULL DEFAULT 1,
          `wis` text NOT NULL,
          `do` text,
          FOREIGN KEY (father) REFERENCES item_list(id)
          ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''',
        #  存储成员信息  
            # `id` 索引
            # `user_id` 飞书user_id  
            # `name` 实名
            # `root` 管理 1是0否   
        'members': '''CREATE TABLE `members` (
          `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `user_id` text NOT NULL,
          `name` text NOT NULL,
          `root` int(1) NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;'''
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
                    free = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 1)
                WHERE id = NEW.father;

                UPDATE item_category
                SET total = (SELECT SUM(total) FROM item_list WHERE father = NEW.father)
                WHERE id = NEW.father;
            END;
        ''',
        'update_item_total_free_on_delete': '''
            CREATE TRIGGER update_item_total_free_on_delete
            AFTER DELETE ON item_info
            FOR EACH ROW
            BEGIN
                UPDATE item_list
                SET total = (SELECT COUNT(*) FROM item_info WHERE father = OLD.father),
                    free = (SELECT COUNT(*) FROM item_info WHERE father = OLD.father AND useable = 1)
                WHERE id = OLD.father;

                UPDATE item_category
                SET total = (SELECT SUM(total) FROM item_list WHERE father = OLD.father)
                WHERE id = OLD.father;
            END;
        ''',
        'update_item_total_free_after_update': '''
            CREATE TRIGGER update_item_total_free_after_update
            AFTER UPDATE ON item_info
            FOR EACH ROW
            BEGIN
                UPDATE item_list
                SET total = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father),
                    free = (SELECT COUNT(*) FROM item_info WHERE father = NEW.father AND useable = 1)
                WHERE id = NEW.father;

                UPDATE item_category
                SET total = (SELECT SUM(total) FROM item_list WHERE father = NEW.father)
                WHERE id = NEW.father;
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
    inserts = {
        'item_category': '''
        INSERT INTO item_category(`name`)
        VALUES 
            ('裁判系统'),
            ('电机'),
            ('机械物资'),
            ('其他');
        ''',
        'item_list_referee': '''
        INSERT INTO item_list (`id`, `father`, `name`)
        VALUES 
            ('001001', '1', '主控模块'),
            ('001002', '1', '电源管理'),
            ('001003', '1', '灯条模块'),
            ('001004', '1', '装甲模块'),
            ('001005', '1', '测速模块'),
            ('001006', '1', '场地交互模块'),
            ('001007', '1', '相机图传模块'),
            ('001008', '1', '定位模块'),
            ('001009', '1', '超级电容管理模块'),
            ('001010', '1', '飞镖触发装置'),
            ('001011', '1', '图传接收端'),
            ('001012', '1', '图传供电器'),
            ('001013', '1', '官方航空线');
        ''',
        'item_list_motor': '''
        INSERT INTO item_list (`id`, `father`, `name`)
        VALUES 
            ('002001', '2', 'DJI_3508电机'),
            ('002002', '2', 'DJI_6020电机'),
            ('002003', '2', 'DJI_2006电机');
        ''',
        'item_list_mechanical': '''
        INSERT INTO item_list (`id`, `father`, `name`)
        VALUES 
            ('003001', '3', 'M3螺丝刀'),
            ('003002', '3', 'M2.5螺丝刀'),
            ('003003', '3', 'M4螺丝刀'),
            ('003004', '3', 'M2螺丝刀'),
            ('003005', '3', '剪刀'),
            ('003006', '3', '水口钳');
        ''',
        'item_list_consumable': '''
        INSERT INTO item_list (`id`, `father`, `name`)
        VALUES 
            ('004001', '4', '打印料-PLA-白'),
            ('004002', '4', '打印料-PLA-灰'),
            ('004003', '4', 'micro数据线'),
            ('004004', '4', 'typeC数据线'),
            ('004005', '4', '电池架'),
            ('004006', '4', '达妙板子'),
            ('004007', '4', 'C板'),
            ('004008', '4', 'USB2UART'),
            ('004009', '4', '达妙USB2CAN'),
            ('004010', '4', 'J-Link'),
            ('004011', '4', '排插');
        '''        
    }
    for table_name, create_sql in inserts.items():
            cursor.execute(create_sql)
            print(f"已插入初值{table_name}")
    conn.commit()

    conn.close()

    print('数据库初始化成功')


