# `api/token_tracker.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，但它是【三套额度口径】的其中一套** —— 见下 ⚠️<br>🟢 **①a 已落地（2026-10-01）**：额度常量已收口到 `api/token_config.py`（本文件**只剩同名别名**）· 本文件下方 **实施计划 ①a** 已执行完<br>🔵 **①b 进行中（2026-10-01）**：Task 0 ✅ / Task 1 ✅（B7 接线）/ **Task 2 ✅（B8 会话级 · 已接 7 条链，真能拦）** / **Task 3 ✅（B10 全局日级 · ⚠️ 只有函数，未接线）** / ⬜ **Task 4 起待做（B11 熔断）**<br>⚠️ **两者的完成度【不一样】，别一起读**：`B8` 有调用点 ⇒ **改行为**；`B10` **没有调用点** ⇒ **不产生任何行为变化**，接线在 `B11` |
| **对外提供** | `record_usage()` · `record_cost()` · `check_multilevel_budget()` · `check_token_budget_detail()` · `get_token_budget_info()` · 9 个汇总函数 |
| **谁在用** | `permission`（取角色）· `agent_graph_advanced.py:239`（唯一调多级预算的地方）· `cost_dashboard.py` · 各 `api_v1_*.py` |
| **规模** | 888 行 |

## ✅ 做了什么

- **按 model 记账**：`record_usage(model=…)`（`:69`）· `PRICING` 表（`:50`）+ 兜底单价（`:54`）· `by_model` 汇总（`:467`）
- **多级预算**（`:651` `check_multilevel_budget`）—— **自标「3 级」**：
  ① 单次上限（**元**，`MAX_SINGLE_CALL_COST=0.5`，`:646`）
  ② 单线程上限（**元**，`MAX_THREAD_COST=5.0`，`:649`）
  ③ 每日预算（**token**，`ROLE_TOKEN_BUDGET`，`:286`）
- **9 个汇总函数**：`get_daily_token_usage`(:191) · `get_user_summary`(:240) · `get_purpose_summary`(:247) · `get_thread_summary`(:252) · `get_recent_usage`(:259) · `get_token_budget_info`(:338) · `generate_monthly_report`(:354) · `get_daily_usage_cost`(:583) · `get_intercept_count`(:633)
- **拦截记录**：`record_intercept`(:607)

## 🟡 做到哪 / 缺什么

- 🔴 **额度常量散在 4 个文件 6 处**（本文件的 `ROLE_TOKEN_BUDGET` / `MAX_THREAD_COST` / `MAX_SINGLE_CALL_COST` / `PRICING`、`permission.ROLE_QUOTA`、`plan_execute.PLAN_TOTAL_BUDGET_SECONDS`）
- ✅ ~~🔴 **`"admin": float("inf")`**~~ ⇒ **2026-10-01 已去**（`DEC-040`）：现在是有限值 = `premium` = 100000/天。<br>⚠️ **但"全局日级"仍是另一个东西**（B10，在 `①b`）—— per-user 检查**永远看不到「大家加起来超了」**
- ✅ ~~🔴 **没有「会话级」上限**~~ ⇒ **2026-10-01 有了**（`B8` · `①b` Task 2）：
  `get_session_token_usage` / `check_session_token_budget`，**接在 7 条真调 LLM 的对话链上**（`DEC-041`）。
  ⚠️ **数据源是 `token_usage_logs` 表，⛔ 不是 `_thread_summary`** —— 内存**重启即清零**，拿它当上限等于"重启就能绕开"
- 🟡 **「全局日级」** ⇒ **2026-10-01 建了函数**（`B10` · `①b` Task 3）：`get_global_daily_token_usage` / `check_global_daily_budget`。
  🔴 **但⛔ 没有任何调用点** ⇒ **本条不产生任何行为变化**，接线在 `B11`（`①b` Task 4）
- ⬜ **零测试覆盖**（`docs/说明/测试.md` §六 **#8**）
- ⬜ **R2.2 恢复条件未核** —— `EXPIRE 86400` 是首次 INCR 时设的（滚动），**没人实测过 TTL**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「多级预算是硬拦截」** | ⛔ **不是** —— `agent_graph_advanced.py:239` 超预算时是往图里**塞一条 `ToolMessage` 文本提示**，**HTTP 仍是 200**。**前端看不出"被拒了"** |
| 🔴 **「这个文件管所有配额」** | ⛔ **不是** —— 另有 `permission.ROLE_QUOTA`（**请求次数**）与 `quota_limiter.py`（**每日次数**）。**三套口径并存**，`DEC-029` 实测**差 35 倍** |
| ⚠️ **「两个单位混着 ⇒ 是 bug」** | 🟢 **不是** —— 第一二级（元）与第三级（token）**量纲本来就不同**，代码注释 `:665` 明说「**别统一掉**」 |
| ⚠️ **「`ROLE_TOKEN_BUDGET` 就是最终日限额」** | ⚠️ **只对 `_invoke_llm` 那条链**。**挂多级预算的只有 `/agent/mcp_chat` 一条**（`check_multilevel_budget` 全仓唯一调用点在 `agent_graph_advanced.py:239`）⇒ **其他链全无预算** |
| ⚠️ **「本文件定义着 `PRICING` / `ROLE_TOKEN_BUDGET` / `MAX_*_COST`」** | 🔴 **2026-10-01 起【只是别名】** —— 真值在 `api/token_config.py`，本文件**顶部 import 进来**（`PRICING is token_config.MODEL_PRICING` → `True`）。⇒ **改价改额度请去 `token_config.py`**，改这里没用（会被 import 覆盖） |
| 🔴 **「`check_global_daily_budget` 存在 ⇒ 全站额度在管着」** | ⛔ **不是** —— **它没有任何调用点**（2026-10-01 · Task 3 只出函数）。<br>**判据（可打印）**：`grep -rn "check_global_daily_budget" api/ --include="*.py"` ⇒ 只应命中**定义处 + 测试**；命中不到任何 `api_v1_*.py` = **它还没生效**。<br>⚠️ 接线在 `B11`（Task 4）。📌 这是「**常量/函数建好没接上**」那个陷阱的**第三次**（前两次：`B7` 前、`B8` 前） |
| 🔴 **「`get_global_daily_token_usage` 与 `get_daily_token_usage` 差不多」** | 差的正是**全部**：前者 SQL **⛔ 不许有 `user_name`**（全站），后者**必须有**（单用户）。<br>⚠️ 抄后者改前者时**漏删** `WHERE user_name` ⇒ 函数名还叫「全局」、**返回值正常、只是偏小**、**没有任何报错** ⇒ 本仓**永远不会有全局额度**。<br>⇒ 已用 **AST 静态守卫**钉死（`api/test_global_daily_budget_offline.py` 的**配对**测试：一边必须有、一边必须没有） |
| ⚠️ **「`GLOBAL_DAILY_TOKEN_LIMIT` = 1,000,000 是个随手写的默认值」** | 🟡 **2026-10-01 起它变成了【裁定值】**（`DEC-042`）—— 业务方在源文档 B10 那个空上填的。⚠️ 但**它仍不在环境变量契约里**（`.env.example` / `docs/契约/环境变量.md` 都无此项），想不改代码调它**得先补契约** |

## 关联

`docs/specs/token_config.md`（**常量的真身**）· `docs/specs/quota_limiter.md`（**次数**那套）·
`docs/specs/permission.md`（⏳ 待建）·
`DEC-029`（两套口径，**已由 `DEC-040` 收口**）· `后端补齐清单` **B7/B8/B10/B11/B13**

---

# ✅ 实施计划 ①a · **额度收口**（2026-09-30 立 · **2026-10-01 已执行完**）

> **来源**：`后端补齐清单-待裁-20260929.md` 的 **B12 · B7 · 决策一**（**业务方已逐条裁定**）。
> **范围**：只做**两件【不改行为】的事** + 一条决策记录。
> ⚠️ **B8 / B10 / B11 / B13 不在本计划**；**`决策一` 的【实现】也不在**（原因见 Task 3 那节的「顺序陷阱」）。
> ⛔ **本计划做完，服务的外部行为应当【完全不变】** —— 除 Task 1 改的那几句错误文案。
>
> **为什么先做这批**：业务方定的开工序是「**B12 第一**」（全清单最便宜），
> 且 **`决策一`（统一 token）是结构改动** —— 它一落地，B8/B10 才知道挂在哪。

**目标**：把散在 4 个文件的额度常量收到 `api/token_config.py` 一处；
让错误响应带**恢复时间**；把「请求次数」那套配额**降级**（`决策一` = 统一到 token）。

**架构**：新建 `api/token_config.py` 作为**唯一常量来源**（**只读 env，⛔ 不做热加载** ——
`ChatOpenAI(max_tokens=…)` 是 **import 时求值**，17 个构造点都是，改了本来就要重启）。
`token_tracker` 与 `permission` 改为从它取值。

**技术栈**：Python 3.10 · FastAPI · pytest（marker：`needs_db` / `integration`）

**Spec**：本文件（`docs/specs/token_tracker.md`）·
`fastapi-rag-agent-TODO待办/后端补齐清单-待裁-20260929.md`（B12 · B7 · 决策一）

## 全局约束（**每个任务都适用**）

- 🔴 **跑测试必须用 CI 的同一条命令**：`python -m pytest api/ -m "not integration and not needs_db" -q`
  （⛔ 别拿"全量"顶替 —— 全量含 `needs_db` 用例，会掩盖"偷偷依赖库"，**2026-09-30 栽过**，见 `docs/复盘/2026-09-30-本地绿当成了不依赖.md`）
- 🔴 **新增/修改的测试不许碰 DB 或 Redis**，除非标了 marker。做法参照 `api/test_rate_limit_identity.py` 的 `_no_db` fixture
- 🔴 **提交信息里要答两问**：① 有无决策（有 ⇒ 建 DEC）② CHANGELOG 写没写（见 `docs/规范/开发规范.md` §2.2）
- 🔴 **命令里写中文用「」『』，不用 ASCII 引号**（会被 shell 吃掉 —— 2026-09-30 栽过）
- ⛔ **`admin` 的日上限 = `premium` = 100000**（业务方 2026-09-30 裁）
- ⛔ **单次上限不分角色**（否则对 admin 等于不存在）
- ⏸ **角色档位体系本轮不重塑** —— 只改值，**不改"分几档"**（业务方：留第二轮）

## 文件结构

| 动作 | 文件 | 职责 |
|---|---|---|
| **新建** | `api/token_config.py` | **额度常量的唯一来源**（只读 env） |
| **新建** | `docs/specs/token_config.md` | 它的 spec（⛔ 新建模块**必须**同时建 spec —— `pre-commit-gates.py` 会硬拦） |
| **新建** | `api/test_token_config.py` | 常量来源与取值的回归测试 |
| **新建** | `docs/decisions/DEC-040-额度统一到token一套.md` | `决策一` 的决策记录 |
| **修改** | `api/exceptions.py` | `AppException` 加 `retry_after` |
| **修改** | `api/main.py` | 异常处理器带上 `retry_after`；**修 4 处错误文案** |
| **修改** | `api/token_tracker.py` | 常量改为从 `token_config` 取；`admin` 去 `inf` |
| **修改** | `api/permission.py` | `ROLE_QUOTA` 降级为「接口权重」（`决策一`） |
| **修改** | `api/test_plan_execute_tools.py` | **那条钉住"两套口径差 35 倍"的用例要改**（见 Task 3） |
| **修改** | `CHANGELOG.md` | 本次有行为改动 |

---

## Task 0 · 建 `DEC-040`（`决策一` 的决策记录）

**Files:**
- Create: `docs/decisions/DEC-040-额度统一到token一套.md`

**为什么它是 Task 0**：后面三个任务**都按它写**。没有它，实施的人不知道"次数那套是废掉还是降级"。

- [ ] **Step 1: 写 DEC**（模板见 `docs/decisions/DEC-038-*.md` / `docs/decisions/DEC-033-*.md`）

必须含这五节（**别省「备选」和「反悔成本」**）：

| 节 | 内容 |
|---|---|
| **决策事项** | 本仓**已有两套口径**（请求次数 `permission.ROLE_QUOTA` vs token `token_tracker.ROLE_TOKEN_BUDGET`），`DEC-029` 实测**差 35 倍**；再加 R1 四层会变成三套 |
| **备选** | **甲** 统一到 token 一套（次数配额废掉或降为"接口权重"）· **乙** 保留两套但打通 · **丙** 先不动 |
| **裁定** | **甲**（业务方 2026-09-30 原话：「**甲 · 统一到 token 一套**」） |
| **落地含义** | ① 新建 `token_config.py` 收口 ② `ROLE_QUOTA` **降级为接口权重**（不删，因为 `QuotaMiddleware` 还挂在上面）③ `admin` 去 `inf` |
| **反悔成本** | **低** —— 全靠 `token_config.py` 一处取值，回退 = 改一个 `get_role_request_weight()` 的实现 |
| **关联遗留** | `DEC-029` 的乙/丙**未做** ⇒ **本决策相当于用「甲」把它收口**，需在 `DEC-029` 里补一条「由 `DEC-040` 收口」 |

- [ ] **Step 2: 在 `DEC-029` 里补一条指针**

在 `docs/decisions/DEC-029-两套配额口径不一致.md` 末尾加：

```markdown
> ✅ **2026-10-01 收口**：本决策的「乙/丙 未做」状态**已由 `DEC-040`（统一到 token 一套）终结** ——
> 见 `docs/decisions/DEC-040-额度统一到token一套.md`。
```

- [ ] **Step 3: 提交**

```bash
git add docs/decisions/DEC-040-额度统一到token一套.md docs/decisions/DEC-029-两套配额口径不一致.md
git commit -m "docs(DEC-040): 决策一裁定落地 —— 额度统一到 token 一套（收口 DEC-029）"
```

---

## Task 1 · **B12** · 错误响应带恢复时间 + 修 4 处文案

**Files:**
- Modify: `api/exceptions.py`（`AppException.__init__`）
- Modify: `api/main.py`（异常处理器 `:345` 附近；4 处文案 `:158` `:460` `:481` `:496`）
- Test: `api/test_error_contract.py`（新建）
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `AppException(error_code, message=None, retry_after=None)` —— `retry_after: int | None`（**秒**）
- Produces: 响应体多一个可选字段 `retry_after`；响应头 `Retry-After`

📌 **`retry_after` 的含义**（写进 docstring，别只写名字）：**客户端还要等多少秒**才能重试。

- [ ] **Step 1: 写失败测试**

```python
# api/test_error_contract.py
"""错误响应的契约（对应 B12）。

🔴 为什么要有这个文件：本仓**有一条文案是说反的** ——
   `api/main.py` 全局限流触发时返回 429，`error` 字段却写着 "Internal server error"。
   那正是 `通用方法 §7.1` 的 R3.3 要防的：「❌ 熔断时静默/白屏/500 → 对方以为你的系统坏了」。

本文件**不需要 DB / Redis** —— 只测异常对象与处理器产出的契约。
"""
from exceptions import AppException, ErrorCode


def test_app_exception_carries_retry_after():
    """`retry_after` 要能挂到异常上 —— 否则处理器没法把它写进响应。"""
    exc = AppException(ErrorCode.RATE_LIMITED, "请求过于频繁", retry_after=30)
    assert exc.retry_after == 30


def test_app_exception_retry_after_defaults_to_none():
    """不给就是 None —— 不是 0（0 会被读成'立刻可重试'）。"""
    exc = AppException(ErrorCode.INTERNAL_ERROR, "boom")
    assert exc.retry_after is None
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
python -m pytest api/test_error_contract.py -q
```
预期：`TypeError: AppException.__init__() got an unexpected keyword argument 'retry_after'`

- [ ] **Step 3: 改 `api/exceptions.py`**

```python
class AppException(Exception):
    """自定义业务异常，附带错误码，由全局异常处理器统一捕获"""
    def __init__(self, error_code: ErrorCode, message: str = None,
                 retry_after: int = None):
        self.error_code = error_code
        self.message = message or error_code.value  # 未提供消息则使用错误码名称
        self.status_code = ERROR_CODE_TO_HTTP_STATUS.get(error_code, 500)
        # 客户端还要等多少秒才能重试。只在【限流/配额】这类可恢复的错误上给；
        # 其他错误留 None ⇒ 处理器不会写这个字段（避免"等 0 秒"被误读成"立刻可试"）。
        self.retry_after = retry_after
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
python -m pytest api/test_error_contract.py -q        # → 2 passed
```

- [ ] **Step 5: 写失败测试（响应契约）**

加到同一个文件：

```python
from fastapi.testclient import TestClient


def _client():
    # 惰性导入：`main` 导入期会建 Gradio Blocks（见 api/conftest.py 的注释）
    from main import app
    return TestClient(app)


def test_rate_limited_response_is_not_internal_server_error():
    """🔴 本条钉的是那条【说反了的文案】（`api/main.py` 全局限流分支）。

    改前：`{"error": "Internal server error", "code": "RATE_LIMITED", "status_code": 429}`
    改后：文案必须说清"是限流"，⛔ 不许出现 "Internal server error"。
    """
    from main import _rate_limited_payload      # 见 Step 7 抽出的纯函数
    body = _rate_limited_payload()
    assert body["code"] == "RATE_LIMITED"
    assert "Internal server error" not in body["error"], (
        f"限流却写着内部错误 —— 正是 R3.3 要防的：{body['error']!r}"
    )
    assert "频繁" in body["error"] or "限流" in body["error"], (
        f"文案要说清是限流，不是故障：{body['error']!r}"
    )
```

- [ ] **Step 6: 跑测试，确认失败**

```bash
python -m pytest api/test_error_contract.py -q
```
预期：`ImportError: cannot import name '_rate_limited_payload'`

- [ ] **Step 7: 抽出纯函数并改文案（`api/main.py`）**

在 `RateLimitMiddleware` **之前**加：

```python
def _rate_limited_payload(retry_after: int = 60) -> dict:
    """全局限流触发时的响应体（抽成纯函数 ⇒ 可单测，不必真打 Redis）。

    ⚠️ 2026-10-01 修：此处原写 `"error": "Internal server error"` ——
       状态码是 429、文案却说"内部错误" ⇒ 调用方会以为**系统坏了**，
       而实际是**自己发太快**。这正是 `通用方法 §7.1` R3.3 要防的。
    """
    return {
        "error": f"请求过于频繁，请在 {retry_after} 秒后重试",
        "code": ErrorCode.RATE_LIMITED.value,
        "status_code": 429,
        "retry_after": retry_after,
    }
```

然后 `RateLimitMiddleware.dispatch` 里那段 `JSONResponse(status_code=429, content={...})`
改成：

```python
            response = JSONResponse(status_code=429, content=_rate_limited_payload())
            response.headers["Retry-After"] = "60"
            return response
```

**同类修正 3 处**（`503`，文案 `:460` `:481` `:496`）—— 把 `"error": "Internal server error"`
改成**说清是"还没就绪"**：

```python
            "error": "服务尚未就绪，请稍后重试",     # 原：Internal server error
```

⛔ **`:364` 那处（全局 500）不要动** —— 它**真的是**内部错误。

- [ ] **Step 8: 加一条守卫测试（防那 3 处被改回去）**

```python
def test_service_unavailable_copy_is_not_internal_error():
    """503 的三处也必须说清"未就绪" —— 它们与 500 不同。"""
    import inspect, main
    src = inspect.getsource(main)
    # 允许 500 处理器保留那句英文，但 503 的 payload 里不许再有
    unavailable_blocks = [b for b in src.split("status_code=503") if "Internal server error" in b[:400]]
    assert not unavailable_blocks, (
        "有 503 响应体还在用 'Internal server error' —— 那是'未就绪'，不是'内部错误'"
    )
```

- [ ] **Step 9: 跑全量 + CI 同款命令**

```bash
python -m pytest api/test_error_contract.py -q                                        # → 4 passed
python -m pytest api/ -m "not integration and not needs_db" -q                         # → 全绿
```

- [ ] **Step 10: 补 CHANGELOG 并提交**

```bash
git add api/exceptions.py api/main.py api/test_error_contract.py CHANGELOG.md
git commit -m "fix(错误契约): B12 —— 429/503 文案不再说'内部错误'，并加 retry_after"
```

---

## Task 2 · **B7** · 新建 `api/token_config.py`，把额度常量收口

> ### ⚠️ **2026-09-30 追加 / 10-01 已做：本 Task 顺带并入 3 条**（`/specs` 核账挖出的 · 见 `待办总表` 🅗 的 `S4`–`S6`）
>
> ⛔ **不另开轮次** —— 它们都落在**同一个新文件**上，分批做等于**改两遍 `token_config.py`**。
>
> | 并入 | 事 | 为什么必须在这里 |
> |---|---|---|
> | **`S4`** | 3 处 `record_usage(model="qwen-turbo")` 硬编码 ⇒ 改成**从 `llm` 对象取** | 它和 `S5` **不可拆**（见下） |
> | **`S5`** | **`PRICING` 补 `deepseek` 条目** | ⚠️ **只修 `S4` 不补价 ⇒ 落到 `_DEFAULT_PRICING` 兜底价，比"明确配一个"更糟**（看不出来是兜底） |
> | **`S6`** | **限流参数**（`global/user_limiter` 的 `rate`/`capacity`）也收进来 | 与 `B7` **同型**（参数写死）⇒ 一起收，⛔ 别再开一次 |
>
> ⇒ **Step 3 的 `token_config.py` 要多两块**（`MODEL_PRICING` 补 deepseek + 限流参数），
> 并**新增一个 Step** 改那 3 处 `model=`。

**Files:**
- Create: `api/token_config.py`
- Create: `docs/specs/token_config.md` ← ⛔ **必须同时建**，否则 `pre-commit-gates.py` 硬拦
- Create: `api/test_token_config.py`
- Modify: `api/token_tracker.py`（常量改为从 `token_config` 取）

**Interfaces:**
- Produces: `MAX_TOKENS_ANSWER` · `MAX_TOKENS_AGENT` · `SESSION_TOKEN_LIMIT` · `GLOBAL_DAILY_TOKEN_LIMIT` · `ROLE_DAILY_TOKEN` · `MODEL_PRICING` · `DEFAULT_MODEL_PRICING`

- [ ] **Step 1: 写失败测试**

```python
# api/test_token_config.py
"""额度常量的【唯一来源】的回归测试（对应 B7）。"""
import token_config


def test_single_call_caps_are_the_agreed_values():
    """业务方 2026-09-30 裁的起始值。⚠️ 终值等前端做完、浏览器实测后再调。"""
    assert token_config.MAX_TOKENS_ANSWER == 2000
    assert token_config.MAX_TOKENS_AGENT == 1024


def test_admin_is_no_longer_infinite():
    """🔴 业务方 2026-09-30 裁：「admin 也要同样上限」⇒ 不许是 inf。"""
    assert token_config.ROLE_DAILY_TOKEN["admin"] != float("inf")
    assert token_config.ROLE_DAILY_TOKEN["admin"] == token_config.ROLE_DAILY_TOKEN["premium"]


def test_single_call_cap_does_not_depend_on_role():
    """单次上限【不分角色】—— 否则对 admin 等于不存在。"""
    assert not hasattr(token_config, "ROLE_MAX_TOKENS")
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
python -m pytest api/test_token_config.py -q     # → ModuleNotFoundError: token_config
```

- [ ] **Step 3: 建 `api/token_config.py`**

```python
"""额度配置的【唯一落点】（B7 · 2026-10-01 落盘）。

为什么建这个文件：在此之前，额度类常量**散在 4 个文件 6 处**，且**单位混着**：
  · `permission.ROLE_QUOTA`（**次数**）
  · `token_tracker.ROLE_TOKEN_BUDGET`（token）· `MAX_THREAD_COST`（**元**）· `MAX_SINGLE_CALL_COST`（**元**）
  · `token_tracker.PRICING`（元/1000token）
  · `plan_execute.PLAN_TOTAL_BUDGET_SECONDS`（**秒**）
⇒ 这正是 `DEC-029`「两套口径差 35 倍」与 `决策一`「三套怎么合」的**物理原因**。

⚠️ **本模块只读 env，不做热加载** —— 故意的。
   `ChatOpenAI(model=…, max_tokens=…)` 是 **import 时求值**（17 个构造点全是），
   改了值本来就要重启。**只求"集中"，不求"热加载"。**
"""
import os


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# ==================== 单次上限（token）· ⛔ 不分角色 ====================
# 行业区间 500–2000（见 后端补齐清单 B7 附的检索来源）。
# ⚠️ 取上沿而不是"中和"：压低到 1800 以下**会开始截断答案**。
MAX_TOKENS_ANSWER = _int("TOKEN_MAX_ANSWER", 2000)   # RAG 答案生成 / WS agent
MAX_TOKENS_AGENT = _int("TOKEN_MAX_AGENT", 1024)     # Agent 对话 / planner / 质检
# 查询改写**已有自己的值**（query_rewriter.py:65/143），此处只登记、不改行为
MAX_TOKENS_REWRITE_VARIANTS = _int("TOKEN_MAX_REWRITE_VARIANTS", 200)
MAX_TOKENS_REWRITE_INTENT = _int("TOKEN_MAX_REWRITE_INTENT", 800)

# ==================== 分层上限（token）· 由后续计划接线 ====================
SESSION_TOKEN_LIMIT = _int("SESSION_TOKEN_LIMIT", 50000)          # B8
GLOBAL_DAILY_TOKEN_LIMIT = _int("GLOBAL_DAILY_TOKEN_LIMIT", 1_000_000)  # B10

# ==================== 角色日预算（token） ====================
# ⚠️ 档位体系【本轮不重塑】—— 业务方 2026-09-30：「还没有想好「分几档」，留第二轮」。
#    本轮只把 admin 的 inf 换掉。
ROLE_DAILY_TOKEN = {
    "free": _int("DAILY_TOKEN_FREE", 10_000),
    "premium": _int("DAILY_TOKEN_PREMIUM", 100_000),
    # ✅ 2026-09-30 裁（实施 2026-10-01）：admin = premium，⛔ 不再是 float("inf")
    "admin": _int("DAILY_TOKEN_ADMIN", 100_000),
}

# ==================== 模型单价（元 / 1000 tokens） ====================
# 迁自 token_tracker.PRICING（:50）。⚠️ 加新模型时**只改这里**。
MODEL_PRICING = {
    "qwen-turbo": {"prompt": 0.003, "completion": 0.006},
    "qwen-plus": {"prompt": 0.008, "completion": 0.016},
    "text-embedding-v2": {"prompt": 0.0005, "completion": 0},
}
# 未登记模型的**兜底单价** —— 取偏保守的一组（不低报花费）
DEFAULT_MODEL_PRICING = {"prompt": 0.003, "completion": 0.006}

# ==================== 花费上限（元）· 多级预算的第一、二级 ====================
MAX_SINGLE_CALL_COST = _float("MAX_SINGLE_CALL_COST", 0.5)
MAX_THREAD_COST = _float("MAX_THREAD_COST", 5.0)
```

> 🔴 **2026-10-01 更正（实施后回写）**：上面那段是**计划草稿**，其中
> `# 未登记模型的兜底单价 —— 取偏保守的一组（不低报花费）` **这句是错的** ——
> 0.003/0.006 只对**比 qwen-turbo 便宜**的模型保守，**对 `qwen-plus`（0.008/0.016）是低报**。
> 实际落地的 `api/token_config.py` **已把这句改掉**（含"兜底价不是上界"的说明）。
> 📄 为什么值得单记一笔：我**先信了这句旧注释**，又**把它写成测试** ⇒ **CI 直接红**。
> 见 `docs/specs/token_config.md` 的 ⚠️ 表 + `api/test_token_config.py`。

- [ ] **Step 4: 跑测试，确认通过**

```bash
python -m pytest api/test_token_config.py -q     # 计划时估计 3 条；实际落地 10 条（含后加的守卫）
```

- [ ] **Step 5: 写 `docs/specs/token_config.md`**

⛔ **不写会被 `pre-commit-gates.py` 硬拦**（"新增模块必须同时建 spec"）。
按 `docs/specs/quota_limiter.md` 的格式写四节，**重点写「⚠️ 看代码会误判的地方」**：

必须写进去的一条：**「本模块只集中常量，⛔ 不做运行时路由/热加载」** ——
看代码的人容易以为"集中了就动态了"，**那两件事不是一回事**。

- [ ] **Step 6: 让 `token_tracker.py` 从 `token_config` 取值**

把这几处的**字面量**换成引用（⛔ **行为不变**，纯搬家）：

```python
from token_config import (
    MODEL_PRICING as PRICING,
    DEFAULT_MODEL_PRICING as _DEFAULT_PRICING,
    ROLE_DAILY_TOKEN as ROLE_TOKEN_BUDGET,
    DEFAULT_DAILY_TOKEN_BUDGET,
    MAX_SINGLE_CALL_COST,
    MAX_THREAD_COST,
)
```

⚠️ **`DEFAULT_DAILY_TOKEN_BUDGET` 目前是 `int(os.getenv("DEFAULT_DAILY_TOKEN_BUDGET", "100000"))`
（`token_tracker.py:283`）** —— 也搬进 `token_config.py`。

- [ ] **Step 7: 跑全量，确认行为没变**

```bash
python -m pytest api/ -m "not integration and not needs_db" -q     # → 应仍是 124 passed
```

- [ ] **Step 8: 更新模块表并提交**

```bash
bash scripts/spec_status.sh --write
git add api/token_config.py api/test_token_config.py docs/specs/token_config.md \
        docs/specs/README.md api/token_tracker.py
git commit -m "feat(额度): B7 —— 建 token_config.py 把散在 4 文件的额度常量收口（行为不变）"
```

---

## Task 3 · **⚠️ 已移出本计划** —— 见文末「后续」的 ①b

> ## 🔴 写这份计划时发现的一个**顺序陷阱**（**这条比 Task 3 本身重要**）
>
> **初稿把 Task 3（撤掉「请求次数」配额）排在这里，是错的。**
>
> **为什么错**：`决策一` 要**撤掉** `QuotaMiddleware` 的每日次数计数，
> **而 token 那套的【会话级】与【全局日级】（B8 / B10）在 ①b 里**。
> ⇒ **先撤次数、后接 token** ⇒ **中间出现一段"谁都不拦"的窗口** ——
> 一个**已经能上线跑**的服务**开了个日限额的洞**，而且**没人会立刻发现**。
>
> **正确顺序**：**先让 token 那套接管（①②b 的 B8/B10/B11 落地），再撤次数。**
>
> ⇒ **`决策一` 的【实现】跟着挪到 ①b 的最后一步**；本计划里的 Task 0 只**建 DEC**（把口径定死），
> **⛔ 不动任何行为**。
>
> 📌 **教训（值得单独记）**：**「降级旧机制」和「上线新机制」必须【新先旧后】**
> —— 反过来就有一段**看起来一切正常**的空窗期。
> 本仓已有同型前科：`docs/复盘/2026-09-20-同源的两个输入不能互相作证.md` 讲的也是"两个都在，但谁都不真拦"。

---

## （原 Task 3 · 已移出 —— 保留在此只作查阅，**执行请去 ①b**）

### 原 Task 3 · **`决策一` 落地** · 次数配额降级 + admin 去 `inf`

**Files:**
- Modify: `api/permission.py`（`ROLE_QUOTA` → 权限权重）
- Modify: `api/test_plan_execute_tools.py`（**那条钉住"两套口径"的用例要改**）
- Modify: `CHANGELOG.md`

**⚠️ 本任务是【唯一会改行为】的一个** —— 前两个是加字段和搬家。

- [ ] **Step 0: 先读那条会红的测试**

`api/test_plan_execute_tools.py:498` 的 `test_free_users_real_daily_limit_on_plan_execute_is_known`。
它断言 `by_tokens < by_requests`，**并直接 `from permission import ROLE_QUOTA`**。
⇒ **`决策一` 一落地它必红** —— **这不是意外，是它本来就想提醒的事**（它的 docstring 写着
「📌 谁改了 `ROLE_TOKEN_BUDGET`…这条会红 —— ⭐ 这不是"防改动"，是"防不知情"」）。

- [ ] **Step 1: 写失败测试**

```python
# 加到 api/test_token_config.py
def test_request_quota_is_no_longer_a_second_accounting_system():
    """决策一：**统一到 token 一套** ⇒ 「请求次数」不再是一套独立配额。

    它保留下来只作**接口权重**（哪些端点更"贵"），⛔ 不再是"每天 100 次"那种口径。
    """
    from permission import get_user_quota, ROLE_QUOTA
    assert ROLE_QUOTA == "deprecated-见-DEC-040", (
        "次数配额应已降级 —— 若这里还是数字，说明决策一没落地"
    )
```

- [ ] **Step 2: 跑，确认失败**

```bash
python -m pytest api/test_token_config.py::test_request_quota_is_no_longer_a_second_accounting_system -q
```

- [ ] **Step 3: 改 `api/permission.py`**

```python
from enum import Enum

class UserRole(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    ADMIN = "admin"


# 🔴 2026-09-30：本表**不再是配额**（`DEC-040` · 决策一）。
#
# 原先它是一套【独立的每日请求次数配额】（FREE 100 / PREMIUM 10000 / ADMIN 无限），
# 与 `token_tracker.ROLE_TOKEN_BUDGET`（token）**互不知情** ——
# `DEC-029` 实测两者**口径差 35 倍**（`plan_execute` 一次 ~3346 token ⇒ 按次数能跑 100 次、
# 按 token 只能跑 ~3 次）。
#
# ⇒ 决策一（业务方 2026-09-30）裁：**统一到 token 一套**。
#    本常量**降级为「接口权重」** —— 用来表达"哪些端点更贵"，⛔ **不再当日限额用**。
#    ⚠️ 具体怎么用（或者干脆删掉）**还没定** —— 见 `DEC-040` 的遗留一节。
ROLE_QUOTA = "deprecated-见-DEC-040"


def get_user_role(user_name: str) -> UserRole:
    """根据用户名获取角色。⚠️ 现在仍是硬编码；接 DB 的落点是 B9/R1.3（已挂起）。"""
    if user_name == "admin":
        return UserRole.ADMIN
    elif user_name == "test_user":
        return UserRole.PREMIUM
    else:
        return UserRole.FREE
```

⛔ **`get_user_quota` 暂时保留但会抛异常** —— 逼着调用点显式改掉（见 Step 4），
免得"静默变成了别的语义"：

```python
def get_user_quota(user_name: str):
    raise NotImplementedError(
        "次数配额已按 DEC-040 降级，不再是配额 —— "
        "调用点请改走 token 那套（token_config.ROLE_DAILY_TOKEN / token_tracker）。"
    )
```

- [ ] **Step 4: 改三个调用点**

| 位置 | 怎么改 |
|---|---|
| `api/main.py:245`（`QuotaMiddleware`） | **整段撤掉计数**，只保留"身份解析 + 响应头"。⚠️ **注意**：`_rate_limited_payload` 里那句"调用次数已用完"要改成 token 口径 |
| `api/api_v1.py:221` | 改走 `token_tracker.get_token_budget_info(user_name)`（它已能答"已用/剩余/预算"） |
| `api/api_v1_rag.py:25` | 只删 import（**实测未使用**） |

- [ ] **Step 5: 改那条会红的测试**

`api/test_plan_execute_tools.py::test_free_users_real_daily_limit_on_plan_execute_is_known`
→ **重写成"只剩一套口径"的版本**：删掉 `ROLE_QUOTA` 的比较，
**保留**「FREE 用户对 `plan_execute` 的真实每日次数 ≈ 3」这个**实测数**（它本身是宝贵事实），
并把它**改挂到 token 口径**上。**别整条删掉** —— 那会丢掉 `DEC-029` 的唯一量化证据。

- [ ] **Step 6: 跑全量**

```bash
python -m pytest api/ -m "not integration and not needs_db" -q
```
预期：全绿。**如果有红，先看是不是"还有地方在读次数配额"** —— 那正是这个任务要清干净的东西。

- [ ] **Step 7: 更新文档 + 提交**

要同步的三处：`docs/specs/quota_limiter.md`（它写着"额度来自 `permission.ROLE_QUOTA`"）·
`docs/specs/token_tracker.md`（本文件的 ⚠️ 节）· `CHANGELOG.md`

```bash
git add -A
git commit -m "refactor(配额): 决策一落地 —— 次数配额降级，统一到 token 一套（DEC-040）"
```

---

## ⏭ 后续（**不在本计划**，等 ①a 落地再立）

| 计划 | 条 | 为什么必须等 |
|---|---|---|
| **①b · 限额与熔断** | **B8**（会话级）· **B10**（全局日级）· **B11**（熔断 + `L2` 顺带）· **B13**（实跑核）<br>🔴 **+ `决策一` 落地（原 Task 3）** | ① 它们要挂的**常量和取值口径**由 ①a 定；② **`决策一` 必须排在 B8/B10 【之后】** —— 新机制先上线，旧机制才降级（见 Task 3 那节的「顺序陷阱」） |
| **② · 人工接管** | B4 · B5 · B6 | 与 ① 无依赖，可并行 |
| **③ · 流式与取消** | B1 · B2 · B3（核） | 同上；B2 自标「最易假完成」⇒ 排最后 |

> ### 📌 ①b 的**开工顺序**（写在这里，免得到时又想反）
>
> ```
> B7 的接线（把 token_config 接到 15 个构造点）   ← ✅ 2026-10-01 做完
>   → B8  会话级上限                              ← ⭐ 下一步
>   → B10 全局日级总额        ← 到这一步，token 那套【才真正能拦住东西】
>   → B11 熔断（按 key 断路器 + 要素④ 恢复实测 Redis TTL）+ L2 顺带
>   → 决策一落地（撤次数配额）  ← ⭐【最后】
>   → B13 实跑核一遍可见性
> ```

---

# 🔵 实施计划 ①b · **限额与熔断**（2026-09-30 立 · **执行中** —— Task 0 ✅ / Task 1 ✅ / Task 2 ✅ / Task 3 ✅ / **Task 4 起待做**）

> **来源**：`后端补齐清单-待裁-20260929.md` 的 **B8 · B10 · B11 · B13 · 决策一（实现）**；
> 以及 `LLM模型路由与额度策略-待裁-20260930.md` 的 **L2**（十几个 model 顺带）。
> **前置**：**①a 必须先落地**（B7 的 `token_config.py` 要先建出来，否则没有常量可取）。
> **本计划【会改行为】** —— 这是它与 ①a 最大的区别。

**目标**：让 token 那套配额**真的能拦住东西** —— 会话级、全局日级、触顶熔断；
然后把旧的「请求次数」配额**最后**降级掉。

**架构**：**新增一层「查询 + 判定」**，全部**查库**（`token_usage_logs`），⛔ **不复用 `_thread_summary`**（理由见 Task 2）。
熔断做成**按 key 的通用断路器**（Redis 标记 + **TTL 分两种**：额度耗尽=永久 / 临时故障=数小时，见 Task 0 `L3`）—— 这一套同时覆盖
**全局额度触顶**（动作=拒绝）与 **L2 的「某个模型免费额度耗尽」**（动作=换模型）。

---

## Task 0 · **前置决策：`L3` / `L4` / `L5`** —— ✅ **2026-10-01 全部已裁**

> 这三条在 `LLM模型路由与额度策略-待裁-20260930.md` §七 标着「**等 `B11` 开工时再答**」。
> **业务方 2026-10-01 裁完** —— 权威记录在 **`docs/待办总表.md` §一·附 的 L 表**（本表只留摘要）。

| # | 问题（原备选） | ✅ **裁定** | 影响哪个 Task |
|---|---|---|---|
| **L3** | 熔断 key 的 **TTL 设多久** | 🔴 **分两种 key、两种 TTL**（**不是**原推荐的"到次日 0 点"）：<br>① `AllocationQuota.FreeTierOnly`（免费额度耗尽）⇒ **永久**，人工解封；<br>② 其余（限流 / 临时故障）⇒ **数小时**。<br>⚠️ **我原推荐的"到次日 0 点"已被证伪**（见下方更正块） | Task 4 |
| **L4** | **降级要不要对用户可见** | ✅ **响应里带标记**（与我推荐一致） | Task 5（L2 换模型时） |
| **L5** | **降级链按什么排序** | ✅ **人工指定顺序**（与我推荐一致） | Task 5 |

> 🔴 **2026-10-01 更正（本表自己那句推荐是错的）**：原写「到次日 0 点（**我推荐**，与"预算按天"天然对齐）」。
> **前提就不成立**：源文档 §三 部件 5 明写**免费额度是一次性的（90 天有效期），不是每天重置**
> ⇒ 「预算按天」这个类比**用错了对象** ⇒ 按它设 TTL，**到期自动放出来会立刻再撞一次 429**
> （额度根本没恢复）。**"天然对齐"是对齐了一个不存在的天然。**
> 📌 与 `①a` 那条 CI 红**同型**：**我拿一个自己觉得顺的类比，当成了事实**。

> ⚠️ **注意 L4 / L5 的对象不是"额度触顶"** —— 触顶已裁「**直接拒绝、不降级**」（`B11` 要素②）。
> 它们的对象是 **`L2`：某个模型的免费额度耗尽 ⇒ 换下一个模型**。

- [x] **Step 1**：把这三条的裁定**写进 `docs/待办总表.md` §一·附**的 L 表 —— ✅ **2026-10-01 做完**。

---

## Task 1 · **B7 接线** · ✅ **2026-10-01 做完** —— 让【15】个构造点用上 `token_config.MAX_TOKENS_*`

> 🔴 **2026-10-01 落盘时更正两处【我自己写错的计划】**（原写「17 个」）：
> 1. ⚠️ **「17」是我没数就写下的数。** 实测（AST 扫 `api/*.py` 的 `ChatOpenAI(`）= **15 处**。
>    计划里那张 Files 清单逐条数出来是 **14** —— 连清单本身也对不上 17。
>    ⇒ **本 Task 的权威清单不是这张表，是 `api/test_max_tokens_wiring.py` 的
>    `EXPECTED_MAX_TOKENS`**（它**同时**是守卫：漏一个就红）。
> 2. 🔴 **`evaluate_with_ragas.py:44` 计划里【一次都没提】** —— 它也是个 `ChatOpenAI` 构造点，
>    而且**恰恰是"漏掉会看不出来"的那类**（离线评测脚本，不跑就没人发现它没有上限）。
>    ⇒ 已补：接 `MAX_TOKENS_ANSWER`（它 `:127` 生成被评答案、`:272` 又当 RAGAS judge，
>    **两处都是长输出**；给 1024 可能**截断 judge 输出 ⇒ 评分静默失真**）。
> 📌 **教训与 `①a` 那条 CI 红同族**：**计划里的数字同样是"作者当时的理解"，不是事实。**
>    ⇒ 计划交给守卫测试去核，⛔ 别交给"我记得写的是 17"。

> ⚠️ **2026-09-30 追加：本 Task 顺带并入 1 条**（`待办总表` 🅗 的 **`S12`**）
>
> **`S12`**：`agent_graph_advanced.py:39` 的 `llm` **没有 `timeout` / `max_retries`** ——
> 同型问题 `plan_execute.py:70-76` **早就修过**（显式设 30/20/15 + `max_retries=1`），**这里漏了**。
> ⇒ **本 Task 本来就要动那 17 个构造点**，顺手补上，⛔ **别另开一轮**。
> ⬜ **具体秒数待定** —— 这是**多轮对话**，比 `plan_execute` 的单步长，**别直接抄 30/20/15**。

**Files:**
- Modify: `api/api_v1_rag.py`（`:563` `:726`）· `api/rag_pipeline.py`（`:48`）· `api/agent_graph.py`（`:20`）· `api/agent_checkpointer.py`（`:20`）· `api/agent_graph_advanced.py`（`:39`）· `api/plan_execute.py`（`:92` `:249` `:458`）· `api/agent_graph_advanced_learning.py`（`:20` `:85-87` `:221`）
- Test: `api/test_max_tokens_wiring.py`（新建）

**Interfaces:**
- Consumes: `token_config.MAX_TOKENS_ANSWER` / `MAX_TOKENS_AGENT`

⚠️ **一致性陷阱**：17 处要**按角色分类**接，⛔ **不是全接同一个常量**：
**答案生成类**（RAG answer / WS agent / `rag_pipeline.answer_llm`）接 `MAX_TOKENS_ANSWER`；
**中间步骤类**（planner / executor / quality_checker / agent 各节点）接 `MAX_TOKENS_AGENT`。

- [ ] **Step 1: 写失败测试**

```python
# api/test_max_tokens_wiring.py
"""单次上限的接线回归（B7）。

🔴 为什么不能只测常量值：常量对了、**没接上**，等于没有上限。
   本文件钉的是"构造点真的带上了 max_tokens"。
⚠️ 不碰 DB / Redis —— 只看构造出来的对象属性。
"""
import inspect


def test_no_chat_openai_without_max_tokens():
    """全仓**不许**再有"没给 max_tokens"的 `ChatOpenAI(...)` 调用。

    ⚠️ 用 AST 而不是 grep：`ChatOpenAI(` 会出现在注释与 docstring 里
       （本仓栽过 —— 见 `docs/规范/开发规范.md` §3.1「批量替换后按位置核」）。
    """
    import ast, pathlib
    offenders = []
    for p in pathlib.Path("api").glob("*.py"):
        if p.name.startswith("test_"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "ChatOpenAI":
                continue
            if not any(k.arg == "max_tokens" for k in node.keywords):
                offenders.append(f"{p}:{node.lineno}")
    assert not offenders, (
        "这些 ChatOpenAI(...) 没设 max_tokens ⇒ 单次上限对它们不存在：\n  "
        + "\n  ".join(offenders)
    )
```

- [x] **Step 2: 跑，确认失败** —— ✅ 2026-10-01，**列出 15 处**（原计划写"17 处"，实测 15）

```bash
python -m pytest api/test_max_tokens_wiring.py -q
```
预期：FAIL，并**列出**那 15 处（**这条失败信息本身就是待办清单**）。
📌 **实测**：`2 failed, 1 passed` —— 两条红各列一遍那 15 行（含计划漏掉的 `evaluate_with_ragas.py:44`）。

> ⚠️ **本 Task 的 Step 1 最终落地**是 **3 条测试**（计划只写了 1 条）—— 多出来的两条见
> `api/test_max_tokens_wiring.py` 顶部：
> * `test_each_site_uses_the_agreed_budget` —— 钉**分类**（只钉"有没有"的话，全接成 1024 也能过，
>   而那会把**答案截断**；这正对应本 Task 顶部那条 ⚠️「一致性陷阱」）
> * `test_the_two_budgets_are_distinct_and_answer_is_larger`

- [x] **Step 3: 逐处接上** —— ✅ 2026-10-01，**15 处全接完**

模式（以 `api/agent_checkpointer.py:20` 为例）：

```python
from token_config import MAX_TOKENS_AGENT          # 新增
llm = ChatOpenAI(
    model=LLM_MODEL_FAST,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    max_tokens=MAX_TOKENS_AGENT,                   # 新增
)
```

分类表（**照这个接，别自己判断**）：

| 构造点 | 接哪个 |
|---|---|
| `api_v1_rag.py:566`（流式答案）· `:730`（WS agent）· `rag_pipeline.py:49`（`answer_llm`）· **`evaluate_with_ragas.py:50`**（计划里**漏了**，2026-10-01 补） | **`MAX_TOKENS_ANSWER`** |
| `agent_checkpointer.py:21` · `agent_graph.py:21` · `agent_graph_advanced.py:50` · `agent_graph_advanced_learning.py:21/87/88/89/223` · `plan_execute.py:93/251/461` | **`MAX_TOKENS_AGENT`** |

> ⚠️ **行号是 2026-10-01 接线【之后】的**（接线本身让每处 +1~2 行）。
> ⛔ **别拿这张表当清单用** —— 权威清单是 `api/test_max_tokens_wiring.py` 的 `EXPECTED_MAX_TOKENS`。

- [x] **Step 4: 跑测试，确认通过** —— ✅ **2026-10-01**

```bash
python -m pytest api/test_max_tokens_wiring.py -q         # → 3 passed
python -m pytest api/ -m "not integration and not needs_db" -q   # → 15 failed / 127 passed（红的仍是 Redis/MCP）
```

> 📌 **实测记录**（⚠️ 本机无 Redis ⇒ 那 15 条红是**本机固有问题**，CI 上绿）：
> * **接线前**（在 `HEAD=a257de3` 的独立 worktree 上实测）：`15 failed / 124 passed / 3 skipped`
> * **接线后**：`15 failed / 127 passed / 3 skipped` ⇒ **+3 正好是新测试 3 条**
> * **两份 `FAILED` 清单 `diff` 逐条相同** ⇒ 无回归

- [x] **Step 5: 提交** —— ⏸ **待业务方发话**（业务方 2026-10-01：「不要频繁提交 commit」）
  ⚠️ 且**门这一层就过不去**：`.claude/worktrees/ci-local-env`（**业务方正在用的 worktree，⛔ 别动**）
  让**文档链接门变红** ⇒ `commit` 被 `.claude/hooks/pre-commit-gates.py` 拦下。
  📌 **不是本 Task 的改动有问题** —— 红线全落在那个 worktree 的副本里。详见 `ROADMAP.md` ①b 段的「一处副作用」。

```bash
git add api/*.py api/test_max_tokens_wiring.py
git commit -m "feat(额度): B7 接线 —— 15 个 ChatOpenAI 构造点带上单次上限（2000/1024）+ S12"
```

---

## Task 2 · **B8** · 会话级 token 上限 · ✅ **2026-10-01 做完**

> 🔴 **落地时更正计划里三处**（**口径**，全部由业务方 2026-10-01 裁定：
> **窗口** / **key** / **范围**）—— 见 `docs/decisions/DEC-041-B8会话上限的窗口与接线范围.md`：
>
> 1. **窗口 = 会话 × 今日**（带 `CURRENT_DATE`）。计划原样是对的，**但那是"没写理由的选择"**；
>    定它的真正理由是：与仓里**其余所有 token 预算**（用户日预算）同口径，
>    ⛔ 而不是"顺手复制 `get_daily_token_usage`"。
> 2. 🔴 **key 从「只 `thread_id`」改成「`user_name` + `thread_id`」** ——
>    计划**只想到 `thread_id`**。核实端点时发现 4 个 Agent 端点的 `thread_id` **默认值是 `"default"`**
>    ⇒ 只按 `thread_id` 分桶，**所有没显式传它的调用者共用一个桶**，谁先烧完 50000
>    **其他默认用户一起撞 429**（软共享状态 → 硬拒绝）。
>    ⇒ 连带 **接口改名**：`get_thread_token_usage` → **`get_session_token_usage`**
>    （key 变两段了，沿用旧名**表述不实**），且 `user_name` **必填、不给默认值**
>    （给了默认值 ⇒ 漏传的调用点静默落进同一个桶，**决策二白定**）。
> 3. 🔴 **范围：计划写「两处主链」，实做【7 条】** —— 来源文档 B8 要求「**覆盖全部对话链**」。
>    ⚠️ **但比来源文档又少 4 条** —— 逐条核实后发现 **`/rag/ask` · `/rag/jwt_ask` ·
>    `/rag/async_ask` · `/rag/parallel_ask` 根本不调 LLM**（前两条只 `SELECT documents`，
>    后两条是 `asyncio.sleep(2)` 的 mock）⇒ **接上去是错的**（让不花钱的接口占额度甚至被拦）。
>
> 📌 **教训与 Task 1 那条同族**：**计划里的清单同样是"作者当时的理解"，不是事实。**
>    Task 1 是**少数**了（漏 `evaluate_with_ragas.py`），本条是**多数**了（多列 4 条）
>    —— 两个方向都会错，⇒ **清单必须逐条对着代码核**。

**Files:**
- Modify: `api/token_tracker.py`（新增 2 个函数）· `api/api_v1_agent.py`（5 处接线 + 1 个新参数）·
  `api/api_v1_rag.py`（2 处接线 + 1 个新参数 + 1 个 WS 会话 id）
- Create: `api/test_session_budget_offline.py`（**无 marker ⇒ 进 CI**）·
  `api/test_session_budget.py`（`needs_db`）· `api/test_session_budget_wiring.py`（**接线守卫**）

**Interfaces（⚠️ 与计划原名不同 —— 见上方更正 ②）：**
- Produces: `get_session_token_usage(user_name: str, thread_id: str) -> float`
- Produces: `check_session_token_budget(user_name: str, thread_id: str, estimated_tokens: int = 0) -> tuple[bool, str]`

> ### 🔴 那个**必须避开**的陷阱（设计理由）—— 计划写对了，保留
>
> `record_usage` 里已经在内存里按 thread 累加了（`_thread_summary`）。
> **⛔ 但绝不能拿它当上限的数据源** —— 它是**进程内存**，
> **重启即清零** ⇒ 想绕开上限，**重启一下就行**。
>
> ⇒ **权威数据源只能是 `token_usage_logs` 表**（`get_daily_token_usage` 就是这么做的）。
> ⚠️ 这也意味着**每次检查要查一次库** —— 这正是 Task 4 的熔断器要解决的（触顶后别再查）。
>
> ⚠️ **来源文档 B8 的「落点」栏与此相反**（它写「`_thread_summary` **可直接扩展**」）——
> **那一句已被 `DEC-041` 显式推翻**，以 DEC 为准。

### 判据（可打印）

```bash
venv/bin/python -m pytest api/test_session_budget_offline.py -q     # 11 passed
venv/bin/python -m pytest api/test_session_budget_wiring.py -q      # 8 passed
venv/bin/python -m pytest api/ -m "not integration and not needs_db" -q
#   ⇒ 15 failed / 138 passed / 3 skipped
#      接线前是 15 failed / 127 passed / 3 skipped ⇒ +11 = 本次新增的离线判据
#      `15 failed` 与接线前 FAILED 清单同为「本地无 Redis」，**逐条同类 ⇒ 无回归**
```

**做过红→绿实证的守卫**（⛔ 不是"写完就绿"）：

| 守卫 | 怎么验出红 |
|---|---|
| `test_session_query_is_scoped_by_user_name` | 把 SQL 的 `WHERE user_name = %s` 改掉 ⇒ **红** |
| `test_user_name_is_required` | 给 `user_name` 加默认值 `"unknown"` ⇒ **红** |
| `test_endpoint_calls_session_budget[memory_chat]` | 摘掉 `memory_chat` 里的判定调用 ⇒ **红** |

**对象级核**（⛔ 不是只看源码）：`import main` 后读 `app.openapi()` ——
6 个 HTTP 端点的 query 参数里都有 `thread_id`（含**新补的** `/agent/plan_execute` ·
`/rag/stream_search`）。

### 并入 `🅗 S9`

接线的同时把「**同一维度、两种窗口**」写进 `DEC-041` 备选方案·一 与本节：
`MAX_THREAD_COST`（元/线程，**无日期**）vs 会话 token 上限（**按日**）——
⚠️ **它是【已知且有意】的**，归并留给 `DEC-040` 的 `①b` Task 6。⛔ 别当成 bug 顺手"统一"。

---

## Task 3 · **B10** · 全局日级 token 总额 · ✅ **2026-10-01 做完**

**Files:**
- Modify: `api/token_tracker.py`
- Test: `api/test_global_daily_budget_offline.py`（无 marker，进 CI）

**Interfaces:**
- Produces: `get_global_daily_token_usage() -> float`
- Produces: `check_global_daily_budget(estimated_tokens: int = 0) -> tuple[bool, str]`

### ✅ 做完了什么

| 项 | 落点 |
|---|---|
| `get_global_daily_token_usage()` | `api/token_tracker.py` —— `SUM(total_tokens) WHERE created_at >= CURRENT_DATE`，**⛔ 无 `user_name`** |
| `check_global_daily_budget(estimated_tokens=0)` | 同上；阈值取 `token_config.GLOBAL_DAILY_TOKEN_LIMIT` |
| 阈值 | **`1_000_000` /天** —— 值没变，但**从"没人读的默认值"变成了裁定值** |
| 测试 | `api/test_global_daily_budget_offline.py` —— **12 passed**（无 marker ⇒ 进 CI） |
| 决策 | `docs/decisions/DEC-042-B10全局日级阈值与fail-open.md` |

### 🔴 三处与计划原样不同的地方（都已落地）

1. **阈值是【业务方裁定】过的，不是默认值**。
   源文档 B10 的「✍️ 裁」栏原文是「**⚠️ 附一问（仍待答）：具体阈值 ______（业务判断，我不替你定）**」。
   ⇒ 业务方 2026-10-01 裁定 = **`1,000,000` /天**（≈ ¥1–2/天 · = 10 个 premium 满额）。
   ⚠️ 选它的**另一个理由**：5,000,000 太松 ⇒ 熔断**永远触发不了** ⇒ **验收时无法证明它成立**。
2. **`estimated_tokens` 从「收下不用」改成「真的参与判定」**。
   计划样例的签名有它，**函数体里却没用** —— 「签名看着对、行为是死的」。
   ⇒ 已补上，并加 `test_estimated_tokens_can_trip_it` 钉住（变异验证：删掉那三行 ⇒ 红）。
3. **守卫改用 AST，不用计划里那段 `inspect.getsource(...).split('"""')[-1]`**。
   理由与 `B8` 同：**注释/docstring 里也有 `user_name` 这些词**，
   按"源码里有没有这个词"判会把**注释**当成 **SQL**（`docs/规范/开发规范.md` §3.1）。
   ⇒ 统一用 `ast.walk` 取 `cur.execute(...)` 的**字面量**。

### ⚠️ 本任务【不接线】——「全绿」≠「全局限额生效」

`check_global_daily_budget` **没有任何调用点**。接线在 **`Task 4`（`B11`）**：
断路器 + `api/main.py` 放行路径。

> 🔴 **这是同一个陷阱的第三次**：
> · `B7` 之前 —— 常量建好了，**没接上** ⇒ 单次上限不存在；
> · `B8` 之前 —— 有 `SESSION_TOKEN_LIMIT`，**没有判定函数**；
> · **`B10` 现在** —— 有判定函数，**没有调用点**。
> ⇒ 📌 **判据**：`grep -rn "check_global_daily_budget" api/ --include="*.py"` 只应命中
> **定义处 + 测试**；**命中不了任何 `api_v1_*.py` = 它还没生效**。

### 证据（可打印）

```bash
pytest api/test_global_daily_budget_offline.py -q    # 12 passed
pytest api/ -m "not integration and not needs_db" -q # 15 failed / 158 passed / 3 skipped
```

全量里 15 条失败**全是** `redis.ConnectionError`（本机没起 Redis），与改动前同集合。
📌 **条数对账**（别只看"通过数涨了"）：无 `B8`/`B10` 三个文件时收集 **145** 条
⇒ `+11 +8`（B8 两份）⇒ 164 ⇒ `+12`（本任务）⇒ **176** = 实跑 `158 + 15 + 3`。
（⚠️ 另有一份 `api/test_global_daily_budget.py` 带 `needs_db` ⇒ **被 CI 命令 deselect**，不计入 176。）

### 🔴 那条 SQL **真的被执行过** —— 但这一步有个坑，记下来

**离线测试从头到尾【没有执行】那条 SQL**（只 `AST` 取字面量）。
⇒ 表名/列名/语法错，**CI 永远绿**。这是 `Task 3` 计划里没堵上的一个口子。

**本机 PG 没起**（`nc -z localhost 5432` 不通；`docker ps` 空）⇒ `needs_db` 那类跑不了。
⇒ 改用 **stdlib `sqlite3`**：把**从函数里 AST 取出的那条真 SQL 字符串**（⛔ 不是我重打的）
配上 `api/schema.sql` 里那三列的真实 DDL 执行一遍（这条 SQL 无 PG 专有构造）：

```bash
# 一次性验证（未提交成测试 —— sqlite ≠ postgres，提交它会造成"验过了"的错觉）
sqlite> CURRENT_DATE = 2026-10-01
【全站】今日         = 12000   ← 1000(alice) + 2000(bob) + 4000(alice) + 5000(admin)
【对照·单用户】alice = 5000
【对照·单用户】bob   = 2000
```

✅ **证明了**：SQL 真的可解析可执行 · **跨用户求和**（含 `admin`）· **日期窗口真的在生效**
（昨天那条 9999 **没被算进今日**）。
⛔ **没证明**：PostgreSQL 下的行为（方言/类型/时区）· 真库上的列名是否 100% 一致
（列名是对着 `api/schema.sql` 与 `api/db.py:109` 的建表语句核的，**不是**对着真库核的）。
⇒ **补洞口的是 `api/test_global_daily_budget.py`**（`needs_db`）—— 本机起 PG 后跑它。

### 变异验证（**4 条守卫逐条证明会红**，跑完即还原、sha256 一致）

| 变异 | 变红的测试 |
|---|---|
| 全局 SQL 加回 `WHERE user_name = %s` | `test_global_query_has_no_user_filter` · `test_the_two_daily_queries_are_actually_different` |
| 全局 SQL 去掉 `CURRENT_DATE` | `test_global_query_is_today_only` |
| 阈值写死在函数里（不取 `token_config`） | `test_limit_comes_from_token_config` |
| 删掉 `estimated_tokens` 的判定 | `test_estimated_tokens_can_trip_it` |

---

## Task 4 · **B11** · 熔断（按 key 的通用断路器）

**Files:**
- Create: `api/breaker.py` + `docs/specs/breaker.md`（⛔ 新建模块**必须**同时建 spec，否则 `pre-commit-gates.py` 硬拦）
- Create: `api/test_breaker.py`（无 marker）
- Modify: `api/token_tracker.py`（触顶时开断路器）· `api/main.py`（放行前先问断路器）

**Interfaces:**
- Produces: `is_open(key: str) -> bool` · `trip(key: str, ttl_seconds: int) -> None` · `seconds_until_reset(key: str) -> int`
- key 形如 `global:2026-09-30`（B11）/ `model:qwen-turbo:2026-09-30`（`L2`）

> ### 为什么是「按 key」而不是写死"全局额度"
> 这就是 `L2`「十几个 model 顺带」的**具体形态**：**同一个函数换一个 key 前缀**。
> ⛔ 不为 `L2` 先建任何东西。

- [ ] **Step 1: 写失败测试**（mock Redis，⛔ 不连真 Redis）

```python
def test_trip_then_is_open_then_expires(monkeypatch):
    """开 → 判 → 到期恢复。⚠️ 用假 Redis，不连真服务。"""
    import breaker
    fake = {}
    monkeypatch.setattr(breaker, "_setex", lambda k, ttl, v: fake.__setitem__(k, (ttl, v)))
    monkeypatch.setattr(breaker, "_exists", lambda k: k in fake)
    monkeypatch.setattr(breaker, "_ttl", lambda k: fake.get(k, (0, None))[0])

    assert breaker.is_open("global:2026-09-30") is False
    breaker.trip("global:2026-09-30", ttl_seconds=3600)
    assert breaker.is_open("global:2026-09-30") is True
    assert breaker.seconds_until_reset("global:2026-09-30") == 3600


def test_breaker_keys_are_daily():
    """🔴 key 必须带日期 —— 那才让"跨天自然恢复"成立（B11 要素④）。"""
    import breaker
    k = breaker.daily_key("global")
    import datetime
    assert datetime.date.today().isoformat() in k
```

- [ ] **Step 2: 跑 → 失败 → Step 3: 实现 `api/breaker.py`**（用 `rate_limiter.py` 同一个 `redis.Redis` 连接方式；`trip` 用 `SETEX`）

- [ ] **Step 4: 接线**（`token_tracker` 触顶 ⇒ `trip`；`main.py` 中间件先 `is_open` ⇒ 直接抛 `AppException(QUOTA_EXCEEDED, retry_after=…)`）

- [ ] **Step 5: ⭐ 要素④ 的【实测】**（**这是 B11 唯一需要新实测的一条**）

```bash
# 开一个 5 秒的断路器，等它自己消失 —— 证明"到点真的会恢复"
docker compose exec redis-rag redis-cli --eval /dev/stdin <<'LUA'
redis.call('SETEX', KEYS[1], ARGV[1], '1')
return redis.call('TTL', KEYS[1])
LUA
```
⇒ 记下 `TTL` 与到点后 `EXISTS` 的结果，**写进 `docs/specs/breaker.md`**。
⚠️ `quota_limiter.md` 里那条「`EXPIRE 86400` 从未实测过 TTL」**一并核掉**（同一件事）。

- [ ] **Step 6: 跑 + 建 spec + 提交**

---

## Task 5 · **`L2` 顺带** · 某个模型的免费额度耗尽 ⇒ 换下一个

**Files:** Modify `api/breaker.py` 接线处（**复用 Task 4 的断路器，不新建文件**）

- [ ] ⛔ **开工前必须已有 `L3` / `L4` / `L5` 的裁定**（Task 0）。
- [ ] 判据（`LLM模型路由与额度策略` 坑②）：**只对 `403` + `AllocationQuota.FreeTierOnly` 开断路器**，
  ⛔ **`RateLimitExceeded`（限流）不许开** —— 那是"等一下"，不是"用完了"。
- [ ] key 用 `model:<名>:<日期>`；动作按 `L4`/`L5` 裁的结果（换哪个、要不要对用户可见）。

---

## Task 6 · **`决策一` 落地** · 撤掉「请求次数」配额（⭐ **必须最后做**）

**Files:** `api/permission.py` · `api/main.py`（`QuotaMiddleware`）· `api/api_v1.py:221` · `api/api_v1_rag.py:25` · `api/test_plan_execute_tools.py:498`

> ⚠️ **为什么必须最后**：见 ①a 里 Task 3 那节的「**顺序陷阱**」——
> **先撤次数、后接 token ⇒ 中间有一段"谁都不拦"的窗口。**
> **到这一步，B8/B10/B11 已经在拦了，撤掉次数才是安全的。**

具体步骤与代码：**见 ①a 里「（原 Task 3 · 已移出）」那一节，照它执行**，⛔ 但**顺序放在这里**。

---

## Task 7 · **B13** · 实跑核一遍成本可见

- [ ] **不写代码先核**：起服务，依次看 `/dashboard` · `/agent/token/budget` · `/agent/cost/overview` · `/agent/trace/{thread_id}`
- [ ] 判据（`R4`）：**界面上能直接看到数字；能回答"今天花了多少、还剩多少"**
- [ ] ⚠️ R4.2 的「还剩多少」**依赖 B10** —— B10 做完它才答得出来。**如果以前答不出而现在答得出，本任务就完成了**
- [ ] 缺什么再补什么；⛔ **别为了"补齐"而新写一套汇总**（`token_tracker` 已有 9 个）
