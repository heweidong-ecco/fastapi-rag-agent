# 决策记录：DEC-063 · 写 `documents` 表的地方必须让 BM25 缓存作废 —— 修法放【helper 层】

- 日期：2026-10-04
- 状态：**已立 · ✅ 已实施**（`db.py` 两处 + 守卫用例 `api/test_bm25_cache_invalidation_wiring.py`）
- 待办总表：**N3**（现为 ✅）
- 触发：业务方 2026-10-04 点「下一步」= **N3**（`docs/specs/db.md` 里记着的那条）

---

## 一 · 要裁的是什么

`/rag/upload_document` 插完文档**不失效 BM25 进程内缓存**。三件事要定：

| # | 要裁的 |
|---|---|
| **1** | 修哪 —— 只有 `/rag/upload_document` 一处，还是这个**类**？ |
| **2** | **修法放哪一层** —— 端点（跟另外三条写路径一样）还是被调用的 helper（`db.insert_document`）？ |
| **3** | 判据怎么写才**治得住复发** —— 本仓的坑明写是「**修过一次、没修全**」 |

---

## 二 · 实测（改前 · 可打印）

```bash
# ① 四条写路径里，只有 upload_document 那条没有失效调用
grep -rn 'invalidate_bm25_cache' api/*.py | grep -v test_
# ⇒ api_v1_rag.py:164（/rag/insert）· :264（/rag/insert_batch）· :358（DELETE）
#    以及 db.py 的转发层定义 —— /rag/upload_document 一处都没有

# ② upload_document 的整个函数体里没有它
awk 'NR>=272 && NR<=331 && /invalidate_bm25_cache/' api/api_v1_rag.py   # ⇒ 空

# ③ 它写库走的是 helper（所以"这条路径上没有插入语句"这件事是真的）
grep -n 'insert_document' api/api_v1_rag.py     # ⇒ :317 insert_document(chunk, file.filename, …)
grep -rn 'insert_document' api/db.py            # ⇒ :175 定义 —— 里面也没有失效调用
```

**行为侧**（同一条判据的另一种写法，见守卫用例）：把 `db.get_db` 换成假连接、
往 `bm25_index._bm25_cache` 里塞一个桶、调一次 `db.insert_document(...)` ⇒
**改前桶还在**，改后桶没了。

⚠️ **这不是本 DEC 首次发现的**：`api/api_v1_rag.py:163-164` 的注释里留着
**2026-09-11 的实测**（"重启前新文档不在 top10，重启后第 2 名"）——
那次修只给了 `/rag/insert`。**同一个坑，隔了近一个月，还漏着一条。**

---

## 三 · 根因

⛔ **不是"某个人忘了写一行"**。

`invalidate_bm25_cache()` 这个不变量**只写在端点上** ⇒
**每一次新增写路径，都要靠人"记得"再补一句**，而**没有任何东西会在漏掉时响**。
2026-09-11 的修复正是这么漏的：修的人**知道**这条规矩（注释就是他写的），
只是他修的是**手上那一个端点**。

> 📌 与 `DEC-051` 同型：那边的病根是「**白名单抄了一份**」而不是「指向同一份」。
> **知识/不变量挂在"要人记得"的位置 ⇒ 迟早再犯。**

---

## 四 · 裁定

**A. 不变量下沉到 helper 层。**

在 `db.insert_document()` 与 `db.insert_batch_documents()` 末尾加 `invalidate_bm25_cache()`。
⇒ 谁经这个 helper 写文档，**都不可能忘**；`/rag/upload_document` 因此**不用改一行**。

⚠️ **清缓存是惰性的**（`_bm25_cache.clear()`，重建发生在下次搜索）
⇒ `upload_document` 逐块调用造成的"N 次清"**不是 N 次重建**，代价约等于零。

**B. 判据改成【推导型】，⛔ 不是【清单型】。**

新建守卫 `api/test_bm25_cache_invalidation_wiring.py`，**从 `api/*.py` 的 AST 里推出写路径**：

| # | 规矩 |
|---|---|
| **A** | 函数体内**直接**写 `documents` ⇒ 它**自己**必须调 `invalidate_bm25_cache()` |
| **B** | 函数调用了「写文档的 helper」⇒ 要么**自己**调，要么**那个 helper** 调了 |

⇒ **新增一条写路径而忘了清缓存，本文件立刻转红**，⛔ 不需要谁记得去更新一张名单。

**C. ⛔ 不动另外三条已合规的写路径。**

`/rag/insert` · `/rag/insert_batch` · `DELETE /rag/documents/{id}` 本来就调了 ——
它们**在判据里照样被覆盖**（判据 A 会看着它们），但**本次不改它们的代码**。

---

## 五 · 判据（可打印）

```bash
# ① 守卫（离线 · 进 CI）—— 3 条：判据A · 判据B · 行为侧
venv/bin/python -m pytest api/test_bm25_cache_invalidation_wiring.py -q          # ⇒ 3 passed

# ② 改前它必须红 —— 把 helper 里那句拿掉即可（本 DEC 的 RED 就是"改前的代码"）
#    ⚠️ 判据必须"能红"才是判据（DEC-061 的教训）
```

**红→绿实测**（改前跑同一条命令）：

```
FAILED test_每个直接写_documents_的函数都让缓存作废
       ⇒ db.py::insert_document · db.py::insert_batch_documents
FAILED test_调用写文档helper的函数也清缓存
       ⇒ api_v1_rag.py::upload_document 调了 insert_document()，两边都没清缓存   ← 就是 N3 本身
FAILED test_insert_document_跑一次真把缓存桶清空
3 failed
```

**证伪（判据逮不逮得住"将来的新写路径"）**：把 `API_DIR` 指向一个只含**合成模块**的临时目录，
里面放一条「写 `documents` 但没清缓存」的函数 ⇒ **判据 A 立刻报它**（实测输出见 PR 正文）。
⇒ 证明这是**推导型**判据，⛔ 不是把已知的几个函数钉住的清单。

**全量**（CI 口径 —— ⛔ 别拿裸 pytest 顶替，见 `docs/说明/测试.md` §5.2）：

```bash
bash scripts/ci-local.sh      # ⇒ 见 PR 正文记录的数（改前以 base commit 实测为准）
```

---

## 六 · 边界与没解决的

1. ⚠️ **守卫只认"直接名调用"** —— `f(...)` 与 `obj.f(...)` 都认，但**别名 / 重导出不追**
   （`from db import insert_document as ins` 这种会被漏掉）。这是**已知的判据边界**，
   ⛔ 别读成"这里已经安全"；仓里目前没有这种写法。
2. ⚠️ **只扫生产模块**（`api/*.py` 去掉 `test_*.py`）。测试里的探针自己负责清理
   （`api/test_isolation.py::_probe_cleanup` 就是干这个的）。
3. ⚠️ **判据 A 认的是「传给 `execute*` 的字符串常量」** ⇒
   若将来把 SQL 挪进模块级常量再传变量，**判据会瞎**（会退化成空集）。
   守卫里已加 `assert writers` 钉住"扫描没瞎"，空集**不会静默通过**。
4. ⛔ **`db.insert_batch_documents()` 仍是死代码**（全仓无调用方）——
   本次按同一条不变量给它补了那一句，但**没有让它复活**，也没删它。
5. ⛔ **没有解决**：`invalidate_bm25_cache()` 是**清所有用户的桶**（`bm25_index.py:96`）。
   每次写入都让**所有人**的索引重建一次。本次**没动**它的粒度 —— 那是另一件事
   （`docs/specs/bm25_index.md` 已登记该设计是有意的"安全侧"）。

---

## 七 · 否掉的备选

| 备选 | 为什么否 |
|---|---|
| **只在 `/rag/upload_document` 末尾加一行** | 改动最小，但**病根原样留着**：下一条写路径照样没人提醒。本仓的坑**明写就是"修过一次没修全"** |
| **守卫写成「4 个端点各自必须调」的清单** | 清单型 ⇒ **只钉住当时知道的那几个**。N3 正是"清单漏了一条"，用清单去防清单漏项 = 没防 |
| **让 `/rag/insert` 等三条也改走 helper** | 它们已经合规，改它们 = **顺手重构**（业务方明令不做的事），且会扩大本 PR 的爆炸半径 |
| **干脆删掉死代码 `insert_batch_documents`** | 那是**另一件事**（死代码清理在 `docs/待办总表.md` 另有条目），不并进来 |
| **把不变量放进 `bm25_index` 侧的写钩子** | 写入根本不经过 `bm25_index`（它是检索侧）⇒ 钩不上 |

---

## 八 · 一句话

**一个"每次新写路径都要记得补一句"的不变量，等于没有不变量。**
修法不是再补一句，而是**把它挪到写操作自己的那一层**（`db.insert_document`），
再配一道**从代码里推导写路径**的守卫 —— 两者合起来，这个坑才**不可能再复发**。
