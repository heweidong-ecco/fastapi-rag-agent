# `.claude/` —— 本仓的**门**都在这里

> ## 这份文件是什么
>
> **本仓挂了哪些自动门、在哪、拦什么。**
>
> 📌 **为什么要有它**：门**挂在别处就等于没有门**（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）——
> 而**新会话不会主动去看 `.claude/` 里有什么**。

---

## 一 · 本仓挂的门（**3 道** —— 提交前 1 + 编辑后 2）

### ① 提交前的门 —— `.claude/hooks/pre-commit-gates.py`

**触发**：`PreToolUse` 匹配 `Bash` ⇒ 命令里含 **`git commit`** 时。
**做**：跑下面**四道检查**，**任一不通过就阻止提交**（exit 2）。

| # | 门 | 脚本 | 拦住什么 | 拦不拦 |
|---|---|---|---|---|
| 1 | **凭据门** | `scripts/check_secrets.sh` | PUBLIC 仓里混进**明文凭据**（**进了历史就改不掉**） | 🛑 拦 |
| 2 | **链接检查** | `scripts/check_doc_links.sh` | 文档里**指向不存在的路径** | 🛑 拦 |
| 3 | **孤儿检查** | `scripts/check_doc_orphans.sh` | 建了文档**但没人指向它**（索引挂空） | 🛑 拦 |
| 4 | 🆕 **模块 spec 门** | **内联在 hook 里**（不调外部脚本） | **新增了 `api/X.py` 但 `docs/specs/` 下与模块同名的那个 不存在** | 🛑 **拦** |

> ⚠️ **它只管 `git commit`** —— 不拦 `add` / `push` / `status`。
> ⚠️ **门本身跑不起来时不阻止**（只警告）—— 否则 hook 坏了会把人锁死。
> ⚠️ **第 ④ 道门只管【新增】模块**（`--diff-filter=A`）——
> **改已有模块要不要更新 spec 是【判断】，机械判不了** ⇒ 交给下面那个 PostToolUse hook **提醒**。

### ①·5 · 写完 `api/*.py` 之后的**提醒** —— `.claude/hooks/spec-remind.py`

**触发**：`PostToolUse` 匹配 `Edit|Write|NotebookEdit`。
**做**：如果动的是 **`api/` 下的 `.py`、且不是测试** ⇒ 打一行：

```
有 spec 的： 📋 你动了 `api/reranker.py` —— 记得更新 `docs/specs/reranker.md`（⭐ 关键节：「看代码会误判的地方」）
没 spec 的： 📋 你动了 `api/db.py` —— ⚠️ **它还没有 spec**……做完记得建一份
其它（文档/测试/脚本）： 静默
```

> ⛔ **它不阻止** —— `PostToolUse` 拦不住已经发生的编辑，而且写代码时会频繁触发。
> 📌 **这是有意的分工**：**能机械判的（新增）⇒ 硬拦；判不了的（要不要更新）⇒ 提醒。**

### ①·6 · 🆕 改**路由文件**之后的提醒 —— `.claude/hooks/route-auth-remind.py`

**触发**：`PostToolUse` 匹配 `Edit|Write|NotebookEdit`，**且**改的是
`api/main.py` / `api_v1.py` / `api_v1_rag.py` / `api_v1_agent.py`（**脚本自己判路径**）。
**做**：跑 `scripts/check_route_auth.py --baseline` ⇒ **只报「比基线【变多】」**：

```
🔴 路由鉴权检查：**新引入了没有鉴权依赖的路由**
❌ 比基线【多了 1 条】—— 新引入了没鉴权的路由：
     + /api/v1/debug/cache_stats
⇒ 要么给它加 `Depends(get_current_user_hybrid)`（或 require_admin），
   要么确认它确实该公开 —— 后者请同时把它加进 `main.PUBLIC_PATHS`。
```

> ### 为什么要有它（**这是本仓一条教训的落地**）
> 核 `api_v1.py` 时**手工扫"哪些路由没鉴权"，第一版扫出 0 条** ——
> 因为 `FastAPI 0.141` 起 `include_router` 的结果被包成 `_IncludedRouter`。
>
> 🔴 **那个坑【仓里早就写着】**（`api/test_public_paths.py:17-20`）——
> **知识在，但挂在一个谁都不会去读的地方**（一个测试文件的 docstring 里），**我当天踩了两次**。
>
> ⇒ **不是再写一条规矩**（那天规矩写了三条、犯了五次），
> 是**把它挪到"一定会撞上"的位置** —— **改路由文件 ⇒ 自动跑一次检查**。
> 📄 复盘：`docs/复盘/2026-09-30-判据在手边却没查.md` · 规矩：`docs/规范/开发规范.md` **§1.5**

⚠️ **性能取舍（实测）**：
· 改**非**路由文件 ⇒ **0.05s**，静默退出
· 改**路由**文件 ⇒ **约 9–13s**（要 import `main` 拿真实路由表）
⇒ ⛔ **所以它【先判路径】** —— 不然每次编辑都付 10 秒。
📌 另外那条 91s→9s 的提速，靠的是**在 import 前关掉遥测**（`GRADIO_ANALYTICS_ENABLED` 等），
   根因与 `api/conftest.py:20` 记的**是同一个**。

> ⛔ **它不阻止**（`PostToolUse` 拦不住已发生的编辑）—— 价值是**把话说到眼前**。
> 📌 与 ①·5 的分工一致：**能机械判的 ⇒ 硬拦；判不了的 ⇒ 提醒。**

### ② 用户级的 4 道门（**不在本仓，但会影响你**）

它们在 `~/.claude/hooks/`，**跨项目通用**：

| 脚本 | 何时触发 | 干什么 |
|---|---|---|
| `outward-guard.py` | `PreToolUse` on `Bash` | 对外/不可逆动作（git commit、推送、删文件）**要人工确认** |
| `bulk-write-guard.py` | `PreToolUse` on `Bash` | 批量改写（循环/sed）前**要求先看命中范围** |
| `kb-write-guard.sh` | `PreToolUse` on `Edit\|Write` | 写**避坑库**时的检查（`KB_WRITE_GUARD=1` 门控） |
| `doc-open-reminder.py` | `UserPromptSubmit` | 提醒**打开要用户批注的文档 + 给绝对路径** |

> 📌 **它们不在本仓 ⇒ 克隆的人没有**。本仓的规矩里凡依赖它们的，**要写明"这条靠用户级门"**。

---

## 一·5 · 🆕 斜杠命令（**2 个**）

| 命令 | 什么时候用 | 干什么 |
|---|---|---|
| **`/handoff`** | ⭐ **开发一两个小时后要休息 / 收尾时** | 把这次会话**记到"该记的地方"**，并给出一段「**下次从这里接**」<br>让它**下次会话能接得上**（这是本仓反复出问题的地方 —— 锚点停在 09-24 而 09-29 一整天没记） |

**它按 6 步走**：看 `git`（**不凭记忆**）→ 逐类判断记到哪（**四本账**）→
⭐ **更新 `ROADMAP` 的接续状态** → 跑三道门 → 提交 → 给「下次从这里接」。

| **`/specs`** | 要核**「有哪些模块 / 各自做到哪」**时 | 跑模块 spec 对账；也可给某个模块建 spec |

📄 源文件：`.claude/commands/handoff.md` · `.claude/commands/specs.md` · ⚠️ 它们在仓里 ⇒ **克隆的人也拿得到**

---

## 二 · 手动跑的门（**不在 hook 里，要自己跑**）

| 命令 | 什么时候跑 | 为什么不在 hook 里 |
|---|---|---|
| `bash scripts/list_endpoints.sh` | 要知道**有哪些接口** | 它需要服务在跑 |
| `bash scripts/backup.sh` | 要备份数据库 | **不该每次提交都跑** |
| `bash scripts/impact.sh <关键词>` | 改代码前看**影响面** | 按需 |
| **`bash scripts/check_remote_sync.sh`** 🆕 | **推完 / 收工前**核「本地是不是真跟远端一致」 | **需要网络** ⇒ 在 CI 里三方恒等，**跑了等于没跑**（`DEC-069` §四）。⚠️ 退出码 **`3` = 未知**，⛔ 不是通过 |

---

## 三 · 目录约定

```
.claude/
├── README.md                     ← 本文件：门的一览
├── settings.json                 ← 注册 hook（⛔ 不要 gitignore 它）
├── hooks/
│   ├── pre-commit-gates.py       ← 提交前四道门（凭据/链接/孤儿/模块spec）
│   ├── spec-remind.py            ← 改 api/*.py 后提醒更新 spec（①·5）
│   └── route-auth-remind.py      ← 🆕 改路由文件后查「有没有没鉴权的」（①·6）
└── commands/
    ├── handoff.md                ← `/handoff` 斜杠命令（休息前做记录）
    └── specs.md                  ← `/specs` 斜杠命令（模块对账）
```

**配套脚本**（不在 `.claude/` 里，在 `scripts/`）：
`check_route_auth.py`（无鉴权路由清单 + 基线比对）· `route-auth-baseline.txt`（基线，**现为 1 条** —— 见下）

> 🔴 **2026-10-04（`DEC-065`）基线由 10 条降到 1 条** —— `S1`/`S2`/`S14` 那 9 条**已收口**
> （5 条加 `require_admin` · 4 条**端点删除**）。**仅剩 `/api/v1/`**（`main.py` 的根路径，
> ⚠️ **是否有意公开仍未裁**）。
> 📌 判据（可打印）：`venv/bin/python scripts/check_route_auth.py` ⇒ **无鉴权路由 1 条** ·
> `venv/bin/python scripts/check_route_auth.py --baseline` ⇒ **与基线一致**。

> 🔴 **`.claude/` 必须入库**（本仓实测：**没有被 `.gitignore` 挡**）。
> 理由：hook 脚本要靠它分发；`.gitignore` 掉 ⇒ **克隆的人没有门**。
> 📌 官方说明：skills / agents / commands 有「回退到主检出」机制，**hooks 没有**。
> ⬜ **本仓不用 worktree**（业务方 2026-09-29 裁定：**用 subagent 代替**）。

---

## 四 · ⚠️ 一条已知的**结构弱点**（业务方 2026-09-29 裁「**甲**」：就这样）

> **这些门本身就在仓里 ⇒ 写它的 Agent 有权限改它。**

```
.claude/hooks/pre-commit-gates.py   ← 能改
scripts/check_secrets.sh            ← 能改
.claude/settings.json               ← 能删
```

**⇒ 理论上，AI 能让自己面前的门失效，而没有任何机制会拦。**

**为什么仍然选「甲」**（业务方裁定）：
* ✅ **能提交进 git ⇒ 可审查**（改了什么看得见）
* ✅ **克隆的人也有门**
* ⚠️ 反面是「乙：放 `~/.claude/`」—— AI 碰不到，但**不入库、别人看不到、也审不了**

📌 **依据**：那份《多项目 + 多 worktree》文档说，方案乙**唯一的理由**是
「**不想让 AI 碰得到约束自己用的规则**」。业务方权衡后**选了甲**。

> ### ⭐ 所以这里有一条**结构性补偿**
>
> **门改没改，是可以用命令查的**：
> ```bash
> git log --oneline -- .claude/ scripts/check_*.sh     # 谁什么时候动过门
> git diff HEAD -- .claude/ scripts/check_*.sh         # 有没有未提交的改动
> ```
> ⇒ **选甲的前提是【改动能被看见】** —— 而不是"相信不会改"。

## 变更记录

- **2026-09-30** 加第 ③ 道门（**①·6 `route-auth-remind.py`** + `scripts/check_route_auth.py` + 基线）。
  起因：核 `api_v1.py` 时**手工扫无鉴权路由，第一版扫出 0 条**（踩了 `_IncludedRouter`）——
  **而那个坑仓里早写着**（`api/test_public_paths.py:17-20`），**当天踩了两次**。
  ⇒ **把知识从"没人读的 docstring"挪到"一定会撞上的 hook"。**
  📄 `docs/规范/开发规范.md` **§1.5** · `docs/复盘/2026-09-30-判据在手边却没查.md`
- 2026-09-29 建立（业务方裁「甲」；hook 从 1 道扩到 3 道）。
