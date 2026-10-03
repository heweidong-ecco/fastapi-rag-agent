# 决策记录：DEC-020 · LLM 工具表改为从 MCP 注册表派生（🔴C 的根因修法）

- 日期：2026-09-20
- 状态：**已采纳并执行**
- 关联：`docs/待办登记-2026-09-20-全仓审计与方向更正.md` §一·C（🔴C）· §四·2（本决策即它的裁决）· **§十三**（「先核」结论）

## 决策事项

🔴C 的**根因修法**怎么实现？

**🔴C 是什么**：`mcp_server.TOOLS`（**6** 个工具）与 `agent_graph_advanced_learning.tools`（**7** 个，多 `fetch_webpage_html`）**各写各的** ⇒ LLM 看得见 `fetch_webpage_html`，而 `mcp_server.TOOL_HANDLERS` 是**从 `TOOLS` 生成的** ⇒ 取不到 handler ⇒ 走到那一步只回「未找到工具: fetch_webpage_html」，**不报错、不 500**。

**业务方裁决**：**乙**（让 LLM 工具表**从 MCP `TOOLS` 派生**，单一事实源）—— 而非"把它加进 MCP"或"手工摘掉"。

## 背景与约束

**「先核」推翻了原来的两个选项**（详见 §十三）：

| 原选项 | 为什么被推翻 |
|---|---|
| ① 把 `fetch_webpage_html` **加进** MCP `TOOLS` | 🔴 **实测它是死的**：`BrowserType.launch: Executable doesn't exist`。它**同样依赖 Playwright/Chromium**（`browser_tools.py:3` 模块级 import + `p.chromium.launch()`），而**本仓任何部署方式都不装浏览器**（`api/Dockerfile` / `docker-compose.yml` 都没有 `playwright install`）⇒ 加进去也**永远 unhealthy**（工具健康 4/6 → **4/7**），只是把静默失败换个形式 |
| ② 从 LLM 工具表**手工摘掉** | 只修**这一次**。根因是「**两份手工维护的清单**」—— 不修根，**下次加工具还会漂** |

**约束**：
- 仓里**已有**这个模式的样板：`api/agent_graph_advanced.py:275-282`
  ```python
  tools_result = await get_mcp_tools()
  langchain_tools = [{"name": ..., ...} for mcp_tool in tools_result.tools]
  return llm.bind_tools(langchain_tools)
  ```
  ⇒ **优先抄现成的**，而不是发明第三种写法。
- ⚠️ **工具 schema 是对外行为** —— 本仓 `ROLEMAP`/PR 纪律把「Prompt / 工具 / 记忆」列为必须显式声明的三类。
- 本文件的 `tools` 是**模块级**（同步构造）。

## 备选方案

| 方案 | 一句话 |
|---|---|
| **甲 · 静态派生**（采纳） | `from mcp_server import TOOLS`；`tools = [t["func"] for t in TOOLS]` |
| 乙 · 运行时查 MCP | 照 `agent_graph_advanced.py` 的样板：`await get_mcp_tools()` 再建表 |
| 丙 · 只手工对齐 | 从 LLM 表摘掉 `fetch_webpage_html`（= 上文"原选项②"） |

## 评估标准

1. **单一事实源强度** —— 以后加工具会不会再漂？
2. **同步 / 异步** —— 能否在模块级构造（不引入 await）
3. **导入副作用** —— `import mcp_server` 会不会起服务、打印、连网？
4. **改动面** —— 越小越好
5. **可测性** —— 能否用一条廉价用例守住

## 方案对比

| 标准 | 甲 静态派生 | 乙 运行时查 | 丙 手工对齐 |
|---|---|---|---|
| **1 单一事实源** | ✅ **最强** —— 直接读权威表 | ✅ 强（读的是跑起来的 server） | ❌ **不修根，下次还会漂** |
| **2 同步** | ✅ **同步可用**（模块级直接建） | ❌ **必须 async** ⇒ 要么改造成惰性、要么把 `tools` 从模块级挪走（**改动面大**） | ✅ 同步 |
| **3 导入副作用** | ✅ **已实测无副作用** —— `mcp_server` 模块级只有导入 + 字典构造；`print` 与 `asyncio.run` **都在 `__main__` 守卫里** | ✅ 无 |
| **4 改动面** | ✅ **最小**（一个文件、十几行） | ⚠️ 大（要动模块级初始化时机） | ✅ 最小 |
| **5 可测性** | ✅ 一条用例即可守住（两表相等） | ✅ 同 | ✅ 同 |

## 最终决策 + 理由

**采纳「甲 · 静态派生」。**

1. **它是唯一同时满足 1 和 2 的方案** —— 乙的单一事实源强度也够，但**必须 async**，而本文件的 `tools` 是模块级的；改成运行时查要连带重构初始化时机，**改动面与风险都不划算**。
2. **导入副作用已实测排除**（标准 3）—— 这是甲能成立的前提，**不是假设**。
3. **丙 被业务方排除**（它不修根因）。

**✅ 已核实：实现逐字等价，行为不变。**
本文件自带的 `calculator` / `date_today` 与 `simple_tools` 那两份，**实现代码逐字相同**
（都是 `str(eval(expression))` + 同样的 `except`；`date_today` 的拼接与星期表也相同）。
⇒ 派生**不改变工具的行为**，只改变**它们是哪个对象**。

⚠️ **但必须显式声明：这是一次【工具 schema 变更】。**
LLM 现在看到的 `calculator` / `date_today` 描述来自 `simple_tools`，**docstring 更详细**：
- `calculator`：多出「**输入的必须是纯数学表达式**」
- `date_today`：多出「**忽略查询参数**」

⇒ 影响 LLM 的工具选择倾向 ⇒ **按本仓 PR 纪律，已在 PR 里显式声明**。

## 影响与后续行动

| 项 | 状态 |
|---|---|
| `api/agent_graph_advanced_learning.py`：`tools` 改为派生 | ✅ 完成 |
| 新增回归用例 `test_llm_tool_table_is_sourced_from_mcp_registry` | ✅ 完成（**红→绿已验证**） |
| 全套离线层 | ✅ **69 passed / 1 skipped / 11 deselected**（68 + 新增 1，**零回归**） |
| `import main`：`ROUTES=13` / `OPENAPI_PATHS=59` | ✅ **与改动前实测一致** |
| ⚠️ **本文件仍自带 `calculator` / `date_today`** —— 被**子图节点**直接 `.invoke()`（`:145` / `:160`） | ⬜ **未动**（超出本决策范围，属"重复定义"清理项） |

**⬜ 登记为后续**（不属本决策）：
- **同类隐患**：`api/agent_graph.py:44` 与 `api/agent_checkpointer.py:43` **各自还有一份手工工具表**
  （`[search_tool, calculator, date_today]`，3 个 —— ⚠️ **这是当时的名字与行号**；
  `DEC-051`（2026-10-03）后搜索工具换成 `web_search`，两份手工表**仍然各自一份**）。⚠️ 它们是**活路径**（被 `api_v1*.py` 导入），
  但**没纳入本次修复** —— 是否同源化涉及"代际裁决"（M5 范围，`Agent 不代判`）。
- **重复定义清理**：本文件的 `calculator` / `date_today` 与 `simple_tools` 的同名重复。

## 反悔成本

**低。**
- 回退：把 `tools = [t["func"] for t in _MCP_TOOLS]` 换回原来的手工列表即可（**原文在 git 历史里**）。
- 换方案：若将来要改走"乙 · 运行时查 MCP"，只需把模块级 `tools` 改成惰性取值 —— **回归用例不用改**（它断言的是"两表相等"，与怎么实现无关）。
- ⚠️ **唯一需要留意**：回退后会**恢复** 🔴C 的静默失败 —— 但那正是本决策要消除的。
