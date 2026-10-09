# DEC-126 · 容器名 `api/` → `app/`（**只改名字，⛔ 不改成包**）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已落**（2026-10-09 · 与 `DEC-125` 同分支 `refactor/modular-layout`） |
| **触发** | 业务方 2026-10-09：「**文件夹名 api/ 应该改为 app/**……**api/routing 应该改为 app/api**」 |
| **类型** | **纯改名重构**（⛔ 不改行为、⛔ 不改包语义、⛔ 不动 Docker 语义） |
| **落点** | `api/` → `app/` · `docker-compose.yml` · `dev.sh` · `ci.yml` · `scripts/` · `.claude/hooks/` · `frontend/索引.md` |

---

## 一 · 要解决的是什么（业务方确认过）

> 业务方 2026-10-09：「**是的，主要也是考虑这个问题**」（指下面那两条）。

| # | 缺陷 | 是不是真的 |
|---|---|---|
| **(a)** | **`api/` 名不副实** —— 它装的是**整个应用**（`agent/` `rag/` `tools/` `billing/`），不只是 API | ✅ **真缺陷** |
| (b) | ~~`routing/` 与 URL `/api/v1/` 撞名~~ | ❌ **本 DEC 否决** —— 见 §三 |

---

## 二 · 决策点

### 2.1 只改**(a)**，且**只改名字**

| 备选 | 判断 |
|---|---|
| **甲（选）：`api/` → `app/`，⛔ 不起 `app.` 前缀** | 196 个 `git mv` + **约 50 处路径**，**导入 0 改动** |
| 乙：`api/` → `app/` **且 `app/` 变成 Python 包**（`from app.core.config import X`） | ⛔ **不选**，理由见 §2.2 |
| 丙：不改 | ⛔ 业务方要改 (a) |

### 2.2 🔴 为什么**不**做成包（否掉「乙」）

业务方原话里的 **`api/routing` → `app/api`** 这条，**只有在"做成包"时才自然**。
而「做成包」的要价是四样：

| # | 代价 |
|---|---|
| 1 | **510 处导入改写**（`from core.config import X` → `from app.core.config import X`），分布在 **113 个文件** |
| 2 | **Docker 构建上下文从 `./api` 改成仓库根** —— 因为要 `/app/app/` 这种结构 |
| 3 | **必须新建仓根 `.dockerignore`** —— 否则 `venv/`(**927 M**) + `venv-ragas/`(442 M) + `.git/` 全进 Docker daemon |
| 4 | 一次 **15–20 分钟** 的 `docker build` 验证才敢说"没坏" |

⚠️ 而这四样**换来的只是 `app.` 前缀的显式性** ——
⛔ **不是缺陷 (a) 的修复**。(a) 的修复只需要**改名字**。

📌 本仓立场（`CLAUDE.md` ② / 反引号那条「非必要的不要做」）：
**为一件纯命名的改动动部署单元与跨项目依赖，不划算。**

### 2.3 🔴 否掉 (b)：**⛔ 不做 `routing/` → `api/`**

**理由（本 DEC 最重要的一条）**：

- **今天 `routing/` 与 URL `/api/v1/` 并不撞名** —— `routing` ≠ `api`。
- **撞名是"把组名改成 `api/`"之后才会发生的事** ⇒ 那是**这个提议自己制造出来的问题**。
- 而在**甲**（`app/` 不是包）的形状下，`app/api/api_v1.py` 会被导入成 **`api.api_v1`**
  ⇒ **把 URL 前缀的歧义从"无"变成"有"**。

⇒ **保留 `routing/`**，导入名仍是 `from routing.api_v1 import X` —— 干净、无歧义。

---

## 三 · 判据（**可打印**）

```bash
# 1. 改名生效、导入没动
ls -d app/                      # ⇒ 在；  ls -d api/ ⇒ 不存在
grep -rn "^from core\.\|^from routing\." app/*.py app/*/*.py | head   # ⇒ 仍是原样（⛔ 没有 app. 前缀）

# 2. 行为没变 —— 主判据
./venv/bin/python -m pytest app/ -m "not integration and not needs_db" -q   # ⇒ 913 passed / 2 skipped
bash scripts/ci-local.sh                                                     # ⇒ 退出码 0

# 3. 门
bash scripts/check_doc_links.sh ; bash scripts/check_doc_orphans.sh
bash scripts/test_remind_hooks.sh                                            # ⇒ 22 通过 / 0 失败

# 4. Docker 配置仍能解析（⛔ 不改语义，只改路径串）
docker compose config >/dev/null && echo OK
```

---

## 四 · 反悔成本

**低** —— 纯改名，`git mv` 保了历史；回退 = 再把 `app/` 移回 `api/` + 改回那约 50 处路径。
⛔ **没有**任何"改完就难退"的东西（无数据迁移、无外部接口变更、镜像名不变）。

---

## 五 · ⛔ 本 DEC **没有**解决的

1. ⚠️ **`app/` 不是 Python 包** —— 所以它**不会**出现在导入里（`from routing.api_v1 import X`，⛔ 不是 `app.routing.api_v1`）。
   **这是"只改名字"的固有形状，⛔ 不是 bug**。
2. ⚠️ **文档里仍有大量 `api/...` 的旧路径**（历史记录：`CHANGELOG` · `docs/复盘` · `docs/decisions`）。
   ⛔ **有意不改**（本仓立场：原始记录不改写）。断链门**只查 `.md` 目标**，`.py` 路径不在它射程内。
3. ⬜ 段 2 / 段 3 的落点自此改成 **`app/<组>/specs/`** 与 **`app/...`**。

---

## 关联

- `DEC-125` —— 模块化重构（本 DEC 是它的**续**：段 1 拆完组 ⇒ 容器名接着改）
- `DEC-120 §七` —— `api/static/` 落点维持（本 DEC **不动** `app/static/` 的位置）
- `docs/规范/开发规范.md` —— ⚠️ 它**没有**关于模块目录名的规矩；
  本 DEC 采纳的是**外部通用惯例**（`app/` 作应用根），⛔ 不是本仓既有规范
