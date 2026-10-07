"""Eval 页入口 `GET /eval` 的回归守卫（`DEC-097` · `F3`）。

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 本页与另外三个页面【不一样】—— 它是**占位页**

`/chat` `/approvals` `/trace` 都是**功能页**（有取数、有交互）。
本页**没有数据源**（后端**没有任何 `/agent/eval*` 路由**，`B14` 仍是 ⬜），
所以它只做两件事：**一个按钮** + 点开后**一行字**（`DEC-097` 业务方裁剪的口径）。

⚠️ **正因为它是占位页，才更需要守卫** —— 占位页没人看，改坏了不会有人发现：
   路由被删 ⇒ 没入口；跳转目标改名 ⇒ 302 照样 302、用户落到 404、**服务端不报错**。

## 本文件管什么

前三条与 `test_approvals_page.py` / `test_trace_page.py` 那两份同款。
后两条管**页面本体这个占位页的契约**：① 有个按钮 ② 按钮指向的那个子页**真的在**。

⚠️ **"页面里的 URL 字面量必须带 `/api/v1`"这条不在这里** ——
   它在 `api/test_web_pages.py`，**扫 `api/static/` 下每一个 `.html`**（⛔ 别搬回来）。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_eval_page.py -q -p no:warnings`
"""
import os
import re

from fastapi.testclient import TestClient

from main import app, static_dir

STATIC_PREFIX = "/static/"
PAGE_NAME = "web/eval.html"
SUBPAGE_NAME = "web/eval_gate.html"
EXPECTED_LOCATION = STATIC_PREFIX + PAGE_NAME

#: 子网页上**唯一的那一行字**（`DEC-097`）。⛔ 改它要同时改本处与页面 ——
#: 这正是本条用例的用途：**防止它被"顺手"改成别的**。
SUBPAGE_LINE = "agent-eval-gate · Agent 生产就绪评测门 · TODO"


def _page_path(name=PAGE_NAME):
    return os.path.join(static_dir, name)


def _page_text(name=PAGE_NAME):
    with open(_page_path(name), encoding="utf-8") as f:
        return f.read()


# ==================== 入口路由（与另外三页同款）====================


def test_eval_redirects_to_static_page():
    client = TestClient(app)
    resp = client.get("/eval", follow_redirects=False)

    assert resp.status_code == 302, (
        f"`GET /eval` 应回 302，实际 {resp.status_code}。"
        "⇒ 要么这条路由没了（用户就没有 Eval 页入口了），要么有人把它改成直接返回文件"
    )
    assert resp.headers["location"] == EXPECTED_LOCATION, (
        f"跳转目标应指向 {EXPECTED_LOCATION}，实际 {resp.headers['location']}")


def test_eval_redirect_target_exists_on_disk():
    """🔴 **目标写错时，302 依然是 302** —— 用户会落到一个 404 空白页，而服务端不报错。"""
    client = TestClient(app)
    loc = client.get("/eval", follow_redirects=False).headers["location"]

    assert loc.startswith(STATIC_PREFIX), f"跳转目标 {loc} 不在 {STATIC_PREFIX} 下"
    on_disk = os.path.join(static_dir, loc[len(STATIC_PREFIX):])
    assert os.path.isfile(on_disk), f"302 指向 {loc}，但盘上没有 {on_disk}"

    page = client.get(loc)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


def test_eval_is_not_in_openapi():
    assert "/eval" not in app.openapi()["paths"], (
        "`/eval` 出现在 openapi 里了 —— 检查 `include_in_schema=False` 是不是被顺删了")


# ==================== 页面本体（这个【占位页】的契约）====================


def test_page_has_a_button_pointing_at_the_subpage():
    """页面必须有一个**链接到子网页**的按钮（`DEC-097` 的落地口径）。

    ⚠️ 判据是"**href 真的指向那个子页**" —— ⛔ 不是"文件里出现过按钮这个词"。
       反证检验：把 `href` 改成 `#`（或删掉 `<a>`）⇒ 本条红。
    """
    text = _page_text()
    hrefs = re.findall(r'<a\b[^>]*\bhref="([^"]*)"', text)
    assert hrefs, "页面里没有 `<a href=...>` —— 业务方要的「一个按钮点击可以跳转」没落地"
    assert STATIC_PREFIX + SUBPAGE_NAME in hrefs, (
        f"按钮没有指向子网页 {STATIC_PREFIX + SUBPAGE_NAME}，实际 href = {hrefs}"
    )


def test_subpage_exists_and_carries_the_one_line():
    """子网页必须**在盘上**，且正文里**有那一行字**。

    ⚠️ 两件事都测：① 文件在（否则点过去是 404，而**服务端不报错**）
       ② 那一行在（占位页的全部内容就是它，被"顺手"改掉就等于内容变了）
    """
    assert os.path.isfile(_page_path(SUBPAGE_NAME)), (
        f"子网页 {SUBPAGE_NAME} 不在盘上 ⇒ 按钮点过去是 404"
    )
    text = _page_text(SUBPAGE_NAME)
    assert SUBPAGE_LINE in text, (
        f"子网页里没有那一行字：{SUBPAGE_LINE!r}\n"
        f"⇒ 它是这个占位页的【全部内容】，改它必须同时改本用例的 SUBPAGE_LINE"
    )
