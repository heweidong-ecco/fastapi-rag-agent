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

# 🔴 `DEC-055`：一轮问答**没能正常走完**（取消 / 异常）时，存进历史的半截**必须带这个尾巴**。
#    ⚠️ 与 `DEC-053` 用的是**同一个字符串**（原文在 `api_v1_rag.py`，2026-10-04 搬来这里 ⇒ 单一来源）。
INTERRUPTED_SUFFIX = "…（本次回答被中断，以上为已生成部分）"


# 服务端：将对话历史存入 Redis :流式对话中的历史管理：在 WebSocket 或 SSE 接口中，需要在服务端维护用户的对话历史（如存入 Redis），这样即使页面刷新，上下文也不会丢失。
def get_chat_history(user_name: str) -> list[dict]:
    """获取指定用户的对话历史，返回最近5轮消息列表。

    ⚠️ **老条目没有 `status`**（`DEC-055` 之前写的），读回时补 `"done"`。
    🔴 归一化只在这**一个读取点**：老条目只可能是**完整答案**
       （`DEC-053` 之前根本不存半截）⇒ 补 `done` 是对的，⛔ 不是猜。
    """
    key = f"chat_history:{user_name}"
    data = redis_client.lrange(key, -10, -1)  # 只取最近10条（5轮问答）
    entries = [json.loads(msg) for msg in data] if data else []
    return [{**e, "status": e.get("status", "done")} for e in entries]

def append_chat_history(user_name: str, role: str, content: str, *, status: str):
    """向用户的对话历史中追加一条消息，并设置24小时过期时间。

    ⚠️ `status`（`DEC-055` 决策 3）是**关键字专用、且必填**：
       · **必填** —— 留痕字段一旦有默认值，「忘了传」会**静默**变成假信号，
         而本 DEC 的全部意义就是「读的人能分辨这一轮说完了没有」；
       · **关键字** —— 位置参数会让 `api/test_cancel_propagation.py` 里
         `for _, r, c in store` 式的解包 **`ValueError`**（那是测试夹具，⛔ 不该被产品签名牵动）。
    """
    key = f"chat_history:{user_name}"
    redis_client.rpush(key, json.dumps({"role": role, "content": content, "status": status}))
    redis_client.expire(key, 86400)  # 24小时后自动过期


def persist_turn(user_name: str, question: str, answer: str, *, status: str) -> None:
    """一轮问答的**留痕** —— `done` / `cancelled` / `error` **三条出口共用这一段**（`DEC-055` 决策 2）。

    ⚠️ 三条规则：
      · `done` ⇒ 存**完整答案**、**不带**标记（带了会让下一轮把好答案当"被截断"的）；
      · 非 `done` ⇒ 存**半截 + `INTERRUPTED_SUFFIX`**；
      · **空答案 ⇒ 什么都不写** —— 空的助手消息只会污染下一轮 prompt（`DEC-053` 决策 4）；
      · **成对写** —— 只写答案不写提问 ⇒ 历史里出现一条**没有来由**的助手消息。
    """
    text = answer or ""
    if not text.strip():
        return
    if status != "done":
        text = text.strip() + INTERRUPTED_SUFFIX
    append_chat_history(user_name, "user", question, status=status)
    append_chat_history(user_name, "assistant", text, status=status)

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