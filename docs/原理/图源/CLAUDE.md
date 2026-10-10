# `docs/原理/图源/` —— 架构图的【源文件】

> 📇 **这里是 `.mmd`（Mermaid 源）** —— 一条命令渲染成 `docs/*.png`。
> ⛔ **不是**"手画一张图贴上去"那种（那种图**必然烂**，见下面规矩 1）。

## 📇 本目录索引

| 源文件 | 出图 | 画的是什么 |
|---|---|---|
| `00-系统总览.mmd` | `docs/architecture.png` | 四层：客户端 → FastAPI 应用 → 存储 → 外部服务 |
| `01-请求流与中间件.mmd` | `docs/request-flow.png` | **中间件顺序陷阱**（执行顺序与源码顺序逐层相反） |
| `02-两条检索链.mmd` | `docs/retrieval-chains.png` | `/rag/search` vs `/rag/stream_search` |
| `03-部署拓扑.mmd` | `docs/deploy-topology.png` | 6 容器 · 3 张网络 · 端口 |
| `mermaid-config.json` | — | 样式（字体 / 颜色 / 换行宽度） |
| `出图.sh` | — | ⭐ **渲染脚本**（就是那条命令） |

## 🔧 怎么重出图（**一条命令**）

```bash
bash docs/原理/图源/出图.sh          # 全部重出
bash docs/原理/图源/出图.sh 02       # 只出文件名含 "02" 的那张
```

**前置**（本机已装）：`mmdc`（mermaid-cli）。装法（**跳过它自带的 Chromium，复用 Playwright 那个**）：

```bash
PUPPETEER_SKIP_DOWNLOAD=true npm i -g @mermaid-js/mermaid-cli
```

⚠️ **脚本会自动探测 Chromium**（先找 Playwright 缓存，再找 `/Applications`）—— ⛔ **别写死版本号**
（Playwright 一升级换了目录名，写死的脚本就**静默跑不了**）。

## 🔴 本层特有的规矩

1. 🔴 **图必须能【一条命令重出】** —— 本仓**有前科**：旧图把工具层画成 `rag_search`，
   而实际是 `fetch_webpage_html`，**烂了很久没人知道**（断链门只查路径存不存在，⛔ **不查图上画得对不对**）。
   ⇒ **改内容 = 改 `.mmd` + 跑 `出图.sh`**，⛔ 不许"直接改 PNG"。
2. 🔴 **出图要对得上代码** —— 内容来源一律 `docs/原理/架构.md`（**那份核过代码**）与 `docker-compose.yml`。
3. 🔴 **图里只放【结构】，说明放 README** —— ⚠️ 这条是踩出来的：
   **节点标签一长，Mermaid 的自动布局就把图撑散**（实测出过 **12.8:1 的横条**和 **0.24 的竖条**，两种都读不了）。
   ⇒ 目标比例 **0.9–1.7**，用 `PIL` 量：`venv/bin/python -c "from PIL import Image; …"`。
4. ⚠️ **排布上踩过的三个坑**（⛔ 别重犯）：
   - **两个子图之间【连边】** ⇒ 被拉成一条横条
   - **父 `TB` + 子图 `direction TB`** ⇒ 子图的 `direction` **被忽略**
   - **`direction` 只在【父 LR + 子图 TB + 子图之间不连边】** 时可靠
5. ⚠️ **`wrappingWidth` 太小会在节点里【断词】**（实测出现过"清洗 · 改写 · 扩 展"）⇒ 现设 **420**。

## 📍 往上读

- `../CLAUDE.md`（`docs/原理/`）· `../../CLAUDE.md`（`docs/`）
