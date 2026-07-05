# 工具调用缓存，升级版了，包含三大风险的防护
import hashlib
import json
import time
import random
import redis
from functools import wraps
import os
from config import REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

# ==================== 基础缓存操作 ====================
def get_tool_cache_key(tool_name: str, *args, **kwargs) -> str:
    """为工具调用生成缓存键"""
    raw = f"{tool_name}:{str(args)}:{str(sorted(kwargs.items()))}"
    return "tool:" + hashlib.md5(raw.encode()).hexdigest()

def get_cached_tool_result(tool_name: str, *args, **kwargs):
    """获取缓存的工具调用结果。返回None表示未命中或空值缓存"""
    key = get_tool_cache_key(tool_name, *args, **kwargs)
    cached = redis_client.get(key)
    if cached is None:
        return None  # 未命中
    if cached == "__NULL__":
        return None  # 命中了空值缓存（防穿透）
    return json.loads(cached)

def set_cached_tool_result(tool_name: str, result, expire_seconds: int = 300, *args, **kwargs):
    """缓存工具调用结果，带随机抖动防雪崩"""
    key = get_tool_cache_key(tool_name, *args, **kwargs)
    if result is None:
        # 防穿透：空值也缓存，但时间短
        redis_client.set(key, "__NULL__", ex=60)
    else:
        # 防雪崩：过期时间加随机抖动
        actual_expire = expire_seconds + random.randint(0, expire_seconds // 10)
        redis_client.set(key, json.dumps(result), ex=actual_expire)

# ==================== 缓存装饰器 ====================
def cached_tool(expire_seconds: int = 300):
    """装饰器：自动为工具函数添加缓存（含穿透、击穿、雪崩防护）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tool_name = func.__name__
            # 1. 查缓存
            cached = get_cached_tool_result(tool_name, *args, **kwargs)
            if cached is not None:
                return cached
            
            # 2. 防击穿：互斥锁
            lock_key = f"lock:{tool_name}"
            if redis_client.set(lock_key, "1", nx=True, ex=10):
                try:
                    # 3. 执行工具函数
                    result = func(*args, **kwargs)
                    # 4. 回写缓存（带防穿透和防雪崩）
                    set_cached_tool_result(tool_name, result, expire_seconds, *args, **kwargs)
                    return result
                finally:
                    redis_client.delete(lock_key)
            else:
                # 没拿到锁，等一小会儿再递归查缓存
                time.sleep(0.1)
                return wrapper(*args, **kwargs)
        return wrapper
    return decorator