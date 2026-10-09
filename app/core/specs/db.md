# `app/core/db.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 连接池 + 建表 + 向量检索；**2026-10-03 起它同时是「多用户隔离」的两个承重层之一**（`DEC-056` 决策 5） |
| **对外提供** | 连接池：`init_pool()` · `close_pool()` · `get_db()`<br>建表：`create_table()`<br>写入：`insert_document()` · `insert_batch_documents()`<br>检索：`search_similar()` · `bm25_search()` · `search_similar_async()` · `bm25_search_async()` · `invalidate_bm25_cache()` |
| **谁在用** | ⚠️ **几乎是全仓** —— `auth.py` · `deps.py` · `cost_dashboard.py` · `main.py` · `api_v1*.py` … 都 `from db import get_db` |

## ✅ 做了什么

- **`ThreadedConnectionPool` 连接池**（上下限走 `config.py` 的 `DB_MIN_CONN` / `DB_MAX_CONN`）
- **`create_table()`** —— 建 5 张表 + 索引 + `pgvector` 扩展；含**兼容旧表**的 `DO $$ … ADD COLUMN` 块
- **向量检索 `search_similar()`** —— `pgvector` 余弦距离
- **BM25 检索的转发层** —— 惰性导入 `bm25_index`，见下方「兼容转发层」

## 🔴 2026-10-03 · 多用户隔离（`DEC-056` 甲段）

**这是 决策 5「共享层承重」的那个"共享层"** —— 过滤**写在这里**，⛔ 不是每个端点各写一遍。
一次改动**同时修好 4 条端点**（`/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search`）。

- `search_similar()` / `search_similar_async()` 加 **`WHERE requested_by = %s`**（`:222`）
- `bm25_search()` / `bm25_search_async()` 把 `user_id` **透传**给 `bm25_index`（过滤实现在那边）
- 四个检索函数的 `user_id` 都是 **关键字必填（`*, user_id: str`）**：⛔ **不给默认值** ——
  有默认值 = "可以忘记传" = 还是 fail-open，漏传即 `TypeError`（`DEC-056` §六 ③）
- **`_require_identity()`（`:197`）挡在【取连接之前】** —— ⚠️ 这是关键：
  若放在查询之后判，**"传 `None` ⇒ 不过滤 ⇒ 返回全库"那条路仍然存在**。
  它的 docstring 写明了这个理由。

## 🟡 做到哪 / 缺什么

- 🔴 **`insert_batch_documents()` 是【死代码】**（`:185`）—— `grep -rn "insert_batch_documents(" app/`
  **只有 def 那一行**；两处 `import`（`api_v1_rag.py:36` · `api_v1.py:21`）是**死的**。
  ⚠️ **而且它就算被调用也不写 `requested_by`** —— 见下方 ⚠️ 表第 1 行。**别拿它当批量插入的入口。**
- 🔴 **`create_table()` 里 `documents.requested_by` 的默认值是 `'anonymous'`**（`:70`）——
  即"**没有主人**"。⚠️ 配合上一条 ⇒ 任何漏写 `requested_by` 的插入**都不会报错**，
  只会静默落进一个**谁都不是**的桶（⇒ 按隔离过滤后**谁也检索不到**）。
- ⚠️ **`db.py` 已不再是"重包引入口"** —— 模块层**不再** `import numpy / jieba / rank_bm25`，
  全部切给了 `bm25_index.py`。**别在模块层给它加回这些** —— 那会让**每个**
  `from db import get_db` 的调用方（含 `auth.py`）又被迫拉起重包。
- ⚠️ **本文件的隔离改动【只有】`app/tests/test_isolation.py` 守着** —— 那 8 条里 4 条直接打在
  `search_similar` / `bm25_search` 上（**已做过证伪**：临时拿掉 `WHERE` ⇒ 4 条变红）。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴🔴 **「`insert_batch_documents()` 和 `insert_document()` 是一对，只是批量版」** | ⛔ **两处都错**：<br>① **全仓零调用**（只有 def + 两处死 import）—— 真正在跑的批量插入是 `api_v1_rag.py:259` **自己的 SQL**；<br>② 它的 SQL **没有 `requested_by` 列**（`:191`）⇒ 就算调用，落的是表默认值 `'anonymous'` ⇒ **成为"谁的都不是"的文档**。<br>📌 判据：`grep -rn "insert_batch_documents(" app/` ⇒ **1 行（就是 def）** |
| 🔴 **「文档一定属于某个人」** | ⛔ **不是** —— `requested_by` 有 `DEFAULT 'anonymous'`（`:70`）。<br>⇒ **漏写的插入不报错**，静默落进无主桶；**而隔离过滤会让它谁都搜不到**。<br>⚠️ 真库现状（2026-10-03）：84 篇**全是 `admin`** ⇒ **还没踩到**，但这是**结构上留着的坑** |
| 🔴 **「`db.bm25_search` 是 BM25 的实现」** | ⛔ **只是【惰性转发】** 到 `bm25_index.bm25_search`（`:242`）—— 过滤/打分**都在那边**。<br>⚠️ **为什么必须惰性**：`bm25_index` **反向** `from db import get_db`，模块层互相 import 会**成环**，且**只在"先 import bm25_index"时炸** ⇒ 最难查的一类 |
| 🔴 **「写完 `documents` 表，BM25 缓存必然已经作废」** | ✅ **2026-10-04 起成立**（`DEC-063`）—— 不变量**下沉到写操作自己那层**：`insert_document()` / `insert_batch_documents()` 末尾各有一次 `invalidate_bm25_cache()`。<br>⚠️ **改前不成立**：`/rag/upload_document`（它走 helper）**没清缓存** ⇒ 上传的新文档在 BM25 召回里"不存在"，直到别的写路径顺手清了或重启。另三条写路径（`/rag/insert` · `/rag/insert_batch` · `DELETE`）**当时就已经调了**。<br>🔴 **同一个坑修过一次没修全**：`api_v1_rag.py:163-164` 的注释留着 2026-09-11 的实测（"重启前新文档不在 top10，重启后第 2 名"）—— 那次**修给了 `/rag/insert`，漏了 `/rag/upload_document`**。<br>⇒ 本次修法 ⛔ **不是"再补一句"**，而是把不变量挪进 helper + 加**推导型守卫**（`app/tests/test_bm25_cache_invalidation_wiring.py`，从 AST 里推出写路径 ⇒ 新写路径忘了清缓存**立刻转红**）。📄 `DEC-063` |
| ⚠️ **「`user_id` 传进来就安全了」** | ⚠️ **`_require_identity` 只挡【空值】，不挡【伪造】** —— 它查的是 `if not user_id`。<br>⇒ **身份真假由端点层的 `get_current_user_hybrid` 保证**；若哪条端点把**请求体里**的字段直接传下来，这层**挡不住**。<br>📌 判据：`grep -n "user_id=user_name" app/routing/api_v1_rag.py` ⇒ 传的必须**是鉴权依赖的返回值**，⛔ 不是 `req.` 上的字段 |
| ⚠️ **「`get_db()` 用完不 commit 会丢」** | ✅ **不会** —— 它是 `@contextmanager`（`:35`）：正常退出 `commit`、异常 `rollback`、`finally` 归还连接。<br>⚠️ 但**别因此把 `with` 写成手动 `getconn/putconn`** —— 那会绕过归还逻辑，**连接池会漏** |
| ⚠️ **「`search_similar` 第 4 列是"距离"，越小越像」** | ⛔ **是"相似度"** —— SQL 里写的是 `1 - (embedding <=> %s)`，`<=>` 是余弦**距离**，减完变成相似度 ⇒ **越大越像** |
| 🔴🔴 **「调用方 patch 了【自己模块的】`get_db`，就能把这里的连接短路掉」** | ⛔ **不能** —— 本文件里的 `search_similar` / `bm25_search` 调的是 **`db.py` 自己的模块全局 `get_db`**。调用方 patch `api_v1_rag.get_db` **够不着这里**。<br>⇒ **调用方一旦从"自己写 SQL"改成"调共享层"**，原来那条 monkeypatch **静默失效** ⇒ 会**真去连库**。<br>🔴 **而本机看不出来**（本机 Postgres 开着 ⇒ 连上、回 `[]`，与假连接**返回值一样**）；**CI 没有 Postgres ⇒ `Connection refused`**（2026-10-03 实测 12 条红）。<br>⇒ **判据**：`grep -rn 'setattr(.*get_db' app/test_*.py` —— 逐条看 patch 的是**哪个模块的**。📄 `docs/复盘/2026-10-03-CI同款命令不等于CI等价物.md` |

## 关联

`docs/decisions/DEC-056-多用户资源隔离的现状审计与分阶段收口.md`（决策 3 · 5 · 7）·
`app/rag/specs/bm25_index.md`（转发目标与缓存分桶）·
`app/rag/specs/hybrid_search.md` · `docs/契约/数据模型.md`（表结构）·
`docs/原理/架构.md`（依赖方向：`db` ← `bm25_index` 单向）
