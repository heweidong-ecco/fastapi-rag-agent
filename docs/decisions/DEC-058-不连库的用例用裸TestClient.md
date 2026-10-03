# 决策记录：DEC-058 · **不连库的用例一律用【裸】`TestClient(app)`，⛔ 不用 `with … as`**

- 日期：2026-10-03
- 状态：**已立 · ✅ 已实施**（`api/test_removed_endpoints.py` 改回裸用 · 全量 CI **412 passed**）
- 触发：**PR #74 合并后、N6 开 PR 前**（`feat/remove-rag-ask` 的 rebase 收尾）跑
  `bash scripts/ci-local.sh` ⇒ **`1 failed, 411 passed`** —— 红的正是 N6 自己新写的那条
  `api/test_removed_endpoints.py::test_rag_ask_stays_removed`（`psycopg2` · `Connection refused`）。

  ⚠️ **这条红在本机是看不见的**（本机 Postgres 真开着 ⇒ 连得上 ⇒ 照样绿）。是 `ci-local.sh` 报的。

  同日业务方裁决（原话）：

  > 「**1.删除。2.开 DEC。**」（本份即 ②）

---

## 一 · 要裁的是什么

修这条 CI 红，**至少有三条路**，且它们**不是"写法偏好"** —— 选错会**悄悄废掉这条用例存在的理由**。

先把那条用例是什么说清（`DEC-057` §3.1）：

| 项 | 值 |
|---|---|
| 它是什么 | **反向守卫** —— 「`/rag/ask` 回来就红」 |
| 它的判据 | **HTTP 404**（路由不存在） |
| 它**需要**什么 | **只需要路由表** —— ⛔ **不需要 DB、不需要 Redis、不需要 lifespan startup** |

**红的原因**：写成了 `with TestClient(app) as client:` —— **上下文管理器形态会触发 lifespan 的 startup**
⇒ `init_pool()` **真去连 Postgres** ⇒ CI 没有 Postgres ⇒ `Connection refused`。

⇒ **这是一个"用例需要的"与"用例触发的"不匹配**：它**只**要路由表，却**顺手**把整个应用的启动流程跑了一遍。

---

## 二 · 备选方案（三条，⛔ 不是两条）

### 甲 · **裸 `TestClient(app)`**（✅ **选用**）

```python
client = TestClient(app)          # ⛔ 不加 with
resp = client.post("/api/v1/rag/ask", json={...})
```

Starlette 的 `TestClient` **只有在被当作上下文管理器使用时才运行 lifespan** ⇒ 裸用**只发请求、不跑 startup**。

### 乙 · **给该用例标 `needs_db`**

```python
pytestmark = pytest.mark.needs_db     # ❌ 没选
```

⇒ CI 的 `-m "not integration and not needs_db"` 会把它**排除** ⇒ 它**不在 CI 里跑**。

### 丙 · **保留 `with … as`，另加一个 patch 把 `init_pool` 短路掉**

```python
monkeypatch.setattr(db_mod, "init_pool", lambda *a, **k: None)    # ❌ 没选
```

⇒ 启动流程**照跑**，只是不真连库。

---

## 三 · 评估标准（**按重要性排序**）

| # | 标准 | 为什么它排这个位置 |
|---|---|---|
| **1** | ⭐ **这条用例在 CI 里还跑不跑？** | **这是它存在的全部理由。** 一条"只在某人本机能跑"的守卫，等于**没有守卫** —— 本仓立场：「**门挂在别处，就等于没有门**」 |
| **2** | **它会不会掩盖真问题？** | 用 patch 让它变绿，可能**盖住**「这个用例到底需不需要 startup」这个真问题 |
| **3** | **是不是【回到既有写法】，而不是【新立一套】** | 本仓已有明确惯例，新立一套要付"解释成本" |
| **4** | **反悔成本** | 低不低 |

---

## 四 · 裁决与理由

> ### **选 甲 · 裸 `TestClient(app)`。**

**逐条对照**：

| 标准 | 甲 | 乙 | 丙 |
|---|---|---|---|
| **1 · 还在 CI 里跑吗** | ✅ 在 | 🔴 **不在**（被 `-m` 排除）⇒ **守卫失效** | ✅ 在 |
| **2 · 掩盖真问题吗** | ✅ 不掩盖 —— 它**本来就不需要** startup | ⚠️ 掩盖：让人误以为"这用例需要库" | 🔴 **掩盖** —— 它**替用例回答了"不需要 startup"**，而那个回答**是猜的**：真正的回答是**这条用例压根不该触发 startup** |
| **3 · 是既有写法吗** | ✅ **是**（见下） | ⚠️ 不是（本仓从没有"守卫用例标 `needs_db`"的先例） | ⚠️ 不是（新增一处 patch，且**理由不明显**） |
| **4 · 反悔成本** | 低 | 中（要先把守卫从 CI 外搬回来） | 低 |

### 4.1 为什么标准 1 是决定性的 —— **乙 是自废武功**

`needs_db` 的语义是「**这条用例真的需要真库**」。而这条用例的**全部意思**是
「**路由表里不该有这个端点**」—— 它**与库毫无关系**。

把它标 `needs_db` ⇒ **等于"因为 CI 没有 Postgres，所以把这条守卫从 CI 里摘出去"**。
⇒ **守卫还在，只是不在会红的地方** —— 正是本仓反复记的那个病的**变体**：

> **「门挂在别处，就等于没有门」**（`CLAUDE.md` · `.claude/README.md`）
> 📄 同族的实测：`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`（8 个 PR 一次都没跑过 `/留痕-checks`）

### 4.2 为什么 丙 也不行 —— **它把"猜的答案"固化进代码**

丙 让 startup **照跑**，只是不连库。它**能绿**，但它**默认了一个未经核实的判断**：
「这条用例是需要 lifespan 的，只是需要把库摘掉」。

⛔ **而事实相反**：这条用例**根本不需要 lifespan**。丙 会把一个**错误的前提**写进代码，
并且**下一个人照抄时，会照抄那个前提** —— 这正是本仓最贵的一类成本（**错误示范的传染**）。

### 4.3 甲 成立，是因为它**是本仓的既有写法**（已实测）

```bash
grep -rnE '^[[:space:]]*with TestClient' api/*.py     # 修复后 ⇒ 0 命中
```

**修复前，全仓只有这一处用 `with … as`** —— 就是它把自己坑了。
其余**不连库**的用例（`test_isolation.py` · `test_rag_search.py` …）**一律裸用**。

⇒ **本次不是"新立口径"，是"回到既有写法"。** 所以 §三 标准 3 满足。

---

## 五 · 由此立的一条规矩

> ### **不连库的用例 ⇒ 裸 `TestClient(app)`。用 `with … as` 的用例 ⇒ 必须标 `needs_db`。**

**理由**：`with … as` 的唯一效果就是**跑 lifespan** ⇒ 它会**拉起整个应用的 startup**（含 `init_pool()`）
⇒ **那是一条真·集成用例**，理应标 `needs_db`。

**所以两侧应当【一一对应】**：

| 用了 | 就必须 | 否则 |
|---|---|---|
| 裸 `TestClient(app)` | **不该**标 `needs_db` | ⚠️ 把原本能进 CI 的用例摘出去了 |
| `with TestClient(app) as …` | **必须**标 `needs_db` | 🔴 **CI 上必红**（`Connection refused`） |

**可打印判据**（两个集合应当一致）：

```bash
# A · 用了上下文管理器的文件
grep -rlnE '^[[:space:]]*with TestClient' api/*.py
# B · 自报需要真库的文件
grep -rln 'pytestmark = pytest.mark.needs_db' api/*.py
# ⇒ A ⊆ B。A 里有、B 里没有的，就是"上了 CI 必红"的那些。
```

⚠️ **判据的写法有坑（本 commit 的 message 初稿就栽了）**：

```bash
grep -rn 'with TestClient' api/*.py      # ⛔ 会命中【docstring 里】那句
                                         #   「⛔ 别把这里改成 with TestClient(app) as client:」
                                         #   ⇒ 数成 1（实测）
```

⇒ **判据纪律第 2 条**：**按位置核，注释 / 文档串里也有同样的串**。
有效写法是 **`^[[:space:]]*with TestClient`**（行首缩进后直接就是 `with` ⇒ 只有真正的语句会命中），
**并做过证伪**：把修复退回 ⇒ **1 命中**；修后 ⇒ **0 命中**。

---

## 六 · 判据（可打印）

```bash
bash scripts/ci-local.sh
# ⇒ 412 passed, 3 skipped, 32 deselected     （修前：1 failed, 411 passed）

grep -rnE '^[[:space:]]*with TestClient' api/*.py        # ⇒ 0 命中
venv/bin/python -m pytest api/test_removed_endpoints.py -q -p no:warnings   # ⇒ 1 passed
python3 .claude/hooks/pre-commit-gates.py
# ⇒ 凭据门 ✅ ｜ 链接检查 ✅ ｜ 孤儿检查 ✅ ｜ 模块spec门 ✅
```

---

## 七 · 反悔成本（**≈ 0，但要说清"退回去会怎样"**）

**结论**：**≈ 0**。

| 项 | 反悔成本 |
|---|---|
| 改回 `with … as` | **极低**（一处两行）—— ⚠️ **但改回就必须同时标 `needs_db`**，否则**复原当天那条 CI 红** |
| `DEC-058` 本身的结论 | 低（是一条**判据**，不是一份**实现**） |
| **用户可见的影响** | **零** |

⚠️ **唯一要记住的**：**这条红在本机复现不出来**。
⇒ 反悔时**不能靠"我本机跑一遍是绿的"来确认没坏事** —— 必须跑 `bash scripts/ci-local.sh`。

---

## 八 · 关联

| 文档 | 说明 |
|---|---|
| `api/test_removed_endpoints.py` | 🔴 本裁决的落点（裸 `TestClient(app)` + 注释写明为什么不能改回 `with`） |
| `docs/规范/开发规范.md` **§2.5·5** | ⭐ **本裁决立成的规矩**（两个集合应当一一对应） |
| `docs/规范/开发规范.md` **§2.5** | 同族：「本地绿」不许用来宣称「不依赖某个外部服务」 |
| `docs/decisions/DEC-057-…` | 那条用例是 N6 的**反向守卫**（判据 = 404） |
| `docs/复盘/2026-10-03-CI同款命令不等于CI等价物.md` | ⭐ **同一个成因家族** —— 「本机看得见 ≠ CI 看得见」 |
| `docs/说明/测试.md` §5.2 | `scripts/ci-local.sh` 的用法 |

> 📌 **本份与那份复盘的关系**：复盘记的是**#74 那 12 条红**（改了函数的依赖来源）；
> 本份裁的是**同一家族的另一个触发面** —— **测试自己把 startup 拉起来了**。
> 两者的共同点是：**它们都只在"没有真服务的环境"里才现形**。

## 变更记录

- 2026-10-03 建立（实施同日）。触发：N6 的 rebase 收尾时 `ci-local.sh` 报出 1 条红；业务方裁定「开 DEC」。
