# `.claude/` —— 本仓的**门**与 agent 配置

> 📇 **本层 = 本仓挂了哪些自动门、在哪、拦什么。** 详细说明见 `README.md`。

## 📇 本目录索引
| 条目 | 是什么 |
|---|---|
| `settings.json` | 项目级配置（**hooks 注册在这里**） |
| `README.md` | ⭐ **门一览**（6 道提交前门 + 提醒型 hook） |
| `hooks/` | 5 个 hook 脚本（见 `hooks/CLAUDE.md`） |
| `agents/` | subagent 规范与归档（见 `agents/CLAUDE.md`） |
| `commands/` | 项目级 slash command（`/specs` · `/handoff`） |

## 🔴 本层特有的规矩
- 🔴 **「门挂在别处，就等于没有门」** —— 新加一道门，**必须登记进 `README.md`**
- 🔴 **门必须能测出自己会红** —— 没有自测的门 = 装饰（本仓已记多次）
- ⚠️ **`worktrees/` 在 `.gitignore`** —— `git worktree` 造的是**整仓副本**，
  各种脚本要**按路径前缀剪枝**，⛔ 别用目录名匹配

## 📍 往上读
- 仓库根 `CLAUDE.md`
