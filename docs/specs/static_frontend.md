# `api/static/` —— 前端（**本仓第一个没有 `.py` 模块的子系统**）

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用**（2026-10-06 建 · `DEC-085` 段 1 第一刀）—— 对话页一条线通了，**其余三个页面都没做** |
| **对外提供** | `GET /chat` → **302** `/static/web/chat.html`（`api/main.py:531`，**`include_in_schema=False`**）<br>· 页面本体由已挂的 `/static` 托管（零构建、零新服务、零 CORS） |
| **谁在用** | 人（浏览器）。⚠️ **后端不 import 它、没有任何 `.py` 依赖它** —— 这就是本目录此前一直是"没人管"的原因 |

**本刀新增/涉及的 3 个文件**（其余 3 个老页面见 §🟡）：

| 文件 | 行数 | 是什么 |
|---|---:|---|
| `api/static/web/chat.html` | 358 | 对话页：装配层（DOM / fetch / 状态机 / 渲染） |
| `api/static/js/sse.js` | 136 | **纯逻辑**：帧解析 / 引用映射 / 出口判定 / 费用格式 —— ⛔ 不碰 DOM、不发请求 |
| `api/static/js/sse.test.js` | 207 | `node --test` 用例（**18 条**）—— 钉住 `sse.js`<br>⚠️ **数量别抄文档** —— 跑 `node --test api/static/js/sse.test.js`（Task 1–8 期间从 11 涨到 18） |

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

## 🟡 做到哪 / 缺什么

| # | 没做 | 说明 |
|---|---|---|
| 1 | **不显示历史消息** | 后端**没有**"取历史"的公开接口（`DEC-085` 契约 C 只把历史喂给**模型**）。⇒ 切回旧会话时页面给一句实话（`showEmptyLog`），⛔ **不留一块看不出所以然的空白** |
| 2 | **引用卡片固定放在 `#log` 末尾** | ⛔ 不是插在该条回答下面；再点一次就换内容。DEMO 版取舍，不是 bug —— 但**会被读成 bug** |
| 3 | **接管页 / Trace 页改造 / Eval 页** | 全都没做。Trace 页改造的对象是 `api/static/trace_viewer.html`（⚰️ 见下） |
| 4 | **硬门 A / C 的其余前端项** | 本刀只做了"能流、能停" |
| 5 | **R3.2 熔断提示卡片** | 没做 |
| 6 | **DOM 那层没有自动判据** | 滚动 / 按钮态 / 渲染仍靠 DevTools 手工。`sse.js` 覆盖的是**决策**，⛔ 不是**像素** |

### ⚰️ 同目录下三个【存量坏页】—— 本刀**没碰**（本仓：⛔ 不顺手清理）

| 文件 | 什么毛病 |
|---|---|
| `api/static/stream_test.html` | 调**不存在**的 `/api/v1/user/chat_history` |
| `api/static/trace_viewer.html` | `fetch` **不带认证头** ⇒ 现在 401 |
| `api/static/websocket_test.html` | 端点路径写错 + 浏览器 WebSocket **送不了 `X-API-Key` 头**（它自己的注释里就写了） |

> ⇒ ⛔ **别读成"`api/static/` 下都是本刀的东西"**。本刀只动了 `web/chat.html` + `js/`，
> 另外三个是同一批「没记录过、也没人管」的遗留。

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

## 判据（可打印）

```bash
# ① 纯逻辑（自动的，CI 里也有）
node --test api/static/js/sse.test.js        # ⇒ ℹ tests 18 / pass 18 / fail 0（2026-10-06 实测）
venv/bin/python -m pytest api/test_chat_page.py -q   # ⇒ 3 passed（GET /chat 的三条守卫）
#   对端（后端那半，本页消费的契约）——
venv/bin/python -m pytest api/test_frontend_contract.py -q   # ⇒ 7 passed（DEC-085 契约 A/B）
venv/bin/python -m pytest api/test_token_tracker_cost_helpers.py -q   # ⇒ 5 passed（费用行那三个纯函数）

# ② 那条路由
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:8000/chat
#   ⇒ 302 http://127.0.0.1:8000/static/web/chat.html

# ③ ⛔ 写不成命令的三条（手工，2026-10-06 实测过一次）
#   · 硬门 A：Network 里 type = text/event-stream，正文增长时连接未关
#   · 硬门 B：点 [来源:X] ⇒ 卡片里是【全文】（⛔ 不是摘要）
#   · 硬门 C：点「停止」⇒ 请求变 (canceled) + 徽标「已中断」+ 费用行「中断未计费」
```

## 关联

- `docs/decisions/DEC-085-对话页一条线的四个契约.md`（A/B/C/D 四个契约 + 9 条裁定）
- `docs/specs/api_v1_rag.md`（对端：`sources` 的 `index` / 末尾 `usage` 帧）· `docs/specs/sse.md`（共享 SSE 层）
- `docs/decisions/DEC-033-上公网路线的两条前置约束.md` 🅱️（**后端先行** —— 前端是本刀才开始的）
- 施工单 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-对话页.md`
