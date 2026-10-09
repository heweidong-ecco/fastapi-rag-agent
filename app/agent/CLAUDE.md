# `app/agent/` —— Agent 编排

> 📇 **本层 = 索引表 + 主要内容**：agent 进到这一层，先读这份；不够再往 `specs/` 转。

## 📇 本目录索引

**职责**：编排 · 计划 · 审批 · 检查点 · 长期记忆

| 模块 | 它的 spec |
|---|---|
| `agent_checkpointer.py` | `specs/agent_checkpointer.md` |
| `agent_graph.py` | `specs/agent_graph.md` |
| `agent_graph_advanced.py` | `specs/agent_graph_advanced.md` |
| `agent_graph_advanced_learning.py` | `specs/agent_graph_advanced_learning.md` |
| `approval_audit.py` | `specs/approval_audit.md` |
| `memory_store.py` | `specs/memory_store.md` |
| `pending_approvals.py` | `specs/pending_approvals.md` |
| `plan_constraints.py` | ⛔ **缺** |
| `plan_execute.py` | `specs/plan_execute.md` |
| **`specs/`** | 本组模块的规格 —— **与模块同名**（见 `specs/CLAUDE.md`） |

## 🔴 本层特有的规矩

- 🔴 **改完一个模块 ⇒ 更新 `specs/<同名>.md`**（`pre-commit-gates.py` 对**新增模块**硬拦）
- 🔴 **导入写绝对形式、根是 `app/`**：`from core.config import X`（⛔ 不是 `from app.core...`）
- ⚠️ 本组的 `.py` **已不在 `app/` 根** ⇒ 凡 `dirname(__file__)` 算路径的**都已跟着搬**，
  ⛔ **别再把它和它的数据文件拆开**

## 📍 往上读

- `../CLAUDE.md`（`app/`）· 仓库根 `CLAUDE.md`（全局约定）
