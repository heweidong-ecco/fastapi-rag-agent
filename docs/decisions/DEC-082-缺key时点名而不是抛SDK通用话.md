# DEC-082 · 批 6：缺 key 要**点名**，⛔ 不是抛 SDK 那句通用话（`T1`）

- 日期：**2026-10-05**
- 分支：`fix/batch6-t1-lazy-embedding-client`（基点 `ba9bc03` = `main`）
- 起因：`docs/待办总表.md` §三 **`T1`**（自标「优先级最高」）—— **业务方 2026-10-05 选定为批 6**
- ⚠️ 该表自己写着「T1–T3 的判断来自扫描，**我没有逐条复核**」⇒ **本批第一件事是核实**（见 🅐）

---

## 一 · 这批的一句话

**「缺配置」时报的错，必须让人一眼知道缺的是哪个变量。**

改前两条路都是：把 `None` 递给 SDK ⇒ SDK 抛它那句通用话 ——
`The api_key client option must be set … or by setting the OPENAI_API_KEY environment variable`。
🔴 **它提的 `OPENAI_API_KEY` 本仓根本不用** ⇒ 照它去设变量，**问题不会消失**。

```
embedding 侧：模块级构造 ⇒ 改【惰性单例】+ 缺 key 点名      （真的不崩了）
LLM     侧：构造时机不变 ⇒ 只改【报什么】                  （照旧在 import 期中止）
```

---

## 二 · 逐条决定

### 🅐 `T1` 现状核实 —— 成立，但**原话有一处不准**

| 原话 | 实测（2026-10-05） |
|---|---|
| `api/embedding_client.py:10` 模块级 `OpenAI(api_key=…)` | ✅ 属实（`:10-13`） |
| 「key 为空会**炸掉整条 import 链**」 | ✅ **复现了**：掐掉 `.env` 后 `import embedding_client` ⇒ `OpenAIError`；连 `rag_pipeline` 也起不来 |
| ⚠️ 「空」要**分清两种** | 🔴 变量**缺失**（`config.py:39` 的 `os.getenv` **无默认值** ⇒ `None`）⇒ **构造期就抛**；<br>变量**为空串** ⇒ `OpenAI(api_key='')` **构造成功**，要到**请求时**才 401。<br>⇒ 真正中招的是**没配这一行**的那类，⛔ 不是「填了空值」那类 |
| — | 🔴 `.env.example:3` 给的是**非空占位符** `sk-your-api-key-here` ⇒ **照着 example 抄的人不炸** |
| — | 🔴 **为什么一直没被发现**：`ci.yml:140` 塞了 dummy `DASHSCOPE_API_KEY`、本地开发有 `.env` ⇒ **两条路都不触发**。<br>📌 `ci.yml:135-138` 的注释自己写着「空 key 会抛 `OpenAIError`，故给个非空占位即可」——**那是把门挂在别处**。 |

### 🅑 修法选型 —— **惰性单例**，否掉「模块级 `__getattr__`」

| 方案 | 判定 |
|---|---|
| **甲 · 模块内惰性单例**（`_client = None` + `_get_client()`） | ✅ **采用**。5 行；`import` 期**不做任何网络/凭据相关构造** |
| 乙 · PEP 562 模块级 `__getattr__` 保留 `client` 这个名字 | ⛔ **否**。`from embedding_client import client` 在 **import 期**就会触发 `__getattr__` ⇒ **照样炸**，只是把「炸在模块级」换成「炸在别人 import 时」——**等于没修** |
| 丙 · 构造挪进 `try/except` 吞掉 | ⛔ **否**。把「配错了」变成「调的时候才莫名其妙」 |

**缺 key 时报什么**：`EnvironmentError` —— 与本仓既有同族**一致**
（`config.validate_config()` ⇒ `config.py:76` · 审批白名单启动硬拦 ⇒ `agent_graph.py:92/100`）。
消息里**必须含字面量 `DASHSCOPE_API_KEY`**（判据就是拿这个字符串断言的）。

### 🅒 顺带**必须**处理的一行：`api_v1.py:35` 的未使用导入

`from embedding_client import client` —— **全仓唯一引用**（`grep` 实测），且**这一行从未被使用**。

⚠️ 它**不是**「顺手清理」，是**本次改动的必要条件**：模块级 `client` 一旦去掉，
这行会让 `api_v1` 直接 `ImportError` ⇒ **整个 app 起不来**。
⇒ **业务方 2026-10-05 裁「删掉这一行」**；原处留一行注释说明为什么没有它。

### 🅓 取客户端的**位置**：放在查缓存**之前**（⚠️ 一处行为变更）

改前：缓存命中 ⇒ **根本不碰客户端**。改后：`get_embedding()` **第一行**就取客户端。

**为什么**：否则「同一句话有时报错、有时不报」取决于**缓存状态** —— 比一律报错更难查。
**代价**：缓存命中时也要求 key 配好。**这笔账我认为划算**（配错了本来就该响亮地断），
⚠️ 但**它是行为变更，写在这里备案**。

### 🅔 LLM 侧同族：**只改「报什么」，不做真惰性**（业务方 2026-10-05 裁）

实测：`make_llm()` 构造 `ChatOpenAI(api_key=None)` **抛的是同一句话**（`config.py:65` 的注释早就在说这件事）。

🔴 **但 LLM 侧的「真惰性」不是改一处** —— 核实下来的改动面：

| 模块 | 模块级构造 | 模块级 `bind_tools` 链 |
|---|---|---|
| `agent_graph.py` | `:25` | 🔴 `:60 llm_with_tools = llm.bind_tools(tools)` |
| `agent_checkpointer.py` | `:29` | 🔴 `:51` 同上 |
| `agent_graph_advanced_learning.py` | `:26` + `:85/86/87` | 🔴 `:79` 同上 |
| `agent_graph_advanced.py` · `plan_execute.py`（3 处）· `evaluate_with_ragas.py` | `:61` · `:101/320/539` · `:60` | （`bind_tools` 已在函数内） |

⇒ 真惰性要**把那 3 张图的模块级初始化整体下沉**，而它们正承载着**硬门 D 与六条流式端点**。
**而它实质就是 `DEC-044` 里【有意推迟】的「运行时可切」** —— 夹进一个 bug 批会把它变成大改。

⇒ **本批只把「报什么」改对**（一行判断），**构造时机不动** ⇒ LLM 侧**照旧在 import 期中止**，
但报的是 `EnvironmentError: LLM_API_KEY 未设置 …`。
⛔ **别把这条读成「LLM 侧也修好了」** —— 「import 不许崩」那半**没做**。

---

## 三 · 反悔成本

| 若将来要 | 代价 |
|---|---|
| 撤回惰性（回到模块级构造） | 删 `_get_client` + 把 `api_v1.py` 那行加回去（若那时还需要它）—— ⛔ 但**别退回「抛 SDK 通用话」**，那是本 DEC 要消灭的东西 |
| **给 LLM 侧做真惰性** | 按 🅔 那张表动 4 个模块；**建议与 `DEC-044` 的「运行时可切」一起裁**，⛔ 不单独立项 |
| 改报错类型（`EnvironmentError` ⇒ 别的） | 改 2 处 raise + 3 条测试的断言；⚠️ 换之前先看 `config.py` / `agent_graph.py` 用的什么 |

---

## 四 · 本批**没做**的（诚实清单）

1. 🔴 **LLM 侧「import 不许崩」没做** —— 只改了报什么（见 🅔）。
2. ⚠️ **`ci.yml` 那组 dummy key 仍要留着** —— embedding 侧不再需要它，但 **LLM 侧仍会在 import 期构造**。
3. ⚠️ **embedding 仍不可换** —— `base_url` 与模型名写死在模块里，⛔ 不是配置项（`docs/契约/环境变量.md` §4 的老结论不变）。
4. ⚠️ **「上游计费」「真调一次 DashScope」仍没验** —— 本批全部用例**离线**，⛔ 不证明 API 通。
5. ⚠️ **`T1` 之外的四条（`T2`–`T5`）一条没碰**。

---

## 判据（可打印）

```bash
venv/bin/python -m pytest api/test_embedding_client_lazy.py api/test_llm_factory.py -q   # 17 passed
bash scripts/ci-local.sh                                                                  # 658 passed, 3 skipped, 0 failed · 退出码 0
grep -rn "from embedding_client import client" api/                                        # 0 命中
```

**变异自证 4/4**（逐条把修复退回去 ⇒ **恰好那条转红**）：
M1 退回模块级构造 ⇒ `test_import_succeeds_without_the_key` 红 ·
M2 去掉 key 检查 ⇒ `test_missing_key_is_reported_by_name_not_by_openai`（embedding）红 ·
M3 拆掉惰性单例 ⇒ `test_client_is_built_once_and_carries_the_configured_key` 红 ·
M4 去掉 `llm_factory` 的 key 检查 ⇒ 同名的那条（LLM）红。

## 关联

`docs/待办总表.md` §三 **`T1`**（本批销账）· `docs/specs/embedding_client.md` · `docs/specs/llm_factory.md` ·
`docs/契约/环境变量.md` §4（Embedding 与 LLM 不是同一家）·
`DEC-044`（LLM 构造收口；**真惰性/运行时可切在那里推迟**）· `config.py:58-76`（`validate_config` 的口径）
