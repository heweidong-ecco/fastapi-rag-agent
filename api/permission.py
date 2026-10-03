from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    ADMIN = "admin"


# 🔴 2026-10-03 删（决策一落地 · `DEC-040` / `DEC-046`）：
#    此处原有 `ROLE_QUOTA = {FREE: 100, PREMIUM: 10000, ADMIN: inf}` 与 `get_user_quota()`。
#    那是**一套独立的「每日请求次数」配额**，与 `token_config.ROLE_DAILY_TOKEN`（token）
#    **互不知情** —— `DEC-029` 实测两者口径**差 35 倍**（`plan_execute` 一次 ~3346 token
#    ⇒ 按次数能跑 100 次、按 token 只能跑 ~3 次）。
#    ⇒ 业务方裁「**统一到 token 一套**」⇒ 次数那套**整张表连入口一起删**。
#    ⚠️ 配额表在 `token_config.ROLE_DAILY_TOKEN`；判定在 `token_tracker`，
#       全路径那层挂在 `main.QuotaMiddleware` 上（= `R1.3`）。
#    ⚠️ 注意：`DEC-040` 原写「降级为**接口权重**、**不删**」—— **该条已被 `DEC-046` 推翻**。


def get_user_role(user_name: str) -> UserRole:
    """根据用户名获取角色。

    ⚠️ 现在仍是硬编码（`admin` / `test_user` 特判，其余 FREE）。
    🔴 2026-10-03 更正：原先这里写「接 DB 的落点是 **B9/R1.3**」——
        **`R1.3` 当天已随 `DEC-046` 落地**（配额那层已改挂 token 口径），
        所以这个前置**变了**，⛔ 别照旧读。接 DB 这件事仍**挂起**（`DEC-033` 🅱️ 后端先行）。
        📄 重新挂在哪里 ⇒ `DEC-046` §遗留 4。
    """
    if user_name == "admin":
        return UserRole.ADMIN
    elif user_name == "test_user":
        return UserRole.PREMIUM
    else:
        return UserRole.FREE
