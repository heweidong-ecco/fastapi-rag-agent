"""检索实验室页入口 `GET /lab` 的回归守卫（规格 §2.2 · 施工单**刀 3**）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与 `test_trace_page.py` / `test_chat_page.py` 那份同款（入口路由最容易在"看着没事"
的情况下被改坏）：路由被删 / 跳转目标写错 / 混进 openapi / 跳转目标不在盘上。
后三条管**页面本体**：脚本真的被引上 · 五个面板都在 · **边界提示条在提交按钮之前**。

⚠️ **"页面里的 URL 字面量必须带 `/api/v1`"这条不在这里** —— 它在 `app/tests/test_web_pages.py`，
   扫 `app/static/` 下每一个 `.html`。
   🔴 **但本页对它【空过】** —— 本页**一个 URL 字面量都没有**（5 条路径由 `RagLab.buildRequest()`
   出），全局只有额度那条 `/api/v1/agent/token/budget`。
   ⇒ 那五个 `/api/v1/rag/*` 前缀的尺子在 **`app/static/js/lab.test.js`**（与 `trace.js` 同分工）。

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_lab_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/lab.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 规格 §2.2 的那 5 条接口 —— 一个面板一条，⛔ 少一个就等于那条接口没入口。
#: ⚠️ 这几个键必须与 `app/static/js/lab.js` 的 `RagLab.PANELS` **逐字一致**（页面靠它认面板）。
EXPECTED_PANELS = ("pg", "hybrid", "rerank", "rewrite", "pipeline")


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


# ==================== 入口路由（与另五页同构） ====================


def test_lab_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/lab", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /lab` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（访客就没有检索实验室入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_lab_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/lab", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_lab_is_not_in_openapi():
    assert "/lab" not in app.openapi()["paths"], (
        "`/lab` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================


def test_page_loads_both_scripts():
    """页面必须挂上 `panel.js` **和** `lab.js`。

    ⚠️ 少任一个都是一种坏法，而**两侧都抓不到**：
      · 少 `panel.js` ⇒ 页面里每处 `RagPanel.xxx` `ReferenceError`（边界标注一条都填不上）；
      · 少 `lab.js`   ⇒ 每处 `RagLab.xxx` `ReferenceError`（5 个面板全都跑不起来）。
    `node --test` 走的是 `module.exports`，**管不到"页面加没加这个 <script>"**。
    """
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert 'src="/static/js/lab.js"' in text, "页面没有引入 /static/js/lab.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "lab.js"))


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径/字段名** —— 它们由 `RagLab.buildRequest` 出
    （那 5 个带 `/api/v1` 的路径在 `app/static/js/lab.test.js` 里有用例钉住）。

    ⚠️ 判据是"**至少真调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"
       （后者过不了反证检验：注释里提一句也能过）。
    """
    text = _page_text()
    assert re.search(r"RagLab\.buildRequest\s*\(", text), (
        "页面没调用 RagLab.buildRequest() —— 那 5 条路径是在哪儿拼的？"
    )


def test_page_has_all_five_panels():
    """🔴 **5 个面板一个都不能少** —— 每个面板 = 规格 §2.2 的一条接口的**唯一可点入口**。

    少一个的后果不是"页面难看"，是**那条接口按最高判据等于没做**（「显示了才知道你有做」）。
    ⚠️ 反证：删掉任何一个 `data-panel="…"` ⇒ 本条红。
    """
    text = _page_text()
    keys = re.findall(r'data-panel\s*=\s*["\']([^"\']+)["\']', text)
    # 🔴 先证明尺子有读数（空集合断言会一路绿着放行 —— `DEC-065` 那族）
    assert keys, "一个 data-panel 都没扫到 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    missing = [k for k in EXPECTED_PANELS if k not in keys]
    assert not missing, (
        f"这些面板不见了：{missing}（实扫到 {keys}）。"
        f"⇒ 规格 §2.2 的 5 条检索接口各有面板，少一个那条接口就没有可点入口了。"
    )


def test_each_panel_shows_a_boundary_notice_before_its_run_button():
    """🔴 **边界提示条必须排在提交按钮【之前】**（规格 §3.6.1 的② · 硬约束 #7）。

    业务方原话：「**让别人在用接口的时候要先看到这个提示，才给接口**」
    ⇒ ⛔ 不是页脚挂一行小字、⛔ 不是 tooltip。**顺序本身是要求。**

    ⚠️ 判据钉的是【在两个标记的先后】，⛔ 不是"文件里有没有 `data-boundary` 这个词"
       —— 后者过不了反证检验（把提示条挪到按钮**后面**它照样有）。
    """
    text = _page_text()
    blocks = re.findall(r'<section class="panel" data-panel="[^"]+".*?</section>', text, re.S)
    assert len(blocks) == len(EXPECTED_PANELS), (
        f"按 `data-panel` 切出 {len(blocks)} 段，应有 {len(EXPECTED_PANELS)} 段 —— 页面结构变了"
    )
    for block in blocks:
        i_boundary = block.find("data-boundary")
        i_button = block.find("<button")
        assert i_boundary != -1, f"这个面板没有边界提示条：{block[:60]!r}"
        assert i_button != -1, f"这个面板没有提交按钮：{block[:60]!r}"
        assert i_boundary < i_button, (
            "边界提示条排在了提交按钮【之后】⇒ 与业务方原话相拗"
            "（「让别人在用接口的时候要先看到这个提示，才给接口」）"
        )
