# 代码代际盘点（M5 产出 · 2026-09-15）

> **状态**：已盘点，**待裁决**。本文件只记事实与建议;「留/并/删」的最终决定权在业务方。
> **方法**：3 个只读 agent 分头盘点(Agent 子系统 / RAG+数据层 / 接口·测试·脚本·死代码),业务方侧对关键结论做二次复核。
> **标记**：✅ = 业务方已亲自复核 ｜ ⚠️ = 静态推断,**未实跑验证**。
> **盘点基线**：`main` @ `5f0312e`,工作树干净,未修改任何文件。
>
> **⛔ 本文件不得写入明文凭据** —— 它是 **PUBLIC 仓库**里的文档。发现凭据只记「文件:行号 + 凭据类型」，原文留在代码与 git 历史里，**不要复制进来**。（本文件初版违反了这条，见 `docs/复盘/2026-09-15-为记录漏洞而制造新漏洞.md`）

---

## 0. 先看三条已复核的重大发现

### 🔴 0-1 公开仓库上存在硬编码登录凭据,且**是活的登录路径** ✅

```python
# api/auth.py:87-89  ← 口令原文已脱敏（本文件不得写入明文凭据，见 docs/复盘/）
_users_db = {
    "admin":     "<明文口令 · 原文见 git 历史>",
    "test_user": "<明文口令 · 原文见 git 历史>"
}
# api/auth.py:92-94
def authenticate_user(user_name: str, password: str) -> bool:
    return _users_db.get(user_name) == password
```

已确认 `authenticate_user` 被**真实登录路由**调用:`api/api_v1.py:75`(`POST /auth/login`)。

**风险**:本仓库是 **PUBLIC**。任何人看到该口令即可尝试登录;若部署实例与仓库同名同口令,是直接的账号接管。注意它**不是**"教学死代码" —— 它在请求路径上。

另:`api/config.py:36` `API_KEY = os.getenv("API_KEY", "test-key-123")` 保留了开发默认值,同属一类问题。

### 🔴 0-2 `token_tracker.py` 预算单位错配 → 预算拦截与告警**实际打不到** ✅

```python
# api/token_tracker.py:503-506
budget   = get_user_token_budget(user_name)   # 返回 Token 数(ROLE_TOKEN_BUDGET: 10000/100000)
used_cost = get_daily_usage_cost(user_name)   # 返回「元」(SUM(cost))
remaining = budget - used_cost                # ← Token 数 减 元
```

**已复核**:两个函数的返回单位确实不同(L279 返回 `ROLE_TOKEN_BUDGET`,L520 是 `SUM(cost)`)。
**后果**:剩余额度恒约等于 10000,而单次预估花费约 0.01 ⇒ `cost > remaining` 永不成立,拦截分支与"消耗达 80% 预警"都不会触发。错误信息里还把两者都印成 `¥`,更具误导性。
**性质**:这不是"删代码",是 **bug**,建议优先于 M5 的删除工作处理。

### 🟠 0-3 `locustfile_hybrid.py` 的 Agent 压测**必然 422** ✅

`mcp_agent_chat(question: str, thread_id: str = "default", ...)` 没有 Pydantic body 模型(`api/api_v1_agent.py:349-351`),FastAPI 会把 `question` 当作**必填 query 参数**;而 `locustfile_hybrid.py:83/101/113` 用 `json={...}` 发请求体。
**后果**:占该压测脚本 25% 权重的 Agent 任务(单轮 + 多轮)全部返回 422,压出来的 Agent 数据是假的。
⚠️ 未实跑,但端点签名已核对。

---

## 1. 代码量总表

| 口径 | 文件数 | 行数 |
|---|---|---|
| `api/*.py` 合计 | 53 | **8,294** |
| ├ 业务代码 | 46 | 7,935 |
| └ `test_*.py` | 7 | 359 |
| 根目录 `locustfile*.py` | 3 | 363 |
| `archive/scripts/*.py`(**不入库**) | 6 | 623 |
| `archive/drafts/requirements.in` | 1 | 18 |
| **Python 总计** | **63** | **≈9,280** |

最大文件:`api_v1_rag.py`(858) > `token_tracker.py`(678) > `api_v1_agent.py`(630) > `main.py`(508)。

---

## 2. 代际并存总表

**8 组**,按"同结构与文件存在多种代码"口径归档。

| 组 | 内容 | 规模 | 现状 |
|---|---|---|---|
| **1** | **Agent 图 3 代 + 2 旁支** | **903 行** | 四套**同时挂在线上**,见下 |
| **2** | **检索入口 2 套** | ~380 行 | `hybrid_search.py`(函数式3路线) vs `rag_pipeline.py`(类式可配置);**RRF 算法写了两遍** |
| **3** | **检索接口 5 个端点做同一件事** | — | `pg_search`→`hybrid_search`→`rerank_search`→`rewrite_search`→`/rag/search`,后者是前四者的超集 |
| **4** | **答案生成 Prompt 3 处** | ~40 行 | `answer_with_citations.py` vs `api_v1_rag.py:595-613`(内联复制)vs 普通模式 2 处 |
| **5** | **工具注册 5 件套 + 3 份 `calculator`** | ~320 行 | `calculator` 3 份、`date_today` 2 份、`search` 2 代(DuckDuckGo vs 百炼) |
| **6** | **`redis.Redis()` 实例化 6 份** | — | `cache`/`rate_limiter`/`quota_limiter`/`query_rewriter`/`tool_cache`/`agent_graph_advanced` 各建各的 |
| **7** | **locustfile 3 版** | 363 行 | `locustfile.py`(旧) / `_v2.py`(中) / `_hybrid.py`(最新,文档指定) |
| **8** | **产物层同代际重复** | 131KB + 17KB | `api/ rag-agent-api.postman_collection.json` 与 `archive/artifacts/rag-api-openapi.json` 是**同一次导出**的两份,且都已失效 |

### 组 1 展开:Agent 三代同挂线上(最核心的裁决点)

| 代 | 文件 | 行数 | 入口路由 | 特征 |
|---|---|---|---|---|
| 1 基础 | `agent_graph.py` | 150 | `/agent/langgraph_chat`、`/agent/approve` | 内联工具;**独有人工审批中断点** |
| 1 旁支 | `agent_checkpointer.py` | 117 | `/agent/memory_chat` | 结构照抄第 1 代,换持久化后端 |
| 2 | `agent_graph_advanced.py` | 393 | `/agent/mcp_chat` | **MCP Client** + 会话池 + Redis 缓存 + 预算前置检查 |
| 2 旁支 | `agent_graph_advanced_learning.py` | 357 | `/agent/advanced_chat` | supervisor 意图路由 + 5 子图,工具走本地 handler |
| **5** | *(藏在 `api_v1_rag.py` 内)* | — | `/ws/agent` | LangChain `AgentExecutor` 实现,**第 4 套,盘点规格外发现** |

⚠️ **第 2 代两个文件谁先谁后无法从代码判定**(`advanced.py` 自述"升级版",但 `learning` 版依赖 `mcp_server` 却不用 MCP Client)。需业务方确认或查更早的 git 历史。

---

## 3. 死代码清单

### 3-1 真·死代码,可直接删(判定最确定)

| 位置 | 行数 | 内容 |
|---|---|---|
| `api/rate_limiter.py:123-127` | 5 | `'''...'''` 包着的"原来基础格式"旧实例 |
| `api/agent_graph_advanced_learning.py:216-219` | 4 | `'''...'''` 包着的旧工具执行逻辑(已搬到 `mcp_server`) |
| `api/api_v1_rag.py:577-579 + 611-614` | 7 | `stream_search` 里 `messages` 构造两遍后被 L617 清零重建 |
| **合计** | **16 行** | |

### 3-2 未使用导入:**54 行**,零风险

`api_v1.py` 29 行(该文件已无检索端点,RAG 能力整体搬走后留下的壳) / `api_v1_rag.py` 11 / `api_v1_agent.py` 9 / `token_tracker.py` 3 / `cost_dashboard.py` 2。

### 3-3 错位 docstring:**32 行,建议上移而非删除**

13 处真文档被写在代码之后而失去 docstring 语义(如 `query_rewriter.py:46-48`、`rag_pipeline.py:74-76`、`main.py:469`)。**删掉会丢文档。**

### 3-4 悬空引用

- `api/agent_graph_advanced.py:2` 写"升级版:`api/agent_graph_advanced_1.0.0.py`" —— 该文件**不存在**。
- `api/LEARNING_INDEX.md` 记录 reranker v1/v2/v3 三代,但**三个文件都不存在**。

---

## 4. 「已合并完成」的正面样例 —— reranker

`api/reranker.py`(58 行)= v2(批量)+ v3(单例)的合体,`LEARNING_INDEX.md` 记录的三代版本文件已收敛为一个文件。**这一类无需再动,只留文档证据。** 说明合并路线在本项目是走得通的。

---

## 5. 工作量评估

**口径**:单人、熟悉本项目、含自测与回归。**这是估算,不是承诺。**

| 档 | 内容 | 代码量 | 估时 | 风险 |
|---|---|---|---|---|
| **A** | 零风险纯删(§3-1 死代码 + §3-2 未用导入 + 归档中已被取代的脚本 + 失效产物) | **约 -1,050 行** / -131KB | **0.5 天** | 低,`compileall` CI 可验证 |
| **B** | 三个 🔴🟠 问题修复(§0-1/0-2/0-3) | 小改 | **0.5–1 天** | 低,但需实跑验证 |
| **C** | **组 1 Agent 三代裁决 + 收敛**(先定产品版本,再合并独有能力,其余按 `status: superseded` 归档) | **903 行** | **2–3 天** | **高** —— 决定掉哪些路由 |
| **D** | 组 2/3/5 检索与工具收敛(保留 1 套检索入口、1 份工具实现) | **约 -700 行** | **1–2 天** | 中,需回归检索正确性 |
| **E** | 组 7 locust 合并为 1 版(补回 v2 独有的 SSE 任务 + 修 422) | -225 行 | **0.5 天** | 低 |
| **F** | **M6 单模块完整测试闭环**(选一个模块打通) | — | **1–2 天** | 中,取决于选哪个模块 |
| | **合计(A+B+C+D+E)** | **≈ -2,000 行** | **5–8 天** | 不含 F |

**删完之后**:`api/*.py` 从 8,294 行降至约 **6,300 行**(≈ -24%),且组 1/2/3/5 的重复消失。
**注意**:M5 的产出不只是"变少",而是**每个结构只剩一代 + 一份可读的代际说明** —— 否则三个月后又会重新长出并存的分支。

---

## 6. 建议的裁决顺序(供业务方参考,非决定)

1. **先修 §0 的三个问题** —— 尤其 0-1 的公开凭据,它与"删代码"无关但风险最高。
2. **再做 A 档纯删** —— 零风险,先让仓库瘦一圈,顺带验证 CI 链路。
3. **然后攻组 1(Agent 三代)** —— 这是最大也最难的一块,必须先定"哪个是产品版本"。
4. **组 2/3/5 跟随** —— 检索入口与工具实现收敛,依赖组 1 的选择结果。
5. **M6 单模块测试闭环** —— 建议就选**最终留下的那套 Agent** 或 **`/rag/search`**,因为它们是重构后最需要护栏的地方。

### 裁决格式建议:沿用你现成的 `LEARNING_INDEX.md` 规范

该文件定义的 frontmatter(`version` / `status: active|superseded|deprecated` / `superseded_by` / `key_learning`)正是为这件事设计的。
**实测现状:全仓库 0 个文件使用它**(唯一命中是 `tool_visualizer.py:19` 的 dataclass 字段,非此规范),且该文件**没有任何文件引用**。
建议裁决时直接把被淘汰的文件标上 `status: superseded` + `superseded_by`,**让裁决结果机器可读** —— 而不是又产出一份"写了没人用"的说明。

---

## 7. 明确不确定项(未猜测填充)

1. §0-2、§0-3 的**运行期后果**为静态推断,**未实跑**(未执行 pytest / locust / 未连库)。修复后需实测确认。
2. 组 1 中第 2 代两文件(`advanced` 与 `learning`)的**先后顺序**无法从代码判定。
3. `/rag/jwt_ask`(只 `SELECT content FROM documents LIMIT n`,不检索)是否仍在被调用 —— 仓内有 Postman collection 可作依据,本次未读。
4. `stream_search` 缺少 `WHERE requested_by` 用户隔离(`pg_search` 有)—— **是有意还是 bug,不确定**。
5. `api/document_parser.py` 的 `parse_markdown_to_plain` / `table_to_text` 是否被外部引用 —— 仅 grep 了仓内 `.py`。

---

## 8. 明确建议**不要删**

| 对象 | 原因 |
|---|---|
| `archive/scripts/evaluate_with_ragas.py`(218) + `eval_dataset.json`(37 条) + `ragas_report.json` + `ragas_detailed_report.json` | **全仓唯一的评估链路与唯一的历史评估证据**。ROADMAP M7 写着"RAGAS 复跑";`api/requirements.txt` 里还装着 `ragas`、`datasets`。要删必须先决定是恢复进 `api/` 还是放弃评估能力 |
| `archive/scripts/data_retention.py`(72) | 它是 `api/db.py` 里已建好的 `cost_records_archive` 表(L155)的**唯一操作者**。删了这张表永远是死表 |
| §3-3 的 13 处错位 docstring | 是真文档,位置错了而已 —— 上移,别删 |
| `api/reranker.py` + `api/LEARNING_INDEX.md` | 已合并完成的正面样例,留着当范式 |
