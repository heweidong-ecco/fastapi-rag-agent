# `api/approval_audit.py`

## ✅ 做了什么

- 审批留痕的**唯一落点**：惰性建表 + 写（`record_decision`）+ 读（`list_decisions`）
  + `summarize_tool_calls`（留痕里「为什么」那栏的摘要）。
- 表 `approval_events`：`owner`（会话是谁的）· `actor`（谁做的裁决）· `raw_thread_id` ·
  `graph` · `decision` · `edited`（有没有代替模型给结论）· `rounds` · `reason` · `created_at`。
- 写入方：`api/api_v1_agent.py` 的 `POST /agent/approve`（每次**真的落到图上的裁决**写一条）。
- 读取方：`GET /agent/approvals/history` → 接管页（`api/static/web/approvals.html`）下半栏。
- 建表方式与 `budget_intercepts` **完全同款**（`token_tracker.py` 里那段）：
  **不在 `db.py` 的 `create_table()` 里**，第一次写入时惰性 `CREATE TABLE IF NOT EXISTS`。

## 🟡 做到哪 / 缺什么

- ✅ 四个出口里**「真的落到图上的裁决」**都记（`approved` / `rejected`，含 `forced_finish=True` 那次
  与「放行后模型又停在审批点」那次）。
- ⛔ **不记**「根本没批成」的**四条**：没有可待批任务 · 歧义（多条）· 无权限 · **登记陈了**
  （图没停在审批点）。⚠️ 前三条是 `DEC-088` §3.2 列的，**第四条是施工时核出来的**
  （见下面「看代码会误判的地方」）。
- ⛔ **不记「越权审批的尝试」** —— 要它得另定保留期与读取权限，属另一件事（`DEC-088` §六·3）。
- ⛔ **无保留期 / 无清理任务** —— 表会一直长。

## ⚠️ 看代码会误判的地方

- 🔴 **留痕的落点位置是刻意的，⛔ 别"顺手往上挪"。** 它写在 `/agent/approve` 的
  `current_state.next != ("approval",)` **那道守卫之后** —— 那条出口（登记陈了）发生在
  **归属校验通过之后**，把留痕挪到它前面，就会记下一次**根本没落到图上**的裁决。
  判据：`api/test_approve_audit_wiring.py::test_stale_registry_records_nothing`。
- 🔴 **`edited=True` ≠「改了模型的答案」。** 审批点上模型**还没有生成答案** —— 它停下是因为
  「我要调这个敏感工具」（`tool_calls` 就是这个请求）。`edited` 的真实语义是
  「**人工代替模型给出了这次工具调用的结果**」（回填成 `ToolMessage` + 显式 `as_node="tools"`，
  走 `api_v1_agent._tool_rulings`）。⇒ 界面主文案必须如实写，⛔ 别写「改写答案」。
- **fail-open 是刻意的**：写失败只 `print` 一行、读失败返回 `[]`。
  ⇒ **表里少一条 ≠ 那次裁决没发生**。查历史时⛔ 别把"查不到"读成"没批过"。
- **`owner` 与 `actor` 是两个身份**：admin 接管 alice 的会话时 `owner="alice"`、`actor="admin"`。
  合成一个字段 ⇒ 留痕当场变假话，**而且不报错**。
- **`list_decisions(owner=...)` 是必填关键字参数**：`None` = 全量。
  ⛔ **别给它加默认值** —— 那会让「我忘了传」与「我要查所有人」再也分不出来（`DEC-055` 口径）。
- **`_COLUMNS` 的顺序必须与 `list_decisions` 的 `SELECT` 列顺序一致** ——
  靠 `zip` 配名，**错位不报错**，只会把 `decision` 显示成 `actor`。

## 关联

`docs/decisions/DEC-088-接管页与硬门D的三个缺口.md` · `docs/specs/pending_approvals.md` ·
`docs/specs/api_v1_agent.md` · `api/schema.sql`（`approval_events` 尚未进这份**生成的**快照，见下）

> ⚠️ **`api/schema.sql` 里现在还没有 `approval_events`** —— 那份文件是 `pg_dump` **生成的**
> （文件头明写「⛔ 不要手改」），要它出现只能**重新导一次**（需要活着的库）。
> 在那之前，**本模块的 `_DDL` 是唯一的权威**。
> ⚠️ **顺带一条**：这表是**惰性**建的（`api/approval_audit.py:72` 的 `CREATE TABLE IF NOT EXISTS` 在写入路径里）
> ⇒ **不先真跑一次 approve，表根本不存在**，`pg_dump` 照样导不出它。
> 🔴 **两件事（重生成 + 真库用例）已登记** ⇒ `docs/待办总表.md` §三·附 **`N12`**（含可打印判据）。
