# DEC-110 · 解 `mcp` 上界到 2.x + 服务端 API 迁移（批④-**A**）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施（2026-10-08）** —— 批④ **A** 半，4 个 Task 全部落地 |
| **触发** | `DEC-104`（业务方 2026-10-08 选「批④：B（MCP client）：**解开 SDK 锁 mcp，用最新版**，开一个长驻 `async with`」）+ **本轮范围裁定**：业务方 2026-10-08 定「**先 A，B 另起一批**」 |
| **类型** | 依赖版本口径 · **服务端 API 迁移** · 可见行为变更（工具描述不变、**接口形状不变**） |
| **落点** | `api/requirements.txt` · `api/mcp_server.py` · `api/agent_graph_advanced.py` · `api/api_v1_agent.py` · `api/tool_health.py` · `api/test_agent_repairs.py` · 🆕 `api/test_mcp_protocol_e2e.py` |
| **施工单** | `fastapi-rag-agent-TODO待办/施工单-20261008-mcp解上界.md` |
| **判据** | 见 §六（逐条可打印） |

---

## 一 · 要裁的是什么

### 1.1 范围：**只做 A**

`DEC-104` 记的批④ 是**两半**：

| | 是什么 | 本 DEC |
|---|---|---|
| **A** | **解 SDK 上界** + 服务端从装饰器迁到 2.x 构造器回调 | ✅ **本文** |
| **B** | **长驻会话**（后台 task 持有的 `async with`），并把它铺到各图 | ⬜ **另起一批** |

🔴 **为什么拆**：`DEC-104` §2.2 自己那条理由 —— 「**把两件事捆在一起 ⇒ 出事时分不清是"清单没收口"还是"换了通道"**」。
A 与 B 也有同一对纠缠：A 是**换 SDK 版本**（可独立验证），B 是**换会话模型**（**改变运行时行为**：进程边界 / 超时 / 失败形态）。

### 1.2 上锁的理由**属实**（🔵 解包实测，⛔ 不是转述 `DEC-104`）

`api/requirements.txt` 原注释写「`mcp` 2.x 的 `Server` 去掉了 `list_tools()` 方法」。核实：

```bash
# 解包 mcp==2.3.0 后
grep -n "def list_tools\|def call_tool" mcp/server/lowlevel/server.py   # ⇒ 0 命中
```

✅ **确实没有**。替代品是**构造器回调**（`Server.__init__` 的 `on_list_tools=` / `on_call_tool=`）。

---

## 二 · 决策

### 2.1 版本钉：`mcp>=2.3.0,<3`

| | `mcp>=2.3.0`（完全不加界） | **`mcp>=2.3.0,<3`（选中）** |
|---|---|---|
| 照谁的 | `DEC-104` 的字面（「**解开上界**」） | **本仓对重依赖的既有惯例**（`langchain>=0.3.13,<0.4` · `langgraph>=1.0,<2`） |
| 好处 | 永远自动吃最新版 | 新装的机器**不会**被 3.x 静默搞坏；升 3.x 是**一次显式动作** |
| 代价 | 哪天 3.x 静默改 API ⇒ **又是这一轮的重演** | 会像这次一样"停在 2.x 一阵子" |

🔴 **业务方 2026-10-08 当场选了 `<3`**（本 Agent 先按惯例写、**停下问**，⛔ 没有自己收窄 —— 本仓有前科：
「**我把业务方的 ④ 自己收窄过，随后照着它推错了"下一步"**」）。
下界 `2.3.0` = **本批实测过的版本**。

### 2.2 服务端：装饰器 → 构造器回调（逐条对照）

| | **1.x（改前）** | **2.x（改后）** |
|---|---|---|
| 注册 | `@server.list_tools()` 装饰器 | `Server(..., on_list_tools=…)` |
| 列表处理器 | `async def list_tools() -> list[Tool]` | `async def list_tools(ctx, params) -> types.ListToolsResult` |
| 调用处理器 | `async def call_tool(name, arguments)` | `async def call_tool(ctx, params: types.CallToolRequestParams)` |
| 返回值 | 裸 `list[Tool]` / 裸 `list[TextContent]` | `ListToolsResult(tools=[…])` / `CallToolResult(content=[…])` |
| 取名字 | 形参 `name` | `params.name` |
| 取参数 | 形参 `arguments` | 🔴 `params.arguments` —— **缺省 `None`，⛔ 不是 `{}`** |

⚠️ **`Server(...)` 的创建点跟着挪了** —— 2.x 的处理器是**构造参数** ⇒ 建 server 时必须已经拿得到那两个函数
（1.x 那行在文件顶部，已挪到两个处理器定义**之后**）。

### 2.3 🔴 **「客户端的 API 没变」≠「客户端不用改」** —— 本批最值钱的一条

施工单初版写的是「客户端侧没变 ⇒ `agent_graph_advanced.py` **一行不用改**」。**实测不成立。**

> **客户端的【函数】没变，但它返回的 `Tool` 对象换了字段名。**

| 玩法 | 1.x | 2.x |
|---|---|---|
| **构造** `Tool(...)` | `inputSchema=` | ✅ **两种都能写**（`populate_by_name=True`） |
| **读属性** `tool.???` | `tool.inputSchema` | 🔴 **只有** `tool.input_schema` ⇒ 写旧的会 `AttributeError: … Did you mean: 'input_schema'?` |
| **拿线上拼法** | `tool.inputSchema` | `model_dump(by_alias=True)["inputSchema"]` |

🔴 **是两条【既有】守卫先红才照出来的**（`test_get_llm_with_mcp_tools_unpacks_list_tools_result` ·
`test_mcp_tools_dynamic_handles_list_tools_result`）—— 它们不是本批新写的，是**批①/批③ 时就在的**。
⇒ **先有一把能红的尺子，才有了这次发现**。

⚠️ **一处特别容易改错的**：`api/api_v1_agent.py` 里那个 dict 的**键** `"inputSchema"` 是**本接口的响应契约**
（⛔ 不动），**值**才来自 mcp 的 `Tool`（改成 `.input_schema`）。**改前左右同名、改后必须不一样**。

### 2.4 🆕 补一条真端到端守卫

本仓**没有任何**"真起 MCP 子进程、真走协议"的用例 —— `api/test_agent_repairs.py` 里那几条
**全 monkeypatch 掉**了 `stdio_client` / `ClientSession` ⇒ 它们验的是**和假对象的契约**。
⇒ **服务端 API 接错了，现有测试一条都不会红** —— 而那正是本批唯一的风险面。

🆕 `api/test_mcp_protocol_e2e.py`：真子进程 × 真协议 × 真调用（实测约 **3s**，不标 `integration`/`needs_db`）。
🔴 **先在 1.x 上跑绿**，再迁移 —— 那是**证明这把尺子量得住东西**。

---

## 三 · 🔵 实测依据（⛔ 不是转述）

| 事实 | 怎么核的 | 结果 |
|---|---|---|
| `Server` 没有 `list_tools()` | 解包 `mcp==2.3.0` 后 `grep` | **0 命中** ✅ |
| 新写法四个构造都对 | 用**真 `mcp_types` 2.3.0** 跑一遍 | 四条全 ✅（含 `arguments` 缺省 `None`） |
| **依赖升级是干净的** | `pip install --dry-run 'mcp>=2'` | **只动 `mcp` / `mcp-types`** ⇒ `DEC-104` §六·7「一次只动一个变量」**能满足** |
| 实际装完还是只动两个 | 装前装后逐个 `importlib.metadata.version` **逐行 diff** | 八个数**逐行相同**，只有 `mcp 1.30.0→2.3.0` · `mcp-types 2.2.0→2.3.0` ✅ |
| 上锁理由在**运行时**也成立 | 装完立刻 `import mcp_server` | 🔴 **当场炸**：`AttributeError: 'Server' object has no attribute 'list_tools'` —— **预言的炸点原样兑现** |
| 客户端**函数**没变 | 解包核 `stdio_client` / `StdioServerParameters` / `ClientSession.list_tools` | 都在 ✅ |
| 客户端**类型字段**变了 | **两条既有守卫先红** | 见 §2.3 ✅ |

---

## 四 · 备选与反悔成本

| 决策点 | 没选的备选 | 为什么 | 反悔成本 |
|---|---|---|---|
| 上界 | 完全不加界 | 见 §2.1 | **低**（改一行 requirements + 重装） |
| 上界 | 锁到 `<2.4`（只吃已测次版本） | 最保守，但**很快要手动跟版**；本仓惯例是大版本界 | 低 |
| 服务端抽象 | 换 2.x 新增的**高层** `MCPServer` | ⛔ 那是**换抽象层**，⛔ 不是迁移。本批目标是「同一个形状升到 2.x」 | 中 |
| 处理器命名 | 改名（如 `_on_list_tools`） | 保留原名 ⇒ diff 最小，且 `tool_health.py` 那两处注释**只需补半句** | 低 |
| 迁移与解上界是否分开提交 | 分两个提交 | ⛔ **不能分** —— 解了上界而没改用法，**导入期就炸**（已实测） | — |

🔴 **反悔路径**：把 `requirements.txt` 改回 `mcp>=1.0.0,<2` + `mcp_server.py` 改回装饰器 +
两处 `.input_schema` 改回 `.inputSchema`。⚠️ **但三处必须同一个提交**（同 §2.2 的理由）。

---

## 五 · 边界（⛔ 别读成「可以顺手」）

1. ⛔ **本批不含 B（长驻会话）** —— 见 §1.1。`DEC-104` §2.1 那道
   「anyio cancel scope 要求进入与退出**在同一个 task**」的坎**还在**，⛔ 没被本批绕过。
2. ⛔ **不换传输层** —— `stdio_client` 照旧（`DEC-104` §2.2 的「② 执行统一」是 B 的事）。
3. ⛔ **不动 `execute_python` / 容器 / `SENSITIVE_TOOLS`** —— 那是批② 与已结清的第 11 条。
4. ⛔ **不提升 `mcp` / `mcp-types` 之外的任何依赖**（`DEC-104` §六·7，§三 逐行 diff 已证）。
5. ⛔ **不改 `DEC-104` 正文的历史记录** —— 只加**带日期的快照标记**（§四 那张现状表是当时的快照）。

---

## 六 · 判据（逐条可打印）

```bash
# ① 版本真的解了 + 只动了两个包
grep -n '^mcp' api/requirements.txt                      # ⇒ mcp>=2.3.0,<3
./venv/bin/python -c "import importlib.metadata as m; print(m.version('mcp'), m.version('mcp-types'))"
# ⇒ 2.3.0 2.3.0

# ② 旧写法一处不剩（注释里的说明不算）
grep -rn "server\.list_tools\|server\.call_tool" api/*.py | grep -v '#'      # ⇒ 空
grep -rn "\.inputSchema" api/*.py | grep -v "^api/test_" | grep -v '#'       # ⇒ 空

# ③ 🔴 端到端真跑（本批唯一的风险面就压在这条上）
venv/bin/python -m pytest api/test_mcp_protocol_e2e.py -q                    # ⇒ 2 passed

# ④ 全量（CI 的等价物，⛔ 不是裸 pytest）
bash scripts/ci-local.sh
# ⇒ 850 passed, 2 skipped, 40 deselected（exit 0）
#    ⚠️ 【改前】= 848（`64902ad`）⇒ **+2** = 🆕 那两条端到端

# ⑤ 六道门（真 hook + 喂 stdin）
echo '{"tool_name":"Bash","tool_input":{"command":"git commit"},"cwd":"'"$(pwd)"'"}' \
  | python3 .claude/hooks/pre-commit-gates.py
```

🔴 **反证（实做过）**：把 `Server("agent-tools", on_list_tools=list_tools, on_call_tool=call_tool)`
里的 `on_list_tools=list_tools,` 拿掉 ⇒ 跑 ③ ⇒ **红**（`ExceptionGroup: unhandled errors in a TaskGroup`
—— 服务端不再响应 `tools/list`）⇒ 还原后 `git diff --stat` **为空**。

⚠️ **这条反证的诚实边界**：它是**在协议请求那一刻炸的**，⛔ **没走到那条 `assert served == registered`**。
⇒ 它抓得住「**根本没接上**」，**抓不住「接上了却返回空清单」** —— 后者只有 `assert` 会管。
**两条都在同一个用例里**，但这次反证只激活了前一条。

---

## 关联

- **批④ 施工单** ⇒ `fastapi-rag-agent-TODO待办/施工单-20261008-mcp解上界.md`
- **路线裁定（A/B 的母体）** ⇒ `DEC-104`（§2.1 anyio cancel-scope · §2.2 两层拆分 · §六 边界）
- **事实依据** ⇒ `docs/reference/mcp-stateless-and-transport.md`（官方原文摘录 + 逐条实测）
- **债：批④-B（长驻会话）** ⇒ ⬜ **未做**，`DEC-104` §2.1 的坎还在
- **同族先例** ⇒ `DEC-051`（一个名字两个来源必然漂移）—— 本批 §2.3 是它的**镜像**：
  **一个类型两个写法**（`inputSchema` / `input_schema`），而**属性读取只认一个**
