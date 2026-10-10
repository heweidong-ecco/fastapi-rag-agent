# `docs/原理/图源/` —— 架构图的【源文件】

> 📇 **这里的 HTML 不是给人看的网页，是【画图的源文件】** —— 用浏览器渲染后截成 PNG，放到 `docs/`。

## 📇 本目录索引

| 源文件 | 出图（PNG） | 画的是什么 |
|---|---|---|
| `00-系统总览.html` | `docs/architecture.png` | 四层：客户端 → FastAPI 应用 → 存储 → 外部服务 |
| `01-请求流与中间件.html` | `docs/request-flow.png` | 一次请求怎么走 + **中间件顺序陷阱** |
| `02-两条检索链.html` | `docs/retrieval-chains.png` | `/rag/search` vs `/rag/stream_search` |
| `03-部署拓扑.html` | `docs/deploy-topology.png` | 6 容器 · 3 张网络 · 端口 |

## 🔴 本层特有的规矩

1. 🔴 **图必须能【再生成】** —— 它是 HTML + CSS，⛔ 不是"手画完就没人会更新"的位图。
   **改内容 ⇒ 改这里的 HTML ⇒ 重出图**（三步见下）。
2. 🔴 **出图要对得上代码** —— 内容来源一律 `docs/原理/架构.md`（**那份核过代码**）与 `docker-compose.yml`。
   ⚠️ 本仓有前科：**旧图把工具层画成 `rag_search`，而实际是 `fetch_webpage_html`** —— 图比文字更容易烂。
3. ⚠️ **⛔ 不要为出图引入新依赖**（不装 graphviz / mermaid CLI）—— 本机只有 `matplotlib` + `PIL`，
   而**截图这条路不需要任何新依赖**（Playwright MCP 已在）。

## 🔧 怎么重出图（三步）

```bash
# ① 起一个【只绑回环】的静态服务（⛔ 别省 --bind）
cd <仓根> && python3 -m http.server 8898 --bind 127.0.0.1 --directory "docs/原理/图源" &
# ② 用 Playwright 打开对应 HTML（file:// 被浏览器挡，必须走 http）
#    · 视口宽度设 1700 · 截图用 fullPage=true · scale=css
# ③ 存到 docs/<对应文件名>.png
```

> ⚠️ **本机出图是【Agent 用 Playwright MCP 做】的**，⛔ 没有 CLI 脚本 —— 因为出图工具是 MCP，
> 不是命令行。要重出 ⇒ 让 Agent 照上面三步做。

## 📍 往上读
- `../CLAUDE.md`（`docs/原理/`）· `../../CLAUDE.md`（`docs/`）
