# `api/answer_with_citations.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **后端可用 · 但【默认不启用】—— 且零测试** |
| **对外提供** | `generate_answer_with_citations(contexts, question, llm, *, user_name, thread_id="default")` |
| **谁在用** | `rag_pipeline.py:182`（仅当 `generate_answer=True` **且** `citations=True`） |

## ✅ 做了什么

- 生成带 **`[来源:n]` 行内引用标记**的 LLM 答案
- 返回 `answer` + **结构化的 `sources`**（`[{"id","source","content_preview"}]`）
- 支持**无据拒答**（资料不足时输出「根据现有资料，无法回答」）—— `docs/demos.md:50-51` 有实测
- 🔴 **2026-10-05（`DEC-073`）：生成后记一笔真账**（`token_tracker.record_from_response`，`:68`），
  身份由**必填** keyword `user_name` 传进来（`:35`）

## 🟡 做到哪 / 缺什么

- 🔴 **零测试覆盖**（`docs/说明/测试.md` §六 **#6**）
  ⚠️ **2026-10-05 澄清**：`api/test_rag_billing_wiring.py` 里那两条测的是**记账**，
  ⛔ **不是**引用格式 / 无据拒答 ⇒ **上面这条欠账依然成立**。
- 🔴 **前端不存在** ⇒ **引用点不开**（见下）
- ⚠️ **它是硬门 B 的【后端】主体** —— 硬门 B 的另一半（可点开的界面）**完全没做**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「引用溯源做完了」 | 🔴 **只做了一半** —— 后端能给引用，**但全仓无业务前端**（`api/static/` 只有 3 个调试页，**无 `package.json`**）⇒ **"点开展开原文/高亮命中段"做不到** |
| 「调用它就会有引用」 | 🔴 **不会** —— **`citations` 默认 `False`**（`api/schemas.py:16`），**`generate_answer` 默认也 `False`**（`:14`）⇒ **两个都不显式打开 ⇒ 连 `answer` 字段都没有，更不会有引用** |
| 「README 说的点击溯源是真的」 | 🔴 **那句已在 2026-09-29 更正** —— 原文写「支持点击溯源到原始文档块」，**"点击"不成立** |
| 「`llm \| StrOutputParser()` 是常规写法，无妨」 | 🔴 **在本文件里它是个坑** —— `StrOutputParser` 把 `AIMessage` **剥成 `str`**，`usage_metadata` **随之丢光** ⇒ 记账**拿不到数**、且**静默跳过**（不抛错）。<br>⇒ 本文件**直调 `llm.invoke(messages)`** 取消息本体（`:62`）。⛔ **别"顺手统一成链式写法"** —— 那等于把记账再关掉一次。<br>📌 守卫：`api/test_rag_billing_wiring.py::test_no_llm_usage_is_swallowed_by_string_output_parser`（**全文件扫描**，不依赖任何前置识别） |
| 「`user_name` 可以不传」 | 🔴 **它是必填 keyword**（`:35`）—— 漏传 = `TypeError`。⛔ 不是"静默记成 `unknown`"（`DEC-072` 明文反例）。 |

> 📌 **这是硬门 B 的典型"看着有、实际缺一半"** ——
> `ROADMAP` 功能现状表标的是「硬门 B 引用溯源**界面** ❌」，**后端那半才是 ✅**。

## 关联

`ROADMAP` 功能现状表 · `docs/契约/接口契约.md` §四（`generate_answer` / `citations` 默认值）·
`docs/demos.md:46-54` · `通用/四硬门-定义与验收标准.md` 硬门 B ·
`DEC-073`（RAG 侧关闭零记账）· `docs/specs/token_tracker.md`
