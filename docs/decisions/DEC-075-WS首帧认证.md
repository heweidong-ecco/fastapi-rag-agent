# 决策记录：DEC-075 · **WebSocket 首帧认证** —— 顺带把身份透传与记账接上

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施**（2026-10-05）—— 待提交 / 待合 |
| **触发** | 业务方 2026-10-05：「**`/api/v1/ws/agent` 仍未鉴权**，为什么不做鉴权，我提出的问题就是需要，**如果要用就要做完整**」 |
| **前身** | `DEC-074` §七 遗留·1／·2 —— 上一轮**只让它在一份清单里显形**，⛔ **没修** |
| **类型** | 🔴 补鉴权（安全）· 🔴 补记账（成本）· 🟡 改一个写死的身份 |
| **落点** | `api/deps.py` · `api/api_v1_rag.py` · `api/websocket_callback.py` · `api/static/websocket_test.html` · `scripts/check_route_auth.py` · `scripts/route-auth-baseline.txt` |
| **判据** | `api/test_ws_auth.py`（**30 条**）· `api/test_route_auth_scan.py`（10 条）· 扫描器（见 §六） |

---

## 一 · 病：**三件，但是同一条链上的**

业务方那句话我只读出了一半 ——「鉴权」。查下去发现**单独补鉴权会造出一个更坏的东西**。

### 1.1 真花钱的端点，匿名可达

```bash
venv/bin/python scripts/check_route_auth.py    # 改动前
#   ⇒ 无鉴权路由：3 条（HTTP 1 · WS 2）
#        WS /api/v1/ws/agent     ← 跑 agent executor，真调 LLM
#        WS /api/v1/ws/test
```

`/api/v1/ws/agent` 一条消息就跑一次 `get_agent_executor().ainvoke(...)` ——
**路人连上就能烧钱**。债的出处是 `DEC-041` 遗留·1。

### 1.2 身份是写死的字符串

```bash
grep -n 'ws_user_name' api/api_v1_rag.py     # 改动前
#   ⇒ ws_user_name = "unknown"    # 字面量
```

⇒ 就算将来记了账，**账也会记在 `"unknown"` 头上**。

### 1.3 🔴 **记账根本不存在 —— 闸是装饰**

这条是我在补鉴权时才挖出来的，**它才是"做完整"里最要紧的一件**：

```bash
grep -n 'check_session_token_budget' api/api_v1_rag.py
#   ⇒ 有，在 /ws/agent 里
grep -n 'record_from_response\|record_usage' api/api_v1_rag.py
#   ⇒ ❗ 一条都没有
```

`check_session_token_budget(user_name, thread_id)` 的**数据源**是
`token_usage_logs` 按 `(user_name, thread_id)` 当天的求和 ⇒ **没人写 ⇒ 永远读 0**
⇒ **这道闸一次都不会触发**。

> 🔴 这正是 `DEC-073 §六 备选 B` **白纸黑字否掉**的形态：
> 「**只补闸、不记账 ⇒ 闸恒不触发 = 白加**」。
> ⇒ 同一轮里，**闸的旁边必须有人记账**，否则不如不加。

⚠️ 反过来说：如果我只按业务方字面要求"补鉴权"就收工，
交付的东西是「**一个需要凭据才能进的、依然把账记在 `"unknown"` 名下、额度闸永远读 0 的门**」——
**门面上锁了，里面什么都没接**。这就是「**如果要用就要做完整**」要挡的。

---

## 二 · 取证：为什么不能照抄 HTTP 那套（⛔ 四个"想当然"全错）

动手前先证伪了四条，**每一条都能让"看着像接了鉴权"的写法变成事故**：

| # | 想当然 | 实测 |
|---|---|---|
| 1 | 「中间件不是已经挡过了吗」 | ⛔ `api/main.py` 那两个是 `BaseHTTPMiddleware`，**只看 `scope["type"]=="http"`** ⇒ **永远看不到 WebSocket**。WS 的鉴权**只能挂在路由自己的依赖上**。 |
| 2 | 「WS 路由也能用 `get_current_user_hybrid`」 | ⛔ `new WebSocket(url)` **不能自定义请求头**（浏览器 API 限制）⇒ `X-API-Key` / `Authorization` **客户端根本发不出**。照抄形态 ⇒ **把所有人挡在门外**。 |
| 3 | 「失败了直接 `close()` 就行」 | ⛔ **`accept()` 之前关 ⇒ 浏览器只看到握手失败，拿不到关闭码**。要前端能读到 `1008`，**必须 `accept()` 之后再关**。 |
| 4 | 「`accept()` 调两次无所谓」 | ⛔ Starlette 1.6.0 的 `WebSocket.accept()` **不幂等** ⇒ 第二次 `RuntimeError: Expected ASGI message "websocket.send" …, but got 'websocket.accept'`（实测报错原文）。 |

**另一条实测**：`ExceptionMiddleware.websocket_exception` **靠 MRO** 接住
`fastapi.WebSocketException`（它是 `starlette.exceptions.WebSocketException` 的子类，`__mro__` 核过）
⇒ **抛异常**比**自己 close** 可靠：自己 close 之后星型再 close ⇒
`RuntimeError: Cannot call "send" once a close message has been sent.`
⇒ **只能二选一**。

---

## 三 · 裁定（业务方 2026-10-05 选定）

| 问题 | 选定 | ⛔ 否掉的 |
|---|---|---|
| **凭据怎么带上来** | **首帧认证** —— 连上后第一帧发 `{"type":"auth","api_key":…}`（或 `{"token":"<JWT>"}`），通过则回 `{"type":"ready","user":…}` | 查询串（**key 会进 access log / 浏览器历史**）· 子协议（`Sec-WebSocket-Protocol` 装凭据是**滥用**，且**部分代理会剥**） |
| **范围到哪** | **两个都锁 + 调试页跟上** —— `/api/v1/ws/agent` 与 `/api/v1/ws/test` 都挂依赖；`api/static/websocket_test.html` 同步改成要填 key | ⛔ **不采纳「`/ws/test` 不花钱所以留着匿名」** —— 不花钱 ≠ 该匿名（它是**公网上的口子**） |

---

## 四 · 实施：**一个依赖，四处接线**

### 4.1 `api/deps.py` —— `require_ws_user`（依赖）+ `resolve_ws_identity`（纯函数）

拆成两半是**为了可测**：`resolve_ws_identity` 是**纯函数**（收 payload，出 `(user_name, code, reason)`），
所有"哪种凭据不合格 ⇒ 报哪个码"的判定都在这儿，**不碰 WebSocket 对象** ⇒ 31 条用例里大半是喂 dict 断言。

| 关闭码 | 含义 | 给客户端的处置 |
|---|---|---|
| **1008** | 你的凭据不行（缺 / 格式错 / 无效 / 过期） | **换 key** |
| **1011** | **我这边的认证服务不可用**（库连不上等） | **重试，别换 key** |

🔴 **把库抖动报成 1008 = 让用户去换一把没问题的 key** —— 他换了还是连不上，且**永远查不到原因**。

⚠️ **`require_ws_user` 里那次 `accept()` 是本仓唯一一次** ——
**端点里那次必须删**（见 §二·4）。这条写在依赖的 docstring 与 `docs/specs/deps.md` 的
「看代码会误判」表里，两处都点名，**因为看代码的人第一反应就是"重复了，删一个"**。

⚠️ **fail-closed 在这里、fail-open 在 `token_tracker`，是故意的**：
这里是**安全边界**（放错了 = 匿名进门）；那边是**成本控制**（挡错了 = 全站停摆）。
`token_tracker` 的 docstring 里写着同一条 —— ⛔ **别"统一"**。

### 4.2 `api/api_v1_rag.py` —— 两条路由挂依赖，**`accept()` 那次删掉**

> ⚠️ **2026-10-05 同日后续**：本节说的「两条」里，`/ws/test` 当天**又被删掉了** ⇒ 见 **§十**。
> 本节保留的是**那一刻**的记录（当时确实给两条都上了锁）。

```python
@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket,
                          ws_user_name: str = Depends(require_ws_user)):
    # ⛔ 不要再 await websocket.accept() —— 依赖已经 accept 过了
```

FastAPI 在 WS 路由上**先解依赖、后跑端点体**（实测）⇒ **认证不过，端点体一次都不执行**。
这一点有专门的用例钉着：`test_ws_agent_body_never_runs_before_auth` 把
`get_agent_executor` 换成**一被调用就 AssertionError** 的探针。

### 4.3 `api/websocket_callback.py` —— 身份**必填** + 真记账

- `__init__` 的三个参数改成**关键字必填**（`user_name` / `thread_id` / `llm`）——
  **漏传 = `TypeError`**，⛔ 不是退回 `"unknown"` 静默记账。
- `on_llm_end` 调**本仓唯一被认可的**记账实现 `token_tracker.record_from_response`
  （`DEC-072` 裁定），`purpose="agent_decision"`。
- 判据键是 `usage_metadata`，⛔ **不是 `.usage`**（那个属性**不存在**）。
  没有 `usage_metadata` 就**不记**（别的通路已记过）。

### 4.4 两处结构门跟上

- `scripts/check_route_auth.py` 的 `AUTH_NAMES` 加 `"require_ws_user"` ——
  **那个门是靠函数名字符串认人的**，名单漂了会**静默放过**（自证见 §六）。
- `scripts/route-auth-baseline.txt` **3 条 → 1 条**，头注写清那 2 条是**真修好**，⛔ 不是挪走。

---

## 五 · 有意留下的口子（⛔ 别读成遗漏）

1. 🔴 **WS 的会话桶仍是"每连接"** —— `thread_id = f"ws-{uuid4}"` ⇒ **断开重连 = 换一个新桶**，
   每连接的额度可以靠重连刷新。
   - **为什么不这轮修**：WS **没有客户端传上来的会话 id**，要修得先给协议加一层会话协商，
     那是**另一件事**，塞进本轮会让"补鉴权"变成一个没人能一次审完的改动。
   - **为什么现在也不算失控**：**全局日级熔断 B11 仍罩着** ⇒ 重连刷不出全局额度。
2. ⚠️ **注入面换了人，没消失** —— `calculator` 那处（`DEC-066`）的 `expression` 仍是
   **LLM 生成**、上下文含用户输入 ⇒ **间接提示注入依旧成立**。
   改前是**路人**，现在是**持合法凭据的用户**。
   ⇒ `safe_math` 那三道闸**一条都不能撤**。

---

## 六 · 判据（可打印）

```bash
venv/bin/python -m pytest api/test_ws_auth.py api/test_route_auth_scan.py -q
#   ⇒ 40 passed（30 + 10）

venv/bin/python scripts/check_route_auth.py
#   ⇒ 真实路由总数：60（HTTP + WS）
#      🔴 无鉴权路由：1 条（HTTP 1 · WS 0）
#         GET /api/v1/          ← WS 那两条已消失

venv/bin/python scripts/check_route_auth.py --baseline ; echo $?
#   ⇒ ✅ 与基线一致。   exit 0

grep -n 'record_from_response' api/websocket_callback.py
grep -n '"unknown"' api/api_v1_rag.py        # ⇒ 应当没有输出
```

**两次自证（⛔ 不能只看"绿的那一次"）**：

| 探针 | 动作 | 实测 |
|---|---|---|
| ① | 从 `AUTH_NAMES` 里**拿掉** `require_ws_user`（内存里，不改源） | 无鉴权 WS 立刻变 `['/api/v1/ws/agent','/api/v1/ws/test']` ⇒ **名字名单是承重的** |
| ② | 从 `/ws/test` 上**摘掉** `Depends(require_ws_user)`（改源→跑→复原） | `❌ 比基线【多了 1 条】… + /api/v1/ws/test`；复原后 exit 0 |
| ③ | 把扫描器的 **WS 收集分支关掉**（改源→跑→复原） | **五条断言各自用自己的话报红**（`合成 WS 路由没被收进 ws 桶` / `真实 WS 路由数变了（现在是 0）` / …）⇒ 不是一条红了带一片 |

⚠️ **③ 是补测的**：`DEC-074` 那两条用例原先是**拿真 app 那两条 WS 当样本**的
（当时它们无鉴权 ⇒「扫描器看得见 WS」与「它俩在清单里」恰好同一件事）。
**现在样本消失** ⇒ 若继续用真 app，这条测试会**逼着人把鉴权改回去才能绿**（**测试在保护 bug**）。
⇒ 样本换成**合成 `APIWebSocketRoute`**，真 app 那条改成断言**相反**的事实
（`test_real_websocket_routes_are_protected_now`）。

---

## 七 · 代价与反悔成本

**代价**
- 前端要多一次往返（`ready` 之前不能发消息）。⇒ 调试页 `websocket_test.html` 已改成
  **显式连接 + 等 `ready`**，并区分 `1008`（认证被拒）/ `1011`（认证服务不可用）两种 `onclose`。
- ⚠️ **`1008` / `1011` 的语义是给客户端的契约** —— ⛔ 以后别图省事把两类合成一种。
- 5 秒首帧超时（`WS_AUTH_TIMEOUT_SECONDS`）：慢客户端会被关。**是有意的** ——
  ⛔ 不能为了"兼容慢客户端"把它调成无限（那等于给匿名连接留一个**永不关闭的挂起槽位**）。

**反悔成本**：**低**。
- 它**不改任何 HTTP 行为**，也不改 WS 的业务逻辑 —— 只加了一层前置依赖。
- 退 = 摘掉依赖 + 复原基线 + 删 `require_ws_user`；⚠️ 副作用是**退回匿名可达 + 零记账**。

---

## 八 · 备选方案（⛔ 都没采纳）

| # | 方案 | 为什么否 |
|---|---|---|
| A | **只在中间件里加 WS 支持** | `BaseHTTPMiddleware` 结构上做不到（§二·1）；改中间件基类 = 动全站，**风险与收益不成比例**。 |
| B | **凭据走查询串** `?api_key=…` | key 会进 **access log / 浏览器历史 / Referer**；且本仓已有"key 泄露不自知"的看板（`Product-utilities/key-usage-dashboard`）⇒ **主动制造泄露面**。 |
| C | **用 `Sec-WebSocket-Protocol` 装凭据** | 那是**滥用**该头（它声明的是子协议）；且**部分代理/网关会剥掉** ⇒ 出现"我这儿能连、那儿连不上"。 |
| D | **先签发一次性 ticket，再用它连 WS** | 更安全（凭据不进首帧），但**多一个端点 + 多一层状态**（ticket 存储与过期）。⚠️ **不是坏方案**，是本轮**过头**了 —— 记在这里，等有真实需求（对外发 key）再取。 |
| E | **只补鉴权、记账留到下轮** | ⛔ **造出 §一·1.3 那个"装饰闸"** —— 正是 `DEC-073 §六 备选 B` 明文否掉的形态。**业务方说的"做完整"挡的就是它**。 |
| F | **顺手把会话桶改成按人**（连 §五·1 一起修） | 要改 WS 协议（加会话协商）⇒ **范围翻倍**，且与"补鉴权"**无法一起审**。⇒ 单独立项。 |

---

## 九 · 遗留（⛔ 本轮没做）

1. **WS 会话桶仍是每连接**（§五·1）—— 要修得先给协议加会话协商。
2. **`verify_api_key` 的 `get_db()` 没有 try**（`DEC-074` 遗留·4，**仍在**）——
   HTTP 侧库抖动时「带无效 key」变成 **500 而不是 401**。
   ⚠️ **WS 侧已绕过这个坑**（`resolve_ws_identity` 自己 try ⇒ 1011），**HTTP 侧没修**。
3. **`route-auth-remind.py` 的 `ROUTE_FILES` 仍是写死的 4 个文件名**（`DEC-074` 遗留·3，**仍在**）——
   它只是提醒、不是门。
4. ~~**`/api/v1/ws/test` 的存废**（`DEC-074` 遗留·2）~~ ⇒ ✅ **2026-10-05 同日裁定：删**（见 §十）。
   本轮**先给它上了锁**（上一条实施），**随后另行裁定它的存废** —— 两步是分开做的，
   ⛔ 不是"边锁边删"：先锁的那一版**可独立成立**（即便它留下，也不能匿名）。

---

## 十 · 同日后续：**删掉 `/api/v1/ws/test`**（业务方 2026-10-05）

> **业务方原话**：「`/api/v1/ws/test` 还有用吗，是否是测试需要，**先核对判断再执行**，
> 如果不需要没用**可以直接删除**。」
> ⇒ 这是一条**先举证、后执行**的指令 —— 本节先摆判据，再记执行。

### 10.1 判据（三条，与 `DEC-065` 删那 4 条【同一套标准】，⛔ 不是另立一套）

| # | 判据 | 实测 |
|---|---|---|
| ① | **消费者 = 0** | **三处独立扫过**：**本仓**（`api/static/websocket_test.html` 连的是 `/ws/agent`，⛔ 不是它）· **本仓测试**（`git log -S 'ws/test' -- 'api/test_*.py'` 在 `DEC-074` 之前 **零命中** —— 它的全部命中都是 `DEC-074`/`DEC-075` 这两轮"把它登记成债"留下的）· **仓外**（`agent-eval-gate` 的 SUT harness 等 **5 个**兄弟项目，**全 0**） |
| ② | **本仓自己早就点名** | `DEC-055` 的流式出口普查表里就写着 `WS /ws/test` = **「测试桩」** |
| ③ | **连它唯一可能的用途也没了** | 它**不花钱**（纯回声），故曾可能被当作「免鉴权的 WS 探活口子」。⚠️ **但 §四给 WS 补上首帧认证之后它自己也要凭据** ⇒ 这个口子**已经不成立** |

⚠️ **②是关键的一条**：`DEC-065` 那批删的也不是"坏东西"，是**本仓自己标为桩/零消费者的东西**。

### 10.2 🔴 判据形态：**WS 没有状态码，所以⛔ 不能照抄 HTTP 那套 `== 404`**

实测（2026-10-05，`TestClient`）：

| 情形 | `client.websocket_connect(path)` 的行为 |
|---|---|
| 路由**不存在** | **建连那一刻**（`__enter__`）就抛 `WebSocketDisconnect` |
| 路由**存在且要鉴权** | 建连**成功**；退出上下文时才抛 `WebSocketDisconnect(1000)` |

🔴 **所以「抛了 `WebSocketDisconnect` 就算删干净」是【假判据】** ——
一条**活着的、带鉴权的** WS 路由**也会抛**（第二行）。
这与 `DEC-064`/`DEC-065` 里那个「**不是 200**」**同型**：**判据成立，却什么也没钉住**
（`/rag/jwt_ask` 删之前本来就是 401 ⇒ 那种写法从第一天起就是绿的）。

⇒ 取下**两个不同的可观测量**（同源，各指一层）：

- **端到端**：建连**当场**被拒 —— 这是 **404 在 WS 上的对应物**；
- **注册层**：`/api/v1/ws/test` **不在** WS 路由集合里。

### 10.3 执行

- `api/api_v1_rag.py`：删掉整个块，**留一条 ⚰️ 墓碑**（三条理由 + "别改回来"）。
  🔴 **墓碑里刻意⛔ 不写 `@router.` 字面串**（写 `WS /ws/test`）——
  本仓判据 `grep -c '@router\.' api/api_v1_rag.py` 是**数路由**用的，
  注释里留同款串会**多数一条**。⚠️ **本仓已栽过两次**：`DEC-065` 一次，**同一天又栽一次**
  （本次墓碑初稿写成了装饰器字面量 ⇒ 数出 12，应 11）。判据见 `docs/specs/api_v1_rag.md`。
- **TDD**：先写 `api/test_removed_endpoints.py::test_ws_test_stays_removed`，
  **看着它红**（`Failed: DID NOT RAISE WebSocketDisconnect`）⇒ 再删路由 ⇒ 绿。
- **跟着变的地方**（本轮全找出来改了）：`api/test_ws_auth.py`（−2 条用例 · 1 条改名收窄）·
  `api/test_route_auth_scan.py`（WS 计数 2→1 · 自检算式 · 模块 docstring）·
  `scripts/check_route_auth.py` 的**基线生成模板**（⛔ 不改它，下次 `--write-baseline` 会**把假话写回去**）·
  `scripts/route-auth-baseline.txt` · `docs/specs/api_v1_rag.md` · `docs/specs/deps.md` · `docs/契约/接口契约.md` ·
  `docs/待办总表.md` · `.claude/README.md` · `ROADMAP.md` · `CHANGELOG.md`。

### 10.4 判据（可打印）

```bash
venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings   # ⇒ 7 passed
venv/bin/python scripts/check_route_auth.py                                 # ⇒ 无鉴权 1 条（HTTP 1 · WS 0）· 真实路由总数 59
venv/bin/python scripts/check_route_auth.py --baseline                      # ⇒ 与基线一致（exit 0）
grep -c '@router\.' api/api_v1_rag.py                                       # ⇒ 11（10 HTTP + 1 WS）
```

### 10.5 留下的守卫（⛔ 别与上一条合并）

`test_ws_test_stays_removed` 的判据是「**它不存在**」；
`api/test_ws_auth.py::test_the_ws_route_carries_the_auth_dependency` 的判据是
「**`/ws/agent` 存在且挂着 `require_ws_user`**」—— **两条判据恰好相反，⛔ 别合并。**

⚠️ **代价说清楚**：将来若有人再建一条 WebSocket 路由，**不会有测试自动拉红**叫它去挂鉴权
—— `test_the_ws_route_carries_the_auth_dependency` 里那句
`assert set(found) == {"/api/v1/ws/agent"}` **会红**（这是本轮专门加的），
但它**只说明"WS 集合变了"**，⛔ 不替你判断新那条该不该有鉴权。
