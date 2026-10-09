"""对话页入口 `GET /chat` 的回归守卫（`DEC-085` §3.1 · 裁定 #10）。

⚠️ **为什么要有这份用例**：这条路由本身**没有业务逻辑** —— 它就是一句 `RedirectResponse`，
于是它**最容易在"看着没事"的情况下被改坏**。三种真实的坏法，三种都不报错：

| 坏法 | 不测会怎样 | 本文件哪条会红 |
|---|---|---|
| 路由被删 / 路径被改 | 页面**没有入口了**。⛔ `check_route_auth.py` **测不出来** —— 那种情况它只报「少了 1 条（修好了）」并 **exit 0** | `test_chat_redirects_to_static_page` |
| 跳转目标写错 / 页面被改名 | 302 **照样是 302**，只是跳到 404 ⇒ 用户看到一片空白，**服务端不报错** | `test_chat_redirect_target_exists_on_disk` |
| 有人顺手删掉 `include_in_schema=False` | `/chat` **混进 openapi 文档**，被当成一条 API 对外承诺（它根本不是） | `test_chat_is_not_in_openapi` |

⚠️ `check_route_auth.py --baseline` 覆盖不了前两种：它只在**新公开路由变多**时 exit 1；
**变少**是「修好了」⇒ exit 0。⇒ 本条路由的"还在不在"**必须**有本文件才成立。

🔴 **⛔ 别把 `TestClient(app)` 改成 `with TestClient(app) as client:`** —— 那会触发 lifespan 的
   startup（`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。
   本文件只断「路由存不存在 / 跳去哪」，**不需要任何 startup**。
   📄 `docs/decisions/DEC-058-不连库的用例用裸TestClient.md` · `docs/规范/开发规范.md §2.5·5`

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_chat_page.py -q -p no:warnings` ⇒ **3 passed**
"""
import os

from fastapi.testclient import TestClient

from main import app, static_dir

#: 页面本体由已挂的 `/static` 托管（`app/main.py` 第 720 行那个 mount）。
#: ⚠️ 这里**不硬编码盘上路径** —— 从 `main.static_dir` 取，挂载点挪了本文件自动跟着挪。
STATIC_PREFIX = "/static/"
EXPECTED_LOCATION = STATIC_PREFIX + "web/chat.html"


def test_chat_redirects_to_static_page():
    """`GET /chat` ⇒ 302 到页面的**唯一**入口。

    ⚠️ 302（临时）而不是 301：这只是一句"把人送到页面"的跳转，⛔ 别让浏览器把它永久缓存住
    —— 页面将来换个位置时，缓存过的 301 会把老用户钉在 404 上。
    """
    client = TestClient(app)
    resp = client.get("/chat", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /chat` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（用户就没有对话页入口了），要么有人把它改成直接返回文件"
        "（那就得同时想清楚 `include_in_schema` 与静态托管的关系，见 main.py:531 的注释）"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}"
    )


def test_chat_redirect_target_exists_on_disk():
    """跳转目标必须**真的存在**，且走 `/static` 取得到。

    🔴 这条才是本文件的主要价值：**目标写错时，302 依然是 302** ——
    没有这条用例，页面被改名 / 挪走之后，服务端**一个错都不报**，只有用户看到空白页。
    """
    client = TestClient(app)
    loc = client.get("/chat", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), (
        f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下 —— 那它就不是被静态托管的那份，"
        "本用例的换算前提（去前缀取盘上路径）也就不成立了"
    )
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), (
        f"302 指向 {loc}，但盘上没有 {on_disk} ⇒ 用户会落到一个 404 空白页，"
        "而**服务端不会有任何报错**"
    )

    page = client.get(loc)
    assert page.status_code == 200, f"{loc} 应可取到 200，实际 {page.status_code}"
    assert page.headers["content-type"].startswith("text/html"), (
        f"{loc} 的 content-type 是 {page.headers['content-type']} —— 页面没被当成网页发出去"
    )


def test_chat_is_not_in_openapi():
    """`/chat` **不许**出现在 openapi 里（`include_in_schema=False`，`main.py:531`）。

    ⚠️ 它返回的是一个 **HTML 跳转**，不是 API —— 进了 openapi 就等于被当成一条
    对外承诺的接口，之后改它就成了"破坏兼容"。
    """
    assert "/chat" not in app.openapi()["paths"], (
        "`/chat` 出现在 openapi 里了 —— 检查 `@app.get(\"/chat\", include_in_schema=False)` "
        "那个参数是不是被顺手删了"
    )
