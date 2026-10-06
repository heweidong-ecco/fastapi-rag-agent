# DEC-088 · 段 1 第二刀：**接管页**，与硬门 D 的三个缺口

| 项 | 内容 |
|---|---|
| **状态** | 🔵 **设计中**（2026-10-06）—— 设计已与业务方过完 **六条裁定**（§一），**⛔ 实现一行未写**<br>施工单由 `writing-plans` **在本份之后**另出 |
| **触发** | `ROADMAP` 的 `⬜ 接管页`（`docs/待办总表.md` §三·附2 的 **`F1`**）—— 它是**唯一一条做完就能把一个 🟡 硬门变 ✅ 的**（业务方 2026-10-06 已按此顺序批准执行）<br>硬门 D 至今 🟡 的理由就是**它的演示/反例里明写含界面** |
| **业务方裁定** | **六条**（§一）。⚠️ 其中 **③④⑤⑥ 四条**是**本份核出缺口之后才出现的新选择**，⛔ 不是开工前就问好的 |
| **类型** | 🆕 第 2 个面向人的页面 · 🆕 一张表 + 一个新端点 · 🔧 **两处既有端点改动**（可见性 · 歧义定位） |
| **落点** | `api/api_v1_agent.py` · `api/pending_approvals.py` · `api/approval_audit.py`（新）· `api/static/web/approvals.html`（新）· `api/static/js/approvals.js`（新）· `api/main.py` · `api/schema.sql` · `scripts/route-auth-baseline.txt` · `docs/specs/` 三份 |
| **判据** | §五 —— 全部**可打印** |

> 📌 **行号基准 = `ffb2c54`**（`#104` 合并后的主干）。
> **定位一律用命令，⛔ 别抄行号** —— 本仓栽过「行号写死 → 一改就变成新的假话」：
> ```bash
> grep -n 'rows = list_pending()' api/api_v1_agent.py              # ⇒ 675
> grep -n 'def list_pending' api/pending_approvals.py              # ⇒ 116
> grep -n 'return \[dict(v) for v in _pending.values()' api/pending_approvals.py   # ⇒ 113（单值比对）
> grep -n 'include_all=get_user_role' api/api_v1_agent.py          # ⇒ 1943（要照抄的那一行）
> grep -n 'Query("default", min_length=1)' api/api_v1_agent.py     # ⇒ 10 处（213/283/689/742/927/981/1098/1164/1480/1564）
> ```

> ⚠️ **本份是「设计」，不是「施工单」** —— 命令级的步骤**另出一份**（`writing-plans` 产出）。

---

## 一 · 六条裁定

| # | 事项 | 裁定 | 备选 / 为什么没选 |
|---|---|---|---|
| **1** | **接管页代表谁操作** | **镜像 `/agent/traces` 的语义** —— 本人默认只看自己的，**admin 看全量**（`api_v1_agent.py:1943` 那一行原样照抄） | ①只给 admin ⇒ 普通用户永远看不到自己那个卡住的会话；②只给本人 ⇒ 与 `pending_approvals.py` 里「**admin 得能批别人的**」那条设计意图相反。**选它的理由**：它与 `/agent/approve` 已有的权限「**本人或 admin**」**完全对齐** —— 现状是「approve 允许的」与「pending 能看到的」两边对不上 |
| **2** | **「完整上下文」完整到什么程度** | **图里的 messages 序列原样给**（`Human`/`AI`/`Tool` 全部，工具返回也是全文），前端默认折叠、可展开 | ①摘要式（最近 N 轮）—— 硬门 D 的证真要「会话**上下文连续**」，而"连续"只有原样序列能证；摘要漏一段 ⇒ 操作员在不知道前因的情况下放行；②先量真实长度再定 —— 要起容器 + 花一次真 LLM 造会话，**收益只是选 A 还是 B，不值一次往返** |
| **3** | **审批留痕落在哪** | **PG 新表 `approval_events`**，照 `budget_intercepts` 那套抄（`schema.sql:127` + `token_tracker.py:815` 的**惰性 `CREATE TABLE IF NOT EXISTS`** + `:824` 写 + `:1859` 读端点） | ①**只在内存**（与待接管队列同生共死）—— 最省，但与「留痕」的本意相反：`MemorySaver` 重启后**图也没了** ⇒ 两边一起消失，事后什么都查不到；②并进现有 `/agent/trace` 轨迹轴 —— 那条轴记的是「工具调用轨迹」，裁决不是一次工具调用，形状对不上 |
| **4** | 🔴 **那个输入框在界面上叫什么** | **如实写**：「**代替模型执行这次工具调用**」 | ①沿用硬门 D 演示里的「改写答案」—— ⛔ 主文案与真实语义不同（见 §二·发现②下的说明）；②本轮只做批/拒不做改写 —— 硬门 D 的**演示原文里明写了「能改写答案」**，拿掉就关不了那扇门，要改验收口径 |
| **5** | **队列怎么刷新** | **轮询 5s**，且仅当 `document.visibilityState === 'visible'` | ①手动刷新按钮 —— 演示里"待处理项自己冒出来"会显得笨；②**SSE** —— 多一条流式端点 + 取消语义 + 那一整族测试，**YAGNI**（队列本来就是进程内的一个 dict） |
| **6** | 🔴 **`thread_id` 撞车怎么办** | **`/agent/pending/context` 与 `/agent/approve` 都加一个【可选】 `owner` 参数**（默认 `None` ⇒ 退回现有行为） | 见 §二·发现④ —— 这是**核出来才知道是个真问题**的。①只给 context 加 ⇒ 留一条裂缝（**上下文打得开、一提交审批却报"对应多条"**），而 admin 接管**正是**硬门 D 要演示的那条路；②都不动 ⇒ 撞车时谁也批不了。⚠️ 也考虑过「下游直接收**拼过的键**」，但那会改掉 `/agent/approve` 现有「收 raw + 反查属主」的语义（`DEC-056` 丙段那条注释与一批用例钉着它）⇒ **改动面更大**，不走 |

---

## 二 · 四个缺口（它们推翻了「`F1` 只差一个页面」）

> 出处：业务方 2026-10-06 问「下一步」，`ROADMAP` 里 `F1` 记的是「🟢 **后端全齐** …… ⇒ **只差一个页面**」。
> ⛔ **那句话是错的。** 下面四条都是**动设计之前核出来的**，判据全部可打印。

### 发现① 上下文**没有任何来源**

硬门 D 的**演示**要求「点开后**能看到完整上下文**」。

- `/agent/pending`（`api_v1_agent.py:658`）的实现是 `rows = list_pending()`，返回的只有登记表那 **7 个字段**：
  `thread_id`（拼过的键）· `raw_thread_id` · `user_name` · `graph` · `tool_calls` · `rounds` · `since`（`pending_approvals.py:79-87`）。
  ⇒ **没有 messages、没有用户问的原话、没有已生成的部分。**
- 全仓也**没有任何端点**暴露某会话的图状态：`aget_state` 只在**端点内部**被用过（`:362` 取答案 · `:790` · `:1205` · `:1612`），⛔ 没开成接口。

### 发现② 审批**零留痕**

硬门 D 的**证真**要求「接管事件有记录（**谁**、何时、为什么）」。

| 三要素 | 现状 |
|---|---|
| **何时** | ✅ `since`（`pending_approvals.py:86`） |
| **为什么** | ✅ `tool_calls`（`:84`） |
| **谁** | 🔴 **没有** —— `grep -rn -i approv api/*.py` 过滤掉测试与注释后，**没有任何** `logger` / `metrics` / `record` / `INSERT` 落点。谁做的裁决、批还是拒、有没有改写，**一处都没记** |

⚠️ 且 `since` 只在**进程内存** ⇒ 重启即空。

### 发现②之附 · 为什么裁定 4 必须「如实写」

**审批点上模型还没有生成答案** —— 它停下的原因是「我要调这个敏感工具」（`tool_calls` 就是这个请求）。
而 `/agent/approve` 的 `edited_answer` 在 `DEC-062` 里的落法是**回填成 `ToolMessage` + 显式 `as_node="tools"`**（`api_v1_agent.py:551`/`:562`，走 `_tool_rulings`，`:173`）。

⇒ **人工写的那段文字，语义上是「这次工具调用的结果」，⛔ 不是「对模型的答案做的改写」。**
硬门 D 演示原文写的「能改写答案」与后端语义**对不上** ⇒ 界面主文案若照抄，就是在写假话。

### 发现③ 🔴 `/agent/pending` **跨用户可见**

- `api_v1_agent.py:675` 是 `rows = list_pending()`；`pending_approvals.py:116` 的 `list_pending()` **一处过滤都没有**。
- 端点的唯一依赖是 `user_name: str = Depends(get_current_user_hybrid)`（`:660`）⇒ **任何登录用户都能看到所有人的待批会话**，含别人的 `tool_calls` 与 `raw_thread_id`。
- **同族的 `N4` 修过、它没跟上**：`/agent/traces`（`:1936-1946`）当时改成「本人默认 · admin 全量（显式一行）」。
- 🔴 **它能活到现在的原因**：`api/test_pending_approvals.py` 与 `api/test_pending_approvals_wiring.py` 里**没有任何属主 / 可见性用例**（`grep -iE 'user\|属主\|owner\|admin\|可见'` ⇒ 空）。

### 发现④ 🔴 `thread_id` 撞车 ⇒ **两个端点都定位不了**

- `thread_id` 的默认值是 **`"default"`，在 10 条 agent 端点上** —— `api_v1_agent.py` 的
  `213 · 283 · 689 · 742 · 927 · 981 · 1098 · 1164 · 1480 · 1564`
  （⚠️ **基准 `ffb2c54` 实测**；跑 `grep -n 'Query("default", min_length=1)' api/api_v1_agent.py` 取现行值 —— ⛔ 别抄这串）。
- `find_by_raw_thread_id`（`pending_approvals.py:113`）是**单值比对** ⇒ 两个用户都不传 `thread_id` ⇒ 队列里两条 `raw_thread_id="default"`。
- ⇒ `/agent/approve` 走 `:495` 那条「**对应多条待审批会话（属主：[…]）**」**拒绝**。
- ⚠️ **而 `/agent/pending` 返回的每一行本来就带着 `user_name`** —— 信息在手上，只是两个下游端点都没收它。

> 🔴 **这四条合起来意味着**：硬门 D 的**判定**（主动停 → 人工回 → 系统续跑）后端确实过了（`DEC-062`），
> 但**演示**（上下文）· **证真**（谁）· **反例**（界面上找不到）**三栏全缺** ⇒ 所以它至今 🟡。

---

## 三 · 交付形状

### 3.1 上下文端点（新）· `GET /agent/pending/context`

**定位逻辑与 `/agent/approve` 同构**（⛔ 不另起一套）：

```
candidates = find_by_raw_thread_id(raw_thread_id)          # pending_approvals.py:100
if owner is not None:                                      # ← 裁定 6（可选参数）
    candidates = [c for c in candidates if c["user_name"] == owner]
  ├─ 0 条   → 拒绝 ·「当前没有等待审批的任务」
  ├─ >1 条  → 拒绝 ·「对应多条待审批会话（属主：…）」
  └─ 1 条   → 归属校验（本人 or admin，照 :505 那条）
              → 取登记的 graph（照 :521 的 GRAPHS 字典，⛔ 不写死）
              → aget_state({"configurable": {"thread_id": sess}})
              → 序列化 messages
```

⚠️ **`owner` 只是【收窄候选】，⛔ 不是授权** —— 传了它**照样**要走下面那条归属校验。
（给了 `owner` 却一条都不匹配 ⇒ 落在「0 条」那支。）

**返回**：`messages`（完整序列，每条带 `type` / `content` / `tool_calls` / `name` / `tool_call_id`）
+ `next`（图停在哪一步）+ `graph` + `owner` + `rounds`。

⚠️ **两处要防御的**：① `content` **可能是 list**（多模态消息）⇒ ⛔ 别假定是 `str`；
② `0 条` 用 **200 + `{"status":"error", …}`**，⛔ **不改成 404** —— 与 `/agent/approve` 一致比"我认为更规范"重要。

### 3.2 留痕（新表 + 读端点）

```sql
CREATE TABLE IF NOT EXISTS approval_events (
    id            serial,
    owner         text NOT NULL,   -- 属主（会话是谁的）
    actor         text NOT NULL,   -- 谁做的裁决   ⚠️ 两个身份，⛔ 不是一个
    raw_thread_id text,
    graph         text,
    decision      text NOT NULL,   -- 'approved' / 'rejected'
    edited        boolean NOT NULL,-- 有没有代替模型给结论
    rounds        integer,         -- 第几轮停在审批点
    reason        text,            -- 「为什么」= 待批的 tool_calls 摘要
    created_at    timestamptz DEFAULT CURRENT_TIMESTAMP
);
```

- 模块：**`api/approval_audit.py`（新）** —— 惰性建表 + 写 + 读，一处一职责。
  ⚠️ **为什么不塞进 `pending_approvals.py`**：那个模块的 docstring 全篇在论证「**为什么必须是内存**」，
  往里加 PG 写会把它变成"两种存储各说一半"的模块。
- **记哪些出口**：**只记"真的做出了一次裁决"**（`approved` / `rejected`，含 `forced_finish=True` 那次）。
  ⛔ **不记"根本没批成"的三条**（没有可待批任务 / 歧义 / 无权限）—— 那不是裁决事件，见 §六。
- 读端点：`GET /agent/approvals/history` —— **页面下半栏就读它**，它就是硬门 D 证真那栏的可视证据。

### 3.3 页面（新）· `api/static/web/approvals.html` + `GET /approvals` → 302

照 `api/main.py:531` 那条（`@app.get("/chat", include_in_schema=False)` → 302）与 `chat.html` 的整套模式：
`X-API-Key` 从 `localStorage` · **零构建** · 纯逻辑抽 `api/static/js/approvals.js`（`node --test`）。

| 区 | 内容 |
|---|---|
| **上 · 待接管列表** | `GET /agent/pending`，每条：`属主 · 哪张图 · 第几轮 · 卡了多久 · 待批的工具名`（末项即「为什么」的摘要） |
| **点开** | `GET /agent/pending/context` → **完整消息序列**（`Human`/`AI`/`Tool` 分色，默认折叠） |
| **操作区** | `批准` / `拒绝` / 输入框 —— 标题照**裁定 4** 写：「**代替模型执行这次工具调用**」，副文案说明"它拿着你给的结论继续答" |
| **下 · 裁决历史** | `GET /agent/approvals/history` —— **证真的可视部分** |
| **刷新** | 照**裁定 5**：轮询 5s + 仅可见时 |

### 3.4 顺手修的两处既有端点（⛔ 不属于 `F1` 本身）

| | 改动 | 落点 |
|---|---|---|
| **③** | `/agent/pending` 加 `include_all`，照 `:1943` 那一行 | `api_v1_agent.py:658` |
| **④** | `/agent/pending/context` 与 `/agent/approve` 各加**可选** `owner`（默认 `None` ⇒ 退回现有行为） | `:436` 与 3.1 |

⚠️ **两条都是"改既有端点"** ⇒ 按 `DEC-051` 夹在 PR `#73` 里的先例：**同 PR、正文里单独标明它们不属于 `F1`**。

---

## 四 · 备选与为什么没选

| 方案 | 内容 | 为什么不选 |
|---|---|---|
| **乙** | 入队时把**上下文快照**存进登记表 | 快照会**过期** —— `DEC-062` 的「放行后又停 ⇒ 重新入队」会让快照停在上一轮；列表每行带全文 ⇒ 重；**存了第二份真相**（本仓刚在 `DEC-047` 栽过「两处口径」） |
| **丙** | 做一个**通用**的 `GET /agent/session/{thread_id}`（不绑 pending） | **YAGNI** —— 要单独定义「谁能看哪个会话」这条权限面，而本轮只有接管页一个消费者。将来 Trace 页要时再抽 |
| **页面用框架** | React / Vue | 本仓**无 `package.json`、无构建**，CI 是纯 Python ⇒ 要么加构建链、要么进 CDN（外网依赖）。已有一族先例：`api/static/` 下 3 个原生页 + `chat.html` |

---

## 五 · 判据（可打印）

> ⚠️ **全部要在实现完成、且跑过之后才填数** —— 本份是设计，下面留的是**命令形状**。

```bash
# ① 上下文端点（离线 · 假图）
venv/bin/python -m pytest api/test_pending_context.py -q
#   · 找不到 ⇒ 拒绝（⛔ 不是 404）
#   · 歧义 ⇒ 拒绝            · 给了 owner ⇒ 不再歧义（裁定 6 的正面）
#   · 非属主且非 admin ⇒ 拒绝（反面：属主本人 / admin 各一条正面控制）
#   · content 是 list 的多模态消息 ⇒ 序列化不炸（防御，不是 happy path）

# ② 留痕
venv/bin/python -m pytest api/test_approval_events.py -q          # 假 pg · 出口覆盖
POSTGRES_DB=rag_test venv/bin/python -m pytest api/test_approval_events_db.py -q   # 真写入

# ③ 页面契约（照 api/test_chat_page.py 的 3 条：重定向 / 目标文件在盘上 / 不进 OpenAPI）
venv/bin/python -m pytest api/test_approvals_page.py -q

# ④ 前端纯逻辑
node --test api/static/js/approvals.test.js

# ⑤ 顺手修的两处（③ 的可见性**此前一条用例都没有**）
venv/bin/python -m pytest api/test_pending_approvals.py api/test_approve_ownership.py -q

# ⑥ 全量（⭐ CI 等价物，⛔ 别拿裸 pytest 顶替）
bash scripts/ci-local.sh
venv/bin/python scripts/check_route_auth.py --baseline      # 新公开路由 ⇒ 必须显式改基线
```

---

## 六 · 本份【没有】解决什么

1. ⛔ **`F2`–`F8` 全部不动** —— Trace 页改造 · Eval 页（前置 `B14`）· 无据拒答 · 熔断卡片 · 两个存量坏页 · `?thread_id=` 空串残余 2 条 · 取消补不上 token · 硬门 B 残余。
2. ⛔ **待接管队列仍然是【进程内存】**（`pending_approvals.py:24`）—— 本份**没有**改它。
   ⚠️ **本份之后，那个模块里第一次出现"两种寿命不一样的东西"**：队列重启即空，而**留痕在 PG 里活着**
   ⇒ 重启后「历史查得到、会话找不到」是**预期行为，⛔ 不是 bug**（`warn_if_backend_mismatch()` 那条警告管的是另一件事）。
3. ⛔ **「越权审批的尝试」不记** —— 裁定 3 只记**裁决**。不记「没有可批任务 / 歧义 / 无权限」那三条。
   ⚠️ **代价认了**：一条"谁试图批别人的会话"的审计线索**不存在**。要它得另定**保留期与读取权限**，属另一件事。
4. ⛔ **`/agent/approve` 的 raw 语义不动** —— 裁定 6 加的是**可选参数**，⛔ 不是把定位改成"收拼过的键"。
5. ⛔ **不做 SSE 推送**（裁定 5）。
6. ⚠️ **硬门 D 能不能因此翻成 ✅，本份不下结论** —— 那要走它的**验收原文**（`fastapi-rag-agent-TODO待办/通用/四硬门-定义与验收标准.md` 硬门 D 四栏）逐条对，⛔ 不是"页面写完了就 ✅"。
