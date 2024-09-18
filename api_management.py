import api_mysql

class ApiManagement(object):
    def __init__(self, sql):
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
    
    def return_itemTable_by_info(self, info):
        r = {'oid': [], 'useable': [], 'wis': [], 'do': []}
        for it in info:
            r['oid'].append(it[0])
            if it[2] == 1:
                r['useable'].append('是')
            elif it[2] == 0:
                r['useable'].append('已借出')
            elif it[2] == 2:
                r['useable'].append('维修中')
            elif it[2] == 3:
                r['useable'].append('已报废')
            elif it[2] == 4:
                r['useable'].append('申请中')
            r['wis'].append(it[3])
            if it[4] is None or it[4] == '' or it[4] == 'None':
                r['do'].append('无')
            # elif len(it[4]) > 20:
            #     r['备注'].append(it[4][:20] + '...')
            else:
                r['do'].append(it[4])
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

    def add_member(self, user_id, user_name):
        print(self.sql.fetchone('members', 'user_id', user_id),flush=True)
        if not self.sql.fetchone('members', 'user_id', user_id):
            print('a')
            ins = {
                'user_id':user_id,
                'name': user_name
            }
            self.sql.insert('members', ins)
            self.sql.commit()
            print('add done')