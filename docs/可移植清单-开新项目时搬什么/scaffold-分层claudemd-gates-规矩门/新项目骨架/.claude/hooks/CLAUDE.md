# `.claude/hooks/` —— 本仓的 hook

## 📇 本目录索引
| 文件 | 触发 | 干什么 |
|---|---|---|
| `pre-commit-gates.py` | `PreToolUse`·Bash 含 `git commit` | **提交前的门**（任一不过就**阻止提交**）|
| `claim-evidence-remind.py` | `PostToolUse`·Edit/Write | 写「不存在 / 唯一」前先出**一条命令** |
| `py-compile-remind.py` | `PostToolUse`·Edit/Write | 改完 `.py` **当场编译一次** |

## 🔴 本层特有的规矩
- 🔴 **所有 hook 都【只从 stdin 读 JSON】** ⇒ ⛔ **直接 `python3 x.py` 会"全绿"，那是【静默假通过】** ⇒ 自测**每条都要喂真 JSON**
- 🔴 **提醒型 hook 必须恒 `exit 0`**
- ⚠️ **加一个 hook ⇒ 两处都要改**：① 这里 ② `../settings.json` 的 `hooks` 块（⛔ 漏了②等于没装）

## 📍 往上读
- `../CLAUDE.md`（`.claude/`）
