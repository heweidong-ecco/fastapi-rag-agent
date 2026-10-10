"""工具与记忆页入口 `GET /tools` 的回归守卫（规格 §2.7 + §2.8 · 施工单**刀 5**）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与另几页同款（入口路由最容易在"看着没事"的情况下被改坏）。
后五条管**页面本体**，其中**三条是本页特有的**：

| # | 钉什么 | 不钉会怎样 |
|---|---|---|
| 5 | 两个脚本都引了 | 少任一个 ⇒ 页面里 `RagPanel.*` / `RagTools.*` 全 `ReferenceError` |
| 6 | 路径由 `RagTools.buildRequest` 出 | 页面自己拼路径 ⇒ 少 `/api/v1` 不报错（`DEC-094`） |
| 7 | 七格都在 | 少一个 = 那条接口按最高判据**等于没做** |
| 8 | 🔴 **每格都要有【口径徽标】** | 这一页同时有**进程内存 / 代码常量 / 真调 MCP / 容器磁盘**四种来源，<br>而它们对「重启后还在不在」的答案**不同**。⛔ 不标 ⇒ 读的人**会把"进程内存 0"当成"工具都没了"**（`DEC-047` 真栽过：库里有 4216 tokens，界面答 0，**不报错**） |
| 9 | 🔴 **两个分区锚点必须在** | 首页那两张卡分别指 `/tools#tools` 与 `/tools#memory`（口径 ④：同一个 href ⛔ 不许在一页出现两次 ⇒ 只能靠锚点分开）。<br>⚠️ **锚点没了不报错** —— 点击照常跳转，只是**落到页首**，访客以为自己点错了 |
| 10 | 边界提示条排在提交按钮**之前** | 规格 §3.6.1 的② + 业务方原话（`DEC-123` §1.1） |

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_tools_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/tools.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 七格 —— 必须与 `app/static/js/tools.js` 的 `RagTools.PANELS` 的键**逐字一致**。
EXPECTED_PANELS = (
    "available", "health", "refresh", "versions", "mcp", "memadd", "memsearch",
)

#: 五种口径的 key（`app/static/js/tools.js` 的 `RagTools.SOURCE_LABELS`）。
#: ⚠️ 页面上的 `data-source` 只放**这个 key**；徽标的文案与 class 由 `RagTools` 填
#:    ⇒ ⛔ 判据不能是"页面里有没有 `src-mem` 这个词"（那会把两份实现拆开）。
SOURCE_KEYS = ("mem", "const", "live", "disk", "mixed")

#: 两个分区锚点 —— 首页两张卡分别指过来（口径 ④：同一 href ⛔ 不许在一页出现两次）。
EXPECTED_ANCHORS = ("tools", "memory")


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


def _panel_blocks(text):
    """按 `data-tools="…"` 切出每一格 —— ⚠️ 正则**不吃属性顺序**（`test_cost_page.py` 的教训）。"""
    return re.findall(r'<section class="panel"[^>]*data-tools="[^"]+"[^>]*>.*?</section>', text, re.S)


# ==================== 入口路由（与另几页同构） ====================


def test_tools_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/tools", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /tools` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（访客就没有工具与记忆的入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_tools_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/tools", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_tools_is_not_in_openapi():
    assert "/tools" not in app.openapi()["paths"], (
        "`/tools` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================


def test_page_loads_both_scripts():
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert 'src="/static/js/tools.js"' in text, "页面没有引入 /static/js/tools.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "tools.js"))


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径** —— 那七条带 `/api/v1` 的路径在 `app/static/js/tools.test.js` 里有用例钉住。

    ⚠️ 判据是"**至少真调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"。
    """
    text = _page_text()
    assert re.search(r"RagTools\.buildRequest\s*\(", text), (
        "页面没调用 RagTools.buildRequest() —— 那七条路径是在哪儿拼的？")


def test_page_has_all_seven_panels():
    """🔴 **7 格一个都不能少**（= 规格 §2.7 的 5 条 + §2.8 的 `memory/add` · `memory/search`）。

    ⚠️ 反证：删掉任何一个 `data-tools="…"` ⇒ 本条红。
    """
    text = _page_text()
    keys = re.findall(r'data-tools\s*=\s*["\']([^"\']+)["\']', text)
    assert keys, "一个 data-tools 都没扫到 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    missing = [k for k in EXPECTED_PANELS if k not in keys]
    assert not missing, (
        f"这些格不见了：{missing}（实扫到 {keys}）。"
        f"⇒ 每一格 = 一条接口的唯一可点入口，少一个那条接口就没有入口了。"
    )


def test_every_panel_declares_where_its_number_comes_from():
    """🔴 **每一格都要有【口径徽标】**（进程内存 / 代码常量 / 真调 MCP / 容器磁盘 / 常量+内存）。

    为什么：这一页同时摆着几种来源，而它们对「**重启后还在不在**」的答案**不同**。
    ⛔ 不标 ⇒ 读的人会把「进程内存 0」当成「工具都没了」——
    本仓真栽过：`/agent/cost/overview` 曾读进程内存，库里有 4216 tokens 它答 `0`，**不报错**（`DEC-047`）。

    ⚠️ 判据钉的是**结构**（这格有没有声明它的来源 key），⛔ 不是"文案写得对不对"
       —— 文案与 class 由 `tools.js` 那一份填，由 `tools.test.js` 钉。
    ⚠️ 页面上的 `data-source` 放的是**来源 key**（`mem` / `const` / …），⛔ 不是 class
       —— 这样"哪一格的来源是什么"在 HTML 与 JS 之间**只有一个来源**。
    """
    text = _page_text()
    blocks = _panel_blocks(text)
    assert len(blocks) == len(EXPECTED_PANELS), (
        f"按 `data-tools` 切出 {len(blocks)} 段，应有 {len(EXPECTED_PANELS)} 段 —— 页面结构变了")
    for block in blocks:
        head = block.split("</div>", 1)[0]          # 只看 panel-head 那一段
        m = re.search(r'data-source\s*=\s*["\']([^"\']+)["\']', head)
        assert m, (
            f"这一格的标题上没有口径徽标（`data-source`）：{head[:80]!r}\n"
            f"⇒ 访客分不出这一格是【代码常量】还是【进程内存】（重启归零的那个）"
        )
        assert m.group(1) in SOURCE_KEYS, (
            f"`data-source=\"{m.group(1)}\"` 不在 {SOURCE_KEYS} 里 —— "
            f"`RagTools.SOURCE_CLASSES` 取不到它会当场报错，而这种错只在浏览器里看得见。"
        )


def test_page_has_both_zone_anchors():
    """🔴 **两个分区锚点必须在** —— 首页那两张卡分别指 `/tools#tools` 与 `/tools#memory`。

    ⚠️ 为什么需要（口径 ④ · `DEC-124` 的同一条）：**同一个 href ⛔ 不许在一页出现两次** ⇒
       「工具 / MCP」与「记忆」两张卡**只能靠锚点分开**。
    ⚠️ **锚点没了不报错** —— 点击照常跳转，只是**落到页首**，
       而访客看到的是"点工具那卡，怎么跑到最上面了"（本仓对这类静默失效的立场：**照出它**）。
    """
    text = _page_text()
    for a in EXPECTED_ANCHORS:
        assert f'id="{a}"' in text, (
            f"分区锚点 `#{a}` 不见了 —— 首页那张卡指过来会落到页首（而**不报任何错**）")


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
