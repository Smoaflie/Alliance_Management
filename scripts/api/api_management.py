from . import api_mysql 
import hashlib
import ujson
import time
import logging

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
    
    def get_list(self, category_id):
        info = self.sql.fetchall('item_list', 'father', int(category_id))
        if not info:
            raise Exception(f"无法找到目标物品 category_id:{category_id}")
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
        return self.return_itemTable_by_info(info) if info else None

    def get_item(self, oid):
        info = self.sql.fetchone('item_info', 'id', int(oid))
        if info:
            father = self.sql.fetchone('item_list', 'id', info[1])
            return self.return_itemTable_by_info(info, father[2])
        else:
            raise Exception(f"无法找到目标物品 oid:{str(oid)}") if info else None

    def get_items(self, name_id=None, name=None):
        if not (name_id or name):
            raise Exception("参数错误")
        if name:
            father = self.sql.fetchone_like('item_list', 'name', name)
        else:
            father = self.sql.fetchone('item_list', 'id', int(name_id))
        
        if not father:
            if name:
                raise Exception(f"无法找到目标物品 name:{name}")
            if name_id:
                raise Exception(f"无法找到目标物品 name_id:{name_id}")

        name_id = father[0]
        name = father[2]

        info = self.sql.fetchall('item_info', 'father', int(name_id))
        return self.return_itemTable_by_info(info, name=name)  if info else None
    
    def get_member_items(self, user_id=None, user_name=None):
        if not user_name:
            if user_id:
                user_name = self.get_member(user_id)['name']
            else:
                logging.error(f'缺少参数')
            
        member_items = self.sql.fetchall('item_info','wis',user_name)

        if not member_items:
            return None
        
        name_id_map = {}
        member_items_out = {'oid':[], 'name':[], 'do':[]} 
        for item in member_items:
            oid     = item[0]
            name_id = str(item[1])
            do      = item[4]

            if name_id not in name_id_map:
                item_list = self.get_list(int(oid/1000000))
                for name_id_,name_ in zip(item_list['id'],item_list['name']):
                    name_id_map[f'{name_id_}']=name_
        
            name = name_id_map[name_id]

            member_items_out['oid'].append(oid)
            member_items_out['name'].append(name)
            member_items_out['do'].append(do)
        
        return member_items_out


    def add_member(self, user_id, user_name):
        if not self.get_member(user_id):
            ins = {
                'user_id':user_id,
                'name': user_name
            }
            self.sql.insert('members', ins)
    def add_member_batch(self, user_list):
        for user in user_list:
            if not self.sql.fetchone('members', 'user_id', user['user_id']):
                self.sql.insert('members', user)

    def get_member(self, user_id):
        member = self.sql.fetchone('members', 'user_id', user_id)
        if member:
            return {
                'user_id': member[0],
                'name': member[1],
                'root': member[2]
            }
        else:
            raise Exception(f"无法找到目标用户 user_id:{user_id}")
    
    def get_members_root(self):
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
        
    def set_member_root(self, user_id):
        self.sql.update('members', ('user_id',user_id), {'root':1})

    def set_member_unroot(self, user_id):
        self.sql.update('members', ('user_id',user_id), {'root':0})

    def add_item(self, name_id=None, name=None,  \
                  num=1, num_broken=None,\
                  category_name=None, category_id=None, params=None):
        if params:
            name_id = params.get('name_id')
            num = params.get('num')
            name = params.get('name')
            num_broken = params.get('num_broken')
            category_name = params.get('category_name')
            category_id = params.get('category_id')

        # 查找父记录
        #TODO：无法添加同名物品到不同分类            
        if name_id:
            father_recoder = self.sql.fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = self.sql.fetchone('item_list', 'name', name)
        else:
            raise Exception("缺少必要的参数")
        
        if not father_recoder:
            if (category_name or category_id) and name:
                name_id = self.add_list(category_name=category_name, category_id=category_id, name=name, params=params)
            else:
                raise Exception(f"父记录list Id:{name_id if name_id else category_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            name_id = father_recoder[0]

        self_recoder = self.sql.fetchall('item_info', 'father', name_id)
        new_id = (1000*name_id) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        for i in range(int(num) if num else 1):
            # 设置Id，进行添加
            self.sql.insert('item_info', {
                'id':new_id+i,
                'father':name_id,
            })
        if num_broken:
            for i in range(num_broken):
                self.sql.update('item_info', ('id',i+new_id), {'useable':3})

    def add_items_until_limit(self, name_id=None, num=1, name=None, num_broken=None, category_name=None, category_id=None):
        if name_id:
            father_recoder = self.sql.fetchone('item_list', 'id', name_id)
        elif name:
            father_recoder = self.sql.fetchone('item_list', 'name', name)
        else:
            raise Exception("缺少必要的参数")
        if father_recoder:
            num = num - father_recoder[3] if num - father_recoder[3] > 0 else 0
            num_broken = num_broken - father_recoder[5] if num_broken - father_recoder[5] > 0 else 0
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

    def apply_item(self, user_id, oid, do=None):
        item_info = self.get_item(oid)
        if item_info['useable'] != '可用':
            return 'error'
        
        do = item_info['do'] + do if do else item_info['do']

        self.sql.insert('logs', {'time':int(time.time()*1000),
                                 'userId':user_id,
                                 'operation':'APPLY',
                                 'object':oid,
                                 })
        self.sql.update('item_info', ('id',oid), 
                        {'useable':4,
                        'do':do})
        return 'success'
    
    def set_item_state(self, operater_user_id=None, operation=None,\
                        oid=None, useable=None, wis=None, do=None):
        self.sql.insert('logs', {'time':int(time.time()*1000),
                                 'userId':operater_user_id,
                                 'operation':operation,
                                 'object':oid,
                                 })
        self.sql.update('item_info', ('id',oid), 
                        {'useable':useable,
                        'wis':wis,
                        'do':do})

    def return_item(self, user_id, oid):
        try:
            member = self.get_member(user_id)
            item_info = self.get_item(oid)
        except Exception as e:
            return f"Error: {e}"
        
        if item_info['useable'] == '报废':
            return "Error: 它已经报废了，你真的要放进仓库吗"
        if item_info['useable'] == '申请中':
            return "Error: 该物品正在被申请，请先进行审批"
        if item_info['wis'] != member['name'] and not member['root']:
            return "Error: 你不是该物品的持有者"
        else:
            self.set_item_state(operater_user_id=user_id,operation='RETURN',\
                                oid=oid,useable=1,wis='仓库',do='null')
            return f'你{"帮忙" if member['root'] else ""}归还了物品 {item_info['name']} oid:{oid}'

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
        return result[1]
    
    def update_contact_md5(self,contact_md5):
        if not self.fetch_contact_md5():
            self.sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the contact.'})
        self.sql.update('logs',('do','used to detect changes in the contact.'),{'time':contact_md5})

    def fetch_itemSheet_md5(self):
        result = self.sql.fetchone('logs', 'do', 'used to detect changes in the spreadsheet.')
        return result[1]
    
    def update_itemSheet_md5(self,itemSheet_md5):
        if not self.fetch_itemSheet_md5():
            self.sql.insert('logs',{'time':'0', 'userId':'0', 'operation':'CONFIG', 'do':'used to detect changes in the spreadsheet.'})
        self.sql.update('logs',('do','used to detect changes in the spreadsheet.'),{'time':itemSheet_md5})
    
    