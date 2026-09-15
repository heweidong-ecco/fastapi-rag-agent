<!--
PR 模板 · fastapi-rag-agent
合并纪律见 ROADMAP.md「当前指针」：**开好 PR 先问业务方「可以合吗」，拿到那句话才合；
Agent 自己开的 PR 不许自合**（依 agent-eval-gate 的 D-23：单人仓里「点合并」是唯一的人工审核位）。

写法：不适用的条目直接删掉，**不要留空模板**；每节都要有实际内容或明确的「不适用」。
-->

## 这个 PR 做了什么

<!-- 一句话说清变更。有对应 DEC / 复盘 / issue 的，把编号写上（本仓 DEC 在 docs/decisions/）。 -->

-

## 一、评估回归

> 本仓是 `agent-eval-gate` 的**被测系统（SUT）**。凡触及 `/rag/*`、`/agent/*` 的
> **响应结构 / 检索模式 / 拒答行为 / 重排序 / 查询改写**，都会改变评测口径。

- [ ] **不影响**评测口径（纯文档 / CI / 测试资产改动）
- [ ] **影响**评测口径 —— 已复跑：<命令 + 结果 + 与基线的对比>
- [ ] 未复跑，原因：<…>（⚠️ 影响口径却不复跑，请在此写清风险与补偿措施）

## 二、是否改 Prompt / 工具 / 记忆

| 类别 | 是否改动 | 位置 |
|---|---|---|
| **Prompt** | 是 / 否 | `api/answer_with_citations.py` · `api/rag_pipeline.py` · `api/query_rewriter.py` |
| **工具** | 是 / 否 | `api/mcp_server.py` · `api/mcp_tool_factory.py` · `api/simple_tools.py` · `api/search_tools.py` |
| **记忆** | 是 / 否 | `api/memory_store.py`（Mem0） |

> **任一为「是」时必须写明改了什么、为什么改。** 这三类直接改变系统对外行为，
> 是评测与线上表现最敏感的面 —— 改而不说，等于让下一个人对着行为变化猜原因。

## 三、观测证据

- [ ] **CI 通过**（`.github/workflows/ci.yml` 只跑 `compileall`，是本仓唯一的自动门槛）
- [ ] **实机验证**：<命令 + 实际输出；没实机跑就不勾>
- [ ] **本机预检**：`python3.10 -m compileall api/ -q` 已过

> ⚠️ 改动涉及 `locustfile*.py` 时注意：**CI 不编译仓库根目录**，漏跑 `py_compile` 则语法错了 CI 照样绿。

## 四、回滚

<!-- 怎么退回去？有无数据/契约副作用（改了 API 契约、有 DB 迁移、动过存量数据）？ -->
