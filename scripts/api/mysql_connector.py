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
    def create_table(self, table_name, db = None):
        """
        创建表
        """
        sql = f"CREATE TABLE IF NOT EXISTS `{table_name}`;"
        with self.get_connection(db).cursor() as cursor:
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
        if hasattr(self, 'pool'):
            self.pool.close()

class SQLException(Exception):
    """自定义异常."""
    
    def __init__(self, code=0, msg=None):
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return "{}:{}".format(self.code, self.msg)

    __repr__ = __str__

def sync_table(cursor, table_name, column_defs, foreign_keys=None, table_options="ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"):
    """
    同步MySQL表结构

    :param cursor: MySQL连接cursor对象
    :param table_name: 需要同步的表名
    :param column_defs: 列定义列表，例如：
        [
            ("id", "INT", "AUTO_INCREMENT PRIMARY KEY"),
            ("name", "VARCHAR(255)", "NOT NULL"),
            ("created_at", "TIMESTAMP", "DEFAULT CURRENT_TIMESTAMP")
        ]
    :param foreign_keys: 外键定义列表，例如：
        [
            {
                "columns": ["father"],
                "ref_table": "item_list",
                "ref_columns": ["id"],
                "on_update": "CASCADE",
                "on_delete": "NO ACTION"
            }
        ]
    """
    # 检查表是否存在
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        # 为防止元数据残留问题，先 DROP 表（DROP TABLE IF EXISTS 也适用于不存在的情况）
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        
        # 创建新表
        columns = []
        pk_columns = []
        for col in column_defs:
            col_name, col_type, col_extra = col
            # 判断是否包含 PRIMARY KEY
            if "PRIMARY KEY" in col_extra.upper():
                # 移除PRIMARY KEY关键字，后续单独定义主键
                clean_extra = col_extra.upper().replace("PRIMARY KEY", "").strip()
                columns.append(f"`{col_name}` {col_type} {clean_extra}".strip())
                pk_columns.append(f"`{col_name}`")
            else:
                columns.append(f"`{col_name}` {col_type} {col_extra}".strip())
        if pk_columns:
            # 统一添加主键约束
            columns.append(f"PRIMARY KEY ({', '.join(pk_columns)})")
        # 添加外键
        if foreign_keys:
            for fk in foreign_keys:
                fk_sql = (
                    f"FOREIGN KEY (`{'`,`'.join(fk['columns'])}`) REFERENCES `{fk['ref_table']}` "
                    f"(`{'`,`'.join(fk['ref_columns'])}`) ON UPDATE {fk.get('on_update', 'NO ACTION')} "
                    f"ON DELETE {fk.get('on_delete', 'NO ACTION')}"
                )
                columns.append(fk_sql)
        create_sql = f"CREATE TABLE `{table_name}` (\n  {',\n  '.join(columns)}\n) {table_options}"
        cursor.execute(create_sql)
        logger.info(f"新增表 {table_name} 成功")
        return

    # 表存在，进行同步操作

    # 获取现有列信息
    cursor.execute(f"""
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' AND table_schema = DATABASE()
    """)
    existing_columns = {row[0]: {
        "type": row[1].lower(),
        "nullable": row[2] == "YES",
        "default": row[3],
        "extra": row[4].lower()
    } for row in cursor.fetchall()}

    # 获取现有主键
    cursor.execute(f"""
        SELECT COLUMN_NAME 
        FROM information_schema.key_column_usage 
        WHERE table_name = '{table_name}' 
          AND constraint_name = 'PRIMARY' 
          AND table_schema = DATABASE()
    """)
    existing_pk = [row[0] for row in cursor.fetchall()]

    # 解析目标主键（从列定义中提取含有PRIMARY KEY的列）
    desired_pk = [col[0] for col in column_defs if "PRIMARY KEY" in col[2].upper()]

    alter_queries = []

    # 遍历列定义，处理新增或修改列
    for col in column_defs:
        col_name, col_type, col_extra = col
        # 如果定义中包含 PRIMARY KEY，则在修改列时移除（主键统一后续处理）
        clean_extra = col_extra.upper().replace("PRIMARY KEY", "").strip()
        # 如果 clean_extra 为空，说明只是为了标识主键，可设为空字符串
        if not clean_extra:
            clean_extra = ""
        if col_name not in existing_columns:
            # 新增列（不直接定义主键）
            alter_queries.append(
                f"ALTER TABLE `{table_name}` ADD COLUMN `{col_name}` {col_type} {clean_extra}".strip()
            )
            continue

        # 对比现有列属性
        current = existing_columns[col_name]
        # 判断 NOT NULL 状态：若定义中含有 "NOT NULL"，则 target_nullable 为 False
        target_nullable = "NOT NULL" in col_extra.upper()
        type_mismatch = current["type"] != col_type.lower()
        nullable_mismatch = current["nullable"] != target_nullable
        extra_mismatch = current["extra"] != clean_extra.lower()
        if type_mismatch or nullable_mismatch or extra_mismatch:
            alter_queries.append(
                f"ALTER TABLE `{table_name}` MODIFY COLUMN `{col_name}` {col_type} {clean_extra}".strip()
            )

    # 主键处理：若现有主键和期望主键不匹配，则先DROP再ADD
    if sorted(existing_pk) != sorted(desired_pk):
        if existing_pk:
            alter_queries.append(f"ALTER TABLE `{table_name}` DROP PRIMARY KEY")
        if desired_pk:
            pk_columns = ", ".join(f"`{col}`" for col in desired_pk)
            alter_queries.append(f"ALTER TABLE `{table_name}` ADD PRIMARY KEY ({pk_columns})")

    # 外键处理
    if foreign_keys:
        # 使用别名消除字段歧义
        cursor.execute(f"""
            SELECT kcu.CONSTRAINT_NAME,
                   GROUP_CONCAT(kcu.COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION) AS columns,
                   kcu.REFERENCED_TABLE_NAME,
                   GROUP_CONCAT(kcu.REFERENCED_COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION) AS ref_columns,
                   rc.UPDATE_RULE,
                   rc.DELETE_RULE
            FROM information_schema.KEY_COLUMN_USAGE kcu
            JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
              ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
             AND kcu.TABLE_SCHEMA = rc.CONSTRAINT_SCHEMA
            WHERE kcu.TABLE_NAME = '{table_name}'
              AND kcu.TABLE_SCHEMA = DATABASE()
              AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
            GROUP BY kcu.CONSTRAINT_NAME, kcu.REFERENCED_TABLE_NAME, rc.UPDATE_RULE, rc.DELETE_RULE
        """)
        existing_fks = {}
        for row in cursor.fetchall():
            fk_name = row[0]
            existing_fks[fk_name] = {
                "columns": row[1].split(','),
                "ref_table": row[2],
                "ref_columns": row[3].split(','),
                "on_update": row[4].upper(),
                "on_delete": row[5].upper()
            }
        # 期望外键：这里使用自动生成的外键名称（例如：fk_<table>_<col1>_<col2>）
        for desired_fk in foreign_keys:
            fk_name = f"fk_{table_name}_{'_'.join(desired_fk['columns'])}"
            desired_fk_normalized = {
                "columns": desired_fk["columns"],
                "ref_table": desired_fk["ref_table"],
                "ref_columns": desired_fk["ref_columns"],
                "on_update": desired_fk.get("on_update", "NO ACTION").upper(),
                "on_delete": desired_fk.get("on_delete", "NO ACTION").upper()
            }
            if fk_name not in existing_fks:
                fk_sql = (
                    f"ALTER TABLE `{table_name}` ADD CONSTRAINT `{fk_name}` FOREIGN KEY "
                    f"(`{'`,`'.join(desired_fk_normalized['columns'])}`) REFERENCES `{desired_fk_normalized['ref_table']}` "
                    f"(`{'`,`'.join(desired_fk_normalized['ref_columns'])}`) ON UPDATE {desired_fk_normalized['on_update']} "
                    f"ON DELETE {desired_fk_normalized['on_delete']}"
                )
                alter_queries.append(fk_sql)
            else:
                existing_fk = existing_fks[fk_name]
                if (existing_fk["columns"] != desired_fk_normalized["columns"] or
                    existing_fk["ref_table"] != desired_fk_normalized["ref_table"] or
                    existing_fk["ref_columns"] != desired_fk_normalized["ref_columns"] or
                    existing_fk["on_update"] != desired_fk_normalized["on_update"] or
                    existing_fk["on_delete"] != desired_fk_normalized["on_delete"]):
                    alter_queries.append(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{fk_name}`")
                    fk_sql = (
                        f"ALTER TABLE `{table_name}` ADD CONSTRAINT `{fk_name}` FOREIGN KEY "
                        f"(`{'`,`'.join(desired_fk_normalized['columns'])}`) REFERENCES `{desired_fk_normalized['ref_table']}` "
                        f"(`{'`,`'.join(desired_fk_normalized['ref_columns'])}`) ON UPDATE {desired_fk_normalized['on_update']} "
                        f"ON DELETE {desired_fk_normalized['on_delete']}"
                    )
                    alter_queries.append(fk_sql)

    # 执行所有 ALTER 语句
    for query in alter_queries:
        try:
            print("执行 SQL:", query)
            cursor.execute(query)
        except Exception as err:
            logger.error(f"执行 SQL 失败: {query}\n错误信息: {err}")
    logger.info(f"同步表 {table_name} 成功")
    

def sync_triggers(cursor, triggers):
    """
    同步数据库触发器

    :param cursor: MySQL连接的cursor对象
    :param triggers: 触发器定义字典，格式例如：
        {
            "update_item_total_free": '''
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
            # 其它触发器...
        }
    """
    for trigger_name, trigger_sql in triggers.items():
        try:
            # 先删除旧的触发器（如果存在）
            drop_sql = f"DROP TRIGGER IF EXISTS `{trigger_name}`;"
            # print("执行 SQL:", drop_sql)
            cursor.execute(drop_sql)

            # 创建触发器
            # print("执行 SQL:", trigger_sql)
            cursor.execute(trigger_sql)
            logger.info(f"同步触发器 {trigger_name} 成功")
        except Exception as err:
            logger.error(f"同步触发器 {trigger_name} 失败，错误信息: {err}")
