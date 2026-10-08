"""Trace 页入口 `GET /trace` 的回归守卫（`DEC-093` · `F2`）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与 `test_approvals_page.py` 那份同款（入口路由最容易在"看着没事"的情况下被改坏）：
路由被删 / 跳转目标写错 / 混进 openapi / 跳转目标不在盘上。
后三条管**页面本体**：路径由测过的 helper 拼 · 脚本真的被引上 · 不印那两格死卡。

⚠️ **"页面里的 URL 字面量必须带 `/api/v1`"这条【已经搬走】了** ——
   现在在 `api/test_web_pages.py`，**扫 `api/static/` 下每一个 `.html`**
   （**⛔ 别搬回来**：只盯一个页面的门，下一个页面照样能坏，这正是它当初没拦住
   `approvals.html` 的原因）。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_trace_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/trace.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


def test_trace_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/trace", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /trace` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（用户就没有轨迹页入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_trace_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/trace", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_trace_is_not_in_openapi():
    assert "/trace" not in app.openapi()["paths"], (
        "`/trace` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================
# ⚠️ 「URL 字面量必须带 /api/v1」**不在这里** ⇒ `api/test_web_pages.py`
#    （它扫的是 `api/static/` 下的每一个 `.html`，比只盯本页强 —— 见文件头）。


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径** —— 路径由 `RagTrace.buildPath` / `buildCostPath` 出，
    那两个函数在 `api/static/js/trace.test.js` 里有用例钉住。

    ⚠️ 判据是"**至少调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"
       （后者过不了反证检验：注释里提一句也能过）。
    """
    text = _page_text()
    assert re.search(r"RagTrace\.buildPath\(", text), "页面没调用 RagTrace.buildPath() —— 路径是在哪儿拼的？"
    assert re.search(r"RagTrace\.buildCostPath\(", text), "页面没调用 RagTrace.buildCostPath()"


def test_page_loads_the_trace_script():
    """页面必须 `<script src>` 上 `trace.js` —— 少了它页面上每个 `RagTrace.*` 都是 ReferenceError。

    ⚠️ 这条与 `trace.test.js` 里那条（`window.RagTrace` 挂得上）**是两回事**：
       那条管"脚本挂不挂得上全局"，这条管"页面到底加没加这个脚本"。
       两条都缺一不可 —— 少任一条都有一种坏法能溜过去。
    """
    text = _page_text()
    assert 'src="/static/js/trace.js"' in text, "页面没有引入 /static/js/trace.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "trace.js"))


def test_page_does_not_print_the_two_dead_overview_cards():
    """🔴 **概览里不许再出现「总 Token」/「总花费」两格**（`DEC-093` 具体化 D）。

    它们原先读 `trace.total_tokens` / `trace.total_cost`，而 `finish_trace` 的两个
    调用点**都没传这两个值** ⇒ 两格**从上线起恒为 `--` / `¥0.0000`**。
    把永远为假的数印在页面上，正是硬门 C「最容易假完成」要防的那件事。

    反证检验：把概览卡里的标题换成「总花费」⇒ 本条红。
    ⚠️ 查的是**卡片标题**那一处形状（`.metric-l`），⛔ 不是全文禁词 ——
       页脚说明里提到"总花费"、以及页面注释里回顾这段历史，都是允许的。
    🔴 **2026-10-09 改判据**：卡片标题的 class 从 `.k` 换成了设计系统的 **`.metric-l`**
       （`frontend/README.md` §五 的 `metric` 组件）⇒ 旧正则解析不到任何卡片，
       本用例**红在了它自己那句 `assert cards` 上**（"页面结构变了，判据跟着失效"）。
       ⇒ ✅ **正是那句话在起作用** —— 它没让我静默通过，也没让我直接删用例。
    """
    text = _page_text()
    cards = re.findall(r'<div class="metric-l">([^<]*)</div>', text)
    assert cards, "没解析到概览卡片 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    for dead in ("总 Token", "总花费", "总Token"):
        assert dead not in cards, (
            f"概览卡里又出现了「{dead}」—— 它的数据源是追踪轴，那里**恒为 0**。"
            f"真金额在下半页的成本轴（查库）。"
        )
