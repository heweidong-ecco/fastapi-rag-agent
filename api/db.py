import psycopg2
from contextlib import contextmanager
from psycopg2.extras import execute_values
import os
import asyncio
from config import DB_MIN_CONN, DB_MAX_CONN, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_PASSWORD,POSTGRES_USER

from psycopg2 import pool

# 连接池（全局唯一）使用环境变量设置 连接池的上下限，DB_MIN_CONN, DB_MAX_CONN
_connection_pool = None

def init_pool():
    """初始化连接池（应用启动时调用，参数从环境变量读取）"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=DB_MIN_CONN,
            maxconn=DB_MAX_CONN,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        print(f"✅ 数据库连接池已初始化（最小{DB_MIN_CONN}，最大{DB_MAX_CONN}）")

def close_pool():
    """关闭连接池（应用关闭时调用）"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        print("数据库连接池已关闭")

@contextmanager
def get_db():
    """从连接池中获取一个连接，使用完后归还"""
    if _connection_pool is None:
        init_pool()
    conn = _connection_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _connection_pool.putconn(conn)

DB_CONFIG = {
    "dbname": POSTGRES_DB,
    "user": POSTGRES_USER,
    "password": POSTGRES_PASSWORD,
    "host": POSTGRES_HOST,
    "port": POSTGRES_PORT
}
# 注意：仅保留上方基于连接池的 get_db()（自动提交/回滚/归还连接）。
# 历史版本曾在下方重复定义 get_db() 覆盖连接池版本，导致写入不提交、连接池失效，已删除。

def create_table():
    try:
        with get_db() as conn:#连接管理
            with conn.cursor() as cur:#游标创建
                #SQL 执行
                # 确保 pgvector 扩展已启用（必须放在建表之前）
                # 表中增加 owner 字段用requested_by表示，owner是内部关键字直接用owner会冲突报错，所有查询和修改都带上当前用户的ID进行过滤，从而实现多用户数据隔离。
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id SERIAL PRIMARY KEY,
                        content TEXT NOT NULL,
                        source TEXT,
                        embedding vector(1536),
                        requested_by TEXT NOT NULL DEFAULT 'anonymous'  -- 新增字段
                    );
                """)
                # API Key 表
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        key_hash TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL
                    );
                """)
                conn.commit()
                # 如果表已存在但缺少列，则添加（兼容旧表）
                cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='documents' AND column_name='requested_by'
                        ) THEN
                            ALTER TABLE documents ADD COLUMN requested_by TEXT NOT NULL DEFAULT 'anonymous';
                        END IF;
                    END $$;
                """)
                # 为向量字段创建索引，加速检索
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS documents_embedding_idx
                    ON documents
                    USING ivfflat (embedding vector_cosine_ops);
                """)
                # 为 owner 字段用requested_by表示，建立索引，加速按用户过滤
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS documents_requested_by_idx
                    ON documents (requested_by);
                """)
                # Token使用日志表
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS token_usage_logs (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        thread_id TEXT DEFAULT 'unknown',
                        model TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        prompt_tokens INTEGER NOT NULL,
                        completion_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        cost REAL NOT NULL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # 为常用查询字段创建索引
                cur.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_user ON token_usage_logs(user_name);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_date ON token_usage_logs(created_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_thread ON token_usage_logs(thread_id);")
                # 新增：花费明细表
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cost_records (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        thread_id TEXT DEFAULT 'unknown',
                        model TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        prompt_tokens INTEGER NOT NULL DEFAULT 0,
                        completion_tokens INTEGER NOT NULL DEFAULT 0,
                        total_tokens INTEGER NOT NULL DEFAULT 0,
                        input_cost REAL NOT NULL DEFAULT 0.0,
                        output_cost REAL NOT NULL DEFAULT 0.0,
                        total_cost REAL NOT NULL DEFAULT 0.0,
                        tool_name TEXT,
                        tool_args TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # 索引
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cost_records_user ON cost_records(user_name);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cost_records_date ON cost_records(created_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cost_records_thread ON cost_records(thread_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cost_records_purpose ON cost_records(purpose);")
                # 增加归档表 建表语句：
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cost_records_archive (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        thread_id TEXT DEFAULT 'unknown',
                        model TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        prompt_tokens INTEGER NOT NULL DEFAULT 0,
                        completion_tokens INTEGER NOT NULL DEFAULT 0,
                        total_tokens INTEGER NOT NULL DEFAULT 0,
                        input_cost REAL NOT NULL DEFAULT 0.0,
                        output_cost REAL NOT NULL DEFAULT 0.0,
                        total_cost REAL NOT NULL DEFAULT 0.0,
                        tool_name TEXT,
                        tool_args TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            # 🔥 关键：显式提交，防止上下文管理器未提交
            conn.commit()
        print("✅ 表创建/确认成功，表结构更新成功,已包含 owner的requested_by 字段")
    except Exception as e:
        print("❌ 数据库初始化失败：", e)
        raise
def insert_document(content: str, source: str, embedding: list, requested_by: str = "anonymous"):
    """插入一条文档块及其向量"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (content, source, embedding, requested_by) VALUES (%s, %s, %s::vector, %s)",
                (content, source, embedding, requested_by)
            )
            conn.commit()

def insert_batch_documents(docs: list[tuple[str, str, list,]]):
    """批量插入文档块。docs: [(content, source, embedding), ...]"""
    with get_db() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO documents (content, source, embedding) VALUES %s",
                [(c, s, e) for c, s, e in docs],
                template="(%s, %s, %s::vector)"
            )
            conn.commit()

def search_similar(query_embedding: list, top_k: int = 3):
    """根据向量相似度检索文档"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,content, source, 1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

# ==================== 兼容转发层（重构计划 ⑥ 切开点 1）====================
# 本文件原先在**模块层** `import sqlalchemy / numpy / jieba / rank_bm25`，
# 于是**任何** `from db import get_db` 的调用方（auth.py / deps.py / cost_dashboard.py …）
# 都被迫把这 4 个重包一起拉起来。现已切走：
#   · 表结构声明 → `db_metadata.py`（纯 sqlalchemy，**不依赖本文件**，故可安全单向导入）
#   · BM25 检索   → `bm25_index.py`（反过来 `from db import get_db`）
#
# 下面这几个是**函数内惰性导入**的转发层：老调用方 `from db import bm25_search` 照旧可用，
# 但 `import db` 本身**不再**拉起重包。
# ⚠️ 必须惰性 —— `bm25_index` 反向依赖本文件的 `get_db`，模块层互相 import 会成环，
#    且只在"先 import bm25_index"时才炸，属最难查的一类。
# ⚠️ `alembic/env.py` 需要的 `metadata` **没有**在这里转发（它是值不是函数，转发要动
#    PEP 562 的 `__getattr__`）—— 已改为直接从 `db_metadata` 导入。

def bm25_search(query: str, top_k: int = 10):
    """转发到 `bm25_index.bm25_search`（惰性导入，见上方说明）。"""
    from bm25_index import bm25_search as _impl
    return _impl(query, top_k)

def get_bm25_index():
    """转发到 `bm25_index.get_bm25_index`（惰性导入）。"""
    from bm25_index import get_bm25_index as _impl
    return _impl()

def get_all_documents():
    """转发到 `bm25_index.get_all_documents`（惰性导入）。"""
    from bm25_index import get_all_documents as _impl
    return _impl()

def invalidate_bm25_cache():
    """转发到 `bm25_index.invalidate_bm25_cache`（惰性导入）。"""
    from bm25_index import invalidate_bm25_cache as _impl
    return _impl()

# ==================== 异步包装 ====================
async def search_similar_async(query_embedding: list, top_k: int = 3):
    return await asyncio.to_thread(search_similar, query_embedding, top_k)

async def bm25_search_async(query: str, top_k: int = 10):
    from bm25_index import bm25_search as _impl
    return await asyncio.to_thread(_impl, query, top_k)
