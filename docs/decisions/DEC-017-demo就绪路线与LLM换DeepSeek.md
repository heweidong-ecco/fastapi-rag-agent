# DEC-017 · Demo/版本就绪路线 · LLM 换 DeepSeek · Agent 七处依赖漂移的修法

- 日期:2026-09-20 · 状态:**已裁决**(业务方逐条口头裁定) · 关联:PR #31 之后的 demo 就绪度工作
- 前置:PR #29/#30/#31 已合并(`a1839cbb` → `f748ef81` → `e1248edb`)

## 一 · 这一轮要回答的问题

业务方提问:「**距离一个产品/demo 还差多少,能不能成 version,要不要发 Releases**」。
先出实证汇报,再逐条裁定。**本 DEC 记录裁定与依据**,不重复汇报正文。

## 二 · 裁决表

| # | 事项 | 备选 | **裁决** | 依据(实测) |
|---|---|---|---|---|
| 1 | **路线** | 只做 A(demo)/ 只做 C(产品) / **A→B 先走** | ✅ **A→B 先走,C 单独排期** | A/B 两档**不需要业务方做大裁决**; C 卡在"哪一代 Agent 是产品版本"(M5 前置裁决) |
| 2 | **LLM 端点** | 继续用阿里百炼 / **换 DeepSeek** | ✅ **换 DeepSeek**(业务方已完成) | `.env` 已指 `https://api.deepseek.com` · `deepseek-v4-flash`;**实测真调通**(返回内容) |
| 3 | **Embedding 额度** | 换 / 保留 | ✅ **保留 DashScope `text-embedding-v2`** | **实测可用** —— 真返回 **1536 维**。⚠️ 口径:只证明"**现在能调通**";**剩余额度 API 不提供,测不出来** |
| 4 | **本地 `v1.0` tag** | 留 / 改名 / **删** | ✅ **删除** | 它是 **2026-07-05 GitLab 时代**的遗留,指向一个**文档提交**,**落后 main 47 个 commit**,且**从未推到远端**(远端 tags = `[]`)。若误推,会在远端造出一个指向 7 月旧代码的 `v1.0` |
| 5 | **版本号语义** | `v1.0` / **`v0.x`** | ✅ **`v0.x`(技术预览)** | `1.0` 隐含"**可依赖**",而本仓**没有一个测得住的数字**支撑它(见 DEC 五·3)。`v0.x` 定位成"**可演示、可评审**"才是诚实的 |
| 6 | **B 档范围** | 带病发版 / **先修 Agent 再发版** / 收窄到 RAG | ✅ **先修 Agent 再发版** | 实测 Agent **三条路径全断**,而 README/仓库描述把 Agent/MCP/记忆当卖点 ⇒ 带病发版 = "形式完备掩盖实质空缺" |
| 7 | **MCP 会话** | **B1**(AsyncExitStack 池化)/ B2(单 task 自开自关)/ B3(换 HTTP transport) | ✅ **B2** | **B1 已证伪** —— 见 §三。B2 **实测可行**(单 task 内 `async with` 全包 → `list_tools` 6 个工具 · `call_tool` 到达服务端) |
| 8 | **审批契约** | **C1**(返回待审批状态)/ C2(auto_approve)/ C3(去掉 HITL) | ✅ **C1** | 端点在"等人工审批"时返回 **200 + 空答案且不告知调用方**,而本仓**明明有配套的 `/agent/approve`** ⇒ 是契约缺陷,不是功能缺失 |
| 9 | **Playwright 浏览器** | 下载 / 降级 playwright / 不处理 | ⚠️ **下不动 —— 见 §四** | `Playwright does not support chromium on mac13`(本机 macOS **13.6**) |

## 三 · 🔴 最重要的一条:**我推荐的 B1 被证伪,而且我做成了回归**

**B1(AsyncExitStack 池化)实现后实测**:

```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
ERROR:    Application startup failed. Exiting.
```

- **根因**:`stdio_client` 基于 **anyio**,其 cancel scope 要求「**进入与退出在同一个 task**」。池化的生命周期**天然跨 task**(启动 task 建 · 请求 task 用 · 归还 task 关)。
- ⚠️ **它比原 bug 更糟**:原来是"应用能跑、只是 MCP 健康检查挂";B1 之后是"**应用根本起不来**"。已**回退**,并如实记录。
- 📌 **附带查明:那个会话池从未生效过** —— `initialize_pool()` **无调用方**(`main.py` 不调,成功启动日志「MCP 会话池已初始化」**0 次**);`release_mcp_session()` / `close_all_sessions()` **零调用方**。
  ⇒ B2 **不是在删功能**,是把**从来没生效、且架构上不可行**的机制拆掉。

**反悔成本**:低。B2 的代价是"每次调用起一个 MCP 子进程";若将来要复用会话,上 **HTTP/SSE transport**(B3)即可 —— 那是独立改动。

## 四 · 本机环境的两条**天花板**(不是代码缺陷)

> 与 2026-09-17 记录的「8GB 装不下 torch ⇒ `mode=accurate/full` 与 rerank 验不了」是**同一类**:
> **挡住的是验证覆盖面,不是产品能力。**

| # | 天花板 | 实测证据 | 影响 |
|---|---|---|---|
| 1 | **8GB 内存 / 4 核** | 2026-09-17 已登记 | `mode=accurate/full` · 重排序**本机验不了** |
| 2 | **macOS 13.6 + Playwright 1.62** | `venv/bin/playwright install chromium` ⇒ **`ERROR: Playwright does not support chromium on mac13`**;本机缓存是 chromium **1228**,而 1.62 要 **1234**;`playwright install --dry-run` 确认要下 1234 | `fetch_webpage` / `screenshot_webpage` **在本机永远 unhealthy**(实测报 `BrowserType.launch: Executable doesn't exist`) |

**处置**:不降级 playwright(依赖改动面大,须业务方另裁);**如实写进 README/部署文档**,并说明"换 macOS ≥14 或降 playwright 即可恢复"。

## 五 · 这一轮修掉的 7 个 bug —— **全是依赖/环境漂移,没有一个是业务逻辑错**

装上的版本都比代码写作时新:`mcp 1.30.0` · `mem0ai 2.0.20` · `qdrant-client 1.19.0` · `playwright 1.62.0`。

| # | 位置 | 根因 |
|---|---|---|
| 1 | `memory_store.py` | mem0 2.x **两层**漂移:**签名**(`user_id`→`filters`、`limit`→`top_k`)**+ 返回形状**(list → `{"results":[…]}`) |
| 2 | `agent_graph_advanced.py` MCP 传输 | `stdio_client` 是 async CM,且 anyio 要求同 task |
| 3 | `api_v1_agent.py` 审批契约 | 停在 `interrupt_before` 时最后一条是**无文字的 AIMessage** |
| 4 | `mcp_tool_factory.py` 参数 | 把 **pydantic 实例**喂 `invoke()`(要 dict) |
| 5 | `agent_graph_advanced.py` MCP 路径 | `"api/mcp_server.py"` **相对 CWD** ⇒ 从 `api/` 起服务时指向不存在的文件 |
| 6 | `browser_tools` 同步 Playwright | **两个入口**:FastAPI 端点 **+ MCP server**(`mcp_server.py:71` 是 async 却同步调 handler) |
| 7 | `get_llm_with_mcp_tools` | mcp 1.30 的 `list_tools()` 返回 **`ListToolsResult`**(列表在 `.tools`),直接遍历得元组 |

**验证**:14 条新用例(`api/test_agent_repairs.py`),**逐条红→绿**;全套离线层 **64 passed / 1 skipped**(基线 50,零回归)。
**端到端**:三条 Agent 路径 **全部 200 且内容正确**;工具健康 **0/6 → 4/6**(剩余 2 个卡 §四·2)。

## 六 · ⚠️ 三条"同一个病,这轮犯了三次"的记录(防止再犯)

| 次 | 现象 | 教训 |
|---|---|---|
| 1 | **B1 推荐错误** —— 实现后让应用启动失败 | 提修法前**必须先验证它在目标约束下可行**(anyio/task 约束是硬约束) |
| 2 | **(a) 第一版是"假修好"** —— 测试 stub 用的是**我以为的**返回形状(list),于是绿了;线上照样 500 | **测试替身必须复刻真实契约**,不能复刻"我以为的契约" |
| 3 | **bug 6 只修了一半** —— 修了 FastAPI 端点,忘了健康检查走 **MCP** 那条 | **修一条路径时必须问:同一个形状还有别的入口吗?** |

> 📌 这三条与本仓已有的 `A2-R11`(「能落痕迹的才能强制」)同源:**教训必须落到代码注释 + 回归测试上**,否则就是文字。

## 七 · 仍未处置(挂账)

| 项 | 说明 |
|---|---|
| 🔴 **`rag_db` 语料是测试垃圾** | demo 检索命中的是「测试文档一」「Python是一门强大的编程语言」(`source` = `test`/`test_docs`)—— 即已登记的那 77 行污染,**且没有真实语料** ⇒ **demo 会当场演出一堆无关内容**。⚠️ 与"清理会改变 `agent-eval-gate` 评测基线"的既有裁决耦合,**须业务方另裁** |
| ⚠️ `timing.total_ms` **名不副实** | 同一响应 `total_ms: 15.41` vs 实际 **2.09s** —— 计时在生成答案**之前**就固定了 |
| ⚠️ `/ready` 未就绪时返回 `"Internal server error"` | 运维会误判成"服务崩了",应说"尚未就绪" |
| ⚠️ **本地 Qdrant 单实例锁** | `mem0_client` 在 `memory_store.py` **模块导入期**就开 `./.mem0/qdrant` ⇒ **app 跑着时 pytest 跑不了**(实测 `Storage folder ... already accessed by another instance`)· **应用不能并发起两份** |
| ⚠️ `agent_graph_advanced.py` 里 `mcp` **import 了两遍** | `:27,28` 与 `:86,87`(旧清理未清干净) |

## 八 · 反悔成本

| 裁决 | 反悔成本 |
|---|---|
| 换 DeepSeek | **极低** —— `LLM_*` 三键本就是环境变量,改回 DashScope 即可(`config.py:51` 已写明切法) |
| 删 `v1.0` tag | **零** —— 它从未推到远端,本地一个 `git tag` 就能重建(但**不建议**) |
| B2(单 task 自开自关) | **低** —— 独立改动,可单独 revert;要复用会话另走 B3(HTTP transport) |
| C1(待审批契约) | **低** —— 只是响应里多 `status` / `pending_tool_calls` 两字段,不破坏既有 `answer` |
| `v0.x` 版本号 | **零** —— 打 tag 前随时可改 |

## 变更记录
- 2026-09-20 建立(承接业务方「距离产品/demo 还差多少」的提问与逐条裁定)。
