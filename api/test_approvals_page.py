"""接管页入口 `GET /approvals` 的回归守卫（`DEC-088` §3.3）。

⚠️ **为什么要有这份用例**：这条路由本身**没有业务逻辑** —— 它就是一句 `RedirectResponse`，
   于是它**最容易在"看着没事"的情况下被改坏**。三种真实的坏法，三种都不报错：

| 坏法 | 不测会怎样 | 本文件哪条会红 |
|---|---|---|
| 路由被删 / 路径被改 | 页面**没有入口了**。⛔ `check_route_auth.py` **测不出来** —— 那它只报「少了 1 条（修好了）」并 **exit 0** | `test_approvals_redirects_to_static_page` |
| 跳转目标写错 / 页面被改名 | 302 **照样是 302**，只是跳到 404 ⇒ 用户看到一片空白，**服务端不报错** | `test_approvals_redirect_target_exists_on_disk` |
| 有人顺手删掉 `include_in_schema=False` | `/approvals` **混进 openapi**，被当成一条 API 对外承诺（它根本不是） | `test_approvals_is_not_in_openapi` |

🔴 **⛔ 别把 `TestClient(app)` 改成 `with TestClient(app) as client:`** —— 那会触发 lifespan 的
   startup（`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。
   📄 `docs/decisions/DEC-058-不连库的用例用裸TestClient.md`

📌 判据（可打印）：`venv/bin/python -m pytest api/test_approvals_page.py -q -p no:warnings` ⇒ **3 passed**
"""
import os

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
EXPECTED_LOCATION = STATIC_PREFIX + "web/approvals.html"


def test_approvals_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/approvals", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /approvals` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（用户就没有接管页入口了），要么有人把它改成直接返回文件"
        "（那就得同时想清楚 `include_in_schema` 与静态托管的关系）"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_approvals_redirect_target_exists_on_disk():
    """🔴 这条才是本文件的主要价值：**目标写错时，302 依然是 302**。"""
    client = TestClient(app)
    loc = client.get("/approvals", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), (
        f"302 指向 {loc}，但盘上没有 {on_disk} ⇒ 用户会落到一个 404 空白页，"
        "而**服务端不会有任何报错**")

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_approvals_is_not_in_openapi():
    assert "/approvals" not in app.openapi()["paths"], (
        "`/approvals` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")
