# `api/code_executor.py` + `api/code_executor_impl.py`

| 项 | 内容 |
|---|---|
| **状态** | ✅ **可用 · 已进容器（2026-10-08 · 批②）** —— 改前是「宿主同权限的子进程 + 白名单」 |
| **对外提供** | `code_executor.execute_python`（**`@tool`，给 LLM 的那一层**）<br>内核（`_impl`，**纯 stdlib**）：`execute_python_impl` · `run_in_sandbox_subprocess` · `create_safe_globals` · `ALLOWED_BUILTINS` · `ALLOWED_MODULES` · `MAX_EXEC_TIME` · `MAX_OUTPUT_LENGTH` |
| **谁在用** | `mcp_server.TOOLS`（⇒ 各图按派生表拿到它）· `api_v1_agent.py` 的 `/agent/execute_code` 直接 `.invoke()`<br>⚠️ **`agent_graph` / `agent_checkpointer` 显式排除它**（见下方 🟡） |
| **测试** | `api/test_impl_modules.py` · `api/test_code_executor_remote.py`（**4**）· `api/test_plan_execute_tools.py` · `api/test_tool_registry_single_source.py`（demo 那 2 条） |

**两个文件的分工**（⛔ 别合并）：

| 文件 | 是什么 | 依赖 |
|---|---|---|
| `code_executor.py`（150 行） | **`@tool` 外壳** —— 给 LLM 读的 docstring + 缓存包装 | langchain · `tool_cache` |
| `code_executor_impl.py`（292 行） | **纯 stdlib 内核** —— 白名单 · 子进程 · 超时硬杀 · 远端路径 | ⚠️ **只 import 标准库** |

⚠️ **依赖方向单向**：`code_executor.py` 引用 `_impl`；⛔ **`_impl` 绝不反向引用**。
📌 `_impl` 的这条不变量**有实际用途**：它让沙箱逻辑能**脱离 langchain 单测**。

## ✅ 做了什么

- **AST 白名单求值环境**（`create_safe_globals`）：`ALLOWED_BUILTINS` + `ALLOWED_MODULES`
  ⚠️ 例外类（`ValueError` 等）与 `__build_class__` 是 **2026-09-20/21 业务方裁「放开」**的
  —— 依据是「它们**不提供逃逸能力**」，⛔ 不是"为了方便"
- **子进程 + 5 秒硬杀**（`MAX_EXEC_TIME`）：⚠️ **线程超时杀不掉 Python 线程** ⇒ 死循环会把进程拖垮
- **输出截断**（`MAX_OUTPUT_LENGTH = 2000`）
- **意图检测**：把「帮我写一段代码」这类**需求描述**挡在**执行之前**
- 🔴 **2026-10-08（批②）**：执行**进容器** —— `EXECUTOR_URL` 有值走远端，没值回落本地子进程

## 🟡 做到哪 / 缺什么

- 🟡 **`execute_python` 暂不进 `agent_graph` / `agent_checkpointer`** —— 那两张图里它**无审批**（不在 `SENSITIVE_TOOLS`）。
  🔴 **本条的"有效期"到了**：批① 立的理由有**两条** —— ①无隔离 ②**无审批**。
  **批② 解决了 ①，⛔ 没解决 ②。** ⇒ 业务方 2026-10-08 对此答「**待定**」，**保持现状**。
  📌 判据：`grep -n '_EXCLUDED_TOOLS' api/agent_graph.py api/agent_checkpointer.py`
- ⬜ **`calculator` 的间接提示注入面**（与执行器同族的"LLM 生成输入"问题）—— 记在 `docs/待办总表.md` §二 8
- ⚠️ **容器方案下 `EXECUTOR_TIMEOUT = MAX_EXEC_TIME + 10`** —— ⛔ 别设成与 `MAX_EXEC_TIME` 相同
  （那会把"执行器还没跑完"误判成"远端超时"，**正常的慢代码变成报错**）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「它是"安全沙箱"，所以安全」 | 🔴 **容器之前它【不是】** —— 白名单是**进程内**的，一旦被绕过的就是**宿主**。**容器（批②）才是那道 OS 级隔离**，白名单是**第二层**，⛔ 不是替代品 |
| 「白名单里没有 `os` / `open` ⇒ 读不了文件」 | ⚠️ 对**沙箱内**成立。但**子进程本身**与宿主**同权限、同文件系统** ⇒ 逃逸 = 拿到宿主。这就是批② 要解决的 |
| 「`_run_remote` 失败会回落本地」 | 🔴 **⛔ 不会** —— 回落**只由配置**（`EXECUTOR_URL` 空不空）决定。若"失败就回落"，**运维停了执行器 ⇒ 代码又回到宿主跑，而没人会发现**。实测：停掉执行器 ⇒ 返回错误、**没有返回 42** |
| 「`run_in_sandbox_subprocess` 只是个内部工具」 | ⚠️ **它是执行沙箱的【唯一】落点** —— **本地路径**与**执行器服务**都调它。⛔ 别在别处再抄一份超时 / 报错文案（批① 刚把"抄 5 份"收口掉 · `DEC-107`） |
| 「`MAX_EXEC_TIME = 5` ⇒ 每次最多跑 5 秒」 | ⚠️ 是**墙钟 5 秒**，⛔ 不是"5 秒的计算量"。容器限 `cpus: 0.5` ⇒ **并发一上来，同一段码会慢好几倍** ⇒ 可能撞 5 秒（`DEC-108` §3.6 有实测数字） |
| 「`code_executor.py` 最下方那段 Docker 代码是活的」 | ⛔ **那是方案记录**（业务方要求保留），**未生效**。⛔ 别照它去改实现 —— 里面那个 `docker.from_env()` 正是**批② 要避开的**写法（要挂 `docker.sock`） |
| 「`demo` 上也能用 `execute_python`」 | 🔴 **⛔ 不能** —— `DEMO_MODE` 下**不注册它**。创空间**单容器** ⇒ 没有执行器 ⇒ 会**回落本地沙箱** = 宿主同权限（`DEC-108` §3.7） |

## 关联

- **决策** ⇒ `DEC-108`（进容器 · 全量）· `DEC-049` / `DEC-066`（`eval` → `safe_math`）· `DEC-107`（工具清单收口）
- **容器那侧** ⇒ `docs/specs/` 下的 `executor_server` 那份 · `DEC-108` §3.3（硬化逐条）
- **邻居** ⇒ `docs/specs/safe_math.md`（`calculator` 的安全实现，同族的"LLM 输入"问题）
- ⚠️ **`EXECUTOR_URL` 的注入处** = `docker-compose.yml` 的 `api` 服务 —— 改它要动那里，⛔ 不是改代码默认值
