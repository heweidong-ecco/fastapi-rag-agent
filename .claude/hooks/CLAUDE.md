# `.claude/hooks/` —— 5 个 hook

## 📇 本目录索引
| 文件 | 触发 | 干什么 |
|---|---|---|
| `pre-commit-gates.py` | `PreToolUse`·Bash 含 `git commit` | **提交前 8 道门**（任一不过就**阻止提交**） |
| `spec-remind.py` | `PostToolUse`·Edit/Write | 写完 `app/**.py` 提醒更新**同目录 `specs/<同名>.md`** |
| `route-auth-remind.py` | `PostToolUse`·Edit/Write | 改了**路由文件**就跑**路由鉴权门** |
| `py-compile-remind.py` | `PostToolUse`·Edit/Write | 改完 `.py` **当场编译一次** |
| `claim-evidence-remind.py` | `PostToolUse`·Edit/Write | 写「不存在 / 唯一」前先出**一条命令** |

## 🔴 本层特有的规矩
- 🔴 **所有 hook 都【只从 stdin 读 JSON】** ⇒ ⛔ **直接 `python3 x.py` 会"全绿"，那是【静默假通过】**
  （`pre-commit-gates.py` 的前科）⇒ 自测**每条都要喂真 JSON**（见 `scripts/test_remind_hooks.sh`）
- 🔴 **提醒型 hook 必须恒 `exit 0`** —— ⛔ 它的失败方式里不许有"把主流程搞挂"
- 🔴 **路径判据要能测出会红** —— `spec-remind` / `route-auth-remind` 的自测在
  `scripts/test_remind_hooks.sh`（**22 条**，含变异自证）
- ⚠️ **hook 只在 Claude 会话里跑**；CI 不触发它们 —— 但**自测进 CI**（它们是要分发给克隆者的东西）

## 📍 往上读
- `../CLAUDE.md` · `../README.md`（门一览）
