"""已删端点的【反向守卫】 —— ⛔ 别把它们默默改回来。

⚠️ **为什么要有这条用例**：删掉一个端点之后，**没有任何东西会阻止它被重新加回来** ——
`grep` 只说明「现在没有」，不说明「以后不会有」（本仓 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
记的就是同族毛病：**拿一次观察当全称判断**）。这条用例把「它不该回来」变成一条**会红的检查**。

| 端点 | 删除日 | 理由（全文见对应 DEC） |
|---|---|---|
| `POST /api/v1/rag/ask` | 2026-10-03 | `DEC-057` |
| `POST /api/v1/rag/jwt_ask` | 2026-10-04 | `DEC-064` |

`/rag/ask` 为什么删（摘要）：它是 `tags=["模拟类测试"]` 的桩，却**读真库**，且 `LIMIT` **无 `ORDER BY`**
⇒ **结果不可复现**；能力被 `/rag/pg_search` 覆盖（**同鉴权**、**同入参**，且多了 embedding /
`ORDER BY` / 更丰富的输出）；全仓**无消费者**。

`/rag/jwt_ask` 为什么删（摘要）：**与上一条逐条同构** —— 收到 `question` 却**不拿它检索**（无 embedding、
无 `ORDER BY` ⇒ **同样的结果不可复现**）；能力被 `/rag/pg_search` 覆盖，且那次是**更严的覆盖**：
它的 `get_current_user_jwt` **只收 JWT**，而 `pg_search` 的 `get_current_user_hybrid` **JWT 与 API Key 都收**
⇒ 是它的**超集**（"只收 JWT"是**限制**，不是能力）；全仓**无消费者**。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings` ⇒ **2 passed**
"""
from fastapi.testclient import TestClient

from main import app


def test_rag_ask_stays_removed():
    """`/rag/ask` 已删（`DEC-057`）—— 它回来就该红，⛔ 别默默改回来。

    ⚠️ **判据是 404，⛔ 不是「不是 200」** —— 端点还在但**没带鉴权**时是 401/403，
    那也是「它回来了」。只有 **404（路由不存在）** 才算删干净。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 那样会**触发 lifespan 的 startup**
    ⇒ `init_pool()` **真去连 Postgres** ⇒ **CI 没有 Postgres ⇒ `psycopg2.OperationalError`**
    （2026-10-03 实测：`bash scripts/ci-local.sh` ⇒ `1 failed, 411 passed`）。
    ⚠️ **本机看不出来**：本机 Postgres 真开着 ⇒ 连得上 ⇒ 照样绿。
    📌 **本仓判据**：本用例只断**路由存不存在**，**不需要任何 startup** ⇒ 用**裸 `TestClient(app)`**
    （全仓不连库的用例都是这么写的；`with … as` 全仓**只有这一处**，就是它把自己坑了）。
    📄 `docs/复盘/2026-10-03-CI同款命令不等于CI等价物.md`
    📄 **裁决全文（含"为什么不标 `needs_db`"）⇒ `docs/decisions/DEC-058-不连库的用例用裸TestClient.md`**
    　　· 规矩落在 `docs/规范/开发规范.md §2.5·5`
    """
    client = TestClient(app)
    resp = client.post("/api/v1/rag/ask", json={"question": "x", "top_k": 3})

    assert resp.status_code == 404, (
        f"`/api/v1/rag/ask` 应已删除（`DEC-057`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )


def test_rag_jwt_ask_stays_removed():
    """`/rag/jwt_ask` 已删（`DEC-064`）—— 它回来就该红，⛔ 别默默改回来。

    ⚠️ **判据是 404，⛔ 不是「不是 200」** —— 理由与上一条逐字相同：端点还在但**带了鉴权**时
    回的是 **401/403**，那也是「它回来了」。⚠️ 本条尤其容易踩：删之前它**本来就是 401**
    （缺 Bearer Token），所以「不是 200」这种写法**在这条上从第一天起就是绿的**，什么也没钉住。

    📌 **为什么走 `get_current_user_jwt` 也一样要删**（最容易读反的一点）：
    它「只收 JWT、不收 API Key」看着像一项独有能力，其实是**限制** ——
    `/rag/pg_search` 的 `get_current_user_hybrid` **JWT 与 API Key 都收**，是它的**超集**。
    ⇒ 删掉它，**JWT 用户一个能力都没少**。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 同上一份
    `docs/decisions/DEC-058-不连库的用例用裸TestClient.md`。
    """
    client = TestClient(app)
    resp = client.post("/api/v1/rag/jwt_ask", json={"question": "x", "top_k": 3})

    assert resp.status_code == 404, (
        f"`/api/v1/rag/jwt_ask` 应已删除（`DEC-064`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )
