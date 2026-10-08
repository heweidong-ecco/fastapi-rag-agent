# `api/permission.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用 —— 但它是【硬编码】的**：`admin` 特判 + 探针身份特判，其余一律 `FREE`。⛔ **接 DB 这件事仍挂起** |
| **对外提供** | `UserRole`（`str, Enum`：`FREE` / `PREMIUM` / `ADMIN`）· `get_user_role(user_name) -> UserRole` |
| **谁在用** | **8 处**：`deps.py:76`（`require_admin`）· `api_v1.py:220` · `api_v1_rag.py:362` · `api_v1_agent.py` **5 处**（`:525 :725 :802 :2035 :2098 :2133 :2146`）· `token_tracker.py:495`（按角色取日额度） |
| **测试** | `api/test_isolation.py` · `api/test_pending_visibility.py` · `api/test_approve_ownership.py` · `api/test_trace_isolation.py` · `api/test_quota_middleware.py` · `api/test_token_config.py`（**都是间接测**，⛔ 没有"角色判定"自己的用例） |

## ✅ 做了什么

一个**三角色**的判定函数 + 一张**测试身份表**。

```python
def get_user_role(user_name: str) -> UserRole:
    if user_name == "admin":                       # ① 特判字面量 "admin"
        return UserRole.ADMIN
    if user_name in _PREMIUM_PROBE_USERS:          # ② 特判探针身份
        return UserRole.PREMIUM
    return UserRole.FREE                           # ③ 其余全 FREE
```

**它是「多用户隔离」的判据来源之一**（`DEC-056`）—— `ADMIN` 是**跨用户可见**的那个例外，
所以 8 个调用点里**大半是**「本人 or admin」这种归属校验的**后半句**。

## 🟡 做到哪 / 缺什么

| 缺口 | 说明 |
|---|---|
| 🔴 **角色表没接 DB** | 🔴 **这件事【挂起】**，理由：`DEC-033` 🅱️「**后端先行**」。⚠️ **别照旧文的落点找** —— `DEC-040` 原文写「接 DB 的落点是 `B9`/`R1.3`」，而 **`R1.3` 当天已随 `DEC-046` 落地**（配额改挂 token 口径）⇒ 那个前置**变了**。重新挂在 `DEC-046` §遗留 4 |
| ⚠️ **没有"改角色"的入口** | 没有 API、没有表 ⇒ 换角色**只能改代码**（`_PREMIUM_PROBE_USERS` 那个集合） |
| ⚠️ **没有"不存在的用户"这一档** | 任何没被特判的字符串**都是 FREE**，包括拼错的用户名 ⇒ 见 §⚠️ 第 1 条 |

## ⚠️ 看代码会误判的地方

> ⭐ 这一节是整份 spec 的价值所在 —— 前面两节读代码也能推出来，这一节**推不出来**。

### 1. 🔴 **未知用户名 ⇒ `FREE`，⛔ 不是报错** —— 这是 fail-**open**，刻意的

函数**不查库、不抛异常**：任何没被特判的名字都拿 `FREE`。
⇒ **拼错一个用户名不会失败，只会降级成 free** —— 而 `FREE` 是有额度上限的，
所以症状是**"这个人莫名其妙被限额了"**，⛔ **不是**一条报错。

⚠️ 与 `api/deps.py` 的鉴权**方向相反**：那里未知凭据是 **fail-closed**（401）。
⇒ **别把两处的取向记混**：**"你是谁"必须 fail-closed；"你是什么档"允许 fail-open。**

### 2. 🔴 `isolation_a` / `isolation_b` **不在本文件的表里** —— ⛔ 别去补

它们**故意不列**：走默认分支拿 `FREE`。那正是「**同角色**那一档」的测法
（两个都是 FREE 的账号，互相看不见对方的东西）。

🔒 **用例里有反向守卫钉住这一点** —— ⛔ **别把默认分支改成 `PREMIUM`**：那会让"同角色隔离"那个用例
**静默失去意义**（两边都变 PREMIUM，测的还是同角色 —— 但已经不是它想测的那一档了）。

### 3. 🔴 `isolation_c` / `test_user` 是**【测试身份】，⛔ 不是业务角色**

业务方 2026-10-03 原话：「**在对应代码位置注释或者写文档记录这几个用户身份**」——就是下面这三个：

| 身份 | 属于哪一档 |
|---|---|
| `isolation_a` / `isolation_b` | **同角色**（都是 FREE）互不串 |
| `isolation_c` | **跨角色**（PREMIUM vs FREE）互不串 |
| `test_user` | 历史沿用，与 `isolation_c` 同属 PREMIUM 探针 |

⛔ **别把 `isolation_c` 读成"premium 用户的代表"** —— 它**没有业务含义**，只是为了让"跨角色"那一档**测得出来**。
⛔ **也别删它**（删了 `DEC-056` §六 的判据**跑不起来**）。

> 📌 **"留档"这件事本身**（业务方要的）= **本注释** + `DEC-056`，⛔ **不另开文件**（`DEC-056` 决策 2）。

### 4. 🔴 那张**次数配额表已删** —— 看 git 历史会看到它，⛔ 别以为还在

本文件原先有 `ROLE_QUOTA = {FREE: 100, PREMIUM: 10000, ADMIN: inf}` 与 `get_user_quota()`。
**2026-10-03 整张表连入口一起删**（`DEC-040` → `DEC-046`）。

**删的理由（判据可打印）**：那是**一套独立的「每日请求次数」配额**，与 `token_config.ROLE_DAILY_TOKEN`（token）
**互不知情** —— `DEC-029` 实测**两者口径差 35 倍**（`plan_execute` 一次 ~3346 token ⇒ 按次数能跑 100 次、按 token 只能跑 ~3 次）。

⚠️ **`DEC-040` 原写「降级为接口权重、不删」—— 该条已被 `DEC-046` 推翻。**
⚠️ **配额表现在的家在 `token_config.ROLE_DAILY_TOKEN`**，判定在 `token_tracker`，全路径那层挂在 `main.QuotaMiddleware`。

### 5. ⚠️ `UserRole` 是 `str, Enum` ⇒ 与字符串键**直接可比**

所以 `token_config` 里那张表**用字符串当键**（`"free"` / `"premium"` / `"admin"`）也能对上。
⚠️ 代价：**写错字符串不会报错**，只会**查不到** ⇒ 见 `docs/specs/token_config.md`。

### 6. ⚠️ 函数**每次调用都重新判**，没有缓存

`get_user_role` 无 `lru_cache`。⚠️ **看着像"该缓存没加"，其实是有意的**：一旦缓存，
`monkeypatch` 改角色对**已经调过**的代码路径就失效，本仓大量用例靠这个机制。
⇒ ⛔ **别顺手加 `@lru_cache`**。

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/deps.md` | `require_admin` 怎么用它（**fail-closed** 的那一侧） |
| `docs/specs/token_config.md` | `ROLE_DAILY_TOKEN` —— 角色**真正影响的东西**（额度） |
| `docs/specs/token_tracker.md` | 按角色取额度的调用点（`:495`） |
| `docs/decisions/DEC-056-多用户资源隔离的现状审计与分阶段收口.md` | 三角色与探针身份的**来由**；接 DB 的挂起点 |
| `docs/decisions/DEC-046-决策一落地撤次数配额改用token口径.md` | §⚠️ 第 4 条的裁定 + §遗留 4（接 DB 的新落点） |
| `docs/decisions/DEC-040-额度统一到token一套.md` | 去掉 `admin: inf`（**部分被 `DEC-046` 推翻**） |
