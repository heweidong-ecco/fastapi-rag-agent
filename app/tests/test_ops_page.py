"""运维探针页入口 `GET /ops` 的回归守卫（规格 §2.12 · §3.7 · 施工单**刀 7**）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与另几页同款（入口路由最容易在"看着没事"的情况下被改坏）。
中间四条管**页面本体**的结构。
🔴 **后三条是本页特有的** —— 它们钉的是 `DEC-141` 给这一页定的那个前提。

| # | 钉什么 | 不钉会怎样 |
|---|---|---|
| 5 | 两个脚本都引了 | 少任一个 ⇒ 页面里 `RagPanel.*` / `RagOps.*` 全 `ReferenceError` |
| 6 | 路径由 `RagOps.buildRequest` 出 | 字面量少写 `/api/v1` ⇒ **四条全 404，而页面不报任何错**（`DEC-094` 那个前科） |
| 7 | 四格都在 | 少一个 = 那条接口按最高判据**等于没做** |
| 8 | 🔴 **每格都要有【口径徽标】** | 这页同时摆 **Redis**（键与桶）与**真库**（行）两种数 ⇒ ⛔ 不标就被读成同一种 |
| 9 | 🔴 **每格的边界提示条排在提交按钮【之前】** | 规格 §3.6.1 的② + 业务方原话（`DEC-123` §1.1） |
| 10 | 🔴🔴 **页面里⛔ 不许有任何 `user_name` 输入框** | 见下 |
| 11 | 🔴🔴 **页面里⛔ 不许出现带 `{...}` 的路径** | 见下 |
| 12 | 🔴 **「调试视角」那条声明必须在，且排在第一个提交按钮【之前】** | 施工单刀 7 点名的那一条 |

### 🔴 第 10 / 11 条为什么单独立（本页特有的）

`DEC-141` 敢把这 4 条从「要管理员」降到「登录即可」的**唯一前提**，是
**`/debug/quota/{user_name}` 与 `/debug/rate_limit/{user_name}` 的路径形参被删掉了**
（那两条原先「**可枚举用户名**」，这正是 `DEC-065` 当初加 `require_admin` 的理由）。

⇒ **这一页上不允许有任何"查谁"的入口**：
* 有输入框 ⇒ 它**看起来能查别人**，而服务端**根本不收那个参数**
  （静默忽略、查的仍是调用者自己）⇒ 那个框是**假的**，比没有更糟；
* 路径里写回 `{...}` ⇒ **越权面回来**。

⚠️ 真尺子在两处，⛔ 不止本文件：
`app/tests/test_debug_endpoints_self_only.py`（查**路由表**）· `app/static/js/ops.test.js`（查 **`PANELS` 的 path**）。
本文件管的是**页面这一侧**。

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_ops_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/ops.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 四格 —— 必须与 `app/static/js/ops.js` 的 `RagOps.PANELS` 的键**逐字一致**。
EXPECTED_PANELS = ("cache", "count", "quota", "rate")

#: 两种口径的 key（`app/static/js/ops.js` 的 `RagOps.SOURCE_LABELS`）。
#: ⚠️ 页面上的 `data-source` 只放**这个 key**；徽标的文案与 class 由 `RagOps` 填。
SOURCE_KEYS = ("redis", "db")


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    """剥掉 HTML 注释与 JS 行注释。

    🔴 **为什么必须剥**：本页的注释里**大量在讲**那条被删掉的路径（那是沿革记录，给人读的）。
    不剥的话，第 11 条会**报在它自己头上** —— 本仓栽过同型的第 5 次，纪律是
    「**要提那串，就拆开写或只描述它**」。⚠️ 这里采取的是"剥注释"，因为注释是**有意的记录**。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//[^\n]*", r"\1", text, flags=re.M)
    return text


def _panel_blocks(text):
    """按 `data-ops="…"` 切出每一格 —— ⚠️ 正则**不吃属性顺序**（`test_cost_page.py` 的教训）。"""
    return re.findall(r'<section class="panel"[^>]*data-ops="[^"]+"[^>]*>.*?</section>', text, re.S)


# ==================== 入口路由（与另几页同构） ====================


def test_ops_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/ops", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /ops` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（访客就没有运维探针的入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_ops_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/ops", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_ops_is_not_in_openapi():
    assert "/ops" not in app.openapi()["paths"], (
        "`/ops` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================


def test_page_loads_both_scripts():
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert 'src="/static/js/ops.js"' in text, "页面没有引入 /static/js/ops.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "ops.js"))


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径**。

    ⚠️ 判据是"**至少真调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"。
    """
    text = _page_text()
    assert re.search(r"RagOps\.buildRequest\s*\(", text), (
        "页面没调用 RagOps.buildRequest() —— 那四条路径是在哪儿拼的？")


def test_page_has_all_four_panels():
    """🔴 **4 格一个都不能少**（= 规格 §2.12 的 4 条）。

    ⚠️ 反证：删掉任何一个 `data-ops="…"` ⇒ 本条红。
    """
    text = _page_text()
    keys = re.findall(r'data-ops\s*=\s*["\']([^"\']+)["\']', text)
    assert keys, "一个 data-ops 都没扫到 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    missing = [k for k in EXPECTED_PANELS if k not in keys]
    assert not missing, (
        f"这些格不见了：{missing}（实扫到 {keys}）。"
        f"⇒ 每一格 = 一条接口的唯一可点入口，少一个那条接口就没有入口了。"
    )


def test_every_panel_declares_where_its_number_comes_from():
    """🔴 **每一格都要有【口径徽标】**（Redis / 真库）。

    为什么：这一页同时摆着**两种来源**，而它们对「**重启后还在不在**」的答案不同。
    ⛔ 不标 ⇒ 读的人会把「Redis 里的 0 条缓存」当成"缓存坏了"。
    ⚠️ 判据钉的是**结构**（这格有没有声明它的来源 key），⛔ 不是"文案写得对不对"。
    """
    text = _page_text()
    blocks = _panel_blocks(text)
    assert len(blocks) == len(EXPECTED_PANELS), (
        f"按 `data-ops` 切出 {len(blocks)} 段，应有 {len(EXPECTED_PANELS)} 段 —— 页面结构变了")
    for block in blocks:
        head = block.split("</div>", 1)[0]          # 只看 panel-head 那一段
        m = re.search(r'data-source\s*=\s*["\']([^"\']+)["\']', head)
        assert m, (
            f"这一格的标题上没有口径徽标（`data-source`）：{head[:80]!r}\n"
            f"⇒ 访客分不出这一格读的是【Redis】还是【真库】"
        )
        assert m.group(1) in SOURCE_KEYS, (
            f"`data-source=\"{m.group(1)}\"` 不在 {SOURCE_KEYS} 里 —— "
            f"`RagOps.SOURCE_CLASSES` 取不到它会当场报错，而这种错只在浏览器里看得见。"
        )


def test_each_panel_shows_a_boundary_notice_before_its_run_button():
    """🔴 **边界提示条必须排在提交按钮【之前】**（规格 §3.6.1 的② · 硬约束 #7 · `DEC-123` §1.1）。

    业务方原话：「**让别人在用接口的时候要先看到这个提示，才给接口**」。
    ⚠️ 判据钉的是【两个标记的先后】，⛔ 不是"文件里有没有 `data-boundary` 这个词"
       —— 后者过不了反证检验（把提示条挪到按钮**后面**它照样有）。
    """
    text = _page_text()
    blocks = _panel_blocks(text)
    assert len(blocks) == len(EXPECTED_PANELS), "面板段数不对 —— 先核页面结构"
    for block in blocks:
        i_boundary = block.find("data-boundary")
        i_button = block.find("<button")
        assert i_boundary != -1, f"这一格没有边界提示条：{block[:60]!r}"
        assert i_button != -1, f"这一格没有提交按钮：{block[:60]!r}"
        assert i_boundary < i_button, (
            "边界提示条排在了提交按钮【之后】⇒ 与业务方原话相拗"
            "（「让别人在用接口的时候要先看到这个提示，才给接口」）"
        )


def test_page_has_no_place_to_type_someone_elses_name():
    """🔴🔴 **页面里⛔ 不许有任何"查谁"的入口**（`DEC-141` 的前提）。

    那条前提是：两条端点的 `{user_name}` **路径形参被删掉了** ⇒ 服务端**只认调用者**。

    ⇒ 页面上若有 `user_name` 输入框：
    ① 它**看起来能查别人**；② 而服务端**根本不收那个参数**（静默忽略，查的仍是自己）
    ⇒ 那个框是**假的** —— 比没有更糟（本仓立场：「**显示了，才知道你有做**」的反面：
    **显示了一个做不到的东西**）。

    ⚠️ **剥掉注释再扫** —— 页面里**有意**用注释记录着那条被删掉的路径（沿革），
       不剥的话本条会报在它自己头上（本仓栽过同型 5 次）。
    ⚠️ **反证**：给任意一格加一个 `<input data-param="user_name">` ⇒ 本条红。
    """
    live = _strip_comments(_page_text())
    assert "data-param" not in live, (
        "页面里出现了 `data-param` —— 本页 **4 条端点一个参数都不收**（`DEC-141` 把形参删了）\n"
        "⇒ 任何参数控件都是**摆设**：服务端静默忽略它，查的仍是调用者自己"
    )
    assert "user_name" not in live, (
        "页面的**活代码**里出现了 `user_name` —— 本页⛔ 没有任何「查谁」的入口（`DEC-141`）"
    )


def test_page_has_no_path_parameter_in_any_url():
    """🔴🔴 **页面里⛔ 不许出现带 `{...}` 的路径**（`DEC-141` 的前提 · 另一半）。

    ⚠️ 与上一条**分工不同**：上一条管"控件"，这条管"路径字面量"。
    两者都能把**越权面**弄回来，而**只有这一条**能测出"照旧文档把 `{user_name}` 写回去"。

    ⚠️ 剥注释再扫（同上）。
    ⚠️ **反证**：把任意一格的 `buildRequest` 调用处改成写死一条带 `{}` 的路径 ⇒ 本条红。
    """
    live = _strip_comments(_page_text())
    hits = re.findall(r"/api/v1/[A-Za-z0-9_/]*\{[^}]*\}", live)
    assert hits == [], (
        f"页面里出现了带形参的路径：{hits}\n"
        f"⇒ 那正是 `DEC-141` 删掉的东西 —— 加回来 = **越权面回来**，"
        f"而这一页的整个存在理由就是「只查你自己」"
    )


def test_debug_view_notice_is_present_and_comes_first():
    """🔴 **「这是调试视角，⛔ 不是产品功能」必须写在页面上，且排在第一个提交按钮【之前】**。

    施工单刀 7 点名的那一条。为什么单独立：这 4 条**名字带 `debug`**，
    访客点进来会把它读成"产品功能"，然后拿这里的数去问"为什么我的额度是这样"。
    ⛔ 不说清 ⇒ 这一页会把**运维视角**与**用户视角**混成一件事。
    ⚠️ 判据钉的是【它存在 + 它的先后】，⛔ 不是"文案写得对不对"。
    ⚠️ **比的是【面板的提交按钮】（`data-run`），⛔ 不是页面里第一个 `<button>`** ——
       页头那颗「保存 API Key」按设计就在最上面（所有页面都这样）。
       本仓 2026-10-10 试过写 `text.find("<button")`，**当场红**、值 2645 vs 2398 ⇒
       那是把"页头那颗"当成了"接口之前"的标尺（**判据选错了量**，不是页面错了）。
    """
    text = _page_text()
    m = re.search(r'id="debugview"', text)
    assert m, "页面上没有那段【调试视角】声明（`id=\"debugview\"`）—— 施工单刀 7 点名要有"
    i_notice = m.start()
    i_first_run = text.find("data-run")
    assert i_first_run != -1, "页面里一个面板按钮都没有 —— 结构变了"
    assert i_notice < i_first_run, (
        "【调试视角】那条排在了**面板的提交按钮之后**（多半是被挪到下面去了）\n"
        "⇒ 那正是本仓那句「**门挂在别处，就等于没有门**」的同型：提示写在按钮后面 = 提示不存在"
    )
    assert "调试视角" in text[i_notice:i_notice + 400], (
        "`debugview` 那一段里没有「调试视角」四个字 —— 它现在讲的是别的事"
    )
