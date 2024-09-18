import pymysql
import time

class MySqlError(Exception):
    def __init__(self, arg):
        self.args = arg


class MySql:
    def __init__(self, Info):
        self.Info = Info
        self.connect()
        self.__cursor = self.__db.cursor()

    def connect(self):
        attempt = 0
        retries = 10
        # 尝试连接MySQL，失败时自动重试，直到最大重试次数。
        while attempt < retries:
            try:
                self.__db = pymysql.connect(host=self.Info['host'], user=self.Info['user'], passwd=self.Info['password'], db=self.Info['db'],
                                    port=int(self.Info['port']), charset='utf8')
                print('连接mysql数据库成功')
                break
            except pymysql.MySQLError as e:
                print(f'连接mysql数据库失败，尝试重连 {attempt}/{retries}，错误原因：{e}')
                attempt += 1
                time.sleep(1)
        # 如果达到最大尝试次数后仍未成功连接，则结束程序
        if attempt == retries:
            raise Exception("无法连接到MySQL，超过最大重试次数。")

    def refresh(self):
        try:
            self.__db.ping()
        except:
            print('SQL error, try to reconnect')
            self.__cursor.close()
            self.__db.close()
            self.connect()
            self.__cursor = self.__db.cursor()

    def fetchone(self, table, key, value):
        self.refresh()
        if isinstance(value, str):
            value = "'%s'" % value
        else:
            value = str(value)
        sql = "SELECT SQL_NO_CACHE * from %s WHERE %s = %s" % (table, key, value)
        self.__cursor.execute(sql)
        result = self.__cursor.fetchone()
        if result is not None:
            return result
        else:
            return None

    def fetchall(self, table, key, value):
        self.refresh()
        if isinstance(value, str):
            value = "'%s'" % value
        else:
            value = str(value)
        sql = "SELECT SQL_NO_CACHE * from %s WHERE %s = %s" % (table, key, value)
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchall()
            return result
        except Exception as e:
            raise MySqlError("Error happen when get date !")

    def getall(self, table):
        self.refresh()
        sql = "SELECT * from %s" % table
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchall()
            return result
        except:
            raise MySqlError("Error happen when get date !")

    def insert(self, table, data):
        self.refresh()
        KeyTable = ''
        ValueTable = ''
        for key, value in data.items():
            if isinstance(value, str):
                value = "'%s'" % value
            else:
                value = str(value)
            if value == '\'\'' or value is None or value == 'None':
                value = 'NULL'
            KeyTable += key + ', '
            ValueTable += value + ', '
        sql = "INSERT INTO %s" \
              "(%s) " \
              "VALUES" \
              "(%s);" % (table, KeyTable[:-2], ValueTable[:-2])

        self.__cursor.execute(sql)

    def update(self, table, key, updates):
        """
        更新表中的多个字段。

        :param table: 表名
        :param key: 用于查找记录的键，格式为 (key_column, key_value)
        :param updates: 更新字段及其新值的字典，例如 {'column1': 'new_value1', 'column2': 'new_value2'}
        """
        self.refresh()
        # 处理更新的字段
        set_clause = []
        for col, val in updates.items():
            if isinstance(val, str):
                val = "'%s'" % val
            else:
                val = str(val)
            if val == "''" or val is None or val == 'None':
                val = 'NULL'
            set_clause.append(f"{col} = {val}")
        set_clause_str = ', '.join(set_clause)
        
        # 处理WHERE子句
        key_col, key_val = key
        if isinstance(key_val, str):
            key_val = "'%s'" % key_val
        else:
            key_val = str(key_val)
        if key_val == "''" or key_val is None or key_val == 'None':
            key_val = 'NULL'
        sql = f"UPDATE {table} SET {set_clause_str} WHERE {key_col} = {key_val}"
        self.__cursor.execute(sql)

    def remove(self, table, key, value):
        self.refresh()
        if isinstance(value, str):
            value = "'%s'" % value
        else:
            value = str(value)
        sql = "DELETE FROM %s WHERE %s = %s" % (table, key, value)
        self.__cursor.execute(sql)

    def commit(self):
        try:
            self.__db.commit()
        except:
            self.__db.rollback()
            self.__db.commit()
            raise MySqlError("Error happen when remove date !")

    def __del__(self):
        self.__cursor.close()
        self.__db.close()
