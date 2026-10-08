# 施工单 · embedding 切 `qwen3.7-text-embedding-flash` ＋ 从 `.env` 读 ＋ 重烤（**`①b` 的一组**）

> **For agentic workers:** 逐步照做。⚠️ **每一步的「判据」都要真跑并看到输出** —— ⛔ **退出码 0 不算**
> （本仓纪律：「拿『动作成功』当『结果正确』」这一族栽过多次）。

**Goal:** 把 embedding 模型**从 `.env` 读**（新变量 **`EMBEDDING_MODEL_MAIN`**），
切到 `qwen3.7-text-embedding-flash`，并把由此产生的**维度变更 + 重烤**一次做干净。

**依据（⛔ 本单不自拟裁定 —— 全部来自已有决策）:**
- `docs/decisions/DEC-098-demo单容器化设计-存储限流与边界.md` **§二·2**（模型名写死那一处）·
  **§2.1**（模型名 + 维度 + 表定义 = **三件套** + 启动自检）· **§2.2**（**全切**，本地也切）
- 变量名 **`EMBEDDING_MODEL_MAIN`** —— ✅ **2026-10-08 业务方定**（⚠️ 此前它**全仓只出现过 1 次**，
  在 `DEC-098` 的关联表里，是**上一轮会话的提议**，⛔ 不是已存在的名字）

## Global Constraints

- 🔴 **`safe_math` 无关，但同一条纪律适用**：**⛔ 不许"模型名可配了就算完"** ——
  只改模型名 ⇒ 维度对不上；**最危险的不是报错，是"维度恰好相同"时不报错**（`DEC-098` §2.1）。
- **判据一律写成可打印的命令**，并做**取反检验**。
- **commit 前必须跑** `bash scripts/ci-local.sh`，⛔ **别抄本单里的数**。
- 🔴 **PR 按【类型】攒**：本组与 `①b` 其余部分**同属 demo 化** ⇒ 尽量**同 PR**；
  ⛔ 别一笔一 PR。**动手前先问「这笔跟哪个已开的 PR 同类？」**
- ⛔ **`git checkout -- <file>` 回到的是 `HEAD`** ⇒ 做反证要还原文件时**先 `cp` 备份再 `cp` 回来**。
- ⛔ **不加新依赖**（`PyYAML` 那类教训：不为一件小事给 demo 镜像增肥）。

---

## 🔴 顺序：本单分 **A / B 两段**（2026-10-08 业务方裁定）

> **业务方原话（2026-10-08）**：「**语料重建，肯定是要再重烤之前的……这个要先做，
> 不然垃圾数据重烤了，有什么用？？**」
> ⇒ **重烤那一次，是给【乙产出的优质语料】烤的，⛔ 不是给现在那 129 条烤的。**
> ✅ 仓里**早就这么裁了** —— `DEC-098` §二·0 的对照表：
> **甲（机制）→ 乙（语料重建）→ 重烤一次 → `⑤`**。
> ⚠️ **本单初稿把 Task 6 / Task 8 排在乙之前，是错的** —— 2026-10-08 按业务方判断拆开。

| 段 | 内容 | 什么时候能做 |
|---|---|---|
| **🅰 A 段 · 代码就绪** | `EMBEDDING_MODEL_MAIN` 进 `config.py` · `get_embedding` 从 env 读 · 缓存键加模型名 · `memory_store` 收口 · 单价登记 · 自检函数 · **实测维度**（只读） | ✅ **现在就能做** |
| **🅱 B 段 · 切换 + 重烤** | 重建表（维度）· 重烤 | 🔴 **必须等「乙 · 语料重建」产出语料之后** |

### 🔴 A 段有一个**前提**，⛔ 别忽略

A 段的设计前提是「**默认值仍是 `text-embedding-v2` ⇒ 行为一字节不变**」。
🔴 **但业务方已于 2026-10-08 把 `.env` 改成了 `EMBEDDING_MODEL_MAIN=qwen3.7-text-embedding-flash`**
（实测：`.env:4` 有那一行 · `grep -rn 'EMBEDDING_MODEL_MAIN' api/` ⇒ **0 命中** ⇒ **它现在是【死的】**）。

⇒ 🔴 **A 段的代码一接上，那一行立刻生效** —— 而本地库还是 v2 的 **1536 维**向量，
查询用 flash（**1024 维**）⇒ **本地检索当场报错**
（`expected 1536 dimensions, not 1024`；⚠️ **这是"好的失败"** —— 它响亮；
**真正危险的是维度恰好相同**时的静默错配，见 `DEC-098` §2.1）。

**⇒ 二选一（A 段落地【之前】必须定）：**

| | 做法 | 代价 |
|---|---|---|
| **甲** | A 段落地**之前**，把 `.env` 那行**暂时改回** `EMBEDDING_MODEL_MAIN=text-embedding-v2`；**B 段再翻成 flash** | ⚠️ 要动 `.env` **两次**（它 gitignored，⛔ 不进仓） |
| **乙** | `.env` 保持 flash，**接受本地检索在 B 段之前是坏的** | 🔴 那段时间**本地 `/chat` 不可用**；⚠️ **CI 不受影响**（CI 用的是 dummy 环境） |

📌 **本单按【甲】写**（这样 A 段才真的行为中立）；若选【乙】，
把 A 段里「行为不变」那几句**当反话读**。

---

## §范围（**先说清本单是什么、⛔ 不是什么**）

| | 内容 |
|---|---|
| ✅ **本单做** | 模型名从 env 读（**两处**）· 切 flash · 缓存键加模型名 · 单价登记 · 维度三件套 · 启动自检 · **重烤** · 文档同步 |
| ⛔ **本单不做** | **单容器化 / PG→SQLite 迁移 / 限流 / 边界标注 / 前端一张页 / 语料契约** —— 那些是 `①b` 的**其余组**，本单只做其中的 **embedding 与重烤** |
| ⛔ **也不做** | **`N12`**（`approval_events` 表 + `schema.sql`）—— 独立一条。⚠️ **但它与本单有一处交汇**：都要动 `api/schema.sql`（那是**生成物**）⇒ **谁先做谁生成，后者只需确认** |

⚠️ **一句边界**：本单产出的是**代码 + 命令**，⛔ **不是 demo 产物**。demo 打包是 `①b` 其余组的事。

---

## 🅰 A 段 · **代码就绪**（✅ 现在就能做 · ⛔ 不改行为，前提见上面「A 段有一个前提」）

> Task 0 · 1 · 2 · 3 · 4 · 5 · 7 属于 A 段。做完 A 段，**系统行为应与改前【逐字相同】**
> （默认值仍是 `text-embedding-v2`）—— ⚠️ **除非 `.env` 那行没改回去**（见上）。

---

## Task 0 · 🔴 **先实测维度，⛔ 不照抄"1024"**

**Files:** 无（只读；产出一个**实测值**，下面 Task 6 要用）

**为什么**：`DEC-098` §2.1 那张表里写的「**1024**」来源是**官方资料**，**我们没实调过**
（原文：「支持 256/512/768/1024 维，**默认为 1024**」）。
⚠️ **表都要按它重建了，这个数必须是【我们量的】那个** —— 这正是 §2.1 自己那条「启动自检」的道理。

- [ ] **Step 1: 拿现行的 key 实调一次**

```bash
cd /Users/heweidong/Desktop/Product/agent-projects/projects/fastapi-rag-agent
venv/bin/python - <<'PY'
import os, json, urllib.request
from dotenv import load_dotenv
load_dotenv()
key = os.environ["DASHSCOPE_API_KEY"]
body = json.dumps({"model": "qwen3.7-text-embedding-flash",
                   "input": "人工智能正在改变世界"}).encode()
req = urllib.request.Request(
    "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    data=body,
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    d = json.loads(r.read())
print("模型:", d.get("model"))
print("维度:", len(d["data"][0]["embedding"]))
print("usage:", d.get("usage"))
PY
```

**判据**：打印出**维度**与**模型名**。
🔴 **把维度记下来**（下面 Task 6 的 `1536 → ??` 用**这个数**，⛔ 不用 1024 这个传闻值）。
⚠️ **若这一步就报错**（模型名不存在 / 无权限 / 端点不对）⇒ **停在这里**，把报错原文报给业务方 ——
⛔ **别往下做**（后面的表重建全都建立在"这个模型能调通"之上）。

> 🔴 **顺带核一件事**：`docs/契约/环境变量.md:67` 现在写着 embedding「**⛔ 不能换，必须 DashScope**」。
> Step 1 如果通了，就说明**它在同一个端点上** ⇒ 那句话要**一并更正**（Task 9）。

---

## Task 1 · `EMBEDDING_MODEL_MAIN` 进 `api/config.py`

**Files:**
- Modify: `api/config.py`
- Modify: `api/test_max_tokens_wiring.py`（**只在 Task 5 那条守卫红时**才动；先别动）

**Interfaces:**
- Produces: `config.EMBEDDING_MODEL_MAIN: str`（供 Task 2 / Task 3 / Task 7 用）

- [ ] **Step 1: 读一眼现状（⛔ 不凭印象加）**

```bash
sed -n '50,56p' api/config.py
```
**现有约定**（照它写）：`LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "deepseek-v4-flash")`
—— **env 优先 + 模块级默认值**，默认值**只有一处**。

- [ ] **Step 2: 加变量**

在 `LLM_MODEL_CHAT` 那行**下面**追加：

```python
# ==================== Embedding —— 端点 = 阿里云百炼 DashScope ====================
# 🔴 2026-10-08：模型名从【写死在 `embedding_client.get_embedding()` 签名里】收拢到这里。
#    变量名由业务方定为 `EMBEDDING_MODEL_MAIN`（`DEC-098` 关联表里那个提议）。
# ⚠️ **改这里必须连【维度】一起改**（`DEC-098` §2.1：模型名 + 维度 + 表定义 = 三件套）
#    —— 只把模型名变可配 ⇒ 维度对不上；而**最危险的是"维度恰好相同"**：不报错，但
#    老向量与新查询向量**不同源** ⇒ 检索结果全是垃圾。
# ⚠️ 默认值 = 现状（`text-embedding-v2`）⇒ **本行落地时行为不变**，切换是【改 .env】那个动作。
EMBEDDING_MODEL_MAIN = os.getenv("EMBEDDING_MODEL_MAIN", "text-embedding-v2")
```

- [ ] **Step 3: 判据（跑）**

```bash
venv/bin/python -c "import config; print(config.EMBEDDING_MODEL_MAIN)"
# ⇒ text-embedding-v2（未设 env 时）
EMBEDDING_MODEL_MAIN=xxx venv/bin/python -c "import config; print(config.EMBEDDING_MODEL_MAIN)"
# ⇒ xxx（env 优先）
```
🔴 **反证**：把默认值改成别的 ⇒ 上面第一条输出跟着变 ⇒ 尺子在量那一行。

- [ ] **Step 4: `.env.example` 同步**（Task 9 一起提交也行，但**别漏**）

在 `LLM_MODEL_CHAT` 那两行注释**下面**加：

```
# EMBEDDING_MODEL_MAIN=text-embedding-v2   # embedding 模型（⚠️ 换它必须连维度一起改！见 DEC-098 §2.1）
```

---

## Task 2 · `embedding_client.get_embedding()` 从 env 读（**站点①**）

**Files:**
- Modify: `api/embedding_client.py:40`

**Interfaces:**
- Consumes: `config.EMBEDDING_MODEL_MAIN`（Task 1）
- Produces: `get_embedding(text, model=None)` —— `model=None` 时**解析成** `EMBEDDING_MODEL_MAIN`

⚠️ **签名要保留 `model=` 形参** —— `api/test_isolation.py:357/391/416/493` 有 4 处
`monkeypatch.setattr(..., "get_embedding", lambda text, model=None: ...)`，
⛔ **删掉形参会让那 4 处 `TypeError`**（它们已经写成 `model=None` 了，说明**签名早就预留了**）。

- [ ] **Step 1: 写失败用例**

新建 `api/test_embedding_model_from_env.py`：

```python
"""embedding 模型名必须**从 env 读** —— ⛔ 不许再写死在签名里（`DEC-098` §二·2）。

## 为什么
`get_embedding(text, model="text-embedding-v2")` 把模型名写死在**形参默认值**里 ⇒
换模型要改代码。而 embedding 的模型名**必须与新变量的维度一起管**（`DEC-098` §2.1）。
"""


def test_default_comes_from_config(monkeypatch):
    """不传 `model` ⇒ 走 `config.EMBEDDING_MODEL_MAIN`（⛔ 不是字面量）。"""
    import config
    import embedding_client as ec

    monkeypatch.setattr(ec.config, "EMBEDDING_MODEL_MAIN", "sentinel-model-name")
    seen = {}

    class _FakeEmbeddings:
        def create(self, input, model):
            seen["model"] = model
            class _R:
                data = [type("D", (), {"embedding": [0.0] * 4})()]
                usage = type("U", (), {"prompt_tokens": 3})()
            return _R()

    monkeypatch.setattr(ec, "_get_client", lambda: type("C", (), {"embeddings": _FakeEmbeddings()})())
    monkeypatch.setattr(ec, "get_cached_embedding", lambda t: None)
    monkeypatch.setattr(ec, "set_cached_embedding", lambda t, e: None)
    monkeypatch.setattr(ec, "record_usage", lambda **k: None)

    ec.get_embedding("你好")
    assert seen["model"] == "sentinel-model-name"


def test_explicit_model_still_wins(monkeypatch):
    """显式传 `model=` ⇒ **听它的**（`test_isolation` 那 4 处靠这个形状活着）。"""
    import embedding_client as ec
    seen = {}

    class _FakeEmbeddings:
        def create(self, input, model):
            seen["model"] = model
            class _R:
                data = [type("D", (), {"embedding": [0.0] * 4})()]
                usage = type("U", (), {"prompt_tokens": 3})()
            return _R()

    monkeypatch.setattr(ec, "_get_client", lambda: type("C", (), {"embeddings": _FakeEmbeddings()})())
    monkeypatch.setattr(ec, "get_cached_embedding", lambda t: None)
    monkeypatch.setattr(ec, "set_cached_embedding", lambda t, e: None)
    monkeypatch.setattr(ec, "record_usage", lambda **k: None)

    ec.get_embedding("你好", model="explicit-model")
    assert seen["model"] == "explicit-model"
```

- [ ] **Step 2: 跑，确认它失败**

```bash
venv/bin/python -m pytest api/test_embedding_model_from_env.py -q
# ⇒ test_default_comes_from_config 失败（现在走的是写死的 text-embedding-v2，不是哨兵值）
```

- [ ] **Step 3: 改实现**

把 `:40` 那行改成：

```python
def get_embedding(text: str, model: str | None = None) -> list:
    """带缓存的 Embedding 调用。

    🔴 2026-10-08（`DEC-098` §二·2）：`model` 的**默认值不再写死** —— 走
        `EMBEDDING_MODEL_MAIN`（先 env 后 `config`，与 `_get_client()` 取 key **同一种写法**）。
        ⛔ **别把默认值改回字面量** —— 换模型要改代码，而那正是本次要消掉的。
    ⚠️ **形参 `model` 必须保留**：`api/test_isolation.py` 有 4 处按 `lambda text, model=None:` 打桩。
    """
    if model is None:
        model = os.getenv("EMBEDDING_MODEL_MAIN") or config.EMBEDDING_MODEL_MAIN
```

（函数体其余**一字不动**）

- [ ] **Step 4: 跑，确认全绿 + **那 4 处打桩没被打破**

```bash
venv/bin/python -m pytest api/test_embedding_model_from_env.py -q          # ⇒ 2 passed
venv/bin/python -m pytest api/test_isolation.py -q -m "not needs_db"       # ⇒ 全绿
```

- [ ] **Step 5: Commit**（本组最后一个 Task 一起提交也行 —— ⛔ 别一件事没做完就 commit）

---

## Task 3 · 🔴 **缓存键加模型名**（**这条不做，前两个 Task 会静默出错**）

**Files:**
- Modify: `api/cache.py:14-29`
- Modify: `api/test_embedding_model_from_env.py`（加用例）

**为什么（🔴 本单最值钱的一条）**：`cache.py:16` 的键是 `"emb:" + md5(text)` —— **模型名不在键里**，
TTL **24 小时**。⇒ **换了模型之后，同一句话会命中【旧模型】的向量** ⇒
而它**不报任何错**（维度对不上时 pgvector 会报；**维度恰好相同时连报都不报**）。
📌 这就是 `DEC-098` §2.1 点名的那类**静默错配**，只是入口在**缓存**上。
✅ **业务方 2026-10-08 裁：缓存键加模型名。**

- [ ] **Step 1: 先用一条判据证明它现在真的会错**

```bash
grep -n 'def get_cache_key' -A 3 api/cache.py
# ⇒ :16  return "emb:" + hashlib.md5(text.encode()).hexdigest()   ← 模型名不在键里
```
🔴 **反证**：把模型名加进键 ⇒ **同一命令打出来的不再是那一行**。

- [ ] **Step 2: 写失败用例**

追加到 `api/test_embedding_model_from_env.py`：

```python
def test_cache_key_separates_models():
    """🔴 换模型必须换缓存键 —— ⛔ 否则会命中旧模型的向量（静默错配）。"""
    import cache

    assert cache.get_cache_key("同一句话", "model-a") != cache.get_cache_key("同一句话", "model-b")
    assert cache.get_cache_key("同一句话", "model-a") == cache.get_cache_key("同一句话", "model-a")
    assert cache.get_cache_key("另一句话", "model-a") != cache.get_cache_key("同一句话", "model-a")
```

- [ ] **Step 3: 跑，确认失败**（现在 `get_cache_key` 只收 1 个位置参数 ⇒ `TypeError`）

```bash
venv/bin/python -m pytest api/test_embedding_model_from_env.py::test_cache_key_separates_models -q
```

- [ ] **Step 4: 改 `api/cache.py`**

```python
def get_cache_key(text: str, model: str) -> str:
    """缓存键 = **模型名 + 文本 MD5**。

    🔴 2026-10-08：`model` 是**新加的必填形参**，⛔ 不是可选。
      改前是 `"emb:" + md5(text)` —— **模型名不在键里** ⇒ 换 embedding 模型后，
      同一句话会**命中旧模型的向量**，而**不报任何错**（`DEC-098` §2.1 那类静默错配）。
    ⚠️ **`model` 不设默认值**：漏传要 `TypeError`，⛔ 不是悄悄回落到某个默认桶
      （与 `tool_visualizer.get_all_traces(user_name)` 同一条取向）。
    ⚠️ **键格式变了 ⇒ 旧 `emb:*` 键自然失效**（不必手工 flush，24h 后也会没）。
    """
    return "emb:" + model + ":" + hashlib.md5(text.encode()).hexdigest()
```

并把两个调用点（`:20` / `:28`）改成接收并透传 `model`：

```python
def get_cached_embedding(text: str, model: str):
    key = get_cache_key(text, model)
    ...

def set_cached_embedding(text: str, embedding: list, model: str, expire_seconds: int = 86400):
    key = get_cache_key(text, model)
    ...
```

- [ ] **Step 5: 把 `embedding_client` 的两处调用连同模型名传下去**

`api/embedding_client.py`：`cached = get_cached_embedding(text, model)` ·
`set_cached_embedding(text, embedding, model)`。

- [ ] **Step 6: 判据（跑）**

```bash
venv/bin/python -m pytest api/test_embedding_model_from_env.py -q          # ⇒ 3 passed
grep -rn 'get_cached_embedding(\|set_cached_embedding(\|get_cache_key(' api/ --include='*.py' | grep -v 'def \|^api/test_'
# 🔴 判据：**每个调用点都带 model** —— 逐行看，⛔ 不是数条数
venv/bin/python -m pytest api/ -q -m "not integration and not needs_db"    # ⇒ 全绿
```

⚠️ **别忘了 `query_rewriter.py` 有它自己的 `_get_cache_key(prefix, text, extra)`** ——
那是**改写缓存**、与 embedding 无关（`api/cache.py:37` 的注释区分过）⇒ ⛔ **别顺手一起改**。

---

## Task 4 · `memory_store.py` 的 embedder 也走同一个变量（**站点②**）

**Files:**
- Modify: `api/memory_store.py:30-37`

**为什么**：你说的是「**全局**的 embedding 模型要全部改成从 .env 加载」—— 这是**第二处**写死：
`memory_store.py:34` 的 mem0 embedder `"model": "text-embedding-v2"`。
⚠️ **它不走 `config.validate_config()`**（`docs/契约/环境变量.md:145` 明写），
而 `memory_store.py:33` 的 `os.getenv("DASHSCOPE_API_KEY")` 是**裸 `os.getenv`** ——
⇒ **它自成一个站点**，⛔ 收口时容易漏。

- [ ] **Step 1: 改**

```python
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("DASHSCOPE_API_KEY") or config.DASHSCOPE_API_KEY,
                # 🔴 2026-10-08：与 `embedding_client` **同一个变量** —— ⛔ 不许在这里另写一份字面量
                #    （本仓「一个名字两个来源必然漂移，而漂移是静默的」）。
                "model": os.getenv("EMBEDDING_MODEL_MAIN") or config.EMBEDDING_MODEL_MAIN,
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            }
        }
```
⚠️ **先确认该文件已经 `import config`**（`grep -n '^import config\|^from config' api/memory_store.py`）；没有就按文件既有风格补上。

- [ ] **Step 2: 判据（跑）**

```bash
grep -n 'text-embedding-v2' api/memory_store.py    # ⇒ 应【无命中】
grep -rn 'text-embedding-v2' api/ --include='*.py' | grep -v '^api/test_'
# 🔴 判据：**活代码里一处都不该再有**（剩下的只该在测试的断言里，见 Task 5）
venv/bin/python -m pytest api/test_memory*.py -q 2>/dev/null || echo "（没这份用例就跳过）"
```

---

## Task 5 · 单价表加新模型（**那条守卫会红 —— 那是它在干活**）

**Files:**
- Modify: `api/token_config.py`（`MODEL_PRICING`）
- Modify: `api/test_token_config.py:106`

**为什么**：`token_tracker.record_usage(model=...)` 按 `MODEL_PRICING` 查价；
**没登记 ⇒ 落兜底价 0.003/0.006**（`DEC-098` §2.1 实测：**高报 24 倍**）。
而仓里有一条守卫 **`test_models_actually_in_use_have_explicit_pricing`** 专防这件事 ⇒
**它会在切完模型后转红** —— `DEC-098` §2.1 原话：「**那是它在干活，⛔ 别绕过它。**」

⚠️ **单价先核，⛔ 别照抄**：`DEC-098` §2.1 写新模型 **0.125 元/百万**
（⇒ 本表单位是**元/1000 tokens** ⇒ **0.000125**）；
🔴 **但它给 `text-embedding-v2` 写的是 0.7 元/百万，而本表登记的是 `0.0005`（= 0.5 元/百万）** ——
**两个数对不上** ⇒ ⛔ **别信任何一个，去阿里云控制台/价目页核一次**，并把**出处**写进注释。

- [ ] **Step 1: 核单价**（人工：阿里云百炼价目页 / 控制台）。把**链接或截图日期**记下来。

- [ ] **Step 2: 加一行**

```python
    # 🔴 2026-10-08：新 embedding 模型（`DEC-098` §2.1）。⚠️ 单价来源：<你核到的那页>（<日期>）。
    #    ⚠️ 落兜底价 (0.003/0.006) 会**高报 24 倍** ⇒ 这行是承重的。
    "qwen3.7-text-embedding-flash": {"prompt": 0.000125, "completion": 0},
```

- [ ] **Step 3: 改 `api/test_token_config.py:106`**

```bash
sed -n '100,110p' api/test_token_config.py
```
✅ **2026-10-08 业务方裁定：旧那行 `text-embedding-v2` 【不留，直接删除】。**
原话：「**没有用了，留下是污染。**」

⇒ 本步要做**两件**：
1. **删** `api/token_config.py` 里 `"text-embedding-v2"` 那一行；
2. **改** `api/test_token_config.py` 那条断言（它现在钉的正是这个串 ⇒ **删了它必红**）。

⚠️ **但先看清那条断言在测什么**（下面这条命令），⛔ 别把"断言红"当成"删错了"：
```bash
sed -n '100,110p' api/test_token_config.py
```
🔴 **一个要当场判的岔口**：若那条断言是**通用形状**（"在用的模型都要登记"），
那它删掉旧模型后**应该照样绿**（因为 `text-embedding-v2` 不再是"在用的"）；
若它是**写死了 `"text-embedding-v2"` 这个具体名字**，那把那一行改成新模型名。
⇒ ⛔ **别为了让它绿而把断言删掉** —— 那等于把守卫拆了。

⚠️ **一条诚实的边界**：删掉旧单价后，**历史上的 `token_usage_logs` 里那些 `text-embedding-v2` 记录**
会落**兜底价**（`0.003/0.006`）⇒ 旧账会**偏高估**。
🔴 **业务方已裁「不留」** ⇒ 这是**已知代价**，⛔ 不再讨论；但**记在这里**，免得日后有人看到旧账对不上又去查。

- [ ] **Step 4: 判据（跑）**

```bash
venv/bin/python -m pytest api/test_token_config.py -q      # ⇒ 全绿
venv/bin/python -m pytest api/test_token_config.py::test_models_actually_in_use_have_explicit_pricing -q
# 🔴 反证：把新模型那行【注释掉】⇒ 这条必须【红】。不红 ⇒ 它没在守这件事。
```

---

## 🅱 B 段 · **切换 + 重烤**（🔴 **必须等「乙 · 语料重建」产出语料之后**）

> 🔴 **这一段是本单初稿排错的地方。** 业务方 2026-10-08 原话：
> 「**语料重建，肯定是要再重烤之前的……这个不然垃圾数据重烤了，有什么用？？**」
> ⇒ **现在那 129 条（含重复 / 低质）【不烤】** —— 重烤是给乙的语料做的。
> ✅ 与 `DEC-098` §二·0 的顺序（**甲机制 → 乙语料 → 重烤一次 → `⑤`**）一致。
> ⚠️ **B 段开工的前置条件（可打印）**：乙产出的语料**已经落在【语料契约】规定的目录里**
> （契约本身还没定 —— `DEC-098` §五 占位 1，属 `①b` 其余组）。
> ⛔ **在那之前，B 段一步都不许做。**
>
> ⚠️ **B 段的成本要按 §2.3 的额度重算**：现库 129 条 ≈ 1 万 token；
> **乙的语料规模未知** ⇒ 用 `DEC-098` §2.3 那条 **TPM 100 万/分钟**与**免费 100 万 token**去核。

### 🔴🔴 B 段的**范围是两个语料库，⛔ 不是一个**

> **业务方原话（2026-10-08）**：「……**我们现在做的数据库语料。后面重烤的时候，
> `isolation_a/b/c` 也要把他们的语料重烤进去。**」

| # | 烤什么 | 为什么不能漏 |
|---|---|---|
| 1 | **demo 语料库**（乙产出的） | 这是本来就要做的 |
| 2 | 🔴 **`isolation_a/b/c` 的 9 篇常驻语料** | 它们靠 `requested_by` 隔离，**和 demo 语料在【同一个 `documents` 表】里**。<br>⚠️ **换模型后它们的向量一样作废** ⇒ 只烤 demo 语料 ⇒ **三家隔离测试当场全废** |

⚠️ **为什么这条最容易漏**：那 9 篇**早就灌好了**（`DEC-071`），看着"已经完事" ——
**但换 embedding 模型会让它们的向量一起失效**，而**没有任何门会红**
（维度对得上时静默返回垃圾；对不上时报错，但那是**跑测试时才发现**）。
📌 **判据**：`docs/说明/语料要求.md` **§3.4** 那条 `GROUP BY requested_by` 的 SQL ——
**每一行的 `count(embedding)` 都必须 == `count(*)`**。

---

## Task 6 · 维度三件套（**模型名 + 维度 + 表定义**）

**Files:**
- Modify: `api/db.py:67`（`CREATE TABLE documents` 的 `embedding vector(1536)`）
- Modify: `api/schema.sql:248`（**生成物**，见下）
- Modify: `api/test_isolation.py:191`（`_PROBE_DIM = 1536`）
- Modify: `docs/契约/数据模型.md:44`

⚠️ **用 Task 0 实测出来的那个维度**，⛔ 不用传闻的 1024。

- [ ] **Step 1: 先把"维度写死在哪"数清（⛔ 别只改一处）**

```bash
grep -rn 'vector(1536)\|1536' api/db.py api/schema.sql api/test_isolation.py | grep -v '^\s*#'
```
**2026-10-08 实测**（⛔ 读的人**重跑**，别抄）：`api/db.py:67` · `api/schema.sql:248` · `api/test_isolation.py:191`。
⚠️ `api/db.py` 更上面还有 `CREATE EXTENSION IF NOT EXISTS vector;` —— **那行不动**。

- [ ] **Step 2: 重建表（**已裁：直接重建 + 重烤**）**

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U postgres -d rag_db -c '\d documents'
# ⚠️ 先看现状（维度 / 索引 / 行数）—— 判据是【输出】，⛔ 不是"命令跑了"

# ① 备份现有原文（重烤要它的 content）
docker compose exec -T postgres psql -U postgres -d rag_db \
  -c "\copy (SELECT id, content, source, requested_by FROM documents) TO '/tmp/documents_backup.csv' CSV HEADER"
docker compose exec -T postgres cat /tmp/documents_backup.csv > /tmp/documents_backup.csv

# ② 重建（维度换成 Task 0 的实测值）
docker compose exec -T postgres psql -U postgres -d rag_db <<'SQL'
DROP INDEX IF EXISTS documents_embedding_idx;   -- ⚠️ 先看 \d documents 里的真实索引名再写
TRUNCATE documents RESTART IDENTITY;
ALTER TABLE documents DROP COLUMN embedding;
ALTER TABLE documents ADD COLUMN embedding vector(<实测维度>);
SQL
```

⚠️ **`DROP INDEX` 那句要先看真实索引名**（`api/db.py:128` 建的是 ivfflat；`\d documents` 会打出来）。
⚠️ **重建后要重跑 `api/db.py` 的建表路径**（它是 `CREATE TABLE IF NOT EXISTS` ⇒ 表在就不重建）
⇒ **最稳的做法：`DROP TABLE documents` 后让应用自己建**（`api/db.py` 会在启动时建）。

- [ ] **Step 3: 改代码里写死的维度** —— ✅ **2026-10-08 业务方已裁：⛔ 不抽常量，逐处改**

🔴 **先跑这条数一遍**（⛔ 别只改 `db.py` 一处 —— 实测**活代码/测试里共 5 处**）：

```bash
grep -rn '1536' api/*.py api/schema.sql | grep -v '^\s*#'
```
**2026-10-08 实测命中（⛔ 读的人重跑，别抄）**：
`api/db.py:67`（建表）· `api/test_isolation.py:191`（`_PROBE_DIM`）·
`api/test_rag_search.py:222` · `api/test_rag_billing_wiring.py:274` · `:305`（三处 `[0.0] * 1536`）
—— 另有两处是 **docstring / 注释**（`api_v1_rag.py:86/186` · `evaluate_with_ragas.py`），**一并改口径**。

**改法**：每处 `1536` ⇒ **Task 0 实测出来的那个维度**。
⚠️ 那三处 `[0.0] * 1536` 是**假向量**，维度错了 PG 会**响亮报错**（不会静默）⇒ 改对即可。

⛔ **不抽 `EMBEDDING_DIM` 常量**（业务方 2026-10-08 裁）—— 理由：
① **Task 7 的启动自检已经把"维度漂移"从静默变成响亮**（**运行时检查 > 少写一个字面量**）；
② 实测**抽了也只解决 5 处里的 1 处**（另 4 处在测试里，且 `api/schema.sql` 是生成物更管不着）；
③ 改行为面（SQL 变 f-string），而 B 段之后本仓**基本冻结**。

- [ ] **Step 4: `api/schema.sql`（⛔ 它不是手改的）**

它是 `pg_dump --schema-only` 的**生成物**，头部明写「⛔ 本文件是【生成的】，不要手改」。
按 `docs/待办总表.md` 的 **`N12`** 那条判据重导：

```bash
docker compose exec -T postgres pg_dump -U postgres -d rag_db --schema-only --no-owner --no-privileges > api/schema.sql
grep -n 'embedding' api/schema.sql      # ⇒ 维度应是新值
```
🔴 **这里与 `N12` 交汇**：`N12` 也要重导这份文件（它要补 `approval_events`）。
⇒ **谁先做谁导，后者只需确认**（两次导出结果一致）。

- [ ] **Step 5: 判据（跑）**

```bash
grep -rn 'vector(1536)' api/ | grep -v '^api/test_'   # ⇒ 无命中
venv/bin/python -m pytest api/test_isolation.py -q -m "not needs_db"   # ⇒ 全绿
```

---

## Task 7 · 启动自检：**拿模型实测一次维度，对不上就响亮地断**

**Files:**
- Modify: `api/config.py` 或 `api/main.py:709`（`validate_config()` 的调用处）

**为什么（`DEC-098` §2.1 原文）**：「**模型名与维度一起管**，且**启动时自检** ——
拿模型名**实测一次维度**，与表定义对不上就**响亮地断**（⛔ 不是警告、不是回落）」。

🔴 **为什么必须有**：`DEC-098` §2.1 说得很直白 —— 「**真正危险的是"维度恰好相同"的情况**：
**不报任何错**，但老向量与新查询向量**不同源** ⇒ **检索结果全是垃圾**」。
自检挡不住"同维不同源"那一种，但它能挡住**配置漂移**（.env 改了、表没改）。

- [ ] **Step 1: 实现在 `_get_client()` 同族的惰性路径上**（⛔ 不在 import 期打网络）

⚠️ **别放进 `validate_config()`** —— 它跑在 `main.py:709` 的 startup 里，**可以**打网络；
但 `embedding_client` 的取向是**惰性 + 第一次调用时才断**（`DEC-082` 的教训：
**import 期打网络会炸掉整条 import 链**）。⇒ **建议挂成一个显式的、可单测的函数**：

```python
def assert_model_dimension(expected: int) -> None:
    """启动自检：**拿真模型实测一次**，与表定义对不上就断（`DEC-098` §2.1）。

    ⛔ **不是警告** —— 维度不匹配时检索**不是变慢、是变错**。
    ⚠️ 它在 **startup** 里调（`api/main.py` 的 `validate_config()` 旁边），
       ⛔ **不在 import 期** —— 那会炸掉整条 import 链（`DEC-082`）。
    """
```

- [ ] **Step 2: 用例（拿桩测，⛔ 不真打网）**

```python
def test_dimension_mismatch_raises(monkeypatch):
    """维度对不上 ⇒ **响亮地断**（⛔ 不是 warning、⛔ 不是回落）。"""
    import pytest, embedding_client as ec
    monkeypatch.setattr(ec, "get_embedding", lambda text, model=None: [0.0] * 8)
    with pytest.raises(EnvironmentError, match="维度"):
        ec.assert_model_dimension(1536)
```

- [ ] **Step 3: 判据（跑）**

```bash
venv/bin/python -m pytest api/test_embedding_model_from_env.py -q
# 🔴 反证：把 `pytest.raises` 换成 `pytest.warns` ⇒ 用例必须【红】（它测的是"断"不是"提醒"）
```

---

## Task 8 · **重烤**（命令级 · 🅱 B 段 —— 🔴 只烤**乙的语料**，⛔ ⛔ 不烤现在那 129 条）

**Files:** 无（一个一次性脚本 + 判据；⚠️ **脚本要不要入库，见 Step 4**）

> 🔴🔴 **B 段的正身 —— 烤的是【乙的语料】，⛔ 不是现在这 129 条。**
> 业务方 2026-10-08 原话：「**语料重建，肯定是要再重烤之前的……这个要先做，
> 不然垃圾数据重烤了，有什么用？？**」
> ⇒ ⛔ **不许在乙产出语料之前跑本 Task**（跑出来的就是"垃圾重烤一遍"）。
>
> ⚠️ **但下面这几步【仍然成立】**，因为：
> ① **Task 6 备份的 21 kB 不是"要丢的垃圾"** —— `DEC-098` §二·0 说的是
>    「**有些**没有的、低价值或者没用的就不要烤了」⇒ **是有取舍的**，⛔ 不是全弃；
>    乙的筛选**可能**要从这批里挑，所以**备份必须留到乙做完**。
> ② **限速**（Step 2 的脚本要按 `DEC-098` §2.3 的 **TPM 100 万/分钟** 与 **批量 20 行** 来写）。

**口径（`DEC-098` §四 4.1 ⑦ 实测 · ⚠️ **只对现在那 129 条成立**）**：
`documents` 表 **129 chunks · 9,000 字符 · 正文 21 kB** ⇒ 全量重烤 **≈ 0.001 元**、占额度 **≤ 1%**。
🔴 **乙的语料规模未知 ⇒ B 段开工时【重算】**，并拿 `DEC-098` §2.3 的**免费额度 100 万 token**去核。

🔴 **重烤 = 只重算向量，⛔ 不重新切分** —— `documents.content` **还在**（Task 6 Step 2 备份过），
而分块策略**没变**。⚠️ 「重新切分」属于 `乙 · 语料重建`，**是另一件事**。

- [ ] **Step 1: 把语料导进去（🔴 **乙产出的**那份，⛔ 不是现在这 129 条）**

> 🔴 **别忘了第二个语料库** —— `isolation_a/b/c` 的 9 篇**也要一起烤**（见上面「B 段的范围是两个语料库」）。
> 它们**已经在库里**（`DEC-071` 灌的）⇒ **不用重灌，但向量要重算**。
> ⇒ **Step 2 的重算脚本要按 `requested_by` 分组跑，⛔ 不是只跑 demo 那一桶。**

⚠️ **导谁的、从哪导** —— 由【语料契约】定（`DEC-098` §五 占位 1，**还没定**）。
⛔ **契约没定之前，本步写不下去**；下面给的是**形状**，⛔ 不是可直接跑的命令：

```bash
# ⚠️ 占位：等「语料契约」定了放哪、什么格式，再填这一条
# docker compose exec -T postgres psql -U postgres -d rag_db -c "\copy ... FROM '<乙的语料>' CSV HEADER"
docker compose exec -T postgres psql -U postgres -d rag_db -c "SELECT count(*) FROM documents;"
# ⇒ 报出实际条数（⛔ 别期待 129 —— 乙产出多少就是多少）
```


- [ ] **Step 2: 重算向量**

```bash
venv/bin/python - <<'PY'
import psycopg2, embedding_client as ec
conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="rag_db",
                        user="postgres", password=__import__("os").environ["POSTGRES_PASSWORD"])
cur = conn.cursor()
cur.execute("SELECT id, content FROM documents ORDER BY id")
rows = cur.fetchall()
print(f"待重烤 {len(rows)} 条")
for i, (doc_id, content) in enumerate(rows, 1):
    vec = ec.get_embedding(content)                      # ⚠️ 走的是新模型 + 新缓存键
    cur.execute("UPDATE documents SET embedding = %s::vector WHERE id = %s", (str(vec), doc_id))
    if i % 20 == 0:
        conn.commit(); print(f"  …{i}/{len(rows)}")
conn.commit()
cur.execute("SELECT count(*) FROM documents WHERE embedding IS NULL")
print("embedding 为 NULL 的：", cur.fetchone()[0])       # ⇒ 必须是 0
conn.close()
PY
```
⚠️ **`psycopg2` 的连接参数**：本仓 PG 在 **5432**（⚠️ 5433 是 `memory-system` 的）；
`POSTGRES_PASSWORD` 从 `.env` 来，⛔ **别把密码写进命令行**（会进 shell 历史）。

- [ ] **Step 3: 判据（🔴 这一步是本 Task 的正身）**

```bash
docker compose exec -T postgres psql -U postgres -d rag_db -c "SELECT count(*) FROM documents;"
# ① 条数没变 ⇒ 129
docker compose exec -T postgres psql -U postgres -d rag_db -c "SELECT count(*), vector_dims(embedding) FROM documents GROUP BY vector_dims(embedding);"
# ② 维度 = Task 0 的实测值
# ③ 🔴 端到端：真查一次，看还能不能捞到对的东西
```

**③ 的做法**（⛔ 不是"跑一次没报错"）：

```bash
# 起服务后
bash scripts/list_endpoints.sh >/dev/null   # 确认服务在
# 用一条【语料里确实有】的问题查，看 citations / 相似度合不合理
```

> 🔴 **诚实边界（`DEC-098` §四 4.1 ⑦ 自己写的）**：**129 条是【退化样本】**
> —— 「**在 129 条上跑通，不代表在 1 万条上跑通**」（耗时、内存、镜像大小）。
> ⇒ **别把"本地 129 条通了"说成"重烤没问题"**。

- [ ] **Step 4: 脚本入库** —— ✅ **2026-10-08 业务方裁定：入库**

放 `scripts/`，命名跟本仓既有的 `seed_isolation_docs.sh` 一族对齐
（⚠️ **先 `ls scripts/` 看当前命名**，⛔ 别自己发明一套）。

⚠️ **入库前要满足的三条**：
1. **⛔ 不写死凭据** —— `POSTGRES_PASSWORD` 从 env 读（本仓凭据门会拦）
2. **限速** —— 按 `DEC-098` §2.3 的 **批量 20 行**分批（TPM 100 万/分钟 我们远够，但**批不能超**）
3. **`--check` 模式** —— 照 `seed_isolation_docs.sh` 的先例（**只查不动数据**），
   否则谁跑一次就把库改了

---

## 收尾（两段共用 · ⚠️ 「文档同步」要分清改的是**哪一段**的）

## Task 9 · 文档同步（⛔ 漏一处就是"两套口径"）

| 文档 | 改什么 | 判据 |
|---|---|---|
| `.env.example` | 加 `# EMBEDDING_MODEL_MAIN=...` | `grep -n 'EMBEDDING_MODEL_MAIN' .env.example` |
| `docs/契约/环境变量.md` | ① 新增该变量一行 ② 🔴 **更正 `:67` 那句「embedding ⛔ 不能换，必须 DashScope」**（Task 0 若已实测通，说明**模型可换、端点不变**） ③ `:52` 的「（`text-embedding-v2`）」改成变量口径 | `grep -n 'EMBEDDING_MODEL_MAIN' docs/契约/环境变量.md` |
| `docs/契约/数据模型.md:44` | 维度 + 模型名 | 同上 |
| `docs/specs/embedding_client.md` | §对外提供那行的签名（`model="text-embedding-v2"` ⇒ 从 env 读） | `grep -n 'EMBEDDING_MODEL_MAIN' docs/specs/embedding_client.md` |
| `docs/specs/cache.md`（**在，8901 B**） | 缓存键格式**变了** ⇒ **必须写**（`get_cache_key` 多了必填形参 `model`） | `grep -n 'emb:\|get_cache_key' docs/specs/cache.md` |
| `docs/specs/token_tracker.md:488` | 单价表加新模型 | `grep -n 'qwen3.7-text-embedding-flash' docs/specs/token_tracker.md` |
| `README.md:32` · `ROADMAP.md:49` | 「Embedding 走 DashScope `text-embedding-v2`」⇒ 变量口径 | `grep -n 'text-embedding-v2' README.md ROADMAP.md` |

🔴 **判据（一条打尽）**：
```bash
grep -rn 'text-embedding-v2' --include='*.md' --include='*.py' . 2>/dev/null | grep -v '^./venv' | grep -v worktrees
# ⚠️ 【不是要打成 0】—— 历史记录（CHANGELOG / DEC / 复盘）里的**必须留着**（⛔ 历史不改写）。
# 🔴 判据是：**活文档 + 活代码里不再有它**，历史里照旧有。
```

---

## Task 10 · 收尾

- [ ] **Step 1: 全量门**

```bash
bash scripts/ci-local.sh    # ⇒ 末行真数字（⛔ 别抄本单的）
```

- [ ] **Step 2: 一次**端到端**实跑**（⛔ 不是只看用例绿）

```bash
docker compose up -d
# 用一条语料里真有答案的问题，走一遍 /chat ⇒ 看引用对不对
```

- [ ] **Step 3: Commit / PR**

⚠️ **先问**：「**这笔跟哪个已开的 PR 同类？**」—— 与 `①b` 其余部分同属 demo 化 ⇒ **尽量同 PR**。

---

## Self-Review

| 检查 | 结果 |
|---|---|
| **顺序** | ✅ **已按业务方 2026-10-08 裁定拆成 🅰 / 🅱 两段** —— B 段（切换 + 重烤）**必须等乙**；依据 `DEC-098` §二·0 |
| 依据覆盖 | `DEC-098` **§二·2 / §2.1 / §2.2 / §2.3（2026-10-08 补记）** 全部落到 Task 1–8 ✓ |
| 占位符 | 两处**故意留空**且都标了出处：Task 0 的**实测维度**（⛔ 不是 TBD，是"必须先量"）· Task 5 的**单价**（要求去核，⛔ 不许照抄） |
| 类型一致 | `get_embedding(text, model=None)` · `get_cache_key(text, model)` · `set_cached_embedding(text, embedding, model, ...)` 三处签名在本单内一致 |
| ⛔ 不做的 | 单容器化 / SQLite 迁移 / 限流 / 前端 / 语料契约（`①b` 其余组）· 重新切分（属 `乙`）· `N12` |

## ⬜ 待裁（⛔ 本 Agent 不自拟）

> ✅ **2026-10-08 业务方已逐条裁定** —— 下表「裁定」列就是结论，⛔ 别再当悬案读。

| # | 问题 | ✅ 裁定（2026-10-08 业务方） |
|---|---|---|
| **0** | `.env` 那行改不改回 `text-embedding-v2`？ | ✅ **已改回**（实测 `.env:4` = `EMBEDDING_MODEL_MAIN=text-embedding-v2`）⇒ **走【甲】那条路**，A 段真正行为中立。<br>🔴 **业务方要求：「进入 B 段的时候提醒我。」** ⇒ 见文末「⏰ 待办提醒」 |
| 1 | 重烤脚本要不要入库 `scripts/` | ✅ **要入库** |
| 2 | `api/db.py` 的维度要不要抽成模块级常量 | 🟡 **业务方反问「这个是什么意思，是函数的常量吗？」** ⇒ 已解释（把 `1536` 从 SQL 字符串里提成具名常量 `EMBEDDING_DIM`，SQL 变 f-string）。<br>⚠️ **解释后未再表态** ⇒ **仍待裁**（见下「仍未定」） |
| 3 | `text-embedding-v2` 那行单价留不留 | ✅ **不留，直接删除** —— 业务方原话：「**没有用了，留下是污染**」 |
| 4 | 「乙 · 语料重建」的语料要求 | ✅ **已由 Agent 定义** ⇒ **`docs/说明/语料要求.md`**（联网调研 · 逐条带 🟢/🟡/⚪ 置信度 · 4 类内容 + 1 个负样本设计） |

### ✅ 已全部裁完（2026-10-08 业务方逐条选）

| # | 问题 | ✅ 裁定 |
|---|---|---|
| **2** | `api/db.py` 的维度抽不抽模块级常量 | ✅ **不抽** —— 理由：① **Task 7 的启动自检已把"维度漂移"从静默变响亮**（运行时检查 > 少一个写字面量的地方）② 实测**抽了只解决 5 处里的 1 处**（另 4 处在测试里）③ 改行为面（SQL 变 f-string），而 B 段之后本仓**基本冻结**。<br>⇒ **B 段一次性把 5 处改对 + 自检兜住** |
| **5** | `doc_type` 的推断方式改不改 | ✅ **不改代码，改语料要求** —— 落点 = `docs/说明/语料要求.md` **§2.7 第 11 条**（本仓分块器**先按 `\n\n`/`。` 切、`chunk_size=500` 只是上限** ⇒ 让语料"一篇一个主题、`##` 分节"即可） |

### 🆕 #6 / #7 —— ✅ **2026-10-08 业务方已逐条裁完**

> **业务方原话**：「**chunks 主要是看文档类型决定的，你联网搜索应该有大概标准的，不同类型有不同的 chunks。**」
> ⇒ 我按**中英文 8 份来源**做了 **§5.4 分类型 chunk 标准表**（`docs/说明/语料要求.md`）。

| # | 缺口 | ✅ 裁定 |
|---|---|---|
| **6** | **没有 `faq` 档** —— FAQ 的 Q&A 对（140–300 字）会被**合并进 500 的块** | ✅ **乙 —— 上传接口加【可选】 `doc_type` 形参**（默认 = 现有推断 ⇒ **访客行为一字不变**）<br>🔴 **这是【代码改动】⇒ 已登记 `docs/待办总表.md` 的 `N19`**（⛔ **别只活在施工单里**） |
| **7** | **没有表格档** —— 来源一致说「**表格不要切开**」，而本仓分块器**不认表** | ✅ **甲 —— 语料层解决**：表写成 **Markdown 列表**（每行一条 + **表头在每块重复**），让 `\n` 当切点。⛔ **不改代码**；落点 = `docs/说明/语料要求.md` §2.2 |
| — | ⚠️ **还牵连 `technical` 那一档** | 🟡 **建议提到 600**（来源说手册类 600–800 字，本仓 500）—— ⬜ **未裁** |

## ⚠️ 本单的三个已知风险（写出来，⛔ 不藏）

1. **Task 0 可能直接失败**（模型名不对 / 无权限 / 端点不对）。⇒ 那时**整单停住**，
   因为 Task 6 的表重建**全都建立在"这个模型能调通"之上**。
2. **Task 6 会【丢本地库】**（已裁：重建）。⚠️ **备份那一步（Step 2 ①）是唯一的退路**
   —— ⛔ **别跳过它**。21 kB 的数据丢得起，但**没备份就重建**是流程错，不是代价问题。
3. ~~🔴 **`.env` 已经指着 flash 了**~~ ⇒ ✅ **2026-10-08 已改回 `text-embedding-v2`**（业务方）。
   ⚠️ **但这条风险没有消失，只是被推到了 B 段** —— **B 段开工时【必须】把 `.env` 翻回 flash**，
   否则重烤会用旧模型烤（**烤完还是对不上**）。见下面的提醒。

---

## ⏰ 待办提醒 —— 🔴 **进入 B 段时必须提醒业务方**（他 2026-10-08 明确要求）

> **业务方原话（2026-10-08）**：「**进入 B 段的时候提醒我。**」

**触发条件（⛔ 别靠记性，看这两个判据）**：

```bash
# ① 乙的语料到位了吗（先看语料契约定了没 —— 它是 ①b 的占位 1）
#    契约没定 ⇒ B 段不开工，本提醒也不该响
# ② 真到了 B 段，第一件事是【翻 .env】：
grep -n '^EMBEDDING_MODEL_MAIN' .env
#   ⇒ 现在是 text-embedding-v2（业务方 2026-10-08 改回的）
#   ⇒ 🔴 开工前【必须】改成 qwen3.7-text-embedding-flash，否则重烤用错模型
```

**要提醒的三件事**：

1. 🔴 **`.env` 要翻回 `qwen3.7-text-embedding-flash`**（现在是 `text-embedding-v2`）
2. 🔴 **表要重建**（维度跟着模型走）—— ⚠️ **这一步会丢本地库**，备份是唯一退路（Task 6 Step 2 ①）
3. 🔴 **重烤的语料是【乙产出的那份】**，⛔ 不是现在这 129 条
