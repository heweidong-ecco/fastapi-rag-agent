# `api/chunker.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 但**五档配置里只有两档真被用到**，且**零测试** |
| **对外提供** | `get_text_splitter(doc_type)` · `split_text(text, doc_type)` · `split_text_with_filter(text, doc_type, min_length=20)` · `CHUNK_CONFIGS` · `DEFAULT_SEPARATORS` |
| **谁在用** | 🔴 **生产调用点只有 1 处**：`api/api_v1_rag.py:325`（文档上传时切块）。⛔ 别处没有 |
| **测试** | 🔴 **零** —— `ls api/test_*chunk*` ⇒ **无此文件**。它靠 `api/test_documents.py` 之类的**上游用例间接覆盖**（走"上传→入库"那条路） |

## ✅ 做了什么

**按文档类型选分块参数**，底层是 LangChain 的 `RecursiveCharacterTextSplitter`。

| `doc_type` | `chunk_size` | `chunk_overlap` | 谁在用 |
|---|---:|---:|---|
| `default` | 500 | 50 | ⚠️ **无人**（只作兜底） |
| `technical` | 500 | 50 | ✅ `api_v1_rag.py:324` —— **非 PDF 都走这条** |
| `legal` | 800 | 100 | ✅ `api_v1_rag.py:324` —— **PDF 走这条** |
| `report` | 800 | 100 | ⚠️ **无人** |
| `article` | 1000 | 200 | ⚠️ **无人** |

`split_text_with_filter` 额外**丢掉短于 `min_length`（默认 20 字符）的块**。

## 🟡 做到哪 / 缺什么

| 缺口 | 说明 |
|---|---|
| 🔴 **五档里三档是死的** | `default` / `report` / `article` **全仓零调用**（判据见 §⚠️ 第 1 条）。⇒ **配置表看起来比实际能力大** |
| 🔴 **`"technical"` 与 `"default"` 的配置逐字相同** | 两档**行为完全一样** ⇒ 那一档现在**等于没生效**（分不出来） |
| 🔴 **`doc_type` 没有校验** | 传不认识的值会**静默落 `default`**（见 §⚠️ 第 1 条） |
| ⚠️ **零测试** | 分块边界（超长块、全空文本、单个超长句）**没有一条用例钉着** |
| ⚠️ **没有"每块字符数上限"的保证** | `RecursiveCharacterTextSplitter` 在**找不到分隔符**时会**切出超长块**（见 §⚠️ 第 4 条）—— 而下游要拿块去算 embedding |

## ⚠️ 看代码会误判的地方

> ⭐ 这一节是整份 spec 的价值所在 —— 前面两节读代码也能推出来，这一节**推不出来**。

### 1. 🔴 **`doc_type` 不是请求参数** —— 它是**算出来的**，而且只有两个取值

读本文件会以为"调用方可以按文档类型精细选"。**实际**，全仓唯一调用点写的是：

```python
# api/api_v1_rag.py:324
doc_type = "legal" if ext == "pdf" else "technical"
```

⇒ 🔴 **只有 `pdf` 档和非 `pdf` 档两档**。`report` / `article` / `default` **永远不会被传进来**。

🔴 **判据（可打印）**：
```bash
grep -rn 'doc_type' api/ | grep -v '^api/chunker.py'
```
⇒ 只有 `api_v1_rag.py` 那两行。

### 2. 🔴 **`doc_type` 传错** → `default`，**⛔ 不报错**

```python
config = CHUNK_CONFIGS.get(doc_type, CHUNK_CONFIGS["default"])
```

⚠️ **`.get` 带兜底 ⇒ "传了个拼错的类型" 与 "传了 `default`" 在行为上完全一样**，
**没有任何痕迹**。⇒ 这与本仓对 `mode` 的处理**正好相反**（`api_v1_rag.py` 的 `SearchMode` 是 `Literal`，
非法值 **422**，明文理由写在 `DEC-013`）。

⛔ **别把这里的 `.get` 当成"容错设计"** —— 那是一种**静默**；真容错要**打日志**或**拒绝**。

### 3. 🔴 **过滤短块的是 `split_text_with_filter`，⛔ 不是 `split_text`**

两个函数**只差一个 `min_length` 过滤**，名字也接近。谁直接调 `split_text` 就**不过滤**。
⇒ 下游拿到空块 / 单字符块是可能的（会让 embedding 白花钱、也让 RRF 的分母变脏）。
⚠️ **目前唯一调用点用的是带过滤的那个**（`api_v1_rag.py:325`）—— 但**这个选择没有任何东西拦着**。

### 4. ⚠️ 分隔符里**混了中英文标点** —— 这是**实质**，⛔ 别"优化"掉

```python
DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "，", " ", ""]
```

中文没有空格分词，**句读符号就是天然的块边界**。⛔ 按英文习惯精简成 `["\n\n", "\n", " ", ""]`
会让中文长段**没有可切的地方** ⇒ 落到最后一个 `""` 分隔符 ⇒ **按字符硬切**（切断句子）。
⇒ 这份顺序是**中文分块的实质**，改动它的后果**不会让任何用例变红**（因为**零测试**）。

### 5. 🔴 两个常量**已删**（2026-10-07）—— 看 git 历史会看到 `DEFAULT_CHUNK_SIZE` / `DEFAULT_CHUNK_OVERLAP`

删的理由写在文件里：**全仓零引用**，且与 `CHUNK_CONFIGS["default"]` 的 500/50 **重复**
—— 「**同一个数两个来源必然漂移**」。

### 6. ⚠️ 块大小是**字符数**，⛔ 不是 token 数

`chunk_size=500` 是**字符**。⇒ 中文 500 字 ≈ 更多 token。
⚠️ **别拿它去估算 embedding / LLM 的成本**（成本按 token 算，在 `token_tracker`）。

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/api_v1_rag.md` | 唯一调用点所在的模块（文档上传链） |
| 预处理模块（`api/document_preprocessor.py`） | ⛔ **它还没有 spec**（221 行）⇒ 本表**不给路径**（给了就是断链）。它在本链的**上游**：切块前先过它 |
| `docs/specs/embedding_client.md` | 切出来的块**下一步去哪**（逐块算向量 = 真花钱） |
| `docs/decisions/DEC-013-M6测试分层与CI接法.md` | 同仓对"非法取值该 422 而不是静默兜底"的裁定（本文件是**反例**） |
