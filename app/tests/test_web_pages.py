"""全站页面脚本里 URL 字面量的守卫 —— **页面写死的 URL 必须带 `/api/v1`**。

起因是一个**真事故**（`DEC-093` §四）：`app/static/web/approvals.html` 把
`/agent/pending` 写死，而真实路由是 `/api/v1/agent/pending`
⇒ **那个页面在浏览器里 404，从合进去那天起就是坏的**，而**没有任何用例红**：

| 层 | 为什么漏 |
|---|---|
| `app/tests/test_approvals_page.py`（3 条） | 只看 `GET /approvals` 的 **302 与跳转目标**，⛔ 不看页面脚本里的 URL |
| `app/static/js/approvals.test.js`（14 条） | 全是**纯函数** —— `buildContextQuery()` 只回 query string，前缀根本不经过它 |
| `scripts/check_route_auth.py` | 管的是「后端有没有多余的无鉴权路由」，与页面打什么 URL 无关 |

⇒ **URL 前缀硬编码在那一行 HTML 里，而那一行没有任何判据。**

⛔ 本文件**不连库**（裸 `TestClient(app)`）—— 见 `DEC-058`：
   ⚠️ 别写成 `with TestClient(app) as client:`，那会触发 lifespan 的 startup
   （`init_pool()` 真去连 Postgres）⇒ **CI 没有库 ⇒ 直接红**。

## 🔴 为什么**扫目录**而不是逐个列页面名

「逐个列名」是本仓反复踩的形态：**新增一个页面/用例，忘了在门里加一行 ⇒
它永远不受管，而且没有任何东西会红**（同一形态：`.github/workflows/ci.yml` 的
`node --test` 逐行列文件名 = `N18`）。
⇒ 这里**扫 `app/static/` 下所有 `.html`**，页面一多**自动**进网（结构上的，
不是靠人记得加行）。

⚠️ **配套那条"至少发现 N 个页面"的用例是必需的**，⛔ 不是凑数 ——
   glob 写错时 `PAGES` 会是空列表，**参数化用例一条都不跑，而且是绿的**
   （本仓最恨的「空跑 = 静默假通过」；前科：`pre-commit-gates.py` 空跑）。

## ⚠️ 看代码会误判的地方

* **某个页面若改用 JS helper 拼路径，本用例对它是【空过】的。**
  `web/trace.html` 就是这种 —— 它不写字面量，走 `RagTrace.buildPath()` /
  `buildCostPath()`。那时前缀的保护来自**那个 helper 自己的 node 用例**
  （`app/static/js/trace.test.js` 的「`buildPath` / `buildCostPath` 会编码 thread_id」）。
  ⇒ ⛔ **别把"扫不到字面量"读成"这个页面验过了"**。
* 只查**调用点里的字面量**（`getJSON('…')` / `fetch('…')`），
  ⛔ **不做全文件子串扫描** —— 那会连注释一起命中（本仓 `N14` 的原话）。
* `app/static/` 根下的页面也在扫描面内。🔴 **2026-10-07（`DEC-096` · `F5`）起只剩
  `websocket_test.html` 一个** —— 原先那两个（`stream_test.html`：调**不存在**的
  `/api/v1/user/chat_history`；`trace_viewer.html`：`fetch` **不带认证头** ⇒ 必然 401）
  **已经删掉**。⇒ ⚠️ **本文件的用例数会跟着页数自动变**（当时 7 ⇒ 现在 5），
  **⛔ 别把"少了两条"读成"守卫变松了"** —— 少的是**两个不存在的页面**。

📌 判据（可打印）：`venv/bin/python -m pytest app/tests/test_web_pages.py -q -p no:warnings`
"""
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser

import pytest

from main import static_dir

# 必须含有的页面 —— 只有这些都发现得到，才说明"扫描真的在工作"。
# ⚠️ 加进这里 = "这个页面删了是件该被看见的事"，⛔ 不是随手 Grep。
_REQUIRED = ("web/approvals.html", "web/chat.html", "web/cost.html", "web/index.html", "web/lab.html", "web/ops.html", "web/system.html", "web/tools.html", "web/trace.html")

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
        f"（真实路由前缀是 `/api/v1` —— 见 `app/routing/api_v1_agent.py` 的 `APIRouter(prefix=…)`。"
        f"⚠️ **服务端不会报任何错**，页面只是空白/失效。）"
    )


# ══════════════ 页面**内联**的 JS 必须真能跑（2026-10-10 立 · 补一个结构缺口）══════════════
#
# 🔴🔴 **这道门是拿一个真事故换来的**，事故长这样：
#   8 个能力页**全部是死的**（一行内联脚本都不执行），而
#   **982 条 pytest + 283 条 node 用例全绿**。
#
# 为什么一条都没红：
#
# | 层 | 为什么够不到 |
# |---|---|
# | `app/tests/test_*_page.py`（各页守卫） | 它们读的是**页面文本**（正则找标记、比先后）—— **不解析 JS** |
# | `app/static/js/*.test.js`（node 用例） | 只测 **`js/*.js` 自己**，⛔ 从不加载页面里那段内联脚本 |
# | 静态检查（ruff 棘轮） | 只管 `.py` |
#
# ⇒ **页面里那段内联 JS 没有任何判据** —— 它写错了，全世界的门都是绿的，
#   只有**把页面真打开**才看得见。这正是本仓那句「**门挂在别处，就等于没有门**」。
#
# 具体那次错在**全局重名**：共用脚本 `session.js` 顶层写了 `function key()`，
# 而经典脚本的顶层 `function` **是全局的** ⇒ 与 8 个页面各自的 `const key` 撞上 ⇒
# `SyntaxError: Identifier 'key' has already been declared` ⇒ **整段内联脚本作废**。
#
# ⭐ 所以这道门钉的是**最外圈、也最便宜**的那一层：**它能解析吗**。
#   ⇒ ⛔ 它**不管**逻辑对不对（那是各页自己的用例 + `js/*.test.js` 的事）；
#      但"解析不了"这一类**从今夜起再也过不去了**。
#   📄 复盘：`docs/复盘/2026-10-10-页面里那段JS没有任何门会去跑它.md`

def _inline_scripts(text):
    """把页面里**内联**的 `<script>` 正文抽出来（带 `src=` 的是外部文件，⛔ 不算）。

    🔴 **为什么用 `html.parser` 而不是正则**（2026-10-11 · **CodeQL 连着抓了两次**）：

    | 第几次 | 正则漏了什么 | 后果 |
    |---|---|---|
    | 1 | **大写** `<SCRIPT>` | 那一页**扫不到** ⇒ **静默跳过** |
    | 2 | `</script >`（**带空格**） | 同上（或把两段脚本**吞成一段**） |

    ⚠️ **两次都是同一个毛病**：**漏扫 ≠ 通过** —— 正则没覆盖到某种写法，
    那个页面就被**静默跳过**，**而门照样绿**。这正是这道门存在的理由，也是它最不能犯的错。
    🔴 而且第 2 次我**事先把那条限制写在注释里当成了"有意不收"**，理由是"本仓页面一处都没有这种写法"
    —— **那正是本仓明令不许的那种推理**（拿「本仓现在没有」当「不会发生」）。
    ⇒ 换成 stdlib 的**真解析器**：**"某种写法没覆盖到"这一类洞，一次都没有了**。

    ⚠️ 换之前做过的核对：拿它和旧正则跑过 `app/static/` 下**全部 12 个 `.html`**
    ⇒ **逐页逐段完全一致**（含 `eval.html` / `eval_gate.html` 那两个"一段都没有"的）。
    ⇒ 所以这是一次**行为不变、鲁棒性变强**的替换。
    """
    p = _InlineScripts()
    p.feed(text)
    return ["".join(b) for b in p.blocks]


class _InlineScripts(HTMLParser):
    """收集**内联** `<script>` 的正文。⚠️ 带 `src=` 的⛔ 不算（那是外部文件，另有门管）。

    ⚠️ `handle_comment` 那道补丁不是多余的：老式脚本里 `<!--` 是**脚本内容**，
    而 `html.parser` 可能把它当注释 ⇒ 不补回去就会**少一段**（而⛔ 门照样绿）。
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        if any((k or "").lower() == "src" for k, _v in attrs):
            return                       # 外部文件 ⇒ ⛔ 不归这道门管
        self._depth += 1
        self.blocks.append([])

    def handle_data(self, data):
        if self._depth and self.blocks:
            self.blocks[-1].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._depth:
            self._depth -= 1

    def handle_comment(self, data):
        if self._depth and self.blocks:
            self.blocks[-1].append("<!--" + data + "-->")


def test_inline_script_scan_never_silently_skips_a_page():
    """⚠️ **下面那道门的【正控】** —— 认不出某种写法 = 那个页面被**静默跳过**（而门照样绿）。

    🔴 **为什么单立一条**：这道门一开始是**正则**写的，而 **CodeQL 连着抓了它两次**
    （`Bad HTML filtering regexp` · HIGH）：

    | 第几次 | 漏了什么 | 后果 |
    |---|---|---|
    | 1 | **大写** `<SCRIPT>` | 那一页扫不到 ⇒ **静默跳过** |
    | 2 | `</script >`（**带空格**） | 同上（或把两段脚本**吞成一段**） |

    ⇒ 两次都是"**漏扫 ≠ 通过**"，而这正是本仓最恨的形态（「空跑 = 静默假通过」）。
    ⇒ 现在换成了 stdlib 的**真解析器**（`html.parser`），这一类洞**一次都没有了**；
      本条就是钉住它的**正控** —— 下面每一种写法都**必须**被认出来。
    ⚠️ **反证**：把 `_inline_scripts` 换回「只认小写、不认标签里空格」的老正则 ⇒ 本条立刻红。
    """
    for src, why in [
        ("<script>var a=1;</script>", "最普通那种"),
        ("<SCRIPT>var a=1;</SCRIPT>", "🔴 大写 ⇒ 第 1 次 CodeQL 报的就是它"),
        ("<script >var a=1;</script >", "🔴 标签里带空格 ⇒ 第 2 次报的就是它"),
        ('<script type="text/javascript">var a=1;</script>', "带别的属性"),
        ("<script>\nvar a=1;\n</script>", "跨行"),
        ("<script>var a=1;</script><script>var b=2;</script>", "两段脚本（⛔ 不许吞成一段）"),
    ]:
        got = [s.strip() for s in _inline_scripts(src)]
        want = ["var a=1;"] if "b=2" not in src else ["var a=1;", "var b=2;"]
        assert got == want, f"认不出「{why}」⇒ 那个页面会被静默跳过（拿到的是 {got}）"

    for src, why in [
        ('<script src="/x.js"></script>', "带 `src=` 的是外部文件"),
        ('<SCRIPT SRC="/x.js"></SCRIPT>', "同上，大写"),
    ]:
        assert _inline_scripts(src) == [], f"{why} ⇒ ⛔ 别把它算成内联脚本（那是别的门管的事）"


@pytest.mark.parametrize("page", PAGES, ids=PAGES)
def test_inline_page_script_parses(page):
    """🔴 **页面内联的 JS 必须能被解析** —— 解析不了 ⇒ 那一整段一行都不执行，页面就是死的。

    判据用的是 **`node --check`**（真解析器），⛔ 不是"用正则数括号"那种自造的近似物。
    ⚠️ 反证检验：在任一页面的内联脚本里加一句 `const key = 1;`（与全局 `key` 撞名）
    或写一个语法错 ⇒ 本条立刻红。
    """
    with open(os.path.join(static_dir, page), encoding="utf-8") as f:
        blocks = _inline_scripts(f.read())
    if not blocks:
        pytest.skip(f"{page} 本来就没有内联脚本 —— ⛔ 这不是「这条门放过了它」")

    node = shutil.which("node")
    assert node, (
        "找不到 `node` ⇒ **这道门根本没法跑**。\n"
        "⚠️ ⛔ 别把它当通过 —— 这正是本仓「**取不到真值 ≠ 通过**」那条"
        "（同型：`check_remote_sync.sh` 的退出码 3）。\n"
        "⇒ 本仓的离线测试 job 本来就跑 `node --test`（`ci.yml`），所以 node 是**前置条件**。"
    )

    bad = []
    for i, src in enumerate(blocks):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
            tf.write(src)
            tmp = tf.name
        try:
            r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                bad.append(f"第 {i + 1} 段：{r.stderr.strip().splitlines()[0] if r.stderr else r.stdout}")
        finally:
            os.unlink(tmp)
    assert not bad, (
        f"`{page}` 里有内联脚本**解析不过** ⇒ 浏览器里那一整段**一行都不执行**，页面是死的：\n"
        + "\n".join(bad)
        + "\n⇒ 最常见的一种是**全局重名**：共用脚本的顶层 `function`/`const` 是**全局的**，"
          "会与页面自己的顶层绑定撞上（2026-10-10 就是这么栽的）。"
    )

