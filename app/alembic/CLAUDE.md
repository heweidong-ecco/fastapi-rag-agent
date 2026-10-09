# `app/alembic/` —— 数据库迁移

## 📇 本目录索引
| 条目 | 是什么 |
|---|---|
| `env.py` | 迁移入口。⚠️ 它 `sys.path.insert(0, dirname(dirname(__file__)))` ⇒ **把 `app/` 放上路径**（⛔ 靠的是**相对层数**） |
| `script.py.mako` | 新迁移的模板 |
| `versions/` | 迁移脚本 |
| `../alembic.ini` | 配置（在 `app/` 根，`script_location = %(here)s/alembic`） |

## 🔴 本层特有的规矩
- ⚠️ **`env.py` 的 `dirname(dirname(__file__))` 是【相对层数】** ⇒
  **本目录整体搬家时必须同步改**，否则迁移找不到 `app/` 里的模块。
- ⚠️ **表结构的【真相】有两处，别读混**：迁移脚本 vs **`app/schema.sql`**（导出的 DDL）。
  后者由 `bash scripts/gen_schema_sql.sh` 重新生成 —— ⛔ **别手改 `schema.sql`**。
- ⚠️ 迁移**不在 CI 里跑**（CI 没有 postgres service）。
- 🔴 **而且本机【根本跑不了】**（2026-10-09 实测）：**`alembic` 既没装、也不在 `app/requirements.txt` 里**
  —— 从仓根 `import alembic` ⇒ `ModuleNotFoundError`；`venv/bin/alembic` ⇒ 不存在。
  ⇒ **本目录下那 4 份迁移，一份都没在本机被执行过**，它们的正确性**只经过人工审读**。
  ⚠️ **本项目实际加列靠的是 `app/core/db.py:create_table()` 里那段 `DO $$ … ALTER`**
  （`api_keys.role` 就是这么加的，已在真库上核过）。
  ⇒ **改了表结构，两处都要写**，⛔ 别只写迁移。
  ⬜ **待裁**：要不要把 `alembic` 加进 `requirements.txt` ⇒ `docs/待办总表.md` **`N22`**。

## 📍 往上读
- `../CLAUDE.md`（`app/`）· `docs/契约/数据模型.md` · 仓库根 `CLAUDE.md`
