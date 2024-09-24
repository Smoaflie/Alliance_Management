import pymysql
import time
from pymysql import OperationalError

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
        except OperationalError:
            print('SQL error, trying to reconnect')
            if self.__cursor is not None:
                self.__cursor.close()
            if self.__db is not None:
                self.__db.close()
            self.connect()
            self.__cursor = self.__db.cursor()
        except Exception as e:
            print(f"Unexpected error during refresh: {e}")

    def fetchone(self, table, key, value):
        self.refresh()
        sql = f"SELECT SQL_NO_CACHE * from {table} WHERE {key} = %s"
        try:
            self.__cursor.execute(sql,(value,))
            result = self.__cursor.fetchone()
            return result
        except Exception as e:
            raise Exception(f"Error occurred while fetching data: {e}")

    def fetchall(self, table, key, value):
        self.refresh()

        sql = f"SELECT SQL_NO_CACHE * from {table} WHERE {key} = %s"
        try:
            self.__cursor.execute(sql,(value,))
            result = self.__cursor.fetchall()
            return result
        except Exception as e:
            raise Exception(f"Error occurred while fetching data: {e}")

    def gettable(self):
        self.refresh()
        sql = "SHOW TABLES"
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchall()
            return result
        except Exception as e:
            raise Exception(f"Error occurred while show tables: {str(e)}") from e
        
    def getall(self, table):
        self.refresh()
        sql = "SELECT * from %s" % table
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchall()
            return result
        except Exception as e:
            raise Exception(f"Error occurred while fetching data: {str(e)}") from e

    def insert(self, table, data):
        self.refresh()
        keys = data.keys()
        values = tuple(data.values())

        KeyTable = ', '.join(keys)
        ValueTable = ', '.join(['%s'] * len(keys))

        sql = f"INSERT INTO {table} ({KeyTable}) VALUES ({ValueTable})"
        self.__cursor.execute(sql,values)

    def update(self, table, key, updates):
        """
        更新表中的多个字段。

        :param table: 表名
        :param key: 用于查找记录的键，格式为 (key_column, key_value)
        :param updates: 更新字段及其新值的字典，例如 {'column1': 'new_value1', 'column2': 'new_value2'}
        """
        self.refresh()
        # 处理更新的字段，使用占位符
        set_clause = ', '.join([f"{col} = %s" for col in updates.keys()])
        # 处理 WHERE 子句
        key_col, key_val = key

        sql = f"UPDATE {table} SET {set_clause} WHERE {key_col} = %s"
        
        # 将更新字段的值和 key_val 一起作为参数传递给 execute
        values = list(updates.values()) + [key_val]
        self.__cursor.execute(sql, values)


    def delete(self, table, key, value):
        self.refresh()
        sql = f"DELETE FROM {table} WHERE {key} = %s"
        self.__cursor.execute(sql,(value,))
        

    def commit(self):
        try:
            self.__db.commit()
        except:
            self.__db.rollback()
            self.__db.commit()
            raise MySqlError("Error happen when delete date !")

    def getchecksum(self, table):
        self.refresh()
        sql = f"CHECKSUM TABLE {table}"
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchall()
            return result
        except Exception as e:
            raise Exception(f"Error occurred while get checksum: {str(e)}") from e

    def __del__(self):
        self.__cursor.close()
        self.__db.close()