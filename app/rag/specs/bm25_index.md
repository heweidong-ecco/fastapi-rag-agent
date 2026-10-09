# `app/rag/bm25_index.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 且 **2026-10-03 起它是「多用户隔离」的两个承重层之一**（`DEC-056` 决策 5：过滤写在共享层） |
| **对外提供** | `bm25_search()` · `get_all_documents()` · `get_bm25_index()` · `invalidate_bm25_cache()`（+ 私有的 `_meaningful_tokens()` / `_require_identity()` / `_NON_WORD`） |
| **谁在用** | ⚠️ **没有直接调用方** —— 都是经 `db.py` 的**惰性转发层**（`db.bm25_search` / `db.bm25_search_async` / `db.invalidate_bm25_cache`）⇒ 再往上是 `hybrid_search.py` 与 `rag_pipeline.py` |

## ✅ 做了什么

- **BM25 关键词检索** —— `jieba` 中文分词 + `rank_bm25.BM25Okapi`
- **进程内缓存**，避免每次搜索重建索引
- 是 `ROADMAP` 功能现状表里 **✅「混合检索（向量 + BM25 + RRF 融合）」** 的**稀疏那一路**

## 🔴 2026-10-03 · 多用户隔离（`DEC-056` 甲段）

**两件事都改了**（互相牵连，别拆开读）：

**① 语料按人切，⛔ 不是"检索出来再筛掉"** —— `get_all_documents(user_id)` 在 **SQL 层**就
`WHERE requested_by = %s`；缓存的 key 从「一份全局」改成 **`user_id` 分桶**。

> ⚠️ **为什么必须是"切语料"**：若是"全库建索引、返回时筛"，别人的文档**仍会参与 IDF 统计**
> （`BM25Okapi` 是在整个语料上算的）—— 结果里虽看不到原文，**但词频/权重已被别人的数据影响**。
> 判据是「**看不见**」，那就**别让它进索引**（`DEC-056` 决策 3）。

**② 入选判据换了**（**`DEC-056` 决策 7** —— ⚠️ 本 Agent 拍的板，业务方 2026-10-03 裁「不拆单独 DEC」）：

```
原判据： if scores[idx] > 0        ← "分数为正才算命中"
新判据： if query_tokens & token_sets[idx]   ← "实词有重合"
```

**根因**：`rank_bm25` 的 idf = `log(N - n + 0.5) - log(n + 0.5)` ——
**词出现在超过一半文档里就是负的**。语料**按人切**之后，小用户（1 篇）必然触发
⇒ 分数为负 ⇒ 原判据**恒假** ⇒ **关键词检索对小用户整个失效**（`/rag/hybrid_search` 退化成纯向量）。

**实测**（探针语料）：1 篇时 `idf = -0.27` / `score = -0.82`；5 篇时 `idf = +1.10` / `score = +2.18`。

⚠️ **对外部行为的差异（大语料上）**：以前"只靠高频词命中"的文档会被**丢弃**，
现在会**入选但分数最低** ⇒ 排在最后（`hybrid_search` 的 RRF 按**名次**给分，它们的贡献最小）。

## 🟡 做到哪 / 缺什么

- 🔴 **「改完文档要清缓存」全靠调用方记得** —— 本模块**没有**任何自动失效机制。
  已知**有 3 处记得**（`/rag/insert` · `/rag/insert_batch` · `DELETE /rag/documents/{id}`），
  **1 处漏了**：`/rag/upload_document`。详解见 `db.md` 的同名条目。
- ⚠️ **缓存是进程内的** ⇒ 多 worker 部署时**每个 worker 各一份**，
  A worker 插入后清不到 B worker 的缓存。**单 worker 下不成问题，多 worker 下是真问题。**
- ⚠️ **零测试覆盖本模块直接行为** —— `app/tests/test_isolation.py` 有 2 条**间接**打到
  `bm25_search` 的隔离性（`test_bm25_search_only_returns_own_documents` ·
  `test_bm25_still_finds_own_document`），**但打分质量 / 排序正确性无测试**。
- ⚠️ **`_meaningful_tokens` 只用于入选判定**，⛔ **不参与打分** ——
  过滤会改变词频/idf，那属"调质量"，不在隔离这一段的范围内（有意留着）。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`scores` 是正的 ⇒ 命中」** | ⛔ **判据已经不是分数了**（2026-10-03 起）—— `scores` **只用来排序**，入选靠 `query_tokens & token_sets[idx]`。<br>⇒ 会看到"分数为负还挺在结果里"而以为坏了 —— **那是有意的**（决策 7）。<br>📌 判据：`grep -n "query_tokens & token_sets" app/rag/bm25_index.py` ⇒ `:135` |
| 🔴 **「`_bm25_cache` 是一份全局索引」** | ⛔ **2026-10-03 起按 `user_id` 分桶**（`:44`）。<br>⚠️ 且 **`invalidate_bm25_cache()` 清【所有】桶**（`:96` `_bm25_cache.clear()`）—— **不是只清某人**。<br>⇒ 插入/删除时**不知道影响谁**，全清是**安全侧**（宁可多重建，⛔ 不可留旧语料）。**代价是重建变频繁** |
| 🔴 **「BM25 在 `hybrid_search.py` 里」** | ⛔ **不在** —— 那是 **RRF 融合**层。BM25 本体**只在本文件**；`hybrid_search.py` 经 `db` 转发层调它 |
| 🔴 **「`jieba` 分出来的词都参与"是否重合"判定」** | ⛔ **不是** —— `jieba.cut` 会吐出 `' '` / `'·'` / `'-'` 这类**每篇都有**的词元，拿它们判定 ⇒ **任意两篇都算重合**，判定就废了。<br>⇒ `_NON_WORD`（`:23`）专门剔掉它们，**只用于入选判定** |
| ⚠️ **「IDF 是按全库算的」** | ⛔ **按【该用户的语料】算** —— 这是**故意的**（同上方 ①）。<br>⇒ **同一个词，在不同用户那里分数不同** ⇒ ⛔ **别拿 A 的分数去解释 B 的结果** |
| ⚠️ **「两路召回（向量/BM25）各返回 `top_k`」** | ⛔ **实际各取 `top_k * 2`** —— 融合前多召回一些，见 `hybrid_search.py:84` / `:87` |

## 关联

`docs/decisions/DEC-056-多用户资源隔离的现状审计与分阶段收口.md`（决策 3 · 5 · 7）·
`app/core/specs/db.md`（转发层与 `_require_identity`）· `app/rag/specs/hybrid_search.md`（RRF 融合）·
`docs/原理/架构.md` §1.2
