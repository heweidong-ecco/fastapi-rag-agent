# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

> ⚠️ **2026-09-17 起本文件改为【入库】**（业务方裁决）—— 此前在 `.gitignore:17`，现已移出。
> **它现在是 PUBLIC 仓库内容，不得写入明文凭据**（移出前已扫：5 个真实凭据 + 3 个历史泄露字面量，0 命中）。
> 最近一次全面复审：2026-08-17。重要修复记录见文末「本次复审修复记录」。

---

# 🔴🔴 当前方向（**2026-09-24 起 · 高于本文档其余一切**）

> **主线换了**：不是"收拾仓库 / 清遗留"，是 **把它变成一个【能分享的链接】（上公网）**。
> 路线已拍板：**路线 C = 域名 + Cloudflare 隧道**。
>
> ## 🔴 **先读 `ROADMAP.md`**（**2026-09-29 起：它是唯一权威**）
>
> 状态 / 进度 / 功能现状 / 接口怎么查 / 待办总账 —— **全部收敛到那一份**。
> （📌 之前有 **6 份文档各自声称写了"当前状态"**，已汇总；其余见 `fastapi-rag-agent-TODO待办/归档/README.md`。）
>
> 📄 **两份配套工作文档**：
> * **`fastapi-rag-agent-TODO待办/施工单-本项目.md`** —— 命令级、可直接照做（阶段 ④–⑧ ；**进度留痕表已移入 `ROADMAP.md`**）
> * ⚠️ **`fastapi-rag-agent-TODO待办/现状与差距.md` 已【归档】** ⇒
>   现为 **`fastapi-rag-agent-TODO待办/归档/现状与差距.md`**（其 §3.1「根因 = torch」**已被 `DEC-034` 推翻**）
>
> 📌 **`docs/重构计划-2026-09-15.md` 已成【档案】，不是待办**（它下面那段仍保留，供查历史）。
> 🔴 **2026-09-29 补充**：该文件**已移入** `fastapi-rag-agent-TODO待办/归档/重构计划-2026-09-15.md`，
> 且它**标题里那句「当前最高优先级」已失效**（归档头里写明了）。

## 🔴 两条【高等级约束】—— 业务方 2026-09-24 裁定（全文见 **`docs/decisions/DEC-033`**）

### 🅰️ **Docker 由本仓独占使用**

> 业务方原话：「现在 Docker 一直都只有我们在使用，其他的项目的 docker **我都不会开**，
> 基本上是开发阶段已经完成，不会使用到 docker 了。」

⇒ **不需要容器名 / 端口 / 数据卷的隔离** ——
**`施工单 §2.2` 的 B2 路径（`docker-compose.override.yml` + `-p rag-demo`）作废，走 B1（原目录直接 build+up）。**

⚠️ **没有解除的两条**（别读成"可以随便 up"）：
1. 🔴 **有评测在跑时仍不许 `docker compose up`** —— `rag-api-eval` 曾被 `agent-eval-gate` 使用。
   **判据**：`docker ps --format '{{.Names}}' | grep eval` **为空即安全**。
2. ⚠️ **独占 ≠ 内存变多** —— 本机 **8 GB**，Docker Desktop 只分到 **3.84 GB**。
   ⇒ `施工单 §4.2 档 1（fast 模式、不装重排序）` 那条判断**不变**。

### 🅱️ **后端先行 —— 先把后端全部完成并跑通，再进前端**

> 业务方原话：「分阶段做，**先把后端全部完成和跑通，再进入前端开发阶段**。」

⇒ **把 `施工单 ③` 里的【后端部分】抽出来先做完，再做页面。** 调整后的顺序：

```
✅ ② 本机验证跑通
🔵 后端全部完成        ← 本约束插入的阶段（原混在 ③ 里）
     硬门 A 的 Agent 端流式 · 硬门 C 的【服务端 cancel 传播】 ·
     硬门 D 的触发条件与续跑 · R1–R4 限额/熔断/结构化错误 · §8.2 eval 接入
⬜ 前端开发            ← 4 个页面 + 硬门 B 界面 + 停止按钮 + 接管队列 + R3.2 熔断提示卡片
⬜ ④ 测内存定机器 → ⑤ 买域名 → ⑥ 上云 → ⑦ 开隧道 → ⑧ 保护/自验/发链接
```

📌 **一条理由**（`施工单 §3.3` 自己标的）：硬门 C 标着「**最容易假完成**」，
**而它的难点全在后端**（"必须让上游模型的 HTTP 流也终止"）⇒ **先做后端 = 先啃最硬的骨头。**

⛔ **受此约束而【挂起】的一件事**：`permission.get_user_role()` 接 DB ——
它的真正落点是 **R1.3（限额必须对匿名生效）**，**属后端阶段**，等做 R1.3 时一并想
（`DEC-001` 已裁过它的更大版本，方案 A 被否）。

---

> ## 🔴 以下为【档案】（2026-09-15 时期）：`fastapi-rag-agent-TODO待办/归档/重构计划-2026-09-15.md`
>
> **开工前先读它。** 其余 M5 裁决工作**让位于它**。
>
> 它含一条**前提级更正**（与本文档下文若干处描述冲突，以它为准）：
>
> - 本机**能跑测试**（曾误判为"做不了运行期验证"）。但**不要借用** `ai-learning/venv` —— 它的 `fastapi 0.115.11` 与 `starlette 1.6.0` **不配对**，任何 `APIRouter(...)` 都建不起来
> - 正确做法：**在本仓自建隔离 venv** → `python3.10 -m venv venv && venv/bin/pip install -r api/requirements.txt`
> - 🔴 **2026-09-20 更新**：原文走的是 `api/requirements-test.txt`（剔重版，不含 torch 系）——
>   业务方裁决「**不用双 requirements.txt，这样会混**」⇒ **该文件已删，统一用 `api/requirements.txt`**。
>   代价：本机会拉 torch 系（GB 级）。⚠️ 若只想跑**离线测试**，本仓 `api/reranker.py:14` 是真懒加载、
>   **不碰 torch也能跑**（只有 `mode=accurate/full` 与 `rerank_search` 才需要）—— 但**依赖清单只有一份**，不要另建
> - ⇒ **"切模块"不是测试的前置条件**
> - 执行顺序：**基线 → 修 bug → 归档 → 切模块 → M6**
>
> 另两处登记：`ROADMAP.md`「当前指针」最上方 · `fastapi-rag-agent-TODO待办/归档/重构计划-2026-09-15.md` 正文

## 推送节奏(跨项目纪律)

> 📌 **2026-09-21 由业务方给定原文，**本仓与用户级 `~/.claude/CLAUDE.md` 各存一份**。
> **为什么本仓也要有**：用户级那份**不入库**，**克隆者 / 换机器看不到** —— 而本仓是 PUBLIC 仓。
> ⚠️ **两处的【核心段落逐字一致】；本仓版本额外多两段** ——
> 「📌 本节的来源」与文末的「本仓实测补充」。**那两段是本仓特有的，用户级那份没有。**
> ⇒ **同步规则**：改**核心段落**要两处一起改；**本仓特有的两段只在改本仓时动**
> （本仓在"两处真相"上吃过亏，所以这里把边界写清楚）。
> 📌 **本节的来源**：2026-09-21 一整个会话里 `git push` / `git fetch` **断了 4 轮**，
> 而 `gh api` / `gh pr create` **全程能通** —— 业务方据此写下了这条纪律。

- **本地 commit 随便攒**;**推送以「一个可验证单元」为界** —— 一个 PR 的活儿做完再推,
  **不是**每个 commit 都推。
- **为什么**:GitHub 连接不稳定,**频繁推送会断开**。实测会出现「`gh` 能建 PR、
  `git push` 推不上去」的假象 —— 那是**传输抖动**,不是权限/store/证书问题。
  **做法:重试 1–3 次即可,⛔ 不要去调 CA。**

### ⚠️  三条代价(别读成"可以不推")
1. **本地 = 不 durable** —— 机器丢/目录被重构成别样,工作就没了。**给"未推送"设上限:当天结束前至少推一次。**
2. **主干有分支保护** ⇒ 最终仍要走 PR;攒批省的是**推送 + PR 创建**的次数。
3. 一次失败**损失更多** —— 但 git 推送**按 ref 原子**,失败**不会写坏的中间态** ⇒ 重推即可。

### 两个配套判据(同族,别重犯)
- `git fetch` 失败时,`git merge --ff-only origin/main` 会报 **「Already up to date」—— 那是假的**
  (本地 `origin/main` ref 根本没更新)。**判据:读文件内容核对,别信那句提示。**
- 推送前**先 fetch**;fetch 失败**要重试**(本机实测失败过 2 次,重试第 1 次即通)。

> 📌 **本仓实测补充（2026-09-21）**：`git fetch` 挂掉时，**本地 `origin/main` ref 停在旧 commit** ⇒
> `git log origin/main` / `git checkout main` 的提示**都是基于旧 ref 的，会骗人**。
> **两条可用的替代判据**：
> ① `gh api repos/heweidong-ecco/fastapi-rag-agent/commits/main` —— **两条路是独立的，实测 git 挂了 gh 还能通**；
> ② `git rev-list --left-right --count main...origin/main` —— 但**它读的也是本地 ref**，所以只在 fetch 成功后才可信。
> ⇒ **最稳的做法：`gh pr view <n> --json state,mergeCommit` 回查**，别信 `gh pr merge` 的退出码
> （本仓有「**合并已成功却报错**」的前科）。

## 🔴 「判据」纪律 —— 六条（2026-09-21 起 · 出自复盘）

> **出处**：**`docs/复盘/2026-09-21-拿动作成功当结果正确.md`**（含三条错的完整经过与判据）。
> **为什么单独成一节**：那三条错的**根因是同一条** —— **拿「动作成功」当「结果正确」的判据**，
> 而**三条全都躲过了当时的自查**（脚本打印「替换了 10 处」/ 我"把内容写进去了" / `git commit` 退出码 0）。
> 📌 **这一族在本仓已栽过多次**（PR #48 · PR #51 · 两次 heredoc）⇒ **不是"下次注意"能解决的，
> 要的是"换个判据"** —— 所以写成这里。

### 一条根因：三种错判据 / 三种对判据

| 我用的判据（**错的**） | 应该用的判据 |
|---|---|
| 「脚本说**替换了 10 处**」 | **按位置核**：`grep -n` 逐处看**改的是哪一行** |
| 「我**把内容写进去了**」 | **跑一次语法检查**（`compileall` / 直接跑那个脚本） |
| 「`git commit`**退出码 0**」 | **`git status` + `git show --stat HEAD`** 看**实际装了什么** |

### 六条（下次直接照做）

1. ⭐ **改完必须"看结果"，不能只看"动作返回"**。
   —— 与 `verification-before-completion` 的「**evidence before assertions always**」是同一条。
   ⚠️ **本仓实测：那张 A 级必用表里列着它，而被违反的正是它** ⇒ **「列在表里」≠「会执行」**。
2. ⭐ **批量替换之后，按【位置】核一遍**（`grep -n` 看命中在哪几行）——
   ⛔ **别只数"替换了几处"**。**注释里也会出现同样的串**（PR #48 就是这么漏的：
   `replace(..., 1)` 命中了 `:283` 的注释，真正的调用点 `:472` 原样没变）。
3. ⭐ **写了代码 / 脚本，先跑一次再说话** —— 哪怕只是一行 `compileall`。
4. ⭐ **`git stash` / `pop` 会丢索引** ⇒ **提交前【必须】重看 `git status`**，
   确认每行是**暂存态**（`M `，第 1 列有字母）而不是**未暂存**（` M`，第 2 列）。
   （PR #51 就是这么丢的：`add -A` 之后 `stash pop` 把索引全撤了 ⇒ 5 个文件只提交了 1 个，
   **而 `git commit` 退出码仍然是 0**。）
5. ⭐ **PR 合并之后，核「内容真的在主干上」** —— `git show origin/main:<文件> | grep -c <特征串>`，
   ⛔ **不要只信 `gh pr view --json state`**（那只说明"**合并动作**完成了"，不说明内容进去了）。
6. **在 heredoc / 命令参数里写中文句子时**：**一律用「」『』，不用 ASCII 引号**；
   或者**写成临时文件再跑**（不拼字符串）。⚠️ **本仓实测犯过 3 次**，
   每次都是**字符串被提前截断** ⇒ **整段脚本没跑**，而人已经在心里当成"写好了"。

### 📌 触发面（**别读成"只在收尾时用"**）

复盘里那三条**全都发生在【改代码 / 写脚本的过程中】**，而**不在显而易见的"提交/收尾"时刻**。
⇒ **触发时机**：**任何批量编辑之后** · **任何"我写进去了"之后** · **任何 `git` 写操作之后**。

## ⚡ 用户级 skills · 必用表（**目录共 20 个 · 本表已定级 14 个**）

> 🔴 **2026-09-29 更正**：原标题写「用户级 · **14 个**」—— **目录里实际是 20 个**
> （`ls -d ~/.claude/skills/*/` 实测，**全部是真实目录、无 symlink**）。
> **本表列的 14 个只是其中一部分**，且**不全是 superpowers 的**
> （`agent-system-creator` / `gate-review` / `new-project-launch` / `留痕-checks` 是**自建**的）。
>
> ⬜ **表外还有 6 个，本表【未定级】**：
> `agent-system-creator` · `gate-review` · `grilling` · `new-project-launch` · `skill-creator` · `留痕-checks`
> （⚠️ **`留痕-checks` 虽未进表，但在下面被单独讨论** —— 它有本仓适配裁决，见 §冲突与例外）

> **用户指令（2026-09-17）**：「使用用户级中 superpowers 的 skills……**如果命中必须用**，
> 先写好，过程中我再动态调整。」
> **定位**：业务方 2026-09-17 裁决「**两份都留本仓**」—— 先在本仓试点，跑通再考虑提全局。
> **本表由体检定级**，依据见 `docs/skill-适配体检-2026-09-17.md`。

### ⛔ 第一条：**知道 skill 存在 ≠ 会用 skill**

每次会话我自动收到**所有 skill 的名字 + 一行描述**，但那**只是索引** ——
**只有调用 `Skill` 工具，正文才会进入上下文。没调用 = 这个 skill 等于不存在。**

> **实测佐证（本仓）**：此前 **8 个 PR 一次都没跑过 `/留痕-checks`**，而我每遍读 PR 纪律时
> 都"知道"它存在 —— 见 `docs/复盘/2026-09-16-八个PR跳过了留痕门.md`。**门挂在别处，就等于没有门。**

### A 级 · **命中必须用**（9 个 —— 与我们的工作流一致）

| 触发场景 | 必须用 | 原文判据 | 代价 |
|---|---|---|---|
| **任何 bug / 测试失败 / 异常行为**，提出修法之前 | `systematic-debugging` | before proposing fixes | ~10k |
| **实现任何功能或修 bug**，写实现代码之前 | `test-driven-development` | before writing implementation code | ~4k |
| **要说"做完了 / 修好了 / 过了"之前**，或提交 / 开 PR 之前 | `verification-before-completion` | **evidence before assertions always** | ~0.9k |
| 有 spec/需求要做多步任务，**动代码之前** | `writing-plans` | before touching code | ~2.2k |
| 已有书面计划要执行（带 review 检查点） | `executing-plans` | with review checkpoints | ~0.6k |
| 完成一个任务 / 大功能 / **合并之前** | `requesting-code-review` | | ~2.2k |
| **收到** code review 意见时（尤其看不懂或不认同的） | `receiving-code-review` | 要**技术较真与验证**，不是表演式认同、不是盲目照做 | ~1.6k |
| 实现完成、测试全过，要决定**怎么合入** | `finishing-a-development-branch` | | ~1.9k |
| **任何创造性工作之前**（加功能 / 建组件 / 改行为） | `brainstorming` | MUST use before any creative work | **~20k** ⚠️ |

> ⚠️ **`brainstorming` 是表里最贵的（≈20k tokens）** —— 它挂在"任何创造性工作之前"，
> 意味着**每个功能请求都会拉 20k**。本机上下文 1M，扛得住，但**要知道它是笔开销**。

### B 级 · `⬜ 待适配`（5 个 —— **它假设的工作流与我们不同**，用前先判）

| skill | 为什么待适配 | 我们的实际 |
|---|---|---|
| `using-git-worktrees` | 假设需要 worktree 隔离 | **在本仓直接干、一分支一 PR**；worktree 不是我们的模式 |
| `dispatching-parallel-agents` | 假设并行派发多 agent | **单人逐条确认** |
| `subagent-driven-development` | 假设用子 agent 执行计划 | 同上，且我们的规矩是「**改动等发话**」 |
| `writing-skills` | 假设常写 skill（且 **~26.8k**，表里最贵） | 极少写 |
| `using-superpowers` | ⚠️ **它的核心主张与本仓纪律冲突**（见下） | 只采纳它的「名字≠skill」，**不采纳"1% 就必须调用"** |

> ⚠️ **`using-superpowers` 的冲突点**（原文）：它要求「只要有 **1% 可能** skill 适用就**绝对必须**
> 调用」「**任何**回复或动作**之前**都要先调用 —— 包括提问、看代码、查文件」，还把
> 「这只是个小问题」「我先看一眼文件」全标成 **rationalizing**。
> **这与本仓「非必要的不要做」「改动等发话」正面冲突。**
> ✅ **好在它自己第 63 行写了**：`User instructions (CLAUDE.md …) take precedence over skills`
> ⇒ **以 CLAUDE.md 为准**，那条"1% 就必须调用"**不采纳**。

### 冲突与例外 —— **必须说出来，不许静默跳过**

1. **同场景命中多个** → 按上表**从上到下**依次执行。
   （例："修 bug" = `systematic-debugging` → `test-driven-development` → `verification-before-completion`）
2. **skill 与项目 `CLAUDE.md` / `ROADMAP.md` 冲突** → **以项目规矩为准**，并**写明冲突点**。
3. **skill 的判据在本仓对不上**（引用路径本仓没有）→ ⛔ **不许含糊通过**。
   有替代判据 → 标 `⬜ 待适配` 并**写明替代判据**；**没有 → 标 `⛔ 无法执行`，不当作通过**。
   规则见 `docs/规则草稿-规则必须绑定路径.md`。

> ⚠️ **已知不适配（2026-09-17 实测）**：`留痕-checks` 的 check 7 引用
> `contracts/tools-mcp` · `总纲.md` · `eval/README.md` · `eval/阈值.md` —— 这些路径**存在，
> 但相对另一个仓库** `agent-eval-gate`（**不是本仓**；本仓无 `eval/`，`ci.yml` 也无 eval 门）。
> **本仓 prompt 内联在 `.py` 里**，故它的**路径式**触发在本仓**永不命中**。

> 📌 **`/留痕-checks` 本仓适配（2026-09-17 业务方裁决）**：该 skill 查 8 项，本仓**只有 5 项适用**。
> **仍要调 skill，但只报那 5 项**，其余 3 项一行带过。
> **#7 用双判据（文件清单 + 内容兜底）**，且清单**可重生成**（第一版手写清单被当场证伪，只覆盖约 40%）。
> **细则与清单见 `ROADMAP.md` 的「PR 纪律」段** —— 此处不复制，避免两处真相。

## 项目概述

> 📌 **2026-09-29 改写**：原文是「基于 FastAPI、PostgreSQL+pgvector 和 Redis 构建的**生产级**
> RAG + Agent API 服务。使用阿里云百炼 DashScope 提供 Embedding（`text-embedding-v2`）
> **和 LLM（`qwen-turbo`、`qwen-plus`）**」—— 其中 **LLM 那半句已过时**（见下）。
> 业务方 2026-09-29 裁定：**分两段写，一段"它是什么"、一段"它现在到哪"**。

### 它是什么（技术实质）

基于 **FastAPI + PostgreSQL(pgvector) + Redis** 的 **RAG + Agent API 服务**。

| 环节 | 用什么 |
|---|---|
| **LLM** | 🔴 **DeepSeek** —— `LLM_MODEL_CHAT` / `LLM_API_KEY` / `LLM_BASE_URL` 三个键控制<br>（📌 由 `docs/decisions/DEC-017` 裁决「**LLM 换 DeepSeek**」；**业务方 2026-09-29 确认这是当前实况**） |
| **Embedding** | **阿里云百炼 DashScope `text-embedding-v2`**（1536 维）—— ⚠️ **与 LLM 不是同一家，别混** |
| **重排序** | 本地 `BAAI/bge-reranker-v2-m3` Cross-Encoder（**真懒加载**，见 `api/reranker.py:14`） |
| **向量存储** | PostgreSQL + **pgvector** |
| **缓存 / 限流 / 配额** | **Redis** |
| **Agent 框架** | **LangGraph**（+ LangChain） |
| **可观测** | Prometheus（代码级）+ Grafana（🔴 **手工配置，仓库无 provisioning**，见 `DEC-034` §遗留①） |

🔌 **对外接口：57 个端点**（`agent` 28 · `rag` 15 · `debug` 4 · `auth` 2 · 其余 8 组各 1）。
⛔ **这份文档【不列】接口清单** —— 手写的必然过期。**跑命令**：

```bash
bash scripts/list_endpoints.sh
```

### 它现在到哪（2026-09-29）

```
✅ ② 本机验证跑通          五条判据全过（5 容器 healthy + 能问答）
🔵 后端全部完成            ← 【当前阶段】硬门 A/C/D + R1–R4 限额熔断 + eval 接入
⬜ 前端开发                4 个页面 + 硬门 B 界面 + 停止按钮 + 接管队列 + R3.2 熔断卡片
⬜ ④ 测内存定机器 → ⑤ 买域名 → ⑥ 上云 → ⑦ 开隧道 → ⑧ 保护/自验/发链接
```

🎯 **目标**：**把它变成一个【能分享的链接】**（路线 C = 域名 + Cloudflare 隧道）。
🔴 **当前状态 / 进度 / 待办总账 ⇒ 一律以 `ROADMAP.md` 为准**（2026-09-29 起它是唯一权威）。

---

## ⭐ 目标 vs 实测 —— **本仓的一条纪律**

> 🔴 **不把【目标】写成【指标】。** 这份文档里凡是"性能/能力"的描述，都可能混着两类东西：
> **设计目标**（想达到）与 **实测结果**（达到了）。**不标清楚 = 对方点开就发现对不上。**

| 项 | 是目标还是实测 | 出处 |
|---|---|---|
| **P99 < 800ms** · **失败率 < 0.1%** · **10 并发不崩** | 🔴 **目标**（**从未实测**） | `README.md` 性能表 ← 出自 `归档/硬性指标终极核查清单.md`（**原系统**的验收清单，28 项**全未勾**） |
| **57 个端点** | ✅ **实测**（2026-09-29，从 `/openapi.json`） | `scripts/list_endpoints.sh` |
| **5 容器 healthy · 能问答 · 知识库 77 行** | ✅ **实测**（2026-09-29） | `ROADMAP.md` 阶段② |
| ~~「`/rag/stream_search` SSE 实现**带真中断**」~~ | ⚠️ **不成立** —— 只 `except CancelledError`（`api_v1_rag.py:676`），**不关上游 HTTP 流** | `后端补齐清单` **B2**（硬门 C · **最易假完成**） |
| ~~「停止按钮会将已生成的部分内容保存为对话历史」~~ | ⚠️ **不成立** —— **全仓无前端、无停止按钮**；代码里**没找到**落库逻辑 | `后端补齐清单` **B3**（⬜ 待核） |
| **四层限额** | 🔴 **缺 2 层半**（单次半 · 单会话缺 · 全局日级缺） | `ROADMAP.md` 功能现状表 |
| **熔断** | 🔴 **完全没有** | 同上下 |
| **引用溯源 / 人工接管 / 前端** | 🟡 后端部分有 · **界面全无** | 同上下 |

> 📌 **本仓已经吃过这个亏**：`README.md` 的性能表**没标"这是目标"**，
> 而压测基线**跑在坏环境上**（77–97% 错误率，见 `施工单 §8` 第 4 条）。
> ⇒ **要引用那几个数，先说明它是目标。**
>
> 🔴 **要当前状态 ⇒ 看 `ROADMAP.md` 的「功能现状表」** —— 那份是**逐条核过代码**的。

## 常用命令

```bash
# 完整生产环境启动（API + Postgres + Redis + Prometheus + Grafana）
docker compose up -d

# 本地开发：DB/Redis 用 Docker 启动，API 本地热重载运行
bash dev.sh
# 或手动执行：
cd api && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 运行全部测试（需要依赖已安装 + Postgres/Redis 已启动）
cd api && pytest -v

# 运行单个测试文件
cd api && pytest test_auth.py -v

# 数据库迁移（在 api/ 目录下执行，注意 env.py 会用 config 里的连接串覆盖 alembic.ini）
cd api && alembic upgrade head
cd api && alembic revision --autogenerate -m "描述信息"

# 性能压测
locust -f locustfile_hybrid.py
```

## 架构

### 入口与中间件链

`api/main.py` 创建 FastAPI 应用，并按以下顺序挂载中间件：

1. **HTTP 日志 + Prometheus 指标** — 每个请求生成唯一 `request_id`（ContextVar 实现，线程安全），记录 method/path/status/duration，通过 `metrics.py` 采集指标
2. **RateLimitMiddleware（限流）** — 两层令牌桶：全局（100次/秒，容量150）→ 用户级（3次/秒，容量20）。使用 Redis Lua 脚本保证原子性
   > 🔴 **2026-09-29 更正（跳过名单）**：原文写 `/auth/login` · `/auth/refresh` · `/admin/create_user` ——
   > ⚠️ **缺 `/api/v1` 前缀**。**这正是 2026-09-16 修过的那个 bug**（三个 router 都带前缀 ⇒ 名单对不上 ⇒ 等于没跳过），
   > 而 CLAUDE.md 一直在用**修前的旧写法**。
   > ✅ **实际名单是 `api/main.py:107-111` 的 `PUBLIC_PATHS`，共 11 条**：
   > `/` · `/docs` · `/redoc` · `/docs/oauth2-redirect` · `/openapi.json` · `/health` · `/ready` · `/metrics` ·
   > **`/api/v1/auth/login`** · **`/api/v1/auth/refresh`** · **`/api/v1/admin/create_user`**
   > （📌 **两个中间件共用它** —— `main.py:120` 与 `:202`）
3. **QuotaMiddleware（配额）** — 按角色限制每日调用次数（免费 100次/天 · 付费 10000次/天 · 管理员不限，出处 `api/permission.py:11-15`）。通过 X-API-Key 或 Bearer JWT 识别身份
   > 🔴 **必知**：`api/main.py:222` 是 `if user_name:`，**没有 `else` 分支** ⇒
   > **匿名请求直接落到 `:262` 放行，完全绕过配额**。⇒ 这正是**硬门 R1.3「限额必须对匿名生效」**要修的（见 `ROADMAP.md`）
4. **TextNormalizationMiddleware（文本规范化）** — 自动将请求体中的全角字符转为半角，跳过 URL、Token 等非自然语言字段

> ⚠️ **中间件异常处理要点**：FastAPI 的 `@app.exception_handler(AppException)` 只捕获路由层抛出的异常。**在中间件 dispatch 中抛出的 `AppException` 不会被该处理器捕获**，会落到通用 `Exception` 处理器返回 500。因此中间件拒绝请求时必须直接返回 `JSONResponse`（限流/配额中间件均如此实现）。

### 路由结构

三个路由模块均挂载在 `/api/v1` 前缀下：

> 🔴 **2026-09-29 更正**：原文写 `/rag/stream_search` 是「SSE 实现**带真中断**」—— **不成立**（见 §「关键开发模式」的 SSE 条）。
> 且**漏了 6 条端点**（下表已补）。⛔ **完整清单别照这张表 —— 跑 `scripts/list_endpoints.sh`。**

| 文件 | 职责 |
|------|------|
| `api/api_v1.py` | 公开接口（`/`）、认证（`/api/v1/auth/login`、`/api/v1/auth/refresh`）、管理员建用户、调试接口（**含 `POST /rag/benchmark-embedding`** —— 它**在这个文件里，不在 `api_v1_rag.py`**）、`/api/v1/users/{user_id}`、`/api/v1/tool/benchmark` |
| `api/api_v1_rag.py` | **15 条**：文档管理（`/rag/insert` · `/rag/insert_batch` · `/rag/upload_document` · **`DELETE /rag/documents/{doc_id}`**）、检索（`/rag/pg_search` · `/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search` · **`/rag/jwt_ask`**）、流式生成（`/rag/stream_search`，**SSE，但无"真中断"**）、**`/rag/ask`**（`tags=["模拟类测试"]`，按 `requested_by` 过滤的真检索，**无 `answer` 字段**）、**`/rag/async_ask`** 与 **`/rag/parallel_ask`**（⚠️ **两者是模拟**，返回假文档）、WebSocket（`/api/v1/ws/agent` · `/api/v1/ws/test`） |
| `api/api_v1_agent.py` | **28 条**：LangGraph Agent 对话、人工审批（`/agent/approve`）、多分支路由高级 Agent、Plan-Execute、长期记忆（Mem0）、浏览器工具（Playwright）、Python 代码执行器、MCP Client 对话、MCP 工具列表、工具健康检查、Token 预算与成本看板、执行轨迹可视化 |

> ⚠️ **两条 WebSocket 不在 OpenAPI 里**（OpenAPI 规范不支持 WS）⇒ `list_endpoints.sh` 的 57 条**不含它们**。
> 判据：`curl -i -H "Upgrade: websocket" ... /api/v1/ws/agent` → **101 Switching Protocols**（实测）。

### RAG 检索管线（`api/rag_pipeline.py`）

> 🔴 **2026-09-29 更正**：原文写「支持**三种**检索模式（fast / accurate / full）」—— **实际 4 种**，
> 而且把 `fast` 描述成「**仅**向量检索」**也是错的**（它**含 BM25**）。

`RAGPipeline` 类由**可独立开关的环节**组合而成。**实际 4 种模式**
（枚举与工厂在 **`api/api_v1_rag.py:467-476`**，**不在 `rag_pipeline.py`**）：

| mode | 查询改写 | 查询扩展 | **BM25** | Cross-Encoder 重排序 | 依赖 torch |
|---|:--:|:--:|:--:|:--:|:--:|
| **`fast`** | ✗ | ✗ | **✅** | ✗ | ✗ |
| **`accurate`** | ✅ | ✗ | ✅ | ✅ | ⚠️ **是** |
| **`accurate_norerank`** ⭐ **默认值** | ✅ | ✗ | ✅ | ✗ | ✗ |
| **`full`** | ✅ | ✅ | ✅ | ✅ | ⚠️ **是** |

- ⭐ **`accurate_norerank` 是默认值**（`api/api_v1_rag.py:482`）—— **不依赖 torch**，所以本机在
  **镜像里没装 torch 系**（`DEC-034` 构建期裁掉）的情况下**仍能跑**。
- ⛔ **`mode` 是受限枚举**：传别的值（如 `fst`）会得到 **422**，**不会被静默兜底**
  （2026-09-17 修，见 `docs/decisions/DEC-013`）。
- ⚠️ **`fast` 不是"只查向量"** —— 它走 **BM25 + 向量 + RRF 融合**，只是不做改写/扩展/重排序。

管线中的关键模块：

管线中的关键模块：
- `query_rewriter.py` — 基于 LLM 的查询扩展（生成多个变体）和上下文感知改写（指代消解、口语转书面语）。结果缓存在 Redis（1小时 TTL）
- `hybrid_search.py` — 使用 RRF（Reciprocal Rank Fusion，k=60）算法融合稠密向量检索和稀疏 BM25 关键词检索两路结果
- `reranker.py` — 懒加载 `BAAI/bge-reranker-v2-m3` CrossEncoder 模型，对候选文档进行精细排序
- `answer_with_citations.py` — 生成带 `[1]` 行内引用标记的 LLM 答案，支持溯源到原始文档块

### Agent 系统（LangGraph）

> 🔴 **2026-09-29 更正**：原文写「**三个** Agent 实现」—— **实际 6 套**（5 套图/Executor + 1 套 Plan-Execute）。
> 原文**漏了 `agent_checkpointer.py`（挂 `/agent/memory_chat`）、`/ws/agent` 的内联 Executor、
> 以及 `plan_execute.py`（它被误归到下面"配套基础设施"里，但它自己就是一个挂在 `/agent/plan_execute` 上的独立实现）**。

**共 6 套，都挂在线上**（`docs/CODE_INVENTORY.md` §2 说的「4 套」**也低估了** —— 它自己的表里就有 5 行，且未计 `plan_execute`）：

| # | 文件 | 路由 | 是什么 |
|---|---|---|---|
| 1 | `agent_graph.py` | `/agent/langgraph_chat` · `/agent/approve` | **基础 Agent**：LLM 决策 → 工具循环（**DuckDuckGo** 搜索、计算器、日期）。带人工审批 `interrupt_before=["approval"]` |
| 2 | **`agent_checkpointer.py`** | **`/agent/memory_chat`** | **检查点版**：`build_checkpointer_agent()`，状态持久化（MemorySaver / SqliteSaver） |
| 3 | `agent_graph_advanced.py` | `/agent/mcp_chat` | **MCP Client 版**：MCP 协议动态调工具（会话池）、Mem0 记忆注入、多级 Token 预算、工具缓存。全局实例 `mcp_agent` |
| 4 | `agent_graph_advanced_learning.py` | `/agent/advanced_chat` | **意图分类路由版**：supervisor（SEARCH/CALCULATOR/DATE/TRANSLATE/REACT）→ 专用子图。⚠️ 原名 `…learning1.0.0.py`，**含点号无法导入**，已重命名 |
| 5 | **`api_v1_rag.py` 内联** | **`/api/v1/ws/agent`** | **WebSocket 版**：`create_tool_calling_agent` + `AgentExecutor`（`api_v1_rag.py:714`）。**也是 DuckDuckGo** |
| 6 | **`plan_execute.py`** | **`/agent/plan_execute`** | **Plan-and-Execute**：非 LangGraph 图，含动态重规划与质量检查 |

> 🔴 **哪一套是"产品版本"—— 【未裁】**，属 **M5 的代际收敛**（留 / 并 / 删）。
> `CODE_INVENTORY` §7 明写「**2 代与 3 代 Agent 的先后顺序从代码判不出**」⇒ **只能业务方定**。
> ⇒ 在那之前，**6 套并存是现状，不是 bug**。

#### ⚠️ 搜索工具目前是**两代并存**（别读成"全仓已换真抓取"）

- **新**：`api/search_tools.py` 的 `web_search`（**真抓取** `cn.bing.com` 解析）—— 由 `DEC-028` 引入。
  **只接在 2 处**：MCP 注册表（`api/mcp_server.py`）与 `agent_graph_advanced_learning.py`。
- **旧**：**DuckDuckGo 仍残留在 3 个文件** —— `agent_graph.py:43` · `agent_checkpointer.py:43` · `api_v1_rag.py:736`（`/ws/agent`）。
  ⚠️ **而本机实测 `duckduckgo.com` 网络不通**（`search_tools.py:48` 注释记着）⇒ **那 3 条链上的搜索会失败**。

Agent 配套基础设施：
- `agent_checkpointer.py` — 基于 MemorySaver（默认）/ SqliteSaver（`AGENT_CHECKPOINT_BACKEND=sqlite`）的检查点持久化，保证对话连续性
- `plan_execute.py` — Plan-and-Execute 模式，适用于复杂多步任务（含动态重规划、质量检查）
- `memory_store.py` — Mem0 集成（本地 qdrant 模式），提供长期用户记忆
- `browser_tools.py` — 基于 Playwright 的网页抓取和截图
- `code_executor.py` — 沙箱化 Python 代码执行（白名单内置函数/模块 + 时间/输出限制）
- `mcp_server.py` / `mcp_tool_factory.py` — MCP（模型上下文协议）Server，用工厂函数自动从 `@tool` 函数注册工具定义与处理器
- `tool_health.py` — 通过 MCP 动态探测工具健康状态，自动降级
- `tool_visualizer.py` — 记录 Agent 工具调用轨迹（`/agent/trace/{thread_id}`）
- `token_tracker.py` — Token 用量/成本追踪、预算控制、月度报告（所有查询走数据库）

### 数据层

- **PostgreSQL + pgvector**：存储文档及其向量（1536维）。表结构在应用启动时通过 `db.py:create_table()` 自动创建。使用 psycopg2 `ThreadedConnectionPool` 连接池（默认最小2，最大30连接，`.env` 中 `DB_MIN_CONN`/`DB_MAX_CONN` 可调）
- **`get_db()` 上下文管理器**：始终从连接池获取连接，成功时 `commit()`，异常时 `rollback()`，最终 `putconn()` 归还。禁止直接创建原始连接（历史上曾出现重复定义 `get_db()` 覆盖连接池版本的 bug，已修复）
- **Redis**：承担三种职责 —（1）Embedding 缓存（MD5 键名，24小时 TTL，`emb:*` 前缀），（2）用户对话历史（24小时 TTL，保留最近5轮），（3）限流/配额计数器（Lua 脚本保证原子操作）
- **Alembic**：数据库迁移工具，配置在 `api/alembic/`。`env.py` 会用 `config.py` 中的连接串**覆盖** `alembic.ini` 里硬编码的 `sqlalchemy.url`，无需手动改 ini

### 认证与授权

双认证体系（`deps.py`）：
- **X-API-Key 请求头**：API Key 的 SHA256 哈希值存储在 `api_keys` 表中，含过期时间。通过 `auth.py:verify_api_key()` 验证
- **JWT Bearer Token**：短期令牌（access token，15分钟有效）+ 长期令牌（refresh token，7天有效）。使用 HS256 算法，密钥为 `JWT_SECRET_KEY`
- **混合认证**（`get_current_user_hybrid`）：优先尝试 API Key，无则回退到 JWT。注意 `HTTPBearer` 使用 `auto_error=False`——若为默认的 `True`，缺少 Authorization 头时会在依赖解析阶段直接抛 403，导致纯 API Key 认证全部失效
- **角色体系**（`permission.py`）：三级权限——`free`（免费，100次/天）、`premium`（付费，10000次/天）、`admin`（管理员，不限）。当前角色映射硬编码在 `get_user_role()` 中

### 配置管理

`api/config.py` 集中管理所有环境变量。敏感配置项（`DASHSCOPE_API_KEY`、`POSTGRES_PASSWORD`、`JWT_SECRET_KEY`）不设默认值——启动时 `validate_config()` 检测到缺失会拒绝启动。

**主机地址约定**：`.env` 中 `POSTGRES_HOST`/`REDIS_HOST` 填 **Docker 服务名**（`postgres`/`redis`）；本地开发时 `config.py` 会根据 `IS_DOCKER` 标志（`DOCKER_ENV` 环境变量）自动覆盖为 `localhost`。所有需要 Redis 连接的模块都应从 `config.py` 导入 `REDIS_HOST`/`REDIS_PORT`（不要直接用 `os.getenv` 读取，否则本地/Docker 切换会不一致）。

### 可观测性

- **日志**（`logger_config.py`）：Loguru 三通道输出——彩色控制台（DEBUG 级别）、按日滚动的文件日志（INFO 级别，保留30天）、错误日志单独存储（ERROR 级别，保留90天）。每条日志通过 `logger.bind(request_id=...)` 携带请求ID
- **指标**（`metrics.py`）：Prometheus 计数器/直方图/仪表盘，暴露在 `GET /metrics`
- **健康检查**：`/health`（检测数据库 + Redis 连通性）、`/ready`（Kubernetes 就绪探针，启动后10秒才开始响应就绪）
- **Token 追踪**（`token_tracker.py`）：按用户/用途/会话维度追踪 Token 用量和成本，持久化到数据库。预算消耗达 80% 时发出预警
- **成本看板**（`cost_dashboard.py`）：Gradio 可视化面板，挂载在 `/dashboard`

### 关键开发模式

- **错误处理**：所有业务错误统一使用 `AppException(ErrorCode, message)` 抛出。`ErrorCode` 枚举值与 HTTP 状态码的映射保存在 `ERROR_CODE_TO_HTTP_STATUS`。全局异常处理器同时捕获 `AppException` 和未处理的 `Exception`。⚠️ 中间件中不要抛 `AppException`（见上），直接返回 `JSONResponse`
- **数据库访问**：始终使用 `get_db()` 上下文管理器——自动从连接池获取连接，成功时提交，异常时回滚，最终归还连接。禁止直接创建原始连接
- **缓存策略**：Embedding 调用统一走 `embedding_client.get_embedding()`，内部先查 Redis 缓存再调 API。启动时 `warmup_cache()` 预热10个热点查询的 Embedding。查询改写结果同样在 Redis 中缓存
- **SSE 流式输出** —— ⚠️ **2026-09-29 更正，原文两处不成立**：
  > 原写「答案可通过 SSE 流式返回，**支持真中断**（**停止按钮**会将已生成的部分内容保存为对话历史）」。
  >
  > | 原说法 | 实测 |
  > |---|---|
  > | 「支持真中断」 | ❌ **不成立**。全仓**唯一**的中断处理是 `api/api_v1_rag.py:676` 的 `except asyncio.CancelledError` ⇒ 只有 `print` + `yield [DONE]`。**全仓无 `is_disconnected` / `aclose`** ⇒ **不关上游 LLM 的 HTTP 流** |
  > | 「停止按钮保存部分内容」 | ❌ **不成立**。**全仓无前端、无停止按钮**（`api/static/` 只有 3 个调试测试页）。⚠️ **更细一层**：`append_chat_history` 两行（`:670` / `:672`）**在 `try` 内、流跑完之后** ⇒ **中断路径根本走不到它们** |
  >
  > ✅ **能成立的部分**：SSE 本身是**真的**（`StreamingResponse` + `text/event-stream`，`api_v1_rag.py:687`），逐字返回已验证。
  > ✅ **正常跑完**的轮次**确实**会写对话历史（Redis，24h）。
  > 🔴 **这属硬门 C，本仓自标「最容易假完成」** ⇒ 见 `后端补齐清单` **B2 / B3**
- **文档处理管道**：`document_preprocessor.py`（文本规范化）→ `document_parser.py`（解析 PDF/Word/Markdown/HTML）→ `chunker.py`（按文档类型选择分块策略）→ `embedding_client.py`（向量化）→ 入库
- **模型命名约定** —— ⚠️ **2026-09-29 重写**（原文写「DashScope 模型名必须用 `qwen-turbo`/`qwen-plus`/`text-embedding-v2`」，**已过时**）：
  > | 用途 | 现状 |
  > |---|---|
  > | **生成 / 对话 LLM** | 🔴 **不再固定** —— 由 `LLM_MODEL_FAST` / `LLM_MODEL_CHAT` 决定。<br>代码默认值仍是 `qwen-turbo`/`qwen-plus`（`api/config.py:54-55`），**但本机 `.env` 已覆盖成 `deepseek-v4-flash`**（`LLM_BASE_URL=https://api.deepseek.com`） |
  > | **Embedding** | ✅ **固定 `text-embedding-v2`（DashScope）—— 不得改动**<br>（`api/embedding_client.py:15` 是**唯一真正的调用点**） |
  > | ⛔ 禁用 | `qwen3.7-plus` —— **DashScope 无此模型**，调用会报错。**历史误写已全部修正**（全仓仅剩 1 条注释，`api/plan_execute.py:462`） |
  >
  > 🔴 **两条【已知不一致】，改代码时留意**（**是代码问题，不是文档问题**）：
  > 1. `api/agent_checkpointer.py:58` · `api/agent_graph_advanced.py:316` · `:364` 三处
  >    `record_usage(model="qwen-turbo")` —— **与实际调用的 DeepSeek 模型不符**
  > 2. `api/token_tracker.py:48-52` 的 `PRICING` 表**没有 DeepSeek 条目** ⇒ 走兜底单价（qwen-turbo 价）
  >    ⇒ **金额口径不准**（⚠️ **Token 口径不受影响**，所以 80% 预警仍然准）

## 本次复审修复记录（2026-08-17）

以下为全面复审时发现并修复的问题，涉及**启动崩溃 / 运行崩溃 / 认证失效 / 数据丢失**：

1. **`api_v1_agent.py` 导入崩溃**：`from agent_graph_advanced import build_advanced_agent` 指向不存在的函数（该函数在 learning 文件中）。已将 `agent_graph_advanced_learning1.0.0.py` 重命名为 `agent_graph_advanced_learning.py`（原名含点号无法导入），并修正导入。同时清理了该文件内大量重复的 import 语句
2. **`agent_checkpointer.py` 空图编译**：`build_checkpointer_agent()` 只写了"添加节点和边的代码保持不变"注释，实际没加节点/边，编译空图在导入时报错。已补全 agent→tools→agent 的完整接线
3. **`token_tracker.py` NameError**：`record_usage()` 在构造 `TokenUsage` 时使用尚未赋值的 `cost`（`cost=cost`），每次调用必崩。已把成本计算移到构造之前
4. **`hybrid_search.py` 元组解包崩溃**：`reciprocal_rank_fusion` 按 3 元组解包 `(content, source, similarity)`，但 `db.search_similar` 实际返回 4 列 `(id, content, source, similarity)`，必抛 `ValueError`。已改为 4 元组并补 `id` 字段
5. **`tool_health.py` 启动崩溃**：在 async 的 `startup_event` 中调用 `asyncio.run()` 会抛 `RuntimeError`。已把 `update_tool_health`/`run_health_check` 改为 async，并同步更新 `main.py`、`api_v1_agent.py` 中的调用点为 `await`
6. **`deps.py` 认证失效**：`HTTPBearer()` 默认 `auto_error=True`，缺少 Authorization 头时纯 API Key 请求在依赖解析阶段被 403 拦截。已改为 `auto_error=False`，并为 `get_current_user_jwt` 补 None 分支
7. **`db.py` 数据丢失**：`get_db()` 被重复定义，后定义的简单连接版本覆盖了连接池版本，导致写入不提交（CLAUDE.md 描述的连接池/自动提交实际失效）。已删除重复定义，保留连接池版，并修正 `DB_CONFIG` 的硬编码 `user`
8. **错误模型名 `qwen3.7-plus`**：出现在 `agent_graph_advanced.py`、`agent_graph_advanced_learning.py`、`search_tools.py`、`api_v1_rag.py`（流式 + WebSocket）、`plan_execute.py`，全部改为 `qwen-plus`
9. **`agent_graph_advanced.py` 轨迹误报**：工具调用成功后仍记录"未找到工具"错误轨迹。已改为成功状态
10. **`api_v1_rag.py` SQL 参数颠倒**：`/rag/ask` 中 `WHERE requested_by = %s LIMIT %s` 传参为 `(req.top_k, user_name)`，LIMIT 收到用户名必报错。已交换为 `(user_name, req.top_k)`
11. **`api_v1_rag.py` WebSocket Agent 调用错误**：`create_tool_calling_agent` 的输入键应为 `input`、输出键为 `output`，原代码用 `messages` 导致 KeyError。已改为 `agent_executor.ainvoke({"input": ...})` 并读取 `result["output"]`
12. **`main.py` 限流返回 500**：中间件中 `raise AppException` 不会被 `@app.exception_handler(AppException)` 捕获，限流时返回 500 而非 429。已改为直接返回 429 `JSONResponse`；同时将 `/auth/login`、`/auth/refresh` 加入限流跳过名单（与配额中间件一致）
13. **`rag_pipeline.py` 失效过滤**：`SIMILARITY_THRESHOLD=0.7` 对 RRF 分数不成立（RRF 分数约 1/(k+rank)，k=60 时远小于 0.7），导致过滤逻辑形同虚设/误导。已改为仅重排序启用时按 `rerank_score >= 0` 过滤
14. **依赖缺失**：`requirements.txt` 缺少 `gradio`（`main.py` 挂载面板必需）、`sqlalchemy`（`db.py` 元数据定义必需）、`numpy`、`datasets`，已补充
15. **Redis 主机不一致**：`query_rewriter.py`、`agent_graph_advanced.py` 直接用 `os.getenv("REDIS_HOST", "redis")` 读取，本地开发会连错地址。已改为从 `config.py` 导入；`.env`/`.env.example` 的 `POSTGRES_HOST`/`REDIS_HOST` 统一改为 Docker 服务名
16. **`.gitignore` 补充**：新增 `.pytest_cache/`、`.mem0/`、`screenshots/`、`*.db`（运行期产物不入库）

### 实时环境测试补充修复（2026-08-17，在 venv + Docker 实机验证时发现）

17. **`code_executor.py` @tool docstring 位置错误**：`execute_python` 的 docstring 写在可执行代码之后（不再是 `__doc__`），langchain `@tool` 装饰器运行时报 `ValueError: Function must have a docstring`。已移到函数第一行
18. **`document_preprocessor.py` 正则损坏**：`remove_noise_markers` 中硬编码正则 `r'!\\[...'`（raw string 双重转义）导致 `re.error: unbalanced parenthesis`，文档上传（`process()`）必崩。已改为单层转义
19. **`memory_store.py` 适配 mem0>=2.0**：mem0 2.x 的 `Memory.__init__` 不再接受 dict 配置，改用 `Memory.from_config(dict)`
20. **`reranker.py` 真·懒加载**：原代码在模块顶层 `from sentence_transformers import CrossEncoder`，违背"懒加载"承诺，导致缺少该依赖时应用整体无法启动。已移入 `get_reranker()` 内部延迟导入
21. **限流/配额中间件豁免健康检查**：`/health`、`/ready`、`/metrics` 此前会被计入限流/配额，K8s/Docker 健康探针可能收到 429 被误判为不健康。已加入两个中间件的跳过名单
22. **限流按 JWT 用户分桶**：`RateLimitMiddleware` 之前只按 X-API-Key 分桶，JWT 用户全部挤在 `anonymous` 桶（3次/秒共享）。已支持从 Bearer Token 解析用户名，每用户独立桶
23. **`test_plan_constraints.py` 加 `@pytest.mark.skip`**：该文件是手动实验脚本（需必填参数），现标记 skip，`pytest` 套件干净通过
24. **`logger_config.py` 日志 KeyError**：日志格式引用 `{extra[request_id]}`，但未绑定 `request_id` 的日志（如启动日志）格式化时报 `KeyError`。已用 `logger.configure(extra={"request_id": "no-id"})` 提供默认值

### 已知遗留问题 / 环境注意

- **DashScope 现在只承担 Embedding** —— 🔴 **2026-09-29 更正**：原文写「**chat 模型（qwen-turbo/qwen-plus）免费额度已耗尽**，调用 LLM 的功能会返回 403」——
  ⚠️ **这条对当前路径已不适用**：LLM 已切 **DeepSeek**（`DEC-017` §二 第 2 条：「✅ 换 DeepSeek · **实测真调通**」）⇒ **聊天不再打 DashScope chat 配额**。
  ✅ **但仍有一条残留依赖**：`DASHSCOPE_API_KEY` **是启动必需项**（`api/config.py:39` + `validate_config()` 缺则拒启）——
  因为 **Embedding 仍走 DashScope**。⚠️ `DEC-017` §二 第 3 条注明：「**剩余额度 API 不提供，测不出来**」⇒ **embedding 额度不足会打挂 `get_embedding()`，且事前看不见**。
- **venv 环境** —— 🔴 **2026-09-29 更正**：原文写「测试专用 venv（**在本仓库之外**）」—— **错**。
  **本仓根目录下就有两个**（**已被 `.gitignore` 排除、不入库**）：
  `venv/`（产品用，`.gitignore:5`）· `venv-ragas/`（评估用，`.gitignore:13`）。
  其中已将 `transformers` 降级 4.44.2、`numpy` 降级 1.26.4，以兼容 torch 2.2.2（重排序依赖）。
  ⚠️ 该 venv 还有 gradio/starlette、langchain-chroma/langchain-core 的版本冲突警告，属既有问题，不影响运行。
- **重排序模型**：`BAAI/bge-reranker-v2-m3` 约 2.3GB（**模型名硬编码在 `api/reranker.py:17`**），首次调用 `rerank_search` 或 `accurate`/`full` 管线时自动下载（**真懒加载**），需要网络。
  ⚠️ **而镜像里【没装】torch 系** ⇒ **容器里跑不了重排序**，只有开发机可以。
  🔴 **2026-09-29 更正（我原先写错了）**：原文写「**`api/requirements.txt` 已裁掉 torch 系**」—— **错**。
  ✅ **事实**：`api/requirements.txt` **一个字没动** —— 那 5 个包**都还在**。
  **真正发生的是**：`api/Dockerfile:73` 在**构建期**用
  `grep -vE '^(sentence-transformers|transformers|locust|ragas|datasets)' requirements.txt > /tmp/req-light.txt`
  **过滤掉再装** ⇒ **仓里仍只有一份清单，镜像里少 5 个包**（`DEC-034` 决策二的原文就是这么写的）。
  ⇒ **要在本机跑重排序，`pip install -r api/requirements.txt` 是够的**（它含那 5 个）；**容器里才没有**。
  ⚠️ 顺带：`.env.example` 里有个 `RERANKER_MODEL_NAME` 键，**全仓零引用**（**死键**，别被它误导）。

### 🔴 2026-09-29 核查新发现（原文档没有）

| # | 发现 | 位置 |
|---|---|---|
| 1 | **`PRICING` 表没有 DeepSeek 条目** ⇒ 成本金额走 qwen-turbo 兜底单价 ⇒ **金额口径不准**（Token 口径不受影响） | `api/token_tracker.py:48-52` |
| 2 | **三处 `record_usage(model="qwen-turbo")` 与实际调用的模型不符** | `api/agent_checkpointer.py:58` · `api/agent_graph_advanced.py:316` · `:364` |
| 3 | **80% 预算预警是"拉取式"** —— 只在 `POST /agent/mcp_chat` 的响应体 `budget_warning` 字段里出现，**不推送、不落告警表**；`/rag/*`、`/agent/langgraph_chat`、`/ws/agent` **拿不到预警** | `api/token_tracker.py:721-742`；唯一调用点 `api/api_v1_agent.py:483` |
| 4 | **`.env.example` 里的 `RERANKER_MODEL_NAME` 是死键**（全仓零引用） | `.env.example` |
| 5 | **两条 WebSocket 不在 OpenAPI 里** ⇒ `scripts/list_endpoints.sh` 的 57 条**不含** `/api/v1/ws/agent` · `/api/v1/ws/test` | `api/api_v1_rag.py:773` · `:818` |
- ~~`api/logger_config.py` 第 44 行之后有一段约 70 行的 SLS 远程日志参考文档以 `'''...'''` 字符串形式内嵌~~ ⚠️ **2026-09-20 实测更正：这条不存在** —— `logger_config.py` **只有 45 行**，且 `SLS` 在该文件里出现 **0 次**。**不要去找那段 SLS**。
- `agent_graph_advanced.py`、`mcp_server.py` 等文件内有多处 `'''...'''` 注释掉的旧实现，属学习保留内容，不影响运行
