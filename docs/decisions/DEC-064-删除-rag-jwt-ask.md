# 决策记录：DEC-064 · **删除端点 `POST /rag/jwt_ask`**

- 日期：2026-10-04
- 状态：**已立 · ✅ 已实施**（端点已删 · 守卫用例已绿 · `bash scripts/ci-local.sh` ⇒ **516 passed**）
- 待办总表：**N7**（现为 ✅）
- 触发：业务方 2026-10-04 逐条裁决 `docs/待办总表.md` 时，对 **N7** 的裁定：

  > 「**A2 · N7 删。**」

  ⚠️ **前置**：同一轮里业务方先问了「**这个是 jwt 用户使用的 ask 提问的地方，没有用吗？是 agent 部分吗，还是当时早期的模拟测试？它的用途是否被覆盖？如果是覆盖，这个单功能接口就没用了。先核实。**」
  ⇒ **本份 §一 就是对这句「先核实」的答复**（三条理由**都按代码与全文 grep 核过**，不是推断）。

---

## 一 · 它是什么（**三条理由，都可打印地核过**）

### 1. 收到 `question`，却**完全不拿它做检索**

端点签名收的是 `QuestionRequest`（**带 `question`**），函数体却是：

```python
cur.execute(
    "SELECT content FROM documents WHERE requested_by = %s LIMIT %s",
    (user_name, req.top_k),
)
```

⇒ **`question` 一次都没进 SQL**。无 embedding、无 `WHERE content ILIKE`、无 `ORDER BY` ——
**换任何问题，返回的都是同一批**（取哪几行由**物理顺序**决定）。

> 🔴 **这正是本仓反复记的那种形态**：「**看着像检索、其实不是**」。
> ⚠️ **与 `DEC-057` 删掉的 `/rag/ask` 逐条同构** —— 同样是"桩的形状 + 无 `ORDER BY` 的 `LIMIT`"。
> 📌 **本次把第二个同型体也清掉了**：这个形状在 `api/api_v1_rag.py` 里**从此不再存在**。
> （⚠️ 剩下那两条真 mock 的 `/rag/async_ask` · `/rag/parallel_ask` **不读库**，⛔ 不是同一个形状。）

**为什么"没有 `ORDER BY`"是硬伤**（而不是"风格问题"）：
`LIMIT` 没有 `ORDER BY` ⇒ **取哪几行由物理顺序决定** ⇒ 同一个问题两次可能拿到不同的行。
⇒ **结果不可复现**——任何依赖它做判断的上层（人 / 测试 / 另一个脚本）都在赌。

### 2. 能力被 `/rag/pg_search` 覆盖，**而且那次是"更严"的覆盖**

业务方问「**它的用途是否被覆盖**」⇒ 逐项对照：

| | `/rag/jwt_ask` | `/rag/pg_search` |
|---|---|---|
| 鉴权 | `get_current_user_jwt` —— **只收 Bearer JWT** | `get_current_user_hybrid` —— **JWT 与 X-API-Key 都收** |
| 入参 | `QuestionRequest` | **同** |
| `question` 进 SQL | ⛔ 不进 | ✅ 进（先 embedding） |
| `WHERE requested_by` | ✅ 有 | ✅ 有 |
| `ORDER BY` | ⛔ 无 | ✅ 有 |
| 输出 | `content` 4 列 | 更丰富 |

🔴 **最容易读反的一点在"鉴权"那一行**：`get_current_user_jwt` **只收 JWT** 看着像是**一项独有能力**，
其实是**一项限制** —— `get_current_user_hybrid` 是它的**真超集**（`X-API-Key` 那条分支之外，
JWT 分支走的是**同一个** `verify_jwt_token`）。

```python
# api/deps.py
async def get_current_user_hybrid(x_api_key: str = Header(None),
                                  credentials = Depends(oauth2_scheme)) -> str:
    if x_api_key:
        return await get_current_user(x_api_key)
    if credentials:
        return verify_jwt_token(credentials.credentials)   # ← 与 jwt_ask 用的是同一个校验
    raise AppException(ErrorCode.AUTH_MISSING, "请提供 API Key 或 Bearer Token")
```

⇒ **删掉 `/rag/jwt_ask`，JWT 用户一个能力都没少** —— `/rag/pg_search` 收 JWT，而且做的是真检索。

### 3. 消费者清点 ⇒ 零

⚠️ **判据必须是清点，⛔ 不是"我试了一次没反应"**——本仓有前科：
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`（当时在 **4 处**写下「`/rag/ask` 不存在」，**全错**）。

| 面 | 结果 | 判据 |
|---|---|---|
| 仓内前端 | **无前端** | 本仓没有前端目录（也无 `package.json`） |
| 兄弟仓引用 | **0 处** | 全仓 + 兄弟仓 grep |
| Postman 集合 | **1 个文件夹**（`检索 / rag / jwt_ask`） | 已一并删除（**158 删 / 0 增**） |
| 测试引用 | **3 处，但没有一处是"在用"** | ① `api/test_breaker_wiring.py` · ② `api/test_session_budget_wiring.py` —— 两条都是**钉住它【不该】被接上限**的**反向守卫**；③ `api/test_isolation.py::test_jwt_ask_endpoint_does_not_leak_across_users` —— 乙段隔离用例 |

⇒ **一个真调用者都没有**（三条测试引用全是"关于它的守卫"，⛔ 不是"使用它的代码"）。

> 📌 **它属于"早期形态"**：首次提交 `2c1a922`（2026-07-17）。业务方那句「**还是当时早期的模拟测试？**」
> ——**核对结论是「是」**：它和 `/rag/ask` 是同一批的早期检索桩，后来的真检索能力全部长在 `/rag/pg_search`
> 与共享层上，这两条桩一直没有被接进任何真实用途。

---

## 二 · ⚠️ **删它⛔ 与隔离无关**（最容易被读错的一条）

`/rag/jwt_ask` **有 `WHERE requested_by`** —— `DEC-056` **乙段**（2026-10-03）给它补的
⇒ **在隔离账上它从来不欠**。

⇒ **别把本份读成 `DEC-056` 的一部分**。`DEC-056` 乙段记的只是「**它只加了 `WHERE`，⛔ 没动检索语义**」
（那是一条**留账**，见 N7）。**删它的理由全部与隔离无关**（见 §一 三条）。

🔴 **而且要说清楚是哪种"消账"**：N7 那条账**不是被"修"好的，是那个矛盾的载体被删掉了**。
- **不是**「我们现在让它真检索了」 ⇒ 那会**开始花 embedding 的钱**，撞 `DEC-041` 已裁的额度范围表，
  还要改 `api/test_session_budget_wiring.py` 里 `NON_LLM` 那条**反向守卫**（它明写这条**不该花钱**）。
- **是**「这条端点**没有消费者**，删掉它**没有任何人少一项能力**」。

📌 **为什么两天前（乙段）没顺手删它**：乙段那次的授权是「**只加 `WHERE`，⛔ 不跑语义变更**」——
删端点**不在那次授权里**，是**独立一件事**。本次是业务方**单独点了这个名**（「A2 · N7 删」）才动手。

---

## 三 · 裁决与做法

| 项 | 裁定 |
|---|---|
| 删还是改 | **删** —— 改它 = 把它变成「真检索」，那是**另一个任务**（且能力已被 `/rag/pg_search` 覆盖，改了就是**第二份重复实现**） |
| 何时删 | **2026-10-04**（业务方点名当日）⇒ **不混进任何别的 commit** |
| 判据怎么下 | **TDD：先写一个"它回来就红"的用例** |
| 历史记录 | **原样留**（`DEC-053` · `DEC-056` §1.2 的**对照行** · 归档目录） |

### 3.1 TDD：RED ⇒ GREEN

**先写** `api/test_removed_endpoints.py::test_rag_jwt_ask_stays_removed`，**要求回 404**。

**RED 实测**：

```
POST /api/v1/rag/jwt_ask - 401
```

⚠️ **这条 RED 比 `DEC-057` 那条更值得记**：端点删之前**本来就是 401**（缺 Bearer Token）。
⇒ 如果用「**不是 200**」当判据，这条用例**从第一天起就是绿的**，**什么也没钉住**。
⇒ **必须断言 404（路由不存在）**。

**删** ⇒ **GREEN**（2 passed）。

### 3.2 判据（可打印）

```bash
venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings
# ⇒ 2 passed（含 test_rag_jwt_ask_stays_removed，断 404）

venv/bin/python -m pytest api/test_isolation.py --collect-only -q -p no:warnings
# ⇒ 18 tests collected            （删前 19）

POSTGRES_DB=rag_test venv/bin/python -m pytest api/test_isolation.py -q -m needs_db -p no:warnings
# ⇒ 9 passed                      （删前 10）

grep -n 'WHERE requested_by' api/api_v1_rag.py | grep -v '#'
# ⇒ 1 行（:415 pg_search）—— 删前 2 行
#    ⚠️ 必须带 | grep -v '#' —— 注释里也含这个串

bash scripts/ci-local.sh
# ⇒ 516 passed, 3 skipped, 31 deselected · 退出码 0
```

⚠️ **最后一条那条 grep 与本次踩的坑**：我新写的**墓碑注释**又给这条判据加了一处污染
（`DEC-057` 那次也是同一个坑）。这正是本仓 `CLAUDE.md` 判据纪律**第 2 条**：
「**批量替换后按【位置】核，⛔ 别只数"替换了几处"** —— **注释里也有同样的串**」。
⇒ **两次删端点，两次栽在同一条上** ⇒ 本 DEC 把它记为**第二次**。

---

## 四 · 改了哪几处

| # | 位置 | 改法 |
|---|---|---|
| ① | `api/api_v1_rag.py` | 端点（路由 + `jwt_ask_question`）⇒ **墓碑注释**（三条理由 + 指向本 DEC + 指向守卫用例）。⚠️ **同时收掉一个 import**：`get_current_user_jwt` 在本文件**只有它一处用**，随它一起删（⛔ **`require_admin` 保持原样** —— 那是**既有**的未使用导入，归 `docs/待办总表.md` **T6** 管，⛔ 不顺手清理） |
| ② | `api/test_breaker_wiring.py` | `NON_SPENDING` 删掉 `("api_v1_rag.py", "jwt_ask_question")` ⇒ 3 → **2**；用例名 `…three_non_spending…` → `…two_non_spending…`；docstring 同步（含**计数沿革**行） |
| ③ | `api/test_session_budget_wiring.py` | 同上（清单叫 `NON_LLM`，用例名 `…three_non_llm…` → `…two_non_llm…`）；**外加文件头那张说明表**里的一行 |
| ④ | `api/ rag-agent-api.postman_collection.json` | **整个文件夹** `检索 / rag / jwt_ask` 删掉（⚠️ **文件名前有一个空格**）—— diff **158 删 / 0 增**。⚠️ 用脚本先断言边界行（`{` · `},` · `{"name": "pg_search"`）、再验结果仍是合法 JSON、再断言 `jwt_ask` 没了而 `pg_search` 还在（备份 `/tmp/postman.bak.dec064.json`） |
| ⑤ | `api/test_isolation.py` | 删 `test_jwt_ask_endpoint_does_not_leak_across_users` ⇒ **墓碑注释**；**`probe_api_keys` fixture 保留**（另有 7 条用例在用） |
| ⑥ | `docs/specs/api_v1_rag.md` | **成片的计数与行号随删而变** —— 见 §4.1 |
| ⑦ | `docs/待办总表.md` | **N7 → ✅**（写清"是删不是修"、新判据、证伪方式）· **N2** 的判据数刷新 + 加「6 条仍全部收口」 · **N8** 记下本次逐条核过的锚点 |
| ⑧ | `docs/decisions/DEC-041-…` §三 | **活口径** ⇒ 加「再由 3 条变 2 条」说明（⛔ **不划掉原行**） |
| ⑨ | `docs/decisions/DEC-056-…` §1.2 第 7 行 | **半活** ⇒ 行 7 划掉 + 注「端点已删 ⇒ 实际检索路径 7 变 6」；第 2 行的注同步 |

### 4.1 ⚠️ 第 ⑥ 处：**删了东西，要回头把"数出来的数"全部重数**

本仓判据纪律第 8 条的镜像。那份 spec 里有一批**当时算出来写死的数**，删一个端点后**全部作废**：

| 数 | 删前 | 删后 | 判据 |
|---|---:|---:|---|
| `@router.` 总数 | 15 | **14** | `grep -c '@router\.' api/api_v1_rag.py` |
| HTTP 端点数 | 13 | **12**（检索 6 → **5**） | 上一条 − 2 条 WS |
| 自己写 SQL 的读端点 | 2 条 | **1 条** | `grep -n 'WHERE requested_by' … \| grep -v '#'` |
| 真在 SQL 里的 `WHERE` | 2 处 | **1 处** | 同上 |
| `grep -c '"requested_by"'` | 11 | **10** | `grep -c '"requested_by"' api/api_v1_rag.py` |
| `grep -c 'WHERE requested_by'`（含注释） | 4 | **3**（注释 2） | `grep -c …` |
| `test_isolation.py` 用例 | 19（离线 9 · `needs_db` 10） | **18**（离线 9 · `needs_db` **9**） | `--collect-only` |
| 检索路径（收口时口径） | 8 条 | **8 条**（⚠️ 未变 —— 见下） | — |

⚠️ **最后一行【不变】，这一点最要紧**：spec 里那句「8 条检索路径全部收口」说的是
**`DEC-056` 收口当时的口径**，是个**历史事实**（它确实一度是 8 条）⇒ **⛔ 不改数字**，
只**在旁边加**「现存 6 条」。⇒ 与本仓「**活口径 vs 记录**」的判据一致。

**同时把 spec 里被我改到的行号锚点按实测重算**（⚠️ 全仓行号漂移是**另一个待办 N8**，
本次**只核了编辑到的那些**，⛔ 没扫全）：`stream_search` `:625`→**`:602`** · `sse_response` `:753`→**`:731`** ·
`astream` `:757`→**`:735`** · `persist_turn` `:723`→**`:715`** · `on_incomplete` `:753`→**`:745`** ·
`get_agent_executor` `:796`→**`:776`** · `agent_websocket` `:851`→**`:831`** · WS 路由 `:876`/`:953`→**`:830`/`:907`** ·
`search_similar` `:660`→**`:637`** · `pg_search` 的 `WHERE` `:413`→**`:415`** · `insert_document` `:317`→**`:321`** ·
写侧回显 `:167/:267/:331/:361`→**`:169/:269/:333/:363`**。
⚠️ **标记为【历史】的锚点没动**（`旧 :676` · `原 :608`）—— 它们指的是**当时的**位置，
改成今天的行号**反而是伪造**。

### 4.2 活口径要跟着改，**历史**不动 —— 判据是「这份文件是规则还是记录」

| 文件 | 性质 | 处置 |
|---|---|---|
| `docs/decisions/DEC-041-…` §三 接线范围表 | 🔴 **活口径**（测试 docstring 明写「若有意移除，**先改本表**」） | ✅ **改**（加「再由 3 条变 2 条」，⛔ **不划掉原行**） |
| `docs/decisions/DEC-056-…` §1.2 第 7 行 | 🟡 **审计终态表**（半活） | ✅ **改**（行 7 划掉 + 注明；第 2 行注同步） |
| `ROADMAP.md`（`③` Task 6 记录 · `DEC-056` 记录） | **历史记录** | ⛔ **一字不动** —— 它们记的是「**当时核出什么**」，删掉端点**不改变当时的事实**（⚠️ 那两处把 `/rag/jwt_ask` 列进「真调 LLM 的四条」，**当时就写错了** —— 那是**另一笔账**，⛔ 不借本次改历史） |
| `docs/specs/token_tracker.md:875` · `docs/decisions/DEC-053` · 归档目录 | **历史记录** | ⛔ **一字不动** |

> 📌 **判据（可复用，`DEC-057` §4.2 立的）**：**「这份文件是【规则】还是【记录】？」**
> 是规则 ⇒ **改**（不改就是"两处真相"）；是记录 ⇒ **留**（改了就是篡改历史）。

---

## 五 · 反悔成本（**低，但不是零**）

**结论**：**低**。理由是**删的是能力被覆盖的端点** —— 没有消费者，所以没有"回不来就断了谁"。
另有 git 历史兜底（`git revert` 即可）。

⚠️ **但"恢复"不是 `git revert` 一条命令就完事** —— 上面那 **9 处必须逐条反向恢复**，
⛔ **少一处测试就红**（尤其是 ②③ 那两份**双向守卫**：端点回来了而清单没加回 `jwt_ask_question`，
会报「**这条链对全量熔断完全不设防**」—— 方向反了，报错信息会误导人）。

| 项 | 反悔成本 |
|---|---|
| 端点代码 + `get_current_user_jwt` import | 低（git 历史里有；墓碑注释里记了它原来在哪） |
| ②③ 守卫清单 + **用例名** | 低，但**容易漏** —— 用例名已从 `three` 改 `two`，恢复时要一并改回 |
| ④ Postman | 低（整个文件夹删的，恢复要重建） |
| ⑤⑥⑦⑧⑨ 文档 | 低 |
| **用户可见的影响** | **零** —— 无消费者（见 §一·3） |

**最坏情况**：若将来有人需要「**只收 JWT 的检索接口**」⇒ **正确的做法不是恢复它**，
而是**在 `/rag/pg_search` 上收紧鉴权**（那样**结果可复现**：`question` 真进 SQL、有 `ORDER BY`）。
📌 **本仓立场**：`DEC-064` **不反对**一个只收 JWT 的检索接口，**反对的是一个收了 `question` 却不拿它检索的接口**。

---

## 六 · 关联

| 文档 | 说明 |
|---|---|
| `api/test_removed_endpoints.py` | 🔴 **反向守卫** —— 它回来就红（判据 = **404**） |
| 🔵 **`docs/decisions/DEC-057-删除-rag-ask.md`** | ⭐ **同族先例（同一天里第二个同型体）** —— `/rag/ask`。本份的**结构、判据写法、活口径/记录的判据**全部照它 |
| `docs/decisions/DEC-056-…` | 乙段记的「只加 `WHERE`，⛔ 没动检索语义」（⛔ **删它的理由与隔离无关**，见 §二） |
| `docs/decisions/DEC-041-…` | §三 接线范围表（**活口径**，已同步） |
| `docs/specs/api_v1_rag.md` | 端点现状 + 「看代码会误判的地方」（那批计数已重算） |
| `api/deps.py` | `get_current_user_jwt` 与 `get_current_user_hybrid` 的**超集关系**（§一·2 的判据） |
| `docs/复盘/2026-09-29-结果为空就断言能力不存在.md` | ⚠️ **本份的"前科"** —— ⇒ **本份的删，靠的是清点，不是"试了没反应"** |
| `docs/待办总表.md` **N7** | 条目（现 ✅）· 另见 **N2**（隔离计数）· **N8**（行号锚点漂移，⛔ 仍是待办） |

## 变更记录

- 2026-10-04 建立（实施同日）。触发：业务方逐条裁决时点名「**A2 · N7 删**」，
  且前置追问「**用途是否被覆盖 / 是否早期模拟测试**」⇒ §一 即为该追问的核实答复。
