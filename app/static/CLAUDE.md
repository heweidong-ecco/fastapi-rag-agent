# `app/static/` —— 真前端（静态资源）

> 📇 🔴 **真前端代码在这里，⛔ 不在 `frontend/`** ——
> `frontend/` 里是**设计文档与索引**，代码是这一份。

## 📇 本目录索引
| 条目 | 是什么 |
|---|---|
| `web/` | **8 个页面 html**（`index` · `chat` · `cost` · `lab` · `trace` · `approvals` · `eval` · `websocket_test`） |
| `js/` | 前端 JS（含 **7 份 `*.test.js`**，用 `node --test` 跑，**零 npm 依赖**） |
| `specs/` | 前端的 spec（`static_frontend.md`） |
| `app.css` · `websocket_test.html` | 样式与调试页 |

## 🔴 本层特有的规矩
- 🔴 **每个页面都要有「可点入口」** —— 本仓最高判据①：
  「**95% 的人不会去看代码**……**显示了，才知道你有做**」⇒ **藏进后端 = 等于没做**。
- 🔴 **必须`app.mount("/static", …)` 且路径锚在 `main.py` 旁边**（`os.path.dirname(__file__)`）
  ⇒ ⛔ **`main.py` 搬家会连带这里**。
- ⚠️ **前端的事优先看 `frontend-demo/索引.md`**（业务方立的查找纪律：「**不用靠我来记，也不要用 grep**」）。
- ⚠️ **JS 纯逻辑用 `node --test`**（`app/static/js/*.test.js`），⛔ **不加 `package.json` / `npm install`**
  —— CI 里就是一条 glob + node 自带测试器。

## 📍 往上读
- `../CLAUDE.md`（`app/`）· `frontend-demo/索引.md` · 仓库根 `CLAUDE.md`
