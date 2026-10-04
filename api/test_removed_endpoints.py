"""已删端点的【反向守卫】 —— ⛔ 别把它们默默改回来。

⚠️ **为什么要有这条用例**：删掉一个端点之后，**没有任何东西会阻止它被重新加回来** ——
`grep` 只说明「现在没有」，不说明「以后不会有」（本仓 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
记的就是同族毛病：**拿一次观察当全称判断**）。这条用例把「它不该回来」变成一条**会红的检查**。

| 端点 | 删除日 | 理由（全文见对应 DEC） |
|---|---|---|
| `POST /api/v1/rag/ask` | 2026-10-03 | `DEC-057` |
| `POST /api/v1/rag/jwt_ask` | 2026-10-04 | `DEC-064` |
| `GET /api/v1/users/{user_id}` | 2026-10-04 | `DEC-065` |
| `GET /api/v1/tool/benchmark` | 2026-10-04 | `DEC-065` |
| `POST /api/v1/rag/async_ask` | 2026-10-04 | `DEC-065` |
| `POST /api/v1/rag/parallel_ask` | 2026-10-04 | `DEC-065` |

`/rag/ask` 为什么删（摘要）：它是 `tags=["模拟类测试"]` 的桩，却**读真库**，且 `LIMIT` **无 `ORDER BY`**
⇒ **结果不可复现**；能力被 `/rag/pg_search` 覆盖（**同鉴权**、**同入参**，且多了 embedding /
`ORDER BY` / 更丰富的输出）；全仓**无消费者**。

`/rag/jwt_ask` 为什么删（摘要）：**与上一条逐条同构** —— 收到 `question` 却**不拿它检索**（无 embedding、
无 `ORDER BY` ⇒ **同样的结果不可复现**）；能力被 `/rag/pg_search` 覆盖，且那次是**更严的覆盖**：
它的 `get_current_user_jwt` **只收 JWT**，而 `pg_search` 的 `get_current_user_hybrid` **JWT 与 API Key 都收**
⇒ 是它的**超集**（"只收 JWT"是**限制**，不是能力）；全仓**无消费者**。

后 4 条为什么删（摘要，全文 `DEC-065`）：
· `GET /users/{user_id}` —— **一行数据都不读**，函数体就是 `return {"user_id": …, "detail": …}`
  （参数校验演示）。本仓 `docs/specs/api_v1.md` 的 ⚠️④ 与待办表第 4 条早就写着「**要么真查库，要么删**」。
· `GET /tool/benchmark` —— 它 benchmark 的是 **mock**：`get_weather` 是 `time.sleep(2)` +
  硬编码 `f"{city}当前温度25°C，晴"` ⇒ **证明不了任何生产事实**。
· `POST /rag/async_ask` · `POST /rag/parallel_ask` —— **纯 mock**（`await asyncio.sleep(2)` 后返回
  `["异步文档A(…)", …]`），无库、无 embedding、不花钱，但**也无消费者**。
  ⇒ 这两条一删，`tags=["模拟类测试"]` **整组归零**（`/rag/ask` 2026-10-03 已删 · `/rag/jwt_ask` 2026-10-04 已删）。

⚠️ **这 4 条的判据同样是 404**，⛔ 不是「不是 200」—— 它们删之前**全都是 200**，
所以「不是 200」在那时也成立不了什么；而将来若被**加回来并带上鉴权**，回的是 401/403，
那同样是「它回来了」。**只有 404 才算删干净。**

📌 判据（可打印）：`venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings` ⇒ **6 passed**
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


# ==================== `DEC-065` 一次删掉的 4 条（A1 收口）====================
# ⚠️ 这 4 条删之前**全都回 200**（都是匿名可打的），所以「不是 200」这种写法在它们身上
#    当时就已经是红的 —— 但那**不是**本用例要钉的东西。本用例钉的是 **404**。


def test_users_by_id_stays_removed():
    """`GET /users/{user_id}` 已删（`DEC-065`）—— 它**一行数据都不读**，回来就该红。

    ⚠️ 它当初唯一的行为是 `return {"user_id": user_id, "detail": include_detail}` ——
    **不查库、不看 `user_name`**，纯粹是 **Path/Query 参数校验演示**，却很容易被当成真接口用
    （`docs/specs/api_v1.md` ⚠️④ 记的就是这个）。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 见
    `docs/decisions/DEC-058-不连库的用例用裸TestClient.md`。
    """
    client = TestClient(app)
    resp = client.get("/api/v1/users/1")

    assert resp.status_code == 404, (
        f"`/api/v1/users/{{user_id}}` 应已删除（`DEC-065`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )


def test_tool_benchmark_stays_removed():
    """`GET /tool/benchmark` 已删（`DEC-065`）—— 它 benchmark 的是 **mock**，回来就该红。

    ⚠️ 它比的是 `get_weather("Beijing")` 调两次的耗时，而 `get_weather` 本体是
    `time.sleep(2)` + 硬编码返回值 ⇒ **证明的只是「缓存装饰器在假函数上生效」**，
    **证明不了任何生产事实**。缓存装饰器本身由 `api/test_audit_fixes.py` 单测覆盖。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 同上那份 `DEC-058`。
    """
    client = TestClient(app)
    resp = client.get("/api/v1/tool/benchmark")

    assert resp.status_code == 404, (
        f"`/api/v1/tool/benchmark` 应已删除（`DEC-065`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )


def test_rag_async_ask_stays_removed():
    """`POST /rag/async_ask` 已删（`DEC-065`）—— 纯 mock，回来就该红。

    ⚠️ 它 `await asyncio.sleep(2)` 后返回 `[f"异步文档A({query})", …]` —— 无库、无 embedding、
    不花钱，但**也无消费者**。它一删，`tags=["模拟类测试"]` 只剩 `parallel_ask`，**再删即整组归零**。

    📌 **它的「不接线」守卫去哪了**：原先它由两份反向守卫各钉一行
    （`test_breaker_wiring.py::test_the_two_non_spending_endpoints_stay_unwired` ·
    `test_session_budget_wiring.py::test_the_two_non_llm_endpoints_stay_unwired`）。
    端点删掉后**那两张清单一起空了** —— 空清单 = `for` 体一次都不跑 = **恒绿假通过**
    （正是本仓「空跑 = 静默假通过」那条纪律点的病）。⇒ 两条空守卫**已删**，
    其保护**收敛到这里**。⚠️ **代价说清楚**：将来若有人再加一条 mock 端点，
    **不会有测试自动拉红**叫他去接线 —— 只能靠 `DEC-065` 里那条写明的要求。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 同上那份 `DEC-058`。
    """
    client = TestClient(app)
    resp = client.post("/api/v1/rag/async_ask", json={"question": "x"})

    assert resp.status_code == 404, (
        f"`/api/v1/rag/async_ask` 应已删除（`DEC-065`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )


def test_rag_parallel_ask_stays_removed():
    """`POST /rag/parallel_ask` 已删（`DEC-065`）—— 纯 mock，回来就该红。

    ⚠️ 它调 `parallel_search` → `asyncio.gather` 几个 `async_search`，返回**同样是硬编码串**。
    **这一条删掉后 `tags=["模拟类测试"]` 整组归零。**

    📌 **它的「不接线」守卫去哪了** —— 与上一条逐字相同（两条空守卫已删，见
    `test_rag_async_ask_stays_removed` 的说明与 `DEC-065`）。

    🔴 **⛔ 别把这里改成 `with TestClient(app) as client:`** —— 同上那份 `DEC-058`。
    """
    client = TestClient(app)
    resp = client.post("/api/v1/rag/parallel_ask", json={"question": "x"})

    assert resp.status_code == 404, (
        f"`/api/v1/rag/parallel_ask` 应已删除（`DEC-065`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )
