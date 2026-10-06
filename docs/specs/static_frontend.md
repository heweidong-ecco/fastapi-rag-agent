# `api/static/` —— 前端（**本仓第一个没有 `.py` 模块的子系统**）

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用**（2026-10-06 建 · `DEC-085` 段 1 第一刀）—— **两个页面通了**：对话页（`DEC-085`）+ **接管页**（`DEC-088` · `F1`）；**Trace 页改造 / Eval 页仍没做** |
| **对外提供** | `GET /chat` → **302** `/static/web/chat.html`（`api/main.py:531`，**`include_in_schema=False`**）<br>`GET /approvals` → **302** `/static/web/approvals.html`（`api/main.py:540`，**同上**）<br>· 页面本体由已挂的 `/static` 托管（零构建、零新服务、零 CORS）<br>⚠️ **两条 302 都在无鉴权基线里**（`scripts/route-auth-baseline.txt`）—— **故意公开**：它们是"给人打开 HTML"的跳转，**本身不含数据**；真正的边界在页面调的后端接口上 |
| **谁在用** | 人（浏览器）。⚠️ **后端不 import 它、没有任何 `.py` 依赖它** —— 这就是本目录此前一直是"没人管"的原因 |

**两个页面、各 3 个文件**（其余 3 个老页面见 §🟡）：

| 文件 | 行数 | 是什么 |
|---|---:|---|
| `api/static/web/chat.html` | 358 | 对话页：装配层（DOM / fetch / 状态机 / 渲染） |
| `api/static/js/sse.js` | 136 | **纯逻辑**：帧解析 / 引用映射 / 出口判定 / 费用格式 —— ⛔ 不碰 DOM、不发请求 |
| `api/static/js/sse.test.js` | 207 | `node --test` 用例（**18 条**）—— 钉住 `sse.js`<br>⚠️ **数量别抄文档** —— 跑 `node --test api/static/js/sse.test.js`（Task 1–8 期间从 11 涨到 18） |
| `api/static/web/approvals.html` | 247 | **接管页**：待接管表 / 点开看完整上下文 / 批准·拒绝·代填工具结果 / 裁决历史 |
| `api/static/js/approvals.js` | 86 | **纯逻辑**：消息归一 / 工具摘要 / 计时文案 / 轮询节拍 / 两个载荷构造 |
| `api/static/js/approvals.test.js` | 120 | `node --test` 用例（**14 条**）—— 钉住 `approvals.js`（同上：⛔ 数量别抄） |

## ✅ 做了什么

- **对话页一条线**：登录（粘 API Key，存 `localStorage`）→ 新会话（前端生成 `thread_id`）→
  提问 → **SSE 逐字渲染** → 引用可点开 → 费用行 → **停止按钮**。
- **纯逻辑与装配层切开**：能写成命令的那部分全在 `sse.js`，被 `node --test` 钉住
  （`DEC-085` 裁定 #9）。⇒ **本仓第一次有能自动跑的前端用例**，且**零 npm 依赖**
  （⛔ 没有 `package.json`，不引 Playwright —— 那是另一笔账）。
- **出口状态机**：`idle → 请求中 → 流式中 → 完成 / 已中断 / 出错 / 未收到结束标志`。
  四种出口**分开显示**，⛔ 不合并（`DEC-082` / `N9` 的口径）。
- **三种失败说三句话**（`explainStatus`）：`401` 让重新贴 key · **`503` 明说"不是你的 key 的问题"** ·
  `429` 说额度。⚠️ 合并它们会让人**换 key 换到怀疑人生**（而根因在服务端）。
- **硬门 B / C 的界面那条线**（手工验过，见 §判据）：引用可点开**全文** · 停止 ⇒
  网络层真取消 + 「已中断」徽标 + 「中断未计费」。
- 🔵 **接管页（`DEC-088` · `F1` · 2026-10-06）** —— **硬门 D 演示那一栏**（它的反例原文是
  「**界面上找不到**」，所以这一块**只能靠界面**，后端补不出它）：
  · **待接管表**（属主 / 图 / 轮次 / 卡了多久 / 待批的工具）→ **点一行**拉完整上下文 → **批准 / 拒绝**，
    可**代填这次工具调用的结论**（不填 = 原样放行）；下面一张**裁决历史**表。
  · **同样切开纯逻辑与装配层**：`approvals.js` 被 `node --test` 钉住（**14 条**），渲染 / 点击 / 轮询留在 HTML 里。
  · 🔴 **轮询只在页面可见时**（裁定 5）：`nextPollDelay(document.visibilityState)` ⇒ 不可见返回 `null`，
    调用方**不排下一次**。⚠️ 理由：接管页是**人工**工作台，没人看的时候还每 5s 打三条接口纯属白烧。
  · 🔴 **措辞不是"改答案"**（裁定 4）：界面上写的是「**代替模型执行这次工具调用**」——
    它的真实语义是把结论**当作工具结果**喂回去（见 `docs/specs/approval_audit.md` 那条 `edited`）。
  · 🔴 **接口的四类拒绝全是 HTTP 200 + `{"status":"error"}`** ⇒ 页面必须**读 body**，⛔ 只看 `r.ok` 会把
    "无权查看"当成成功（`explainStatus` 只管 401/429/5xx 那类**真错**的状态码）。

## 🟡 做到哪 / 缺什么

| # | 没做 | 说明 |
|---|---|---|
| 1 | **不显示历史消息** | 后端**没有**"取历史"的公开接口（`DEC-085` 契约 C 只把历史喂给**模型**）。⇒ 切回旧会话时页面给一句实话（`showEmptyLog`），⛔ **不留一块看不出所以然的空白** |
| 2 | **引用卡片固定放在 `#log` 末尾** | ⛔ 不是插在该条回答下面；再点一次就换内容。DEMO 版取舍，不是 bug —— 但**会被读成 bug** |
| 3 | ~~**接管页**~~ ✅ **2026-10-06 做了**（`DEC-088` · `F1`）· **Trace 页改造 / Eval 页** | **后两个没做**。Trace 页改造的对象是 `api/static/trace_viewer.html`（⚰️ 见下） |
| 4 | **硬门 A / C 的其余前端项** | 本刀只做了"能流、能停" |
| 5 | **R3.2 熔断提示卡片** | 没做 |
| 6 | **DOM 那层没有自动判据** | 滚动 / 按钮态 / 渲染仍靠 DevTools 手工。`sse.js` 覆盖的是**决策**，⛔ 不是**像素** |
| 7 | 🔴 **硬门 B 判定里的另外两句** | 判定是**三句**（**⛔ 权威原文** ⇒ `fastapi-rag-agent-TODO待办/通用/四硬门-定义与验收标准.md` 硬门 B），本刀**只做掉第一句**「点开能展开原文片段」。⬜ 「**再点能跳到原文位置**」· ⬜ 证真那句「能看到 **chunk id + 相似度分**」—— 卡片只渲染 `[index] source` + `content`，**两个都没有**。⚠️ **与第 2 行是两个不同的缺**：第 2 行说卡片的**位置**不对，本行说**信息与跳转**没有 ⇒ `docs/待办总表.md` §三·附2 的 `F8` |

### ⚰️ 同目录下三个【存量坏页】—— 本刀**没碰**（本仓：⛔ 不顺手清理）

| 文件 | 什么毛病 |
|---|---|
| `api/static/stream_test.html` | 调**不存在**的 `/api/v1/user/chat_history` |
| `api/static/trace_viewer.html` | `fetch` **不带认证头** ⇒ 现在 401 |
| `api/static/websocket_test.html` | 端点路径写错 + 浏览器 WebSocket **送不了 `X-API-Key` 头**（它自己的注释里就写了） |

> ⇒ ⛔ **别读成"`api/static/` 下都是新做的东西"**。两刀加起来只动了 `web/`（`chat.html` · `approvals.html`）
> + `js/`（`sse.js` · `approvals.js` 及其用例），
> 另外三个是同一批「没记录过、也没人管」的遗留。
> ⚠️ **判据**：`ls api/static/*.html` ⇒ 三个；`ls api/static/web/ api/static/js/` ⇒ 只有上面那 6 个。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`sse.js` 该写成 ES module（`import`/`export`）」** | ⛔ **不能**。本仓**没有 `package.json`** ⇒ Node 把 `.js` 当 **CJS** ⇒ 改成 `import` 会让 `node --test` 报 `Cannot use import statement outside a module`，**而浏览器里照样能跑**（`<script src>` 认经典脚本）⇒ **改坏了本地不报错**。现在两侧都满足：顶层函数 + 末尾条件挂 `window.RagSse` / `module.exports` |
| 🔴 **「引用编号 = `sources` 数组的下标」** | ⛔ **不是**。编号是 `sources[i].index`（1 起），**`id` 是数据库主键**、两者**不是一回事**。按数组下标取 ⇒ **静默错位**（页面上不报任何错）。`resolveCitations` 走 `Map(index → src)` 就是为了这个；守卫 ⇒ `sse.test.js` 的**乱序**用例 |
| 🔴 **「看见 `[DONE]` 就可以收工」** | ⛔ **不行**。`[DONE]` 排在 `sources` / `usage` **之前**（`api_v1_rag.py:_complete` 明写）⇒ 见 `[DONE]` 就 `return` = **引用与费用整段丢**。⇒ 循环必须**直到连接关闭**（`chat.html:274` 那句 `for (;;)`） |
| 🔴 **「不传 `citations` 也会有 `sources` 帧，最多是空数组」** | ⛔ **连帧都没有**。`citations` 默认 `False`（`api/schemas.py:16`）⇒ 前端**必须显式传 `true`**。⚠️ 这个区别让"忘了传"看起来像"这次没有引用" —— 与"检索真的没命中"**长得一模一样** |
| ⚠️ **「本仓 RAG 端点出错时会发 `[DONE]` 收尾」** | ⛔ **故意不发**（`api_v1_rag.py:_on_error`）⇒ "没收到 `[DONE]`" **既可能是出错、也可能是用户点了停止** ⇒ 靠 `aborted` 分流（`classifyExit` 的三个入参缺一不可） |
| ⚠️ **「`hidden` 属性总能藏住元素」** | ⛔ **作者样式的 `display` 压过 UA 的 `[hidden]{display:none}`** ⇒ 曾经登录页与主界面**同时显示**（`#app` 上写着内联 `style="display:flex"`）。修法是页面顶部那条 `[hidden] { display: none !important; }` —— ⚠️ **它管的是全页**，别以为只是给 `#app` 打的补丁 |
| ⚠️ **「`RagSse` 是 `sse.js` 里的一个对象」** | ⚠️ **2026-10-06 才有的** —— 此前有 `module.exports` 但**没有 `window.RagSse`** ⇒ 页面里每处 `RagSse.xxx` 都会 `ReferenceError`，而**两侧都抓不到**：`node --test` 只走 `module.exports`；页面在**答案真的开始流之前**不会用到它。⛔ 删掉 `window.RagSse` 那两行前先想想这条 |
| ⚠️ **「引用的正则可以两边各写一份」** | ⛔ **只能有一份**（`RagSse.splitCitations`）。两处一旦漂移，**画出来的编号与点开的编号不是同一批**，而**页面上不报错**（表现是"点了没反应"）⇒ `chat.html` 里那句注释是在钉这条 |
| ⚠️ **「切回旧会话会看到旧消息」** | ⛔ **看不到** —— 本页不渲染历史（见 §🟡 1）。模型**记得**上下文，但界面上是空的 |
| 🔴 **「接管页的 `data.status === 'error'` 是"服务端 500 了"」** | ⛔ **不是** —— 那四类拒绝（0 条 / 多条候选 / 越权 / 图名不认识）**全是 HTTP 200**，是**正常的业务回答**。<br>⚠️ **代价**：`fetch` 的 `r.ok`**为真** ⇒ 只看 `r.ok` 的写法会**静默把拒绝当成成功**。⇒ `approvals.html` 每条成功路径都要再判一遍 `data.status`。 |
| ⚠️ **「`window.RagApprovals` 和 `module.exports` 是重复的」** | ⛔ **两条是给两侧的，缺一不可** —— `node --test` 只走 `module.exports`；浏览器 `<script src>` 只认 `window.*`（本仓**没有打包器**）。<br>⚠️ **删了 `window.RagApprovals`（`approvals.js:85`）** ⇒ 页面里 6 处 `RagApprovals.xxx` 全 `ReferenceError`，而 `node --test` **照样 14 条全绿**（同 `window.RagSse` 那条）。📌 反证 ⇒ 注释掉那两行后页面立刻报错，而用例**一条都不红**。 |

## 判据（可打印）

```bash
# ① 纯逻辑（自动的，CI 里也有）
node --test api/static/js/sse.test.js        # ⇒ ℹ tests 18 / pass 18 / fail 0（2026-10-06 实测）
node --test api/static/js/approvals.test.js  # ⇒ ℹ tests 14 / pass 14 / fail 0（同批实测）
venv/bin/python -m pytest api/test_chat_page.py -q        # ⇒ 3 passed（GET /chat 的三条守卫）
venv/bin/python -m pytest api/test_approvals_page.py -q   # ⇒ 3 passed（GET /approvals 的三条守卫）
#   对端（后端那半，本页消费的契约）——
venv/bin/python -m pytest api/test_frontend_contract.py -q   # ⇒ 7 passed（DEC-085 契约 A/B）
venv/bin/python -m pytest api/test_token_tracker_cost_helpers.py -q   # ⇒ 5 passed（费用行那三个纯函数）

# ② 那两条路由
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/chat
#   ⇒ 302 http://127.0.0.1:8000/static/web/chat.html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/approvals
#   ⇒ 302 http://127.0.0.1:8000/static/web/approvals.html
# 🔴 这两条**必须在** scripts/route-auth-baseline.txt 里（故意公开）—— `check_route_auth.py --baseline` **查不出"路径被删"**
#    （少一条它报「少了 N 条（修好了）」并 exit 0）⇒ 真正的守卫是那两个 page 用例

# ③ ⛔ 写不成命令的（手工，2026-10-06 实测过一次）
#   · 硬门 A：Network 里 type = text/event-stream，正文增长时连接未关
#   · 硬门 B：点 [来源:X] ⇒ 卡片里是【全文】（⛔ 不是摘要）
#   · 硬门 C：点「停止」⇒ 请求变 (canceled) + 徽标「已中断」+ 费用行「中断未计费」
#   · 硬门 D：接管页点开一行 ⇒ 看得见【完整上下文】（messages 序列）⇒ 批准 / 拒绝
```

## 关联

- `docs/decisions/DEC-085-对话页一条线的四个契约.md`（A/B/C/D 四个契约 + 9 条裁定）
- `docs/specs/api_v1_rag.md`（对端：`sources` 的 `index` / 末尾 `usage` 帧）· `docs/specs/sse.md`（共享 SSE 层）
- `docs/decisions/DEC-033-上公网路线的两条前置约束.md` 🅱️（**后端先行** —— 前端是本刀才开始的）
- 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-对话页.md`
- 🔴 `docs/decisions/DEC-088-接管页与硬门D的三个缺口.md` + `docs/specs/api_v1_agent.md`（**接管页消费的四条后端接口**：
  `/agent/pending` · `/agent/pending/context` · `/agent/approve` · `/agent/approvals/history`）·
  `docs/specs/approval_audit.md`（**裁决历史那张表**）
- 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-接管页.md`
