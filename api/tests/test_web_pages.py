"""全站页面脚本里 URL 字面量的守卫 —— **页面写死的 URL 必须带 `/api/v1`**。

起因是一个**真事故**（`DEC-093` §四）：`api/static/web/approvals.html` 把
`/agent/pending` 写死，而真实路由是 `/api/v1/agent/pending`
⇒ **那个页面在浏览器里 404，从合进去那天起就是坏的**，而**没有任何用例红**：

| 层 | 为什么漏 |
|---|---|
| `api/test_approvals_page.py`（3 条） | 只看 `GET /approvals` 的 **302 与跳转目标**，⛔ 不看页面脚本里的 URL |
| `api/static/js/approvals.test.js`（14 条） | 全是**纯函数** —— `buildContextQuery()` 只回 query string，前缀根本不经过它 |
| `scripts/check_route_auth.py` | 管的是「后端有没有多余的无鉴权路由」，与页面打什么 URL 无关 |

⇒ **URL 前缀硬编码在那一行 HTML 里，而那一行没有任何判据。**

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 🔴 为什么**扫目录**而不是逐个列页面名

「逐个列名」是本仓反复踩的形态：**新增一个页面/用例，忘了在门里加一行 ⇒
它永远不受管，而且没有任何东西会红**（同一形态：`.github/workflows/ci.yml` 的
`node --test` 逐行列文件名 = `N18`）。
⇒ 这里**扫 `api/static/` 下所有 `.html`**，页面一多**自动**进网（结构上的，
不是靠人记得加行）。

⚠️ **配套那条"至少发现 N 个页面"的用例是必需的**，⛔ 不是凑数 ——
   glob 写错时 `PAGES` 会是空列表，**参数化用例一条都不跑，而且是绿的**
   （本仓最恨的「空跑 = 静默假通过」；前科：`pre-commit-gates.py` 空跑）。

## ⚠️ 看代码会误判的地方

* **某个页面若改用 JS helper 拼路径，本用例对它是【空过】的。**
  `web/trace.html` 就是这种 —— 它不写字面量，走 `RagTrace.buildPath()` /
  `buildCostPath()`。那时前缀的保护来自**那个 helper 自己的 node 用例**
  （`api/static/js/trace.test.js` 的「`buildPath` / `buildCostPath` 会编码 thread_id」）。
  ⇒ ⛔ **别把"扫不到字面量"读成"这个页面验过了"**。
* 只查**调用点里的字面量**（`getJSON('…')` / `fetch('…')`），
  ⛔ **不做全文件子串扫描** —— 那会连注释一起命中（本仓 `N14` 的原话）。
* `api/static/` 根下的页面也在扫描面内。🔴 **2026-10-07（`DEC-096` · `F5`）起只剩
  `websocket_test.html` 一个** —— 原先那两个（`stream_test.html`：调**不存在**的
  `/api/v1/user/chat_history`；`trace_viewer.html`：`fetch` **不带认证头** ⇒ 必然 401）
  **已经删掉**。⇒ ⚠️ **本文件的用例数会跟着页数自动变**（当时 7 ⇒ 现在 5），
  **⛔ 别把"少了两条"读成"守卫变松了"** —— 少的是**两个不存在的页面**。

📌 判据（可打印）：`venv/bin/python -m pytest api/test_web_pages.py -q -p no:warnings`
"""
import os
import re

import pytest

from main import static_dir

# 必须含有的页面 —— 只有这些都发现得到，才说明"扫描真的在工作"。
# ⚠️ 加进这里 = "这个页面删了是件该被看见的事"，⛔ 不是随手 Grep。
_REQUIRED = ("web/approvals.html", "web/chat.html", "web/cost.html", "web/index.html", "web/lab.html", "web/trace.html")

# 调用点里的字符串字面量：单引号 / 双引号 / 反引号都收。
# ⚠️ 反引号收进来是有意的：`fetch(`/agent/${id}`)` **同样是坏的**，别放过。
_URL_LITERAL = re.compile(r"(?:getJSON|fetch)\(\s*['\"`]([^'\"`]*)['\"`]")


def _discover_pages():
    pages = []
    for root, _dirs, files in os.walk(static_dir):
        for name in files:
            if name.endswith(".html"):
                pages.append(os.path.relpath(os.path.join(root, name), static_dir))
    return sorted(pages)


PAGES = _discover_pages()


def test_page_scan_is_not_vacuous():
    """🔴 **扫描本身必须有货** —— 否则下面那条参数化用例一条都不跑，而且是绿的。

    ⚠️ 这条**故意写死三个页面名**：删页面是件该被看见的事
       （要么改这条，要么说明为什么那个页面没了），⛔ 不是"顺手 Grep 一下"。
    """
    assert PAGES, (
        f"在 {static_dir} 下一个 `.html` 都没扫到 ⇒ 下面的参数化用例【空跑】。"
        f"先查 `os.walk` 的起点与后缀对不对。"
    )
    missing = [p for p in _REQUIRED if p not in PAGES]
    assert not missing, (
        f"这些页面没被扫到：{missing}（实扫到 {len(PAGES)} 个：{PAGES}）。"
        f"⇒ 要么它们被改名/删了，要么扫描规则漏了它们。"
    )


@pytest.mark.parametrize("page", PAGES, ids=PAGES)
def test_page_url_literals_carry_the_api_prefix(page):
    """页面脚本里**写死的 URL 字面量必须带 `/api/v1`**（`DEC-093` §四）。

    反证检验：把 `web/approvals.html` 里的 `/api/v1/agent/pending` 改回
    `/agent/pending` ⇒ 本条立刻红（**这条是实测过的**，见 `DEC-093` §五）。
    """
    with open(os.path.join(static_dir, page), encoding="utf-8") as f:
        text = f.read()

    found = _URL_LITERAL.findall(text)
    bad = [
        u for u in found
        # 绝对地址（外部 CDN 之类）不归这条门管；相对路径必须落在 /api/v1 下。
        if not u.startswith(("/api/v1", "http://", "https://"))
    ]
    assert not bad, (
        f"`{page}` 里这些 URL 字面量没带 `/api/v1` 前缀，浏览器里会 404：{bad}\n"
        f"（真实路由前缀是 `/api/v1` —— 见 `api/api_v1_agent.py` 的 `APIRouter(prefix=…)`。"
        f"⚠️ **服务端不会报任何错**，页面只是空白/失效。）"
    )
