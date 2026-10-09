# `app/tools/` —— 工具与执行器

> 📇 **本层 = 索引表 + 主要内容**：agent 进到这一层，先读这份；不够再往 `specs/` 转。

## 📇 本目录索引

**职责**：工具 · MCP · 执行器 · 缓存 · 健康

| 模块 | 它的 spec |
|---|---|
| `browser_tools.py` | `specs/browser_tools.md` |
| `code_executor.py` | `specs/code_executor.md` |
| `code_executor_impl.py` | `specs/code_executor_impl.md` |
| `executor_server.py` | `specs/executor_server.md` |
| `mcp_server.py` | `specs/mcp_server.md` |
| `mcp_tool_factory.py` | `specs/mcp_tool_factory.md` |
| `safe_math.py` | `specs/safe_math.md` |
| `search_tools.py` | `specs/search_tools.md` |
| `simple_tools.py` | `specs/simple_tools.md` |
| `simple_tools_impl.py` | `specs/simple_tools_impl.md` |
| `tool_cache.py` | `specs/tool_cache.md` |
| `tool_health.py` | `specs/tool_health.md` |
| `tool_visualizer.py` | `specs/tool_visualizer.md` |
| **`specs/`** | 本组模块的规格 —— **与模块同名**（见 `specs/CLAUDE.md`） |

## 🔴 本层特有的规矩

- 🔴 **改完一个模块 ⇒ 更新 `specs/<同名>.md`**（`pre-commit-gates.py` 对**新增模块**硬拦）
- 🔴 **导入写绝对形式、根是 `app/`**：`from core.config import X`（⛔ 不是 `from app.core...`）
- ⚠️ 本组的 `.py` **已不在 `app/` 根** ⇒ 凡 `dirname(__file__)` 算路径的**都已跟着搬**，
  ⛔ **别再把它和它的数据文件拆开**

## 📍 往上读

- `../CLAUDE.md`（`app/`）· 仓库根 `CLAUDE.md`（全局约定）
