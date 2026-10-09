"""成本看板页入口 `GET /cost` 的回归守卫（规格 §2.5 + §2.6 · 施工单**刀 4**）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与另几页同款（入口路由最容易在"看着没事"的情况下被改坏）。
后四条管**页面本体**，其中**两条是本页特有的**：

| # | 钉什么 | 不钉会怎样 |
|---|---|---|
| 5 | 两个脚本都引了 | 少任一个 ⇒ 页面里 `RagPanel.*` / `RagCost.*` 全 `ReferenceError` |
| 6 | 路径由 `RagCost.buildRequest` 出 | 页面自己拼路径 ⇒ 少 `/api/v1` 不报错（`DEC-094`） |
| 7 | 九个面板都在 | 少一个 = 那条接口按最高判据**等于没做** |
| 8 | 🔴 **每个面板都要有【口径标签】** | 这一页同时有**读库 / 进程内存 / 配置常量**三种数，而它们对"重启后还在不在"的答案不同<br>⛔ 不标 ⇒ 读的人**会把"进程内存 0"当成"我没花过钱"**（`DEC-047` 真栽过：库里有 4216 tokens，界面答 0，**不报错**） |
| 9 | 🔴 **三条【有意不露】的接口不许被页面请求** | 其中 `token/recent` 返回的记录**带别人的 user_name** ⇒ 露给公开访客是越权 |
| 10 | 边界提示条排在提交按钮**之前** | 规格 §3.6.1 的② + 业务方原话（`DEC-123` §1.1） |

📌 判据（可打印）：`venv/bin/python -m pytest api/test_cost_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/cost.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 九个面板 —— 必须与 `api/static/js/cost.js` 的 `RagCost.PANELS` 的键**逐字一致**。
EXPECTED_PANELS = (
    "overview", "records", "history", "monthly", "budget",
    "memusage", "check", "estimates", "intercepts",
)

#: 🔴 三条【有意不露】—— 页面⛔ 不许请求它们（`DEC-124`）。理由见 `RagCost.NOT_EXPOSED`。
NOT_EXPOSED = (
    "/api/v1/agent/token/recent",
    "/api/v1/agent/token/purpose",
    "/api/v1/agent/token/thread",
)

#: 三种口径标签的 class（`api/static/web/cost.html` 的 `<style>` 里定义）。
SOURCE_CLASSES = ("src-db", "src-mem", "src-const")


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


# ==================== 入口路由（与另几页同构） ====================


def test_cost_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/cost", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /cost` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（访客就没有成本看板入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_cost_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/cost", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_cost_is_not_in_openapi():
    assert "/cost" not in app.openapi()["paths"], (
        "`/cost` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================


def test_page_loads_both_scripts():
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert 'src="/static/js/cost.js"' in text, "页面没有引入 /static/js/cost.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "cost.js"))


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径** —— 那九条带 `/api/v1` 的路径在 `api/static/js/cost.test.js` 里有用例钉住。

    ⚠️ 判据是"**至少真调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"。
    """
    text = _page_text()
    assert re.search(r"RagCost\.buildRequest\s*\(", text), (
        "页面没调用 RagCost.buildRequest() —— 那 9 条路径是在哪儿拼的？"
    )


def test_page_has_all_nine_panels():
    """🔴 **9 个面板一个都不能少**（= 规格 §2.5 的 9 条 + §2.6 的 3 条 − 有意不露的 3 条）。

    ⚠️ 反证：删掉任何一个 `data-cost="…"` ⇒ 本条红。
    """
    text = _page_text()
    keys = re.findall(r'data-cost\s*=\s*["\']([^"\']+)["\']', text)
    assert keys, "一个 data-cost 都没扫到 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    missing = [k for k in EXPECTED_PANELS if k not in keys]
    assert not missing, (
        f"这些面板不见了：{missing}（实扫到 {keys}）。"
        f"⇒ 每个面板 = 一条接口的唯一可点入口，少一个那条接口就没有入口了。"
    )


def test_every_panel_declares_where_its_number_comes_from():
    """🔴 **每个面板都要有【口径标签】**（读库 / 进程内存 / 配置常量）—— 本页最要紧的一条。

    为什么：这一页同时摆着三种数，而它们对「**重启后还在不在**」的答案**不同**。
    ⛔ 不标 ⇒ 读的人会把「进程内存 0」当成「我没花过钱」——
    本仓真栽过：`/agent/cost/overview` 曾读进程内存，库里有 4216 tokens 它答 `0`，**不报错、界面照常出数**（`DEC-047`）。

    ⚠️ 判据钉的是**结构**（那张卡上有没有三类标签之一），⛔ 不是"文案写得对不对"
       —— 文案是 `RagCost.SOURCE_LABELS` 那一份，由 `cost.test.js` 钉。
    """
    text = _page_text()
    # ⚠️ 正则**不吃属性顺序** —— 2026-10-09 实测：给其中一个面板加了 `id="…"`（做锚点用）
    #    之后，写死 `class="panel" data-cost="…"` 的版本**当场失配**，两条用例一起红。
    #    ⇒ 这正是本仓那条「门的靶子要定准」：判据要钉**语义**，⛔ 不钉属性的书写顺序。
    blocks = re.findall(r'<section class="panel"[^>]*data-cost="[^"]+"[^>]*>.*?</section>', text, re.S)
    assert len(blocks) == len(EXPECTED_PANELS), (
        f"按 `data-cost` 切出 {len(blocks)} 段，应有 {len(EXPECTED_PANELS)} 段 —— 页面结构变了")
    for block in blocks:
        head = block.split("</div>", 1)[0]          # 只看 panel-head 那一段
        assert any(c in head for c in SOURCE_CLASSES), (
            f"这个面板的标题上没有口径标签（{SOURCE_CLASSES} 之一）：{head[:80]!r}\n"
            f"⇒ 访客分不出这一格是【读库】还是【进程内存】（重启归零的那个）"
        )


def test_page_never_requests_the_three_not_exposed_endpoints():
    """🔴 三条【有意不露】的接口⛔ 不许被这个页面请求（`DEC-124` §1）。

    最要紧的是 `/agent/token/recent` —— 它读的是进程内那张**所有人共用**的记录表，
    **每条记录里都带别人的 `user_name`**。露给公开访客就是**越权**。

    ⚠️ 判据 = **页面源码里不许出现这三条路径的任何一条**。
       ⛔ 别改成"在 `RagCost.NOT_EXPOSED` 里查一下" —— 那张表是**说明用**的，
          本用例要拦的是"有人把其中一条**接到了页面上**"。
    """
    text = _page_text()
    for path in NOT_EXPOSED:
        assert path not in text, (
            f"页面里出现了 {path} —— 它属于【有意不露】那三条（见 `DEC-124`）：\n"
            f"  · token/recent 每条记录带【别人的 user_name】\n"
            f"  · token/purpose / token/thread 是【全站口径、不分用户】\n"
            f"⇒ 公开 demo ⛔ 不露；它们各有本人口径的替代出口。"
        )


def test_each_panel_shows_a_boundary_notice_before_its_run_button():
    """🔴 **边界提示条必须排在提交按钮【之前】**（规格 §3.6.1 的② · 硬约束 #7 · `DEC-123` §1.1）。

    业务方原话：「**让别人在用接口的时候要先看到这个提示，才给接口**」。
    ⚠️ 判据钉的是【两个标记的先后】，⛔ 不是"文件里有没有 `data-boundary` 这个词"
       —— 后者过不了反证检验（把提示条挪到按钮**后面**它照样有）。
    """
    text = _page_text()
    # ⚠️ 正则**不吃属性顺序** —— 2026-10-09 实测：给其中一个面板加了 `id="…"`（做锚点用）
    #    之后，写死 `class="panel" data-cost="…"` 的版本**当场失配**，两条用例一起红。
    #    ⇒ 这正是本仓那条「门的靶子要定准」：判据要钉**语义**，⛔ 不钉属性的书写顺序。
    blocks = re.findall(r'<section class="panel"[^>]*data-cost="[^"]+"[^>]*>.*?</section>', text, re.S)
    assert len(blocks) == len(EXPECTED_PANELS), "面板段数不对 —— 先核页面结构"
    for block in blocks:
        i_boundary = block.find("data-boundary")
        i_button = block.find("<button")
        assert i_boundary != -1, f"这个面板没有边界提示条：{block[:60]!r}"
        assert i_button != -1, f"这个面板没有提交按钮：{block[:60]!r}"
        assert i_boundary < i_button, (
            "边界提示条排在了提交按钮【之后】⇒ 与业务方原话相拗"
            "（「让别人在用接口的时候要先看到这个提示，才给接口」）"
        )
