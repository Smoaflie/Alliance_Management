from . import api_mysql 
import hashlib
import ujson
import time

'''
TODO:测试下所有接口对错误类型的输入会不会产生错误
'''

class ApiManagement(object):
    def __init__(self, sql : api_mysql.MySql):
        self.sql = sql

    
    def get_category(self):
        info = self.sql.getall('item_category')
        r = {'id': [], 'name': [], 'total': []}
        for it in info:
            r['id'].append(it[0])
            r['name'].append(it[1])
            r['total'].append(it[2])
        return r
    
    def get_list(self, father):
        info = self.sql.fetchall('item_list', 'father', int(father))
        r = {'id': [], 'father': [], 'name': [], 'total': [], 'free': []}
        for it in info:
            r['id'].append(it[0])
            r['father'].append(it[1])
            r['name'].append(it[2])
            r['total'].append(it[3])
            r['free'].append(it[4])
        return r
    
    def return_itemTable_by_info(self, info, name=None):
        r = {'name': [], 'id': [], 'father': [], 'useable': [], 'wis': [], 'do': []}
        
        useable_map = {
            1: '可用',
            0: '已借出',
            2: '维修中',
            3: '报废',
            4: '申请中'
        }
        
        for it in info:
            r['name'].append(name)
            if isinstance(it, (list,tuple)):
                r['id'].append(it[0])   # 如果是可迭代对象，取第一个元素
                r['father'].append(it[1])
                r['useable'].append(useable_map.get(it[2], '未知'))
                r['wis'].append(it[3] if it[3] not in ('null', None, '', 'None') else '未知')  
                r['do'].append(it[4] if it[4] not in ('null', None, '', 'None') else '无')
            else:
                r['id'] = info[0]  # 否则直接添加
                r['father'] = info[1]
                r['useable'] = useable_map.get(info[2], '未知')
                r['wis'] = info[3] if info[3] not in ('null', None, '', 'None') else '未知'
                r['do'] = info[4] if info[4] not in ('null', None, '', 'None') else '无'
                break
        return r
    
    def get_all(self):
        info = []
        groups = self.sql.getall('item_category')
        for group in groups:
            name = group[1]
            d = self.sql.fetchall('item_info', 'father', name[0])
            for it in d:
                if it not in info:
                    info.append(it)
        return self.return_itemTable_by_info(info)

    def get_item(self, oid):
        info = self.sql.fetchone('item_info', 'id', int(oid))
        father = self.sql.fetchone('item_list', 'id', info[1])
        return self.return_itemTable_by_info(info, father[2])

    def get_items(self, father=None, father_name=None):
        if not (father or father_name):
            raise Exception("参数错误")
        if father_name:
            father = self.sql.fetchone('item_list', 'name', father_name)
        else:
            father = self.sql.fetchone('item_list', 'id', father)
        father_id = father[0]
        item_name = father[2]

        info = self.sql.fetchall('item_info', 'father', int(father_id))
        return self.return_itemTable_by_info(info, name=item_name)
    
    def add_member(self, user_id, user_name):
        if not self.get_member(user_id):
            ins = {
                'user_id':user_id,
                'name': user_name
            }
            self.sql.insert('members', ins)
            self.sql.commit()
    def add_member_batch(self, user_list):
        for user in user_list:
            if not self.sql.fetchone('members', 'user_id', user['user_id']):
                self.sql.insert('members', user)
        self.sql.commit()

    def get_member(self, user_id):
        member = self.sql.fetchone('members', 'user_id', user_id)
        if member:
            return {
                'user_id': member[0],
                'name': member[1],
                'root': member[2]
            }
        else:
            return None
        
    #TODO:统一变量名，便于使用params进行配置
    def add_item(self, father=None, num=1, father_name=None, num_broken=None,\
                  category_name=None, category_id=None, params=None):
        if params:
            father = params.get['father']
            num = params.get['num']
            father_name = params.get['father_name']
            num_broken = params.get['num_broken']
            category_name = params.get['category_name']
            category_id = params.get['category_id']
        # 查找父记录
        #TODO：无法添加同名物品到不同分类            
        if father:
            father_recoder = self.sql.fetchone('item_list', 'id', father)
        elif father_name:
            father_recoder = self.sql.fetchone('item_list', 'name', father_name)
        else:
            raise Exception("缺少必要的参数")
        
        if not father_recoder:
            if (category_name or category_id) and father_name:
                father = self.add_list(father_name=category_name, father=category_id, name=father_name)
                print(category_name)
            else:
                raise Exception(f"父记录list Id:{father if father else father_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            father = father_recoder[0]

        self_recoder = self.sql.fetchall('item_info', 'father', father)
        new_id = (1000*father) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        for i in range(num if num else 1):
            # 设置Id，进行添加
            self.sql.insert('item_info', {
                'id':new_id+i,
                'father':father,
            })
        if num_broken:
            for i in range(num_broken):
                self.sql.update('item_info', ('id',i+new_id), {'useable':3})
        self.sql.commit()

    def add_items_until_limit(self, father=None, num=1, father_name=None, num_broken=None, category_name=None, category_id=None):
        if father:
            father_recoder = self.sql.fetchone('item_list', 'id', father)
        elif father_name:
            father_recoder = self.sql.fetchone('item_list', 'name', father_name)
        else:
            raise Exception("缺少必要的参数")
        if father_recoder:
            num = father_recoder[3] - num if father_recoder[3] - num > 0 else 0
            num_broken = father_recoder[3] - father_recoder[5]
        self.add_item(father,num,father_name,num_broken,category_name,category_id)


    def add_list(self, father=None, father_name=None, name=None, params=None):
        if params:
            father = params.get['father']
            father_name = params.get['father_name']
            name = params.get['name']
        # 查找父记录
        if father:
            father_recoder = self.sql.fetchone('item_category', 'id', father)
        elif father_name:
            father_recoder = self.sql.fetchone('item_category', 'name', father_name)
        else:
            raise Exception("缺少必要的参数")
        
        if not father_recoder:
            if  father_name:
                father = self.add_category(father_name)
            else:
                raise Exception(f"父记录category Id:{father if father else father_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            father = father_recoder[0]

        # 查找是否已存在
        self_recoder = self.sql.fetchone('item_list', 'name', name)
        if self_recoder:
            print(f"当前列表 {name} 已存在")
            return
        # 设置Id，进行添加
        self_recoder = self.sql.fetchall('item_list', 'father', father)
        new_id = (1000*father) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        self.sql.insert('item_list', {
            'id':new_id,
            'father':father,
            'name':name
        })
        self.sql.commit()
        return new_id #item_info`s father

    def add_category(self, name, params=None):
        if params:
            name = params.get['name']

        # 查找是否已存在
        self_recoder = self.sql.fetchone('item_category', 'name', name)
        if self_recoder:
            print(f"当前类 {name} 已存在")
            return
        # 设置Id，进行添加
        self_recoder = self.sql.getall('item_category')
        new_id = (int(self_recoder[-1][0]) + 1 if self_recoder else 1)
        self.sql.insert('item_category', {
            'id':new_id,
            'name':name
        })
        self.sql.commit()
        return new_id

    #TODO:删除父节点时同时删除所有子节点
    def del_item(self, id, params=None):
        if params:
            id = params.get['id']

        self.sql.delete('item_info','id',id)
        self.sql.commit()

    def del_list(self,name=None,id=None,params=None):
        if params:
            id = params.get['id']
            name = params.get['name']

        if not (name or id):
            raise Exception("缺少必要的参数")
        if name:
            self.sql.delete('item_list','name',name)
        elif id:
            self.sql.delete('item_list','id',id)
        self.sql.commit()

    def del_category(self,name=None,id=None, params=None):
        if params:
            id = params.get['id']
            name = params.get['name']

        if not (name or id):
            raise Exception("缺少必要的参数")
        if name:
            self.sql.delete('item_category','name',name)
        elif id:
            self.sql.delete('item_category','id',id)
        self.sql.commit()

    def apply_item(self, user_id, oid, user_name=None, do=None):
        user_name = user_name if user_name else (self.get_member(user_id).get('name') if self.get_member(user_id) is not None else "")
        item_info = self.get_item(oid)
        do = item_info['do'] + do if do else item_info['do']
        print({
            'time':int(time.time()),
            'userId':user_id,
            'operation':'APPLY',
            'object':oid,
            'userName':user_name,
        })
        self.sql.insert('logs', {'time':int(time.time()),
                                 'userId':user_id,
                                 'operation':'APPLY',
                                 'object':oid,
                                 'userName':user_name,
                                 })
        self.sql.update('item_info', ('id',oid), 
                        {'useable':4,
                        'wis':user_name,
                        'do':do})
        self.sql.commit()

    def get_md5(self):
        table_list = self.sql.gettable()
        table_checksum_list = []
        md5_hash = hashlib.md5()
        for table in table_list:
            table_checksum_list.append(str(self.sql.getchecksum(table[0])[0][1]))
        combined_string = ''.join(table_checksum_list)
        md5_hash.update(combined_string.encode('utf-8'))
        return  md5_hash.hexdigest()