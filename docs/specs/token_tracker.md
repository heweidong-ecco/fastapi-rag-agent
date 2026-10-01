# `api/token_tracker.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，但它是【三套额度口径】的其中一套** —— 见下 ⚠️<br>🟢 **①a 已落地（2026-10-01）**：额度常量已收口到 `api/token_config.py`（本文件**只剩同名别名**）· 本文件下方 **实施计划 ①a** 已执行完<br>⬜ **①b 未开工**（B8 会话级 / B10 全局日级 / B11 熔断 / 决策一落地） |
| **对外提供** | `record_usage()` · `record_cost()` · `check_multilevel_budget()` · `check_token_budget_detail()` · `get_token_budget_info()` · 9 个汇总函数 |
| **谁在用** | `permission`（取角色）· `agent_graph_advanced.py:239`（唯一调多级预算的地方）· `cost_dashboard.py` · 各 `api_v1_*.py` |
| **规模** | 744 行 |

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
- 🔴 **没有「会话级」上限**（`_thread_summary` 内存里按 thread 汇总了，但**没有上限判定**）
- 🔴 **没有「全局日级」**（所有方法第一参都是 `user_name`，**无跨用户记账键**）
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
> B7 的接线（把 token_config 接到 17 个构造点）
>   → B8  会话级上限
>   → B10 全局日级总额        ← 到这一步，token 那套【才真正能拦住东西】
>   → B11 熔断（按 key 断路器 + 要素④ 恢复实测 Redis TTL）+ L2 顺带
>   → 决策一落地（撤次数配额）  ← ⭐【最后】
>   → B13 实跑核一遍可见性
> ```

---

# 🔵 实施计划 ①b · **限额与熔断**（2026-09-30 立 · 待执行 ← ⭐ **下一步**）

> **来源**：`后端补齐清单-待裁-20260929.md` 的 **B8 · B10 · B11 · B13 · 决策一（实现）**；
> 以及 `LLM模型路由与额度策略-待裁-20260930.md` 的 **L2**（十几个 model 顺带）。
> **前置**：**①a 必须先落地**（B7 的 `token_config.py` 要先建出来，否则没有常量可取）。
> **本计划【会改行为】** —— 这是它与 ①a 最大的区别。

**目标**：让 token 那套配额**真的能拦住东西** —— 会话级、全局日级、触顶熔断；
然后把旧的「请求次数」配额**最后**降级掉。

**架构**：**新增一层「查询 + 判定」**，全部**查库**（`token_usage_logs`），⛔ **不复用 `_thread_summary`**（理由见 Task 2）。
熔断做成**按 key 的通用断路器**（Redis 标记 + TTL 到次日）—— 这一套同时覆盖
**全局额度触顶**（动作=拒绝）与 **L2 的「某个模型免费额度耗尽」**（动作=换模型）。

---

## Task 0 · **前置决策：`L3` / `L4` / `L5`**（⛔ 不裁就别开工）

> 这三条在 `LLM模型路由与额度策略-待裁-20260930.md` §七 标着「**等 `B11` 开工时再答**」。
> **现在就是那个时候。** 它们是**业务判断**，我不替你定。

| # | 问题 | 备选 | 影响哪个 Task |
|---|---|---|---|
| **L3** | 熔断 key 的 **TTL 设多久** | 到次日 0 点（**我推荐**，与"预算按天"天然对齐）/ 固定 N 小时 / 永久（人工解封） | Task 4 |
| **L4** | **降级要不要对用户可见** | 响应里带标记（**我推荐**）/ 静默 / 拒绝服务 | Task 5（L2 换模型时） |
| **L5** | **降级链按什么排序** | 人工指定顺序（**我推荐**，十几 model 能力差异大，自动轮转不可控）/ 按剩余额度 / 按角色内轮转 | Task 5 |

> ⚠️ **注意 L4 / L5 的对象不是"额度触顶"** —— 触顶已裁「**直接拒绝、不降级**」（`B11` 要素②）。
> 它们的对象是 **`L2`：某个模型的免费额度耗尽 ⇒ 换下一个模型**。

- [ ] **Step 1**：把这三条的裁定**写进 `docs/待办总表.md` §一·附**的 L 表，然后才开始 Task 1。

---

## Task 1 · **B7 接线** · 让 17 个构造点用上 `token_config.MAX_TOKENS_*`

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

- [ ] **Step 2: 跑，确认失败**

```bash
python -m pytest api/test_max_tokens_wiring.py -q
```
预期：FAIL，并**列出**那 17 处（**这条失败信息本身就是待办清单**）。

- [ ] **Step 3: 逐处接上**

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
| `api_v1_rag.py:563`（流式答案）· `:726`（WS agent）· `rag_pipeline.py:48`（`answer_llm`） | **`MAX_TOKENS_ANSWER`** |
| `agent_graph.py:20` · `agent_checkpointer.py:20` · `agent_graph_advanced.py:39` · `agent_graph_advanced_learning.py:20/85/86/87/221` · `plan_execute.py:92/249/458` | **`MAX_TOKENS_AGENT`** |

- [ ] **Step 4: 跑测试，确认通过**

```bash
python -m pytest api/test_max_tokens_wiring.py -q                       # → passed
python -m pytest api/ -m "not integration and not needs_db" -q           # → 全绿
```

- [ ] **Step 5: 提交**

```bash
git add api/*.py api/test_max_tokens_wiring.py
git commit -m "feat(额度): B7 接线 —— 17 个 ChatOpenAI 构造点带上单次上限（2000/1024）"
```

---

## Task 2 · **B8** · 会话级 token 上限

**Files:**
- Modify: `api/token_tracker.py`（加两个函数）
- Test: `api/test_session_budget.py`（新建，标 `needs_db`）

**Interfaces:**
- Produces: `get_thread_token_usage(thread_id: str) -> float`
- Produces: `check_session_token_budget(thread_id: str, estimated_tokens: int = 0) -> tuple[bool, str]`

> ### 🔴 一个**必须避开**的陷阱（设计理由）
>
> `record_usage` 里已经在内存里按 thread 累加了（`_thread_summary`）。
> **⛔ 但绝不能拿它当上限的数据源** —— 它是**进程内存**，
> **重启即清零** ⇒ 想绕开上限，**重启一下就行**。
>
> ⇒ **权威数据源只能是 `token_usage_logs` 表**（`get_daily_token_usage` 就是这么做的，见 `:191`）。
> ⚠️ 这也意味着**每次检查要查一次库** —— 这正是 Task 4 的熔断器要解决的（触顶后别再查）。

- [ ] **Step 1: 写失败测试**

```python
# api/test_session_budget.py
"""会话级 token 上限（B8）。

⚠️ 标 `needs_db` —— 它必须真读 `token_usage_logs`。
   ⛔ 不许改成"喂内存汇总"来免掉数据库：那样测的就不是权威数据源了，
      而"重启绕开上限"这个 bug 恰恰会因此测不出来。
"""
import pytest

pytestmark = pytest.mark.needs_db


def test_session_usage_is_read_from_db_not_memory(monkeypatch):
    """🔴 核心判据：**把内存汇总塞满，也不影响判定结果**。

    内存里伪造一堆用量、DB 里什么都不写 ⇒ 判定必须说"没超"。
    ⛔ 若哪天有人把数据源改回 `_thread_summary`，本条立刻红。
    """
    import token_tracker
    with token_tracker._lock:
        token_tracker._thread_summary["t-mem-only"]["total_tokens"] = 10 ** 9
    assert token_tracker.get_thread_token_usage("t-mem-only") == 0


def test_session_budget_rejects_over_limit():
    """真写库、真超限 ⇒ 必须拒。"""
    import token_tracker
    from token_config import SESSION_TOKEN_LIMIT
    token_tracker.record_usage(
        model="qwen-turbo", prompt_tokens=SESSION_TOKEN_LIMIT, completion_tokens=0,
        purpose="test", user_name="admin", thread_id="t-over",
    )
    ok, why = token_tracker.check_session_token_budget("t-over")
    assert ok is False and "会话" in why
```

> ⚠️ `test_session_usage_is_read_from_db_not_memory` **不需要 DB**，但同文件里有一条需要 ⇒
> 整个文件标 `needs_db` 会被 CI 排除 ⇒ **那条也就不在 CI 跑了**。
> ✅ **做法**：把它拆到两个文件 —— 内存隔离那条进**不带 marker** 的文件（CI 跑），
> 真写库那条留在 `needs_db` 文件。**⛔ 别为了省事让核心判据掉出 CI。**

- [ ] **Step 2: 跑，确认失败**

```bash
python -m pytest api/test_session_budget.py -q          # → AttributeError: get_thread_token_usage
```

- [ ] **Step 3: 实现（`api/token_tracker.py`）**

```python
def get_thread_token_usage(thread_id: str) -> float:
    """本会话【今日】累计 token —— **查库**，⛔ 不读内存。

    ⚠️ 为什么不复用 `_thread_summary`：那是**进程内存**（`record_usage` 里累加），
       **重启即清零** ⇒ 拿它当上限等于"重启就能绕开"。权威数据源是 `token_usage_logs`。
    """
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage_logs
                       WHERE thread_id = %s AND created_at >= CURRENT_DATE""",
                    (thread_id,),
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Token] 查询会话用量失败: {e}")
        return 0.0          # ⚠️ 失败时**放行**（0 = 没超）—— 见下方"失败开还是关"
```

> ### ⚠️ 一个要**明确写下来**的取舍：查库失败时，放行还是拒绝？
>
> 这里选了 **放行（fail-open）** —— 与本文件既有的 `get_daily_token_usage` 一致。
> **理由**：配额是**成本控制**，不是**安全边界**；DB 抖动时把服务全停掉，
> 代价比"多花点 token"大。
> ⛔ **但它必须被写下来** —— 否则下一个人看到"失败返回 0"会以为是 bug。
> 📌 **与 `api/deps.py` 的鉴权不同**：那里是 **fail-closed**（`verify_api_key` 失败即拒）——
> **因为那是安全边界。** 两者**故意不同**，别"统一"掉。

- [ ] **Step 4: 加判定函数**

```python
def check_session_token_budget(thread_id: str,
                               estimated_tokens: int = 0) -> tuple[bool, str]:
    """会话级上限判定。返回 (是否放行, 原因)。**不写拦截记录**（由调用方决定带什么上下文）。"""
    from token_config import SESSION_TOKEN_LIMIT
    used = get_thread_token_usage(thread_id)
    remaining = SESSION_TOKEN_LIMIT - used
    if remaining <= 0:
        return False, (f"本会话预算已用完（已使用 {used:.0f} tokens，"
                       f"会话上限 {SESSION_TOKEN_LIMIT:.0f} tokens）")
    if estimated_tokens > 0 and estimated_tokens > remaining:
        return False, (f"预估消耗 {estimated_tokens:.0f} tokens 超过本会话剩余 "
                       f"{remaining:.0f} tokens")
    return True, f"会话预算充足（剩余 {remaining:.0f} tokens）"
```

- [ ] **Step 5: 接线**（两处主链）

在**答案生成 / Agent 对话**入口调用它（落点参照 `check_budget` 现有的用法：
`api_v1_agent.py:423-433` 的 `AppException(ErrorCode.QUOTA_EXCEEDED)`）。
**触顶动作已裁 = 直接拒绝**（`B11` 要素②）：

```python
ok, why = check_session_token_budget(thread_id)
if not ok:
    raise AppException(ErrorCode.QUOTA_EXCEEDED, why)
```

- [ ] **Step 6: 跑 + 提交**

```bash
python -m pytest api/ -m "not integration and not needs_db" -q
python -m pytest api/test_session_budget.py -q -m needs_db          # 本机有库时
git add api/token_tracker.py api/test_session_budget.py api/test_session_budget_offline.py
git commit -m "feat(额度): B8 会话级 token 上限 —— 数据源是表，不是内存（重启绕不开）"
```

---

## Task 3 · **B10** · 全局日级 token 总额

**Files:**
- Modify: `api/token_tracker.py`
- Test: `api/test_global_daily_budget_offline.py`（无 marker，进 CI）

**Interfaces:**
- Produces: `get_global_daily_token_usage() -> float`
- Produces: `check_global_daily_budget(estimated_tokens: int = 0) -> tuple[bool, str]`

- [ ] **Step 1: 写失败测试（离线可跑的那半）**

```python
def test_global_usage_query_has_no_user_filter():
    """🔴 核心判据：SQL 里**不许**有 `user_name =`。

    ⚠️ 为什么要测这个而不是测数值：`admin` 的日上限现在也是有限值，
       但**全局额度是另一个东西** —— 漏掉 `user_name` 过滤才叫"全局"。
       一旦有人把 `get_daily_token_usage` 的 SQL 复制过来忘了删 `WHERE user_name`，
       本仓库就**永远不会有全局额度**，而且**看起来一切正常**。
    """
    import inspect, token_tracker
    src = inspect.getsource(token_tracker.get_global_daily_token_usage)
    assert "user_name" not in src.split('"""')[-1], (
        "全局日级的 SQL 里出现了 user_name —— 那它就退化成"单用户"了"
    )
```

- [ ] **Step 2: 跑，确认失败**（`AttributeError`）

- [ ] **Step 3: 实现**

```python
def get_global_daily_token_usage() -> float:
    """今日【所有用户合计】的 token —— **不带 user_name 过滤**。

    ⚠️ **必须包含 admin**：`admin` 的**个人**日上限已是有限值（`DEC-040`），
       但"全局额度"是**另一个东西** —— per-user 检查永远看不到"大家加起来超了"。
    """
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage_logs
                       WHERE created_at >= CURRENT_DATE"""
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Token] 查询全局当日用量失败: {e}")
        return 0.0          # 同样 fail-open，理由见 Task 2 那条取舍
```

- [ ] **Step 4: 加判定函数 + 跑 + 提交**

```python
def check_global_daily_budget(estimated_tokens: int = 0) -> tuple[bool, str]:
    from token_config import GLOBAL_DAILY_TOKEN_LIMIT
    used = get_global_daily_token_usage()
    remaining = GLOBAL_DAILY_TOKEN_LIMIT - used
    if remaining <= 0:
        return False, (f"今日全站额度已用完（已使用 {used:.0f} / "
                       f"上限 {GLOBAL_DAILY_TOKEN_LIMIT:.0f} tokens），请明日再试")
    return True, f"全站预算充足（剩余 {remaining:.0f} tokens）"
```

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
