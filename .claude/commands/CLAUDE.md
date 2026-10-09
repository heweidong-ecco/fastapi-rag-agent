# `.claude/commands/` —— 项目级 slash command

## 📇 本目录索引
| 文件 | 那是什么命令 |
|---|---|
| `specs.md` | `/specs` —— **模块 spec 对账**（看有什么/缺什么/还缺什么模块） |
| `handoff.md` | `/handoff` —— **收尾交接**（把这次会话记到该记的地方） |

## 🔴 规矩
- ⚠️ **command 是给【人】用的入口** ⇒ ⛔ 别把只有 CI 用的东西塞进来
- ⚠️ **command 里引用的脚本**（如 `scripts/spec_status.sh`）**改了要同步改这里**

## 📍 往上读
- `../CLAUDE.md`
