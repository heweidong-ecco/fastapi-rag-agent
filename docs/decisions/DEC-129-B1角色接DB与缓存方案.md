# DEC-129 · B1 —— 角色接 DB，以及**缓存方案**（TTL 60s + 写侧失效）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已落**（2026-10-09 · 分支 `feat/b1-role-from-db`） |
| **触发** | 业务方裁「**B1 · 加 `role` 列**」（`SECURITY.md` §3.2）；缓存方案业务方**当天当场定** |
| **类型** | 功能（`permission.py` 取值来源变更）+ **一处性能取舍** |
| **落点** | `app/access/permission.py` · `app/access/auth.py` · `app/core/db.py` · `app/routing/{schemas,api_v1}.py` · `scripts/issue_api_key.py` · `app/conftest.py` |
| **关联** | `DEC-033` 🅱️（后端先行 —— **已满足**）· `DEC-046` §遗留 4 · `DEC-056`（探针身份）· `DEC-085`/`DEC-086`（`api_keys` 加列的先例）· 施工单 `施工单-20261009-B1角色接DB.md` |

---

## 一 · 要解决的是什么

`get_user_role()` 原先**按用户名硬编码**（`admin` 特判 + 探针身份 + 其余 FREE）：
**换角色只能改代码**，且"谁是 premium"没有任何数据面。

📌 **挂起理由早已消失**：旧文写「挂起于 `DEC-033` 🅱️ 后端先行」，而那个前提**当时就满足了**。

---

## 二 · 决策点

### 2.1 🔴 缓存（**本 DEC 存在的理由**）

**背景**：接 DB 之后，不缓存 = **每请求最多 10 次同一条查询** ——
`token_tracker.get_user_token_budget`（**配额热路径**）·
`api_v1_agent` 一个请求 **7 处** admin 判定。而查的是一个**几乎不变**的值。

⚠️ 但 `app/access/specs/permission.md` §6 **明文写着不许加缓存**，理由是
「一旦缓存，`monkeypatch` 改角色对已经调过的代码路径就失效，**本仓大量用例靠这个机制**」。

| 备选 | 判断 |
|---|---|
| **甲（选，业务方裁）：进程内 TTL **60s** + 写侧主动失效** | ✅ |
| 乙：`@lru_cache`（无 TTL） | ⛔ **不选** —— **永不过期**：改角色要么重启进程、要么"**改了不生效且没人知道**" |
| 丙：纯 TTL、不做写侧失效 | ⛔ 不选 —— 改完**最多 60s 才生效**，而那种"改了没反应"看起来像 bug |
| 丁：Redis 缓存（跨进程一致） | ⛔ 不选 —— **每请求仍是一次网络往返**（只是 PG→Redis），**没解决本问题** |

**选甲的理由**：60s 足够挡掉热路径（命中即返回），又不引入"永不过期"；
**写侧主动失效**让"本进程内改角色"**当场生效**，TTL 只作为兜底。

### 2.2 原担心那条（"`monkeypatch` 会失效"）**实测成不成立**

🔴 **实测结论：那 3 处不受影响，而且理由不是"碰巧绿"** ——
`test_trace_cost.py:293` · `test_token_config.py:77` · `test_budget_soft_return.py:525`
**换的都是函数本身**（`setattr(<模块>, "get_user_role", <lambda>)`）⇒
**缓存活在被换掉的那个函数【里面】**，函数被整个替换，缓存**根本参与不进来**。

⚠️ **但它确实会在另一种情况下咬人**（改的是**输入**而不是函数），所以补了两道防护：
① **写侧失效**（`invalidate_role_cache`）· ② `app/conftest.py` 的 **autouse 清缓存**
（消掉"缓存跨用例残留 ⇒ 结论取决于执行顺序"）。

### 2.3 `role` 为 `NULL` 的含义 —— **回退**，⛔ 不是 `FREE`

那一列是**后加的、可空** ⇒ 老行**都是 `NULL`**。
**"没人写过"与"写了 free"不是一回事**：前者走**回退**（探针身份 + `admin` 特判）。
⛔ **别在任何写侧补 `or "free"`**（三处都有注释钉着）。

### 2.4 捕获范围 = **`psycopg2.Error`**，⛔ 不是 `except Exception`

🔴 **本仓对这条已有明文决定**（`app/access/auth.py:153` + 同款测试）。
宽捕获有两个后果，**第二个是我第一版真踩到的**：
① 把**代码 bug** 伪装成"库挂了"⇒ 真 bug 永远查不出来；
② **让 `test_rate_limit_identity.py::_no_db` 那道「不许碰库」守卫静默失效**
   —— 它靠抛 `AssertionError` 抓（📌 实测：`core.db.get_db` 被调了 1 次、异常被吞、守卫不报错）。

### 2.5 ⚠️ **未裁**：没有"改已有用户的角色"入口

两个入口（`issue_api_key.py --role` · `/admin/create_user` 的 `role`）**都是发新 key 时**写。
改现有用户的角色**目前只能再发一把**。⚠️ 这是**有意留着**还是**漏了**，**没有裁过**。

---

## 三 · 落地了什么 + 判据

| | |
|---|---|
| `api_keys.role TEXT`（**可空**） | 建表 DDL + **老库 `DO $$ … ALTER`**（⛔ 只改建表 ⇒ 老库永远补不上） |
| 🆕 `api_keys_user_name_idx` | ⚠️ `api_keys` **原本没有任何 `user_name` 索引**，而查角色正是按它 ⇒ 那是全表扫 |
| `get_user_role` | 查库 + TTL 60s 缓存 + **回退**（回退那套 = 原逻辑，**只有一份**） |
| 🆕 `invalidate_role_cache(user_name=None)` | 写侧用 |
| DB 访问收口 `_fetch_role_from_db()` | 收口在一处 ⇒ 测试可整体替换 + `_no_db` 守卫只需替换**同一个名字** |

**判据（都可打印）**：

```
pytest app/ -m "not integration and not needs_db" -q   ⇒ 933 passed / 2 skipped（基线 913 + 20 条）
pytest app/tests/test_user_role_from_db.py -q          ⇒ 19 passed
pytest app/tests/test_rate_limit_identity.py -q        ⇒ 9 passed（含新加的自证）
bash scripts/ci-local.sh                               ⇒ 退出码 0
```

🔴 **真服务验**（⚠️ 本仓「测试全过」⛔ 不算这条的凭证）：

```
/admin/create_user role=free     ⇒ /agent/token/budget ⇒ daily_budget = 10000
/admin/create_user role=premium  ⇒ 当场再查 ⇒ 100000        ← 🔴 进程内改 ⇒ 【当场生效】
```

🔴 **跨进程边界（实测，⛔ 不是推理）** —— 缓存活在**服务进程**里，CLI 是**另一个进程**：

```
CLI 发 role=free     ⇒ 查额度 = 10000
CLI 改 role=premium  ⇒ 立刻再查 = 10000   ← ⚠️ 服务进程缓存未失效
（等过 TTL 61s）     ⇒ 再查     = 100000  ← TTL 兜底生效
```

⇒ **进程内改 = 当场生效；跨进程改 = 最多一个 TTL(60s)**。
📄 已写进 `permission.py` 的 `invalidate_role_cache` docstring 与 spec。

---

## 四 · 反悔成本

| 反悔 | 成本 |
|---|---|
| **缓存方案**（甲→乙/丙/丁） | **低** —— 改一个常量 + `get_user_role` 十来行；用例已有 10 条专门钉缓存 |
| **TTL 调长短** | **极低**（改 `ROLE_CACHE_TTL_SECONDS`） |
| **整个 B1 退回**（角色又变回硬编码） | **低** —— `get_user_role` 只留回退那一段即可；⚠️ 但**列留着无害**（读侧不认它就等于没有） |
| **DB 回滚** | `ALTER TABLE api_keys DROP COLUMN IF EXISTS role`（⚠️ **会丢掉已写的角色**） |

---

## 五 · 遗留

1. ⛔ **没有"改已有用户角色"的入口**（§2.5）—— **未裁**。
2. ⚠️ **写侧不校验取值**（`role` 是 TEXT）⇒ 脏值能写进去，**读侧靠回退兜**。
   ⛔ 这是**有意的**（多一处白名单 = 多一处会与 `UserRole` 分叉的事实源），但它是一条**债**。
3. ⚠️ **多 worker 时跨进程最多陈旧一个 TTL** —— ✅ **已实测**（§三），
   ⛔ **不是缺陷，是有意的取舍**；要更实时得上 Redis 广播，而那是**另一个方向的开销**。
4. ⚠️ **`alembic` 没装 ⇒ 本笔的迁移文件【本机没跑过】** ⇒ 登记 `docs/待办总表.md` **`N22`**。
