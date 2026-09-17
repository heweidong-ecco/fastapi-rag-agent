import time
import redis
from fastapi import Request, HTTPException
import os
from config import REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

class TokenBucketLimiter:
    """
    基于Redis的令牌桶限流器。
    每个用户维护一个独立的桶，用Redis Hash存储。
    """
    
    def __init__(self, rate: float = 3.0, capacity: int = 20):
        """
        rate: 每秒补充的令牌数
        capacity: 桶的最大容量（允许的最大突发请求数）
        """
        self.rate = rate
        self.capacity = capacity
    
    def _get_bucket_key(self, user_name: str) -> str:
        """为每个用户生成独立的桶键"""
        return f"rate_limit:{user_name}"
    
    def is_allowed(self, user_name: str) -> bool:
        """
        检查用户是否允许此次请求。
        如果允许，消耗一个令牌；否则返回False。
        """
        key = self._get_bucket_key(user_name)
        now = time.time()
        
        # 使用Lua脚本保证原子性
        lua_script = """
        local bucket = redis.call('HGETALL', KEYS[1])
        local now = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local capacity = tonumber(ARGV[3])
        
        local tokens = capacity  -- 初始令牌数
        local last_time = now    -- 上次补充时间
        
        if next(bucket) ~= nil then
            tokens = tonumber(bucket[2])  -- 当前令牌数
            last_time = tonumber(bucket[4])  -- 上次补充时间
        end
        
        -- 计算新增令牌
        local elapsed = now - last_time
        local new_tokens = math.floor(elapsed * rate)
        tokens = math.min(capacity, tokens + new_tokens)
        
        if tokens >= 1 then
            tokens = tokens - 1  -- 消耗一个令牌
            redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_time', now)
            return 1  -- 允许
        else
            redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_time', now)
            return 0  -- 拒绝
        end
        """
        
        result = redis_client.eval(
            lua_script,
            1,
            key,
            now,
            self.rate,
            self.capacity
        )
        
        return bool(result)
    
    def get_remaining(self, user_name: str) -> int:
        """查询用户剩余令牌数"""
        key = self._get_bucket_key(user_name)
        data = redis_client.hgetall(key)
        if not data:
            return self.capacity
        return int(float(data.get("tokens", self.capacity)))
    
    #增加 get_limit_info 方法，返回当前剩余令牌数及令牌完全恢复的时间戳。
    def get_limit_info(self, user_name: str) -> dict:
        """
        返回当前用户的限流信息，用于构造响应头。
        返回: {
            'remaining': int,     # 剩余令牌数
            'reset': int,         # 令牌桶完全回满的 Unix 时间戳（秒）
            'limit': int,         # 桶的容量（总限制）
        }
        """
        key = self._get_bucket_key(user_name)
        now = time.time()
        data = redis_client.hgetall(key)
        
        if not data:
            tokens = self.capacity
            last_time = now
        else:
            tokens = float(data.get("tokens", self.capacity))
            last_time = float(data.get("last_time", now))
        
        # 计算恢复到满桶所需时间
        need = self.capacity - tokens
        if need <= 0:
            reset_time = now
        else:
            reset_time = now + (need / self.rate)
        
        return {
            "remaining": int(tokens),
            "reset": int(reset_time),
            "limit": self.capacity
        }

# 新增 实现“全局 + 用户”两层令牌桶防护

# 全局限流器：每秒100次，桶容量150（允许一定突发）
global_limiter = TokenBucketLimiter(rate=100.0, capacity=150)

# 用户级限流器：每秒3次，桶容量20
user_limiter = TokenBucketLimiter(rate=3.0, capacity=20)