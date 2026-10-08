# DEC-104 · 本项目 MCP 路线：**工具统一走 MCP client** —— 解 SDK 锁 + 长驻会话

| 项 | 内容 |
|---|---|
| **状态** | 🔵 **已裁定（2026-10-08）** —— **部分实施**：<br>· ✅ **批④-A（解 SDK 上界 + 服务端 API 迁移）2026-10-08 已落地** ⇒ `DEC-110`<br>· ⬜ **批④-B（长驻会话 / 执行通道统一）未做** —— ⚠️ **§2.1 那道 anyio cancel-scope 的坎还在**，见 §二 |
| **触发** | 业务方原话（2026-10-08）：「**`mcp client tools`：execute_python 从 agent_graph / agent_checkpointer：为什么只有 web_search 这个 tools，这两个不是使用 mcp tools 吗？只有一个 web_search 可能是当时测试只用一个 tools 测试是否行得通，现在改道走 mcp client，你的建议是什么。execute_python 也在 mcp client 中注册，走 docker 容器，agent prompt 应该可以统一改 tools 在 mcp client 中，或者有注册，全局 agent tools 统一走 mcp client，更新框架，现在 mcp 是无状态的模式，具体你搜索 anthropic mcp 相关内容，并做文档记录和更新，代码也需要注释。**」<br>以及同日的批④ 选择：「**批④：B（MCP client）：解开 SDK 锁 mcp，用最新版，开一个长驻 async with。**」 |
| **类型** | 架构路线 · SDK 版本口径 · 会话模型 |
| **落点** | `api/requirements.txt`（:95 的 `mcp>=1.0.0,<2` 上界）· `api/agent_graph_advanced.py`（客户端会话）· `api/mcp_server.py`（服务端启动形态）· `api/agent_graph.py` · `api/agent_checkpointer.py` · `api/agent_graph_advanced_learning.py`（三处工具清单） |
| **配套文档** | ⭐ **`docs/reference/mcp-stateless-and-transport.md`**（官方原文摘录 · 自足 · 逐条附出处） |
| **判据** | 见 §六（逐条可打印） |

---

## 一 · 要裁的是什么

### 1.1 现象：工具清单**分了两家**，且**只有一条路走了 MCP**

🔵 **实测**（`grep`）：

| 模块 | 它的工具从哪来 | 走 MCP 吗 |
|---|---|---|
| `api/agent_graph_advanced.py` | **MCP client**（`stdio_client` + `ClientSession`） | ✅ 走 |
| `api/agent_graph_advanced_learning.py` | MCP（`_MCP_TOOLS`） | ✅ 走 |
| `api/agent_graph.py` | **本地直接 import 工具函数**（`tools = [web_search, calculator, date_today]`） | ⛔ **不走** |
| `api/agent_checkpointer.py` | 同上（本地直接 import） | ⛔ **不走** |

⇒ **同一个工具（如 `web_search`）在本仓有两份实现路径**，而**它们的行为可以不一致**
（缓存、TTL、失败处理各写各的 —— 这正是 **批① 要收口的那件事**）。

### 1.2 业务方的问题：「为什么只有 web_search 一个？」

⚪ **本项目的解释**：`api/agent_graph.py` / `api/agent_checkpointer.py` 这两条链**当初只拿 `web_search` 试通了 MCP**，
`calculator` / `date_today` 是**本地直接调用**。**不是设计，是当时只验了一个。**

⚠️ **注意措辞**：这是 ⚪ **本项目判断**，**⛔ 不是留痕事实** ——
我**没有**找到"当时为什么只测一个"的原始记录。**这条解释供参考，⛔ 别当已核事实引用。**

### 1.3 业务方同时点出的：**MCP 现在是无状态的模式**

⇒ 要求「**搜索 anthropic mcp 相关内容，并做文档记录和更新，代码也需要注释**」。
📄 **产出** ⇒ `docs/reference/mcp-stateless-and-transport.md`（🟢官方原文 / 🔵实测 / ⚪本项目判断 逐条标注）。

---

## 二 · 决策

### 2.1 批④ 选 **B：走 MCP client** —— 解开 SDK 锁、用最新版、开**长驻** `async with`

| 项 | 值 |
|---|---|
| SDK 版本 | **解开上界**（现在 `mcp>=1.0.0,<2`）· **升到最新版** |
| 会话模型 | **开一个长驻的 `async with`**（⛔ 不是现在这种"每次调用起一次子进程"） |
| 为什么现在能解上界 | `mcp` 2.x 去掉 `Server.list_tools()` 是本仓上锁的**唯一**原因（`api/requirements.txt:93-94`）⇒ **升版时必须一起改掉那处用法** |

⚠️ **实施上的已知难点**🔵：`stdio_client` 基于 **anyio**，其 cancel scope 要求
「**进入与退出在同一个 task**」（`api/agent_graph_advanced.py:108` 一带的注释 · 回归用例
`api/test_agent_repairs.py::test_call_mcp_tool_keeps_session_lifecycle_inside_one_task`）。
⇒ **长驻会话必须由一个后台 task 持有**（让它的 `async with` 生命周期落在那个 task 内）⇒
**⛔ 不是把 `async with` 挪到函数外那么简单。**

### 2.2 「统一」要拆成**两层**，⛔ 不是一刀切

| 层 | 做什么 | 现在做吗 |
|---|---|---|
| **① 清单统一** | **一处事实源**：工具名 / 描述 / TTL **只有一份**（落点 = `mcp_server.TOOLS` + `api/tool_cache.py: TTL_BY_TOOL`） | ✅ **批① 正在做** |
| **② 执行统一** | 所有 agent 图**都经由 MCP client 调工具** | ⬜ **批④**，且**按图逐个评估**，⛔ 不一刀切 |

🔴 **为什么拆开**：① 是「**别让同一个事实有两个源**」（本仓 `DEC-051` 的病根）；
② 是「**换执行通道**」——**它会改变运行时行为**（进程边界、超时、失败形态）。
把两件事捆在一起 ⇒ **出事时分不清是"清单没收口"还是"换了通道"**。

### 2.3 顺序：批① → 批② → 批③ → **再评估传输层**

业务方 2026-10-08 认可的理由（原话）：

> 「**批① 的「一处事实源」正是换传输层的前置；而代码执行器的安全问题是真风险，优先级高于架构统一。**」

⇒ 🔴 **批④ 排最后，⛔ 不是因为它不重要** —— 是**因为"清单没收口就换传输层"会把两笔账混在一起**。

---

## 三 · 🔴 最容易搞错的一条：MCP 给的是【进程边界】，⛔ **不是【安全边界】**

> **这一条必须在动手前钉死，否则会把批② 该干的事误以为"批④ 会顺带解决"。**

| | 进程边界（MCP stdio **确实**给） | 安全边界（MCP stdio **不给**） |
|---|---|---|
| 是不是独立进程 | ✅ 是 | — |
| 独立 uid / 文件系统 | ⛔ **否** —— 子进程**继承宿主 uid 与文件系统** | ⛔ 否 |
| 内存 / CPU 限额 | ⛔ 否 | ⛔ 否 |
| 文件系统只读 / 隔离 | ⛔ 否 | ⛔ 否 |

🟢 **协议侧依据**：MCP 的 stdio 传输在官方文档里就定义为
「messages over the standard streams of a **client-launched subprocess**」
（`docs/reference/mcp-stateless-and-transport.md` §三·原文 3）——
**⛔ 官方从没说过它是沙箱。**

🔴 **⇒ 结论**：
- **`execute_python` 的安全问题（「不要暴露在系统中执行，是安全事故」）由【批② 独立容器】解决，⛔ 不是由批④ 解决。**
- 批④ 换传输层 **不会**让 `execute_python` 变安全。

---

## 四 · 现状（🔵 实测 · ⛔ 别抄，用命令核）

> 🔴 **2026-10-08（批④-A）更正：本表前两行【已过时】。**
> · SDK 上界：`mcp>=1.0.0,<2` ⇒ **`mcp>=2.3.0,<3`**
> · 实装版本：`1.30.0` ⇒ **`2.3.0`**
> · 服务端形态：装饰器（`@server.list_tools()`）⇒ **2.x 的构造器回调**（`Server(on_list_tools=…)`）
>   —— ⚠️ **但本表"握手形态"那一行的判据（`create_initialization_options()`）仍然成立**，2.x 没删它。
> · 会话那一行（每次调用起一次）**没变** —— 那是 **批④-B** 的事。
>
> ⚠️ **本表是 2026-10-08 上午的快照，按本仓规矩⛔ 不改写**；**现行值一律跑右边那列命令**。
> 📄 迁移的裁定与实测 ⇒ `DEC-110`。

| 项 | 现状 | 判据 |
|---|---|---|
| SDK 上界 | `mcp>=1.0.0,<2` | `grep -n '^mcp' api/requirements.txt` |
| 实装版本 | **1.30.0** | `./venv/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"` |
| 服务端形态 | **握手形态**（`create_initialization_options()`） | `grep -n 'create_initialization_options' api/mcp_server.py` |
| 客户端 | **只有 `agent_graph_advanced.py`** 一条路 | `grep -rln 'stdio_client' api/*.py` |
| 会话 | **每次调用起一次**（短会话） | `grep -n 'async with stdio_client' api/agent_graph_advanced.py` |

---

## 五 · 备选与反悔成本

| 备选 | 为什么**没选** | 反悔成本 |
|---|---|---|
| **A · 维持现状**（有的图走 MCP、有的本地直调） | 工具清单**两个源** ⇒ 行为必然漂移；业务方明确要「**统一**」 | 低（什么都不做） |
| **B · 统一走 MCP client**（**选中**） | — | **中**：解上界后 `mcp` 2.x 改动面未知；长驻会话要处理 anyio 的 cancel-scope 约束 |
| C · 反过来：**全部退回本地直调**（取消 MCP） | 与业务方「更新框架」「走 MCP」的方向相反 | 中 |
| D · **一刀切**：批① 和批④ 一起做 | 出事**分不清是清单没收敛还是换了通道** | 高（正是本仓反复栽的"两笔账混一起"） |

🔴 **反悔路径**：批④ 若在某个图上跑不通（超时 / 失败形态变化）⇒
**该图**退回本地直调即可（**逐图可退**，⛔ 不是整个批④ 推倒）——
**这就是 §2.2「按图逐个评估、不一刀切」留给自己的退路。**

---

## 六 · 边界（**别读成"可以顺手做"**）

1. ⛔ **本 DEC 只是路线裁定** —— **批④ 的实施细节（命令级）到批④ 时另开施工单**，
   ⛔ **别拿这份当施工单用**。
2. ⛔ **批④ 之前不许动 `mcp` 上界** —— 解上界必须与「改掉 `@server.list_tools()` 用法」**同一提交**，
   否则**导入期就炸**（`AttributeError`，2026-09-15 实测）。
3. ⛔ **不许把批④ 当成批② 的替代** —— 见 §三。
4. ⛔ **不许用 MCP 的 `ToolAnnotations`（`readOnlyHint` 等）当授权依据** ——
   🟢 官方原文：「clients **MUST** consider tool annotations to be **untrusted** unless they come from trusted servers」
   （`docs/reference/mcp-stateless-and-transport.md` §六）。
5. ⚠️ **「无状态」⛔ 不等于「每次起新进程」** —— 协议**没这么规定**；
   长驻会话在协议上是允许的（同文档 §四·误读 ① / ②）。
6. ⛔ **不在本批（批④）内提升 `mcp` 之外任何依赖的版本** —— 一次只动一个变量。

---

## 关联

- ⭐ **MCP 官方原文摘录（本 DEC 的事实依据）** ⇒ `docs/reference/mcp-stateless-and-transport.md`
- **工具清单收口（批①）** ⇒ fastapi-rag-agent-TODO待办/施工单-20261007-工具缓存收口.md
  ⚠️ **上述文件名故意【不加反引号】** —— 该施工单目前**只在 `docs/ledger-reconcile` 分支上**
  （`c5442e0`），**本分支取不到** ⇒ 加反引号会被断链门判红。
  🔴 **两个分支合进主干后它会解析得到** —— 到那时可以给它加回反引号。
- **`execute_python` 进容器（批②）** —— ⚠️ 尚未开施工单
- **同族先例：一个事实两个源会漂移** ⇒ `DEC-051`（统计口径四处不一致）
- **`DEC-102` 改线只做 demo** —— ⚠️ 本 DEC **不改变** demo 路线；MCP 改动**面向代码质量**，
  ⛔ 与 demo 交付面（`demo/`）无直接关系
