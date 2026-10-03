"""甲段 · **多用户资源隔离底座**（`DEC-056`）。

> 🔴 **本文件的 ①② 用例现在【是红的】。** 这是故意留的 —— `DEC-056` §四 决策 1/4 已裁：
>   ① 造探针身份（`isolation_a` / `isolation_b` = FREE · `isolation_c` = PREMIUM）；
>   ② 身份**用显式形参**贯穿到下游，⛔ 不用 contextvar。
>   本文件把它们钉成可打印的判据，**先看它红，再动生产码**（`test-driven-development`）。

## 本文件的三层，⛔ 别混

| 层 | 钉什么 | 要什么 | 进 CI 吗 |
|---|---|---|---|
| ① 探针身份 | 三个测试用户的角色 | 无 | ✅ |
| ② **结构守卫** | 检索层必须**要求**身份（漏传 = `TypeError`，⛔ 不是"静默查全库"） | 无（纯 `inspect`） | ✅ |
| ③ **行为用例** | 判据 = **看得见 / 看不见**（`DEC-056` 决策 3） | 真 Postgres | ❌（标 `needs_db`） |

## 为什么先钉「结构」再钉「行为」

真正的判据当然是 ③。但**根因**（`DEC-056` §二）是「**没有中间授权层 ⇒ 默认 fail-open**」——
新写的端点**默认就是"不过滤、查全库"**。修根因不能靠"每个端点记得加过滤"（那还是靠人记），
而是让**忘记传身份这件事在结构上做不到**：身份 = **必填形参**。
② 就是这条的守卫；③ 证明它**真的生效**（而不是"加了个参数但没人用"）。

## 判据（可打印）

```bash
# ①②（CI 也跑这条）
venv/bin/python -m pytest api/test_isolation.py -q -m "not needs_db" -p no:warnings

# ③ —— 🔴 必须带库名，否则 fixture 会 skip（防误写真库，见 §③ 的说明）
POSTGRES_DB=rag_test venv/bin/python -m pytest api/test_isolation.py -q -m needs_db -p no:warnings
```
"""
import inspect

import pytest


# ===========================================================================
# ① 探针身份 —— `DEC-056` §七 裁决 1「加一个 isolation_c，role 是 premium」
# ===========================================================================
#
# ⚠️ `get_user_role` 现在**仍是硬编码**（`admin` / `test_user` 特判，其余 FREE）——
#    这是既定事实，本段**不**顺手把它接 DB（`DEC-033` 🅱️ 后端先行 +
#    `DEC-046` §遗留 4 另有落点）。本段只是把三个**探针身份**加进那张硬编码表，
#    并在代码里注明它们是谁。

def test_isolation_c_is_premium():
    """`isolation_c` 必须是 PREMIUM —— 用来测「跨角色」那一档。

    判据：`DEC-056` §七 裁决 1。它现在会红（走到 else 分支拿 FREE）。
    """
    from permission import get_user_role, UserRole

    assert get_user_role("isolation_c") == UserRole.PREMIUM


def test_isolation_a_and_b_are_free():
    """`isolation_a` / `isolation_b` 必须是 FREE —— 用来测「同角色」那一档。

    ⚠️ 现在**恰好**是绿的（FREE 是默认分支）—— 但它是**反向守卫**：
    将来若有人把默认分支改成 PREMIUM，这条要拦住。
    """
    from permission import get_user_role, UserRole

    assert get_user_role("isolation_a") == UserRole.FREE
    assert get_user_role("isolation_b") == UserRole.FREE


def test_admin_role_unchanged():
    """反向守卫：加探针身份**不许**把 `admin` 挤掉。

    `DEC-056` §1.6 已核实「`require_admin` / 创建管理的权限**本来就没被降**」——
    这条钉住它。
    """
    from permission import get_user_role, UserRole

    assert get_user_role("admin") == UserRole.ADMIN


def test_unknown_user_still_defaults_to_free():
    """反向守卫：⛔ **别把默认分支改成 PREMIUM**。

    探针身份是**特判**，不是**改默认**。默认放松 = 每个陌生用户白拿 premium 额度。
    """
    from permission import get_user_role, UserRole

    assert get_user_role("some-random-stranger") == UserRole.FREE


# ===========================================================================
# ② fail-closed 结构守卫 —— 检索层必须**要求**身份
# ===========================================================================
#
# `DEC-056` §六 ③ 的原话判据：
#   「不传身份调用检索函数 ⇒ 断言【抛错】，⛔ 不是"静默返回全库"」
#
# ⚠️ 为什么用 `inspect` 而不是直接调用：直接调用会在**缺参数之前**就先跑
#    `get_embedding(...)`（真连 DashScope）⇒ 红的原因变成网络错误，
#    那不是我们要钉的东西。签名是**确定性**的，且它正是"漏传还能编译过"的根因。
#
# 🔴 关键点：**必须是必填**（`default is empty`）。带默认值 `user_id=None` 等于
#    "可以忘记传"，就还是 fail-open —— 所以下面每条都额外断言"没有默认值"。

_REQUIRED_IDENTITY_PARAM = "user_id"


def _assert_identity_is_required(func, label: str):
    sig = inspect.signature(func)
    assert _REQUIRED_IDENTITY_PARAM in sig.parameters, (
        f"{label} 没有 `{_REQUIRED_IDENTITY_PARAM}` 形参 —— 它现在**不知道是谁在查**，"
        f"默认就是「不过滤、查全库」（DEC-056 §二 根因）"
    )
    param = sig.parameters[_REQUIRED_IDENTITY_PARAM]
    assert param.default is inspect.Parameter.empty, (
        f"{label} 的 `{_REQUIRED_IDENTITY_PARAM}` 有默认值 —— "
        f"等于「可以忘记传」，就还是 fail-open（DEC-056 §六 ③）"
    )


def test_hybrid_search_requires_identity():
    """`hybrid_search` 是最底下的融合入口 —— 身份必须从这里就进来。"""
    from hybrid_search import hybrid_search

    _assert_identity_is_required(hybrid_search, "hybrid_search")


def test_rerank_search_requires_identity():
    """`rerank_search` 是「最终版检索入口」（它自己的 docstring 写的）。"""
    from hybrid_search import rerank_search

    _assert_identity_is_required(rerank_search, "rerank_search")


def test_hybrid_search_with_rewrite_requires_identity():
    """带查询改写的入口 —— 端点里走这条的是 **`/rag/rewrite_search`**（`rewrite_search_api`）。

    🔴 2026-10-03 更正：本行原先写「走这条的是 `jwt_ask` / `stream_search`」—— **说反了**。
    那两条**自己写 SQL**，⛔ 从不经过 `hybrid_search_with_rewrite`（这正是乙段要单独修它们的原因）。
    判据（可打印）：`grep -rn 'hybrid_search_with_rewrite' api/*.py` ⇒ 调用点只有 `api_v1_rag.py:472`。
    """
    from hybrid_search import hybrid_search_with_rewrite

    _assert_identity_is_required(hybrid_search_with_rewrite, "hybrid_search_with_rewrite")


def test_rag_pipeline_search_async_requires_identity():
    """`RAGPipeline.search_async` —— 管道层的异步检索入口。"""
    from rag_pipeline import RAGPipeline

    _assert_identity_is_required(RAGPipeline.search_async, "RAGPipeline.search_async")


def test_db_search_layer_requires_identity():
    """🔴 **真正决定「谁的文档」的那一层** —— 过滤加在这里，上面几条端点一起修好。

    这是 `DEC-056` 决策 5 的落点：`db.py` / `bm25_index.py` 是**共享层**，
    身份必须一路传到这儿，否则"上面传得再对，下面照样查全库"。
    """
    from db import (
        bm25_search,
        bm25_search_async,
        search_similar,
        search_similar_async,
    )

    _assert_identity_is_required(search_similar, "db.search_similar")
    _assert_identity_is_required(search_similar_async, "db.search_similar_async")
    _assert_identity_is_required(bm25_search, "db.bm25_search")
    _assert_identity_is_required(bm25_search_async, "db.bm25_search_async")


# ===========================================================================
# ③ 跨用户行为用例 —— 真库层（判据 = **看得见 / 看不见**，`DEC-056` 决策 3）
# ===========================================================================
#
# ⚠️ **为什么打在 `db.py` 而不是 HTTP 端点**：
#   · 端点层要真 API key + 真 embedding（DashScope）⇒ 那是【端到端验收】，见文件末；
#   · 而「**谁的文档**」这件事**就是在这层决定的** —— 过滤加在这里，
#     4 条端点（`/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search`）一起修好。
#
# 🔴 **为什么本文件自己多一道 `POSTGRES_DB=rag_test` 的闸**（本仓其它 `needs_db` 文件没有）：
#    本仓有前科 —— 某次冒烟忘带库名，往**真库 `rag_db`** 写了 4 行（`api/pytest.ini` 记着）。
#    本文件的 fixture 会 **INSERT / DELETE `documents`**，误写真库的后果比那次重
#    ⇒ **宁可多一道闸**（宁可 skip，不要误写）。
#
# 📌 `source` 用专用前缀 ⇒ 事后可精确清理：
#    `DELETE FROM documents WHERE source = 'isolation-probe-test';`
#    ⚠️ 业务方 2026-10-03 裁的「**数据不大就长期保留**」只针对**探针身份**（用户 / key），
#       ⛔ **不含**测试自己造的文档 —— 那些每次跑完就删（测试卫生，见 `DEC-056` §遗留·7）。

_PROBE_DIM = 1536  # `documents.embedding` = `vector(1536)`（实测 `\d documents`）
_PROBE_SRC = "isolation-probe-test"
_PROBE_A = "隔离测试数据 · ALPHA-DOC · 归属 isolation_a · 不含任何真实资料"
_PROBE_B = "隔离测试数据 · BETA-DOC · 归属 isolation_b · 不含任何真实资料"


def _probe_vector(seed: float) -> list:
    return [seed] * _PROBE_DIM


def _probe_cleanup(invalidate_bm25_cache):
    from db import get_db

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE source = %s", (_PROBE_SRC,))
        conn.commit()
    invalidate_bm25_cache()


@pytest.fixture
def probe_docs():
    """造两篇探针文档（A 的 / B 的），跑完删掉。

    ⚠️ 先清一遍再插 ⇒ **幂等**：上一次跑崩了留下残渣也不会让这次变成假绿。
    """
    import os

    if os.environ.get("POSTGRES_DB") != "rag_test":
        pytest.skip(
            "needs_db 用例必须带 POSTGRES_DB=rag_test 跑（api/pytest.ini）—— 防误写真库"
        )

    from bm25_index import invalidate_bm25_cache
    from db import get_db

    _probe_cleanup(invalidate_bm25_cache)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO documents (content, source, embedding, requested_by) "
                "VALUES (%s, %s, %s::vector, %s)",
                [
                    (_PROBE_A, _PROBE_SRC, _probe_vector(0.11), "isolation_a"),
                    (_PROBE_B, _PROBE_SRC, _probe_vector(0.11), "isolation_b"),
                ],
            )
        conn.commit()
    invalidate_bm25_cache()

    yield

    _probe_cleanup(invalidate_bm25_cache)


@pytest.mark.needs_db
def test_search_similar_only_returns_own_documents(probe_docs):
    """`isolation_b` 做向量检索 ⇒ 看得到自己的 B，⛔ 看不到 A 的。

    ⚠️ **正向控制必须有**（「自己的在里面」那条）—— 否则「永远返回空」也能让这条绿，
       那是**假绿**：用例什么也没证明。
    """
    from db import search_similar

    rows = search_similar(_probe_vector(0.11), top_k=50, user_id="isolation_b")
    contents = [r[1] for r in rows]

    assert any("BETA-DOC" in c for c in contents), (
        "连自己的文档都召不回 —— 这条用例是空的，下面那条断言证明不了任何东西"
    )
    assert not any("ALPHA-DOC" in c for c in contents), (
        "isolation_b 看到了 isolation_a 的文档 ⇒ **向量检索**这条路的隔离失效"
    )


@pytest.mark.needs_db
def test_bm25_search_only_returns_own_documents(probe_docs):
    """BM25 那条同理 —— 少了它，`hybrid_search` 的 RRF 会把别人的文档捞回来。"""
    from db import bm25_search

    rows = bm25_search("ALPHA-DOC", top_k=50, user_id="isolation_b")

    assert not any("ALPHA-DOC" in r[1] for r in rows), (
        "isolation_b 通过 BM25 看到了 isolation_a 的文档 ⇒ **关键词检索**这条路的隔离失效"
    )


@pytest.mark.needs_db
def test_bm25_still_finds_own_document(probe_docs):
    """反向守卫：过滤**别修过头** —— 自己的文档必须还找得到。"""
    from db import bm25_search

    rows = bm25_search("BETA-DOC", top_k=50, user_id="isolation_b")

    assert any("BETA-DOC" in r[1] for r in rows), "过滤把自己的文档也滤掉了 —— 修过头"


@pytest.mark.needs_db
def test_search_similar_rejects_explicit_none_identity(probe_docs):
    """fail-closed 的行为面：**显式传 `None` 也要抛错**，⛔ 不是"当成匿名、查全库"。

    ⚠️ ② 的签名守卫只挡住"**漏传**"；挡不住"**传了一个恰好是 None 的变量**"。
       这条补上那一格。
    """
    from db import search_similar

    with pytest.raises(ValueError):
        search_similar(_probe_vector(0.11), top_k=5, user_id=None)


# ===========================================================================
# ④ 端到端 —— **HTTP 端点**层（证"身份真的传下去了"）
# ===========================================================================
#
# ⚠️ ③ 证的是「**共享层会过滤**」；本段证的是「**端点真的把身份传下去了**」。
#    **两件事** —— 少了本段，"共享层能过滤"和"端点没传"可以同时成立
#    （那正是 `DEC-056` §二 那个"上面有身份、下面没人用"的形状）。
#
# 🔴 只把**外部依赖**（embedding / torch / LLM）换成假的，**DB 与 HTTP 栈全是真的**
#    ⇒ 走的是「TestClient → 中间件 → 端点 → hybrid_search → db → pgvector」整条链。
#
# ⚠️ **用的 key 是【临时】的**，⛔ 不是 `.env` 里那三把长期身份：
#    `needs_db` 跑在 `rag_test`，而长期身份在 `rag_db`（`DEC-056` §遗留·7 的裁决）。
#    本段要验的是"**HTTP 认不认身份 + 传不传得下去**"，临时 key 一样能验，且不碰真库。

_ENDPOINT_PROBE_USERS = ("isolation_a", "isolation_b")


@pytest.fixture
def probe_api_keys(probe_docs):
    """在**测试库**里给两个探针用户各造一把 key，跑完删掉。"""
    from auth import create_user_api_key
    from db import get_db

    def _drop():
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM api_keys WHERE user_name = ANY(%s)",
                    (list(_ENDPOINT_PROBE_USERS),),
                )
            conn.commit()

    _drop()
    keys = {u: create_user_api_key(u, expire_days=1) for u in _ENDPOINT_PROBE_USERS}
    yield keys
    _drop()


def _post(client, path: str, key: str, question: str = "ALPHA-DOC"):
    return client.post(
        path,
        json={"question": question, "top_k": 5},
        headers={"X-API-Key": key},
    )


@pytest.mark.needs_db
def test_hybrid_search_endpoint_does_not_leak_across_users(probe_api_keys, monkeypatch):
    """`/rag/hybrid_search` —— isolation_b 打自己的 key ⇒ 拿不到 isolation_a 的文档。

    ⚠️ **两条断言缺一不可**：只断言"看不见 A"，在"端点整个坏掉返回空"时也是绿的。
    """
    import hybrid_search

    monkeypatch.setattr(
        hybrid_search, "get_embedding", lambda text, model=None: _probe_vector(0.11)
    )

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    r_b = _post(client, "/api/v1/rag/hybrid_search", probe_api_keys["isolation_b"])
    assert r_b.status_code == 200, r_b.text
    assert r_b.json()["requested_by"] == "isolation_b"
    contents_b = [d["content"] for d in r_b.json()["docs"]]
    assert not any("ALPHA-DOC" in c for c in contents_b), (
        "HTTP 端点上 isolation_b 拿到了 isolation_a 的文档 ⇒ **身份没从端点传下去**"
    )

    # 🔴 正向控制：isolation_a 打自己的 key ⇒ **必须**拿得到自己的
    r_a = _post(client, "/api/v1/rag/hybrid_search", probe_api_keys["isolation_a"])
    assert r_a.status_code == 200, r_a.text
    contents_a = [d["content"] for d in r_a.json()["docs"]]
    assert any("ALPHA-DOC" in c for c in contents_a), (
        "连自己的文档都拿不到 —— 上面那条断言证明不了任何东西（用例是空的）"
    )


@pytest.mark.needs_db
def test_rerank_search_endpoint_does_not_leak_across_users(probe_api_keys, monkeypatch):
    """`/rag/rerank_search` —— **另一条**调用点，要单独验（⛔ 别拿上一条替它）。

    ⚠️ `rerank` 真跑要拉 torch + 2.3GB 模型 ⇒ 换成"原样返回"（本段验的是**隔离**，⛔ 不是重排质量）。
    """
    import hybrid_search

    monkeypatch.setattr(
        hybrid_search, "get_embedding", lambda text, model=None: _probe_vector(0.11)
    )
    monkeypatch.setattr(hybrid_search, "rerank", lambda query, docs, top_k=3: docs[:top_k])

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = _post(client, "/api/v1/rag/rerank_search", probe_api_keys["isolation_b"])
    assert r.status_code == 200, r.text
    contents = [d["content"] for d in r.json()["docs"]]
    assert not any("ALPHA-DOC" in c for c in contents), (
        "`/rag/rerank_search` 这条调用点漏了 —— 身份没传下去"
    )


@pytest.mark.needs_db
def test_rewrite_search_endpoint_does_not_leak_across_users(probe_api_keys, monkeypatch):
    """`/rag/rewrite_search` —— 第三条调用点。

    ⚠️ `rewrite_query` / `expand_query` 真跑要调 chat LLM ⇒ 换成恒等（同上，验的是隔离）。
    """
    import hybrid_search

    monkeypatch.setattr(
        hybrid_search, "get_embedding", lambda text, model=None: _probe_vector(0.11)
    )
    monkeypatch.setattr(hybrid_search, "rewrite_query", lambda q, h=None: q)
    monkeypatch.setattr(hybrid_search, "expand_query", lambda q, num_variants=3: [q])

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = _post(client, "/api/v1/rag/rewrite_search", probe_api_keys["isolation_b"])
    assert r.status_code == 200, r.text
    contents = [d["content"] for d in r.json()["docs"]]
    assert not any("ALPHA-DOC" in c for c in contents), (
        "`/rag/rewrite_search` 这条调用点漏了 —— 身份没传下去"
    )


@pytest.mark.needs_db
def test_retrieval_endpoint_rejects_missing_identity(probe_api_keys):
    """fail-closed 的**端点面**：不带头 ⇒ 必须被挡住，⛔ 不是"匿名查全库"。"""
    from fastapi.testclient import TestClient
    from main import app

    r = TestClient(app).post(
        "/api/v1/rag/hybrid_search", json={"question": "ALPHA-DOC", "top_k": 5}
    )
    assert r.status_code in (401, 403), (
        f"不带身份竟然过了 ⇒ 拿到 {r.status_code}；这正是 fail-open 的形状"
    )


# ===========================================================================
# ⑤ 乙段 —— 自己写 SQL 的那两条（`DEC-056` §1.2 第 7 / 8 条）
# ===========================================================================
#
# ⚠️ 这两条与 ③④ 是**两种形态**：它们⛔ **不走共享层**，SQL 就写在端点上
#    ⇒ `search_similar` 那些判据**碰不到它们** —— 这正是它们能一直漏着的原因。
#    ⇒ 各配一条**端点级**用例，否则「共享层过滤对了」与「端点照旧查全库」可以同时为真。
#
# ⚠️ 只把**外部依赖**（embedding / LLM / Redis / 预算）换假的，**DB 与 HTTP 栈全是真的**。


class _CapturingLLM:
    """假的 LLM 流：只把端点**送进 prompt 的 messages 记下来**，⛔ 一个 chunk 都不吐。

    观测对象就是它 —— `stream_search` 把检索到的上下文拼进 **system prompt**
    （`api_v1_rag.py` 的 `context_text`）。⇒ 「谁进了上下文」= 「谁被检索到了」。
    """

    def __init__(self):
        self.astream_calls = []

    def astream(self, messages):
        self.astream_calls.append(messages)
        return _empty_astream()


async def _empty_astream():
    return
    yield  # 空的一行，但它把本函数变成 async generator（`async for` 需要）


def _system_prompt_of(llm) -> str:
    """取最后一次调用里 role=system 的内容 —— ⛔ **不含 user 那条问题**。

    ⚠️ 为什么不直接搜整个 messages：`req.question` 也在里面。拿问题当关键字搜会
       **永远命中** ⇒ 用例假红。必须只取 system。
    """
    assert llm.astream_calls, "端点没有走到 LLM ⇒ 这条用例什么都没证"
    return "\n".join(
        m["content"] for m in llm.astream_calls[-1] if m.get("role") == "system"
    )


def _stub_rag_externals(monkeypatch, rag_mod, llm):
    """把**外部依赖**换假的：embedding · LLM · Redis 历史 · 会话预算 · 全站熔断。"""
    monkeypatch.setattr(
        rag_mod, "get_embedding", lambda text, model=None: _probe_vector(0.11)
    )
    monkeypatch.setattr(rag_mod, "get_llm_stream", lambda: llm)
    monkeypatch.setattr(rag_mod, "get_chat_history", lambda user: [])
    monkeypatch.setattr(rag_mod, "append_chat_history", lambda *a, **k: None)
    monkeypatch.setattr(rag_mod, "check_session_token_budget", lambda *a, **k: (True, ""))
    monkeypatch.setattr(rag_mod, "circuit", lambda *a, **k: (True, ""))


@pytest.mark.needs_db
def test_stream_search_endpoint_does_not_leak_across_users(probe_api_keys, monkeypatch):
    """`/rag/stream_search` —— isolation_b 的上下文里⛔ 不许出现 isolation_a 的文档。

    ✅ **为什么这条能可靠地红**（⛔ 与下面 `jwt_ask` 那条不同）：
       探针向量 = 查询向量（都是 `_probe_vector(0.11)`）⇒ 余弦相似度 = **1.0 = 最大值**
       ⇒ 两篇探针文档**必然**排在 top-k 前面 ⇒ 未过滤时 A 的文档**一定**进上下文。
       ⚠️ 这个「一定」是它可靠的**根据**，⛔ 不是习惯 —— 下面 `jwt_ask` 那条就**没有**这个性质。
    """
    import api_v1_rag as rag_mod

    llm = _CapturingLLM()
    _stub_rag_externals(monkeypatch, rag_mod, llm)

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    def _stream(key: str):
        return client.post(
            "/api/v1/rag/stream_search",
            json={"question": "隔离测试查询", "top_k": 5},
            headers={"X-API-Key": key},
        )

    r_b = _stream(probe_api_keys["isolation_b"])
    assert r_b.status_code == 200, r_b.text
    prompt_b = _system_prompt_of(llm)
    assert _PROBE_A not in prompt_b, (
        "isolation_b 的检索上下文里混进了 isolation_a 的文档 ⇒ 这条端点仍然查全库"
    )
    assert _PROBE_B in prompt_b, (
        "连自己的文档都没进上下文 —— 上面那条断言证明不了任何东西（用例是空的）"
    )

    # 🔴 正向控制：isolation_a 打自己的 key ⇒ 必须拿得到 A 的、且看不到 B 的
    llm.astream_calls.clear()
    r_a = _stream(probe_api_keys["isolation_a"])
    assert r_a.status_code == 200, r_a.text
    prompt_a = _system_prompt_of(llm)
    assert _PROBE_A in prompt_a
    assert _PROBE_B not in prompt_a


@pytest.mark.needs_db
def test_jwt_ask_endpoint_does_not_leak_across_users(probe_api_keys):
    """`/rag/jwt_ask` —— JWT 身份 ⇒ 只拿得到自己的文档。

    ⚠️ **这条的泄漏判据是【条数】，⛔ 不是【内容】。** 为什么：

       那条 SQL **没有 `ORDER BY`** ⇒ 未加过滤时返回哪 20 篇取决于**物理顺序**，
       而探针文档是刚插进去的、排在物理序**末尾** ⇒ A 的文档**很可能根本不在**
       那 20 篇里。⇒ 只断言「内容里没有 A」**会在修之前就是绿的**（假绿）。

       ⇒ 换成本条：`rag_test` 里 isolation_b **只拥有 1 篇**（就是探针那篇），
         而用户能问的最大 `top_k` 是 **20**（`schemas.py` 的 `le=20`）、库里 200+ 篇。
         **未加 WHERE ⇒ 它拿回 20 篇；加了 ⇒ 拿回 1 篇。** 与物理顺序无关。
    """
    from config import JWT_SECRET_KEY
    from jwt_handler import create_access_token

    assert JWT_SECRET_KEY, "JWT_SECRET_KEY 未设置，无法自签 token"

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    def _ask(user: str):
        # ⚠️ 本条端点是 `get_current_user_jwt` ⇒ 走**自签 JWT**，⛔ 不是 X-API-Key
        return client.post(
            "/api/v1/rag/jwt_ask",
            json={"question": "隔离测试查询", "top_k": 20},
            headers={"Authorization": f"Bearer {create_access_token(user)}"},
        )

    r_b = _ask("isolation_b")
    assert r_b.status_code == 200, r_b.text
    docs_b = r_b.json()["docs"]

    assert len(docs_b) == 1, (
        f"isolation_b 拿回了 {len(docs_b)} 篇 —— 它自己只有 1 篇 ⇒ 这条端点零 WHERE"
    )
    assert _PROBE_B in docs_b[0], "拿回来的不是自己的那篇 —— 上面那条断言证明不了什么"
    assert _PROBE_A not in docs_b[0]

    # 正向控制：admin 有 200+ 篇 ⇒ 它必须**拿满** top_k（证明端点本身是活的，
    # 不是"整体坏掉返回空"让上面那条碰巧成立）
    r_admin = _ask("admin")
    assert r_admin.status_code == 200, r_admin.text
    assert len(r_admin.json()["docs"]) == 20, (
        f"admin 只拿到 {len(r_admin.json()['docs'])} 篇 ⇒ 端点整体不对劲，用例是空的"
    )
