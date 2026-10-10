"""系统与执行器页入口 `GET /system` 的回归守卫（规格 §2.9 + §2.13 · 施工单**刀 6**）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本文件管什么

前四条与另几页同款（入口路由最容易在"看着没事"的情况下被改坏）。
后五条管**页面本体**，其中**三条是本页特有的**：

| # | 钉什么 | 不钉会怎样 |
|---|---|---|
| 5 | 两个脚本都引了 | 少任一个 ⇒ 页面里 `RagPanel.*` / `RagSystem.*` 全 `ReferenceError` |
| 6 | 路径由 `RagSystem.buildRequest` 出 | 🔴 **本页尤其要**：它有 3 条**根路径**（`/health` `/ready` `/metrics`），而硬约束 #8 是「URL 字面量必须带 `/api/v1`」⇒ 写字面量会被那道守卫当场拦下 |
| 7 | 四格都在 | 少一个 = 那条接口按最高判据**等于没做** |
| 8 | 🔴 **每格都要有【口径徽标】** | 这一页同时有**当场真跑**（真执行 / 真探）与**进程内累计**（指标，**重启归零**）两种数 ⇒ ⛔ 不标，读的人会把「指标为 0」当成"服务没跑过" |
| 9 | 🔴 **代码那一格必须是 `<textarea>`** | 它默认填的就是**两行代码** ⇒ 用单行 `<input>` 会**看不见后半行**，而**用例一条都不会红**（本仓原话：「**用例全绿证不了页面没坏**」） |
| 10 | 两个分区锚点必须在 | 首页那两张卡（执行器 / 系统状态）分别指 `/system#executor` 与 `/system#system`（口径 ④：同一 href ⛔ 不许在一页出现两次）<br>⚠️ **锚点没了不报错** —— 点击照常跳转，只是**落到页首** |
| 11 | 边界提示条排在提交按钮**之前** | 规格 §3.6.1 的② + 业务方原话（`DEC-123` §1.1） |

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_system_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/system.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 四格 —— 必须与 `app/static/js/system.js` 的 `RagSystem.PANELS` 的键**逐字一致**。
EXPECTED_PANELS = ("exec", "health", "ready", "metrics")

#: 两种口径的 key（`app/static/js/system.js` 的 `RagSystem.SOURCE_LABELS`）。
#: ⚠️ 页面上的 `data-source` 只放**这个 key**；徽标的文案与 class 由 `RagSystem` 填。
SOURCE_KEYS = ("live", "mem")

#: 两个分区锚点 —— 首页两张卡分别指过来（口径 ④：同一 href ⛔ 不许在一页出现两次）。
EXPECTED_ANCHORS = ("executor", "system")


def _page_path():
    return os.path.join(static_dir, PAGE_NAME)


def _page_text():
    with open(_page_path(), encoding="utf-8") as f:
        return f.read()


def _panel_blocks(text):
    """按 `data-system="…"` 切出每一格 —— ⚠️ 正则**不吃属性顺序**（`test_cost_page.py` 的教训）。"""
    return re.findall(r'<section class="panel"[^>]*data-system="[^"]+"[^>]*>.*?</section>', text, re.S)


# ==================== 入口路由（与另几页同构） ====================


def test_system_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/system", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /system` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（访客就没有系统与执行器的入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_system_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/system", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_system_is_not_in_openapi():
    assert "/system" not in app.openapi()["paths"], (
        "`/system` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体 ====================


def test_page_loads_both_scripts():
    text = _page_text()
    assert 'src="/static/js/panel.js"' in text, "页面没有引入 /static/js/panel.js"
    assert 'src="/static/js/system.js"' in text, "页面没有引入 /static/js/system.js"
    assert os.path.isfile(os.path.join(static_dir, "js", "system.js"))


def test_page_builds_urls_via_the_tested_helper():
    """页面**不许自己拼路径** —— 本页尤其要：那四条里**三条是根路径**。

    ⚠️ 判据是"**至少真调了一次**那个 helper"，⛔ 不是"文件里出现过这个名字"。
    """
    text = _page_text()
    assert re.search(r"RagSystem\.buildRequest\s*\(", text), (
        "页面没调用 RagSystem.buildRequest() —— 那四条路径是在哪儿拼的？")


def test_page_never_hardcodes_the_root_paths():
    """🔴 本页特有的：**`/health` `/ready` `/metrics` ⛔ 不许作为字面量出现在页面里**。

    为什么：它们是**根路径**，而硬约束 #8 是「每个 URL 字面量必须带 `/api/v1`」
    ⇒ 一旦有人"顺手"把它们写成字面量，`app/tests/test_web_pages.py` 会红 ——
    ⚠️ 而那条红**看起来像是"前缀写漏了"**，会把人**引向错误的修法**（去加 `/api/v1`）。
    ⇒ 本条把话说明白：**这三条本来就该走 helper，⛔ 不该有字面量**。
    """
    text = _page_text()
    for p in ("/health", "/ready", "/metrics"):
        assert f"fetch('{p}" not in text and f'fetch("{p}' not in text, (
            f"页面里出现了 `fetch({p}...)` 的字面量 —— 它是【根路径】，⛔ 不该写在页面里；"
            f"走 `RagSystem.buildRequest()`，真尺子在 `system.test.js`"
        )


def test_page_has_all_four_panels():
    """🔴 **4 格一个都不能少**（= 规格 §2.9 的 1 条 + §2.13 的 3 条）。

    ⚠️ 反证：删掉任何一个 `data-system="…"` ⇒ 本条红。
    """
    text = _page_text()
    keys = re.findall(r'data-system\s*=\s*["\']([^"\']+)["\']', text)
    assert keys, "一个 data-system 都没扫到 —— 页面结构变了，本用例的判据跟着失效（⛔ 别直接删了它）"
    missing = [k for k in EXPECTED_PANELS if k not in keys]
    assert not missing, (
        f"这些格不见了：{missing}（实扫到 {keys}）。"
        f"⇒ 每一格 = 一条接口的唯一可点入口，少一个那条接口就没有入口了。"
    )


def test_every_panel_declares_where_its_number_comes_from():
    """🔴 **每一格都要有【口径徽标】**（当场真跑 / 进程内累计）。

    为什么：这一页同时摆着两种数，而它们对「**重启后还在不在**」的答案不同。
    ⛔ 不标 ⇒ 读的人会把「指标进程内累计 = 0」当成"服务没跑过"。
    ⚠️ 判据钉的是**结构**（这格有没有声明它的来源 key），⛔ 不是"文案写得对不对"。
    """
    text = _page_text()
    blocks = _panel_blocks(text)
    assert len(blocks) == len(EXPECTED_PANELS), (
        f"按 `data-system` 切出 {len(blocks)} 段，应有 {len(EXPECTED_PANELS)} 段 —— 页面结构变了")
    for block in blocks:
        head = block.split("</div>", 1)[0]          # 只看 panel-head 那一段
        m = re.search(r'data-source\s*=\s*["\']([^"\']+)["\']', head)
        assert m, (
            f"这一格的标题上没有口径徽标（`data-source`）：{head[:80]!r}\n"
            f"⇒ 访客分不出这一格是【当场真跑】还是【进程内累计】（重启归零的那个）"
        )
        assert m.group(1) in SOURCE_KEYS, (
            f"`data-source=\"{m.group(1)}\"` 不在 {SOURCE_KEYS} 里 —— "
            f"`RagSystem.SOURCE_CLASSES` 取不到它会当场报错，而这种错只在浏览器里看得见。"
        )


def test_the_code_panel_uses_a_textarea():
    """🔴 **代码那一格必须是 `<textarea>`** —— 它默认就填着**两行**代码。

    ⚠️ 用单行 `<input>` 时：第二行**看不见**（要按方向键才滚得到），而
    上面那几条结构型用例**一条都不红**（它们只判"那格在不在 / 有没有徽标"）。
    这正是本仓那句「**用例全绿证不了页面没坏**」（`frontend/README.md` §十一）
    —— 2026-10-10 刀 5 是**靠截图**才发现同类问题的。
    """
    text = _page_text()
    blocks = _panel_blocks(text)
    exec_blocks = [b for b in blocks if 'data-system="exec"' in b]
    assert len(exec_blocks) == 1, f"应恰好切出一段 exec，实际 {len(exec_blocks)} 段"
    block = exec_blocks[0]
    assert "<textarea" in block, (
        "「执行一段 Python」那一格用的不是 `<textarea>` —— 默认那两行代码会**只看得到一行**，"
        "而这一条**没有任何别的门会红**"
    )
    # 🔴 **而且它的 label 必须带 `code-field`** —— 通用 `.field` 带 `white-space: nowrap`，
    #    那条属性**不吃 display 的覆盖** ⇒ 行内的 `<span>` 与 `inline-block` 的 `<textarea>`
    #    会被逼到**同一行**放不下 ⇒ **textarea 溢出到格子外面**
    #    （实测 2026-10-10：label 在 x=253 宽 338，textarea 跑到 **x=547**）。
    #    ⚠️ 只写 `style="display:block"` **不够** —— 这正是那次踩的坑。
    assert 'class="field code-field"' in block, (
        "代码那一格的 label 没有 `code-field` 类 ⇒ 通用 `.field` 的 `white-space: nowrap` 会生效，"
        "把 `textarea` 挤到格子外面（而**布局坏了不会有任何门红**）"
    )


def test_page_has_both_zone_anchors():
    """🔴 **两个分区锚点必须在** —— 首页那两张卡分别指 `/system#executor` 与 `/system#system`。

    ⚠️ **锚点没了不报错** —— 点击照常跳转，只是**落到页首**，
       而访客看到的是"点执行器那卡，怎么跑到最上面了"。
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
