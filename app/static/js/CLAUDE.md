# `app/static/js/` —— 前端纯逻辑

> 📇 **一页一 JS**，且纯逻辑**都有 `node --test` 单测**（零 npm 依赖）。

## 📇 本目录索引
| 文件 | 哪一页 | 单测 |
|---|---|---|
| `sse.js` | `chat`（对话页 · SSE 流式） | `sse.test.js` |
| `cost.js` | `cost`（成本看板） | `cost.test.js` |
| `lab.js` | `lab`（检索实验室） | `lab.test.js` |
| `tools.js` | 🆕 `tools`（工具与记忆） | `tools.test.js` |
| `system.js` | 🆕 `system`（系统与执行器） | `system.test.js` |
| `trace.js` | `trace`（轨迹页） | `trace.test.js` |
| `approvals.js` | `approvals`（接管队列） | `approvals.test.js` |
| `panel.js` | 通用面板 | `panel.test.js` |

## 🔴 本层特有的规矩
- 🔴 **每个页面都要有「可点入口」**（最高判据①）—— **⛔ 不许把能力只做在后端**
- 🔴 **⛔ 不加 `package.json` / `npm install`** —— CI 就一条 glob：
  `node --test app/static/js/*.test.js`
  ⚠️ 那条 glob **自带防空跑**（匹配不到文件 ⇒ 红）—— ⛔ 别把守卫删了
- 🔴 **界面里那几条"边界文案"只许有一份**（结构型守卫：数的是**文件**）
- ⚠️ **请求字面量必须以 `/api/v1` 开头**（页面守卫会扫）

## 📍 往上读
- `../CLAUDE.md`（`app/static/`）· `frontend/索引.md` · 仓库根 `CLAUDE.md`
