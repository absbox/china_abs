import pandas as pd
import psycopg
from psycopg_pool import ConnectionPool
import os
from pathlib import Path

from functools import lru_cache
import toolz as tz
import logging
from contextlib import contextmanager
from typing import Optional, Generator
from psycopg import Connection
from psycopg.rows import dict_row  # 默认返回字典格式，更直观
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import psycopg
from dotenv import load_dotenv
load_dotenv()

host = os.getenv("DATABASE_URL") # "localhost"
dbName = os.getenv("DATABASE_NAME") #  'source'
port = os.getenv("DATABASE_PORT")  # 65432   
pwd = os.getenv("DATABASE_PASSWORD") # 'doadmin'
connStr = (f"postgresql://doadmin:{pwd}@{host}:{port}/{dbName}?"
          "keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabasePoolManager:
    """数据库连接池管理器（生产环境推荐）"""
    
    _instance: Optional['DatabasePoolManager'] = None
    _pool: Optional[ConnectionPool] = None
    
    def __new__(cls):
        """单例模式，确保全局只有一个连接池"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(
        self,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
        timeout: int = 30,
        max_lifetime: int = 3600,
        max_idle: int = 300,
        row_use_dict: bool = False
    ) -> None:
        """
        初始化连接池（应用启动时调用一次）
        
        Args:
            dsn: 数据库连接字符串，如 postgresql://user:password@host:port/dbname
            min_size: 连接池最小连接数（保持活跃）
            max_size: 连接池最大连接数（必须小于数据库max_connections）
            timeout: 获取连接超时时间（秒）
            max_lifetime: 连接最大存活时间（秒），防止长时间使用产生内存碎片
            max_idle: 空闲连接超时时间（秒），自动清理闲置连接
        """
        if self._pool is not None:
            logger.warning("连接池已初始化，跳过重复初始化")
            return
       
        row_dict_flag = {"row_factory": dict_row} if row_use_dict else {}
        # 核心配置
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_lifetime=max_lifetime,
            max_idle=max_idle,
            
            # 关键：配置连接参数
            kwargs={
                # 自动将查询结果转为字典
                #"row_factory": dict_row,
                # 为连接设置应用名，便于在数据库中识别
                "options": "-c application_name=db_source",
                # 设置连接超时
                "connect_timeout": 30,
                "autocommit": True,
            } | row_dict_flag,
            
            # 连接检查配置（重要！）
            check=ConnectionPool.check_connection,  # 取出连接时自动检查
            reconnect_timeout=5,  # 重连超时
            reconnect_failed=None,  # 重连失败时的回调
        )
        
        # 启动连接池
        self._pool.open()
        logger.info(
            f"数据库连接池初始化成功 "
            f"(min={min_size}, max={max_size}, timeout={timeout}s)"
        )
        
        # 注册关闭钩子
        import atexit
        atexit.register(self.close)
    
    @retry(
        stop=stop_after_attempt(3),  # 最多重试3次
        wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避
        retry=retry_if_exception_type(psycopg.OperationalError),  # 只重试连接错误
    )
    @contextmanager
    def get_conn(self) -> Generator[Connection, None, None]:
        """
        获取数据库连接的上下文管理器
        
        使用示例：
            with db_pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                    result = cur.fetchone()
        
        注意：不需要手动提交，成功执行后自动提交；异常时自动回滚。
        """
        if self._pool is None:
            raise RuntimeError("连接池未初始化，请先调用 initialize()")
        
        conn = None
        try:
            # 从池中获取连接（如果池为空，会等待timeout秒）
            conn = self._pool.getconn()
            logger.debug("成功从连接池获取连接")
            
            # 设置会话级参数
            with conn.cursor() as cur:
                # 设置语句超时（单位毫秒），防止慢查询
                cur.execute("SET statement_timeout = 30000;")
                # 设置锁超时
                cur.execute("SET lock_timeout = 10000;")
            
            yield conn
            
            # 没有异常，自动提交事务
            conn.commit()
            logger.debug("事务已自动提交")
            
        except psycopg.Error as e:
            logger.error(f"数据库操作失败: {e}")
            if conn:
                conn.rollback()  # 发生异常时回滚
                logger.debug("事务已回滚")
            raise
        finally:
            if conn:
                # 将连接归还给池，而不是关闭它
                self._pool.putconn(conn)
                logger.debug("连接已归还给连接池")
    
    async def get_conn_async(self):
        """异步版本（适用于async/await环境）"""
        if self._pool is None:
            raise RuntimeError("连接池未初始化")
        
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                # 设置超时参数
                await cur.execute("SET statement_timeout = 30000;")
            yield conn
    
    def get_pool_stats(self) -> dict:
        """获取连接池统计信息（用于监控）"""
        if self._pool is None:
            return {}
        
        return {
            "pool_min_size": self._pool.min_size,
            "pool_max_size": self._pool.max_size,
            "connections_used": self._pool.get_stats().connections_used,
            "connections_idle": self._pool.get_stats().connections_idle,
            "connections_maxed": self._pool.get_stats().connections_maxed,
            "connections_waiting": self._pool.get_stats().queue.qsize() if self._pool.get_stats().queue else 0,
        }
    
    def close(self) -> None:
        """关闭连接池（应用退出时调用）"""
        if self._pool is not None:
            self._pool.close()
            logger.info("数据库连接池已关闭")
    
    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            raise RuntimeError("连接池未初始化")
        return self._pool

db_pool = DatabasePoolManager()
db_pool.initialize(dsn=connStr,min_size=1,max_size=4,timeout=30,max_idle=300,max_lifetime=3600)

def q_with_m(tbl:str,fs, where=None):
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            fstr = '","'.join(fs)
            sql = f'select "{fstr}" from {tbl}'
            if where:
                sql += f' where {where}'
            rs = cur.execute(sql).fetchall()
            return [ dict(zip(fs,r)) for r in rs ]


def mineruExistingKey():
    # fss = cur.execute("select distinct(key) from mineru;")
    # existingKeys = set(tz.concat(fss))
    # return existingKeys
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            fss =  cur.execute("select distinct(key) from mineru where markdown IS NOT NULL;")
            existingKeys = set(tz.concat(fss))
            return existingKeys

def existingDocKey():
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            fss =  cur.execute("select distinct(key) from qiniu_storage;")
            existingKeys = set(tz.concat(fss))
            return existingKeys


def hasMarkdown(k:str):
    _sql = f"SELECT markdown FROM mineru where key='{k}' and markdown IS NOT NULL;"
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            if (x:=r.fetchone()):    
                return True
            else:
                return False

def hasJs(k:str):
    _sql = f"SELECT parsed_json FROM mineru where key='{k}' and parsed_json IS NOT NULL;"
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            if (x:=r.fetchone()):    
                return True
            else:
                return False

def hasFileByKey(k:str):
    _sql = f"SELECT key FROM qiniu_storage where key= %s ; "
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql, (k,))
            return r.fetchone() 


#@lru_cache(maxsize=256)
def getFilesByKey(k:str,nameOnly=True):
    _sql = None
    if nameOnly:
        _sql = f"SELECT key FROM qiniu_storage where key like '%{k}%' ; "
    else:
        _sql = f"SELECT * FROM qiniu_storage where key like '%{k}%' ; "
    assert _sql is not None,"_sql is none"
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            return r.fetchall() 

#@lru_cache(maxsize=256)
def getFilesByKey2(k:str,nameOnly=True):
    _sql = None
    if nameOnly:
        _sql = f"SELECT key FROM qiniu_storage_view where \"keystriped\" like '%{k}%';"
    else:
        _sql = f"SELECT * FROM qiniu_storage_view where \"keystriped\" like '%{k}%';"
    assert _sql is not None,"_sql is none"
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            return r.fetchall() 


def getMdFilesByKey(k:str,nameOnly=True):
    _sql = None
    if nameOnly:
        _sql = f"SELECT key FROM mineru where key like '%{k}%' and markdown IS NOT NULL ; "
    else:
        _sql = f"SELECT * FROM mineru where key like '%{k}%' and markdown IS NOT NULL  ; "
    assert _sql is not None,"_sql is none"
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            return r.fetchall() 


def testFileInCloud(k:str):
    fNames = set(tz.concat(getFilesByKey(k,nameOnly=True)))
    return k in fNames

def getMuMd(k:str):
    _sql = f"SELECT markdown FROM mineru where key='{k}' "
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            return r.fetchone()[0]

def getMuJs(k:str):
    _sql = f"SELECT parsed_json FROM mineru where key='{k}'; "
    with db_pool.get_conn() as conn:
        with conn.cursor() as cur:
            r = cur.execute(_sql)
            if (x:= r.fetchone()):
                return x[0]
            else:
                print(f"lookup Js failed from {k}")
                return None



