# DEC-086 · `api_keys.is_active` 的**唯一来源 = 本仓 DDL**（⛔ 不是某个已不存在的迁移）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已裁 · 已实施**（2026-10-06 业务方裁「选 (a)」） |
| **触发** | 段 1 第一刀（`DEC-085`）**真连后端**验硬门 A/B/C 时，**每把 key 都 503** |
| **业务方裁定** | 2026-10-06：**选 (a) 让这一列真的存在**（语义保持 `DEC-085` 契约 D 的） |
| **类型** | 🔴 **修一处已进分支的真实回归**（`242a74d` 引入）+ 补 DDL / 文档 / 两条尺子 |
| **落点** | `api/db.py` · `api/schema.sql` · `api/db_metadata.py`（注释）· `api/test_auth_api_key_active.py` · `docs/契约/数据模型.md` |
| **判据** | §四 —— 全部**可打印** |

---

## 二 · 症状（实测）

```
GET /api/v1/agent/token/usage
  带真 key    ⇒ 503   {"error":"认证服务不可用（数据库连接失败）… 原因：UndefinedColumn"}
  乱写 key    ⇒ 503   （**同一句**）
  不带 key    ⇒ 401
```

🔴 **`乱写 key` 也是 503** ⇒ 炸的不是"认证失败"，是**认证这条路本身**。
服务端日志同时出现两条**比 503 更值得注意**的：

```
🔴 认证服务不可用 ⇒ 本次【跳过】额度检查 (fail-open)：… 原因：UndefinedColumn
🔴 认证服务不可用 ⇒ 本次请求【不参与用户级限流】(fail-open)：… 原因：UndefinedColumn
```

⇒ **两道本该拦人的闸在同一根因下静默放开**。（上公网后这个组合 = key 全 503 + 限流/额度不生效。）

## 三 · 根因：**四处说"有"，三处说"没有"，而代码信了那四处之一**

| 处 | 有没有 `is_active` |
|---|---|
| 真库 `api_keys`（实测 `information_schema.columns`） | ❌ 只有 5 列 |
| `api/schema.sql`（从真库导出的口径） | ❌ |
| `api/db.py:create_table()`（**运行时真正的建表语句**） | ❌ |
| `docs/契约/数据模型.md` | ✅ 但写的是「**由迁移 `828721f77ef2` 加上**」 |
| `api/db_metadata.py:41`（SQLAlchemy 声明，给 Alembic autogenerate 用） | ✅ |
| `api/auth.py:105`（`DEC-085` 契约 D，本轮加的过滤） | ✅ **它按这一列过滤** |

- 本仓**没有** `alembic.ini`、**没有** `migrations/` —— **全仓没有任何 DDL 加过这一列**
  ⇒ 那句"由迁移加上"描述的是一个**在本库从未生效**的动作。
- `db.py` 用的是 `CREATE TABLE IF NOT EXISTS` ⇒ **对已存在的表什么都不做**
  ⇒ 就算把列写进建表语句，**老库也永远补不上**。

**⇒ 报告里说"由某个外部迁移保证"的写法，让代码和文档【一起】假设了一个不存在的前提。**

### 🔴 为什么 712 条用例一条都没红

那条最该抓住它的用例，表是**它自己现建的**：

```python
# api/test_auth_api_key_active.py（改动前）
conn.execute("CREATE TABLE api_keys (user_name TEXT, key_hash TEXT, is_active INTEGER, expires_at TEXT)")
```

它按**文档的描述**建表，而文档描述的是**真库里没有的那张表**。
⇒ 用例与读文档的人**读的是同一份错前提** ⇒ 恒绿。
（同族：`docs/复盘/2026-10-05-拿代理量当判据.md`、`2026-09-29-结果为空就断言能力不存在.md`。）

## 四 · 候选与裁定

| # | 方案 | 评估 | 结论 |
|---|---|---|---|
| **(a)** | **让这一列真的存在**：补进 `db.py` 建表语句 + 加**启动期 `ALTER`**（照抄同文件里 `documents.requested_by` 那块），同步 `schema.sql` 与文档 | ✅ 语义与契约 D 一致；加列是**加法**，老行自动为真；`⛔ 不重建容器` | ✅ **业务方选此** |
| (b) | 回退 `auth.py` 那句 `COALESCE(is_active, 1) = 1`，回到"停用不生效" | ❌ 让 `DEC-085` 契约 D 作废 ⇒ `scripts/issue_api_key.py --revoke` 变成装饰（它写 `0`，而没人读） | 未选 |

### ⚠️ 实施中的一处**必须记住的细节**：类型是 `INTEGER(0/1)`，⛔ 不是 `BOOLEAN`

第一版 DDL 写成了 `BOOLEAN DEFAULT TRUE` —— **是错的**。写入侧写的是整数：

```python
# scripts/issue_api_key.py:55
"UPDATE api_keys SET is_active = 0 ..."
```

建成 `boolean` ⇒ 那句直接报 `column is of type boolean but expression is of type integer`
⇒ **`--revoke` 会被打挂**。全仓另外两处也都是整数口径：
`api/db_metadata.py:41`（`Integer, server_default="1"`）· 用例里的 sqlite `INTEGER`。

## 五 · 判据（可打印）

```bash
# ① 真库这一列在不在（重启服务让 startup 的 ALTER 生效之后）
#    ⇒ is_active｜integer｜1
psql ... -c "\d api_keys"

# ② 认证恢复：带真 key 200（**且身份正确**）/ 乱写 key 401（⛔ 不再是 503）
curl -H "X-API-Key: $K" .../api/v1/agent/token/usage

# ③ 契约 D 的语义真在跑（真库往返）
venv/bin/python scripts/issue_api_key.py <name> --days 1     # ⇒ 带它 200
venv/bin/python scripts/issue_api_key.py <name> --revoke     # ⇒ 库 is_active=0 ⇒ 带它 401

# ④ 两条尺子（本轮新加，各自反证过 ⇒ 见 §六）
venv/bin/python -m pytest api/test_auth_api_key_active.py -q     # ⇒ 5 passed
```

## 六 · 为什么现在有两条尺子（**各自只挡一半**）

| 用例 | 挡的改法 | 反证（实测） |
|---|---|---|
| `test_table_in_db_py_has_every_column_the_query_touches`<br>表**取自 `db.py` 的真 DDL**，跑 `auth.py` 的真 SQL | 只改 `auth.py` 的查询、**没改建表 DDL**（= 本轮之前的形态） | 把 `is_active` 从建表语句拿掉 ⇒ **只这一条红** |
| `test_columns_newer_than_exported_schema_have_an_alter_in_db_py`<br>「后加的列」必须都有 `ALTER` 补列 | 改了建表 DDL、**忘了老库那句 ALTER** | 把那句 `ALTER` 拿掉 ⇒ **只这一条红** |

⚠️ **两条都【不】覆盖"老库真的补上了"** —— 那一步只能在真库上验（§五 ①）。
用例能保证的是**代码里两处不会再各说各话**。

## 七 · 反悔成本

- **回退**：`git revert` 这一提交即可 —— 列留在库里（多余但无害），代码回到"按不存在的列过滤"的唯一代价是 **503 复现**。
  ⇒ 所以**别单独 revert 代码、却以为库也跟着回去了**。
- **加列本身没有回退压力**：多一列不影响任何现有查询（`SELECT *` 的使用者需自己确认，本仓 `auth.py` 是显式列名）。

## 八 · 本份**没有**解决的（⛔ 别读成"`is_active` 这条线全绿了"）

1. **`api/db_metadata.py` 与 `db.py` 的其余差异仍在**（`documents` 缺 `requested_by`、`embedding` 写成 `Text`）
   —— 本份只动了 `api_keys` 这一处。
2. **没有迁移工具**：本仓至今靠 `create_table()` 的 `DO $$ ... ALTER $$` 做兼容。
   ⚠️ 这个手法的代价是**每加一列都要记得写一句**（现在有尺子盯着）。
3. **`is_active` 的 NULL 语义仍是"放行"**（`COALESCE(x, 1)`）—— 本机真库实测 5 行全为 `1`，无 NULL 行。

## 九 · 一次**未预期**的操作（已复原），如实记在这里

验 §五 ③ 的往返时用了 `scripts/issue_api_key.py admin --revoke`，
而 `--revoke` 撤销的是**该用户名下的全部 key** ⇒
**连带把 `admin` 在 2026-09-10 建的那把老 key（`id=2`）也置成了 `is_active = 0`**。

### ✅ 复原（2026-10-06，当天）

⚠️ **我一度写成"明文找不回" —— 那句是错的。** 业务方指出凭据存放在**仓外**：
`~/Desktop/Product-external/fastapi-rag-agent-凭据/userkey_from_test.md`（`Product-external/` 是
「仓外受管地」，⛔ 不在任何 git 仓的路径闭包内，故可存明文）。

那份文件 `:29` 就存着 `id=2` 的明文，且**哈希逐字符对得上**：

```bash
K=$(grep -oE 'sk-[0-9a-f]{32}' "<那份文件>" | head -1)
echo -n "${K}" | shasum -a 256        # ⇒ bc2fc0f5…e56e3
# 库里：SELECT key_hash FROM api_keys WHERE id=2;   ⇒ bc2fc0f5…e56e3   ← 同一条
```

⇒ **不必重发**（重发会新增一行，还得重新分发明文、并让那份文件的说明过期）。
直接拨回即可：

```sql
UPDATE api_keys SET is_active = 1 WHERE id = 2;
```

**复原后实测**（真后端 + 真库）：
带该 key ⇒ **200 `{"user_name":"admin",…,"requested_by":"admin"}`**（身份正确，⛔ 不是匿名）·
乱写 key ⇒ **401**（⛔ 不再是 503）· 已撤销的 `id=7` ⇒ **401** · 三家 `isolation_*` ⇒ **均 200**。

### ⛔ 教训

1. **`--revoke` 是【按用户名】的**，⛔ 不是"撤销我刚发的那把"。
   要在共享用户名上验往返，**先确认该用户名下有几行**再动手。
2. **说"找不回"之前，先找一遍凭据存放地** —— 本仓有专门的仓外凭据目录，
   而我当时只想着"库里只存哈希"。**"库里没有"≠"世上没有"**（同族：`docs/复盘` 那几篇
   「结果为空就断言…」）。
