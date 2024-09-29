import pymysql
import logging
from functools import wraps
from dbutils.pooled_db import PooledDB

class MySqlError(Exception):
    def __init__(self, arg):
        self.args = arg

def log_errors(func): #使用装饰器来记录异常
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper

class MySql:
    def __init__(self, Info):
        self.Info = Info
        # 创建连接池
        self.pool = PooledDB(
            creator=pymysql,  # 使用 PyMySQL 连接
            maxconnections=5,     # 连接池最大连接数
            mincached=2,          # 初始化时，连接池中至少创建的空闲连接数
            maxcached=5,          # 连接池中最多空闲连接数
            maxshared=3,          # 连接池中最多共享连接数
            blocking=True,        # 连接池中如果没有可用连接后是否阻塞
            host=self.Info['host'], 
            user=self.Info['user'], 
            passwd=self.Info['password'], 
            db=self.Info['db'],
            port=int(self.Info['port']), 
            charset='utf8'
        )

    @log_errors
    def fetchone(self, table, key, value):
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(value,))
                return cursor.fetchone()
        
    @log_errors
    def fetchall(self, table, key, value):
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(value,))
                return cursor.fetchall()

    @log_errors
    def gettable(self):
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                return cursor.fetchall()
        
    @log_errors
    def getall(self, table):
        sql = "SELECT * from %s" % table
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()

    @log_errors
    def insert(self, table, data):
        keys = data.keys()
        values = tuple(data.values())

        KeyTable = ', '.join(keys)
        ValueTable = ', '.join(['%s'] * len(keys))

        sql = f"INSERT INTO {table} ({KeyTable}) VALUES ({ValueTable})"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,values)
                conn.commit()

    @log_errors
    def update(self, table, key, updates):
        """
        更新表中的多个字段。

        :param table: 表名
        :param key: 用于查找记录的键，格式为 (key_column, key_value)
        :param updates: 更新字段及其新值的字典，例如 {'column1': 'new_value1', 'column2': 'new_value2'}
        """
        # 处理更新的字段，使用占位符
        set_clause = ', '.join([f"{col} = %s" for col in updates.keys()])
        # 处理 WHERE 子句
        key_col, key_val = key

        sql = f"UPDATE {table} SET {set_clause} WHERE {key_col} = %s"
        
        # 将更新字段的值和 key_val 一起作为参数传递给 execute
        values = list(updates.values()) + [key_val]
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, values)
                conn.commit()
        
    @log_errors
    def delete(self, table, key=None, value=None):
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                if key and value:
                    sql = f"DELETE FROM {table} WHERE {key} = %s"
                    cursor.execute(sql,(value,))
                else:
                    sql = f"DELETE FROM {table}"
                    cursor.execute(sql)
                conn.commit()
    
    @log_errors
    def getchecksum(self, table):
        sql = f"CHECKSUM TABLE {table}"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()
        
    def __del__(self):
        if self.pool:
            self.pool.close()  # 清理连接池