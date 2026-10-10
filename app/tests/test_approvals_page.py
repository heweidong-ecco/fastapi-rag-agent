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

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_approvals_page.py -q -p no:warnings` ⇒ **8 passed**

🔴 **2026-10-10（施工单刀 8）补了 5 条【页面本体】的** —— 在此之前本文件**只有上面三条**，
   于是「页面上印着星号」与「这页没有骨架」**一条门都不会红**（`DEC-094` 前科的同族）。
"""
import os
import re

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


# ==================== 页面本体（🔴 2026-10-10 补 · 施工单刀 8）====================
#
# 🔴 **为什么到这一刀才补**：本文件此前**只有上面三条**（302 / 目标在盘上 / 不进 openapi）
#    ⇒ **页面本体一条判据都没有** ⇒ 于是两件事**没有任何门会红**：
#      ① 页面上写着 `**完整上下文**`（**两个星号是真的印在页面上的**）；
#      ② 这页**没有骨架**（没有侧边栏、没有页头）—— 而它是「人工接管」，属 5 类主要功能之一。
#    ⚠️ 这正是 `DEC-094` 那个前科的同族：**路由是对的、页面是坏的，三层判据一条不红**。


def _page_text():
    with open(os.path.join(static_dir, "web", "approvals.html"), encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    """剥掉 HTML 注释与 JS 行注释。

    ⚠️ **必须剥** —— 本页注释里**有意**记着旧写法（那是沿革，给人读的）。
    不剥的话，下面那条会**报在它自己头上**（本仓栽过同型的第 5 次：
    「**要提那串，就拆开写或只描述它**」）。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//[^\n]*", r"\1", text, flags=re.M)
    return text


def test_page_has_the_app_shell():
    """🔴 **这一页必须有骨架**（侧边栏 + 页头）—— 它是「人工接管」= 5 类主要功能之一。

    ⚠️ 2026-10-10 之前它是个**裸文档**：没有 `.app-shell`、没有侧边栏、没有页头，
       而别的四个主要功能页都有 ⇒ 只有它长得不像这一站里的页面。
    ⚠️ **反证**：把 `.app-shell` 那一段删掉 ⇒ 本条红。
    """
    text = _page_text()
    assert 'class="app-shell"' in text, "页面没有 `.app-shell` 骨架"
    assert '<aside class="sidebar">' in text, "没有侧边栏"
    assert 'class="page-head"' in text, "没有页头"


def test_page_does_not_print_markdown_marks():
    """🔴 **页面上的字⛔ 不许带 markdown 记号**（本页一律 `textContent` ⇒ 会原样印出星号）。

    ⚠️ 2026-10-10 **实测到过**：那句「待接管会话 · 点一行看 `**完整上下文**` · …」
    —— **两个星号是真的印在页面上的**。
    同族缺陷本仓已记三次（`tools` / `system` / `ops` 各有守卫钉着），
    ⛔ **而本页一条都没有** ⇒ 所以它一直没人管。
    ⚠️ **剥注释再扫**（见 `_strip_comments` 的说明）。
    """
    live = _strip_comments(_page_text())
    hits = [n for n, line in enumerate(live.split("\n"), 1) if "**" in line]
    assert hits == [], f"这些行（已剥注释）里有 markdown 的记号 ⇒ 页面上会原样印星号：{hits}"


def test_page_uses_the_global_table_class():
    """两张表都要挂 `class="tbl"` —— 否则用的是**浏览器默认表格**，与全站不一样。

    🔴 2026-10-10（刀 8）本页的 `table/th/td` 规则**已收进 `app.css`**：
    **规则搬走了，页面就得挂上那个类** —— 否则表格会**掉回浏览器默认样式，而⛔ 不报任何错**。
    """
    text = _page_text()
    for tid in ("pending", "history"):
        assert re.search(rf'<table id="{tid}"\s+class="tbl"', text), (
            f"`#{tid}` 那张表没挂 `.tbl` ⇒ 吃不到全站表格样式（⛔ 且不会报错）")


def test_boundary_notice_comes_before_the_decide_buttons():
    """🔴 **边界提示条必须排在裁决按钮【之前】**（规格 §3.6.1 的② · `DEC-123` §1.1）。

    业务方原话：「**让别人在用接口的时候要先看到这个提示，才给接口**」。
    ⚠️ 判据钉的是**两个标记的先后**，⛔ 不是"文件里有没有 `data-boundary` 这个词"
       —— 后者过不了反证检验（把提示条挪到按钮**后面**它照样有）。
    """
    text = _page_text()
    i_b = text.find('data-boundary="real_api"')
    i_btn = text.find('<button id="approve"')
    assert i_b != -1, "裁决框里没有边界提示条"
    assert i_btn != -1, "找不到批准按钮 —— 页面结构变了"
    assert i_b < i_btn, (
        "边界提示条排在了批准按钮【之后】⇒ 与业务方原话相拗"
        "（「让别人在用接口的时候要先看到这个提示，才给接口」）")


def test_page_loads_the_boundary_helper():
    """🔴 边界文案【全站只有一份】⇒ 必须引 `panel.js`，否则 `RagPanel` 未定义。

    ⚠️ 不引的话，那几条 `data-boundary` 的框**永远是空的** —— 而**页面上不报任何错**
       （只有浏览器控制台里一条 `ReferenceError`）。
    """
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert re.search(r"RagPanel\.boundaryShort\s*\(", text), (
        "页面没调用 RagPanel.boundaryShort() —— 那几条边界提示条是空的？")
