"""已删端点的【反向守卫】 —— ⛔ 别把它们默默改回来。

⚠️ **为什么要有这条用例**：删掉一个端点之后，**没有任何东西会阻止它被重新加回来** ——
`grep` 只说明「现在没有」，不说明「以后不会有」（本仓 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
记的就是同族毛病：**拿一次观察当全称判断**）。这条用例把「它不该回来」变成一条**会红的检查**。

| 端点 | 删除日 | 理由（全文见对应 DEC） |
|---|---|---|
| `POST /api/v1/rag/ask` | 2026-10-03 | `DEC-057` |

`/rag/ask` 为什么删（摘要）：它是 `tags=["模拟类测试"]` 的桩，却**读真库**，且 `LIMIT` **无 `ORDER BY`**
⇒ **结果不可复现**；能力被 `/rag/pg_search` 覆盖（**同鉴权**、**同入参**，且多了 embedding /
`ORDER BY` / 更丰富的输出）；全仓**无消费者**。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings` ⇒ **1 passed**
"""
from fastapi.testclient import TestClient

from main import app


def test_rag_ask_stays_removed():
    """`/rag/ask` 已删（`DEC-057`）—— 它回来就该红，⛔ 别默默改回来。

    ⚠️ **判据是 404，⛔ 不是「不是 200」** —— 端点还在但**没带鉴权**时是 401/403，
    那也是「它回来了」。只有 **404（路由不存在）** 才算删干净。
    """
    with TestClient(app) as client:
        resp = client.post("/api/v1/rag/ask", json={"question": "x", "top_k": 3})

    assert resp.status_code == 404, (
        f"`/api/v1/rag/ask` 应已删除（`DEC-057`），却返回了 {resp.status_code} —— "
        "要么它被改回来了（⛔ 先读那份 DEC 里的删除理由再决定），要么本用例的路径写错了"
    )
