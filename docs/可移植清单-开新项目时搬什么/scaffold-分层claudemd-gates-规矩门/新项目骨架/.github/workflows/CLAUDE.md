# `.github/workflows/` —— workflow 文件

## 📇 本目录索引
| 文件 | 是什么 |
|---|---|
| `ci.yml` | **唯一的 workflow** |

## 🔴 本层特有的规矩
- ⚠️ **每个 job 必须带 `timeout-minutes`** —— ⛔ 「卡住」与「跑得很慢」在机器痕迹上**一样**，
  没有上限时"卡住"不是一个**显式状态**
- ⚠️ **门要跑在这里、⛔ 不能只在本地 hook 里** —— 本地 hook 只在 Claude 会话里触发，
  `--no-verify` / 人直接 commit 都绕得过 ⇒ **不接 CI 就不是门**

## 📍 往上读
- `../CLAUDE.md`（`.github/`）· 仓库根 `CLAUDE.md`
