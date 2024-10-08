import hashlib
import logging
import time

from scripts.api import api_mysql_connector

class ApiManagement(object):
    """物资数据库操作的接口类"""
    # 物资状态对应表,物资状态在数据库中是用int存储的
    useable_map = {
        1: '可用',
        0: '已借出',
        2: '维修中',
        3: '报废',
        4: '申请中',
        5: '未知'
    }
    
    def __init__(self, info : dict):
        """通过info数据初始化sql连接池"""
        self.sql = api_mysql_connector.MySql(info)

    
    def get_categories(self) -> dict:
        """
        获取仓库内所有物品种类
        
        Return:
            一个字典
            {b'id':  (1,2)    类型id,
             b'name':('裁判系统','电机') 类型名, 
             b'total':(10,19) 该类型下物资总数}
        """
        info = self.sql.getall('item_category')
        r = {'id': [], 'name': [], 'total': []}
        for it in info:
            r['id'].append(it[0])
            r['name'].append(it[1])
            r['total'].append(it[2])
        return r
    
    def get_category(
            self,
            category_id: int | None = None, 
            category_name: str | None = None, 
        ) -> dict[str, list]:
        """
        获取仓库内符合条件的物品种类
        
        Args:
            category_id: 物品类型id
            category_name: 物品类型名,精确搜索

        Return:
            {b'id':  (1,2)    类型id,
             b'name':('裁判系统','电机') 类型名, 
             b'total':(10,19) 该类型下物资总数}

        raise:
            ValueError: 缺少必要参数或无法根据条件找到类型时raise
        """
        if category_id:
            info = self.sql.fetchall('item_category', 'father', category_id)
            if not info:
                raise ValueError(f"{__name__}无法通过category_id:{category_id}找到目标类型")
        elif category_name:
            info = self.sql.fetchall('item_category', 'name', category_name)
            if not info:
                raise ValueError(f"{__name__}无法通过category_name:{category_name}找到目标类型")
        else:
            raise ValueError(f"{__name__}缺少必要的参数")
        
        
        r = {'id': [], 'name': [], 'total': []}
        for it in info:
            r['id'].append(it[0])
            r['name'].append(it[1])
            r['total'].append(it[2])
        return r
    
    def get_list(
            self, 
            category_id: int | None = None, 
            category_name: str | None = None, 
            name: str | None = None, 
            name_id: int | None = None
        ) -> dict[str, list]:
        """
        获取仓库内符合要求的物品信息(简略)
        
        Args:
            category_id: 物品类型id
            category_name: 物品类型名,精确搜索
            name: 物品名
            name_id: 物品名id
        
        Return:
            {
                b'id':  (1001,1002)    物品名id
                b'father': (1,1)   父类型id
                b'name':('小装甲板','大装甲板') 物品名 
                b'total':(10,19) 该物品名下物品总数
                b'free':(10,19) 该物品名下可用的物品总数
            }

        raise:
            ValueError: 缺少必要参数或无法根据条件找到物品信息时raise
        """
        if category_id:
            info = self.sql.fetchall('item_list', 'father', int(category_id))
            if not info:
                raise ValueError(f"无法找到目标物品 category_id:{category_id}")
        elif category_name:
            category_id = self.get_category(category_name=category_name).get['id'][0]
            info = self.sql.fetchall('item_list', 'father', int(category_id))
            if not info:
                raise ValueError(f"无法找到目标物品 category_name:{category_name}")
        elif name:
            info = self.sql.fetchall_like('item_list', 'name', name)
            if not info:
                raise ValueError(f"无法找到目标物品 name:{name}")
        elif name_id:
            info = self.sql.fetchall('item_list', 'id', name_id)
            if not info:
                raise ValueError(f"无法找到目标物品 name_id:{name_id}")
        else:
            raise ValueError(f"{__name__} 缺少必要的参数")
        
        
        r = {'id': [], 'father': [], 'name': [], 'total': [], 'free': []}
        for it in info:
            r['id'].append(it[0])
            r['father'].append(it[1])
            r['name'].append(it[2])
            r['total'].append(it[3])
            r['free'].append(it[4])
        return r
    
    def _return_itemTable_by_info(
            self, 
            info: list, 
            name: str | None = None
        ) -> dict[str,list] :
        """
        将物品详细信息格式化成统一格式

        由于物品详细信息的表中没有存物品名的列，输出字典中['name']默认为空
            如果有需要，需手动设置 name值
        
        Args:
            info: mysql返回的存有物品详细信息的列表
            name: 手动设置物品名
        
        Return:
            {
                'name': 物品名
                'id':   物品id
                'father': 物品名id
                'useable': 物品状态，具体内容参考`useable_map`
                'wis': 物品当前位置
                'do': 物品备注，标示该物品的特点(比如'CAN口损坏'的主控板)
            }
        """
        r = {'name': [], 'id': [], 'father': [], 'useable': [], 'wis': [], 'do': []}
        
        

        for it in info:
            r['name'].append(name)
            if isinstance(it, (list,tuple)):
                r['id'].append(it[0])   # 如果是可迭代对象，取第一个元素
                r['father'].append(it[1])
                r['useable'].append(self.useable_map.get(it[2], '未知'))
                r['wis'].append(it[3] if it[3] not in ('null', None, '', 'None') else '未知')  
                r['do'].append(it[4] if it[4] not in ('null', None, '', 'None') else '无')
            else:
                r['id'].append(info[0])  # 否则直接添加
                r['father'].append(info[1])
                r['useable'].append(self.useable_map.get(info[2], '未知'))
                r['wis'].append(info[3] if info[3] not in ('null', None, '', 'None') else '未知')
                r['do'].append(info[4] if info[4] not in ('null', None, '', 'None') else '无')
                break
        return r
    
    def get_all(self):
        """
        获取数据库内的全部物资信息(详情)

        Return:
            {
                'name': None
                'id':   物品id
                'father': 物品名id
                'useable': 物品状态，具体内容参考`useable_map`
                'wis': 物品当前位置
                'do': 物品备注，标示该物品的特点(比如'CAN口损坏'的主控板)
            }
        """
        info = []
        groups = self.sql.getall('item_category')
        for group in groups:
            name = group[1]
            d = self.sql.fetchall('item_info', 'father', name[0])
            for it in d:
                if it not in info:
                    info.append(it)
        return self._return_itemTable_by_info(info) if info else None

    def get_item(self, oid: int) -> dict[str, list]:
        """
        获取某个物品的详细信息
        
        Args:
            oid:    物品id
        
        Return:
            {
                'name': 物品名
                'id':   物品id
                'father': 物品名id
                'useable': 物品状态，具体内容参考`useable_map`
                'wis': 物品当前位置
                'do': 物品备注，标示该物品的特点(比如'CAN口损坏'的主控板)
            }
        
        raise:
            ValueError: 无法找到对应oid的物品时抛出
        """
        info = self.sql.fetchone('item_info', 'id', oid)
        if info:
            father = self.sql.fetchone('item_list', 'id', info[1])
            return self._return_itemTable_by_info(info, father[2])
        else:
            raise ValueError(f"无法找到目标物品 oid:{str(oid)}") if info else None

    def get_items(
            self, 
            name_id: int | None = None, 
            name: str | None = None,
            user_id: str | None = None,
            user_name: str | None = None
        ) -> dict[str, list]:
        """
        获取符合条件的物品的详细信息
        
        Args:
            name_id:    物品名id
            name:   物品名
            user_id: 持有者user_id
            user_name: 持有者用户名
        
        Return:
            {
                'name': 物品名
                'id':   物品id
                'father': 物品名id
                'useable': 物品状态，具体内容参考`useable_map`
                'wis': 物品当前位置
                'do': 物品备注，标示该物品的特点(比如'CAN口损坏'的主控板)
            }
        
        raise:
            ValueError: 缺少参数或无法根据条件找到目标物品时抛出
        """
        if name or name_id:
            if name:
                father = self.sql.fetchone('item_list', 'name', name)
                if not father:
                    raise ValueError(f"无法找到目标物品 name:{name}")
            if name_id:
                father = self.sql.fetchone('item_list', 'id', name_id)
                if not father:
                    raise ValueError(f"无法找到目标物品 name_id:{name_id}")
                
            name_id = father[0]
            name = father[2]

            info = self.sql.fetchall('item_info', 'father', name_id)
            return self._return_itemTable_by_info(info, name=name)  if info else None

        elif user_id or user_name:
            if user_id and not user_name:
                user_name = self.get_member(user_id)['name']
            if not user_id:
                raise ValueError(f"无法找到目标用户 user_id:{user_id}")
            member_items = self.sql.fetchall('item_info','wis',user_name)
            if not member_items:
                raise ValueError(f"无法找到名下物品 user_name:{user_name}")
            name_id_map = {}
            member_items_out = {'name': [], 'id': [], 'father': [], 'useable': [], 'wis': [], 'do': []}
            for item in member_items:
                oid     = item[0]
                name_id = str(item[1])

                if name_id not in name_id_map:
                    item_list = self.get_list(int(oid/1000000))
                    for name_id_,name_ in zip(item_list['id'],item_list['name']):
                        name_id_map[f'{name_id_}']=name_
                name = name_id_map[name_id]

                member_items_out['name'].append(name)
                member_items_out['id'].append(oid)
                member_items_out['father'].append(str(item[1]))
                member_items_out['useable'].append(self.useable_map.get(item[2], '未知'))
                member_items_out['wis'].append(item[3])
                member_items_out['do'].append(item[4])
            
            return member_items_out
        else:
            raise ValueError(f"{__name__}缺少必要的参数")

    def add_member(self, user_id: str, user_name: str):
        """添加用户"""
        if not self.get_member(user_id):
            ins = {
                'user_id':user_id,
                'name': user_name
            }
            self.sql.insert('members', ins)
    def add_member_batch(self, user_list: list):
        """批量添加用户"""
        for user in user_list:
            if not self.sql.fetchone('members', 'user_id', user['user_id']):
                self.sql.insert('members', user)

    def get_member(self, user_id: str) -> dict[str, list]:
        """"
        获取用户信息

        Return:
            {
                'user_id': 用户user_id
                'name':    用户名
                'root':    是否有管理员权限(int 0:无 1:有)
            }
        
        raise:
            ValueError: 无法找到目标用户时抛出
        """
        member = self.sql.fetchone('members', 'user_id', user_id)
        if member:
            return {
                'user_id': member[0],
                'name': member[1],
                'root': member[2]
            }
        else:
            raise ValueError(f"无法找到目标用户 user_id:{user_id}")
    
    def get_members_root(self) -> dict[str, list]:
        """"
        获取所有管理员用户信息

        Return:
            {
                'user_id': 用户user_id
                'name':    用户名
                'root':    是否有管理员权限(int 0:无 1:有)
            }
        """
        members = self.sql.fetchall('members', 'root', 1)
        result = []
        if members:
            for member in members:
                result.append({
                    'user_id': member[0],
                    'name': member[1],
                    'root': member[2]
                })
        return result
        
    def set_member_root(self, user_id: str):
        """设置某个用户为管理员"""
        self.sql.update('members', ('user_id',user_id), {'root':1})

    def set_member_unroot(self, user_id: str):
        """取消某个用户的管理员权限"""
        self.sql.update('members', ('user_id',user_id), {'root':0})

    def add_item(
            self, 
            name_id: int | None = None, 
            name: str | None = None, 
            num: int = 1, 
            num_broken: int = 0,
            category_name: str | None = None, 
            category_id: int | None = None, 
            params: dict | None = None,
            oid: int | None = None,
            useable: int | None = None,
            wis: str | None = None,
            do: str | None = None
        ):
        """
        添加物品到数据库中

        会根据传入参数尝试新建物品，如果父级不存在，会尝试新建父级

        Args:
            name_id:    物品名id
            name:   物品名
            num:    添加数量
            num_broken: 添加的物品中损坏数量(<num)
            category_name: 物品类型名
            category_id:    物品类型id
            params: 参数表，一个存储了上方参数的字典
            oid:    物品oid,可以用于指定物品id
            useable: 物品状态,参照useable_map,默认未知
            wis:    物品位置，默认未知
            do:     物品备注,默认无

        raise:
            ValueError: 传入参数不足以新建物品时抛出
        """
        if params:
            name_id = params.get('name_id')
            num = params.get('num')
            name = params.get('name')
            num_broken = params.get('num_broken')
            category_name = params.get('category_name')
            category_id = params.get('category_id')

        # 查找父记录
        #TODO:无法添加同名物品到不同分类            
        if name_id:
            father_recoder = self.sql.fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = self.sql.fetchone('item_list', 'name', name)
        else:
            raise ValueError("缺少必要的参数")
        
        if not father_recoder:
            if (category_name or category_id) and name:
                name_id = self.add_list(category_name=category_name, category_id=category_id, name=name, params=params)
            else:
                raise ValueError(f"父记录list Id:{name_id if name_id else category_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            name_id = father_recoder[0]

        self_recoder = self.sql.fetchall('item_info', 'father', name_id)
        insert_data = {
            'id':0,
            'father':name_id
        }
        if not oid: #批量设置
            new_id = (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
            for i in range(int(num) if num else 1):
                # 设置Id，进行添加
                insert_data['id'] = name_id*1000 + i + new_id
                self.sql.insert('item_info', insert_data)
            if num_broken:
                for i in range(num_broken):
                    self.sql.update('item_info', ('id',i+new_id), {'useable':3})
        elif oid and wis and do:
            insert_data['id'] = name_id*1000 + int(oid)%1000
            insert_data['useable'] = next((key for key, value in self.useable_map.items() if value == useable), 5)
            insert_data['wis'] = wis
            insert_data['do'] = do
            self.sql.insert('item_info', insert_data)

    def add_items_until_limit(self, name_id=None, num=1, name=None, num_broken=None, category_name=None, category_id=None):
        """
        """
        if name_id:
            father_recoder = self.sql.fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = self.sql.fetchone('item_list', 'name', name)
        else:
            raise ValueError("缺少必要的参数")
        if father_recoder:
            num = num - father_recoder[3] if num - father_recoder[3] > 0 else 0
            num_broken = num_broken - father_recoder[5] if num_broken - father_recoder[5] > 0 else 0
        if num != 0:
            self.add_item(name_id,name,num,num_broken,category_name,category_id)


    def add_list(self, name=None, category_name=None, category_id=None, params=None):
        if params:
            name = params.get('name')
            category_name = params.get('category_name')
            category_id = params.get('category_id')

        # 查找父记录
        if category_id:
            father_recoder = self.sql.fetchone('item_category', 'id', category_id)
        elif category_name:
            father_recoder = self.sql.fetchone('item_category', 'name', category_name)
        else:
            raise Exception("缺少必要的参数")
        
        if not father_recoder:
            if  category_name:
                category_id = self.add_category(category_name)
            else:
                raise Exception(f"父记录category {category_name if category_name else category_id} 未找到，且缺少参数无法新建，跳过插入")
        else:
            category_id = father_recoder[0]

        # 查找是否已存在
        self_recoder = self.sql.fetchone('item_list', 'name', name)
        if self_recoder:
            print(f"当前列表 {name} 已存在")
            return
        # 设置Id，进行添加
        self_recoder = self.sql.fetchall('item_list', 'father', category_id)
        new_id = (1000*category_id) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        self.sql.insert('item_list', {
            'id':new_id,
            'father':category_id,
            'name':name
        })
        return new_id #item_info`s father

    def add_category(self, category_name=None, params=None):
        if params:
            category_name = params.get('category_name')

        # 查找是否已存在
        self_recoder = self.sql.fetchone('item_category', 'name', category_name)
        if self_recoder:
            print(f"当前类 {category_name} 已存在")
            return
        # 设置Id，进行添加
        self_recoder = self.sql.getall('item_category')
        new_id = (int(self_recoder[-1][0]) + 1 if self_recoder else 1)
        self.sql.insert('item_category', {
            'id':new_id,
            'name':category_name
        })
        return new_id

    #TODO:删除父节点时同时删除所有子节点
    def del_item(self, id=None, params=None):
        if params:
            id = params.get('id')

        self.sql.delete('item_info','id',id)

    def del_list(self,name=None,id=None,params=None):
        if params:
            id = params.get('id')
            name = params.get('name')

        if not (name or id):
            raise Exception("缺少必要的参数")
        if name:
            self.sql.delete('item_list','name',name)
        elif id:
            self.sql.delete('item_list','id',id)

    def del_category(self,name=None,id=None, params=None):
        if params:
            id = params.get('id')
            name = params.get('name')

        if not (name or id):
            raise Exception("缺少必要的参数")
        if name:
            self.sql.delete('item_category','name',name)
        elif id:
            self.sql.delete('item_category','id',id)

    def del_all(self):
        self.sql.delete('item_info')
        self.sql.delete('item_list')
        self.sql.delete('item_category')

    def apply_item(self, user_id, oid, do=None):
        # item_info = self.get_item(oid)
        # if item_info['useable'][0] != '可用':
        #     raise Exception (f'Error while {user_id} apply_item {oid} for {do}')
        
        return self.set_item_state(user_id,'APPLY',oid,4,do=do)
    
    def set_item_state(self, operater_user_id=None, operation=None,\
                        oid=None, useable=None, wis=None, do=None):
        self.sql.insert('logs', {'time':int(time.time()*1000),
                                 'userId':operater_user_id,
                                 'operation':operation,
                                 'object':oid,
                                 'do':do})
        update_date = {}
        update_date['useable'] = useable
        update_date['wis'] = wis
        self.sql.update('item_info', ('id',oid), update_date)
        return 'success'

    def return_item(self, user_id, oid):
        try:
            member = self.get_member(user_id)
            item_info = self.get_item(oid)
        except Exception as e:
            return f"Error: {e}"
        if item_info['useable'][0] == '报废':
            return "Error: 它已经报废了，你真的要放进仓库吗"
        if item_info['useable'][0] == '申请中':
            return "Error: 该物品正在被申请，请先进行审批"
        if item_info['wis'][0] != member['name'] and not member['root']:
            return "Error: 你不是该物品的持有者"
        else:
            self.set_item_state(operater_user_id=user_id,operation='RETURN',\
                                oid=oid,useable=1,wis='仓库',do='null')
            return f'你{"帮忙" if member['root'] else ""}归还了物品 {item_info['name'][0]} oid:{oid}'

    def update_card(self, user_id, message_id=None, create_time=None): #更新用户和对应的信息卡片信息
        if message_id and create_time:
            result = self.sql.update('members',('user_id',user_id),{   \
                'card_message_id':message_id,'card_message_create_time':create_time})
        else:
            result = self.sql.update('members',('user_id',user_id),{   \
                'card_message_id':None,'card_message_create_time':None})
        
        return result
        
    def is_alive_card(self, user_id):
        result = self.sql.fetchone('members','user_id',user_id)
        return result[3] if (result and result[3] not in ('null',None) and \
            time.time()-int(result[4])/1000<1036800) else None
    
    def is_user_root(self, user_id):
        result = self.sql.fetchone('members','user_id',user_id)
        return result[2]==1
    
    def get_database_md5(self):
        table_list = self.sql.gettable()
        table_checksum_list = []
        md5_hash = hashlib.md5()
        for table in table_list:
            table_checksum_list.append(str(self.sql.getchecksum(table[0])[0][1]))
        combined_string = ''.join(table_checksum_list)
        md5_hash.update(combined_string.encode('utf-8'))
        return  md5_hash.hexdigest()
    
    def fetch_request(self,event_id):
        return self.sql.fetchone('requests','event_id',event_id)
 
    def insert_request(self,event_id,create_time):
        return self.sql.insert('requests',{'event_id':event_id,'create_time':create_time})
    
    def clean_requests(self):
        return self.sql.delete("requests")

    def fetch_contact_md5(self):
        result = self.sql.fetchone('logs', 'do', 'used to detect changes in the contact.')
        return result[1] if result else None
    
    def update_contact_md5(self,contact_md5):
        if not self.fetch_contact_md5():
            self.sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the contact.'})
        self.sql.update('logs',('do','used to detect changes in the contact.'),{'time':contact_md5})

    def fetch_itemSheet_md5(self):
        result = self.sql.fetchone('logs', 'do', 'used to detect changes in the spreadsheet.')
        return result[1] if result else None
    
    def update_itemSheet_md5(self,itemSheet_md5):
        if not self.fetch_itemSheet_md5():
            self.sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the spreadsheet.'})
        self.sql.update('logs',('do','used to detect changes in the spreadsheet.'),{'time':itemSheet_md5})
    
    