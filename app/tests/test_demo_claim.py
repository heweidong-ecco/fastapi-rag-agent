"""demo 访客凭据那条端点的守卫（`DEC-143` · 施工单第 6 步）。

## 本文件钉的四件事（**只有它会红**）

| # | 钉什么 | ⛔ 不钉会怎样 |
|---|---|---|
| 1 | 🔴 **本仓那条路（`main:app`）上【没有】这条路由** | 「**默认 = 完整版**」就成了**一句口号** —— 谁都能顺手把它挂进本仓 |
| 2 | 🔴 **那条路由本身是**公开**的、且 `demo_main` 真的把它挂上去了** | 它是公开的这件事**只在这里成立**（⛔ 无鉴权基线扫不到它）；而"挂上去了"是**接线**，接线坏了没有任何行为判据会红 |
| 3 | **`visitor_id` 形状不对 ⇒ 422** | 它会被**拼进 `user_name`** ⇒ 不校验就是往库里灌任意垃圾 |
| 4 | **撤销只写 `0`（⛔ 不写 `NULL`）** | 读侧 `COALESCE(is_active, 1) = 1` ⇒ **`NULL` 当激活** ⇒ 写 `NULL` = **没撤销**，而界面上会说"已撤销" |

## 🔴🔴 为什么这里【不用子进程】—— 一条实测出来的硬约束

「跑两个解释器，一个 import `main`、一个 import `demo_main`」本来是最自然的写法
（`demo_main` 干的是 `app.include_router(...)`，**它改的是 `main.app` 这个对象本身**，
所以**同进程里两条路验不了**）。**但这条路走不通**，原因是：

⚠️ **`main` 一被 import，就会拉起 `agent.memory_store` ⇒ `mem0` ⇒ 一个本地 Qdrant 客户端
（单实例锁）**。而 pytest 这个会话**本身**已经 import 过 `main` ⇒ **父进程攥着那把锁**
⇒ 任何**第二个**想 import `main` 的进程都当场死在：

```
RuntimeError: Storage folder … is already accessed by another instance of Qdrant client
```

⇒ 实测过：**同一个子进程命令，单独跑成功、在 pytest 里跑必失败**。
⇒ 所以「子进程」在这个仓里**不是一个可用的判据手段**（至少对任何要 import `main` 的东西）。

**改成什么**：

- **第 1 条**走**同进程**（pytest 自己这个进程里 `main.app` 就是本仓那个 app），
  🔴 并且**明写一条前置断言**：本进程⛔ 没人 import 过 `demo_main` —— 有人 import 过，
  路由表就被就地改过，**这条判据当场失效**（宁可红，⛔ 不许静静放过）。
- **第 2 条**拆成两半：**路由自己**在**一次性 app** 上验（不碰 `main`）；
  **"挂上去了"** 用 **AST** 读 `demo_main.py`（⛔ 不是子串匹配 —— 那会数到注释和字符串）。
  ⚠️ **这一半比"真跑一遍"弱**，如实记在这里：它证的是"代码里挂了"，
  ⛔ 不是"挂上去之后能跑通"（后者要真服务，见下面那条判据）。

⛔ 本文件**不连库**（`DEC-058`）—— 4 条判据一条都不需要真库：
   · #1/#2 看路由表与源码 · #3 在**校验层**就被拦下 · #4 用**假连接**收 SQL。

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_demo_claim.py -q -p no:warnings`

## ⚠️ 还有一条判据【不在本文件里】—— 它在真服务上

「demo 那条路真的能领到凭据」这件事**必须起真服务验**（本仓纪律：每刀起真服务 + 点一次）。
2026-10-10 实测过一轮：领一把 200 · 旧凭据被撤后 401 · 新凭据 200 · 形状不对 422 ·
库里该访客名下 `is_active=1` 的只有 1 条。
"""
import ast
import asyncio
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.exceptions import AppException
from demo.claim import _VISITOR_ID_RE, _VISITOR_KEY_DAYS, _revoke, router
from main import app as repo_app
from main import app_exception_handler

#: 仓根（`app/tests/` 往上两层）—— 用来定位那个基线文件与 `demo_main.py`。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: `app/` 那层。
_APP_DIR = os.path.join(_REPO_ROOT, "app")

_CLAIM_PATH = "/api/v1/demo/claim"
_BASELINE = os.path.join(_REPO_ROOT, "scripts", "route-auth-baseline.txt")
_DEMO_ENTRY = os.path.join(_APP_DIR, "demo_main.py")

#: 本仓那几个【鉴权依赖】的名字。⚠️ 改 `app/access/` 时这里是第二处，要一起动。
_AUTH_DEPS = {"get_current_user_hybrid", "require_admin", "require_ws_user"}


def _walk(routes):
    """把路由表**递归**走一遍。

    ⚠️ `app.routes` **不是平的** —— `include_router` 造出来的是 `_IncludedRouter` 那类壳，
    真要找的 `APIRoute` 在它的 `original_router.routes` 里。
    🔴 本仓在这一条上**栽过两次**（判据报"没有这条路由"，而路由明明在）。
    """
    for r in routes:
        yield r
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _walk(inner.routes)
        sub = getattr(r, "routes", None)
        if sub:
            yield from _walk(sub)


def _find_route(app, path):
    for r in _walk(app.routes):
        if getattr(r, "path", None) == path:
            return r
    return None


def _dep_names(route):
    """这条路由挂了哪些依赖（按函数名）。"""
    dep = getattr(route, "dependant", None)
    out = []
    for d in (getattr(dep, "dependencies", None) or []):
        out.append(getattr(getattr(d, "call", None), "__name__", repr(d.call)))
    return sorted(out)


def _throwaway_app():
    """一个只挂 demo 那条路由的**一次性** app。

    ⚠️ 用它而不是 `demo_main.app`：后者是**就地改过的 `main.app`**，
       而 import `demo_main` 会**污染整个 pytest 会话**（见文件头）。
    ⚠️ 把 `main` 的异常处理器一起挂上 —— 不然 `AppException` 不会被翻译成 422，
       测试里会看到**原始异常**而不是响应（本仓 422 的映射在 `core/exceptions.py`）。
    """
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.include_router(router)
    return app


# ══════════════ 1 · 🔴 「默认 = 完整版」的判据 ══════════════


def test_repo_entry_has_no_demo_route():
    """🔴 **本仓那条路（`main:app`）上【没有】这条路由**（`DEC-142` 第 1 条 · `DEC-143` 判据 1）。

    这是「**不设环境变量 ⇒ 行为与今天逐字一致**」的**唯一**可打印判据。
    ⚠️ 它**不是**靠 `os.getenv` 判断的，**是靠结构** —— 本仓那条路上**压根没有 `demo/` 这个包**
    （`main.py` ⛔ 不 import 它）。📌 本仓立场：「**只有文字就漏，结构才执行**」。

    🔴 **前置断言不是客套**：本进程里只要有人 import 过 `demo_main`，
    `main.app` 就被**就地**加上了那条路由 —— 那时这条判据**测的是别的东西**，
    而且会以一个**看起来像"回归"**的假信号红给你。宁可当场点破。
    """
    assert "demo_main" not in sys.modules, (
        "本进程里已经有人 import 过 `demo_main` ⇒ `main.app` 被**就地**改过了，"
        "这条判据【当场失效】。\n"
        "⛔ 别在本进程 import 它（`demo_main` 会 append 到共享的 `main.app` 上）—— 见文件头。"
    )
    assert _find_route(repo_app, _CLAIM_PATH) is None, (
        f"🔴 本仓那条路（`main:app`）上**出现了** `{_CLAIM_PATH}` —— "
        "「默认 = 完整版」被破了。\n"
        "⇒ demo 的东西只能挂在 `demo_main.py` 那个入口上（业务方 2026-10-10 裁的「甲」）。\n"
        "⚠️ ⛔ 别用「包一层开关门控」来绕 —— 那看着像「默认不变」，"
        "实际仍是 demo 长进了本仓，同一天已经被回滚过一次。"
    )


# ══════════════ 2 · 那条路由是【公开】的，而且真的被挂上去了 ══════════════


def test_the_claim_route_is_public_and_post_only():
    """🔴 **它是公开的（无鉴权）、且只有 POST**（`DEC-143` 判据 3 的另一半）。

    **为什么「公开」这件事只有这里验得到**：无鉴权基线（`scripts/route-auth-baseline.txt`）
    是**静态文件、没有"环境"这一维**，而 `check_route_auth.py` 扫的是**本仓那条路** ——
    那条路上**这条路由压根不存在** ⇒ **扫不到它**。
    ⇒ 所以⛔ **别把它写进基线**（看着"整齐"，实际是给一条扫不到的路由立规矩）。

    ⚠️ 「无鉴权」的判据是【**没挂鉴权那几个**】，⛔ 不是「一个依赖都没有」——
       将来挂个限流之类的**不该**让这条红（那会把"无鉴权"和"无依赖"混成一件事）。
    """
    route = _find_route(_throwaway_app(), _CLAIM_PATH)
    assert route is not None, "把 `demo/claim.py` 的 router 挂在一个空 app 上，居然找不到这条路由"
    assert sorted(getattr(route, "methods", None) or []) == ["POST"], (
        f"它该只有 POST，实际 {sorted(getattr(route, 'methods', None) or [])}"
    )

    leaked = sorted(set(_dep_names(route)) & _AUTH_DEPS)
    assert not leaked, (
        f"`{_CLAIM_PATH}` 上挂了鉴权依赖 {leaked} ⇒ **访客领不到凭据**"
        "（他手里本来就什么都没有 —— 这正是「第一个拿到凭据」那条路）。"
    )


def test_demo_entry_really_mounts_that_router():
    """🔴 **`demo_main.py` 真的把那条 router 挂上去了** —— 这是**接线**，不是行为。

    ⚠️ **为什么单独立一条**：`demo_main.py` 是本仓唯一把 demo 挂上去的地方；
    有人把它那**两行**删了/改名了，**上面所有判据照样全绿**
    （router 文件还在、测试里那个一次性 app 照样能挂上），
    而 **demo 那条路上访客再也领不到凭据**。
    📄 本仓为此专门记过一份复盘：`docs/复盘/2026-10-09-测试全绿而活路径坏了两次.md`
    （**测试覆盖的是「行为」，坏掉的是「接线」**）。

    ⚠️ 判据用 **AST**（真解析），⛔ **不是子串匹配** ——
    子串会数到注释和字符串里的同名文字（本仓 `N14` 那一族）。
    """
    tree = ast.parse(open(_DEMO_ENTRY, encoding="utf-8").read())

    # ① 要有 `from demo.claim import router as <某个名字>`
    aliases = [
        (a.asname or a.name)
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "demo.claim"
        for a in n.names
        if a.name == "router"
    ]
    assert aliases, (
        "`demo_main.py` 里没有 `from demo.claim import router` ⇒ 那条路由根本进不了 demo 的入口"
    )

    # ② 要真的把它 `include_router` 进 app（⛔ 光 import 不挂，等于没挂）
    mounted = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "include_router"
        and n.args
        and isinstance(n.args[0], ast.Name)
        and n.args[0].id in aliases
    ]
    assert mounted, (
        f"`demo_main.py` import 了 {aliases} 却**没有** `app.include_router(...)` 它 —— "
        "光 import 不挂 = 没挂（`sys.modules` 里有了，路由表里没有）"
    )


def test_the_public_route_is_not_written_into_the_unauth_baseline():
    """🔴 **⛔ 别把它写进无鉴权基线**（施工单第 2 步点名的那一条）。

    **为什么**：那份基线是**静态文件、没有"环境"这一维**；而 `check_route_auth.py` 扫的是
    **本仓那条路**（`main:app`）—— 那条路上**这条路由压根不存在**。
    ⇒ 写进去 = 给一条**扫不到的路由**立规矩；哪天它的挂载点变了，基线还是"一致"的，
      **而门什么都不会说**（本仓立场：「**从不命中**」与「没人违规」在机器痕迹上完全一样）。

    ⚠️ 反证：往 `scripts/route-auth-baseline.txt` 里加一行含 `demo/claim` 的 ⇒ 本条立刻红。
    """
    with open(_BASELINE, encoding="utf-8") as f:
        lines = f.readlines()
    assert lines, "基线文件是空的 —— 本用例的扫描前提不成立"
    hits = [ln.strip() for ln in lines if "demo/claim" in ln and not ln.lstrip().startswith("#")]
    assert not hits, (
        f"无鉴权基线里出现了 demo 那条路由：{hits}\n"
        "⇒ 它是**静态文件**、扫的是本仓那条路（那条路上它不存在）⇒ 写进去只会让门变瞎。"
    )


# ══════════════ 3 · 🔴 visitor_id 的形状（它会拼进 user_name）══════════════


def test_visitor_id_regex_accepts_what_the_frontend_generates():
    """⚠️ **这条是下面那条的【正控】** —— ⛔ 少了它，「坏形状都回 422」**用"全拒"也能过**。

    🔴 它钉的是一个**真会发出来的**形状：前端用 `crypto.randomUUID()` 生成的串
    （`8-4-4-4-12` 十六进制 + 连字符）⇒ 必须落在这条正则里。
    正则一旦"收紧"到拒掉它，页面那边**不报错**，只表现为**永远退回"自己填"**。
    📄 前端那一侧：`app/static/js/session.js` 的 `visitorId()`。
    """
    good = [
        "abcdefgh",                                                  # 下界：8 位
        "887fcbbad5cc46a9a6d55a3d929b813d",                          # `randomUUID()` 去掉连字符
        "887fcbba-d5cc-46a9-a6d5-5a3d929b813d",                      # ⚠️ 连字符也留着的那种写法
        "a" * 64,                                                    # 上界：64 位
        "A-Z_0-9a-z-",                                               # 四类字符都收
    ]
    for v in good:
        assert _VISITOR_ID_RE.fullmatch(v), (
            f"「{v}」是前端会发出来的形状，却被拒了 ⇒ 访客永远领不到凭据（而不报错）"
        )

    bad = [
        "",                    # 空
        "a" * 7,               # 低于 8 位
        "a" * 65,              # 高于 64 位
        "演示-visitor",         # ⛔ 中文（会拼进 user_name）
        "abcdefg'h",           # ⛔ 引号
        "abcdefg;DROP",        # ⛔ 分号
        "abcd efgh",           # ⛔ 空格
        "abcdefg\n",           # ⛔ 换行
        "abcdefg%00",          # ⛔ 百分号
    ]
    for v in bad:
        assert not _VISITOR_ID_RE.fullmatch(v), f"「{v!r}」会被拼进 user_name，⛔ 不该放它过去"


def test_claim_rejects_a_bad_visitor_id_with_422():
    """🔴 **形状不对 ⇒ 422**（⛔ 不是 400 —— 本仓 `ErrorCode.PARAM_INVALID` 映射 **422**）。

    ⚠️ 这条**在【校验层】就结束**，碰不到库 ⇒ 所以不需要 `needs_db`（`DEC-058`）。
       判据本身也顺便证明了这件事：坏形状拿到的是 **422**，⛔ 不是 500
       （**500 才说明它真去连库了**）。
    ⚠️ 反证：把 `demo_claim` 里那段校验删掉 ⇒ 本条立刻红（会变成 500 或直接抛异常）。
    """
    client = TestClient(_throwaway_app())

    for bad in ["", "b", "演示-visitor", "x" * 65, "abc defgh", "abcdefg;DROP"]:
        r = client.post(_CLAIM_PATH, json={"visitor_id": bad})
        assert r.status_code == 422, (
            f"`visitor_id={bad!r}` 该被拦在校验层（422），实际 {r.status_code}：{r.text[:200]}\n"
            "⚠️ 422 而不是 400：`app/core/exceptions.py` 把 `PARAM_INVALID` 映射成 422。"
        )

    # ⚠️ 缺字段走同一条路（Pydantic 自己给 422）—— 顺带证明这个 app 真的接上了处理器
    assert client.post(_CLAIM_PATH, json={}).status_code == 422


# ══════════════ 4 · 🔴 撤销只写 0（⛔ 不写 NULL）══════════════


class _FakeCursor:
    """假游标：**把 SQL 抄下来**，其余什么都不做（⛔ 不连库）。"""

    def __init__(self, log, rowcount):
        self._log = log
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._log.append((" ".join(str(sql).split()), params))


class _FakeConn:
    def __init__(self, log, rowcount):
        self._log = log
        self._rowcount = rowcount
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _FakeCursor(self._log, self._rowcount)

    def commit(self):
        self.committed = True


def _run_revoke(monkeypatch, rowcount=2):
    """把 `_revoke` 跑一遍，但**连接是假的** —— 只收它执行的 SQL 与参数。"""
    log = []
    conn = _FakeConn(log, rowcount)
    monkeypatch.setattr("demo.claim.get_db", lambda: conn)
    n = _revoke("demo-abcdefgh")
    return log, conn, n


def test_revoke_writes_zero_not_null(monkeypatch):
    """🔴 **撤销写的是 `0`，⛔ 不是 `NULL`** —— 这一条错了，页面上会**打着"已撤销"而其实没撤**。

    **为什么**：读侧的判据是 `COALESCE(is_active, 1) = 1`（**`NULL` 当激活**）⇒
    写 `NULL` 等于**没撤销**，而**没有任何一层会报错**。

    ⚠️ 反证：把那条 `SET` 改成 `is_active = NULL` ⇒ 本条立刻红。
    ⚠️ 用**假连接**（⛔ 不连库）是有意的：`needs_db` 的用例**不进 CI**，
       而这条要守的恰恰是"有人顺手改了一行 SQL"—— **必须每天跑得到**。
    """
    log, conn, n = _run_revoke(monkeypatch, rowcount=2)

    assert len(log) == 1, f"`_revoke` 该只执行一条 SQL，实际 {len(log)} 条：{log}"
    sql, params = log[0]

    assert "is_active = 0" in sql, (
        f"撤销那句没有把 `is_active` 写成 `0` ⇒ 读侧会当成【还活着】。实际 SQL：{sql}"
    )
    assert "NULL" not in sql.upper(), (
        f"撤销那句里出现了 `NULL` —— 读侧 `COALESCE(is_active, 1) = 1` 把 `NULL` 当**激活**，"
        f"所以写 `NULL` = **根本没撤销**，而页面上会说「已撤销」。实际 SQL：{sql}"
    )
    assert "COALESCE(is_active, 1) = 1" in sql, (
        f"少了那个条件 ⇒ `rowcount` 会把「本来就是 0 的那些」也算进去，**报数虚高**。实际 SQL：{sql}"
    )
    assert params == ("demo-abcdefgh",), (
        f"参数该只有那一个 user_name（⛔ 别拼进 SQL 文本 —— 那是注入面）。实际：{params!r}"
    )
    assert conn.committed, "改完没 `commit` ⇒ 连接一关改动就没了（而函数照样返回成功）"
    assert n == 2, "`_revoke` 该把影响行数原样交回去（调用方靠它判断撤没撤到）"


def test_revoke_targets_only_that_one_visitor(monkeypatch):
    """🔴 **它只动【那一个访客】名下的** —— 少一个 `WHERE` 就是把全站凭据一次撤光。

    ⚠️ 与上一条**分开写**是有意的：上一条看的是「写什么值」，这条看的是「**打谁**」，
       而改错这两处的后果完全不同（一个是没撤，一个是**把所有人踢下线**）。
    """
    log, _conn, _n = _run_revoke(monkeypatch)
    sql, params = log[0]
    assert "WHERE user_name = %s" in sql, (
        f"没有按 `user_name` 限定 ⇒ 会撤到别人头上。实际 SQL：{sql}"
    )
    assert params == ("demo-abcdefgh",)


def test_claim_key_lifetime_is_short_and_explicit(monkeypatch):
    """⚠️ 有效期是**写死的 7 天**（比本机脚本的 30 天短 —— `claim.py` 的常量注释里说了为什么）。

    这条钉的是「**别让它悄悄变成 30 天**」：访客的凭据本来就"换个浏览器就换一把"。
    ⚠️ 它**不判这个数好不好** —— 那是 `DEC-098 §二·4` 的事，⛔ 别在这里替它裁。
    """
    assert _VISITOR_KEY_DAYS == 7, (
        f"访客凭据的有效期成了 {_VISITOR_KEY_DAYS} 天 —— 改它要有理由（见 `claim.py` 的常量注释）"
    )
    seen = {}

    def _fake_create(user_name, expire_days=None, role=None):
        seen.update(user_name=user_name, expire_days=expire_days, role=role)
        return "sk-fake"

    monkeypatch.setattr("demo.claim.create_user_api_key", _fake_create)
    monkeypatch.setattr("demo.claim.get_db", lambda: _FakeConn([], 0))

    from demo.claim import ClaimRequest, demo_claim

    got = asyncio.run(demo_claim(ClaimRequest(visitor_id="abcdefgh")))

    assert seen["user_name"] == "demo-abcdefgh", f"user_name 该是 `demo-<访客标识>`，实际 {seen}"
    assert seen["expire_days"] == _VISITOR_KEY_DAYS
    # 🔴 `role` **刻意不传** ⇒ 库里写 NULL ⇒ 读侧回退成非 admin。
    #    ⛔ **别填 `"free"`** —— `create_user_api_key` 的 docstring 明写：
    #    「别给它一个默认值，那会把『没写』与『写了 free』变成同一件事」。
    assert seen["role"] is None, (
        f"`role` 被填成了 {seen['role']!r} —— 它该【不传】（⇒ 库里 NULL ⇒ 读侧回退）"
    )
    assert got["api_key"] == "sk-fake" and got["user_name"] == "demo-abcdefgh"


def test_the_demo_module_only_uses_the_public_function_of_the_repo_auth():
    """⚠️ **记账型**守卫：demo 那条路⛔ 不许把本仓那三个共享文件拖下水。

    本仓那三个文件（`app/main.py` · `app/access/auth.py` · `scripts/issue_api_key.py`）
    是业务方 2026-10-10 裁的**红线** —— 它们就是「甲」的全部内容。
    ⚠️ 这里只钉**本模块的 import 面**：发凭据这件事**只能**走 `access/auth.py` 那个
    【公开】函数；换任何别的方式（自己拼 SQL 发、去调 `_` 开头的内部件、
    去 `main.py` 里加东西）都意味着**红线被动了**。
    """
    src = open(os.path.join(_APP_DIR, "demo", "claim.py"), encoding="utf-8").read()
    assert "from access.auth import create_user_api_key" in src, (
        "它该用 `access/auth.py` 那个【公开】函数发凭据 —— "
        "换别的方式就意味着那道红线（那三个共享文件）被动了"
    )
    tree = ast.parse(src)
    # 🔴 **两种写法都要认** —— `from main import x` 是 `ImportFrom`，`import main` 是 `Import`。
    #    ⚠️ **本条的初版只认前者** —— 2026-10-10 拿 `import main` 做反证时**没红**才发现。
    #    （本仓立场：**反证检验就是为了抓这个** —— 判据写窄了，它不会喊。）
    deps = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            deps += [a.name for a in n.names if (a.name or "").split(".")[0] == "main"]
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] == "main":
                deps.append(n.module)
    assert not deps, (
        f"demo 的模块去 import 本仓的入口了（{deps}）⇒ 依赖方向反了"
        "（该是 `demo_main` 去 import `main`，⛔ 不是反过来）"
    )
