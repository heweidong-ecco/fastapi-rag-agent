# 决策记录：DEC-073 · **关闭 RAG 侧【不记账】的 LLM 通路**

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施**（2026-10-05）—— 待提交 / 待合 |
| **触发** | `③` Task 6（`B3`）核出、**当时有意没做**（`DEC-053` §遗留·2）⇒ 2026-10-05 业务方选「**非流式三条全做**」 |
| **类型** | 🔴 **修缺陷**（RAG 侧的计费 / 配额漏网）—— 与 `DEC-072` **同型** |
| **落点** | `api/query_rewriter.py` · `api/rag_pipeline.py` · `api/hybrid_search.py` · `api/answer_with_citations.py` · `api/api_v1_rag.py` |
| **范围裁定（业务方）** | 「**非流式三条全做**」—— 含身份透传 + 补闸 + 记账；⛔ **不含** `/rag/stream_search`（见 §五） |
| **判据** | `api/test_rag_billing_wiring.py`（**19 条** · AST 形状 + 假对象行为） |

---

## 一 · 病：RAG 侧**每个成功的请求都在免费跑**

```bash
grep -c 'record_usage\|record_from_response' api/api_v1_rag.py api/rag_pipeline.py api/answer_with_citations.py
#   ⇒ 0 / 0 / 0        ⛔ RAG 侧一处都不记账
grep -n 'check_session_token_budget\|circuit' api/api_v1_rag.py
#   ⇒ **改动前**只有 3 处：:23(import) · :620(/rag/stream_search) · :861(/ws/agent)
#   ⚠️ 上面两个行号是【当时】的值；本轮在本文件上半部插入了约 26 行 ⇒
#      现在同样的两处是 :646 / :887（改动后的完整清单见「判据」节）
```

⇒ 端点上的 **B8 会话上限** / **B11 全站熔断**读的计数器，RAG 链**从不写**
⇒ **对 RAG 链等于不存在**。真库佐证（`B3` 当时记的）：`token_usage_logs` 里
非 embedding 行**全库只有 6 行**，全是 2026-09-20 的 agent graph 运行。

> 与 `DEC-072` 的措辞**同型**：那边是「**门在，锁坏了**」——
> 门挂在正确的位置，**门后面的计量表没接上**。

### 逐条清点（改动前）

| # | 通路 | 何时真调 LLM | 预算闸 | 记账 |
|---|---|---|---|---|
| 1 | `/rag/search` 的**答案生成** | `generate_answer=true` | ⛔ **无** | ⛔ **无** |
| 2 | `/rag/search` 的**改写/扩展** | `mode ∈ accurate / accurate_norerank / full`（**默认 `accurate_norerank` 就开**） | ⛔ **无** | ⛔ **无** |
| 3 | `/rag/rewrite_search` | **无条件** | ⛔ **无** | ⛔ **无** |
| 4 | `/rag/stream_search` 的流式答案 | 无条件 | ✅ `:620` | ⛔ **无** |
| 5 | `query_rewriter` 的两个函数（2 与 3 的底座） | —— | ⛔ **无** | ⛔ **无** |

⚠️ **不在清单内的**：`/rag/hybrid_search` · `/rag/rerank_search` —— 已核，**只跑本地
embedding / Cross-Encoder**，不花 LLM 钱。⛔ 别顺手给它们加闸。

### ⚠️ 顺带更正 `docs/待办总表.md` 的一处

那条红块记的是「**四条**路径」，其中 **`/rag/jwt_ask` 已于 2026-10-04 删除**
（`DEC-064`）⇒ 现行清单是 **3 条端点 + 1 个内部模块**，不是 4 条。已在本轮一并更正。

---

## 二 · 最刺眼的一处：`query_rewriter.py` 的「接了一半」

```bash
grep -n 'record_usage' api/query_rewriter.py     # 改动前 ⇒ 只有 :78 一行
#   ⇒ `from token_tracker import record_usage  # Token统计模块`
#   而全文件【一次都没调用过它】
```

**当初显然打算记，import 写了，调用没写。** 而**接口一切正常** ——
这也是本仓「**门挂在别处，就等于没有门**」那一族的又一例。
同族前科：`DEC-051`（一个名字两个来源，静默漂移）。

---

## 三 · 两个**必须**用对的技术点

### 3.1 `record_usage` ⛔ 不是 `record_from_response`

| 入口 | 判据 | 对裸 `openai.OpenAI` 的响应 |
|---|---|---|
| `record_usage(model, prompt_tokens, completion_tokens, …)` | 直接吃参数 | ✅ **能用** |
| `record_from_response(llm_obj, response, …)` | **`usage_metadata`**（`DEC-072`） | ⛔ **恒返回 `False`，静默跳过** |

`query_rewriter` 是**全仓唯一**用裸 `openai.OpenAI` 的地方（另 15 处走
`llm_factory.make_llm` ⇒ `ChatOpenAI`）⇒ 它的响应只有 **`.usage`**，**没有 `usage_metadata`**。

⇒ 用错入口**比不记账更坏**：它看起来"接了记账"，测试还能全绿，而**账本依旧少一笔**。
📌 守卫：`test_query_rewriter_uses_record_usage_not_record_from_response`

### 3.2 `StrOutputParser` 是 `usage` 的坟墓

答案生成原有的两条分支都是 `PROMPT | llm | StrOutputParser()`。
`StrOutputParser` 把 `AIMessage` **剥成 `str`** ⇒ `usage_metadata` **随之丢光**
⇒ `record_from_response` 静默跳过。

⇒ 两条分支都改成**直调 `llm.invoke(messages)`**，取消息本体：
- `api/answer_with_citations.py:66`（引用分支）
- `api/rag_pipeline.py:206`（普通分支）

---

## 四 · 身份怎么到得了记账点（**已有一条现成的路**）

`DEC-056` 已经给两条管线加了**必填** `user_id`：

```
rag_pipeline.search_async(..., *, user_id)                  # :58（形参在 :67）
hybrid_search.hybrid_search_with_rewrite(..., *, user_id)    # :113（形参在 :118）
```

⇒ **本轮不需要从端点新拉一条透传链**，只是把它**继续往下递一层**：
4 个调用点各加 `user_name=user_id`。

`query_rewriter` 的两个函数**加必填 keyword `user_name`** ——
⛔ **不给默认值**：给了就等于允许「静默记成 `"unknown"`」= **假记账**
（`DEC-072` 把这个形态**明文列为反例**）。漏传 = `TypeError`，**响亮**而不是静默降级。

> 这与 `DEC-056` 加必填 `user_id` 是**同一个取向**，代价也一样：
> 4 个调用点 + `api/test_rag_search.py` 里两个测试桩要跟着改签名
> （改测试桩 ✅ 允许；**⛔ 不许为了迁就桩把真签名的必填改掉**）。

---

## 五 · ⛔ 为什么 `/rag/stream_search` 不在本轮

它**成功路径也记不了**：`llm_factory` **没开 `stream_usage`** ⇒ `ChatOpenAI` 对
`astream` **根本不挂 `usage_metadata`**（`DEC-053` §遗留·2 已把这条边界写死）。
要记它得**顺带开 `stream_usage`** ⇒ 会改**流式帧的形态** = **行为变更**
⇒ 与"补记账"是两件事，**单独一轮**。

⚠️ **取消场景**（用户中途点停止）**补不了** —— usage 只在最后一帧回来，提前 `aclose()`
⇒ 那帧永远不到。硬补只能估算 = **往账本写假数**。这条边界**不因本轮而改变**。

---

## 六 · 备选方案（⛔ 都没采纳）

| # | 方案 | 为什么否 |
|---|---|---|
| A | `user_name` 给默认值 `"unknown"` | ⛔ **假记账** —— 账记上了但归不到任何人头上，配额照样拦不住具体的人。`DEC-072` 明文反例。 |
| B | 只补闸、不记账 | 闸读了计数器，而计数器**依旧没人写** ⇒ 闸**恒不触发** = 白加。 |
| C | 端点层记一次总账，不进屋管线 | 端点**看不到**管线内部的 usage（`search_async` 只回 `answer` 文本）⇒ 要么瞎估、要么把 usage 一路返回（比直传身份**改得更多**）。 |
| D | 本轮连 `/rag/stream_search` 一起做 | 需同时开 `stream_usage`（行为变更）⇒ 混进同一批会让"记账修复"和"流式帧变更"**无法分别回滚**。 |

---

## 七 · 代价与反悔成本

**代价**
- **行为变更**：`/rag/search` 与 `/rag/rewrite_search` **从无闸变成有闸** ——
  超预算的请求现在会被**拒**（`QUOTA_EXCEEDED`）。⚠️ 与本仓 `B10`/`B11` 的
  **fail-open** 取向一致：**DB 挂了仍放行**。
- **签名变更**：`rewrite_query` / `expand_query` / `generate_answer_with_citations`
  三个函数有**必填** keyword ⇒ 任何漏传的调用方**当场 `TypeError`**。
  ⚠️ 已全仓扫过：`grep -rn 'rewrite_query(\|expand_query(' --include='*.py' .`
  ⇒ 真调用点只有 4 个，**全部已传**。
- `purpose` 新增一个取值 `"query_expand"`（`purpose` 是 `TEXT NOT NULL`，
  **无枚举约束** ⇒ 不破坏任何约束；见 `api/db.py:114`）。

**反悔成本**：**低**。回滚 = 撤掉这几处记账调用 + 把三个必填 keyword 还原。
⛔ **但"闸"那两处回滚要单独想** —— 去掉闸会让端点重新变成无上限。

---

## 八 · 判据（可打印）

```bash
venv/bin/python -m pytest api/test_rag_billing_wiring.py -q      # ⇒ 19 passed
bash scripts/ci-local.sh                                          # ⇒ 563 passed, 3 skipped, 31 deselected, 0 failed
```

**基线在 base commit 实测**（⛔ 不抄中间提交的数）：

| | passed |
|---|---:|
| 开工那天的 `origin/main`（`3f37e28`） | **540** |
| ⇒ 同日 `#95` 合入后（`503fa19`，**现在是本轮的 base**） | **544** |
| 本轮之后 | **563** |
| 差 | **+19** = 恰为本轮新增用例数 ⇒ **零回归** |

⚠️ **基线这两个数别混**：本轮**中途** `#95`（`DEC-062`）合进了 main，它自带 4 条用例
⇒ base **540 → 544**。**这与我改的东西无关**（两批文件只有 `CHANGELOG.md` / `待办总表.md` 重叠）。

⚠️ **开工时记的中间值（552）是【旧 base 上的】**，⛔ **别拿它当现在的数** ——
落后 base 一个 `#95` ⇒ 会把「别人的 4 条」算成我的增量。

### 🔴 四条新守卫**逐条自证能红**（临时改坏 → 红 → 还原，逐字节核过）

| 守卫 | 怎么改坏 | 结果 |
|---|---|---|
| `test_every_rag_llm_site_bills` | 把 `expand_query` 的记账改名 | ✅ 1 failed |
| `test_no_llm_usage_is_swallowed_by_string_output_parser` | 把 `StrOutputParser` 接回去 | ✅ 1 failed |
| `test_query_rewriter_uses_record_usage_not_record_from_response` | 换成错的那个入口 | ✅ 1 failed |
| `test_rag_endpoints_gate_both_session_and_global` | 摘掉 `unified_search` 的 B8 | ✅ 1 failed |

### ⭐ 自证救回一条【假守卫】—— 记在这里，因为它是本条最有价值的副产品

`test_no_llm_usage_is_swallowed_by_string_output_parser` **第一版挂在
`_innermost_llm_functions()` 上**（即"先认出 LLM 调用，再看它内部有没有 `StrOutputParser`"）。
自证时**它不红**：改坏的形态是 `(PROMPT | llm | StrOutputParser()).invoke(...)`，
这里的 `f.value` 是个 **`BinOp`**（`|` 链）⇒ `_is_rag_llm_call` **认不出它是 LLM 调用**
⇒ 那个函数根本没进循环 ⇒ 断言**空转通过**。

> 这正是本仓 `DEC-066`「**守卫的形状盲区**」那一族：
> **守卫的判据建立在"能先认出调用"之上 ⇒ 认不出的形态它一律放过。**
> ⇒ 已改成「这份文件里**不许出现** `StrOutputParser()` 调用」，**不依赖任何前置识别**。

⚠️ **它一开始就绿**（写在实现之后）—— **只有自证能发现它**。
⇒ 本仓纪律「**写在实现之后的测试第一遍就绿是假信号**」在这条上**真兑现了一次**。

---

## 九 · 遗留（⛔ 本轮没做）

1. **`/rag/stream_search` 的流式答案记账** —— 见 §五，需单独一轮（含 `stream_usage`）。
2. **`api/rag_pipeline.py` 没有 spec** —— 本轮改了它 3 处，但建 spec 是另一件事。
3. **`rewrite_search_api` 没把 `conversation_history` 传下去** ——
   `api/api_v1_rag.py:488` 是 `hybrid_search_with_rewrite(req.question, req.top_k, user_id=user_name)`，
   **第三位那个 `conversation_history` 一个字都没传**（`QuestionRequest` 里也没有这个字段）；
   改写消解指代**靠的正是历史**，不传 = **改写质量静默变差**。
   ⚠️ 本轮**顺带核出**，按「非必要的不要做」**没改**，已登记 `docs/待办总表.md`。
4. **`api/evaluate_with_ragas.py:144`** 也有一条 `… | eval_llm | StrOutputParser()` ——
   它是**离线评测脚本**（有 `__main__`，⛔ 不是端点，不在服务路径上）。
   本轮**没动**，但它同样**不记账**。
5. **测试覆盖的边界要说清**：普通答案分支（`citations=False`）的**行为**有测
   （`test_plain_answer_branch_records_with_identity`），但 `answer_with_citations`
   的**引用格式/拒答逻辑本身仍零测试** —— 这是一条**早于**本轮的欠账。
