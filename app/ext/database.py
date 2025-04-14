import hashlib
import logging
import sys
import time

from scripts.api.mysql_connector import MySql, sync_table, sync_triggers

logger = logging.getLogger(__name__)

class Database(MySql) :
    # 物资状态对应表,物资状态在数据库中是用int存储的
    useable_map = {
        1: '可用',
        0: '已借出',
        2: '维修中',
        3: '报废',
        4: '申请中',
        5: '未知'
    }

    def __init__(self, config : dict):
        """通过info数据初始化sql连接池"""
        host = config.get('host')
        port = config.get('port')
        user = config.get('user')
        password = config.get('password')
        try:
            super().__init__(host, port, user, password)
        except Exception as e:
            # 获取异常类型
            exception_type = type(e).__name__
            # 获取异常的错误码和错误信息
            error_code = e.args[0]  # 错误码
            error_message = e.args[1]  # 错误信息
            # 打印或处理异常信息
            logger.error(
                f"Create mysql connect error: \n\t"
                f"Exception Type: {exception_type}, \n\t"
                f"Error Code: {error_code}, \n\t"
                f"Error Message: {error_message}"
            )
            sys.exit("创建Mysql连接错误，请检查配置")
        self.db = config.get('db')
        super().set_default_db(self.db)

    def get_categories(self) -> dict:
        """
        获取仓库内所有物品种类
        
        Return:
            一个字典
            {b'id':  (1,2)    类型id,
             b'name':('裁判系统','电机') 类型名, 
             b'total':(10,19) 该类型下物资总数}
        """
        info = super().getall('item_category')
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
            info = super().fetchall('item_category', 'father', category_id)
            if not info:
                raise ValueError(f"{__name__}.get_category无法通过category_id:{category_id}找到目标类型")
        elif category_name:
            info = super().fetchall('item_category', 'name', category_name)
            if not info:
                raise ValueError(f"{__name__}.get_category无法通过category_name:{category_name}找到目标类型")
        else:
            raise ValueError(f"{__name__}.get_category缺少必要的参数")
        
        
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
            info = super().fetchall('item_list', 'father', int(category_id))
            if not info:
                raise ValueError(f"无法找到目标物品 category_id:{category_id}")
        elif category_name:
            category_id = self.get_category(category_name=category_name).get['id'][0]
            info = super().fetchall('item_list', 'father', int(category_id))
            if not info:
                raise ValueError(f"无法找到目标物品 category_name:{category_name}")
        elif name:
            info = super().fetchall_like('item_list', 'name', name)
            if not info:
                raise ValueError(f"无法找到目标物品 name:{name}")
        elif name_id:
            info = super().fetchall('item_list', 'id', name_id)
            if not info:
                raise ValueError(f"无法找到目标物品 name_id:{name_id}")
        else:
            raise ValueError(f"{__name__}.get_list 缺少必要的参数")
        
        
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
        groups = super().getall('item_category')
        for group in groups:
            name = group[1]
            d = super().fetchall('item_info', 'father', name[0])
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
        info = super().fetchone('item_info', 'id', oid)
        if info:
            father = super().fetchone('item_list', 'id', info[1])
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
                father = super().fetchone('item_list', 'name', name)
                if not father:
                    raise ValueError(f"无法找到目标物品 name:{name}")
            if name_id:
                father = super().fetchone('item_list', 'id', name_id)
                if not father:
                    raise ValueError(f"无法找到目标物品 name_id:{name_id}")
                
            name_id = father[0]
            name = father[2]

            info = super().fetchall('item_info', 'father', name_id)
            return self._return_itemTable_by_info(info, name=name)  if info else None

        elif user_id or user_name:
            if user_id and not user_name:
                user_name = self.get_member(user_id)['name']
            if not user_id:
                raise ValueError(f"无法找到目标用户 user_id:{user_id}")
            member_items = super().fetchall('item_info','wis',user_name)
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
            raise ValueError(f"{__name__}.get_items 缺少必要的参数")

    def add_member(self, user_id: str, user_name: str):
        """添加用户"""
        if not self.get_member(user_id):
            ins = {
                'user_id':user_id,
                'name': user_name
            }
            super().insert('members', ins)

    def add_member_batch(self, user_list: list):
        """批量添加用户"""
        for user in user_list:
            if not super().fetchone('members', 'user_id', user['user_id']):
                super().insert('members', user)

    def get_member(self, user_id: str | None = None, open_id:str | None = None) -> dict[str, list]:
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
        if user_id:
            member = super().fetchone('members', 'user_id', user_id)
        elif open_id:
            member = super().fetchone('members', 'open_id', open_id)
        if member:
            return {
                'user_id': member[0],
                'open_id': member[1],
                'union_id': member[2],
                'name': member[3],
                'root': member[4]
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
        members = super().fetchall('members', 'root', 1)
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
        super().update('members', ('user_id',user_id), {'root':1})

    def set_member_unroot(self, user_id: str):
        """取消某个用户的管理员权限"""
        super().update('members', ('user_id',user_id), {'root':0})

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
            father_recoder = super().fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = super().fetchone('item_list', 'name', name)
        else:
            raise ValueError("缺少必要的参数")
        
        if not father_recoder:
            if (category_name or category_id) and name:
                name_id = self.add_list(category_name=category_name, category_id=category_id, name=name, params=params)
            else:
                raise ValueError(f"父记录list Id:{name_id if name_id else category_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            name_id = father_recoder[0]

        self_recoder = super().fetchall('item_info', 'father', name_id)
        insert_data = {
            'id':0,
            'father':name_id
        }
        if not oid: #批量设置
            new_id = (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
            for i in range(int(num) if num else 1):
                # 设置Id，进行添加
                insert_data['id'] = name_id*1000 + i + new_id
                super().insert('item_info', insert_data)
            if num_broken:
                for i in range(num_broken):
                    super().update('item_info', ('id',i+new_id), {'useable':3})
        elif oid and wis and do:
            insert_data['id'] = name_id*1000 + int(oid)%1000
            insert_data['useable'] = next((key for key, value in self.useable_map.items() if value == useable), 5)
            insert_data['wis'] = wis
            insert_data['do'] = do
            super().insert('item_info', insert_data)

    def add_items_until_limit(
        self, 
        name_id: int | None = None, 
        num: int = 1, 
        name: str | None = None, 
        num_broken: int = 0,
        category_name: str | None = None, 
        category_id: int | None = None, 
    ):
        """
        添加一定量物品到数据库中，使总量大于等于设定值

        raise:
            ValueError: 传入参数不足以新建物品时抛出
        """
        if name_id:
            father_recoder = super().fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = super().fetchone('item_list', 'name', name)
        else:
            raise ValueError("缺少必要的参数")
        if father_recoder:
            num = num - father_recoder[3] if num - father_recoder[3] > 0 else 0
            num_broken = num_broken - father_recoder[5] if num_broken - father_recoder[5] > 0 else 0
        if num != 0:
            self.add_item(name_id,name,num,num_broken,category_name,category_id)

    def add_list(
        self, 
        name: str | None = None, 
        category_name: str | None = None, 
        category_id: int | None = None, 
        params: dict | None = None,
    ) -> int:
        """
        添加物品信息到数据库中
        
        Return:
            new_id: 新建的物品信息的id
        
        raise:
            ValueError: 传入参数不足以新建物品时抛出
        """
        if params:
            name = params.get('name')
            category_name = params.get('category_name')
            category_id = params.get('category_id')

        # 查找父记录
        if category_id:
            father_recoder = super().fetchone('item_category', 'id', category_id)
        elif category_name:
            father_recoder = super().fetchone('item_category', 'name', category_name)
        else:
            raise ValueError("缺少必要的参数")
        
        if not father_recoder:
            if  category_name:
                category_id = self.add_category(category_name)
            else:
                raise ValueError("父记录category %s 未找到，且缺少参数无法新建，跳过插入" %
                                 category_name if category_name else category_id)
        else:
            category_id = father_recoder[0]

        # 查找是否已存在
        self_recoder = super().fetchone('item_list', 'name', name)
        if self_recoder:
            logging.info("%s.add_list 尝试创建列表,但当前列表 %s 已存在" % (
                            __name__, name))
            return
        # 设置Id，进行添加
        self_recoder = super().fetchall('item_list', 'father', category_id)
        new_id = (1000*category_id) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        super().insert('item_list', {
            'id':new_id,
            'father':category_id,
            'name':name
        })
        return new_id #item_info`s father

    def add_category(
        self,
        category_name: str | None = None, 
        params: dict | None = None,
    ) -> int:
        """
        添加物品类型到数据库中
        
        Return:
            new_id: 新建的物品类型的id
        
        raise:
            ValueError: 传入参数不足以新建物品时抛出
        """
        if params:
            category_name = params.get('category_name')

        # 查找是否已存在
        self_recoder = super().fetchone('item_category', 'name', category_name)
        if self_recoder:
            print(f"当前类 {category_name} 已存在")
            return
        # 设置Id，进行添加
        self_recoder = super().getall('item_category')
        new_id = (int(self_recoder[-1][0]) + 1 if self_recoder else 1)
        super().insert('item_category', {
            'id':new_id,
            'name':category_name
        })
        return new_id

    def del_item(
        self, 
        id: int | None = None, 
        params: dict | None = None
    ):
        """
        删除物品对象

        Args:
            id: 物品对象oid
            params: 存储物品对象oid的字典
        """
        if params:
            id = params.get('id')

        super().delete('item_info','id',id)

    def del_list(
        self,
        name: str | None = None,
        id: int | None = None, 
        params: dict | None = None
    ):
        """
        删除物品信息

        Args:
            name: 物品名
            id: 物品信息id
            params: 存储上述参数的字典

        raise:
            ValueError: 缺少必要的参数时抛出

        TODO:删除父节点时同时删除所有子节点
        """
        if params:
            id = params.get('id')
            name = params.get('name')

        if not (name or id):
            raise ValueError("缺少必要的参数")
        if name:
            super().delete('item_list','name',name)
        elif id:
            super().delete('item_list','id',id)

    def del_category(
        self,
        name: str | None = None,
        id: int | None = None, 
        params: dict | None = None
    ):
        """
        删除物品类型

        Args:
            name: 类型名
            id: 物品类型id
            params: 存储上述参数的字典

        raise:
            ValueError: 缺少必要的参数时抛出

        TODO:删除父节点时同时删除所有子节点
        """
        if params:
            id = params.get('id')
            name = params.get('name')

        if not (name or id):
            raise ValueError("缺少必要的参数")
        if name:
            super().delete('item_category','name',name)
        elif id:
            super().delete('item_category','id',id)

    def del_all(self):
        """清除所有物品对象、信息、类型"""
        super().delete('item_info')
        super().delete('item_list')
        super().delete('item_category')

    def apply_item(
        self, 
        oid: int, 
        user_id: str, 
        do: str | None = None
    ):
        """
        对物品发出申请

        会在logs表中记录申请人，操作，操作对象，用途
        然后把物品状态修改为'审批中'

        Args:
            user_id: 申请人user_id
            oid:    申请的物品对象oid
            do:     申请用途
        """
        return self.set_item_state(oid=oid,operater_user_id=user_id,
                                   operation='APPLY',useable=4,do=do)
    
    def set_item_state(
        self, 
        oid: int, 
        operater_user_id: str | None = None, 
        operation: str | None = None,
        useable: int | None = None, 
        wis: str | None = None, 
        do: str | None = None
    ):
        """
        修改物品状态

        根据参数修改物品状态,并在logs表中记录

        Args:
            oid:    操作的物品对象oid
            operater_user_id: 操作者user_id
            operation:  操作者名称
            useable: 修改后新状态值,参考useable_map
            wis:    修改后的物品位置
            do:     备注
        """
        super().insert('logs', {'time':int(time.time()*1000),
                                 'userId':operater_user_id,
                                 'operation':operation,
                                 'object':oid,
                                 'do':do})
        update_date = {}
        update_date['useable'] = useable
        update_date['wis'] = wis
        super().update('item_info', ('id',oid), update_date)

    def return_item(
        self, 
        user_id: str, 
        oid: int
    ):
        """
        归还物品

        修改物品状态为可用,并在logs表中记录归还人

        Args:
            user_id: 归还人user_id
            oid:    归还的物品对象oid

        Return:
            操作结果
        """
        try:
            member = self.get_member(user_id)
            item_info = self.get_item(oid)
        except ValueError as e:
            return f"Error: {e}"
        if item_info['useable'][0] == '报废':
            return "Error: 它已经报废了，你真的要放进仓库吗"
        if item_info['useable'][0] == '申请中':
            return "Error: 该物品正在被申请，请先进行审批"
        if item_info['wis'][0] != member['name'] and not member['root']:
            return "Error: 你不是该物品的持有者"
        else:
            self.set_item_state(operater_user_id=user_id,operation='RETURN',
                                oid=oid,useable=1,wis='仓库',do='null')
            return f'你{"帮忙" if member["root"] else ""}归还了物品 {item_info["name"][0]} oid:{oid}'

    def update_card(
        self, 
        user_id: str, 
        message_id: str | None = None, 
        create_time: str | None = None
    ):
        """
        更新用户和对应的信息卡片信息

        Args:
            user_id: 用户user_id
            message_id: 消息卡片id
            create_time: 消息卡片创建时间
        """
        if message_id and create_time:
            super().update('members',('user_id',user_id),{   
                'card_message_id':message_id,'card_message_create_time':create_time})
        else:
            super().update('members',('user_id',user_id),{   
                'card_message_id':None,'card_message_create_time':None})
        
    def is_alive_card(self, user_id: str) -> str | None:
        """
        判断该用户的消息卡片是否可用

        Return:
            如可用,返回消息卡片id
            不可用,返回None
        """
        result = super().fetchone('members','user_id',user_id)
        return result[3] if (result and result[3] not in ('null',None) and
            time.time()-int(result[4])/1000<1036800) else None
    
    def is_user_root(self, user_id: str) -> bool:
        """判断用户是不是管理员"""
        result = super().fetchone('members','user_id',user_id)
        return result[2]==1
    
    def get_database_md5(self) -> str:
        """获取数据库的md5值"""
        table_list = super().gettable()
        table_checksum_list = []
        md5_hash = hashlib.md5()
        for table in table_list:
            table_checksum_list.append(str(super().getchecksum(table[0])[0][1]))
        combined_string = ''.join(table_checksum_list)
        md5_hash.update(combined_string.encode('utf-8'))
        return  md5_hash.hexdigest()

    def fetch_contact_md5(self) -> str | None:
        """获取数据库中存储的通讯录md5值"""
        result = super().fetchone('logs', 'do', 'used to detect changes in the contact.')
        return result[1] if result else None
    
    def update_contact_md5(self,contact_md5: str):
        """设置数据库中存储的通讯录md5值"""
        if not self.fetch_contact_md5():
            super().insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG',
                                     'do':'used to detect changes in the contact.'})
        super().update('logs',('do','used to detect changes in the contact.'),{'time':contact_md5})

    def fetch_itemSheet_md5(self) -> str:
        """获取数据库中存储的电子表格md5值"""
        result = super().fetchone('logs', 'do', 'used to detect changes in the spreadsheet.')
        return result[1] if result else None
    
    def update_itemSheet_md5(self,itemSheet_md5):
        """设置数据库中存储的电子表格md5值"""
        if not self.fetch_itemSheet_md5():
            super().insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG',
                                     'do':'used to detect changes in the spreadsheet.'})
        super().update('logs',('do','used to detect changes in the spreadsheet.'),{'time':itemSheet_md5})

def init_database(database : Database):
    """初始化数据库"""
    if not database.is_database_exists(database.db):
        database.create_database(database.db)
    database.set_default_db(database.db)
    """初始化表"""
    init_tables(database)
    """初始化触发器"""
    init_trigger(database)

def init_tables(database : Database):
    tables_config = {
        "logs": {
            "columns": [
                ("id", "int(255)", "AUTO_INCREMENT PRIMARY KEY"),
                ("time", "text", "NOT NULL"),
                ("userId", "text", "NOT NULL"),
                ("operation", "text", "NOT NULL"),
                ("object", "int(255)", "DEFAULT NULL"),
                ("do", "text", "")
            ],
            "foreign_keys": None,
            "options": "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        },
        "item_category": {
            "columns": [
                ("id", "int(6) UNSIGNED", "AUTO_INCREMENT PRIMARY KEY"),
                ("name", "text", "NOT NULL"),
                ("total", "int(11)", "NOT NULL DEFAULT 0")
            ],
            "foreign_keys": None,
            "options": "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        },
        "item_list": {
            "columns": [
                ("id", "int(10) UNSIGNED", "NOT NULL PRIMARY KEY"),
                ("father", "int(255) UNSIGNED", "NOT NULL"),
                ("name", "text", "NOT NULL"),
                ("total", "int(6)", "NOT NULL DEFAULT 0"),
                ("free", "int(6)", "NOT NULL DEFAULT 0"),
                ("broken", "int(6)", "NOT NULL DEFAULT 0")
            ],
            "foreign_keys": None,
            "options": "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        },
        "item_info": {
            "columns": [
                ("id", "int(10) UNSIGNED", "NOT NULL PRIMARY KEY"),
                ("father", "int(255) UNSIGNED", "NOT NULL"),
                ("useable", "int(2)", "NOT NULL DEFAULT 1"),
                ("wis", "text", ""),
                ("do", "text", ""),
                ("purpose", "text", "")
            ],
            "foreign_keys": [
                {
                    "columns": ["father"],
                    "ref_table": "item_list",
                    "ref_columns": ["id"],
                    "on_update": "CASCADE"
                }
            ],
            "options": "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        },
        "members": {
            "columns": [
                ("user_id", "text", ""),
                ("open_id", "text", ""),
                ("union_id", "text", ""),
                ("name", "text", "NOT NULL"),
                ("root", "int(1)", "NOT NULL DEFAULT 0"),
                ("card_message_id", "text", ""),
                ("card_message_create_time", "text", "")
            ],
            "foreign_keys": None,
            "options": "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        }
    }
    conn = database.get_connection()
    for table_name, config in tables_config.items():
        sync_table(
            cursor=conn.cursor(),
            table_name=table_name,
            column_defs=config["columns"],
            foreign_keys=config["foreign_keys"],
            table_options=config["options"]
        )
    conn.commit()

def init_trigger(database : Database):
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
    conn = database.get_connection()
    sync_triggers(conn.cursor(), triggers)
    conn.commit()