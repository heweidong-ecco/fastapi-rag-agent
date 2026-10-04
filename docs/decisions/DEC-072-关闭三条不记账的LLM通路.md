# 决策记录：DEC-072 · **关闭三条【不记账】的 LLM 通路**

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施**（2026-10-04 · T1–T9 全部完成，**未提交**）—— 另见 §九 每步的实测结果 |
| **触发** | 做 `DEC-071`（三家隔离语料）核链路时顺带撞见 ⇒ 报给业务方 ⇒ **业务方 2026-10-04 裁「要修复，这个要处理」** |
| **类型** | 🔴 **修缺陷**（三个图的计费/配额漏网） |
| **落点** | `api/agent_graph.py` · `api/agent_checkpointer.py` · `api/agent_graph_advanced_learning.py` · `api/api_v1_agent.py` · `api/token_tracker.py` |
| **范围裁定（业务方）** | ① **三条链一起修**（含我后补的第三条）② **深度 = 与参照图完全对齐**（每个 LLM 节点：调用前 `check_token_budget`、调用后记账） |

---

## 一 · 病：三条会真调 LLM 的链，一分钱不记

| # | 端点对 | 图模块 | LLM 调用点 | `record_usage` | `check_token_budget` |
|---|---|---|---|---|---|
| 1 | `/agent/langgraph_chat` (+`/stream`) | `api/agent_graph.py`（277 行） | 1（`:138`） | ⛔ **0** | ⛔ **0** |
| 2 | `/agent/advanced_chat` (+`/stream`) | `api/agent_graph_advanced_learning.py`（449 行） | **6** | ⛔ **0** | ⛔ **0** |
| 3 | `/agent/memory_chat` (+`/stream`) | `api/agent_checkpointer.py` | 1（`:59`） | ⛔ **判据恒假** | ⛔ **0** |

**判据（可打印）**：

```bash
for f in agent_graph.py agent_checkpointer.py agent_graph_advanced_learning.py; do
  printf "%-38s record=%s budget=%s\n" "$f" \
    "$(grep -c 'record_usage' api/$f)" "$(grep -c 'check_token_budget' api/$f)"
done
#   ⇒ agent_graph.py  0 / 0     ⛔
#   ⇒ agent_checkpointer.py  2 / 0（那 2 处里 1 处是 import，真调用在【恒假分支】里）⛔
#   ⇒ agent_graph_advanced_learning.py  0 / 0   ⛔

# 第 3 条的那个恒假判据：
grep -n 'hasattr(response, "usage")' api/agent_checkpointer.py     # ⇒ :83
```

### ⚠️ 第 3 条的坑与别的两条不同 —— 它是「判据写错了」

`AIMessage` / `AIMessageChunk` **没有** `.usage` 属性（真属性是 `usage_metadata`）⇒
`hasattr(response, "usage")` **恒为 False** ⇒ 那段记账**从未执行过**。
⚠️ **源码注释自己早就写着这件事**（`agent_checkpointer.py:78-83`）⇒ ⛔ 不是"没人发现"。

---

## 二 · 为什么「守卫明明在跑、测试还全绿」

🔴 **`api/test_session_budget_wiring.py::EXPECTED_WIRED` 里三条链【全都在表上】**，
且那条测试**一直是绿的**（实测断言的是"这个函数体里调用了 `check_session_token_budget`"）。

**但守卫读的计数器，这三条路从不写** ⇒
`get_session_token_usage()` 恒为 0、`get_global_daily_token_usage()` 也看不到它们
⇒ **端点上的 B8 会话上限 + B11 全站熔断对这三条链等于不存在**。

⇒ **任何用户（含 `FREE`）反复打这 6 个端点 = 无限免费 LLM。**
📌 这是本仓 `docs/复盘/2026-09-16-八个PR跳过了留痕门.md`「**门挂在别处，就等于没有门**」的**同族** ——
只是这次门**挂在正确的位置**，而**门后面的计量表是坏的**。

---

## 三 · 修法：与参照图 `agent_graph_advanced.py` 对齐

**参照图（`agent_graph_advanced.py`，`/agent/mcp_chat` 在用，全仓唯一记对了的两条之一）的既有写法**：

```python
user_name = state.get("user_name", "unknown")
if not check_token_budget(user_name, estimated_tokens=500):
    return {"final_output": "今日Token预算已用完，请明天再试。", ...}
...调 LLM...
if hasattr(response, "usage_metadata"):
    usage = response.usage_metadata
    record_usage(model=…, prompt_tokens=…, completion_tokens=…, purpose=…,
                 user_name=…, thread_id=…)
```

### 三处**必须比参照图更严**的地方（⛔ 别照抄那三行）

1. 🔴 **`state["thread_id"]` 会 `KeyError`** —— 参照图在 `:360` 用的是**下标**。
   三条链的 `AgentState` 里**现在压根没有这个键** ⇒ 一律用 **`.get(…, "unknown")`**。
2. 🔴 **端点根本没往 state 里放身份** —— 光改图**不管用**。
   `api_v1_agent.py` 的 6 处初始 state **只传了 `messages`**（`/agent/advanced_chat` 多一个 `user_name`）
   ⇒ **必须同时改端点**（见 §五）。
3. ⚠️ **`agent_checkpointer.py` 的 `purpose="query_rewrite"` 是错的**（一个对话端点记成"查询改写"）。
   真库实测 `query_rewrite` **0 条**（那段代码从没跑过）⇒ 改成 `agent_decision` **无历史数据要迁**。

---

## 四 · 唯一实现：`token_tracker.record_from_response()`

**为什么不让三处各抄一遍**：本仓对这个病有明确立场 ——
`api/agent_graph_advanced_learning.py:39-53`（工具表从 MCP 注册表**派生**）写着
「**两表结构上不可能再漂**」。**6 + 1 + 1 = 8 个调用点各抄一遍 8 行,必然漂。**

在 **`api/token_tracker.py`** 加：

```python
BUDGET_EXCEEDED_MSG = "今日Token预算已用完，请明天再试。"

def record_from_response(llm_obj, response, purpose, *, user_name="unknown",
                         thread_id="unknown", tool_name=None, tool_args=None) -> bool:
    """从一次 LLM 响应取用量并记账 —— **唯一实现**。

    ⛔ 判据必须是 `usage_metadata`。`AIMessage` / `AIMessageChunk` **都没有** `.usage`
       （本仓 `agent_checkpointer.py:83` 曾用 `hasattr(response, "usage")` ⇒ 恒假 ⇒ 记账从未执行）。
    返回 True = 真记了；False = 这次响应没带用量 ⇒ **静默跳过，不抛异常**（与既有取向一致）。
    """
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return False
    record_usage(
        model=getattr(llm_obj, "model_name", None) or getattr(llm_obj, "model", "unknown"),
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
        purpose=purpose, user_name=user_name, thread_id=thread_id,
        tool_name=tool_name, tool_args=tool_args,
    )
    return True
```

⚠️ **`model=` 必须从对象取**（⛔ 不写死 `"qwen-turbo"`）—— 本仓踩过：
`agent_graph_advanced.py:352-354` 与 `agent_checkpointer.py:85-87` 都记着「写死 ⇒ 按**错的单价**记账」。

⛔ **本轮不重构已经在记账的两条链**（`agent_graph_advanced.py` / `plan_execute.py`）——
它们**是对的**，动它们只有风险没有收益（「不顺手清理」）。⇒ 本决策**不宣称**全仓只剩一处实现，
只说**新代码**走这一处。已登记为后续可选清理。

---

## 五 · 逐文件改动清单

### 5.1 `api/token_tracker.py`
- ➕ `BUDGET_EXCEEDED_MSG` · ➕ `record_from_response(...)`

### 5.2 `api/agent_graph.py`（链 1）
| 位置 | 改动 |
|---|---|
| `:105-107` `AgentState` | ➕ `user_name: str` · ➕ `thread_id: str` |
| `:110` `agent_decide` | LLM 调用**前**拦；`return {"messages": [response]}` **前**记账 |

### 5.3 `api/agent_checkpointer.py`（链 3）
| 位置 | 改动 |
|---|---|
| `:52-55` `AgentState` | ➕ `user_name: str` · ➕ `thread_id: str` |
| `:59` `agent_decide` | ➕ 预算拦；🔴 `:83-92` **整段替换** —— 删恒假判据、改走 `record_from_response`、`purpose` 改 `agent_decision` |

### 5.4 `api/agent_graph_advanced_learning.py`（链 2）
| 位置 | 节点 | purpose | 拦截后的返回 |
|---|---|---|---|
| `:86-91` | `AgentState` ➕ `thread_id` | — | — |
| `:380` | `supervisor` | `agent_decision` | `{"intent": "CHAT", "final_output": BUDGET_EXCEEDED_MSG}` ⚠️ **必须给 `intent`**，否则 `route_by_intent` 读 `state["intent"]` 当场 `KeyError` |
| `:147` | `search_summarize` | `answer_generation` | `{"final_output": BUDGET_EXCEEDED_MSG}` |
| `:169` | `calc_execute` | `query_rewrite` | `{"final_output": BUDGET_EXCEEDED_MSG}` |
| `:210` | `translate_execute` | `answer_generation` | `{"final_output": BUDGET_EXCEEDED_MSG}` |
| `:251` | react `agent_decide` | `agent_decision` | `{"messages": [AIMessage(content=BUDGET_EXCEEDED_MSG)]}` ⇒ `should_continue` 判不出 `tool_calls` ⇒ 走 `summarize` ⇒ 落成 `final_output` |
| `:400` | `chat_node` | `answer_generation` | `{"final_output": BUDGET_EXCEEDED_MSG}` |

### 5.5 `api/api_v1_agent.py`（**6 处初始 state**，⛔ 漏一处 = 那条链记成 `"unknown"`）
| 端点 | 行 | 现在传 | 补成 |
|---|---|---|---|
| `/agent/langgraph_chat` | `:198-201` | `{messages}` | ➕ `user_name` `thread_id` |
| `/agent/langgraph_chat/stream` | `:331-333` | `{messages}` | ➕ 同上 |
| `/agent/advanced_chat` | `:553-559` | `{messages, user_name, memory_space}` | ➕ `thread_id` |
| `/agent/advanced_chat/stream` | `:640-645` | 同上 | ➕ `thread_id` |
| `/agent/memory_chat` | `:936-939` | `{messages}` | ➕ `user_name` `thread_id` |
| `/agent/memory_chat/stream` | `:1025-1029` | `{messages}` | ➕ 同上 |

> ⚠️ **`thread_id` 传【原值】而不是 `sess`** —— `sess = session_key(user_name, thread_id)` 是
> **checkpoint 的键**，两者用途不同。记账要的是**原值**（参照 `/agent/mcp_chat`，`DEC-071` §三）。

---

## 六 · 判据（全部可打印）

```bash
# ① 静态接线：三条链每个 LLM 调用点的外层函数，都同时有【拦】和【记】
venv/bin/python -m pytest api/test_billing_wiring.py -q

# ② 行为：拿假 LLM 驱动三张图，断言 record_usage 收到正确的 user_name / thread_id
venv/bin/python -m pytest api/test_billing_wiring.py -q -k behavior

# ③ 单元：record_from_response 对 `.usage`（旧错属性）必须返回 False
venv/bin/python -m pytest api/test_token_budget_hookup.py -q

# ④ 离线点名（原有的，必须仍绿）：三条链都在 EXPECTED_WIRED 上
venv/bin/python -m pytest api/test_session_budget_wiring.py -q

# ⑤ 全量
bash scripts/ci-local.sh
```

**证伪要求（本仓纪律，⛔ 不许跳）**：把任一处的 `record_from_response` 调用**注释掉** ⇒
①**必须变红**；把任一端点补的 `thread_id` 删掉 ⇒ ②**必须变红**。两步都实测，结果写进 PR。

---

## 七 · ⛔ 本轮**不做**（说清楚，别读成"漏了"）

| 不做的事 | 为什么 |
|---|---|
| **工具级配额** `check_multilevel_budget` | 参照图在 `tool_execute` 里有（`:250`），但那是**工具配额轴**，⛔ 不是"计费漏账"轴。归下一轮 |
| **轨迹留痕** `record_tool_start/end` · `record_agent_decision` | 同上，那是**追踪轴**（`N4` 已单独收口过） |
| **重构已在记账的 2 条链** | 它们是对的，动它们只有风险（见 §四 末） |
| **`/ws/agent`** | 整条**无鉴权**、身份写死 `"unknown"`（`DEC-041` 遗留·1）⇒ 它的账**记给谁都无意义**，要先解决"它是谁" |
| **节点级与端点级的拒绝形状不一致** | 端点级 ⇒ `raise QUOTA_EXCEEDED`（异常）；节点级 ⇒ 200 + 一句话（照参照图）。**本轮保持与参照图一致**，⛔ 不发明新形状 |
| 🔴 **`docs/specs/api_v1_agent.md` 旧行号的全量重取** | **收尾时才发现**（见 §九·T9）—— 该文件从 743 → 1714 行，正文/状态行里的 `:NNN` 大面过时（实测偏差 >150 行）。⚠️ **不在本批做**，理由两条：① **它不属"计费漏账"轴**（本 DEC 只负责它自己那 6 处身份注入行）；② 那 ~30 个引用里**混着实施计划 ②/③ 里"当时为真"的行号**，机械替换会把对的一起改错 ⇒ 要**逐条判"这句说的是现在还是当时"**，是独立一笔账 |

---

## 八 · 反悔成本

| 要退掉 | 怎么退 | 代价 |
|---|---|---|
| 全部改动 | `git revert` 单个 squash commit | **低** |
| 只想关掉记账、保留预算拦 | 注释掉 `record_from_response` 调用 | ⚠️ **中** —— 拦的判据会重新依赖那个永不增长的计数器 ⇒ **等于没拦** |
| ⚠️ **行为变化（知道再选）** | — | **记账一生效，这 3 条链的配额就从"形同虚设"变成"真的生效"** ⇒ 之前能一直免费用 `FREE` 档的用户，**现在会被拦**。**这是我们想要的**，但要写进 `CHANGELOG` 的 `### Changed` |

---

## 九 · 实施步骤（TDD）

> ⚠️ 本仓**不用** subagent 执行（`CLAUDE.md` B 级表：`subagent-driven-development` 标「待适配 ⇒ 我们的规矩是**改动等发话**」）⇒ 由本会话 inline 执行。

- [x] **T1 · 先写会红的测试** —— ✅ **实测 RED = 14 failed**，红的理由全对：
  拆开是 **5 条单元**（`record_from_response` 不存在）+ **9 条静态 AST**；
  后者的失败信息里**逐个点名了 8 个裸奔调用点与 6 个缺身份的端点**（⚠️ 那是**失败信息里的条数**，⛔ 不是额外 14 条用例）。
  ⚠️ **14 是 T6 行为测试加入【之前】的数** —— T6 之后两份文件合计 **19 条**。
  ⚠️ **RED 跑出过一次「红错了地方」并被自查修正**：① `AIMessage(usage_metadata=...)` 漏 `total_tokens` ⇒ 挂 pydantic 校验而非"缺函数"；
  ② 守卫初版用 `ast.walk` **下钻嵌套函数** ⇒ 同一调用点被内外两层各报一次，且**造成假通过**（外层因内层调了守卫而被判"已拦已记"，外层自己的调用点仍裸奔）
  ⇒ 改成 `_own_called_names` + `_llm_sites_by_innermost_function`，重跑后链 2 **精确报 6 条**，与 §一 清单一致。
  - `api/test_billing_wiring.py`：AST 扫 3 个图模块 ⇒ 每个含 `llm*.stream/invoke` 的函数必须**同时**调 `check_token_budget` 与 `record_from_response`；AST 扫 6 处端点初始 state ⇒ 必须含 `user_name`/`thread_id` 键
  - `api/test_token_budget_hookup.py`：`record_from_response` 单测（含 `.usage` 旧属性 ⇒ `False`）
  - 跑一次，**确认全红**（这一步不做 ⇒ 后面无法证明测试有效）
- [x] **T2 · `token_tracker` 加 `record_from_response` + `BUDGET_EXCEEDED_MSG`** ⇒ ✅ `test_token_budget_hookup.py` **5 passed**
- [x] **T3 · 链 1**（`agent_graph.py` + 2 端点）⇒ ✅ 对应断言转绿（`agent_graph.py` 278 → **308** 行）
- [x] **T4 · 链 3**（`agent_checkpointer.py` + 2 端点）⇒ ✅（171 → **192** 行）
- [x] **T5 · 链 2**（`agent_graph_advanced_learning.py` 6 处 + 2 端点）⇒ ✅ `test_billing_wiring.py` 全绿（450 → **540** 行；`api_v1_agent.py` 1692 → **1714**；`token_tracker.py` 963 → **1027**）
- [x] **T6 · 行为测试**（假 LLM 驱动三张图，断言记账参数）⇒ ✅ **5 passed**（含链 3 的行为层墓碑 · 链 2 断言恰好 **2 笔** · 缺身份落 `"unknown"` 不 500 · 超预算**绝不调模型**）
- [x] **T7 · 证伪**（注释掉任一记账调用 ⇒ 变红；删掉任一 `thread_id` ⇒ 变红）—— ✅ **两步都实测**（下 §九·T7）
- [x] **T8 · 端到端实测**（真库）：打一次 `/agent/advanced_chat` ⇒ `token_usage_logs` 新增一行，
      且 `user_name`/`thread_id` 是**调用方传的原值**。📌 判据同 `DEC-071` §三 那套 ⇒ ✅ **三条链全过**（下 §九·T8）
- [x] **T9 · 文档**：5 份 spec（`agent_graph` / `agent_graph_advanced_learning` / `agent_checkpointer` /
      `api_v1_agent` / `token_tracker`）· `CHANGELOG.md`（`### Fixed` + `### Changed`）·
      `docs/待办总表.md` §二 第 6 行消账 · `docs/文档地图.md` 无需改（无新脚本）⇒ ✅ **全部完成**
      · ⚠️ **收尾时自查出三处数字错**（`14 passed` → **`19 passed`**；T1 的算术不自洽；`agent_graph.md` 的 `273 → 308` 应为 **`278 → 308`**）—— 均已改，
      判据是 `git show HEAD:api/agent_graph.py | wc -l` ⇒ `277`（+1 末行无换行 = **278**）
      · 🔴 **顺带发现一件【不在本批范围】的事**：`docs/specs/api_v1_agent.md` 的**旧行号大面积过时**（该文件从 743 行长到 1714 行，
      正文里的 `:NNN` 多是**当时那个长度下**写的 ⇒ 实测 `:473` 现在指向 `pending_calls,`、`:843` 指向一个三引号，
      而两处**都声称**指向 `/stream` 路由）。⇒ **只在本 DEC 负责的 6 处（`:205`/`:342`/`:571`/`:659`/`:957`/`:1048`）核过并对**，
      另在 `api_v1_agent.md` 表下加了 **⚠️⚠️ 行号口径**警示 + 两条可打印重取命令；⛔ **全量重取不在本批做**（单列，见 §七）

### T7 · 证伪实测（两步，均实测 + 还原后 md5 一致）

| 步 | 动作 | 结果（**两步都红，且红在对的地方**） |
|---|---|---|
| **A** | 注释掉 `agent_graph.agent_decide` 的 `record_from_response` | ① 静态：AST 守卫**点名 `agent_graph.py`**；② 行为：`assert 0 == 1` / `len([])` ⇒ **红** |
| **B** | 删掉 `/agent/langgraph_chat` 端点补的 `thread_id` | `AssertionError: api_v1_agent.py:172 的 langgraph_chat() 初始 state 缺 ['thread_id']` ⇒ **红** |

还原后两步均 md5 一致；还原后 **19 passed**（`test_billing_wiring.py` + `test_token_budget_hookup.py`）。

### T8 · 端到端实测（真 HTTP 栈 + 真图 + 真 LLM + 真库）

三条端点各写 `token_usage_logs` 与 `cost_records` **各 4 行** ⇒ 共 **8 行**；
`user_name` 全 `isolation_a` · `thread_id` 全是**端点传进去的原值**
（`T8-c1-001` 629 · `T8-c3-001` **626** · `T8-c2-001` 305+1067）· `purpose` = `agent_decision` · `model` = `deepseek-v4-flash`。
⭐ **链 3 那 626 是【有史以来第一笔】**（那个恒假判据修好后才写得出来）。测试行已清理（`DELETE` 各 4 行，`isolation_a` 回到 3,329）。

⚠️ **未走容器** —— `docker-compose.yml` 的 api 服务**只挂 `./logs`、无源码挂载** ⇒ 容器里是旧代码。
改用 `TestClient(main.app)` 在**进程内**跑真 app：HTTP 栈（路由 / 依赖 / `X-API-Key` 鉴权）、真图、真 LLM、真库**全在**，
只差「有没有经过 Docker 那一跳」。

---

## 附录 · 两个测试文件的骨架（T1 要写的）

### A · `api/test_token_budget_hookup.py`

```python
"""`record_from_response` 的单元判据 —— 重点是【那个恒假的旧属性必须不记账】。"""
from langchain_core.messages import AIMessage
import token_tracker


class _FakeLLM:
    model_name = "fake-model"


def _capture(monkeypatch):
    """把真记账换掉 —— 本文件只验『判据对不对』，不碰库。"""
    calls = []
    monkeypatch.setattr(token_tracker, "record_usage", lambda **kw: calls.append(kw))
    return calls


def test_records_when_usage_metadata_present(monkeypatch):
    calls = _capture(monkeypatch)
    msg = AIMessage(content="hi",
                    usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18})
    assert token_tracker.record_from_response(
        _FakeLLM(), msg, "answer_generation",
        user_name="isolation_a", thread_id="A-thread-001") is True
    kw = calls[0]
    assert (kw["prompt_tokens"], kw["completion_tokens"]) == (11, 7)
    assert kw["user_name"] == "isolation_a" and kw["thread_id"] == "A-thread-001"
    assert kw["model"] == "fake-model"      # ⛔ 不许写死模型名（本仓踩过：按错单价记账）


def test_does_not_record_on_the_old_wrong_attribute(monkeypatch):
    """🔴 这条钉的就是 `agent_checkpointer.py:83` 那个 bug：`.usage` 在 AIMessage 上不存在。"""
    calls = _capture(monkeypatch)

    class _HasDotUsageOnly:
        usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 5})()

    assert token_tracker.record_from_response(
        _FakeLLM(), _HasDotUsageOnly(), "agent_decision") is False
    assert calls == []


def test_real_aimessage_without_usage_is_skipped_not_raised(monkeypatch):
    calls = _capture(monkeypatch)
    assert token_tracker.record_from_response(
        _FakeLLM(), AIMessage(content="no usage"), "answer_generation") is False
    assert calls == []
```

### B · `api/test_billing_wiring.py`（AST 守卫 —— 全仓**没有** `ast` 之外的办法）

```python
"""三条【会真调 LLM】的链：每个调用点必须【先拦后记】，且端点必须把身份塞进 state。

## 与 `test_session_budget_wiring.py` 的分工（⚠️ 那条**一直是绿的**）
那边只断言「端点调了 `check_session_token_budget`」—— 三条链**全都调了**，
却**从不往 `token_usage_logs` 写一行** ⇒ 守卫读的计数器恒为 0 ⇒ **门在、锁坏了**。
本文件钉的是**门后面那张表**。
"""
import ast, pathlib
import pytest

_API = pathlib.Path(__file__).parent
GRAPHS = ["agent_graph.py", "agent_checkpointer.py", "agent_graph_advanced_learning.py"]
ENDPOINTS = [("api_v1_agent.py", n) for n in (
    "langgraph_chat", "langgraph_chat_stream",
    "advanced_agent_chat", "advanced_agent_chat_stream",
    "memory_chat", "memory_chat_stream",
)]
GUARD, BILL = "check_token_budget", "record_from_response"


def _is_llm_call(node: ast.Call) -> bool:
    """只认 `llm…` 开头对象上的 `.stream()` / `.invoke()` —— ⛔ 工具调用也叫 invoke。"""
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in ("stream", "invoke", "astream", "ainvoke")
            and isinstance(f.value, ast.Name) and f.value.id.startswith("llm"))


def _names_and_llm_calls(fn):
    names, llm_sites = set(), []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(getattr(f, "id", None) or getattr(f, "attr", None))
            if _is_llm_call(node):
                llm_sites.append(node.lineno)
    return names, llm_sites


def _find(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("filename", GRAPHS)
def test_every_llm_node_both_guards_and_bills(filename):
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names, sites = _names_and_llm_calls(n)
        if not sites:
            continue                      # 不调 LLM 的节点（date_execute / summarize…）跳过
        assert GUARD in names, f"{filename}:{n.lineno} {n.name}() 调了 LLM 但不拦预算"
        assert BILL in names,  f"{filename}:{n.lineno} {n.name}() 调了 LLM 但不记账"


@pytest.mark.parametrize("filename,func", ENDPOINTS)
def test_endpoint_passes_identity_into_state(filename, func):
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    fn = _find(tree, func)
    assert fn is not None, f"{filename} 找不到 {func}() —— 改名/删了？要同步改本表"
    keys = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("invoke", "astream", "ainvoke") and n.args \
                and isinstance(n.args[0], ast.Dict):
            keys |= {k.value for k in n.args[0].keys if isinstance(k, ast.Constant)}
    assert {"user_name", "thread_id"} <= keys, (
        f"{filename}:{fn.lineno} {func}() 的初始 state 缺 {sorted({'user_name','thread_id'} - keys)}\n"
        "  ⇒ 图里记的账会写成 'unknown'，**而所有测试照样全绿**。"
    )
```

⚠️ **`test_every_llm_node_both_guards_and_bills` 是【形状】判据** —— 本仓对它有过教训
（`DEC-066`：**守卫的形状盲区**）。⇒ 必须**配** T6 的行为测试一起看，⛔ 不许只留形状那一条。

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-04 | 建立 · 业务方裁定范围（三条链 + 完全对齐）· 记下 §二「守卫在跑但计数器是坏的」这一根因 |
| 2026-10-04 | 补附录（两个测试文件的骨架）—— 计划纪律要求「⛔ 不许写『给上面写测试』而不给代码」 |
| 2026-10-04 | **T1–T9 实施完成** · 状态改 ✅ 已实施 → 每步结果回写进 §九（含 T1 两处「红错了地方」的自查修正 · T7 证伪两步 · T8 端到端真库实测）· 5 份 spec / `CHANGELOG` / `待办总表` 同步 |
