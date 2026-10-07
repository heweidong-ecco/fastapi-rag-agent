# DEC-094 · `DEC-093` 两条待裁的收尾：**`approvals.html` 的前缀**与 **`ci.yml` 的 `node --test`**

| 项 | 内容 |
|---|---|
| **状态** | 🟢 **已实现**（2026-10-06）—— 两条都是**业务方当场裁定**的（§一） |
| **触发** | `DEC-093` §六·**待裁 2 / 待裁 3**（以及同日新登记的 `N15` / `N18`） |
| **形状** | 🔧 修**另一个功能**的页面（`F1` 的 `approvals.html`）· 🔧 改 **CI 配置** · 🆕 把一类守卫**从"盯一个页面"改成"盯全站"** |
| **落点** | `api/static/web/approvals.html` · `.github/workflows/ci.yml` · **新增** `api/test_web_pages.py` · `api/test_trace_page.py`（**移走**一条）· `docs/specs/` 三份 · `docs/待办总表.md` · `ROADMAP.md` · `CHANGELOG.md` |
| **判据** | §五 —— 全部**可打印**（**已填实测数**） |

> 📌 **为什么单独开一份，而不是补进 `DEC-093`**：`DEC-093` 是**Trace 页**那一刀的依据；
> 这里两件事是**另一个功能的页面**与**仓库的 CI 配置**。⛔ 混进 `DEC-093` 会让
> 「`DEC-093` 到底管什么」变模糊 —— 而本仓已经吃过一次同形态的亏（`DEC-093` §刀次勘误）。

---

## 一 · 业务方裁定（三条 · 2026-10-06）

| # | 事项 | 裁定 | 备选 / 代价 |
|---|---|---|---|
| **1** | **`F2` 这一刀现在开 PR 吗**（当天已开 **8** 个，`#102`–`#109`，频率门阈值是 3） | **⛔ 先不开，等业务方发话** | 备选是「现在就开」（第 9 个）／「明天开」。⚠️ **代价**：分支上的活**只到远端分支、没进主干** ⇒ 未被任何人评审过 |
| **2** | **`approvals.html` 那 4 条 URL 前缀要不要现在修**（`N15`：页面 **100% 不可用**） | ✅ **现在修，并进 `F2` 这个 PR** | 备选：① 单独开一个小 PR（干净，但当天第 9 个 PR，且它**算不上"一个完整任务"**）② 只登记不动（页面继续不可用）。<br>🔴 **选的这条与 `DEC-051` 先例有张力** —— 先例只允许"同 PR 顺手修**同一功能**的邻近缺陷"，而这是**另一个功能的界面**。**⚠️ 这是业务方明确拍下的例外，⛔ 别把它读成"先例作废"**（先例仍是默认，例外要有人拍板） |
| **3** | **`ci.yml` 的 `node --test` 要不要从"逐行列名"改成 glob**（`N18`） | ✅ **改** | 备选：维持逐名列 + 登记为债（代价见 §三·B：**新增 `.test.js` 忘了加行 = 那份用例永不跑**）。 |

---

## 二 · 修的是什么（`N15` · 4 行字符串）

`api/static/web/approvals.html` 的 4 条 fetch **全少 `/api/v1`**：

```text
改前（当时行号）                                        改后
:109   /agent/pending                        → /api/v1/agent/pending
:145   /agent/pending/context?               → /api/v1/agent/pending/context?
:181   /agent/approve?                       → /api/v1/agent/approve?
:199   /agent/approvals/history?limit=50     → /api/v1/agent/approvals/history?limit=50
```

> ⚠️ **⛔ 别抄上面那组行号** —— **这次修复本身就把它们整体下移了 5 行**（在 `'use strict'` 下面
> 加了一段"本页每个 URL 都必须带前缀"的告示）。**判据用命令**：
> `grep -n "getJSON('/\|fetch('/" api/static/web/approvals.html` ⇒ **4 条，全部带 `/api/v1`**。

**四条【路径】本身都是对的**（不是路由写错，只是前缀）—— 改前改后实测：

```text
改前        改后
404   /agent/pending                  /api/v1/agent/pending                   401  ← 路由在，要鉴权
404   /agent/pending/context?…        /api/v1/agent/pending/context?…         401
404   /agent/approve?…                /api/v1/agent/approve?…                 405  ← POST-only ⇒ 405 也是"路由在"
404   /agent/approvals/history?…      /api/v1/agent/approvals/history?…       401
```

### ⛔ 为什么**不**顺手把 `approvals.html` 改成"helper 拼路径"

`web/trace.html` 走的是另一条路 —— 它**不写字面量**，路径由 `RagTrace.buildPath()` /
`buildCostPath()` 出，那两个函数在 `trace.test.js` 里有 node 用例钉住。

**没跟着改的两个理由**：

1. **`DEC-094`（本份）的裁定是"修那 4 条字符串"**，⛔ 不是"重做那个页面的取数层"；
   重构 `approvals.js` 要动 14 条已绿的 node 用例，是**另一个功能的内部结构**。
2. **守卫改成扫全站之后，改不改 helper 都不影响防线** —— 只要页面上还留着字面量，
   `api/test_web_pages.py` 就会盯住它（§三·A）。

⇒ ⚠️ **代价（知道再选）**：前缀在 `approvals.html` 里**重复了 4 遍**。这不是靠自觉兜的，
靠的是那条扫全站的守卫 —— **"只有文字就漏，结构才执行"**。

---

## 三 · 两处技术决策（⛔ 不是改裁定，是把它落到实处）

### A · 守卫**搬家**：从"盯一个页面"改成"盯全站"

原守卫 `test_page_url_literals_carry_the_api_prefix` 长在 `api/test_trace_page.py` 里，
**只读 `web/trace.html` 一个文件**。而它的**起因**恰恰是 `approvals.html` 那个事故 ——
**"只盯一个页面的门，挡不住下一个页面"，这正是它当初没拦住的原因。**

⇒ 搬进**新增的** `api/test_web_pages.py`，**扫 `api/static/` 下所有 `.html`**：

| | 改前 | 改后 |
|---|---|---|
| 谁被扫 | `web/trace.html`（**写死的一个**） | `api/static/**/*.html`（**实扫到 6 个**：`web/` 三个 + `stream_test.html` · `trace_viewer.html` · `websocket_test.html`） |
| 新页面 | **自动漏掉**（要人记得改那一行） | **自动进网** |
| 引号 | 只认单引号 | 单引号 / 双引号 / **反引号**（`` fetch(`/agent/${id}`) `` 同样是坏的） |

⚠️ **看代码会误判的地方**：某个页面若改用 JS helper 拼路径（`trace.html` 就是），
这条守卫对它是**空过**的 —— 那时前缀的保护来自**那个 helper 自己的 node 用例**。
⛔ **别把"扫不到字面量"读成"这个页面验过了"。**

### B · glob 的反证：**换了 glob 反而会多出一种静默失败**

业务方裁「改成 glob」的字面做法是换一行：

```yaml
node --test api/static/js/*.test.js      # ⛔ 单这一行是【退步】
```

**反证实验照出来的**（本机 node **v26.8.1** 实测）：

| 写法 | 一个都匹配不上时 | 结论 |
|---|---|---|
| 逐行列名（原状） | `Could not find '…'` ⇒ **退出码 1** | **响亮** |
| 裸 glob | `ℹ tests 0` ⇒ **退出码 0** | 🔴 **静默假通过** |

⇒ **只换一行 = 拿一种静默失败换另一种**（"新增用例忘加行" → "目录挪了全场停跑"）。
**所以必须连同防空跑一起写**：

```yaml
test_files=(api/static/js/*.test.js)
if [ ! -e "${test_files[0]}" ]; then
  echo "🔴 一个 .test.js 都没匹配到：api/static/js/*.test.js"; exit 1
fi
node --test "${test_files[@]}"
```

⚠️ 同理，`test_web_pages.py` 里配了一条 `test_page_scan_is_not_vacuous()` ——
**glob 写错时参数化用例一条都不跑，而且是绿的**（与上面是**同一个形态**）。

📌 **两条一起看**：本仓反复踩的「**空跑 = 静默假通过**」（前科：`pre-commit-gates.py` 空跑）。

---

## 四 · 与既有记账的关系

* `N15`（`approvals.html` 前缀）⇒ ✅ **结清**
* `N18`（`ci.yml` 逐名列名）⇒ ✅ **结清**
* ⚠️ **结清的是这两条**，⛔ **不是** `DEC-093` 那四条债里的其他几条：
  `N16`（其余 Agent 链不建轨迹）· `N17`（追踪轴在进程内存）**原样挂着**。

---

## 五 · 判据（全部可打印，**已填实测数**）

```bash
venv/bin/python -m pytest api/test_web_pages.py -q -p no:warnings              # ⇒ 7 passed（1 条防空跑 + 6 个页面）
venv/bin/python -m pytest api/test_trace_page.py api/test_web_pages.py api/test_approvals_page.py -q -p no:warnings
                                                                               # ⇒ 16 passed
grep -n "getJSON('/\|fetch('/" api/static/web/approvals.html                   # ⇒ 4 条，【全部】带 /api/v1
bash scripts/ci-local.sh                                                       # ⇒ exit 0（含 node --test 70 passed）
```

`node --test` 一条 glob ⇒ **70 passed**（= `sse` 32 + `approvals` 14 + `trace` 24 的**实测和**，
⛔ 不是把三个数加起来就算）。

### ⚠️ 反证检验（逐条做过，⛔ 不是"跑了就算"）

| 变异 | 应当红的 | 实测 |
|---|---|---|
| 把 `approvals.html` 的 `/api/v1` 前缀去掉**一条** | `test_web_pages.py` 参数化那 6 条里的 `web/approvals.html` | ✅ 红，且**点名那条 URL** |
| 把 ci.yml 的模式改成 `*.nope.js` | 防空跑那两行 | ✅ **exit 1**（对照：裸 glob 是 **tests 0 / exit 0**） |
| 把 `test_page_scan_is_not_vacuous` 里的 `_REQUIRED` 去掉 | ——（该条**故意写死三个页面名**，删页面是件该被看见的事） | ✅ 少一个页面名 ⇒ 红 |

> ⭐ 中间那行正是 2026-10-05 那条纪律的落地：**先问「把结论取反，这条命令的输出会变吗」** ——
> 变不了 ⇒ 那条判据根本没在测那件事。

---

## 六 · 遗留（⛔ 本批**不做**的事）

1. **`approvals.html` 仍没有"页面真能跑"的端到端判据** —— 本批给的是**静态**守卫
   （源码里的字面量）。真正"点得动"要靠**人拿浏览器开一次**。
   ⚠️ 本批**没做**这次目视（服务没起）。⇒ **登记为债**。
2. **`DEC-051` 先例的边界** —— 本批是业务方拍下的**例外**（跨功能顺手修）。
   ⛔ **先例仍是默认**；下次要再跨功能，**得再拍一次**，⛔ 不许把本份当先例引用。
3. **其余 `DEC-093` 的债**（`N16` / `N17`）**原样挂着**。
