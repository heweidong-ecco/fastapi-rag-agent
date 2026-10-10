# `scripts/` —— 门与工具

> 📇 **`scripts/` 不是一个程序，是一组"判据"** —— 每份脚本基本都对应 `.claude/CLAUDE.md` 上写的某一道门。

## 📇 本目录索引

**门（提交前 · 都在 `pre-commit-gates.py` 里调）**
| 脚本 | 拦什么 |
|---|---|
| `check_secrets.sh` | 明文凭据（**进了历史就改不掉**） |
| `check_doc_links.sh` | 文档里**指向不存在的路径** |
| `check_doc_orphans.sh` | 建了文档**但没人指向它** |
| `check_layered_claude_md.sh` | **新加了一个目录、却没给它 `CLAUDE.md`** |

**CI 形状**
| 脚本 | 用途 |
|---|---|
| `check_ci_job_timeouts.py` | **每个 CI job 必须带 `timeout-minutes`** —— 否则"卡住"不是一个显式状态 |

**判据数据 / 模板**
| 文件 | 用途 |
|---|---|
| `doc-links-ignore.txt` | 断链门的豁免清单（**空白模板**） |
| `secret-denylist.txt.template` | 凭据黑名单（**空白模板**；重命名成 `.secret-denylist`，被 `.gitignore` 挡着） |

## 🔴 本层特有的规矩
1. 🔴 **「门必须能测出自己会红」** —— 新写一道门，**必须同时写自测**，并**挂进 CI**
2. 🔴 **CI 里没接的门不算门** —— `--no-verify` / 人直接 commit 都绕得过本地 hook
3. ⚠️ **⛔ 别把"红了"当"要调宽"** —— 先问「是代码错了，还是判据错了」

## 📍 往上读
- 仓库根 `CLAUDE.md` · `../.claude/CLAUDE.md`（门一览）
