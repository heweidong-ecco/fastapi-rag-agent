from enum import Enum

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


# 🔒 2026-10-03 · **隔离探针身份**（`DEC-056` §七 裁决 1 · 决策 2）
#
# 业务方 2026-10-03 原话：「**在对应代码位置注释或者写文档记录这几个用户身份**」——
# 就是下面这三个。⚠️ **它们是【测试身份】，⛔ 不是业务角色。**
#
#   · `isolation_a` / `isolation_b` —— **同角色**那一档（都是 FREE）互不串
#   · `isolation_c`                —— **跨角色**那一档（PREMIUM vs FREE）互不串
#   · `test_user`                  —— 历史沿用，与 `isolation_c` 同属 PREMIUM 探针
#
# 用途：验证多用户资源隔离，用例在 `app/tests/test_isolation.py`。
# 身份记录（业务方要的"留档"）= **本注释** + `docs/decisions/DEC-056-多用户资源隔离的现状审计与分阶段收口.md`，
# ⛔ **不另开文件**（`DEC-056` 决策 2）。
#
# ⚠️ `isolation_a` / `isolation_b` **不在这里列** —— 它们走默认分支拿 FREE。
#    用例里有反向守卫钉住这一点（⛔ 别把默认分支改成 PREMIUM）。
#
# ⛔ **别删**（删了 `DEC-056` §六 的判据跑不起来）；⛔ **别当成真业务角色**（它们没有业务含义）。
# ⚠️ 这张表的正式出路是**接 DB**（`DEC-046` §遗留 4），届时要**连这段注释一起搬**。
_PREMIUM_PROBE_USERS = {"test_user", "isolation_c"}


def get_user_role(user_name: str) -> UserRole:
    """根据用户名获取角色。

    ⚠️ 现在仍是硬编码（`admin` 特判 + 探针身份特判，其余 FREE）。
    🔴 2026-10-03 更正：原先这里写「接 DB 的落点是 **B9/R1.3**」——
        **`R1.3` 当天已随 `DEC-046` 落地**（配额那层已改挂 token 口径），
        所以这个前置**变了**，⛔ 别照旧读。接 DB 这件事仍**挂起**（`DEC-033` 🅱️ 后端先行）。
        📄 重新挂在哪里 ⇒ `DEC-046` §遗留 4。

    🔴 2026-10-03 补：`isolation_c` 是**测试身份**，加它是为了能测「跨角色」那一档的隔离
        （`DEC-056` §七 裁决 1）。⛔ 别把它读成"premium 用户的代表" —— 它没有业务含义。
    """
    if user_name == "admin":
        return UserRole.ADMIN
    if user_name in _PREMIUM_PROBE_USERS:
        return UserRole.PREMIUM
    return UserRole.FREE
