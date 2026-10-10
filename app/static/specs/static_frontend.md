# `app/static/` —— 前端（**本仓第一个没有 `.py` 模块的子系统**）

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用**（2026-10-06 建 · `DEC-085` 段 1 第一刀 · 同日补 `DEC-089` 的 `F8` · `DEC-090` 的熔断卡片 · `DEC-091` 的无据拒答 · `DEC-093` 的 Trace 页 · 2026-10-07 补 `DEC-097` 的 Eval 页）—— **四个页面通了**：对话页（`DEC-085` · 引用卡片 `DEC-089` · **熔断卡片 `DEC-090`** · **无据拒答 `DEC-091`**）+ **接管页**（`DEC-088` · `F1`）+ **Trace 页**（`DEC-093` · `F2`）+ **Eval 页**（`DEC-097` · `F3`，🔴 **是【占位页】不是功能页** —— 见下） |
| 🔴 **找前端的东西** | ⭐ **`frontend/索引.md`** —— **唯一查找入口**（业务方 2026-10-09 立的：「**不要用 grep 去找，也不准**」） |
| **对外提供** | `GET /chat` → **302** `/static/web/chat.html`（`app/main.py:564`，**`include_in_schema=False`**）<br>`GET /approvals` → **302** `/static/web/approvals.html`（`app/main.py:573`，**同上**）<br>`GET /trace` → **302** `/static/web/trace.html`（`app/main.py:585`，**同上**）<br>`GET /eval` → **302** `/static/web/eval.html`（`app/main.py:598`，**同上**）<br>`GET /lab` → **302** `/static/web/lab.html`（`app/main.py:611`，**同上** —— 2026-10-09 刀 3 · `DEC-123`）<br>`GET /cost` → **302** `/static/web/cost.html`（`app/main.py:623`，**同上** —— 2026-10-09 刀 4 · `DEC-124`）<br>🆕 `GET /tools` → **302** `/static/web/tools.html`（`app/main.py:637`，**同上** —— 2026-10-10 刀 5 · `DEC-139`）<br>🆕 `GET /system` → **302** `/static/web/system.html`（`app/main.py:653`，**同上** —— 2026-10-10 刀 6 · `DEC-140`）<br>· 页面本体由已挂的 `/static` 托管（零构建、零新服务、零 CORS）<br>⚠️ **八条 302 都在无鉴权基线里**（`scripts/route-auth-baseline.txt`）—— **故意公开**：它们是"给人打开 HTML"的跳转，**本身不含数据**；真正的边界在页面调的后端接口上（⚠️ **`/eval` 例外**：它连后端接口都不调，见下）<br>⚠️ **上面那八个行号是 2026-10-10 现算的**（`grep -n '@app.get("/…"' app/main.py`）—— 此前那五个写着 `548/557/569/582/595/607`，**都已经过期**（它们在 `/tools` 之前就已经被别的提交下移过）。⛔ 读的人**跑一遍那条 grep**，别当永久值 |
| **谁在用** | 人（浏览器）。⚠️ **后端不 import 它、没有任何 `.py` 依赖它** —— 这就是本目录此前一直是"没人管"的原因 |

**四个页面、各 3 个文件**（Eval 那组例外，见下；其余老页面见 §🟡）：

| 文件 | 行数 | 是什么 |
|---|---:|---|
| `app/static/web/chat.html` | 501 | 对话页：装配层（DOM / fetch / 状态机 / 渲染 / **引用卡片** / **熔断卡片** / **无据提示条**） |
| `app/static/js/sse.js` | 261 | **纯逻辑**：帧解析 / 引用映射 / 出口判定 / 费用格式 / **卡片头与「再点」** / **熔断卡片四件事** / **无据提示文案** —— ⛔ 不碰 DOM、不发请求 |
| `app/static/js/sse.test.js` | 372 | `node --test` 用例（**32 条**）—— 钉住 `sse.js`<br>⚠️ **数量别抄文档** —— 跑 `node --test app/static/js/sse.test.js`（Task 1–8 从 11 到 18；`DEC-089` 的 `F8` 到 **23**；`DEC-090` 的熔断卡片到 **29**；`DEC-091` 的无据拒答到 **32**） |
| `app/static/web/approvals.html` | 252 | **接管页**：待接管表 / 点开看完整上下文 / 批准·拒绝·代填工具结果 / 裁决历史<br>🔴 **2026-10-06（`DEC-094`）修了 4 条 URL 的前缀** —— 原先全少 `/api/v1` ⇒ **本页从上线起 100% 打不开**（+5 行：`'use strict'` 下面那段"本页每个 URL 都必须带前缀"的告示） |
| `app/static/js/approvals.js` | 86 | **纯逻辑**：消息归一 / 工具摘要 / 计时文案 / 轮询节拍 / 两个载荷构造 |
| `app/static/js/approvals.test.js` | 120 | `node --test` 用例（**14 条**）—— 钉住 `approvals.js`（同上：⛔ 数量别抄） |
| 🆕 `app/static/web/trace.html` | 336 | **Trace 页**：装配层（两轴分屏 / 取数 / 渲染 / 空态解释 / 页脚合计） |
| 🆕 `app/static/js/trace.js` | 198 | **纯逻辑**：两轴的摘要与格式化 / 时间戳解析 / 空态判定 / 路径拼接 —— ⛔ 不碰 DOM、不发请求 |
| 🆕 `app/static/js/trace.test.js` | 272 | `node --test` 用例（**24 条**）—— 钉住 `trace.js`（同上：⛔ 数量别抄） |
| 🆕 `app/static/web/eval.html` | 37 | **Eval 页**（`DEC-097` · `F3`）—— 🔴 **占位页**：一个标题 + 一句实话 + **一个做成按钮的 `<a>`**，指向下面的子页。⛔ **页面上没有任何分数 / 对比箭头**（原 `F3` 那个写法**没有数据源**，硬做只能做出假页面） |
| 🆕 `app/static/web/eval_gate.html` | 22 | **Eval 页的子网页** —— 🔴 **正文只有一行**：`agent-eval-gate · Agent 生产就绪评测门 · TODO`。<br>⚠️ 这一页**不 fetch 任何接口**（后端至今没有 `/agent/eval*` 路由，`B14` 仍是 ⬜）⇒ 它是**静态文字**，也是它比另外三页更没有暴露面的原因<br>⛔ 别"顺手"给它加返回链接 / 卡片 / 表格 —— 加了就不是业务方要的那一行了 |
| 🆕 `app/tests/test_eval_page.py` | 116 | **Eval 页守卫**（Python · 不连库）—— 3 条与另三页同构（302 / 目标在盘上 / 不在 openapi）+ **2 条页面本体的**：`<a href>` 真的指向子页、子页在盘上**且带那一行**（🔴 拿 `SUBPAGE_LINE` 常量钉，改文案会红） |
| 🆕 `app/static/js/panel.js` | 116 | **能力面板的纯逻辑**（2026-10-09 · 施工单**刀 0**）—— 边界标注文案（规格 §3.6.2 那 5 条 · **唯一一份**）· `paramQuery` · `stateOf` 四态 · `emptyReason` · `truncationNotice`（`has_more` 与 `truncated` **两形状不合并**）· `errorText`（401/403 · 429 · 503 **三句话**）。<br>⚠️ 🔴 **第一版真栽过一条**：`stateOf` 只认 `'error' in payload` ⇒ **`{"status":"error"}` 被判成 `ok`**，而那正是本仓四类拒绝的**真实形状**（200 + `status:"error"`）⇒ 已改成两种形状都认 |
| 🆕 `app/static/web/lab.html` | 435 | **检索实验室**（2026-10-09 · 施工单**刀 3**）—— 规格 §2.2 那 **5 条检索接口**的**唯一可点入口**：`pg` / `hybrid` / `rerank` / `rewrite` / `pipeline` 五个面板，一条一跑。🔴 **每个面板顶部先给边界提示条、再给"运行"按钮**（`DEC-123` §1.1） |
| 🆕 `app/static/js/lab.js` | 191 | **检索实验室的纯逻辑** —— 五个面板的路径/分数字段名（`similarity` / `rrf_score` / `rerank_score` **三条链各不相同**）· `buildRequest`（⚠️ `thread_id` **只有 rewrite 与 pipeline 带**）· 结果归一（**缺分数给 `null`，⛔ 不编 0**）· `envLimitHint`（**只有 rerank + 5xx** 才说是环境限制）—— ⛔ 不碰 DOM、不发请求 |
| 🆕 `app/static/js/lab.test.js` | 203 | `node --test` 用例（**20 条**）—— 🔴 **本文件同时是那 5 个 `/api/v1` 前缀的守卫**（页面走 helper ⇒ `test_web_pages.py` 对它**空过**）· + 假 `window` 跑一遍 |
| 🆕 `app/static/web/cost.html` | 443 | **成本看板**（2026-10-09 · 施工单**刀 4**）—— 规格 §2.5(9) + §2.6(3) − **有意不露(2)** = **10 个面板**。🔴 每格标题带**口径徽标**（读库 / 进程内存 / 配置常量）—— 见下「看代码会误判」那条 |
| 🆕 `app/static/js/cost.js` | 306 | **成本看板的纯逻辑** —— 九条路径 · 三态口径（`SOURCE_LABELS`）· `NOT_EXPOSED`（三条不露 + 理由）·`buildRequest` · `kvRows`/`tableOf`/`table2Of` · `memoryWarning` · 格式化（🔴 `fmtMoney(null)` 曾回 `0.0000` ⇒ 已挡） |
| 🆕 `app/static/js/cost.test.js` | 226 | `node --test` 用例（**25 条**）—— 含「面板表与不露表不许重叠」「**缺值不许编 0**」+ 假 `window` |
| 🆕 `app/tests/test_cost_page.py` | 196 | **成本看板守卫**（Python · 不连库）—— 4 条同构 + **4 条本页特有的**：九个面板 · **口径徽标** · **三条不露不许被请求** · 提示条在按钮之前 |
| 🆕 `app/tests/test_lab_page.py` | 149 | **检索实验室守卫**（Python · 不连库）—— 4 条与另几页同构（302 / 目标在盘上 / 不进 openapi / **两个脚本都引了**）+ 2 条页面本体的（**五个面板都在** · 🔴 **边界提示条排在提交按钮【之前】**） |
| 🆕 `app/static/js/panel.test.js` | 156 | `node --test` 用例（**13 条**）—— 除功能断言外有一条**结构型守卫**：**边界文案只许在 `panel.js` 里出现一次**（数的是【文件】，⛔ 不是"我记得没抄第二份"）+ **假 window** 跑一遍（⛔ 少挂 `window.RagPanel` 页面就 ReferenceError） |
| 🆕 `app/tests/test_web_pages.py` | 112 | **全站页面守卫**（Python · 不连库）—— **扫 `app/static/` 下每个 `.html`**：`getJSON(…)`/`fetch(…)` 的字面量必须以 `/api/v1` 开头 + 1 条**防空跑**。<br>🔴 **2026-10-06（`DEC-094`）建的**：原先这条守卫只在 `app/tests/test_trace_page.py` 里、**只读 `trace.html`** ⇒ 下一个页面照样能坏<br>⚠️ **用例数 = 被扫的 `.html` 个数 + 1** —— 走过 7 → 5（`DEC-096` 删两个坏页）→ **7**（`DEC-097` 加两个 Eval 页）。**页面一少它自动跟着少**，⛔ 那不是守卫变松<br>⚠️ **它对 Eval 这两页【空过】**：那两页一个 `fetch` 都没有 ⇒ 没有字面量可查（见 §⚠️ 那条） |
| 🆕 `app/static/web/tools.html` | 485 | **工具与记忆**（2026-10-10 · 施工单**刀 5**）—— 规格 §2.7(5) + §2.8(`add`/`search`) = **7 格**，分两个区（`#tools` 5 格 · `#memory` 2 格）。🔴 每格标题带**口径徽标**（进程内存 / 代码常量 / 真调 MCP / 容器磁盘 / 常量+内存）—— 见下「看代码会误判」那几条 |
| 🆕 `app/static/js/tools.js` | 346 | **工具与记忆的纯逻辑** —— 七条路径 + **方法**（⚠️ 记忆那两条是 POST 但**参数在 query**）· 五态口径（`SOURCE_LABELS`/`SOURCE_BADGES`/`SOURCE_CLASSES`）· `missingRequired`（必填项空的**不发请求**）· `persistenceWarning`（`const` 那格**不挂**警示条 = 不狼来了）· `buildRequest` · `kvRows`/`tableOf`/`table2Of`/`table3Of` · `fmtEpoch`（🔴 **epoch 秒 ×1000**，忘了就显示 1970）—— ⛔ 不碰 DOM、不发请求 |
| 🆕 `app/static/js/tools.test.js` | 308 | `node --test` 用例（**34 条**）—— 🔴 **本文件同时是那七条 `/api/v1` 前缀的守卫**（页面走 helper ⇒ `test_web_pages.py` 对它**空过**）· 含「记忆接口的参数在 query，⛔ 不在 body」「`fmtNum(null)` 不许编 `0`」「七格的空态⛔ 不是同一句话」+ 假 `window` |
| 🆕 `app/tests/test_tools_page.py` | 192 | **工具与记忆页守卫**（Python · 不连库）—— 4 条与另几页同构 + **3 条本页特有的**：**七格都在** · **每格都有口径徽标**（`data-source` ∈ 五态）· **两个分区锚点 `#tools`/`#memory` 必须在**（⚠️ 首页那两张卡靠它落位，锚点没了**不报错**、只是落到页首）· 提示条在按钮之前 |
| 🆕 `app/static/web/system.html` | 454 | **系统与执行器**（2026-10-10 · 施工单**刀 6**）—— 规格 §2.9(1) + §2.13(3) = **4 格**，分两个区（`#executor` 1 格 · `#system` 3 格）。⭐ 它是「**批② 执行器进容器**」那件事的**唯一可见证据**。🔴 每格标题带**口径徽标**（当场真跑 / 进程内存）—— 见下「看代码会误判」那几条 |
| 🆕 `app/static/js/system.js` | 262 | **系统与执行器的纯逻辑** —— 四条路径（⚠️ **三条是根路径**）· 两态口径 · `isRaw`（`/metrics` 是 **text/plain** ⇒ ⛔ 不许 `JSON.parse`）· `rawPreview`（截断要报**总行数**）· `errorPayloadOf`（**503 那支是另一个形状**）· `buildRequest`（`execute_code` 的参数**在 query**）—— ⛔ 不碰 DOM、不发请求 |
| 🆕 `app/static/js/system.test.js` | 307 | `node --test` 用例（**29 条**）—— 🔴 **本文件同时是那四条路径的守卫**，而它**与 `tools.test.js` 那条长得不一样**：它钉的是「**三条根路径 + 一条带 `/api/v1`**」，⛔ **不能照抄「全部以 `/api/v1` 开头」**（照抄会把对的写成错的）。含「渲染文案⛔ 不许带 `**`」那条结构型守卫 |
| 🆕 `app/tests/test_system_page.py` | 227 | **系统与执行器页守卫**（Python · 不连库）—— 4 条与另几页同构 + **4 条本页特有的**：**四格都在** · **每格都有口径徽标** · 🔴 **`/health` `/ready` `/metrics` ⛔ 不许作为 `fetch` 字面量出现**（它们是**根路径**；写成字面量会被硬约束 #8 拦下，而**那条红会把人引向错误的修法**）· 🔴 **代码那格必须是 `<textarea>` 且 label 带 `code-field`**（见下「看代码会误判」那条 CSS 坑）· **两个分区锚点** · 提示条在按钮之前 |

## ✅ 做了什么

- **对话页一条线**：登录（粘 API Key，存 `localStorage`）→ 新会话（前端生成 `thread_id`）→
  提问 → **SSE 逐字渲染** → 引用可点开 → 费用行 → **停止按钮**。
- **纯逻辑与装配层切开**：能写成命令的那部分全在 `sse.js`，被 `node --test` 钉住
  （`DEC-085` 裁定 #9）。⇒ **本仓第一次有能自动跑的前端用例**，且**零 npm 依赖**
  （⛔ 没有 `package.json`，不引 Playwright —— 那是另一笔账）。
- **出口状态机**：`idle → 请求中 → 流式中 → 完成 / 已中断 / 出错 / 未收到结束标志`。
  四种出口**分开显示**，⛔ 不合并（`DEC-082` / `N9` 的口径）。
- **三种失败说三句话**（`explainStatus`）：`401` 让重新贴 key · **`503` 明说"不是你的 key 的问题"** ·
  `429` **走熔断卡片**（`DEC-090`）。⚠️ 合并它们会让人**换 key 换到怀疑人生**（而根因在服务端）。
- 🔵 **熔断提示卡片（`DEC-090` · `F4` 第三条 · 2026-10-06）** —— `R3.2` 要求卡片写清四件事
  （**现状 / 这不是故障 / 何时恢复 / 怎么联系**）：
  · 四件事的**文字**由纯函数 `RagSse.breakerCard(scope, message)` 给（`node --test` 钉住），
    挂 DOM 的 `showBreaker` 留在 `chat.html`。卡片是**另起一个 `.breaker` 元素** ——
    ⛔ 不与引用卡片的 `.card` 共用（后者由 `_openIndex` 驱动、每次重画都被清空，会互相抹掉）。
  · 🔴 **「何时恢复」必须分两种**：全站级（`B11`）只能等跨天；会话级（`B8`）
    **开个新会话立刻能继续**。而两者 `code` **都是 `QUOTA_EXCEEDED`** ⇒ 前端分不出来
    ⇒ 后端给对话页那条链的两处 429 补了 `scope`（`"global"` / `"session"`）。
    ⚠️ **只接了这一个端点**（全仓 35 处 `raise`，其余 33 处**有意不动**）⇒
    没有 `scope` 的 429，卡片把「何时恢复」画 `—`，⛔ **不猜一个口径**。
- 🔵 **无据拒答：后端给信号，前端画提示条（`DEC-091` · `F4` 第一条 · 2026-10-06）** ——
  硬门 B 判定的**第二半**（「再问一个库里没有的 ⇒ **明确拒答**」）。
  · 🔴 **补的是「可观测性」，⛔ 不是拒答率**。开工前业务方裁「先测现状」⇒ 真栈 spike 三轮实测：
    **8/8 都在拒**（含 3 类"话题相邻但事实不在库里"的硬例）。但它**只活在正文里** ——
    前端分不出、评测刷不出样本、日志没有这个数。⇒ 让"拒答了"变成**帧里的一个字段**。
  · 后端 `_complete()` 里：答案**以那句拒答语开头** ⇒ 多发一帧 `{"no_answer": true}`。
    帧序 `… [DONE] → no_answer → sources → usage`（放 `sources` **之前**：标志先到，那一趟重画才画得对）。
    ⚠️ 那句拒答语抽成模块常量 `REFUSAL_SENTENCE`，**prompt 与判据共用** —— 两处分家是**静默**的。
  · 前端：`payloadKind` 多认这一帧 + `RagSse.refusalNotice()` 给文案；`chat.html` 收到 ⇒
    `turn._refused` ⇒ **正文不切引用**（实测见过一条拒答后面挂着 3 个可点来源号，那是**自相矛盾**的呈现）
    + 画 `.noinfo` 提示条（中性灰，⛔ 不用熔断那个警示黄 —— **拒答不是故障**）。
  · 🔴 **判据只有后端那一份** —— 前端**只认帧**，⛔ 不许自己去读正文猜（有结构型用例盯着）。
  · ⛔ **相似度阈值那条路已被实测判死**：能答的最低 **0.794** / 该拒的最高 **0.766**（差 0.028），
    且 `净利润` 与 `营收` 打进的是**同一篇**文档 ⇒ **相似度量的是「问题↔文档」，量不了「事实∈文档」**。
    全文 ⇒ `DEC-091` §三。
- **硬门 B / C 的界面那条线**（手工验过，见 §判据）：引用可点开**全文** · 停止 ⇒
  网络层真取消 + 「已中断」徽标 + 「中断未计费」。
- 🔵 **引用卡片整条做完了（`DEC-089` · `F8` · 2026-10-06）** —— 硬门 B 判定是**三句**，
  本刀之前只做掉第一句，这一刀把后两句一起关掉：
  · **②「再点能跳到原文位置」** ⇒ 裁定走「**甲 · 就地展开/收起**」：
    卡片挂在该条回答**下面**（`addTurn` 里每条自带一个 `<div class="card" hidden>`），
    点引用展开、**再点同一条收起**、点另一条换内容。
    ⚠️ **为什么不做"真的跳原文"**：`documents` 表**只有** `id/content/source/embedding/requested_by`
    （`app/core/db.py:65-71`）—— **没有任何位置字段**，也没有"按 id 取全文"的端点 ⇒ **没有位置可跳**。
  · **③证真「chunk id + 相似度分」** ⇒ 卡片头由 `RagSse.formatSource` 拼出 `id=… · 相似度 …`。
    后端只动**两行**：`sources` 帧加 `"similarity"`（`app/routing/api_v1_rag.py` + `app/rag/answer_with_citations.py`，
    **两个出口都要加**）。🔴 那个数**本来就在手上**（`contexts` 里的 `r[3]`），只是没人往帧里放。
- 🔵 **接管页（`DEC-088` · `F1` · 2026-10-06）** —— **硬门 D 演示那一栏**（它的反例原文是
  「**界面上找不到**」，所以这一块**只能靠界面**，后端补不出它）：
  · **待接管表**（属主 / 图 / 轮次 / 卡了多久 / 待批的工具）→ **点一行**拉完整上下文 → **批准 / 拒绝**，
    可**代填这次工具调用的结论**（不填 = 原样放行）；下面一张**裁决历史**表。
  · **同样切开纯逻辑与装配层**：`approvals.js` 被 `node --test` 钉住（**14 条**），渲染 / 点击 / 轮询留在 HTML 里。
  · 🔴 **轮询只在页面可见时**（裁定 5）：`nextPollDelay(document.visibilityState)` ⇒ 不可见返回 `null`，
    调用方**不排下一次**。⚠️ 理由：接管页是**人工**工作台，没人看的时候还每 5s 打三条接口纯属白烧。
  · 🔴 **措辞不是"改答案"**（裁定 4）：界面上写的是「**代替模型执行这次工具调用**」——
    它的真实语义是把结论**当作工具结果**喂回去（见 `app/agent/specs/approval_audit.md` 那条 `edited`）。
  · 🔴 **接口的四类拒绝全是 HTTP 200 + `{"status":"error"}`** ⇒ 页面必须**读 body**，⛔ 只看 `r.ok` 会把
    "无权查看"当成成功（`explainStatus` 只管 401/429/5xx 那类**真错**的状态码）。
- 🔵 **Trace 页（`DEC-093` · `F2` · 2026-10-06）** —— 入口 `GET /trace` → `/static/web/trace.html?thread_id=…`
  （🔴 **它替代了 `app/static/trace_viewer.html`** —— 那个页面 fetch 轨迹**不带认证头** ⇒ 加了鉴权之后**打开必 401**。🗑️ **该旧页已于 2026-10-07 删除** · `DEC-096`）。
  · **两轴分屏**：上半页**追踪轴**（`/agent/trace/{id}` · 工具调用逐步耗时）·
    下半页**成本轴**（`/agent/trace/{id}/cost` · 逐笔 token / 花费）。
    🔴 **⛔ 两条轴不合并、不相加** —— 它们**没有共同的步 id**，合成一棵树只能靠"时间接近"猜（详见下「看代码会误判」）。
  · 🔴 **页面必须解释"为什么空"**（`RagTrace.emptyTraceReason` 三条分支）—— 对话页走的是检索链，
    **那条链根本不建轨迹** ⇒ 演示时上半页**必然**是空的。只印一句"未找到"会让人以为整个功能坏了。
> 🔴 **2026-10-09 更正（上面这句已不成立）**：`N16` **已于 2026-10-08 落地**（`DEC-093 §七`）—— `/rag/stream_search` **现在建轨迹**（判据：`grep -n 'start_trace' app/routing/api_v1_rag.py` ⇒ 有）。⇒ **现在的"空"是"这条线程还没跑过"，⛔ 不是"这条链不建轨迹"**。⚠️ **`N16` 仍挂着的是另一半**：**其余 Agent 链**仍不建轨迹。

  · 🔴 **时间戳两层设防**：后端一律回带 `+00:00` 的 ISO（`token_tracker._iso_utc`），
    前端 `parseWhen()` **主动拒绝**不带区的时间戳（画 `--`）—— 因为库里那列是**无时区**的 `TIMESTAMP`。
  · 删掉了旧页那两格**假概览卡**（「总 Token」/「总花费」在追踪轴上**恒为 0**，见下「看代码会误判」）。
  · 📌 守卫：`node --test app/static/js/trace.test.js`（**24 条**）· `app/tests/test_trace_page.py`（**7 条**）。
- 🔵 **Eval 页（`DEC-097` · `F3` · 2026-10-07）—— 🔴 是【占位页】，⛔ 不是功能页** —— 入口 `GET /eval`
  → `/static/web/eval.html`（**一个按钮**）→ 点开 `/static/web/eval_gate.html`（**一行字**）。
  · 🔴 **这一刀把 `F3` 的定义改了** —— 原 `F3` 写的是「**跑分 + 与上一版的对比箭头**（数据来自
    `agent-eval-gate`）」，而**后端至今没有任何 `/agent/eval*` 路由**（`B14` 仍是 ⬜）⇒
    按原文做**只能做出一个假页面**（数字从哪来？箭头跟谁比？）。业务方 2026-10-07 当场把它裁成占位页。
  · ⚠️ **代价已认**：它现在**是空的** —— 页面上明写「只有占位」，子页那一行以 `TODO` 结尾。
    ⛔ **这不等于 `F3` 那个功能做完了**，等于**换了个交付口径**（`DEC-097` §二 记了裁定原文）。
  · ⚠️ **它比另外三页【更没有暴露面】**：那三页各自调带鉴权的后端接口（边界在那几条接口上），
    这一页与子页**一个 `fetch` 都没有** ⇒ 公开面 = 两个静态 HTML。
- 🔵 **成本看板（施工单刀 4 · 2026-10-09 · `DEC-124`）** —— 入口 `GET /cost` → `/static/web/cost.html`。
  🔴 **本刀的正文其实是【可见性】不是"画表格"**：
  · ✅ **核了规格点名的那一条**：`/agent/budget/intercepts` 是**本人可见** ⇒ **露**（施工单的规则原文「本人可见 ⇒ 露」）。
  · 🔴 **同时查出同族另有三条不是本人口径** ⇒ **有意不露**（`RagCost.NOT_EXPOSED`）：
    ~~`token/recent`~~（🔴 **2026-10-09 已修** —— 端点原来收了 `user_name` 却没用，**返回所有人的记录**；现已按人过滤 ⇒ **它成为第 10 个面板**）、
    `token/purpose` / `token/thread`（**全站口径、不分用户**）。三条**各有本人口径的替代出口**。
    🔴 其中 `token/recent` 的根因是**端点收了 `user_name` 却从没用它** ⇒ 真缺陷（`N20`）——
    **业务方 2026-10-09 当天裁「修」** ⇒ 已修（`get_recent_usage(limit, user_name=None)` + 端点传身份），
    判据 `app/tests/test_token_recent_scope.py`（**4 条**）。⇒ **修完就必须露**（它是规格 §2.5 那 9 条之一）
    ⇒ 成本看板现在是 **10** 个面板。⛔ 只修不加 = "修好了却还藏着"。
  · 🔴 **这一页同时摆着三种数**（读库 / 进程内存 / 配置常量），而它们对「**重启后还在不在**」答案不同
    ⇒ **每个面板标题上带口径徽标**。⛔ 不标的后果本仓栽过：`DEC-047`（库里有 4216 tokens，界面答 `0`，**不报错**）。
  · 🔴 **「我的额度」一格里有【两套口径】**（本人 `R1.3` + 全站 `R1.4`）⇒ 分成「我 ·」「全站 ·」两组渲染。
  · 📌 守卫：`app/tests/test_cost_page.py`（**9 条**）· `app/static/js/cost.test.js`（**25 条**）。<br>🔴 **其中第 10 格「最近使用记录」是当天【修完再加】的**（`N20`：端点原先收了 `user_name` 却没用 ⇒ 返回所有人的记录）⇒ 判据 `app/tests/test_token_recent_scope.py`（**4 条**）。
  ⚠️ **本页对"URL 字面量"那道门同样【空过】**（9 条路径由 `RagCost.buildRequest()` 出）⇒ 尺子在 `cost.test.js`。

- 🔵 **检索实验室（施工单刀 3 · 2026-10-09 · `DEC-123`）—— 第一个【能力页】** ——
  入口 `GET /lab` → `/static/web/lab.html`；规格 §2.2 那 **5 条检索接口**（`pg_search` ·
  `hybrid_search` · `rerank_search` · `rewrite_search` · `/rag/search`）**一条一个面板**。
  · 🔴 **此前只有 `chat.html` 那条流式被人点到过**，另五条**一条入口都没有** ⇒ 按最高判据**等于没做**。
  · 🔴 **三条链的分数字段名各不相同**（`similarity` / `rrf_score` / `rerank_score`）⇒ 由
    `RagLab.PANELS[key].score` 一处给，⛔ 页面里不写字面量（猜错**不报错**，只是画出一列空的）。
  · 🔴 **`rerank` 的错态必须说清是【环境限制】** —— 演示镜像没装 torch 系（`DEC-034`）⇒
    `RagLab.envLimitHint` **只在 5xx** 时给那句话（⛔ 401/429 不是环境限制，别拿它盖）。
  · 🔴 **`/rag/search` 那块带「生成答案 + 标引用」两个开关** ⇒ **硬门 B 的非流式那条链
    第一次有了界面**。⚠️ **但硬门 B 整体⛔ 不因此翻 ✅**。
  · 🔴 **边界标注的落法（本刀定的 · ⛔ 刀 4–7 照这个来）**：**页面顶部放完整 5 条**（与首页逐字同款）
    ＋**每个面板顶部放一条最相关的**（本页五块都放 `real_api`），**排在提交按钮之前**。
    ⛔ **别把 5 条抄进每个面板** —— 25 个提示框会把「一眼就能看到」稀释掉。
  · 📌 守卫：`app/tests/test_lab_page.py`（**7 条**）· `app/static/js/lab.test.js`（**20 条**）。
  ⚠️ **本页对本目录 §判据 里的"URL 字面量"那道门【空过】** —— 5 条路径由 `RagLab.buildRequest()`
    出，页面里没有 `getJSON('…')` / `fetch('…')` 那样带前缀的字面量（全局只有额度那条）。
    ⇒ 前缀的尺子在 `lab.test.js`（与 `trace.js` 的 `buildPath` 同分工）。

## 🟡 做到哪 / 缺什么

| # | 没做 | 说明 |
|---|---|---|
| 1 | **不显示历史消息** | 后端**没有**"取历史"的公开接口（`DEC-085` 契约 C 只把历史喂给**模型**）。⇒ 切回旧会话时页面给一句实话（`showEmptyLog`），⛔ **不留一块看不出所以然的空白** |
| 2 | ~~**引用卡片固定放在 `#log` 末尾**~~ ✅ **2026-10-06 修**（`DEC-089` · `F8`） | 卡片现在**挂在该条回答下面**（每条自带 `.card`），再点收起。⚠️ 旧注释里那个被 `F8` 判据当"还没修"标记的词**已删** —— ⛔ 别写回来（`grep -c 'DEMO 版' app/static/web/chat.html` ⇒ 0） |
| 3 | ~~**接管页**~~ ✅ **2026-10-06 做了**（`DEC-088` · `F1`）· ~~**Trace 页改造**~~ ✅ **同日做了**（`DEC-093` · `F2`）· ~~**Eval 页**~~ 🔶 **2026-10-07 做了「占位版」**（`DEC-097` · `F3`） | ⚠️ **四个页面都有入口了，但 Eval 那个是【占位页】** —— 页面在、按钮在、子页在，**内容是一句 `TODO`**。⛔ **别读成"评测功能做完了"**：它能变成真页面**只等两件事** —— ① `agent-eval-gate` 出数据 · ② 后端有取它的接口（`B14`）。<br>⚠️ Trace 页是**新建** `web/trace.html`；旧页 `app/static/trace_viewer.html` 曾**保留未删**（`FAQ.md` 写过它的地址）⇒ 🗑️ **2026-10-07 已删，同时改了 `FAQ.md` 那条旧地址**（`DEC-096` · `F5`）—— 见下 ⚰️ 表 |
| 4 | ~~**硬门 A / C 的其余前端项**~~ ✅ **2026-10-06 结清**（`DEC-092`） | 本刀只做了"能流、能停" ⇒ ✅ **「无据拒答」那半同日做了**（`DEC-091`）· ✅ **剩下那条「C 的其余出口」经核【没有指称对象】⇒ 删除**（🔴 硬门 C 判定原文里**没有「出口」这个概念** `grep -c '出口'` ⇒ **0**；那个词的唯一出处是 `DEC-085` §六·1 的**桶话**，**从没被展开过**）⇒ ⛔ **别读成"做掉一件"**，是账上摘掉一个**空指针** |
| 5 | ~~**R3.2 熔断提示卡片**~~ ✅ **2026-10-06 做了**（`DEC-090`） | ⚠️ 但「**怎么联系**」是**占位符** ⇒ 登记在 `N13`，⛔ 别当它做完了。<br>🔴 **2026-10-07 值按业务方裁定改过**（`DEC-095`）：`'（待设置 —— 联系入口尚未确定）'` ⇒ **`'example@example.com'`**（**RFC 2606 保留域**，公网永不解析）。⚠️ **⛔ 别把这次改动读成"联系入口已经有了"** —— 换的是值、不是那个真入口；而且理由**变强了**（旧值**自曝没填**，新值**看着像真的**）。<br>📌 判据（现取）：`grep -n 'BREAKER_CONTACT = ' app/static/js/sse.js`<br>⚠️ **没有用例钉这个值** —— `sse.test.js` 只钉四件事的**键**都在且非空 ⇒ 改它不会有用例红 |
| 6 | **DOM 那层没有自动判据** | 滚动 / 按钮态 / 渲染仍靠 DevTools 手工。`sse.js` 覆盖的是**决策**，⛔ 不是**像素** |
| 7 | ~~🔴 **硬门 B 判定里的另外两句**~~ ✅ **2026-10-06 做**（`DEC-089` · `F8`） | 判定是**三句**（**⛔ 权威原文** ⇒ `fastapi-rag-agent-TODO待办/通用/四硬门-定义与验收标准.md` 硬门 B）。①「点开能展开原文片段」`DEC-085` 做的；②「**再点能跳到原文位置**」+③「**chunk id + 相似度分**」本刀做掉 ⇒ **三句齐了**。⚠️ 但**硬门 B 整体⛔ 不等于翻 ✅** —— 判定里还有「非流式链」那类前提，见 `ROADMAP` |

### ⚰️ `app/static/` 根下的存量页 —— 2026-10-07 起**只剩一个**

| 文件 | 状况 |
|---|---|
| ~~`app/static/stream_test.html`~~ | 🗑️ **2026-10-07 删**（`DEC-096` · `F5`）—— 它调的 `/api/v1/user/chat_history` **根本不存在** ⇒ 从这个文件写下那天起就是**死的** |
| ~~`app/static/trace_viewer.html`~~ | 🗑️ **同日删** —— `fetch` **不带认证头**（加鉴权后打开必 401）；2026-10-06 起已被 `/trace` 取代。⚠️ 删它**同时改了 `docs/FAQ.md` 里那条【对外写过的旧地址】**（现在写明：打它是 404，请用 `/trace`）<br>⚠️ **删前它 `<body>` 顶部有一条指向 `/trace` 的红色横幅**（`DEC-093` 加的）—— 随文件一起没了，⛔ 别去别处找它 |
| `app/static/websocket_test.html` | ⬜ **仍在**（本批有意不碰）—— 端点路径写错 + 浏览器 WebSocket **送不了 `X-API-Key` 头**（它自己的注释里就写了） |

> ⇒ ⛔ **别读成"`app/static/` 下都是新做的东西"**。段 1 的几刀只动了 `web/`（`chat.html` · `approvals.html` · `trace.html` · `eval.html` · `eval_gate.html`）
> + `js/`（`sse.js` · `approvals.js` · `trace.js` 及其用例）；根下剩的这个是**没记录过、也没人管**的遗留。
> ⚠️ **判据（现取，⛔ 别抄旧数）**：`ls app/static/*.html` ⇒ **1 个**（`websocket_test.html`）·
> `ls app/static/web/*.html` ⇒ **5 个**。
> 🔴 **这两行改过两次**：「三个」（`DEC-096` 之前）⇒「三个」（删了两个坏页，但 `web/` 下**只删了 `trace_viewer.html`** ——
> 它在**根下**不在 `web/` 下，`web/` 那三个**没动**）⇒ 现在 **5 个**（`DEC-097` 加了 `eval.html` + `eval_gate.html`）。
> ⛔ 别因为"Trace 页做完了"就以为清单少了一个，**是两个都删了**。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`sse.js` 该写成 ES module（`import`/`export`）」** | ⛔ **不能**。本仓**没有 `package.json`** ⇒ Node 把 `.js` 当 **CJS** ⇒ 改成 `import` 会让 `node --test` 报 `Cannot use import statement outside a module`，**而浏览器里照样能跑**（`<script src>` 认经典脚本）⇒ **改坏了本地不报错**。现在两侧都满足：顶层函数 + 末尾条件挂 `window.RagSse` / `module.exports` |
| 🔴 **「引用编号 = `sources` 数组的下标」** | ⛔ **不是**。编号是 `sources[i].index`（1 起），**`id` 是数据库主键**、两者**不是一回事**。按数组下标取 ⇒ **静默错位**（页面上不报任何错）。`resolveCitations` 走 `Map(index → src)` 就是为了这个；守卫 ⇒ `sse.test.js` 的**乱序**用例 |
| 🔴 **「看见 `[DONE]` 就可以收工」** | ⛔ **不行**。`[DONE]` 排在 `sources` / `usage` **之前**（`api_v1_rag.py:_complete` 明写）⇒ 见 `[DONE]` 就 `return` = **引用与费用整段丢**。⇒ 循环必须**直到连接关闭**（`chat.html:274` 那句 `for (;;)`） |
| 🔴 **「不传 `citations` 也会有 `sources` 帧，最多是空数组」** | ⛔ **连帧都没有**。`citations` 默认 `False`（`app/routing/schemas.py:16`）⇒ 前端**必须显式传 `true`**。⚠️ 这个区别让"忘了传"看起来像"这次没有引用" —— 与"检索真的没命中"**长得一模一样** |
| ⚠️ **「本仓 RAG 端点出错时会发 `[DONE]` 收尾」** | ⛔ **故意不发**（`api_v1_rag.py:_on_error`）⇒ "没收到 `[DONE]`" **既可能是出错、也可能是用户点了停止** ⇒ 靠 `aborted` 分流（`classifyExit` 的三个入参缺一不可） |
| ⚠️ **「`hidden` 属性总能藏住元素」** | ⛔ **作者样式的 `display` 压过 UA 的 `[hidden]{display:none}`** ⇒ 曾经登录页与主界面**同时显示**（`#app` 上写着内联 `style="display:flex"`）。修法是页面顶部那条 `[hidden] { display: none !important; }` —— ⚠️ **它管的是全页**，别以为只是给 `#app` 打的补丁 |
| ⚠️ **「`RagSse` 是 `sse.js` 里的一个对象」** | ⚠️ **2026-10-06 才有的** —— 此前有 `module.exports` 但**没有 `window.RagSse`** ⇒ 页面里每处 `RagSse.xxx` 都会 `ReferenceError`，而**两侧都抓不到**：`node --test` 只走 `module.exports`；页面在**答案真的开始流之前**不会用到它。⛔ 删掉 `window.RagSse` 那两行前先想想这条 |
| ⚠️ **「引用的正则可以两边各写一份」** | ⛔ **只能有一份**（`RagSse.splitCitations`）。两处一旦漂移，**画出来的编号与点开的编号不是同一批**，而**页面上不报错**（表现是"点了没反应"）⇒ `chat.html` 里那句注释是在钉这条 |
| ⚠️ **「切回旧会话会看到旧消息」** | ⛔ **看不到** —— 本页不渲染历史（见 §🟡 1）。模型**记得**上下文，但界面上是空的 |
| 🔴 **「接管页的 `data.status === 'error'` 是"服务端 500 了"」** | ⛔ **不是** —— 那四类拒绝（0 条 / 多条候选 / 越权 / 图名不认识）**全是 HTTP 200**，是**正常的业务回答**。<br>⚠️ **代价**：`fetch` 的 `r.ok`**为真** ⇒ 只看 `r.ok` 的写法会**静默把拒绝当成成功**。⇒ `approvals.html` 每条成功路径都要再判一遍 `data.status`。 |
| ⚠️ **「`window.RagApprovals` 和 `module.exports` 是重复的」** | ⛔ **两条是给两侧的，缺一不可** —— `node --test` 只走 `module.exports`；浏览器 `<script src>` 只认 `window.*`（本仓**没有打包器**）。<br>⚠️ **删了 `window.RagApprovals`（`approvals.js:85`）** ⇒ 页面里 6 处 `RagApprovals.xxx` 全 `ReferenceError`，而 `node --test` **照样 14 条全绿**（同 `window.RagSse` 那条）。📌 反证 ⇒ 注释掉那两行后页面立刻报错，而用例**一条都不红**。 |
| 🔴 **「卡片头那两行在 `chat.html` 里拼一下就行」** | ⛔ **只能有一份实现**（`RagSse.formatSource`）。<br>🔴 **这条有结构型用例钉着**（`sse.test.js`：「相似度」这个字面量在 `static/js` + `static/web` 里**只许出现在 `sse.js`**）⇒ 在 `chat.html` 里写那个词，**用例当场红**。<br>⚠️ **为什么必须这么钉**：本仓原话「**有结构才执行，只有文字就漏**」，而 `DEC-089` 施工时**当场验证了一次** —— 页面注释里留了句「⛔ 不再是…的 DEMO 版」，而 `F8` 的旧判据正好拿 `grep -n 'DEMO 版'` 当"还没修"的标记 ⇒ **修好了反而被那条 grep 指成"还没修"**。 |
| 🔴 **「卡片状态放个全局变量就行」** | ⛔ **不行** —— 状态在**元素上**（`turn._openIndex` / `turn._byIndex`）。本页可以**连着问多轮** ⇒ 全局一个变量会让**两张卡片抢同一个状态**（点第二题的引用，第一题的卡片跟着变）。 |
| 🔴 **「`sources` 帧只在流式那边发，非流式那条链不用管」** | ⛔ **两个出口**（`app/routing/api_v1_rag.py` + `app/rag/answer_with_citations.py`），形状必须**逐字同构**。⚠️ **2026-10-06 之前这句只是注释、没有尺子** —— 实测：只给流式那侧加一个键，**其余 9 条用例全绿**（`DEC-089` §五）。现在有 `test_both_sources_exits_have_the_same_key_set` 钉着。 |
| 🔴 **「非流式那条链的 `similarity` 也该有值」** | ⛔ **它是 `None`，而且【不许】给它编一个**。非流式链的 `contexts` 来自 `rag_pipeline` 的 RRF 融合（候选字典只有 `id/content/source/from/rrf_score`，**没有 `similarity`**）⇒ 前端画 `—`。⚠️ 同 `DEC-084`：**宁可空着不编数**。 |
| 🔴 **「两种熔断靠 `code` 就能分开」** | ⛔ **分不开** —— 全站级（`B11`）与会话级（`B8`）的 `ErrorCode` **都是 `QUOTA_EXCEEDED`**（`app/core/exceptions.py` 就一个枚举）。而两者**恢复条件完全不同**（前者只能等跨天，后者**开新会话立刻能继续**）⇒ 必须靠后端补的 `scope` 字段。<br>⚠️ **改前的真缺陷**：429 只写一行「额度已用完 / 会话额度已用完」把两种混成一句 ⇒ 被会话级挡住的人**会白等一天**。 |
| 🔴 **「429 上没有 `scope` ⇒ 后端坏了」** | ⛔ **有意为之** —— **只有对话页那条链**（`stream_search`）的两处 429 带了 `scope`；全仓另 **33 处** `raise` **没接**（bounded · ⛔ 不顺手清理）。<br>⇒ 没有 `scope` 时卡片把「何时恢复」画 `—`，**这是对的**。⚠️ ⛔ 别为了"消灭 `—`"给 `scope` 兜一个默认值（比如 `"global"`）—— 那会让**中间件的限流 429**（它根本没有日级额度）也长出「明日起恢复」，前端**再也分不出"不知道"**。 |
| 🔴 **「`breakerCard` 那四句话在 `chat.html` 里拼一下就行」** | ⛔ **文字只能有一份实现**（`RagSse.breakerCard`），`chat.html` 的 `showBreaker` **只管挂 DOM**。与 `formatSource` 同一条理由：两处会漂移，而**页面上不报错**。 |
| 🔴 **「删掉某串的守卫，注释里引用那串没关系」** | ⛔ **有关系，而且实测栽过【三次】**。`sse.test.js` 的结构型守卫是**按子串扫整个前端**的 ⇒ 你在 `chat.html` 注释里写下**被禁的那串**（哪怕是为了说明"已经删掉了"），**守卫当场红**。<br>⚠️ 前科：`DEC-089` 的「…的 DEMO 版」（绊的是 `F8` 的 grep 判据）；`DEC-090` 的「额度已用完 / 会话额度已用完」（绊的是本条守卫，施工时**当场红**）；**`DEC-091` 的「根据现有资料，无法回答」**（我在注释里拿它当**例证**，当场被新守卫抓住 —— 见 `DEC-091` §七 ①）。<br>⇒ **判据**：要提那串，**拆开写**或换句话描述。 |
| 🔴 **「前端也该认一下拒答，双保险」** | ⛔ **不许** —— 判据（「这轮算不算拒答」）**只有后端那一份**（`REFUSAL_SENTENCE` + `_complete()` 里那个 `startswith`）。前端**只认帧**。两处各判一次 ⇒ 一旦漂移，**可能出现"后端发了帧、前端按另一套判"**，而**页面上不报任何错**。<br>📌 **有结构型用例盯着**：那句拒答语在 `static/js` + `static/web` 里**一个字都不许出现**（注释也算）。 |
| ⚠️ **「拒答那一轮，正文里的 `[来源:X]` 应该也能点开」** | ⛔ **不能** —— `renderRefusal` **不切引用**。实测（`DEC-091` §二）见过一条拒答**后面挂着 3 个可点来源号**：一边说"答不了"、一边给来源，是**自相矛盾**的呈现。<br>⚠️ 但正文**原样显示**：那是模型说的话，⛔ 不替它改写、⛔ 也不吞掉。 |
| 🔴 **「`no_answer` 帧没收到，说明这轮不是拒答」** | ⛔ **不能这么推** —— 判据是「答案**以那句拒答语开头**」。**换过措辞**的拒答（如「文档未提及净利润，因此无法回答该问题。」）**会被漏掉** ⇒ 那一轮按普通回答呈现。<br>⚠️ 这是**有意**的取舍：**误判比漏判有害**（把答得好的画成"资料里没有"）。取舍 + 代价 ⇒ `DEC-091` §五。 |
| 🔴🔴 **「路由 302 对了 ⇒ 这个页面就能用」** | ⛔ **两件事，实测栽过** —— `approvals.html`（`F1`）**302 正确 · 目标文件在磁盘上 · 不在 openapi 里**（三条用例全绿），**而浏览器里 100% 打不开**：它 fetch 的 **4 条 URL 全少 `/api/v1`**。<br>🔴 **三层判据一条都不会红**：页面用例只看 302 · JS 用例全是**纯函数**（前缀不经过它们）· 路由门只管**后端有没有多余的无鉴权路由**。<br>⇒ 🆕 **加了一类新守卫**：**读页面源码，把 `getJSON(...)` / `fetch(...)` 的字符串字面量抠出来，必须以 `/api/v1` 开头**。<br>🔴 **⚠️ 它在 `app/tests/test_web_pages.py`，不在 `test_trace_page.py` 里** —— 2026-10-06（`DEC-094`）搬的：原版**只读 `trace.html` 一个文件**，而**那正是它当初没拦住 `approvals.html` 的原因**；现在扫 `app/static/` 下**每一个** `.html`（实测 6 个）。<br>📌 **判据（可打印）**：`grep -n "getJSON('/\|fetch('/" app/static/web/approvals.html` ⇒ **4 条**（在 `loadPending` / `openContext` / `decide` / `loadHistory` 四处），**已全部带 `/api/v1`**（✅ 同日修完）<br>⚠️ **⛔ 别抄行号** —— 这次修复本身就把它们整体下移了 5 行（加了一段告示注释） |
| 🔴 **「Trace 页那两条轴是一条链的两段，能拼成一棵树」** | ⛔ **拼不成** —— 上半页读 `/agent/trace/{id}`（**追踪轴** · 进程内存 · 粒度 = **工具调用**），下半页读 `/agent/trace/{id}/cost`（**成本轴** · PG `token_usage_logs` · 粒度 = **模型调用**）。<br>🔴 **两轴没有共同的步 id** ⇒ 一个 `agent_decision`（模型）与一个 `search`（工具）之间**没有可判定的对应**。<br>⇒ 页面**并排画、⛔ 不相加**。⚠️ 想"合成树"只能靠**时间接近**猜层parent-child，而**猜出来的层级不报错**（本仓最恨的形态）。<br>📌 判据 ⇒ `trace.test.js` 里 `summarizeCost` **⛔ 不把 rows 加起来**那条 |
| ⚠️ **「页面里的接口 URL 写相对路径（`/agent/…`）也行」** | ⛔ **不行** —— 后端路由前缀是 **`/api/v1`**（`app/main.py:517-519` 挂载），页面由 `/static` 托管**同源**，所以相对路径**不会**被补前缀，只会打到一个**不存在的路径**上（**404，而页面上通常看不出是路径错**）。<br>⇒ 有了上面那条守卫之后，**裸的 `/agent/…` 会被用例拦下**。<br>⚠️ **但"写字面量"本身是允许的，只要带全 `/api/v1`** —— `approvals.html` 就是**带前缀的字面量**（4 条），而 `trace.html` 走的是已被用例钉住的纯函数（`RagTrace.buildPath` / `buildCostPath`）。**两种写法本仓都有，⛔ 别以为只有一种是对的**。<br>⚠️ 同理：`X-API-Key` 要**显式带**（页面自己从 `localStorage` 取，⛔ 没有 cookie 会话） |
| 🔴 **「成本看板那一页的数就是"我花了多少钱"」** | ⛔ **一半是** —— 那一页**同时摆着三种数**：**读库**的（全时累计，权威）· **进程内存**的（**平台重启容器就归零**）· **配置常量**的。⇒ 每格标题上有口径徽标，⛔ **别只看数字**。<br>⚠️ 本仓栽过同型：`/agent/cost/overview` 曾读进程内存，库里有 4216 tokens 它答 `0`，**不报错、界面照常出数**（`DEC-047`）。 |
| 🔴 **「`token/recent` 现在只回我自己的了」** | ✅ **2026-10-09 起是对的** —— 改前它读进程内 `_usage_records`（**所有人共用**）且**端点收了 `user_name` 却没用** ⇒ 回的是所有人的记录。现已按人过滤（`N20` 已结清）。<br>⚠️ **但顺序有讲究**：**先按人过滤、再取最后 `limit` 条** —— 反过来会在"总记录多、他占得少"时**回空**（看着像"他没有记录"，不报错）⇒ 有专钉顺序的用例。 |
| 🔴 **「`app/tests/test_web_pages.py` 全绿 ⇒ 检索实验室那 5 条路径也验过了」** | ⛔ **对它【空过】** —— 本页的 5 条路径**由 `RagLab.buildRequest()` 出**，页面里没有带 `/api/v1` 的 URL 字面量（全局只有额度那条 `/api/v1/agent/token/budget`）。<br>⇒ 那 5 个前缀的尺子在 **`app/static/js/lab.test.js`**（与 `trace.js` 的 `buildPath` 同一分工）。⚠️ **别把"扫不到字面量"读成"这个页面验过了"**（`DEC-094` 记过同型）。 |
| 🔴 **「三个面板的分数都一样，横向比比看哪个检索更好」** | ⛔ **不能比** —— `pg_search` 给的是余弦 `similarity`（0–1）· `hybrid`/`rewrite` 给的是 `rrf_score`（约 1/(60+rank)，**很小**）· `rerank` 给的是 Cross-Encoder `rerank_score`（logits，**可正可负**）。⇒ 三种口径**没有同一个量纲**，页面上明写了"⛔ 不能横向比大小"。 |
| 🔴 **「`rerank_search` 报 500 ⇒ 这个功能坏了」** | ⛔ **大概率是环境** —— 它要跑 Cross-Encoder（torch），而**演示镜像里没装 torch 系**（`DEC-034`）。⇒ 页面用 `RagLab.envLimitHint` **只对 5xx** 说清"这是环境限制，⛔ 不是功能坏了"。⚠️ **401/429 不走这条**（那是 key / 额度，别拿环境去盖）。 |
| 🔴 **「`app/tests/test_web_pages.py` 那 7 条全绿 ⇒ 两个 Eval 页也被它守住了」** | ⛔ **对这两页它【空过】** —— 它扫的是 `getJSON(…)` / `fetch(…)` 的**字面量**，而 `eval.html` 与 `eval_gate.html` **一个 `fetch` 都没有** ⇒ **没有字面量可查、也没有东西可判**。<br>⚠️ **这正是它那条「防空跑」用例的边界**：那条只保证**它扫过的集合非空**，⛔ 不保证**每个页面都被它真的检查到**（本仓栽过同型的"某页走 helper ⇒ 对它空过"，见 `DEC-094`）。<br>⇒ **Eval 这两页真正的守卫是 `app/tests/test_eval_page.py`**（尤其那两条页面本体的：`<a href>` 指向子页 + 子页带那一行） |
| 🔴 **「Eval 页 = 一个功能页，跟另外三个一样」** | ⛔ **不是** —— 它是**占位页**（`DEC-097`）。三个真页面各自调带鉴权的后端接口；**它一个接口都不调**，子页上那行是**静态文字**。<br>⚠️ **别拿它去证明"评测功能能用"** —— 页面上明写「只有占位」、子页以 `TODO` 结尾。<br>⚠️ **也别因为"四个页面都通了"就以为 `F3` 结清了**：`F3` 原本要的「**跑分 + 对比箭头**」**一个都没做**，是**换了交付口径**（`DEC-097` §二）。 |
| 🔴 **「`POST /agent/memory/add` 该发 JSON body」** | ⛔ **不发** —— 它的 `content` / `memory_space` 是 **query 参数**（判据：从运行中的 app 现读 `app.openapi()` ⇒ `content in=query required=True`）。<br>⚠️ 照"POST 就该发 body"的直觉写 ⇒ **422**，而**页面看起来一切正常**（只是永远失败、且失败得很安静）。<br>⚠️ `GET /agent/memory/search` 同理：它的参数**名叫 `query`** —— ⛔ 别读成"查询串"那个意思。守卫 ⇒ `tools.test.js` 那条。 |
| 🔴 **「可用工具清单 = 每一条都验过而且都好」** | ⛔ **不是** —— 端点写的是 `if health == UNHEALTHY: 剔除 else: 留下`，而**从没进过体检表**的工具 `get_tool_health()` 回 `UNKNOWN` ⇒ **落进"可用"那一堆**。<br>⇒ 这一格该读作「**哪些不是不健康**」。⚠️ 而"体检表是空的"也**不代表工具没了** —— 只有 `TEST_ARGS_MAP` **登记过**的工具才会被体检（没登记的直接 `return`，**静默**）。 |
| 🔴 **「`last_checked` 能直接 `new Date()`」** | ⛔ **不能** —— 它是 **epoch 秒**（Python `time.time()`）⇒ **必须 ×1000**。忘了 ⇒ 页面显示 **1970-01-01**，而**不报任何错**（`tools.js` 的 `fmtEpoch` 就是为这条存在的）。 |
| 🔴 **「记忆是"落盘"的，重启也还在」** | ⛔ **在 demo 平台上不成立** —— Mem0 落在**容器内**的 `./.mem0/qdrant`，而创空间是**单容器、没有挂卷** ⇒ **平台重启容器同样清空**。<br>⇒ 它的结论与"进程内存"那一类**相同**，只是慢一步。⚠️ 页面上那一格的徽标写的是「容器磁盘 · 平台重启同样会丢」，别把它读成"比内存安全"。 |
| 🔴 **「本页那 7 条路径也被 `test_web_pages.py` 守着了」** | ⛔ **对它【空过】** —— 本页路径**由 `RagTools.buildRequest()` 出**，页面里没有带 `/api/v1` 的 URL 字面量（全局只有额度那条 `/api/v1/agent/token/budget`）。<br>⇒ 那 7 个前缀的尺子在 **`app/static/js/tools.test.js`**（与 `lab.js` / `cost.js` / `trace.js` 同一分工）。⚠️ 同 `DEC-094` 记的那条：**别把"扫不到字面量"读成"这个页面验过了"**。 |
| 🔴 **「首页那两张卡都指 `/tools`，口径 ④ 不许同一 href 出现两次」** | ✅ **用锚点分开**：`/tools#tools` 与 `/tools#memory`（与刀 4 的 `/cost#cost-overview` · `/cost#cost-budget` 同一手法）。<br>⚠️ **锚点没了不报错** —— 点击照常跳转，只是**落到页首**，访客会以为自己点错了 ⇒ 所以 `test_tools_page.py` 专门钉了这两个 `id`。 |
| 🔴 **「工具 / 记忆是主要功能，侧边栏该加一条」** | ⛔ **不加** —— 规格 §3.0 把它归在「**其他功能**」，而口径 ② 是「**侧边栏只放 5 类「主要功能」**」。<br>⇒ 入口 = **首页那两张卡**（+ 直链）。⚠️ 刀 3 / 刀 4 **确实加了侧边栏**（它们那两页是主要功能）⇒ ⛔ **别按"上一刀怎么做的"推本刀**（`DEC-139`）。 |
| 🔴 **「`/health` `/ready` `/metrics` 也该带 `/api/v1`」** | ⛔ **不带** —— 它们**就是根路径**（`app/main.py` 的 `@app.get("/health")`，⛔ 不在 `include_router(prefix="/api/v1")` 下）。<br>⚠️ 而硬约束 #8 是「**每个 URL 字面量必须带 `/api/v1`**」⇒ **一旦把它们写成字面量，那道门会红，而那条红看起来像"前缀漏了"**，会把人引向**错误的修法**。<br>⇒ 处置：本页**一个字面量都不写**，四条全走 `RagSystem.buildRequest()`（`system.test.js` 钉"三条根路径 + 一条带前缀"）。📌 `test_system_page.py` 另有专门一条拦这个。 |
| 🔴 **「`POST /agent/execute_code` 该发 JSON body」** | ⛔ **不发** —— 它的 `code` 是 **query 参数**（判据：现读 `app.openapi()` ⇒ `code in=query required=True`）。⚠️ 同 `memory/add`：发 body ⇒ **422**，而页面**看起来一切正常**。 |
| 🔴 **「`/ready` 报 503 ⇒ 服务坏了」** | ⛔ **多半只是"还没到 10 秒"** —— 它先判 `time.time() - APP_START_TIME < 10` ⇒ **刚起的容器必然 503**。<br>🔴 **本机实测过（2026-10-10）**：服务起来后立刻 `curl /ready` ⇒ **503**；`/health` ⇒ 200。⚠️ 这是「**暂时别把流量给我**」，⛔ 不是「我坏了」（`B12` 修过的正是 503/500 的口径）。 |
| 🔴 **「`/health` 只回 200」** | ⛔ **不健康时回 503 + `{error, code, status_code}`** —— ⚠️ **那支与 200 那支的键完全不同**（200 有 `checks`，503 没有）⇒ 页面对非 2xx **也要读 body**（走 `RagSystem.errorPayloadOf`）。 |
| 🔴 **「`/metrics` 能 `JSON.parse`」** | ⛔ **它是 `text/plain`**（Prometheus 格式；实测 `content-type: text/plain; version=1.0.0`）—— 当 JSON 解 ⇒ **当场抛**。⇒ 那一格**只原样显示**（`<pre>` + 截断时**报出总行数**），⛔ 不解析。⚠️ 判据钉在**面板定义**上（`isRaw`），⛔ 不是"运行时看 content-type"（401/503 那类会换结果）。 |
| 🔴 **「执行器挂了会回落本地跑」** | ⛔ **不会** —— 回落**只由配置决定**（`EXECUTOR_URL` 空不空）。若"失败就回落"，**运维停了执行器 ⇒ 代码又回宿主跑，而没人会发现**（`DEC-108` 实测）。⇒ 页面上要写出来，否则访客会以为"没输出 = 代码慢"。<br>⚠️ **而且 `DEMO_MODE` 下 `execute_python` 根本不注册**（创空间单容器 ⇒ 没有执行器）⇒ **演示机上这一格必然失败**，那是**有意的**。 |
| 🔴🔴 **「多行输入那格只写 `style="display:block"` 就能覆盖 `.field`」** | ⛔ **不能** —— 通用 `.field` 带 **`white-space: nowrap`**，而**那条属性不吃 `display` 的覆盖** ⇒ 行内的 `<span>` 与 `inline-block` 的 `<textarea>` 被逼**同一行**放不下 ⇒ **textarea 溢出到格子外面**。<br>📌 **实测（2026-10-10 刀 6）**：label 在 `x=253` 宽 `338`，而 textarea 跑到 **`x=547`**、标签文字被挤到该行**基线下方**。<br>⚠️ **当时 11 条页面守卫全绿** —— 它们判的是"有没有 `<textarea>`"，⛔ **一条都不判它在哪、有多宽**（「**用例全绿证不了页面没坏**」）。⇒ 修法是**另起一个类**（`.field.code-field`）**同时覆盖 display 与 white-space**，且守卫钉住那个类名。 |
| 🔴 **「系统与执行器是主要功能，侧边栏该加一条」** | ⛔ **不加** —— 同刀 5 那条理由（规格 §3.0 归「其他功能」）。⇒ 入口 = 首页那两张卡，带锚点 `/system#executor` · `/system#system`。 |

## 判据（可打印）

```bash
# ① 纯逻辑（自动的，CI 里也有）
node --test app/static/js/sse.test.js        # ⇒ ℹ tests 32 / pass 32 / fail 0（2026-10-06 实测；DEC-091 前是 29，DEC-090 前是 23）
node --test app/static/js/approvals.test.js  # ⇒ ℹ tests 14 / pass 14 / fail 0（同批实测）
node --test app/static/js/trace.test.js      # ⇒ ℹ tests 24 / pass 24 / fail 0（DEC-093 实测）
venv/bin/python -m pytest app/tests/test_chat_page.py -q        # ⇒ 3 passed（GET /chat 的三条守卫）
venv/bin/python -m pytest app/tests/test_approvals_page.py -q   # ⇒ 3 passed（GET /approvals 的三条守卫）
venv/bin/python -m pytest app/tests/test_trace_page.py -q       # ⇒ 6 passed（GET /trace：3 条同构 + 3 条页面坏法的守卫）
venv/bin/python -m pytest app/tests/test_eval_page.py -q        # ⇒ 5 passed（GET /eval：3 条同构 + 2 条占位页本体的）
venv/bin/python -m pytest app/tests/test_lab_page.py -q         # ⇒ 7 passed（GET /lab：4 条同构 + 2 条页面本体的）
venv/bin/python -m pytest app/tests/test_cost_page.py -q        # ⇒ 9 passed（GET /cost：4 条同构 + 4 条本页特有的）
node --test app/static/js/cost.test.js                    # ⇒ pass 25 / fail 0（刀 4 实测；⚠️ 数量别抄）
node --test app/static/js/lab.test.js                     # ⇒ pass 20 / fail 0（刀 3 实测；⚠️ 数量别抄，跑命令）
venv/bin/python -m pytest app/tests/test_web_pages.py -q        # ⇒ 7 passed（6 个 .html 的 URL 前缀 + 1 条防空跑）
#   对端（后端那半，本页消费的契约）——
venv/bin/python -m pytest app/tests/test_frontend_contract.py -q   # ⇒ 17 passed（契约 A/B + DEC-089 的 similarity + DEC-090 契约 E 的 scope 三条 + DEC-091 契约 F 四条）
venv/bin/python -m pytest app/tests/test_token_tracker_cost_helpers.py -q   # ⇒ 5 passed（费用行那三个纯函数）

# ①' 🔴 引用卡片那两句（DEC-089 · F8）—— 会动的判据（⛔ 别用旧那条，它测不出来）
grep -n 'RagSse.formatSource\|RagSse.toggleOpen' app/static/web/chat.html  # ⇒ 非空
grep -c '<div class="card" hidden>' app/static/web/chat.html              # ⇒ 1
grep -c "id='card'\|getElementById('card')" app/static/web/chat.html      # ⇒ 0（旧的全局卡片没了）
grep -c 'DEMO 版' app/static/web/chat.html                                # ⇒ 0（改前 1）
# ⚠️ F8 旧判据的后半条 `grep -c 'chunk\|score\|相似度' app/static/web/chat.html` **改前改后都是 0** ——
#    反证检验：取反（"卡片画了 id/相似度"）它照样打 0 ⇒ **它从来不是③的尺子**，已弃用（见 DEC-089 §五）。

# ①'' 🔴 熔断卡片（DEC-090 · R3.2）—— 同样要"会动"的判据
grep -n 'RagSse.breakerCard' app/static/web/chat.html      # ⇒ 非空（页面真的在用它）
grep -c '<div class="breaker" hidden>' app/static/web/chat.html   # ⇒ 1（每条回答自带一个）
grep -c '今日额度已用完 / 会话额度已用完' app/static/web/chat.html  # ⇒ 0（那句混话没了；改前 1）
#    后端的对端：两种熔断的 429 必须带 **不同** 的 scope ——
venv/bin/python -m pytest app/tests/test_frontend_contract.py -q -k quota   # ⇒ 3 passed
# ⚠️ **反证检验**（DEC-090 §五 实测）：把 breakerCard 里 global/session 两句**对调** ⇒ pass 27 / fail 2 ·
#    拿掉 `scope="session"` ⇒ pass 11 / fail 2。⛔ 别只看"它绿"。

# ①''' 🔴 无据拒答（DEC-091 · F4 第一条）—— 判据只有后端一份
venv/bin/python -m pytest app/tests/test_frontend_contract.py -q -k no_answer   # ⇒ 4 passed, 13 deselected
grep -rn '无法回答' app/static/ | wc -l          # ⇒ 0 —— ⛔ 前端不许自己认拒答（结构型用例在管）
grep -rn 'no_answer' app/static/js/sse.js app/static/web/chat.html        # ⇒ 各 1 处（认帧 / 收帧）
grep -n 'REFUSAL_SENTENCE' app/routing/api_v1_rag.py     # ⇒ 4 行：**两处是代码**（常量定义 + prompt 那句），
#    另两处是注释里提它 ⇒ ⚠️ **别用 `grep -c` 当计数**（这是个混过的集合，本仓栽过）。
# ⚠️ **反证检验**（DEC-091 §六 实测）：`startswith` 改 `in` ⇒ **只红 1 条**；
#    删掉那两行 `yield` ⇒ **红 2 条**（正反两条对照）。⛔ 别只看"它绿"。

# ② 那三条路由
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/chat
#   ⇒ 302 http://127.0.0.1:8000/static/web/chat.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/approvals
#   ⇒ 302 http://127.0.0.1:8000/static/web/approvals.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/trace
#   ⇒ 302 http://127.0.0.1:8000/static/web/trace.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/eval
#   ⇒ 302 http://127.0.0.1:8000/static/web/eval.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/lab
#   ⇒ 302 http://127.0.0.1:8000/static/web/lab.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/cost
#   ⇒ 302 http://127.0.0.1:8000/static/web/cost.html
# 🔴 这**六条**必须在 scripts/route-auth-baseline.txt 里（故意公开）—— `check_route_auth.py --baseline` **查不出"路径被删"**
#    （少一条它报「少了 N 条（修好了）」并 exit 0）⇒ 真正的守卫是那五个 page 用例（2026-10-09 起含 `test_lab_page.py`）

# ②'' 🔴 Eval 占位页（DEC-097 · F3）—— 「按钮指向子页、子页带那一行」两条要能【会动】
venv/bin/python -m pytest app/tests/test_eval_page.py -q               # ⇒ 5 passed
grep -n 'href="/static/web/eval_gate.html"' app/static/web/eval.html   # ⇒ 1 条（按钮真的指向子页）
grep -c 'agent-eval-gate · Agent 生产就绪评测门 · TODO' app/static/web/eval_gate.html  # ⇒ 1
# ⚠️ **反证检验**：把 `href` 改成 `#` ⇒ 红 1 条；把那一行改一个字 ⇒ 红 1 条。⛔ 别只看"它绿"。
grep -rn 'fetch(\|getJSON(' app/static/web/eval.html app/static/web/eval_gate.html  # ⇒ 0 条（**两页都不调接口**）

# ②' 🔴 页面里的 URL 字面量（DEC-093 建的那类守卫，DEC-094 起扫全站）—— 三把尺子
grep -n "getJSON('/\|fetch('/" app/static/web/trace.html        # ⇒ 0 条（Trace 页走 buildPath/buildCostPath，⛔ 不写字面量）
grep -n "getJSON('/\|fetch('/" app/static/web/approvals.html     # ⇒ 4 条，**全部带 /api/v1**（✅ 2026-10-06 修完；改前 4 条均无）
venv/bin/python -m pytest app/tests/test_web_pages.py -q               # ⇒ 7 passed（扫 6 个页面 + 防空跑；⚠️ 某页若走 helper / 不调接口，对它【空过】）

# ③ ⛔ 写不成命令的（手工，2026-10-06 实测过一次）
#   · 硬门 A：Network 里 type = text/event-stream，正文增长时连接未关
#   · 硬门 B：点 [来源:X] ⇒ 卡片里是【全文】（⛔ 不是摘要）+ 卡片头有 id/相似度 +
#     **再点同一条 ⇒ 收起** + 卡片在**该条回答下面**（⛔ 不是 log 末尾）
#   · 硬门 C：点「停止」⇒ 请求变 (canceled) + 徽标「已中断」+ 费用行「中断未计费」
#   · 硬门 D：接管页点开一行 ⇒ 看得见【完整上下文】（messages 序列）⇒ 批准 / 拒绝
```

## 关联

- `docs/decisions/DEC-085-对话页一条线的四个契约.md`（A/B/C/D 四个契约 + 9 条裁定）
- 🔴 `docs/decisions/DEC-089-引用卡片就地展开与sources帧补相似度.md`（**`F8`**：② 就地展开/收起 ·
  ③ 卡片头 `id + 相似度` · `sources` 帧补 `similarity` · **两个出口同形的守卫**）
- 🔴 `docs/decisions/DEC-090-熔断卡片与429补scope.md`（**`F4` 第三条 · `R3.2`**：四件事 ·
    429 补 `scope` · **只接对话页这一条链**）· 对端 `app/billing/specs/breaker.md`（熔断器本身）·
    `app/billing/specs/token_tracker.md`（两种额度的口径）
- 🔴 `docs/decisions/DEC-091-无据拒答给一个机器可读的信号.md`（**`F4` 第一条 · 硬门 B 第二半**：
  `no_answer` 帧 · **判据只有后端一份** · 三轮真栈 spike 判死了"相似度阈值"那条路）
- `app/routing/specs/api_v1_rag.md`（对端：`sources` 的 `index` / 末尾 `usage` 帧）· `app/routing/specs/sse.md`（共享 SSE 层）
- `docs/decisions/DEC-033-上公网路线的两条前置约束.md` 🅱️（**后端先行** —— 前端是本刀才开始的）
- 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-对话页.md`
- 🔴 `docs/decisions/DEC-088-接管页与硬门D的三个缺口.md` + `app/routing/specs/api_v1_agent.md`（**接管页消费的四条后端接口**：
  `/agent/pending` · `/agent/pending/context` · `/agent/approve` · `/agent/approvals/history`）·
  `app/agent/specs/approval_audit.md`（**裁决历史那张表**）
- 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-接管页.md`
- 🔴 `docs/decisions/DEC-093-Trace页两轴分屏.md` + 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-Trace页.md`
  （**`F2` Trace 页**：两轴分屏 · `/trace` 入口 · **第 4 类页面守卫（URL 前缀）** ·
  ⭐ 同时是 **`approvals.html` 缺 `/api/v1` 那个事故的首次记录处**（收尾见 `DEC-094`））·
  对端 `app/routing/specs/api_v1_agent.md`（`/agent/trace/{id}` 与 `/agent/trace/{id}/cost` 两条端点）·
  `app/billing/specs/token_tracker.md`（**成本轴的本尊** —— `thread_cost_breakdown` / `_iso_utc` / 时区陷阱）·
  `app/tools/specs/tool_visualizer.md`（**追踪轴的本尊** —— 进程内存 · 概览卡那两格恒为 0）
- 🔴 `docs/decisions/DEC-094-前缀事故收尾与CI用例改glob.md`（**`approvals.html` 4 条 URL 的修复** ·
  **页面守卫改扫全站** · **`ci.yml` 的 `node --test` 改 glob + 防空跑** —— 含"裸 glob 更弱"的反证实测）
- 🔴 `docs/decisions/DEC-097-Eval页降级为占位页.md`（**`F3`**：**把"跑分 + 对比箭头"改成占位页**的裁定 ·
  `/eval` 入口 · ⚠️ **它明写"这不是把功能做完了，是换了交付口径"**）
- 🔴 `docs/decisions/DEC-124-刀4成本看板的可见性与口径.md`（**刀 4**：**可见性预检**（`intercepts` 本人可见 ⇒ 露；`token/purpose`/`thread` 不是本人口径 ⇒ 不露；`token/recent` **是缺陷 ⇒ 已修 + 加成第 10 格**）· **口径徽标** · 首页两张卡同址用**锚点** · 面板边界文案改**短版** · 六条反证）
- 🔴 `docs/decisions/DEC-123-刀3检索实验室的两个落点.md`（**刀 3**：**能力页的边界标注怎么落**
  （页面顶部 5 条 + 每面板 1 条、排在提交按钮之前）· **五条检索接口归位** ·
  **侧边栏导航只放「主要功能」那 5 类** · 四条反证实测记录）

---

## 🔴 2026-10-08 · 分页（`frontend/README.md` §六）

**改前的现状**：本仓**没有一个列表有 `offset`** —— 全是"取最近 N 条"，
而 `approvals.html` **硬写 `limit=50`、界面不说明被截了**（**静默截断**）。

**做了什么**（先做一条路，⛔ 不是一次铺开）：

| 层 | 落点 |
|---|---|
| **后端** | `GET /agent/approvals/history` 加 **`offset`** · 响应补 **`has_more` / `limit` / `offset`**；`approval_audit.list_decisions(..., offset=0)` 加 `OFFSET` |
| **纯逻辑** | `app/static/js/approvals.js` 的 **`pagerState()`** —— 页码/上下页/偏移量**全在这里算**，⛔ 页面不自己推 |
| **CSS** | `app/static/app.css` 的 **`.pagination`** |
| **页面** | `approvals.html` 的 `#pager`（⚠️ **新增**元素，⛔ 没改任何既有 class/id） |

🔴 **更正（同日核出）**：本节初稿写「本仓没有一个列表有分页」——**不准确**。
`/agent/trace/{thread_id}/cost` **早就做对了**：`items` 有 `LIMIT`，但响应给 `truncated`
（`total.count > len(items)`）、**合计由 SQL 算整条线程**（⛔ 不受 LIMIT 影响）。
⇒ 本仓有**两种**做法：**A `offset` 翻页**（用户要一直往下看）· **B 截断 + 说出来**（看汇总）。
**两条路的共同那一半 —— 「必须说出来」—— 现在是门**：`app/tests/test_truncation_declared.py`
（凡收了 `limit` 的端点，响应必须有 `truncated` 或 `has_more`）。

**两条红线**（规范里的）：

1. **⛔ 不许前端假分页** —— 组件⛔ 不切数组、⛔ 不缓存全量；翻页 = **带新 `offset` 再发一次请求**。
2. **⛔ 被截断必须说出来** —— `has_more` **只认服务端给的字段**；
   ⛔ **尤其不许拿 `count == limit` 猜** —— 那在"正好一整页、后面没有了"时会显示一个
   **点不动的下一页**，而且不报错。`pagerState` 用 **`hasMore === true`**（严格），缺失一律 `false`。

📌 **判据（可打印）**：

```bash
node --test app/static/js/approvals.test.js                       # ⇒ 23 pass（含 pagerState 9 条）
venv/bin/python -m pytest app/tests/test_approval_events.py -q          # ⇒ 14 passed（含 has_more 两条）
POSTGRES_DB=rag_test venv/bin/python -m pytest app/tests/test_approval_events_db.py -q -m needs_db
                                                                  # ⇒ 8 passed（含翻页不重不漏）
```

⚠️ **本份没解决**：**其余列表端点仍无分页**（`/agent/token/usage` · `/agent/cost/*` 等）——
它们的"取最近 N 条"**仍然不说自己被截了**。⇒ 要铺开时照这一条的走法。
⚠️ **已知局限**：`offset` 分页在**有新行插入时会漂移**（第 2 页可能重复上一页的某条）
—— 页面每 5 秒轮询，所以这个窗口是真实存在的。⛔ 没做游标分页（那是另一件事）。


---

## 🔴 2026-10-09 · **首页还没做，但要求已经定了**（⛔ 别以为"4 个页面都有入口"就够了）

> **业务方原话**：「**首页应该是要做成【主要功能】和【其他功能】分开，能点击跳转的**」

| | |
|---|---|
| **业务方问过** | 「**是 specs 没记录吗**」—— 🔴 **当时的答案是【没有】**：<br>`grep -rn '主要功能\|其他功能'` ⇒ **全仓 0 命中**；本文件里也**只有 4 条页面路由**，⛔ 没有"首页"这一格 |
| **现在的落点** | ⭐ **`frontend/页面与接口规格.md` §3.0**（**唯一权威** —— 那里有主次划分的建议 + "能点击跳转"的判据） |
| **为什么写在这里** | 本文件是**前端模块的 spec** ⇒ 它必须**指出那份规格**，⛔ 不能各自记一半 |

### 现状（⛔ 别读成"首页已经算了"）

* ✅ **4 条页面路由**（`/chat` `/approvals` `/trace` `/eval`）—— **都能打开**
* 🔴 **但【没有首页】**：`GET /`（`app/main.py:521`）返回的是 **JSON**（`{"status":"ok",…}`）⇒
  访客打开域名**第一眼是一坨 JSON** —— 正是最高判据说的「**做成一堆、什么都放后端**」
* 🔴 **且全仓 66 条路由里，约 53 条【没有任何可点入口】** ⇒ 按最高判据**都等于"没做"**
  （逐条归位表 ⇒ 那份规格 §二）

⚠️ **`GET /` 改返回是【已存在路由】的行为变更** ⇒ 动它要连带核三处：
① 有没有消费者依赖那段 JSON ② **它在无鉴权基线里**（`scripts/route-auth-baseline.txt`）
③ 新页面路由要不要与现有 4 条**同形**（302 · `include_in_schema=False` · 进基线）
