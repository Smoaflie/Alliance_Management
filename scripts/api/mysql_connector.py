import logging
import pymysql

from functools import wraps
from dbutils.pooled_db import PooledDB

def log_errors(func):
    """记录异常的装饰器."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper

class MySql:
    """基于pymysql和Dbutils的Mysql连接池类."""

    def __init__(self, info):
        """通过info配置初始化Mysql实例."""
        self.info = info
        # 创建连接池
        self.pool = PooledDB(
            creator=pymysql,  # 使用 PyMySQL 连接
            maxconnections=5,     # 连接池最大连接数
            mincached=2,          # 初始化时，连接池中至少创建的空闲连接数
            maxcached=5,          # 连接池中最多空闲连接数
            maxshared=3,          # 连接池中最多共享连接数
            blocking=True,        # 连接池中如果没有可用连接后是否阻塞
            host=self.info['host'], 
            user=self.info['user'], 
            passwd=self.info['password'], 
            db=self.info['db'],
            port=int(self.info['port']), 
            charset='utf8'
        )

    @log_errors
    def fetchone(self, table: str, key: str, value: str) -> list:
        """获取一条数据(精确搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(value,))
                return cursor.fetchone()
        
    @log_errors
    def fetchone_like(self, table: str, key: str, value: str) -> list:
        """获取一条数据(模糊搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} LIKE %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(f"%{value}%",))
                return cursor.fetchone()
            
    @log_errors
    def fetchall(self, table: str, key: str, value: str) -> list:
        """获取多条数据(精确搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(value,))
                return cursor.fetchall()
            
    @log_errors
    def fetchall_like(self, table: str, key: str, value: str) -> list:
        """获取多条数据(模糊搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} LIKE %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql,(f"%{value}%",))
                return cursor.fetchall()

    @log_errors
    def gettable(self) -> list:
        """获取当前数据库中的所有表."""
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                return cursor.fetchall()
        
    @log_errors
    def getall(self, table: str) -> list:
        """获取表table的全部数据."""
        sql = f"SELECT * FROM {table}"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()

    @log_errors
    def insert(self, table: str, data: dict) -> None:
        """向表table插入数据data."""
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
    def update(
        self,
        table: str,
        key: tuple,
        updates: dict
    ) -> None:
        """
        更新表中的多个字段.

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
    def delete(
        self,
        table: str,
        key: tuple = None,
        value=None
    ) -> None:
        """删除表中数据."""
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
    def getchecksum(self, table: str) -> list:
        """获取表table的校验和."""
        sql = f"CHECKSUM TABLE {table}"
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()
        
    def __del__(self):
        """清理连接池."""
        if self.pool:
            self.pool.close() 