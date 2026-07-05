from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    FREE = "free"           # 免费用户：每天100次
    PREMIUM = "premium"     # 付费用户：每天10000次
    ADMIN = "admin"         # 管理员：不限次


# 不同角色的每日调用限额
ROLE_QUOTA = {
    UserRole.FREE: 100,
    UserRole.PREMIUM: 10000,
    UserRole.ADMIN: float("inf"),  # 无限
}


def get_user_role(user_name: str) -> UserRole:
    """
    根据用户名获取角色。
    当前为模拟版本，实际应从数据库查询。
    """
    # 模拟：admin 是管理员，test_user 是付费用户，其他都是免费用户
    if user_name == "admin":
        return UserRole.ADMIN
    elif user_name == "test_user":
        return UserRole.PREMIUM
    else:
        return UserRole.FREE


def get_user_quota(user_name: str) -> int:
    """获取用户的每日调用限额"""
    role = get_user_role(user_name)
    return ROLE_QUOTA[role]