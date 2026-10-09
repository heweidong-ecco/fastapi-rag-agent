# `scripts/` —— 门与工具（28 个）

> 📇 **`scripts/` 不是一个程序，是一组"判据"** —— 每份脚本基本都对应
> `.claude/README.md` 上的某一道门，或一个手工工具。

## 📇 本目录索引

**门（提交前 6 道 · 都在 `pre-commit-gates.py` 里调）**
| 脚本 | 拦什么 |
|---|---|
| `check_secrets.sh` | 明文凭据（**进了历史就改不掉**） |
| `check_doc_links.sh` | 文档里**指向不存在的路径** |
| `check_doc_orphans.sh` | 建了文档**但没人指向它** |
| `check_lint_baseline.sh` | `ruff` 的 `E9`/`F` **比基线变多**（基线棘轮） |
| `check_route_auth.py` | **新引入了没鉴权的路由** |
| `check_ci_job_timeouts.py` | **每个 CI job 带 `timeout-minutes`** |
| `check_index_sync.sh` | **索引声明覆盖的东西还在不在** |

**工具 / 自测**
| 脚本 | 用途 |
|---|---|
| `ci-local.sh` | ⭐ **"CI 等价"**：逐字跑 `ci.yml` 的 run 块 |
| `spec_status.sh` | **模块 ↔ spec 对账**（`--write` 重写对账表） |
| `check_remote_sync.sh` | **三方比对**（本地 / 本地视图 / **远端真值**） |
| `impact.sh` | 改某文件会影响哪些测试 |
| `gen_schema_sql.sh` | 重生成 `app/schema.sql` |
| `seed_isolation_*.sh` | 三家常驻隔离语料 / 会话 |
| `backup.sh` · `issue_api_key.py` · `list_endpoints.sh` | 备份 · 发 key · 列接口 |
| `test_check_*.sh` · `test_remind_hooks.sh` · `test_impact.sh` | ⭐ **门自己的自测**（**进 CI**） |
| `doc-links-ignore.txt` · `ruff-baseline.txt` · `route-auth-baseline.txt` | 三份**判据数据** |

## 🔴 本层特有的规矩

1. 🔴 **「门必须能测出自己会红」** —— 新写一道门，**必须同时写 `test_*.sh`**，并**挂进 CI**
2. 🔴 **别把基线改小来"修红"** —— 基线是**棘轮**：只能**修代码**让它变少，⛔ 不能调基线
3. ⚠️ **⛔ 别往 `app/requirements.txt` 塞 linter**（那份清单进 demo 镜像）
4. ⚠️ **判据脚本扫全仓时要按【路径前缀】剪枝 `.claude/worktrees/`** ——
   ⛔ 别用目录名匹配（本仓为此栽过）

## 📍 往上读
- 仓库根 `CLAUDE.md` · `.claude/README.md`（门一览）
