# `api/hybrid_search.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，但它在全仓是【第二份 RRF 实现】** |
| **对外提供** | `reciprocal_rank_fusion()` · 三个组合函数 |
| **谁在用** | ⚠️ **只有路由层**（`/rag/hybrid_search`）—— **`rag_pipeline` 不用它** |

## ✅ 做了什么

- **RRF（Reciprocal Rank Fusion，k=60）** —— 融合稠密向量检索与稀疏 BM25 两路结果
- 是 `ROADMAP` 功能现状表里标 **✅「混合检索（向量 + BM25 + RRF 融合）」** 的落点

## 🟡 做到哪 / 缺什么

- 🔴 **同算法两份实现**（见下）
- 🔴 **零测试覆盖**（`docs/说明/测试.md` §六 **#1**）
- ⚠️ **它是 `ROADMAP` 自己点名的"复审出过 bug 的地方"**：
  > 「**RRF 恰恰是 2026-08-17 复审出 bug 的地方**」
  > （那次是元组解包崩溃：按 3 元组解包，而 `db.search_similar` 返回 4 列 —— 修复记录 #4）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「`/rag/search` 用的就是 `hybrid_search.py`」 | 🔴 **不是** —— `/rag/search` 走 `rag_pipeline.py:201` 的 **`_rrf_fusion`**（**另一份实现**）<br>⇒ **本文件只服务 `/rag/hybrid_search` 一条端点** |
| 「RRF 被测试守着」 | 🔴 **没有** —— `test_rag_search.py` 测的是它**自己复制的一份 `_rrf_fusion`**（第三份副本）⇒ **真融合逻辑【没有直接覆盖】** |
| 「BM25 在这文件里」 | 🔴 **不在这** —— BM25 在 `api/bm25_index.py`（jieba + rank_bm25，带进程内缓存） |

> ⭐ **这条是本 spec 最有价值的发现**：
> **同一个算法三份代码**（`rag_pipeline._rrf_fusion` · 本文件的 `reciprocal_rank_fusion` · 测试里的副本），
> **测试测的那份【不是产品在跑的那份】。**

## 关联

`ROADMAP` 功能现状表 · `docs/说明/测试.md` §六 · `docs/原理/架构.md` §1.2（"同一算法两份实现"）
