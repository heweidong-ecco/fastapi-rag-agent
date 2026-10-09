# `frontend/` —— 前端落点 ＋ **设计系统规范**

> 📄 业务方 2026-10-08：「**前端的代码和内容网页放在根目录的 `frontend/` 中，我已经创建好了**」·
> 2026-10-07：「**前端页面风格等下发给你**……**页面用我们自己的就可以**」·
> 2026-10-08 晚追加：「**风格是一方面，还有排版和组件，分页等等都有吗**」

| 项 | 内容 |
|---|---|
| **风格稿** | `Knowledge Base Dashboards (Community).fig`（Figma 社区模板 · 8.6 MB）<br>⛔ **不入库**（§八）—— **要留的是下面这套规范，不是那个二进制** |
| **效力** | ✅ **可执行** · ⚠️ **是本 Agent 按风格稿的方向定的，⛔ 不是从 figma 里逐字导出的**（§二） |
| 🔴🔴 **找东西先看这份** | ⭐ **`frontend/索引.md`** —— **前端的一切，从这里找**（业务方 2026-10-09：「**以后你要找，就在索引列表文档里面找，不用靠我来记，也不要用 grep 去找，也不准**」） |
| ⭐ **另一份** | 🔴 **`frontend/页面与接口规格.md`** —— **每页放什么 · 打哪些接口 · 各状态显示什么**（**初稿的唯一输入**）。<br>⚠️ **两份分工**：**本文件** = **怎么长**（token/排版/组件/分页/红线）· **那份** = **放什么**（页面 · 接口 · 状态）。 |
| **覆盖** | 风格（§三）· **排版（§四）**· **组件（§五）**· **列表与分页（§六）** · 落地红线（§七） |
| **现状** | 🔴 **页面代码【还不在这个目录】** —— 在 `app/static/`（5 页 + 3 js + 3 test）· 搬迁见 §九 |

---

## 一 · 从风格稿里读到的**方向**（4 条）

| # | 读到什么 | 依据 |
|---|---|---|
| 1 | **左侧固定 sidebar ＋ 右侧卡片网格**（不是上下长滚动） | 缩略图 |
| 2 | **卡片大圆角 ＋ 柔和的低饱和底色** | 内嵌图采样（§二） |
| 3 | **高饱和多色渐变只做【点缀】**（hero / 强调卡），⛔ 不满屏 | 最大那张内嵌图（品红→橙→青→蓝） |
| 4 | **亮 + 暗两套主题** | 缩略图 |

⚠️ 🔴 **但它是 dashboard 模板** —— 它的组件面（**图表 · KPI 卡 · 团队头像墙**）
与**本仓的页面**（对话 / 接管队列 / 执行轨迹 / 成本）**重叠很有限**。
⇒ **⛔ 不照搬它的组件库**：§五 的组件清单是**从本仓页面反推**的，⛔ 不是从那份稿抄的。

> 🔴 **2026-10-09 追加 —— 第 1 条有一个例外：`GET /`（总览首页）** ⛔ **不挂 sidebar**。
> **起因**：首版首页同时挂了侧边栏和正文卡片，而 `/chat` `/approvals` `/trace` `/eval`
> **四个目标在同一页各出现两次** ⇒ 业务方原话「**侧边栏的和主页面有重叠**」
> （⚠️ 不是几何重叠 —— 那没有；是**功能重叠**）。
> **裁定（业务方 2026-10-09 · 甲）**：**首页 = 门户形态**（顶部条 + 居中卡片列，⛔ 无侧边栏）；
> **侧边栏留内页**。依据：落地/门户页用顶部导航，侧边栏是"应用内导航"（Ant Design 口径；
> 另有来源补一条顶在最高判据上的：「**桌面端⛔ 绝不许把导航藏进汉堡菜单** —— 会砍掉约 50% 的功能发现率」）。
> 📄 规格 §3.0「页面形态」那行 · 守卫 `app/tests/test_index_page.py`（`test_no_navigation_target_appears_twice`）。

---

## 二 · 🔴 为什么 token 是**我定的**、不是 figma 导出的

`.fig` 是 **`fig-kiwi` 二进制**（判据：`head -c 8` ⇒ `fig-kiwi`）。
实测：`strings canvas.fig` **拿不到**图层名、字体名、色值 —— 全是被编码过的。

⇒ **它能给的是"视觉方向"，⛔ 不是"设计 token"。**
⇒ 色值取自**风格稿内嵌图片的真实采样**（可复算），间距/圆角/字号**按方向定的**。

📌 **判据（可打印 · 复算采样）**：

```bash
venv/bin/python - <<'PY'
import zipfile, io
from PIL import Image
z = zipfile.ZipFile('frontend/Knowledge Base Dashboards (Community).fig')
ims = sorted([i for i in z.infolist() if i.filename.startswith('images/') and i.file_size > 50000],
             key=lambda i: -i.file_size)
for i in ims[:9]:
    im = Image.open(io.BytesIO(z.read(i.filename))).convert('RGB').resize((1, 1))
    print('#%02x%02x%02x' % im.getpixel((0, 0)))
PY
# ⇒ 9 个低饱和浅色：#d8e2ee #daebf5 #ead2c6 #e0eed7 #eaceda #efd6d2 #f2dbcb #fbe0d5 #f5dcd8
```

---

## 三 · 设计 token（**色 / 圆角 / 间距 / 字号**）

```css
:root {
  /* ── 卡片底色：取自风格稿内嵌图采样，低饱和 ── */
  --card-mint:   #e0eed7;  --card-sky:   #d8e2ee;  --card-sand:  #ead2c6;
  --card-peach:  #fbe0d5;  --card-rose:  #eaceda;  --card-blush: #efd6d2;

  /* ── 强调渐变：只用于 hero / 单张强调卡 ── */
  --accent-grad: linear-gradient(135deg, #ff2e93 0%, #ff9a5a 35%, #7fd8d8 65%, #2f7bf6 100%);

  /* ── 语义色（⛔ 不跟风格稿走，跟本仓已有的语义走）── */
  --ok: #2f9e5f;  --warn: #c9861a;  --bad: #c0392b;  --info: #2f7bf6;

  /* ── 圆角 ── */   --r-card: 16px; --r-ctl: 10px; --r-pill: 999px;
  /* ── 间距（8 的倍数）── */
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;
  /* ── 字号与行高 ── */
  --fs-h1: 22px; --fs-h2: 17px; --fs-h3: 15px; --fs-body: 14px; --fs-cap: 12px;
  --lh-tight: 1.3; --lh-body: 1.65;
  /* ── 布局 ── */ --sidebar-w: 220px; --content-max: 1200px;
}
:root {
  --bg: #f6f7f9; --surface: #ffffff; --line: #e6e8ec; --fg: #1c1f23; --fg-dim: #6b7280;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131417; --surface: #1c1e22; --line: #2a2d33; --fg: #e8eaed; --fg-dim: #9aa0a6;
  }
}
:root[data-theme="dark"] {
  --bg: #131417; --surface: #1c1e22; --line: #2a2d33; --fg: #e8eaed; --fg-dim: #9aa0a6;
}
```

**两条用法规矩**：

1. 🔴 **渐变最多一处/屏** —— 一屏之内只有 hero 或一张强调卡用它。
2. 🔴 **⛔ 不许硬编码颜色** —— 现在 `trace.html` 的 `.card` 写死 `background:#fff` ⇒
   **暗色主题下它就是一块白斑**。⛔ 一律走 `var(--surface)`。

---

## 四 · **排版规则**（原来没有这一节）

| # | 规则 | 为什么 |
|---|---|---|
| 1 | **标题层级只用 3 级**：`h1` 页标题（22）· `h2` 区块（17）· `h3` 卡片标题（15）。⛔ 不许跳级 | 5 页现在的 `<h1>/<h2>` 用法不一 |
| 2 | **正文行宽 ≤ 78 个中文字**（≈ `--content-max`）。聊天消息另算（≤ 62 字） | 太宽读不下去；对话气泡再窄一点更好读 |
| 3 | **正文行高 1.65**（`--lh-body`）· 标题 1.3（`--lh-tight`） | 中文没有词间距，行高要比英文大 |
| 4 | 🔴 **数字必须用等宽字体且右对齐** —— 金额 / token / 耗时 / 百分比 | 现在成本表的数字是**比例字体**⇒ 位数一对不齐，**扫一列数字看不出量级** |
| 5 | **表格行高 36px** · 单元格左右 `--sp-3` · 表头**加粗 + 底色 `--bg`** | 三页表格现在行高不一 |
| 6 | **代码 / 会话 id / 文件名用等宽字体**，且 `word-break: break-all` | thread_id 很长，会撑破布局 |
| 7 | **段落间距只有两档**：段内 `--sp-2`、段间 `--sp-4`。⛔ 不许用 `<br>` 调间距 | |
| 8 | **空态必须解释"为什么空"**，⛔ 不许只显示空白 | ⭐ 本仓已有先例：`trace.js` 的 `emptyTraceReason`（`DEC-093`）—— **那条规矩现在只在一个页面里，要提到规范层** |

---

## 五 · **组件清单**（🔴 **从本仓页面反推**，不是从 figma 抄的）

> **为什么反推**：§一 那条 —— 风格稿是 dashboard 模板，它的组件与本仓页面重叠有限。
> 下面这些是**页面里真实存在的东西**，⛔ 少一个就会在改造时"顺手新造一个"，
> 而新造的那个**又只活在这一个页面里** —— 那就是今天这套三份内联 CSS 的成因。

### 5.1 布局

| 组件 | 用在哪 | 状态 |
|---|---|---|
| `app-shell`（sidebar ＋ main） | chat / approvals / trace | 默认 · **折叠**（窄屏） |
| `page-head`（标题 ＋ 右侧操作区） | 全部 | 默认 |
| `split`（两栏/两轴分屏） | trace | 默认 · 窄屏**改上下** |

### 5.2 容器

| 组件 | 用在哪 | 状态 |
|---|---|---|
| `card` | 全部 | 默认 · **hover**（可点时）· **selected** · **disabled** |
| `panel`（带标题的卡片） | trace 两轴 · approvals 历史 | 默认 · **collapsed** |
| `hero`（唯一允许用 `--accent-grad` 的地方） | chat 首页（可选） | 默认 |

### 5.3 数据展示

| 组件 | 用在哪 | 状态 |
|---|---|---|
| `table` | approvals 队列/历史 · trace 成本 · （将来）列表 | 默认 · **空**（必带解释）· **加载** · **错** |
| `kv`（键值行，今天的 `.k/.v`） | trace · approvals 上下文 | 默认 |
| `badge`（状态徽标） | 待接管/已完成/已拒绝 · 熔断 · 拒答 | **info / ok / warn / bad** 四色 · 小号 |
| `metric`（大数字 + 小标签） | 成本 · token · 达标率 | 默认 · **缺值显 `--`**（⛔ 不显 `0`） |
| `citation-card`（引用卡 · **本仓专有**） | chat | 收起 · **展开** · 无相似度分（⛔ 不许编一个） |

### 5.4 交互

| 组件 | 用在哪 | 状态（🔴 每个都要有，⛔ 不许只做默认态） |
|---|---|---|
| `btn` | 全部 | **primary / secondary / danger / ghost** × 默认 / hover / **禁用** / **加载中** |
| `input` / `textarea` | chat 输入 · approvals 原因 | 默认 / focus / **禁用** / **错误** |
| `select` | approvals 裁决类型 | 同上 |
| `toggle`（展开/收起） | 引用卡 · 上下文 · panel | 收起 / 展开 |
| `list-row`（可点的一行） | chat 会话列表 · approvals 队列行 | 默认 / hover / **选中** |

### 5.5 反馈

| 组件 | 用在哪 | 状态 |
|---|---|---|
| `alert` | 页面级错误 | **error / warn / info** |
| `breaker-card`（熔断卡 · **本仓专有**） | chat（429） | 默认 · ⚠️ **文案是裁过的**（§七） |
| `empty` | 所有列表 | ⭐ **必须带"为什么空"的一句**（§四 第 8 条） |
| `skeleton`（加载占位） | 所有异步区 | 默认 |

> ⚠️ **这张表是"应有"的清单，⛔ 不是"已有"的清单** —— 现在页面上**一个组件的状态全不全，是没核过的**
> （例：`btn` 现在有没有禁用态、`table` 有没有空态文案，都没人查过）。

---

## 六 · **列表与分页** —— 🔴 **现在【完全没有分页】**

**实地核过的现状（2026-10-08）**：

| 查什么 | 结果 |
|---|---|
| 页面里的分页控件 | 🔴 **0 个**（`grep -rniE '分页\|pagination\|offset\|上一页\|下一页'` ⇒ 无命中） |
| 后端列表接口的 `LIMIT/OFFSET` | 🔴 **只有 1 处 `LIMIT`**（`app/routing/api_v1_rag.py:447`），**没有任何 `OFFSET`** |
| 现在怎么处理"多" | **硬截** —— 拉到上限就**不显示后面的**，且**界面上不说明被截了** |

⇒ 🔴 **这是一个真缺口，而且它不只是"样式"**：分页要**接口 + 组件两头**一起动。

### 6.1 要做的话，动哪两头

- **接口层**：列表端点加 `limit` / `offset`（或游标），**并在响应里回一个总数或 `has_more`**
  —— ⛔ 否则界面**画不出"还有没有下一页"**。
- **组件层**：`pagination` 组件（上一页 / 下一页 / 第 N 页 / 总数），状态：
  **首屏**（上一页禁用）· **末屏**（下一页禁用）· **只有一页**（整个控件不显示）· **加载中**。

### 6.1.5 🔴 **更正：本仓【早就有】一处做对的先例**（2026-10-08 核出）

> ⚠️ **本节的初稿写"本仓没有一个列表有分页"—— 那句不准确。** 实查发现：

✅ **`/agent/trace/{thread_id}/cost` 已经是对的**（`app/billing/token_tracker.thread_cost_breakdown`）：
`items` 有 `LIMIT`，但响应同时给 **`truncated`**（`total.count > len(items)`），
且**合计由 SQL 算整条线程**（⛔ 不受 `LIMIT` 影响）⇒ **页面显示 `total`，⛔ 不自己求和**。

⇒ 所以本仓有**两种**都成立的做法，⛔ 不是只有 offset 一种：

| 做法 | 什么时候用 | 先例 |
|---|---|---|
| **A · `offset` 翻页**（`has_more`） | 用户要**一直往下看** | `/agent/approvals/history`（2026-10-08 加的） |
| **B · 截断 + 说出来**（`truncated` + 服务端算合计） | 本来就是**看个汇总**，翻页没意义 | `/agent/trace/{thread_id}/cost` |

🔴 **两条路都行，但【必须说出来】这一半是共同的** —— 而它现在是**门**：

```
venv/bin/python -m pytest app/tests/test_truncation_declared.py -q
```
⇒ **任何收了 `limit` 的端点，响应里必须有 `truncated` 或 `has_more`**；
真要豁免 ⇒ 登记进 `scripts/truncation-exempt.txt` 并**写明理由**。
✅ **反证跑过**：拿掉一个 `truncated` ⇒ 正身红；把 AST 的装饰器规则改歪 ⇒ **防空跑那条红**。

### 6.2 ⛔ 两条红线

1. 🔴 **不许"前端假分页"** —— 一次拉全量、前端切页。数据量一大就是**假的分页**，
   而且它**看起来完全是好的**（本仓立场：`DEC-076` 那族「看着对、其实没做」）。
2. 🔴 **被截断必须【说出来】** —— 若某接口暂时只能硬截，界面要写一行
   「**只显示最近 N 条**」，⛔ 不许静默截断（今天就是这样）。

> ⚠️ **本条（§六）是【规范】，不是【计划】** —— 它属"前端"这一步，**⛔ 还没排进施工**。

---

## 七 · ⛔ 落地时不许碰的三样

| ⛔ | 为什么 |
|---|---|
| **不许加 `package.json` / npm / 构建链** | 本仓**全仓无构建**，CI 是纯 Python + `node --test`（0 依赖） |
| **不许引外网 CDN 的 CSS/JS** | demo 要能在**创空间的容器里离线起**；外网依赖 = 多一个失效点 |
| **⛔ 不许改页面上的【文案口径】** | 熔断卡的「这不是故障」、拒答的「资料里没有」—— 那些是**裁过的**（`DEC-090` / `DEC-091`）。**改样式⛔ 不等于可以改字** |

📌 一句话：**只改"长什么样"，⛔ 不改"说什么"和"怎么发请求"。**

---

## 八 · `.fig` 的处置：**⛔ 不入库**

它 **8.6 MB**、是**别人的社区模板**、且解析不出 token ⇒ **要留的是本文件，⛔ 不是那个二进制**。
已在 `.gitignore` 加 `frontend/*.fig`。
⚠️ **代价认了**：clone 的人看不到那张预览图 —— 但 §一/§二/§三 已把**它给的信息**留全
（与「**探针只留结论**」`DEC-102 §三`同一条道理）。

---

## 九 · ✅ **落点已定：页面⛔ 不搬到这里**（2026-10-08 · `DEC-119`）

> 业务方 2026-10-08 原话：「**这些网页是否要全部移动到 `frontend/` 文件夹下，还是放在原位，
> 你决定就好，定好了具体路径告诉我一声**」 ⇒ **决定权交出来了**，本节是行使它。

> 🔴 **2026-10-09 两次改口径，最终结论：⛔【不搬】** ——
> 业务方先说「**把前端的东西都移动到 `frontend`**」，同日又说「**搬迁不做也可以**」⇒
> 📄 **`DEC-120 §七`**：**落点维持 `app/static/`**（`DEC-119` 的裁定**恢复有效**）。
> ⚠️ **下面 9.1 那张「5 件代价」表【留着】** —— 记的是「**如果将来要搬，得改哪 5 处**」，⛔ 不是待办。
> 🔴 **找代码请先看 `frontend/索引.md`** —— 它第一行就写着代码在哪。

### 9.1 ✅ （现行）**页面留在 `app/static/`；本目录放【规范 · 规格 · 索引】**

**硬技术约束（⛔ 不是偏好）**：

```bash
grep -n -A3 '^  api:' docker-compose.yml     # ⇒ build: context: ./app
grep -n 'COPY . \.' app/Dockerfile           # ⇒ :96
```

**Docker 只能 `COPY` 【构建上下文内】的文件**，而上下文 = **`app/` 一个目录**
⇒ 页面搬到**仓根** `frontend/` 就**进不了镜像** ⇒ 容器起来**页面 404**。

⇒ 要搬，得连着改 5 件：构建上下文 → 仓根 · **新建仓根 `.dockerignore`**（现在**没有**）·
重排 `Dockerfile` 的 `WORKDIR/COPY` · 改 `main.py:783` 的 mount · 改 **15+ 处引用**
（4 跳转 · `ci.yml` glob · 5 个测试 · 4 份 spec）。⚠️ 且 `fastapi-rag-agent:latest` 被
**`agent-eval-gate` 的 harness** 依赖（它**只 run、从不 build**）。
⇒ **风险与"名字更整齐"的收益完全不成比例。**

### 9.2 ✅ 最终路径（业务方要的那一句）

| 放什么 | 在哪 | 进镜像吗 |
|---|---|---|
| **页面 + JS + CSS**（运行时资源） | **`app/static/`** —— `app.css` · `web/*.html` · `js/*.js` | ✅ **随 `app/` 一起进** |
| **设计系统规范**（人读的） | **`frontend/README.md`**（本文件） | ⛔ 不进 |
| **风格稿原件** | `frontend/*.fig`（⛔ gitignored · 见 §八） | ⛔ 不进 |

**一句话**：**这两类的生命周期不同** —— `app/static/` 是"跑起来要用的"，`frontend/` 是"人看的"；
⛔ 不该因为名字像就并到一起。

📄 **完整裁定（含丙/丁两个备选的否决理由与反悔成本）⇒ `docs/decisions/DEC-119-前端落点页面留api-static.md`**

### 9.3 ⬜ 那"前端"这一步还剩什么

* ✅ **规范定了**（§三–§六）· ✅ **共享样式表建了**（`app/static/app.css`）
* ✅ **`chat.html` 接上了**（零结构改动 · 亮暗两套截图验过）
* ⬜ **另外 4 个页面**（`trace` / `approvals` / `eval` / `eval_gate`）**仍是各带内联 `<style>`**
  —— ⚠️ `trace.html` 的 `.card` **硬编码 `#fff`** 就在这一批里修
* ⬜ **分页**（§六）—— 它要**接口 + 组件两头**，⛔ 还没排进施工

---

## 十 · （原「搬迁计划」留档 · ⛔ 已被 §九 取代）

**为什么分两步**：风格/组件是**用户价值**；搬迁是**零价值的机械改动**（页面还是那些页面），
但它碰 15+ 处 ⇒ **同时做会让"哪一步改坏了"分不清**。

**牵连面（2026-10-08 核过 · 判据 `grep -rn "app/static\|static/web\|static/js"`）**：

| 类 | 处 |
|---|---|
| 应用装配 | `app/main.py`（`app.mount("/static", …)` + **4 条 302 跳转**） |
| CI | `.github/workflows/ci.yml` 的 `node --test app/static/js/*.test.js`（**glob** · `N18` 加的） |
| 用例（5 份） | `test_chat_page.py` · `test_trace_page.py` · `test_approvals_page.py` · `test_web_pages.py` · `test_frontend_contract.py` |
| spec（4 份） | `static_frontend.md` · `main.md` · `api_v1_agent.md` · `approval_audit.md` |
| 其他 | `ROADMAP.md` 多处 |

⚠️ **`CHANGELOG` / `复盘` / `DEC-*` 里的旧路径⛔ 不改**（历史事实 —— 进断链门的 🟡/⚫ 豁免）。

---

## 十一 · 🔧 **前端怎么验**（⛔ 别靠"跑过用例了"）

> **为什么单开一节**：本仓前端**没有自动化视觉回归**（无构建、无 npm）。
> ⛔ 所以「用例全绿」**证不了"页面好看 / 没坏"** —— 它只证"路由在、纯函数对"。

| 手段 | 能验什么 | ⛔ 验不了什么 |
|---|---|---|
| `pytest app/test_*page*.py` | 路由在 · 跳转目标在盘上 · 页面里的 URL 带 `/api/v1` | **长什么样** |
| `node --test app/static/js/*.test.js` | 纯逻辑（含 `pagerState` 那 9 条） | 同上 |
| **headless 截图**（本机 Chrome，见 11.1） | **静态渲染**：亮/暗两套 · 布局 · 颜色 | **交互**（登录 / 点 / 翻页 / 真实数据） |
| **Playwright MCP**（✅ 2026-10-09 已装，见 11.3） | 🔴 **交互**：真登录 · 点 · 填表 · 翻页 · 看 console/network | ⚠️ 不是 CI 门（观察是本机、某一刻的） |

### 11.1 headless 截图怎么跑（⛔ 零依赖，只借本机 Chrome）

仓库根起一个**一次性静态服务**（把 `/static/*` 映到 `app/static/*`，与 `app/main.py` 的 mount 同口径）：

```bash
venv/bin/python tmp/serve.py &          # 见本仓 tmp/serve.py（一次性的，⛔ 不进库）
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1400,760 --screenshot=/tmp/shot.png \
  "http://127.0.0.1:8899/static/web/trace.html"
```

⚠️ **要验亮 / 暗两套** ⇒ 先 `sed` 出一个临时副本（在 `<html …>` 里插 `data-theme="light"` 或 `"dark"`）再截。
🔴 **用完立刻删那个副本** —— `app/static/` 下的**任何 `.html`** 都会被 `app/tests/test_web_pages.py`
**当成一个页面**扫（它是"扫目录"型的门，⛔ 不认"这是临时的"）。

### 11.2 🔴 **要验"有数据的页面"，只能喂假数据** —— ⚠️ 但⛔ 不许把假数留在代码里

页面要登录（`X-API-Key`）才渲染主界面 ⇒ headless 截图**只看得见登录态**。
⇒ 想看主界面 ⇒ **临时注入一段 mock**（照 2026-10-09 那次的做法），**截完把临时文件删掉**。

🔴 **⛔ 别把 mock 写进真页面** —— 本仓有前科：`trace.html` 曾印两格「总 Token / 总花费」，
而它们**没有数据源、恒为 `--`**。守卫在 `app/tests/test_trace_page.py`
（`test_page_does_not_print_the_two_dead_overview_cards`）。

### 11.3 Playwright MCP（🔴 **要新开会话才生效** —— MCP 在**会话启动时**加载）

```
claude mcp add playwright -s user -- npx @playwright/mcp@latest --browser chrome
```

* **`-s user`** ⇒ 落在 `~/.claude.json`，⛔ **不写进本仓**（它是**本机工具**，不是项目依赖）
* **`--browser chrome`** ⇒ 用本机已装的 Chrome，⛔ 不用再下 playwright 的浏览器二进制
* ⚠️ 它**不走视觉模型**，走 **accessibility tree**（返回带 `ref` 的元素快照）⇒ 更便宜、更确定
* ⚠️ 代价：默认 **headed**（会弹窗）· token 成本比 CLI 高 · `@playwright/mcp` 还是 0.x
* 📌 验证装没装：`claude mcp list` ⇒ 应见 `playwright: … ✔ Connected`
