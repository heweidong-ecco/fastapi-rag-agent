# `app/static/js/` —— 前端纯逻辑

> 📇 **一页一 JS**，且纯逻辑**都有 `node --test` 单测**（零 npm 依赖）。

## 📇 本目录索引
| 文件 | 哪一页 | 单测 |
|---|---|---|
| `session.js` | 🆕 **共用（8 页）**：访客凭据的**唯一**一份取法（`DEC-143`） | `session.test.js` |
| `cred.js` | 🆕 **共用（8 页）**：页头那块凭据控件 —— 「已自动获得」⇄「自己填」 | `cred.test.js` |
| `sse.js` | `chat`（对话页 · SSE 流式） | `sse.test.js` |
| `cost.js` | `cost`（成本看板） | `cost.test.js` |
| `lab.js` | `lab`（检索实验室） | `lab.test.js` |
| `tools.js` | 🆕 `tools`（工具与记忆） | `tools.test.js` |
| `system.js` | 🆕 `system`（系统与执行器） | `system.test.js` |
| `ops.js` | 🆕 `ops`（运维探针 · **4 条全无参数、⛔ 不许有形参**） | `ops.test.js` |
| `trace.js` | `trace`（轨迹页） | `trace.test.js` |
| `approvals.js` | `approvals`（接管队列） | `approvals.test.js` |
| `panel.js` | 通用面板 | `panel.test.js` |

## 🔴 本层特有的规矩
- 🔴🔴 **每个文件整体包在 IIFE 里，对外⛔ 只许留【一个】全局键**（`RagXxx`）。
  ⚠️ **经典脚本（`<script src>`）的顶层 `function` / `const` 全是全局的** ——
  而 8 个页面**各自也有顶层绑定**（每页都有 `const $ = …`、`const key = …`、`function el(…)`）。
  2026-10-10 实测：`session.js` 顶层写 `function key()` ⇒ 与页面那句顶层 `const key` **撞上**
  ⇒ `SyntaxError: Identifier 'key' has already been declared`
  ⇒ **整段内联脚本一行都不执行，8 个页面全是死的**，而 982 条 pytest + 283 条 node **全绿**。
  ⇒ 现在两份共用文件各包一层 IIFE；**守卫**：两个 `*.test.js` 末条钉「只许漏一个全局」（反证过）。
  📄 复盘 ⇒ `docs/复盘/2026-10-10-页面里那段JS没有任何门会去跑它.md`
- 🔴 **页面里那段【内联】JS 也有门了**（2026-10-10 新立）——
  `app/tests/test_web_pages.py` 会把每页内联的 `<script>` 抽出来过 `node --check`。
  ⚠️ 它只管「**能不能解析**」；逻辑对不对仍归本目录的 `*.test.js` 与各页用例。
  ❗**在这之前，那段代码没有任何判据** —— 写错了没人知道（同上面那份复盘）。
- 🔴 **每个页面都要有「可点入口」**（最高判据①）—— **⛔ 不许把能力只做在后端**
- 🔴 **⛔ 不加 `package.json` / `npm install`** —— CI 就一条 glob：
  `node --test app/static/js/*.test.js`
  ⚠️ 那条 glob **自带防空跑**（匹配不到文件 ⇒ 红）—— ⛔ 别把守卫删了
- 🔴 **界面里那几条"边界文案"只许有一份**（结构型守卫：数的是**文件**）
- ⚠️ **请求字面量必须以 `/api/v1` 开头**（页面守卫会扫）

## 📍 往上读
- `../CLAUDE.md`（`app/static/`）· `frontend-demo/索引.md` · 仓库根 `CLAUDE.md`
