"""总览首页 `GET /` 的回归守卫（规格 §〇.五 #6 · 施工单刀 1）。

⚠️ **这条路由的家底变了，所以它比别的页面路由更危险**：`/` **原先返回 JSON**
（那段服务索引），而且 `docs/specs/main.md:96` 当时把它称作「**线上契约 · 别动它**」。
⇒ 本文件要把**三件事同时**钉住：

| # | 钉什么 | 不钉会怎样 |
|---|---|---|
| 1 | `/` 现在是 **302 页面** | 有人把它改回 JSON ⇒ 首页又变回一坨 JSON，而**服务端不报错** |
| 2 | **跳转目标真的在盘上** | 目标写错时 **302 照样是 302**，只有用户看到空白页（`test_chat_page.py` 那条的同型风险） |
| 3 | 🔴 **那段 JSON【没丢】**（挪到 `/api/v1/info`） | 「挪走不是删」是本条的**裁定原文** ⇒ 丢了这个 JSON 等于把 `/api/v1/` 那套服务索引一起废了 |

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_index_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

EXPECTED_LOCATION = "/static/web/index.html"

#: 剥注释用（见 `_strip_comments` 的理由）—— ⛔ 别改成"只剥一种"。
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def test_root_redirects_to_overview_page():
    """`GET /` ⇒ 302 到总览首页（规格 §〇.五 #6：它是**替代**那坨 JSON 的页面）。

    ⚠️ 302（临时）而不是 301：首页将来换个位置时，被浏览器永久缓存的 301
    会把老用户钉在 404 上（`test_chat_page.py` 同款理由）。
    """
    resp = TestClient(app).get("/", follow_redirects=False)
    assert resp.status_code == 302, (
        f"`GET /` 应回 302（首页跳转），实际 {resp.status_code}。"
        "⇒ 要么有人把它改回了返回 JSON（那首页又变回一坨 JSON），要么跳转被去掉"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应是 {EXPECTED_LOCATION}，实际 {resp.headers['location']}"
    )


def test_root_redirect_target_exists_on_disk():
    """🔴 跳转目标必须**真的在盘上** —— 目标写错时 **302 依然是 302**，服务端一个错都不报。"""
    client = TestClient(app)
    loc = client.get("/", follow_redirects=False).headers["location"]

    assert loc.startswith("/static/"), f"{loc} 不在 /static/ 下 ⇒ 本用例的换算前提不成立"
    on_disk = os.path.join(static_dir, loc[len("/static/"):])
    assert os.path.isfile(on_disk), (
        f"302 指向 {loc}，但盘上没有 {on_disk} ⇒ 访客会落到一个 404 空白页，而服务端不报错"
    )
    page = client.get(loc)
    assert page.status_code == 200, f"{loc} 应可取到 200，实际 {page.status_code}"
    assert page.headers["content-type"].startswith("text/html")


def test_service_index_json_is_not_lost():
    """🔴 原 `/` 那段 JSON **必须还在**（挪到 `/api/v1/info`）—— 「挪走不是删」是裁定原文。

    反证：把 `/api/v1/info` 那条路由删掉 ⇒ 本条立刻红（404）。
    """
    body = TestClient(app).get("/api/v1/info").json()
    assert body.get("status") == "ok", f"/api/v1/info 的 status 应是 ok，实际 {body!r}"
    assert set(body.get("services", {})) == {"public", "rag", "agent"}, (
        f"services 三个键必须原样保留（那段 JSON 的正文），实际 {body.get('services')!r}"
    )


def test_root_is_not_in_openapi():
    """`/` 是**给人打开的**跳转，⛔ 不是 API —— 进了 openapi 就等于被当成一条对外承诺。"""
    assert "/" not in app.openapi()["paths"], (
        "`/` 出现在 openapi 里了 —— 检查 `@app.get(\"/\", include_in_schema=False)` 那个参数"
    )


def _strip_comments(text: str) -> str:
    """剥掉**注释**再让下面的守卫扫 —— 本仓栽过两次同一个坑（`N14`）。

    🔴 **为什么非剥不可（2026-10-09 实测）**：`test_every_entry_card_has_a_class` 首版
    直接在原文上找 `<li` ⇒ 它命中了**本页 `<style>` 里那句注释**
    （`……写成裸 `<li>`（靠 `#primary > li` 给外观）……`）⇒ **报了两个假阳性**。
    这正是本仓记过的那条：**「判据里的字面会数到自己」**。
    📄 同型：`api/static/js/sse.test.js` 的 `stripComments`（`docs/复盘/2026-10-06-守卫的靶子没定准.md`）。

    ⛔ **有意不剥行尾 `//`** —— 剥它要区分 `https://` 里的 `//`（需要真词法器），
    而"剥错"的方向是**守卫变瞎**（假绿），比多报一次**糟得多**（同上那份复盘的口径）。
    """
    return _CSS_COMMENT.sub("", _HTML_COMMENT.sub("", text))


def _index_html() -> str:
    """首页**正文**（已剥注释）—— 下面的守卫都扫这一份。"""
    with open(os.path.join(static_dir, "web", "index.html"), encoding="utf-8") as f:
        return _strip_comments(f.read())


def test_overview_page_has_no_external_cdn():
    """🔴 **⛔ 无外网 CDN 外链**（规格 §一 硬约束 #2）—— demo 要在**离线容器**里起。

    只查 `src=` / `href=` 上的绝对地址；页面里出现的普通说明文字不算。
    """
    html = _index_html()
    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', html)
    assert urls, "首页一个 src/href 都没有 ⇒ 扫描失效了（本仓要求条数非空，防空跑）"
    bad = [u for u in urls if u.startswith(("http://", "https://", "//"))]
    assert not bad, f"首页引了外部地址 {bad} —— demo 在离线容器里会加载不出来（规格 §一 #2）"


def test_overview_page_carries_the_boundary_notices_on_first_screen():
    """🔴 **边界标注**必须在首页（规格 §3.6.1 的① · 业务方原话「**一眼就能看到**」）。

    这里只钉**结构**（五条都在、且走 `panel.js` 那一份文案）——
    ⛔ 文案本身由 `api/static/js/panel.test.js` 的「只许有一份」守着，别在这里抄第二份。
    """
    html = _index_html()
    keys = re.findall(r'data-boundary\s*=\s*["\']([^"\']+)["\']', html)
    for k in ("platform_restart", "quota", "rate_limit", "real_api", "verify"):
        assert k in keys, f"首页少了边界标注「{k}」的挂点（规格 §3.6.2 那 5 条）"
    assert "/static/js/panel.js" in html, (
        "首页没引 panel.js ⇒ 那些 `data-boundary` 挂点不会被填上文字，页面上是空白"
    )


def test_no_navigation_target_appears_twice():
    """🔴 **同一个目标⛔ 不许在一页里出现两次** —— 这条是【业务方看出来的缺陷】变成的门。

    2026-10-09 首版首页**同时**挂了侧边栏和正文卡片 ⇒
    `/chat` `/approvals` `/trace` `/eval` **各出现两次**。
    业务方原话：「**侧边栏的和主页面有重叠**」——
    ⚠️ 他说的**不是几何重叠**（那没有），是**功能重叠**：同一个地方说了两遍。

    ⇒ 裁定（2026-10-09 · 甲）：**首页去侧边栏**（门户形态 —— 首页的职责是目录，
      它不需要"我在哪个模块"的导航）；**侧边栏留内页**（那里确实要"我在哪 + 去哪"）。
      依据是行业口径：落地/门户页用顶部导航，侧边栏是"应用内导航"（Ant Design）。

    ⚠️ **当时 8 条用例全绿** —— 没有一条问过"同一个地方是不是说了两遍"。
    """
    html = _index_html()
    hrefs = re.findall(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html)
    # 🔴 先证明尺子有读数（空集合断言会一路绿着放行 —— `DEC-065` 那族）
    assert len(hrefs) >= 4, f"只认出 {len(hrefs)} 个 <a href> —— 扫描失效了"
    dupes = sorted({h for h in hrefs if hrefs.count(h) > 1})
    assert not dupes, (
        f"这些目标在同一页出现了两次：{dupes} —— 同一个地方说了两遍，"
        "读的人会以为它们是两件不同的事（业务方把这个叫「侧边栏和主页面有重叠」）"
    )


def test_overview_page_has_no_sidebar():
    """🔴 首页**不挂侧边栏**（2026-10-09 甲案）—— 与上一条是**一对**。

    ⛔ 别"顺手"把侧边栏加回来：加了它就必然与正文的卡片重复（上一条会红）。
    内页（`/chat` 等）保留侧边栏 —— 那里它是"我在哪 + 去哪"，不与正文重复。
    """
    assert 'class="sidebar"' not in _index_html(), (
        "首页挂了侧边栏 ⇒ 它和正文的卡片必然重复（见上一条用例）。"
        "首页是【目录】，不需要'我在哪个模块'的导航。"
    )


def test_every_entry_card_has_a_class():
    """🔴 **每个入口卡都必须带 `class`** —— 这条是【截图时看出来的缺陷】变成的门。

    2026-10-09 首版首页：`#others` 里「评测」那张卡**漏了 `class`** ⇒
    它**没有卡片外观**（其余 7 张都有框）⇒ 页面上**唯一可点的入口反而最不像一张卡**。
    ⚠️ 而当时 7 条用例**全绿** —— 用例只看"分区在不在 / 有没有外链 / 边界标注在不在"，
    **一条都不看卡片长什么样**（本仓原话：「**用例全绿证不了页面没坏**」，`frontend/README.md` §十一）。
    ⇒ 所以补这条**结构**判据：⛔ 不判好看，只判"**这张卡有没有被卡片规则管到**"。
    """
    html = _index_html()
    lis = re.findall(r"<li\b[^>]*>", html)
    # 🔴 先证明尺子有读数（空集合断言会一路绿着放行 —— `DEC-065` 那族）
    assert len(lis) >= 12, f"只扫到 {len(lis)} 个 <li> —— 扫描失效了（两区应有 13 个入口）"
    no_class = [t for t in lis if not re.search(r'class\s*=\s*["\'][^"\']+["\']', t)]
    assert not no_class, (
        f"这些入口卡没带 class ⇒ 它们不会拿到卡片外观（页面上会是一条裸链接）：{no_class}"
    )


def test_overview_page_has_primary_and_other_sections():
    """规格 §〇.五 #2：**上下两个分区**（⛔ 不用 Tab / 折叠 —— 那会让一半内容默认看不见）。"""
    html = _index_html()
    assert 'id="primary"' in html and 'id="others"' in html, (
        "首页缺「主要功能 / 其他功能」两个分区（规格 §〇.五 #1/#2）"
    )
    assert "<details" not in html and "<nav class=\"tabs\"" not in html, (
        "首页用了折叠/Tab —— 规格明文否决：那会让一半内容默认看不见，与最高判据相拗"
    )
