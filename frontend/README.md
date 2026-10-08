# `frontend/` —— 前端落点 ＋ **风格规范**

> 📄 业务方 2026-10-08：「**前端的代码和内容网页放在根目录的 `frontend/` 中，我已经创建好了**」·
> 2026-10-07：「**前端页面风格等下发给你**……**页面用我们自己的就可以**」

| 项 | 内容 |
|---|---|
| **风格稿** | `Knowledge Base Dashboards (Community).fig`（Figma 社区模板 · 2026-09-28 导出 · **8.6 MB**）<br>⛔ **不入库**（见 §五）—— **要留的是下面这套 token，不是那个二进制** |
| **这套 token 的效力** | ✅ **可执行**（直接抄进 CSS）· ⚠️ **它是我按风格稿的方向定的，⛔ 不是从 figma 里逐字导出的**（见 §二） |
| **现状** | 🔴 **页面代码【还不在这个目录】** —— 在 `api/static/`（5 页 + 3 js + 3 test）· 搬迁见 §六 |

---

## 一 · 从风格稿里读到的**方向**（4 条）

| # | 读到什么 | 依据 |
|---|---|---|
| 1 | **左侧固定 sidebar ＋ 右侧卡片网格**（不是上下长滚动） | 缩略图 |
| 2 | **卡片大圆角 ＋ 柔和的低饱和底色** | 内嵌图的采样（§二） |
| 3 | **高饱和多色渐变只做【点缀】**（hero / 强调卡），⛔ 不满屏用 | 最大那张内嵌图（品红→橙→青→蓝） |
| 4 | **亮色 + 暗色两套主题** | 缩略图（左右两组，一浅一深） |

---

## 二 · 🔴 为什么这套 token 是**我定的**、不是 figma 导出的

`.fig` 是 **`fig-kiwi` 二进制**（判据：`head -c 8` ⇒ `fig-kiwi`）。
实测：`strings canvas.fig` **拿不到**图层名、字体名、色值 —— 全是被编码过的。

⇒ **它能给的是"视觉方向"，⛔ 不是"设计 token"。**
⇒ 所以下面这套是**方向的落地版**：色值取自**风格稿内嵌图片的真实采样**（可复算，见判据），
间距/圆角/字号是**按方向定的**。

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
# ⇒ 出 9 个【低饱和浅色】：#d8e2ee #daebf5 #ead2c6 #e0eed7 #eaceda #efd6d2 #f2dbcb #fbe0d5 #f5dcd8
```

---

## 三 · ✅ 设计 token（**直接用这一节**）

```css
:root {
  /* ── 卡片底色：取自风格稿内嵌图采样，低饱和 ── */
  --card-mint:   #e0eed7;
  --card-sky:    #d8e2ee;
  --card-sand:   #ead2c6;
  --card-peach:  #fbe0d5;
  --card-rose:   #eaceda;
  --card-blush:  #efd6d2;

  /* ── 强调渐变：只用于 hero / 单张强调卡 ── */
  --accent-grad: linear-gradient(135deg, #ff2e93 0%, #ff9a5a 35%, #7fd8d8 65%, #2f7bf6 100%);

  /* ── 语义色（⛔ 不跟风格稿走，跟本仓已有的语义走）── */
  --ok:    #2f9e5f;
  --warn:  #c9861a;
  --bad:   #c0392b;
  --info:  #2f7bf6;

  /* ── 圆角 / 间距 ── */
  --r-card: 16px;
  --r-ctl:  10px;
  --r-pill: 999px;
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px;
  --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;

  /* ── 字号 ── */
  --fs-h1: 22px; --fs-h2: 17px; --fs-body: 14px; --fs-cap: 12px;
  --lh-body: 1.65;
}

/* ── 亮色（默认）── */
:root {
  --bg:      #f6f7f9;
  --surface: #ffffff;
  --line:    #e6e8ec;
  --fg:      #1c1f23;
  --fg-dim:  #6b7280;
}
/* ── 暗色：跟随系统；同时留 [data-theme="dark"] 供手动切换 ── */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131417; --surface: #1c1e22; --line: #2a2d33; --fg: #e8eaed; --fg-dim: #9aa0a6;
  }
}
:root[data-theme="dark"] {
  --bg: #131417; --surface: #1c1e22; --line: #2a2d33; --fg: #e8eaed; --fg-dim: #9aa0a6;
}
```

**三条用法规矩**：

1. 🔴 **渐变最多一处** —— 一屏之内只有 hero 或一张强调卡用它。⛔ 不许每张卡都铺渐变
   （风格稿里那是 hero，不是卡片底）。
2. 🔴 **语义色（成功/警告/失败）⛔ 不跟风格稿走** —— 风格稿是 dashboard 模板，没有失败态；
   本仓的熔断卡、拒答、错误提示**必须**用 `--bad` / `--warn`，⛔ 不许用好看的渐变去表示"出错了"。
3. **布局**：`sidebar 220px` 固定 + 右侧 `grid`，卡片 `minmax(280px, 1fr)`，间距 `--sp-4`。

---

## 四 · ⛔ 落地时不许碰的三样

| ⛔ | 为什么 |
|---|---|
| **不许加 `package.json` / npm / 构建链** | 本仓**全仓无构建**，CI 是纯 Python + `node --test`（0 依赖）。加构建链 = 改 CI 的形态 |
| **不许引外网 CDN 的 CSS/JS** | demo 要能在**创空间的容器里离线起**；外网依赖 = 多一个失效点 |
| **⛔ 不许改页面上的【文案口径】** | 例如熔断卡的「这不是故障」、拒答的「资料里没有」—— 那些是**裁过的**（`DEC-090` / `DEC-091`），改样式⛔ 不等于可以改字 |

📌 一句话：**只改"长什么样"，⛔ 不改"说什么"和"怎么发请求"。**

---

## 五 · `.fig` 的处置：**⛔ 不入库**

它 **8.6 MB**、是**别人的社区模板**（⛔ 不是我们的产物）、且解析不出 token ⇒
**要留的是 §三 那套 token 与 §一 的方向**，⛔ 不是这个二进制文件。

⇒ 已在 `.gitignore` 里加 `frontend/*.fig`。
⚠️ **换来的是**：clone 的人**看不到那张预览图** —— 但 §一/§二/§三 已经把**它给的信息**留全了
（与「**探针只留结论**」`DEC-102 §三`同一条道理）。

⛔ **本决定⛔ 不改动**：业务方给的这份稿**仍然是他给的**，只是**留结论不留原件**。

---

## 六 · ⬜ 搬迁：页面代码从 `api/static/` 搬到这里

> ⚠️ **这一节是【计划】，⛔ 还没执行** —— 牵连面见下，**刻意分两步**（先风格、后搬迁）。

**为什么分两步**：风格是**用户价值**；搬迁是**零价值的机械改动**（页面还是那些页面），
但它碰到 15+ 处引用 ⇒ **同时做会让"哪一步改坏了"分不清**。

**牵连面（2026-10-08 核过 · 判据 `grep -rn "api/static\|static/web\|static/js"`）**：

| 类 | 处 |
|---|---|
| 应用装配 | `api/main.py`（`app.mount("/static", …)` + **4 条 302 跳转**） |
| CI | `.github/workflows/ci.yml` 的 `node --test api/static/js/*.test.js`（**glob**，`N18` 加的） |
| 用例（5 份） | `test_chat_page.py` · `test_trace_page.py` · `test_approvals_page.py` · `test_web_pages.py` · `test_frontend_contract.py` |
| spec（4 份） | `static_frontend.md` · `main.md` · `api_v1_agent.md` · `approval_audit.md` |
| 其他 | `ROADMAP.md` 多处 · `scripts/*`（若有） |

⚠️ **`CHANGELOG` / `复盘` / `DEC-*` 里的旧路径⛔ 不改**（历史事实 —— 断了就进断链门的 🟡/⚫ 豁免）。
