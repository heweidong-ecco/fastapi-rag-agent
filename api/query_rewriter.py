"""
查询改写模块
使用 LLM 对用户问题进行扩展和优化，提升检索召回率。
（带 Redis 缓存）
优化查询：结合对话历史补全上下文、转书面语、消解指代。
"""
import os
import hashlib
import json
from openai import OpenAI
import redis

# 复用现有的 Redis 客户端（与 cache.py 中相同配置）
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=0,
    decode_responses=True
)
# 复用现有的 LLM 客户端配置
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

REWRITE_MODEL = "qwen-turbo"

# 缓存过期时间：1小时
CACHE_TTL = 3600

def _get_cache_key(prefix: str, text: str, extra: str = "") -> str:
    """生成缓存键"""
    raw = f"{prefix}:{text}:{extra}"
    return "rewrite:" + hashlib.md5(raw.encode()).hexdigest()

def expand_query(original_query: str, num_variants: int = 3) -> list[str]:
    """生成查询变体（带缓存）"""
    cache_key = _get_cache_key("expand", original_query, str(num_variants))
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    """
    生成多个不同表述的查询变体，用于扩大检索范围。
    """
    prompt = f"""你是一个查询扩展助手。请将用户的问题改写成 {num_variants} 个不同表述但语义相同的查询。
每个查询一行，不要编号，不要任何额外说明。

用户问题：{original_query}

改写结果：
"""
    response = client.chat.completions.create(
        model=REWRITE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,  # 稍高温度以生成多样性
        max_tokens=200
    )
    lines = response.choices[0].message.content.strip().split("\n")
    # 过滤空行，并确保包含原始查询
    variants = [line.strip() for line in lines if line.strip()]
    if original_query not in variants:
        variants.insert(0, original_query)
    result = variants[:num_variants + 1]

    # 写入缓存
    redis_client.set(cache_key, json.dumps(result, ensure_ascii=False), ex=CACHE_TTL)
    return result


def rewrite_query(original_query: str, conversation_history: list[str] = None) -> str:
    """优化查询（带缓存）"""
    # 将历史序列化成字符串作为缓存键的一部分
    history_str = ""
    if conversation_history:
        history_str = "|".join(conversation_history[-5:])
    cache_key = _get_cache_key("rewrite", original_query, history_str)
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    """
    优化查询：补全上下文、转书面语、纠正口语化表达。
    如果提供了对话历史，会尝试消解指代。
    """
    history_text = ""
    if conversation_history:
        history_lines = "\n".join(conversation_history[-5:])  # 只取最近5轮
        history_text = f"\n对话历史：\n{history_lines}"

    prompt = f"""你是一个查询优化助手。请将用户的问题改写成更适合文档检索的书面语形式。
要求：
- 如果问题中有指代不明的代词（如“它”、“这个”、“那个”），请根据对话历史将其替换为明确的对象。
- 如果问题是省略句，请结合历史补全完整的语义。
- 将口语化表达转为正式书面语。
- 保持原始语义不变。
- 只输出改写后的问题，不要任何额外说明。{history_text}

用户问题：{original_query}

改写结果：
"""
    response = client.chat.completions.create(
        model=REWRITE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # 低温以确保语义不变
        max_tokens=200
    )
    result = response.choices[0].message.content.strip()

    # 写入缓存
    redis_client.set(cache_key, result, ex=CACHE_TTL)
    return result