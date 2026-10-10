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
### ✅ 现状

- **`alembic` 已装、已进 `app/requirements.txt`**（`==1.20.0`；⚠️ 传递依赖 `Mako` **不单独钉**）。
  📌 判据：`venv/bin/alembic --version` ⇒ `alembic 1.20.0` ·
  `cd app && ../venv/bin/alembic history` ⇒ **4 份链条完整** ·
  `alembic upgrade head --sql` ⇒ **离线生成 45 行 SQL**（⛔ 不碰任何库）。
- ⚠️ 迁移**不在 CI 里跑**（CI 没有 postgres service）。

### 🔴🔴 ⛔ **别对任何真库跑 `alembic upgrade head`** —— 本链【已作废】

- **`f12a761ae626`（init）的 `upgrade()` 里有一句 `op.drop_column('documents', 'requested_by')`** ——
  那是**多用户隔离的承重列**（`DEC-056`）⇒ **跑一次就把隔离拆了，且不报错**。
  📌 判据：`grep -cn "^    op.drop_column('documents', 'requested_by')" versions/f12a761ae626_init.py` ⇒ **1**
- **它也不能从空库 bootstrap** —— 全篇只有 `ALTER` / `DROP`，默认表已存在。
- 🔴 **⇒ 表结构的【真值】= `app/schema.sql`**（活库 `pg_dump` 生成）+ `app/core/db.py` 的 `create_table()`
  （含那段 `DO $$ … ALTER`）**，⛔ 不是这条迁移链**。
  ⇒ **改了表结构，那两处都要写**，⛔ 别只写迁移。
- 📄 **为什么会变成这样**（autogenerate 方向反了）⇒ `CHANGELOG` 2026-10-10 那条 ·
  文件头注释 ⇒ `versions/f12a761ae626_init.py`。
- ⬜ **待办**：要不要**重做一份 baseline** ⇒ `docs/待办总表.md` **`N24`**
  （⚠️ **不是"顺手改"**：要起 PG，且会改动整条链）。

## 📍 往上读
- `../CLAUDE.md`（`app/`）· `docs/契约/数据模型.md` · 仓库根 `CLAUDE.md`
