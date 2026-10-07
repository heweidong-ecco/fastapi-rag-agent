# 工具调用缓存，升级版了，包含三大风险的防护
import hashlib
import json
import time
import random
import redis
from functools import wraps
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

# 🔴 2026-09-20 加（§三·C5 · 业务方裁「需要调整，不能无限递归」）：
#    **抢不到锁时最多等多久**；超了就**降级为直接执行**（这次不写缓存）。
#
#    原实现在 `else` 分支里是 `time.sleep(0.1); return wrapper(*args, **kwargs)`
#    ⇒ **递归没有上限**：锁一直拿不到（持有者崩了没删锁、或一直被别的请求续上）时，
#      **把栈打爆** —— 实测 `RecursionError: maximum recursion depth exceeded`。
#    ⚠️ 这是**并发正确性**问题、且是**进程级**故障：一旦触发就把整个请求打死。
#
#    ✅ 正确取舍：**缓存是优化，不该因为它拿不到就拒服务。** 等一小段（有上限）后
#       直接执行工具函数 —— 结果照常返回，只是这次不写缓存。
_LOCK_WAIT_SECONDS = 2.0


def cached_tool(expire_seconds: int = 300):
    """装饰器：自动为工具函数添加缓存（含穿透、击穿、雪崩防护）

    ⚠️ 抢锁**有上限**（`_LOCK_WAIT_SECONDS`）：超时后**降级为直接执行** —— 不再等、**不递归**。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tool_name = func.__name__
            # 1. 查缓存
            cached = get_cached_tool_result(tool_name, *args, **kwargs)
            if cached is not None:
                return cached

            # 2. 防击穿：互斥锁（**有上限地等** —— 用循环，不用递归；理由见文件头那段）
            lock_key = f"lock:{tool_name}"
            deadline = time.monotonic() + _LOCK_WAIT_SECONDS
            while True:
                if redis_client.set(lock_key, "1", nx=True, ex=10):
                    try:
                        # 3. 执行工具函数
                        result = func(*args, **kwargs)
                        # 4. 回写缓存（带防穿透和防雪崩）
                        set_cached_tool_result(tool_name, result, expire_seconds, *args, **kwargs)
                        return result
                    finally:
                        redis_client.delete(lock_key)

                # 5. 没拿到锁：到点就**降级**；否则等一小会儿，再看别人有没有把缓存填好
                if time.monotonic() >= deadline:
                    return func(*args, **kwargs)      # 降级：直接执行，这次不写缓存
                time.sleep(0.05)
                cached = get_cached_tool_result(tool_name, *args, **kwargs)
                if cached is not None:
                    return cached
        return wrapper
    return decorator