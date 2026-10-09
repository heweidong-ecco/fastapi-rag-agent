# 给 Agent 的测试与调试指南

> **读者是「另一个 Agent」**（或第一次接手这个仓库的人）。
> 目标：**拿这份文档就能把本仓跑起来、测起来、并在出问题时自己定位** —— 不用问人。
>
> 📌 本文件里的**每条命令与输出都是 2026-09-20 在本机实测过的**。
> 凡写「实测」的，就是真跑过的原文；凡没把握的，会写「未验证」。

---

## 0 · 三十秒判断"现在能不能跑"

```bash
cd <repo>                                   # 仓库根
docker ps --format '{{.Names}}\t{{.Status}}' | head    # ① DB/Redis 在不在
curl -s -m 5 localhost:8000/health                      # ② API 在不在
ls venv/bin/python && venv/bin/python -V               # ③ 有没有可用的 venv
```

| 现象 | 含义 | 处置 |
|---|---|---|
| ①② 都有响应 | **已经在跑** ⇒ 直接测 | 跳到 §3 |
| ① 空 | DB/Redis 没跑 | `docker start postgres-rag redis-rag`（⚠️ 先用 `docker ps` 确认这两个容器**是不是本仓的**，见 §1①） |
| ③ 不存在 | 没建环境 | 见 §1 |

---

## 1 · 把环境跑起来

> 🔴 **2026-09-20 方向更正**：本节此前与 `README.md` 一起被拆成"两条路径"（轻量 / Docker 全量），
> 标题还写着「**不构建镜像**」。**已收敛** —— **交付路径只有一条：`docker compose up -d`**。
> 本节下面那条是 **Agent 要跑测试时的"开发路径"**（本机 venv + 本机 uvicorn），与交付路径不是一回事。

> ⚠️ **本节的定位**：你来测这个仓 —— 要么用**交付路径**（`docker compose up -d`，见 `README.md`），
> 要么用下面的**开发路径**（要改代码 / 跑 `pytest` 时）。**别把开发路径当成交付路径验证。**

```bash
# ① DB + Redis —— ⚠️ 先判断它们是不是本仓的（见下）
docker ps --format '{{.Names}}' | grep -E 'postgres-rag|redis-rag' \
  && docker start postgres-rag redis-rag \
  || docker compose up -d postgres redis

# ② 依赖（清单只有一份：app/requirements.txt）
python3.10 -m venv venv
venv/bin/pip install -r app/requirements.txt

# ③ 环境变量
cp .env.example .env                                    # 然后填【四项】必填（见下）

# ④ 起服务
cd app && ENABLE_DASHBOARD=false ../venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

> 🔴 **①为什么要先判断（2026-09-20 实测）**：`docker compose up` 按 **compose 项目**工作，
> 而容器可能**不属于本项目**。实测本机 `postgres-rag`/`redis-rag` 的
> `com.docker.compose.project` 是 **`my-fixed-name`**、config 指向**另一个仓库**，
> 本仓 `docker compose ps` **是空的** ⇒ 直接 `up` 会计划 **`Container postgres-rag Creating`**
> ⇒ **撞名硬失败**，或**把容器重建到 `fastapi-rag-agent_app-net`**。
> **已有容器 ⇒ `docker start`；全新机器才 `compose up`。**

**必须填的【五项】（`app/core/config.py:58-79` 的 `validate_config` 是 fail-closed，缺一项即拒绝启动）**：
`DASHSCOPE_API_KEY` · **`LLM_API_KEY`** · **`POSTGRES_PASSWORD`** · `JWT_SECRET_KEY` · `LOGIN_PASSWORD`

> ⚠️ 2026-09-20 修：此处原写「三个」——**漏了 `POSTGRES_PASSWORD`**（实测代码检查 4 项）。
> 它由 `.env.example` 提供了占位值，所以容易漏；但**删掉/留空就会起不来**。

> 📌 **② 的依赖清单只有一份：`app/requirements.txt`。**
> 🔴 2026-09-20：此前那份"轻量版" `app/requirements-test.txt` **已删**（业务方裁决
> 「**不用双 requirements.txt，这样会混**」）。已核安全性：实测它是 `requirements.txt` 的**真子集**
> （含版本约束在内比对整行 ⇒ 只在它里面出现的行 = **空**），切过去**不丢任何包**。
> **代价**：本机会拉 torch 系（GB 级）。但 `app/rag/reranker.py:14` 是真懒加载 ⇒
> **不碰 torch 也能跑**（默认模式 `accurate_norerank`）；只有 `mode=accurate`/`full` 与
> `/rag/rerank_search` 才需要 torch + 2.3GB 模型。

---

## 2 · 可粘贴的 Prompt（给另一个 Agent）

### P1 · 冒烟（~1 分钟，只读，零成本）

```
在这个仓库里做一次冒烟测试，只做只读检查，不要改任何文件、不要启动新服务：

1. docker ps 看 postgres-rag / redis-rag 是否在跑（不在就报我，不要自己起）
2. 如果 API 已经在 8000 端口，curl /health 与 /ready
3. cd app && ../venv/bin/python -m pytest . -m "not integration and not needs_db" -q
   （若报 qdrant 单实例锁，改用：从仓库根跑 + MEM0_DIR=$(mktemp -d)）
4. 把结果按「通过/失败/未验证」三态汇报，失败项给出原始报错。

约束：不要写数据库、不要 git commit、不要 docker compose up。
```

### P2 · 契约验证（跑得到 HTTP 层，需要 token）

```
用 curl 验证这些端点的**契约**（不是"跑通"就行，要核对响应形状）：
- POST /api/v1/rag/hybrid_search  → 是否返回 method + docs，且 docs 里有 from 字段
- POST /api/v1/rag/search?mode=fast → 是否返回 query/pipeline/timing/docs
- POST /api/v1/agent/langgraph_chat → 注意：它带人工审批节点，**返回 pending_approval 是正常的**，
  不是失败；要核对 pending_tool_calls 里有工具名
- GET  /api/v1/agent/mcp_tools_dynamic → 应有 tools 列表与 total
认证：先 POST /api/v1/auth/login，字段名是 user_name（不是 username），口令取 .env 的 LOGIN_PASSWORD。
把每个端点的「实测响应」原样贴出来，并明确写出你核对的是哪一条断言。
```

### P3 · 深度测试 / 找 bug（**给你自己用**）

```
把 API 真起来，逐个端点打一遍，找"看起来在工作、实际没在工作"的地方。
重点：
1. 每个端点先看 HTTP 码，再看响应体**内容**是否合理（200 + 空内容是最危险的一类）
2. 对每个 Agent 端点，确认它**真的走到了 LLM**（看耗时、看 intent/status 字段）
3. 凡是你**没实测**的断言，一律标记为「未验证」，不要写成结论
4. 报告格式：[端点] 实测响应原文 → 你的判断 → 依据（命令）
```

> ⚠️ **P3 的注意**：本仓历史上有一整类 bug 是「**HTTP 200 但内容是空的/占位的**」——
> 只看状态码会全部漏掉。**必须读响应体。**

---

## 3 · 测试分层与命令行（**对着本仓的 marker 体系**）

| 层 | 命令 | 需要什么 | 进 CI？ | 说明 |
|---|---|---|---|---|
| **L0/L1/L2 离线** | `cd app && ../venv/bin/python -m pytest . -m "not integration and not needs_db" -q` | **redis**（+ 默认无则跳过部分） | ✅ | **主力**，最快 |
| **L3 集成** | `... -m integration -q` | 真 Postgres + **外网**（DashScope embedding） | ❌ | 本机跑 |
| **需要真库** | `... -m needs_db -q` | 真 Postgres | ❌ | ⚠️ **见 §6 红线：必须带 `POSTGRES_DB=rag_test`** |
| **全部** | `... -q` | 全部 | ❌ | — |

**⚠️ 全套必须带库名隔离**（否则会往**真库** `rag_db` 写文档，而那是 `agent-eval-gate` 的评测知识库）：

```bash
POSTGRES_DB=rag_test ../venv/bin/python -m pytest . -q
```

**2026-09-20 实测基线**（拿它当对照，数字对不上先怀疑环境）：

```
离线层：68 passed / 1 skipped / 11 deselected
新增的 Agent 用例：18 passed（app/tests/test_agent_repairs.py）
```

---

## 4 · ⚠️「**看起来像坏了，其实不是**」清单（**先读这个，能省你半天**）

> 本会话有一大半时间花在这上面。**遇到下列现象，先对照本表，别急着"修 bug"。**

| 现象 | 真相 | 怎么确认 |
|---|---|---|
| `/ready` 返回 503 `"Internal server error"` | **设计行为** —— 启动后 10 秒内就是 503 | 等 10 秒再打；或看 `main.py:430` |
| `/agent/tool_health` 显示 **4/6 healthy**（即 **2 个 unhealthy**：`fetch_webpage` / `screenshot_webpage`） | **环境天花板**，不是代码：本机 macOS **13.6**，而 Playwright **1.62** 要 chromium **1234**，`playwright install chromium` 直接报 `does not support chromium on mac13` | 跑一次 `venv/bin/playwright install chromium` 看报错 |
| `pytest` 报 `Storage folder ./.mem0/qdrant is already accessed by another instance` | **应用正跑着**占着本地 Qdrant 单实例锁 | `pkill -f "uvicorn main:app"`，或从仓库根跑 + `MEM0_DIR=$(mktemp -d)` |
| 起服务报 `connection to server at "localhost", port 5432 failed: Connection refused` | **Postgres 容器没跑**，不是代码 | `docker ps` |
| `import main` 抛 **`OpenAIError`** | `.env` 的 key **缺失**（`None`）—— 客户端在**导入期**就构造。⚠️ **只有"缺失"才会这样** | 填上 key |
| 起得来但一调用就 **401 / `AuthenticationError`** | key 是 **dummy/占位值** —— SDK 不拦，服务照起，**调用时才失败**（CI 正是靠 dummy key 跑离线用例） | 换成真 key |
| 起服务时报 **`EnvironmentError`** | key 是**空串 `''`** —— 由 `validate_config` 拦下（干净的报错） | 填上真 key |
| `/rag/*` 返回 `{"docs":[]}` | **新装的库是空的**，正常 | 先 `/rag/insert` 灌文档 |
| 检索命中「测试文档一」「Python是一门强大的编程语言」 | **知识库里有 35/77 行是测试数据**（`source`= `test`/`test_docs`），已知限制 | 查 `select source,count(*) from documents group by source` |
| `/agent/langgraph_chat` 返回 `{"status":"pending_approval","answer":""}` | 🔴 **正确行为**，不是空答案 —— 该图带**人工审批节点**，工具**还没执行**，要走 `/agent/approve` | 看响应里的 `pending_tool_calls` |
| `/rag/search` 只回 `docs`、没有 `answer` | `generate_answer` 与 `citations` **默认都是 `false`** | 显式传 `"generate_answer":true`（要引用再加 `"citations":true`） |
| 日志里 `403` 一大堆 | 可能是**十六进制地址**（`0x12403bf10`）里的 `403`，**不是 HTTP 403** | 用 `grep -E "\| ERROR"` 这样的锚定模式，别裸 grep 数字 |

---

## 5 · 调试：日志在哪、怎么定位

| 要什么 | 去哪 |
|---|---|
| 应用日志（按日滚动） | `logs/api_YYYY-MM-DD.log`（仓库根）**和** `app/logs/api_YYYY-MM-DD.log`（历史日志在这里，两处都有） |
| 错误日志 | 同上，`error_*.log` |
| 起服务时看失败原因 | uvicorn 的 stderr —— `... > /tmp/api.log 2>&1 &` 然后 `tail` 它 |
| 本仓特有的定位技巧 | 🔴 **本仓的错误日志带 rich 的变量树**（`│ └ <starlette...>`），**裸 grep 很容易误命中**。先 `sed 's/\x1b\[[0-9;]*m//g'` 去 ANSI，再只 grep 指向 `app/` 的帧：`grep -E "File \".*/app/"` |

**定位一个 500 的标准动作**（实测有效）：

```bash
sed 's/\x1b\[[0-9;]*m//g' /tmp/api.log | grep -E "File \".*/app/" | tail -6      # 哪几行本仓代码
sed 's/\x1b\[[0-9;]*m//g' /tmp/api.log | grep -E "^(TypeError|ValueError|RuntimeError|KeyError|AttributeError|openai\..*Error)" | tail -4   # 什么异常
```

---

## 6 · ⛔ 红线（**碰了会伤到别的东西**）

| 别做 | 为什么 |
|---|---|
| ⚠️ 在**已有同名容器**的机器上跑 `docker compose up`（**含只带 `postgres redis` 两个服务名的**） | 实测会**撞名硬失败**或**重建**已有容器（它们可能属于别的 compose 项目，见 §1①）。⛔ **原文此处写的是"会打断 `agent-eval-gate` 的评测，所以是红线"—— 该理由已作废**（业务方：「不用考虑 agent-eval-gate 占用 docker-compose，那个项目已经做完了，我们正常使用」）。✅ 但**"重建会断掉指向它的东西"这个现象仍成立** ⇒ **先 `docker ps` 确认再动手**，不是无条件禁止 |
| ⛔ 不带 `POSTGRES_DB=rag_test` 跑需要真库的测试 | 会往**真库 `rag_db`** 写文档，而那是评测知识库。**本仓已发生过一次**（35/77 行测试数据就是这么来的） |
| ⛔ 改 `main` 分支 / 直接 push | `main` 开了**分支保护**，直推会被服务端拒绝。走 **分支 → PR → 两个必需检查** |
| ⛔ `git commit` 里带明文凭据 | 本仓是 **PUBLIC**。提交前跑 **`bash scripts/check_secrets.sh`**（命中即 `exit 1`） |
| ⛔ 把 `.env` 提交 / 打印凭据值 | `.env` 已 gitignore。报错时要**只写名字不写值** |
| ⚠️ 改 prompt / 工具 schema / 记忆策略 | 那会改**对外行为**，PR 里必须显式声明（见 `ROADMAP.md` 的 PR 纪律） |

---

## 7 · 提交前必跑（本仓硬门）

```bash
bash scripts/check_secrets.sh        # 凭据门：命中即 exit 1（扫 staged 的新增行）
```

> ⚠️ **口径**：它**只扫 staged 的新增行** —— 没 `git add` 就跑，会打印「staged 区为空」然后 exit 0，
> **那不是"通过"，是"没扫"**。
> 另外 `--all` 模式在干净仓库上**本来就会红**（`docs/说明/部署.md` / `app/routing/schemas.py` 里有**占位符**命中 `sk-`/JWT 模式）
> —— 那是**既存的占位符**，不是泄漏；但**不要把它当成"门坏了"**。

---

## 8 · 一句话总结给 Agent

> **先看 §4 那张表**（一半的"bug"都在那里）；
> **交付路径只有一条**：`docker compose up -d`（见 `README.md`）；**要改代码/跑测试才用 §1 的开发路径**；
> **测什么、怎么测在 §3**；
> **别碰的红线在 §6**；
> **凡没实测的断言，写成「未验证」** —— 本仓最看重的就是这一条。
