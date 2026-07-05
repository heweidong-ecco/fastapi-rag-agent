import psycopg2
from contextlib import contextmanager
from psycopg2.extras import execute_values
import os
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
    "user": "postgres",
    "password": POSTGRES_PASSWORD,
    "host": POSTGRES_HOST,
    "port": POSTGRES_PORT
}

@contextmanager
def get_db():
    """提供数据库连接上下文管理器，自动关闭连接"""
    #上下文管理器 = 自动关门：你进房间用完东西，出门时门会自动锁上，绝不会忘。
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
#借助 Python 的 with 语句使用：with get_db() as conn: ...
#进入 with 块时，执行 yield 之前的代码，获得连接对象。
#退出 with 块时（即使发生异常），finally 中的 conn.close() 一定会执行，自动释放连接。

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

# db.py 末尾添加
from sqlalchemy import MetaData, Table, Column, Integer, Text, String, DateTime
from sqlalchemy.sql import func

metadata = MetaData()

# 定义 documents 表的结构（与现有表一致）
documents_table = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("content", Text, nullable=False),
    Column("source", String),
    Column("embedding", Text),  # pgvector 在 Alembic 中可能需要特殊处理，先简化
)

# 定义 api_keys 表的结构
api_keys_table = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_name", Text, nullable=False),
    Column("key_hash", Text, nullable=False, unique=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("expires_at", DateTime, nullable=False),
    Column("is_active", Integer, server_default="1"),  # 新增字段，默认1表示激活
)
    
# ==================== BM25 关键词检索 ====================
import numpy as np
import jieba
from rank_bm25 import BM25Okapi

# 全局缓存：避免每次搜索都重建索引
_bm25_cache = {
    "bm25": None,
    "docs": []
}

def get_all_documents():
    """获取数据库中所有文档的内容、来源和ID，用于构建BM25索引"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, content, source FROM documents")
            return cur.fetchall()

def get_bm25_index():
    """获取缓存的BM25索引，如果不存在则重建"""
    if _bm25_cache["bm25"] is None:
        docs = get_all_documents()
        if docs:
            # 使用 jieba 进行中文分词
            tokenized_docs = [list(jieba.cut(doc[1])) for doc in docs]
            _bm25_cache["bm25"] = BM25Okapi(tokenized_docs)
            _bm25_cache["docs"] = docs
    return _bm25_cache["bm25"], _bm25_cache["docs"]

def invalidate_bm25_cache():
    """在文档插入/删除后调用，清空缓存以触发重建"""
    _bm25_cache["bm25"] = None
    _bm25_cache["docs"] = []

def bm25_search(query: str, top_k: int = 10):
    """
    用 BM25 关键词检索文档。
    返回 [(id, content, source, bm25_score), ...]
    """
    bm25, docs = get_bm25_index()
    if bm25 is None or not docs:
        return []

    tokenized_query = list(jieba.cut(query))
    scores = bm25.get_scores(tokenized_query)

    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            doc = docs[idx]
            results.append((doc[0], doc[1], doc[2], float(scores[idx])))

    return results

# db.py —— 新增异步包装（放在同文件末尾即可）
import asyncio

async def search_similar_async(query_embedding: list, top_k: int = 3):
    return await asyncio.to_thread(search_similar, query_embedding, top_k)

async def bm25_search_async(query: str, top_k: int = 10):
    return await asyncio.to_thread(bm25_search, query, top_k)




