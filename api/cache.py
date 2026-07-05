import redis
import hashlib
import json
import os
from config import REDIS_HOST, REDIS_PORT


redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

def get_cache_key(text: str) -> str:
    """用文本的MD5哈希值作为缓存键"""
    return "emb:" + hashlib.md5(text.encode()).hexdigest()

def get_cached_embedding(text: str):
    """从Redis获取缓存的向量。命中返回向量列表，未命中返回None"""
    key = get_cache_key(text)
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

def set_cached_embedding(text: str, embedding: list, expire_seconds: int = 86400):
    """将向量存入Redis，默认过期时间24小时"""
    key = get_cache_key(text)
    redis_client.set(key, json.dumps(embedding), ex=expire_seconds)

# 服务端：将对话历史存入 Redis :流式对话中的历史管理：在 WebSocket 或 SSE 接口中，需要在服务端维护用户的对话历史（如存入 Redis），这样即使页面刷新，上下文也不会丢失。
def get_chat_history(user_name: str) -> list[dict]:
    """获取指定用户的对话历史，返回最近5轮消息列表"""
    key = f"chat_history:{user_name}"
    data = redis_client.lrange(key, -10, -1)  # 只取最近10条（5轮问答）
    return [json.loads(msg) for msg in data] if data else []

def append_chat_history(user_name: str, role: str, content: str):
    """向用户的对话历史中追加一条消息，并设置24小时过期时间"""
    key = f"chat_history:{user_name}"
    redis_client.rpush(key, json.dumps({"role": role, "content": content}))
    redis_client.expire(key, 86400)  # 24小时后自动过期

# cache.py 新增内容：增加预热函数
# 常见热点查询列表（根据你的业务场景维护）
HOT_QUERIES = [
    "Python是什么？",
    "Docker能解决什么问题？",
    "机器学习是什么？",
    "FastAPI是什么？",
    "PostgreSQL有什么特性？",
    "Redis有哪些用途？",
    "LangChain是什么？",
    "向量数据库的作用",
    "苹果公司的主要产品",
    "全球AI市场规模",
]

def warmup_cache():
    """
    启动时预热缓存：提前计算热点查询的Embedding，存入Redis。
    如果Embedding API调用失败，跳过该查询，不阻塞启动。
    """
    from embedding_client import get_embedding  # 延迟导入，避免循环依赖
    
    print(f"开始缓存预热（共 {len(HOT_QUERIES)} 个热点查询）...")
    success = 0
    for query in HOT_QUERIES:
        try:
            # 调一次 get_embedding，内部会自动存入 Redis 缓存
            get_embedding(query)
            success += 1
        except Exception as e:
            print(f"  预热失败 [{query}]: {e}")
    print(f"缓存预热完成：{success}/{len(HOT_QUERIES)} 个查询已缓存。")