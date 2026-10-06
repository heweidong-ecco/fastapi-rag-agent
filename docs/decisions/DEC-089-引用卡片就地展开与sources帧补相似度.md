# DEC-089 · 引用卡片就地展开 + `sources` 帧补 `similarity`

| 项 | 内容 |
|---|---|
| **日期** | 2026-10-06 |
| **状态** | ✅ 已实施（分支 `feat/hardgate-b-citation-card`） |
| **关掉哪一条** | `docs/待办总表.md` §三·附2 的 **`F8`**（硬门 B 判定三句里的后两句） |
| **上游** | `DEC-085` 契约 A（`sources` 帧形状）· `DEC-088`（收 PR 时自己核出这条）|

---

## 一 · 这条要解决什么

**硬门 B 的判定是【三句】**（⛔ 权威原文 ⇒ `fastapi-rag-agent-TODO待办/通用/四硬门-定义与验收标准.md` 硬门 B）。
段 1 第一刀（`DEC-085`）**只做掉了第一句**：

| # | 判定原文 | 本刀之前 |
|---|---|---|
| ① | 点开**能展开原文片段** | ✅ 流式链上做到了 |
| ② | **再点能跳到原文位置** | ⬜ 卡片是**固定挂在 `#log` 末尾**的旧版，⛔ 不挂在该条回答下面 |
| ③ | **证真**：点开能看到 **chunk id + 相似度分** | ⬜ 卡片只渲染 `[index] source` + `content`，**两个都不显示** |

🔴 **本条的由来值得记一笔**：`F8` **不是**从 `DEC-085` §六 来的 ——
是 `DEC-088` 收 PR 时**我自己核判定原文**发现的漏登记（`ROADMAP` 的 🟡 只按判定的**子集**记了）。
⇒ **同族第 2 次**（第一次见 `docs/复盘/`）。

---

## 二 · ②「再点能跳到原文位置」= 就地展开/收起（业务方 2026-10-06 裁定「甲」）

### 三个方案 + 为什么选甲

| | 做法 | 代价 | 结论 |
|---|---|---|---|
| **甲** | **就近展开/收起** —— 卡片挂在该条回答**下面**，点引用展开、**再点同一条收起**、点另一条换内容 | **零后端变更** | ✅ **选它** |
| 乙 | 加 `GET` 端点取"同一来源的上下文 / 全文"并高亮 | 新端点 + 新契约 | ⛔ |
| 丙 | 独立的文档查看页 | 新页面 + 新路由 | ⛔ |

**为什么甲够用**：判定的原话是「**再点能跳到原文位置**」。
真要做"跳到原文"需要**位置信息**（页码 / 字符偏移 / 段落号），
而 `documents` 表**只有** `id / content / source / embedding / requested_by`（`api/db.py:65-71`）
—— **没有任何位置字段**，也没有"按 id 取全文"的端点。
⇒ 在**没有位置可跳**的前提下，"再点"能给出的最有意义的行为就是**收起**（把视图还回去）。

⚠️ **③ 与 ② 是同一处 DOM 的两个症状**：卡片既然跟着回答走，就应该同时把
`id` / `相似度` 一起画出来（那就顺带把 ③ 做掉了）⇒ 两条一起做，不分刀。

---

## 三 · 后端只动了【两行】

`sources` 帧有 **两个出口**（`DEC-085` 契约 A 的老问题），**两处都要加**：

| 文件 | 改什么 |
|---|---|
| `api/api_v1_rag.py`（流式） | `sources_list.append({...})` 里加 `"similarity": doc.get("similarity")` |
| `api/answer_with_citations.py`（非流式） | 同上，保持两出口**逐字同构** |

🔴 **这个数本来就在手上** —— `api_v1_rag.py:730-735` 建 `contexts` 时已经把 `r[3]`
（`search_similar` 的 `1 - (embedding <=> %s)`）放进去了，**只是没人往帧里放**。
⇒ 不是"新算一个分"，是"把已经算出来的那个发出去"。

### ⚠️ 非流式那条链会**诚实地**给出 `None`

`answer_with_citations.py` 的 `contexts` 来自 `rag_pipeline` 的 RRF 融合结果，
候选字典是 `{"id", "content", "source", "from", "rrf_score"}`
（`api/rag_pipeline.py:218-240`）—— **没有 `similarity`**。
⇒ 那里会取到 `None`，前端画 `—`。
🔴 **⛔ 不许为了"好看"在非流式出口编一个分出来**（同 `DEC-084`：宁可空着不编数）。

---

## 四 · 前端：卡片头与"再点"都抽进 `sse.js`

判定的 ②③ **能写成命令**（本仓立场：写不出命令的，就是还没核过）⇒ 抽进纯逻辑层，
和 `DEC-085` 裁定 #9 同款。**DOM 仍留在 `chat.html`**（手工验）。

| 函数 | 职责 |
|---|---|
| `RagSse.formatSource(src)` | 拼卡片头：`{title: '[i] 来源', meta: 'id=… · 相似度 …'}` |
| `RagSse.toggleOpen(current, clicked)` | 「再点」的三态：没开⇒开 / 点同一条⇒收 / 点另一条⇒换 |

**三条口径**：
1. **缺字段画 `—`**，⛔ 不许把 `undefined` / `NaN` 漏到页面上（非流式链会传 `None` 过来）。
2. ⚠️ **但 `similarity: 0` 与"没有相似度"是两件事** —— 前者画 `0.000`，后者才画 `—`
   （同 `formatCost` 对 `null` 的立场）。
3. **卡片头的格式只许有一份实现** —— `chat.html` 里 ⛔ 不许再拼一遍。
   🔴 **这条有结构型用例钉着**（`sse.test.js`：「相似度」这个字面量在
   `static/js` + `static/web` 里**只能出现在 `sse.js`**）。
   ⚠️ 立这条的理由是本仓原话：**「有结构才执行，只有文字就漏」** —— 本次施工**又验证了一次**：
   我在 `chat.html` 的注释里写了一句「⛔ 不再是…的 DEMO 版」，而 `F8` 的旧判据正好拿
   `grep -n 'DEMO 版'` 当"还没修"的标记 ⇒ **修好了反而被那条 grep 指成"还没修"**。
   ⇒ 已把那句注释改掉，并在 `F8` 行写明新判据。

**DOM 侧（`chat.html`）的改法**：

- `addTurn` 的模板里**每条回答自带一个** `<div class="card" hidden>`（⛔ 不再是全局一个 `#card`）。
- 状态放**元素上**（`turn._openIndex` / `turn._byIndex`）—— ⛔ 不放全局，
  否则连着问两轮时两张卡片会**互相抢同一个状态**。
- `syncCard(turn)` 只按 `_openIndex` 把卡片画成该有的样子（收起 = `hidden`）；
  `toggleCard` 负责算下一个状态（**算的那步走 `RagSse.toggleOpen`**，⛔ 不在 HTML 里重复）。
- `renderAnswer` 末尾调一次 `syncCard` —— 流式期间它会被调很多次，重画后要把"开着哪条"补回去。

---

## 五 · 判据（可打印 · 2026-10-06 实测）

```bash
# ① 纯逻辑
node --test api/static/js/sse.test.js          # ⇒ ℹ tests 23 / pass 23 / fail 0（改前 18）
venv/bin/python -m pytest api/test_frontend_contract.py -q   # ⇒ 10 passed（改前 7）

# ② F8 的旧判据 —— 只有前半条会动
grep -c 'DEMO 版' api/static/web/chat.html      # ⇒ 0（改前 1 ✅ 会动）
grep -c 'chunk\|score\|相似度' api/static/web/chat.html  # ⇒ 0（改前 0 ❌ 不会动）

# ③ 新的、会动的判据
grep -n 'RagSse.formatSource\|RagSse.toggleOpen' api/static/web/chat.html   # ⇒ 非空
grep -c '<div class="card" hidden>' api/static/web/chat.html                 # ⇒ 1
grep -c "id='card'\|getElementById('card')" api/static/web/chat.html         # ⇒ 0（旧的全局卡片没了）

# ④ 全量门
bash scripts/ci-local.sh                        # ⇒ 765 passed, 3 skipped（退出码 0）
```

### 🔴 反证检验（本仓纪律：把结论取反，看命令的输出会不会变）

**旧判据的后半条 `grep -c 'chunk\|score\|相似度'` ⇒ 改前 0、改后 0 —— 它测不出修没修。**
⚠️ 这是**反证检验当场抓出来的**：这条命令从来就不是③的尺子（③ 说的是"卡片画不画"，
而这条 grep 量的是"`chat.html` 源码里有没有那个词" —— 卡片头**本来就该在 `sse.js` 里**，
所以修好之后 `chat.html` 里**依旧不该有**那个词）。⇒ 已换成 §五③ 那三条。

**新守卫 `test_both_sources_exits_have_the_same_key_set` 的活性**（实测，⛔ 不是"应该抓得住"）：

| 步骤 | 命令 | 结果 |
|---|---|---|
| 基线 | `pytest api/test_frontend_contract.py -q`（改动前） | `7 passed` |
| **只改流式出口**、摘掉新守卫 | `-k 'not both_sources_exits'` | **`9 passed, 1 deselected`** ⇒ **一条都不红** |
| 加上新守卫 | `-k 'not both_sources_exits'` 反过来 | **`1 failed, 9 passed`**，报 `Extra items in the left set: 'similarity'` |

⇒ **`answer_with_citations.py` 那句注释（「改一边忘另一边…两边各自的用例都是绿的」）
在 2026-10-05 为止是【真的】，而且【零成本】**。现在它有尺子了。

---

## 六 · 本刀**没做**的（⛔ 别读成"顺手做了"）

- **非流式链没有界面**（`F2`–`F4` 那条线）—— 本刀只保证它的 `sources` 形状**不落后于流式**。
- **「无据拒答」**（`F4`）—— 与引用卡片是两件事。
- **方案 乙 / 丙**（§二）。
- **`api/static/` 下那三个存量坏页**（`stream_test.html` / `trace_viewer.html` /
  `websocket_test.html`）—— ⛔ 本仓纪律：不顺手清理（`DEC-085` §六·4）。
- **DOM 那层仍无自动判据** —— 卡片展开/收起的**像素与滚动**只能手工验
  （本刀未起真实服务：那要花真 token，且需业务方在场）。

## 关联

- `docs/decisions/DEC-085-对话页一条线的四个契约.md`（契约 A：`sources` 帧形状）
- `docs/decisions/DEC-084-流式答案的记账落点.md`（「宁可空着不编数」的同款立场）
- `docs/specs/static_frontend.md`（⚠️ 看代码会误判的地方）· `docs/specs/api_v1_rag.md`（对端）
- `docs/待办总表.md` §三·附2 · **`F8`**
