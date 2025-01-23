import logging
import pymysql
from functools import wraps
from dbutils.pooled_db import PooledDB

logger = logging.getLogger(__name__)

def _log_errors(func):
    """记录异常的装饰器."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper

class MySql:
    """基于pymysql和Dbutils的Mysql连接池类."""
    def __init__(self, host, port, user, password, default_db = None):
        logger.info(f"Connecting to MySQL server at {host}:{port} with user {user}")
        # 创建连接池
        self.pool = PooledDB(
            creator=pymysql,  # 使用 PyMySQL 连接
            maxconnections=5,     # 连接池最大连接数
            mincached=2,          # 初始化时，连接池中至少创建的空闲连接数
            maxcached=5,          # 连接池中最多空闲连接数
            maxshared=3,          # 连接池中最多共享连接数
            blocking=True,        # 连接池中如果没有可用连接后是否阻塞
            host=host, 
            port=int(port), 
            user=user, 
            passwd=password, 
            charset='utf8'
        )
        self.default_db = default_db
    
    def set_default_db(self, db):
        """设置默认数据库."""
        self.default_db = db
        
    def get_connection(self, db = None):
        """获取指定数据库的连接."""
        conn = self.pool.connection()
        conn.cursor().execute(f"USE {db or self.default_db};")
        return conn

    @_log_errors
    def create_database(self, database_name):
        """
        创建数据库
        """
        sql = f"CREATE DATABASE IF NOT EXISTS `{database_name}`;"
        with self.pool.connection().cursor() as cursor:
            cursor.execute(sql)
    
    @_log_errors
    def is_database_exists(self, database_name):
        """
        检查数据库是否已经存在
        """
        sql = "SHOW DATABASES LIKE %s;"
        with self.pool.connection().cursor() as cursor:
            cursor.execute(sql, (database_name,))
            result = cursor.fetchone()
            return result is not None
            
    @_log_errors
    def is_table_exists(self, table_name, db = None):
        """
        检查表是否已经存在
        """
        sql = "SHOW TABLES LIKE %s;"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (table_name,))
            result = cursor.fetchone()
            return result is not None
            
    @_log_errors
    def is_trigger_exists(self, trigger_name, db = None):
        """
        检查触发器是否已经存在
        """
        sql = "SELECT * FROM information_schema.TRIGGERS WHERE TRIGGER_NAME = %s;" 
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (trigger_name,))
            result = cursor.fetchone()
            return result is not None

    @_log_errors
    def fetchone(self, table: str, key: str, value: str | int, db: str = None) -> list:
        """获取一条数据(精确搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (value,))
            return cursor.fetchone()

    @_log_errors
    def fetchone_like(self, table: str, key: str, value: str | int, db: str = None) -> list:
        """获取一条数据(模糊搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} LIKE %s"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (f"%{value}%",))
            return cursor.fetchone()

    @_log_errors
    def fetchall(self, table: str, key: str, value: str | int, db: str = None) -> list:
        """获取多条数据(精确搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} = %s"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (value,))
            return cursor.fetchall()

    @_log_errors
    def fetchall_like(self, table: str, key: str, value: str | int, db: str = None) -> list:
        """获取多条数据(模糊搜索)."""
        sql = f"SELECT SQL_NO_CACHE * FROM {table} WHERE {key} LIKE %s"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql, (f"%{value}%",))
            return cursor.fetchall()

    @_log_errors
    def gettable(self, db: str = None) -> list:
        """获取当前数据库中的所有表."""
        with self.get_connection(db).cursor() as cursor:
            cursor.execute("SHOW TABLES")
            return cursor.fetchall()

    @_log_errors
    def getall(self, table: str, db: str = None) -> list:
        """获取表table的全部数据."""
        sql = f"SELECT * FROM {table}"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

    @_log_errors
    def insert(self, table: str, data: dict, db: str = None) -> None:
        """向表table插入数据data."""
        keys = data.keys()
        values = tuple(data.values())

        KeyTable = ', '.join(keys)
        ValueTable = ', '.join(['%s'] * len(keys))

        sql = f"INSERT INTO {table} ({KeyTable}) VALUES ({ValueTable})"
        with self.get_connection(db) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, values)
                conn.commit()

    @_log_errors
    def update(self, table: str, key: tuple, updates: dict, db: str = None) -> None:
        """
        更新表中的多个字段.

        Args:
            table: 表名
            key: 用于查找记录的键，格式为 (key_column, key_value)
            updates: 更新字段及其新值的字典，例如 {'column1': 'new_value1', 'column2': 'new_value2'}
        """
        # 处理更新的字段，使用占位符
        set_clause = ', '.join([f"{col} = %s" for col in updates.keys()])
        # 处理 WHERE 子句
        key_col, key_val = key

        sql = f"UPDATE {table} SET {set_clause} WHERE {key_col} = %s"
        
        # 将更新字段的值和 key_val 一起作为参数传递给 execute
        values = list(updates.values()) + [key_val]
        with self.get_connection(db) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, values)
                conn.commit()

    @_log_errors
    def delete(self, table: str, key: tuple = None, value=None, db: str = None) -> None:
        """
        删除表中数据.
        
        Args:
            table: 表名
            key: 用于查找记录的键，格式为 (key_column, key_value)
            value: 用于查找记录的值
        """
        with self.get_connection(db) as conn:
            with conn.cursor() as cursor:
                if key and value:
                    sql = f"DELETE FROM {table} WHERE {key} = %s"
                    cursor.execute(sql, (value,))
                else:
                    sql = f"DELETE FROM {table}"
                    cursor.execute(sql)
                conn.commit()

    @_log_errors
    def getchecksum(self, table: str, db: str = None) -> list:
        """获取表table的校验和."""
        sql = f"CHECKSUM TABLE {table}"
        with self.get_connection(db).cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

    def __del__(self):
        """清理连接池."""
        if self.pool:
            self.pool.close()

class SQLException(Exception):
    """自定义异常."""
    
    def __init__(self, code=0, msg=None):
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return "{}:{}".format(self.code, self.msg)

    __repr__ = __str__