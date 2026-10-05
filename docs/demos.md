# Agent 多任务演示

> ### ⚠️ 演示前必读：**`generate_answer` 与 `citations` 默认都是 `false`**
>
> **不显式打开就只返回 `docs`** —— **不生成答案、更不会有引用**。
> 🔴 **这是最容易在演示时翻车的点**：它看起来像「**这个能力不存在**」，其实是**接口的默认值**。
> ⇒ 要出答案，请求体里必须显式写 `"generate_answer": true`（要引用再加 `"citations": true`）。
>
> 📌 **2026-10-05 从下方 Demo B 的中段提上来**（`docs/待办总表.md` §五·2）。
> **为什么值得占第一屏**：它是一条**「看响应会误判」**的坑 ——
> 曾由它推出过三句全称错断言（「`/rag/ask` 不存在」·「`/rag/search` 不生成答案」·
> 「`/rag/stream_search` 是唯一生成答案的端点」），**根因是拿「响应字段为空」当「能力不存在」**。
> 📄 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`

> 🔴 **2026-09-20 加：下面三个场景是【最初写的规划】** —— 命令是 `curl -X POST "..."` 占位，
> 而 Agent 那三条路径当时**根本跑不通**（1 代空答案 / 2 代 500 / 3 代 500）。
> 当天修通了（7 处依赖漂移 + 2 处既存缺陷，见 `docs/decisions/DEC-017-demo就绪路线与LLM换DeepSeek.md`），
> 但**命令仍是占位**，且 Demo 1 依赖的 `fetch_webpage` **在本机不可用**
> （macOS 13 不支持 Playwright 1.62）。
> ⇒ **要真拍 demo，用下面【实测可跑】那一段，不要照这三个场景的占位命令。**

---

## ✅ 实测可跑（**2026-09-20 现场验过，命令与输出都是真的**）

### 前置

```bash
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
docker compose up -d postgres redis          # 只起 DB/Redis
cd api && ENABLE_DASHBOARD=false ../venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
curl -s localhost:8000/health
# ⇒ {"status":"healthy","checks":{"database":"ok","redis":"ok","embedding_api":"deferred to external monitoring"}}
```

### 取 token

```bash
TOK=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"user_name\":\"$LOGIN_USER_NAME\",\"password\":\"$LOGIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

### Demo A · 混合检索（RRF 真融合）

```bash
curl -s -X POST localhost:8000/api/v1/rag/hybrid_search -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"question":"混合检索是怎么做的","top_k":3}'
```
**实测输出**：`{"method":"hybrid (vector + bm25)","docs":[{…,"rrf_score":0.0782,"from":"vector"}, {…,"from":"both"}]}`
⇒ **`from: "both"` 就是 RRF 确实融合了两路的证据**（不是只有向量路）。

### Demo B · 带引用的答案生成（**旗舰**）

```bash
curl -s -X POST "localhost:8000/api/v1/rag/search?mode=accurate_norerank" \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"question":"混合检索是怎么做的？","top_k":3,"generate_answer":true,"citations":true}'
```
**实测输出**（关键片段）：`answer` 里带 **`[来源:1]`** 行内标注；`sources` 是结构化的
`[{"id":64,"source":"eval_dataset.json#23","content_preview":"…"}]`。
**顺带能演「拒答」**：资料不足时它会说「根据现有资料，无法回答。现有资料仅提到：…」
—— **这是正确行为，不是失败**。

> ⚠️ 关于 **`generate_answer` / `citations` 的默认值** ⇒ 说明已提到**本文档开头**（2026-10-05）。
> ⛔ **别在这儿再写一遍**（本仓 §3.1：一份内容只在一处，其余地方留指针）——
> 连**复述那句结论**都不行：复述会让「默认值只在第一屏」这条判据失效。

### Demo C · 三条 Agent 路径（**2026-09-20 修通**）

| 命令 | 实测 |
|---|---|
| `POST /api/v1/agent/langgraph_chat?question=请计算 6*7` | ✅ 200，**但返回的是待审批状态**：`{"status":"pending_approval","pending_tool_calls":[{"name":"calculator","args":{"expression":"6*7"}}]}` —— 该图带**人工审批节点**，**工具还没执行**；要走 `/agent/approve` 才继续 |
| `POST /api/v1/agent/advanced_chat?question=计算 123*456` | ✅ `{"answer":"56088","intent":"CALCULATOR"}` |
| `POST /api/v1/agent/advanced_chat?question=帮我规划学习 Python 的三步计划` | ✅ **真答案**（Markdown 版三步计划）—— 走 REACT 分支；**此前这里返回的是占位串「处理完成」** |
| `POST /api/v1/agent/mcp_chat?question=1+1等于几` | ✅ `{"answer":"1+1 = **2**。"}` |
| `GET /api/v1/agent/mcp_tools_dynamic` | ✅ 200 · 6 个工具 |

> 🔴 **演示前必看**：`GET /api/v1/agent/tool_health` 会显示 **4/6 healthy** ——
> `fetch_webpage` / `screenshot_webpage` 恒为 unhealthy（**本机 macOS 13.6 不支持
> Playwright 1.62 的 chromium 1234**，是环境天花板，不是代码缺陷）。
> **别在演示时贸然打开这个端点**，或打开前先说明这条。

---

## ⬜ 最初写的三个场景（**命令仍是占位，未据实更新**）

> ⚠️ 保留原样是为了留痕 —— 它们描述的是「**想演什么**」，不是「**现在能演什么**」。
> Demo 1 依赖 `fetch_webpage`（本机不可用）；Demo 2/3 的命令与预期结果**从未实测过**。

## Demo 1：研究型任务
**场景**：帮我研究量子计算的最新进展，生成报告
**命令**：curl -X POST "..." 
**展示能力**：Plan-and-Execute、web_search、fetch_webpage、execute_python
**预期结果**：生成一份包含引用的结构化报告

## Demo 2：数据处理型任务
**场景**：帮我分析销售数据
**命令**：...
**展示能力**：代码生成、安全沙箱执行、错误修复
**预期结果**：计算各产品占比、平均值、极值，给出优化建议

## Demo 3：多轮记忆型任务
**场景**：记住偏好并基于偏好回答
**命令**：...
**展示能力**：Mem0 长期记忆、个性化回答、表格形式输出
**预期结果**：回答自动以表格形式展示，包含代码示例

///////////////////////////////

# Demo 录制演示素材，能让面试官或协作者在无法直接运行系统时，也能直观地看到效果。

推荐的录制方案

方案	工具	适用场景	优点
终端录制	macOS 自带 QuickTime	录制 curl 命令和终端输出	免费、无需安装、操作简单
GIF 录制	GIPHY Capture (免费)	录制简短操作流程	体积小、可直接嵌入 Markdown
全屏录制	OBS Studio (免费)	录制浏览器操作、Swagger UI	功能强大、支持画中画
终端文本录制	asciinema	录制纯终端操作	文本格式、体积极小、可嵌入网页
推荐组合：

Demo 1-2（curl 命令）：用 asciinema 录制终端操作，体积小，可直接嵌入 README。
Demo 3（多轮对话）：用 QuickTime 录制 Swagger UI 操作，展示记忆保持效果。
录制步骤（以 asciinema + QuickTime 为例）

1. 安装 asciinema

bash
brew install asciinema
2. 录制 Demo 1（研究型任务）

bash
# 开始录制
asciinema rec docs/demos/demo1_research.cast

# 执行 Demo 1 的命令
curl -X POST "http://localhost:8000/api/v1/agent/plan_execute?goal=帮我研究2026年量子计算的最新进展，包括重要突破、主要参与公司和未来展望，最后生成一份300字的结构化报告" \
  -H "Authorization: Bearer <你的Token>"

# 结束录制（按 Ctrl+D 或输入 exit）
exit
3. 录制 Demo 2（数据处理任务）

bash
asciinema rec docs/demos/demo2_data_analysis.cast

# 先插入测试数据
curl -X POST "http://localhost:8000/api/v1/rag/insert" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <你的Token>" \
  -d '{"content":"2026年7月销售数据：产品A销售额120万，产品B销售额85万，产品C销售额63万，产品D销售额41万","source":"sales_data"}'

# 让 Agent 分析数据
curl -X POST "http://localhost:8000/api/v1/agent/mcp_chat?question=帮我分析7月的销售数据，计算各产品的占比、平均销售额、最高和最低销售额，并给出优化建议&thread_id=demo-data" \
  -H "Authorization: Bearer <你的Token>"

exit
4. 录制 Demo 3（多轮记忆任务，使用 QuickTime）

由于 Demo 3 需要多轮对话展示记忆效果，建议用 QuickTime 录制 Swagger UI 操作：

打开 QuickTime Player → 文件 → 新建屏幕录制。
打开浏览器，访问 http://localhost:8000/docs。
依次执行 Demo 3 的步骤：添加记忆 → 提问 → 观察回答中的表格格式。
录制完成后，保存为 docs/demos/demo3_memory.mov。
5. 将 asciinema 转为 GIF（可选）

如果需要嵌入 Markdown，可以用 asciicast2gif 转换：

bash
npm install -g asciicast2gif
asciicast2gif docs/demos/demo1_research.cast docs/demos/demo1_research.gif
将 Demo 素材整理到项目文档中

在 docs/demos.md 中增加以下内容：

markdown
# Agent 多任务演示

## Demo 1：研究型任务——量子计算研究报告

**场景：** Agent 自主规划步骤，搜索量子计算最新进展，并生成结构化报告。

**演示视频：**
![Demo 1 演示](demos/demo1_research.gif)

**或查看 asciinema 录制：**
```bash
asciinema play docs/demos/demo1_research.cast
核心步骤：

规划器将任务分解为：搜索新闻 → 筛选关键文章 → 抓取网页 → 整理数据 → 生成报告
Agent 依次调用 web_search、fetch_webpage、execute_python 工具
最终生成包含标题、分类和来源引用的 300 字结构化报告
Demo 2：数据处理型任务——销售数据统计分析

场景： Agent 自主编写 Python 代码，在安全沙箱中执行，分析销售数据。

演示视频：
https://demos/demo2_data_analysis.gif

核心步骤：

用户提供销售数据（产品A/B/C/D 的销售额）
Agent 调用 execute_python，编写代码计算各产品占比、平均销售额、最高/最低销售额
代码在 Docker 沙箱中安全执行
Agent 基于计算结果给出优化建议
Demo 3：多轮记忆型任务——个性化偏好回答

场景： Agent 记住用户的偏好（喜欢表格形式），跨会话保持记忆，并自动以表格形式回答。

演示视频：
查看 Demo 3 视频

核心步骤：

用户通过记忆接口添加偏好："喜欢表格形式展示数据"
用户提问"对比 Python 和 Go 在 Web 开发中的优劣"
Agent 自动检索到用户的偏好记忆
回答以表格形式展示，而非大段文字描述
切换到新对话窗口，偏好记忆仍然生效
text

---

### 录制前的准备清单

-   [ ] 确保 API 服务正在运行（`bash dev.sh`）
-   [ ] 准备好 Token（先登录获取，避免在录制中暴露登录信息）
-   [ ] 清理终端历史（`clear` 命令），让录制画面干净
-   [ ] 调整终端字体大小（建议 14px 以上），保证录制可读
-   [ ] 测试一遍命令，确保不会出错

---

现在你可以开始录制了。录制完成后，把文件放到 `docs/demos/` 目录下，然后在 `demos.md` 中引用它们。这些素材将成为你项目展示中最亮眼的部分。