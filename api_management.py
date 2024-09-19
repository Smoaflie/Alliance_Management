import api_mysql

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
        r = {'name': name, 'id': [], 'father': [], 'useable': [], 'wis': [], 'do': []}
        
        useable_map = {
            1: '可用',
            0: '已借出',
            2: '维修中',
            3: '报废',
            4: '申请中'
        }
        
        for it in info:
            if isinstance(it, (list,tuple)):
                r['id'].append(it[0])   # 如果是可迭代对象，取第一个元素
                r['father'].append(it[1])
                r['useable'].append(useable_map.get(it[2], '未知'))
                r['wis'].append(info[3] if info[3] not in (None, '', 'None') else '未知')  
                r['do'].append(it[4] if it[4] not in (None, '', 'None') else '无')
            else:
                r['id']=(info[0])  # 否则直接添加
                r['father'].append(info[1])
                r['useable'].append(useable_map.get(info[2], '未知'))
                r['wis'].append(info[3] if info[3] not in (None, '', 'None') else '未知')  
                r['do'].append(info[4] if info[4] not in (None, '', 'None') else '无')  
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
        return self.return_itemTable_by_info(info)

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
        if not self.sql.fetchone('members', 'user_id', user_id):
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

    def add_item(self, father=None, num=1, father_name=None, num_bad=None, category_name=None, category_id=None):
        # 查找父记录
        if father:
            father_recoder = self.sql.fetchone('item_list', 'id', father)
        elif father_name:
            father_recoder = self.sql.fetchone('item_list', 'name', father_name)
        else:
            raise Exception("缺少必要的参数")
        
        if not father_recoder:
            if (category_name or category_id) and father_name:
                father = self.add_list(father_name=category_name, father=category_id, name=father_name)
            else:
                raise Exception(f"父记录list Id:{father if father else father_name} 未找到，且缺少参数无法新建，跳过插入")
        else:
            father = father_recoder[0]

        self_recoder = self.sql.fetchall('item_info', 'father', father)
        new_id = (1000*father) + (int(self_recoder[-1][0])%1000 + 1 if self_recoder else 1)
        for i in range(num):
            # 设置Id，进行添加
            self.sql.insert('item_info', {
                'id':new_id+i,
                'father':father,
            })
        if num_bad:
            for i in range(num_bad):
                self.sql.update('item_info', ('id',i+new_id), {'useable':3})
        self.sql.commit()

    def add_items_until_limit(self, father=None, num=1, father_name=None, num_bad=None, category_name=None, category_id=None):
        if father:
            father_recoder = self.sql.fetchone('item_list', 'id', father)
        elif father_name:
            father_recoder = self.sql.fetchone('item_list', 'name', father_name)
        else:
            raise Exception("缺少必要的参数")
        if father_recoder:
            num = father_recoder[3] - num if father_recoder[3] - num > 0 else 0
            num_bad = father_recoder[3] - father_recoder[5]
        self.add_item(father,num,father_name,num_bad,category_name,category_id)


    def add_list(self, father=None, father_name=None, name=None):
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

    def add_category(self, name):
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
        return new_id