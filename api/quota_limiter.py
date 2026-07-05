import redis
from datetime import datetime, timedelta
import os
from config import REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)


class QuotaLimiter:
    """基于用户角色的每日调用量限制"""
    
    def _get_quota_key(self, user_name: str) -> str:
        """生成当天的配额键，每天自动重置"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"quota:{user_name}:{today}"
    
    def increment_and_check(self, user_name: str, daily_limit: int) -> bool:
        """
        增加用户调用计数，检查是否超出配额。
        返回 True 表示允许，False 表示配额已用完。
        """
        if daily_limit == float("inf"):
            return True  # 管理员不限次
        
        key = self._get_quota_key(user_name)
        
        # 使用 Lua 脚本保证原子性
        lua_script = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then
            redis.call('EXPIRE', KEYS[1], 86400)  -- 首次设置，24小时后自动过期
        end
        local limit = tonumber(ARGV[1])
        if count <= limit then
            return 1
        else
            return 0
        end
        """
        
        result = redis_client.eval(lua_script, 1, key, daily_limit)
        return bool(result)
    
    def get_remaining(self, user_name: str, daily_limit: int) -> int:
        """查询用户今日剩余调用次数"""
        if daily_limit == float("inf"):
            return -1  # 表示不限次
        
        key = self._get_quota_key(user_name)
        count = redis_client.get(key)
        used = int(count) if count else 0
        return max(0, daily_limit - used)

    def get_quota_info(self, user_name: str, daily_limit: int) -> dict:
        """
        返回完整的配额信息，用于构造响应头。
        {
            "limit": int,       # 每日总限额
            "remaining": int,   # 剩余次数
            "reset": int        # 配额重置的 Unix 时间戳（秒）
        }
        """
        # 计算今天的结束时间（明天凌晨0点）
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        reset_time = int(tomorrow.timestamp())
        
        remaining = self.get_remaining(user_name, daily_limit)
        
        return {
            "limit": daily_limit if daily_limit != float("inf") else -1,
            "remaining": remaining,
            "reset": reset_time
        }

quota_limiter = QuotaLimiter()