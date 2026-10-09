# `.claude/agents/` —— subagent 规范与归档

## 📇 本目录索引
| 条目 | 是什么 |
|---|---|
| ⭐ **`subagent-lifecycle.md`** | **subagent 生命周期与授权规范**（英文）—— 现行权威 |
| `tmp/` | **退役定义归档**（见 `tmp/CLAUDE.md`） |

## 🔴 本层特有的规矩（规范摘要，**全文看 `subagent-lifecycle.md`**）
- 🔴 **一个 subagent 只活一个任务；任务结束就退役** —— **没有人工批准就没有常驻**
- 🔴 **决策阶梯**：① 主会话 → ② settings/hooks/脚本 → ③ **临时 subagent** → ④ 常驻（需批准）
  ⛔ **不许因为"方便"跳到第 ③ 级**
- 🔴 **文件名⛔ 不许中文**（工具链会折叠非 ASCII；且 `name:` 是**地址**）
- 🔴 **退役 = `git mv` 到 `tmp/<任务类>/`**，⛔ 不是写个说明
- ⚠️ **该规范目前是【文字】，没有门**（`§8` 自陈）

## 📍 往上读
- `../CLAUDE.md` · `subagent-lifecycle.md`
