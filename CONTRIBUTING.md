# 贡献指南

> ## 先读这一句
>
> **这是一个单人项目**（见「⚠️ 关于贡献」一节）——
> 所以本文件的主要用途**不是"怎么提 PR"**，而是 **「换了一台机器 / 隔了几个月回来，怎么接着干」**。
>
> 📍 **文档全貌看 [`docs/文档地图.md`](docs/文档地图.md)** —— 那是索引，本文件不重复它。

---

## 一 · 五分钟把环境跑起来

```bash
# ① 配置（⚠️ .env 必须在【仓根】，不是 api/ 下）
cp .env.example .env
#    然后填 4 个必填键：DASHSCOPE_API_KEY · POSTGRES_PASSWORD · JWT_SECRET_KEY · LOGIN_PASSWORD
#    ⇒ 逐键说明见 docs/契约/环境变量.md

# ② 起服务（5 个容器：api / postgres / redis / prometheus / grafana）
docker compose up -d

# ③ 验证（判据是 HTTP 码，不是"我觉得起来了"）
curl -s -o /dev/null -w '/health %{http_code}\n' http://127.0.0.1:8000/health   # 200
curl -s -o /dev/null -w '/ready  %{http_code}\n' http://127.0.0.1:8000/ready    # 200（⚠️ 启动 10 秒内是 503，正常）
bash scripts/list_endpoints.sh                                                   # 57 个端点
```

> ⛔ **`docker compose up` 之前先跑**：`docker ps --format '{{.Names}}' | grep eval`
> —— **空才安全**（有评测在跑时 up 会打断它，见 `DEC-033` 🅰️）。
>
> ⛔ **`docker compose down` 不要加 `-v`** —— 那会**删卷 = 数据全没了**。

**起不来** ⇒ 先查 [`docs/说明/运维.md` §七](docs/说明/运维.md) 的**常见故障表**，再查 [`docs/FAQ.md`](docs/FAQ.md)。

---

## 二 · 开发流程

### 本地开发（API 热重载，不用重建镜像）

```bash
bash dev.sh          # 起 PG+Redis 容器 + 本地 uvicorn --reload
```

### 改代码

```
1. 读 CLAUDE.md 的「🔴 当前方向」—— 现在的主线是【后端先行】（DEC-033 🅱️）
2. 查 ROADMAP.md 的「📋 待办总账」—— 要动的是不是已经在册
3. 动代码前：
   · bug  ⇒ 先 systematic-debugging，再 test-driven-development
   · 新功能 ⇒ 先 brainstorming
4. 改完 ⇒ verification-before-completion（evidence before assertions）
```

> 📌 **skill 必用表见 `CLAUDE.md`** —— ⚠️ **「知道 skill 存在 ≠ 会用 skill」**
> （本仓有 8 个 PR 一次都没跑过 `/留痕-checks` 的前科）。

### 提交

```bash
git add -A
bash scripts/check_secrets.sh        # ⭐ 凭据门（PUBLIC 仓，必跑）
bash scripts/check_doc_links.sh      # 改了文档才需要
git commit
```

⛔ **提交前必须答两个门的两问**（见 `docs/规范/开发规范.md` §2.2）：
1. 有决策事项吗？有 ⇒ 建 `DEC-nnn`；无 ⇒ 写明「本次无决策事项」
2. CHANGELOG 写了吗？没写 ⇒ **先补**

### 推送

* **本地 commit 随便攒；推送以「一个可验证单元」为界**（一个 PR 的活儿做完再推）
* ⚠️ **本地 = 不 durable** ⇒ **当天结束前至少推一次**

---

## 三 · 代码规矩（**要点，全文见 [`docs/规范/开发规范.md`](docs/规范/开发规范.md)**）

| # | 规矩 |
|---|---|
| 1 | 业务错误一律 `raise AppException(ErrorCode.XXX, msg)` |
| 2 | ⛔ **中间件里不许抛 `AppException`** —— 直接返回 `JSONResponse`（否则变 500） |
| 3 | 数据库一律用 `get_db()` 上下文管理器，**禁止裸连接** |
| 4 | 环境变量**从 `api/config.py` 导入**，不要直接 `os.getenv` |
| 5 | 注释**写「为什么」不写「是什么」**；更正类注释**带日期 + 出处** |
| 6 | 删代码时**留一行说明删了什么**，不要静默删 |
| 7 | 🔴 **PUBLIC 仓，不得写入明文凭据** |

> ⚠️ **本仓没有任何自动化规范检查**（无 ruff / black / mypy）
> ⇒ **上面全靠人遵守**。唯一的自动门是**凭据门**和**链接检查**。

---

## 四 · 文档规矩

| 规矩 | 说明 |
|---|---|
| **一份文档只有一个权威** | 同一个问题只有一处是准的 |
| **接口清单不写进文档** | 跑 `bash scripts/list_endpoints.sh` 现取 |
| **按四层放** | 入口 / 契约 / 说明 / 过程 —— 见 `DEC-036` |
| **加/改文档后跑** `scripts/check_doc_links.sh` | 它会抓断链 |
| **同步 `docs/文档地图.md`** | 加了新文档要登记 |

---

## 五 · ⚠️ 关于贡献（**诚实说**）

**本仓目前是单人项目**（业务方 + AI 协作）。

⇒ **本文件不是"招募贡献者"用的**，而是：
1. **给未来的自己看的**（隔几个月回来，从这份进）
2. **给 clone 的人看的**（想跑起来、想知道怎么改）

**如果你确实想改点什么**：本仓**没有**开放的 PR 流程约定。最稳妥的是先开一个 Issue 说明来意。

---

## 六 · 想知道更多

| 我想… | 去哪 |
|---|---|
| **这项目是什么** | [`README.md`](README.md) |
| **现在做到哪了** | [`ROADMAP.md`](ROADMAP.md) ⭐ **唯一权威** |
| 所有文档在哪 | [`docs/文档地图.md`](docs/文档地图.md) |
| 接口怎么调 | [`docs/契约/接口契约.md`](docs/契约/接口契约.md) + `scripts/list_endpoints.sh` |
| 环境变量 | [`docs/契约/环境变量.md`](docs/契约/环境变量.md) |
| 表结构 | [`docs/契约/数据模型.md`](docs/契约/数据模型.md) + [`api/schema.sql`](api/schema.sql) |
| 出问题了 | [`docs/说明/运维.md`](docs/说明/运维.md) §七 · [`docs/FAQ.md`](docs/FAQ.md) |
| 为什么这么设计 | [`docs/decisions/`](docs/decisions/) |
| 过去犯过什么错 | [`docs/复盘/`](docs/复盘/) |
| 安全相关 | [`SECURITY.md`](SECURITY.md) |

## 变更记录

- 2026-09-29 建立（文档体系第二批）。
