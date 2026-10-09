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

## 📍 往上读
- `../CLAUDE.md`（`app/`）· `docs/契约/数据模型.md` · 仓库根 `CLAUDE.md`
