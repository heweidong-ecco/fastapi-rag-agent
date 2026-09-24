> 📦 **已归档（2026-09-24）** —— 内容已**拆分并入**两套新文档：
> `fastapi-rag-agent-TODO待办/施工单-本项目.md`（隔离方案 B2 在其中 · §2.2）
> 与 `fastapi-rag-agent-TODO待办/通用/从代码完成到链接可分享-通用方法.md`。
> **平时不用看这份。**

# 施工单 A ｜ 本机跑通第 ①② 步（`git clone` → `docker compose up -d`）

> **目标**：在**不碰你现有环境**的前提下，把 `fastapi-rag-agent` 在本机跑起来，打开 `127.0.0.1:18000` 自己看到它工作。
> **不涉及**：上云、域名、前端。这一步**不花钱、不依赖机器选型**，今晚就能做。
>
> **本机现状待填**：我不知道你本机 docker 里现在有没有在跑的容器（那条 `docker ps` 被你拒了）。
> 下面的做法**两种情况都安全** —— 见 §1。

---

## 0. 先记住一句话

> **`git clone` 和 `docker compose` 是两个动作，不是一件事。**

```
git clone <repo>                     ← 取代码，得到一个文件夹
cd 文件夹 && docker compose up -d     ← 跑起来，拉起 postgres + redis + api
```

`docker-compose` **不是**用来下载代码的 —— 它是用来**同时把几个容器拉起来**的。

---

## 1. ⚠️ 光"单独文件夹"不够 —— 有 3 个名字是全局的

这是本施工单最重要的一节。`fastapi-rag-agent/docker-compose.yml` 里**有三个东西跟目录无关**，
新 clone 一个目录再 `up`，**会撞上正在跑的旧容器**：

| # | 撞什么 | 原因 | 后果 |
|---|---|---|---|
| 1 | **容器名** | `container_name` **写死**：`rag-api` / `postgres-rag` / `redis-rag` / `prometheus` / `grafana` | 直接 `up` 会**撞名**，可能重建/打断已在跑的容器 |
| 2 | **端口** | `ports` **写死**：8000 / 5432 / 6379 / 9090 / 3000 | **端口冲突**，起不来 |
| 3 | **数据卷** | 卷用 `name:` **钉死**成 `my-fixed-name_postgres_data` 等 | 新目录会**挂到同一个已有数据卷** —— 它跟目录完全无关 |

而且那个文件**末尾自己写着一段警告**（原文）：

> `rag-api-eval` 正被 agent-eval-gate 的评测使用
> ⇒ **有评测在跑时不要执行 `docker compose up`**
> 因为项目名变了，compose 会认为这些容器属于"别的项目"，而 `container_name` 是写死的 ⇒ 直接 up 会撞名/尝试重建，**打断评测**。

**⇒ 所以正确做法是：换一套全局名字，让新旧两套完全隔离。** 下面是做法。

---

## 2. 施工步骤（推荐路径：全新 clone + override）

### 第 1 步｜取代码到一个新目录

```bash
cd ~/Desktop/tmp/1                      # 或你选定的任意目录
git clone https://github.com/heweidong-ecco/fastapi-rag-agent.git rag-demo
cd rag-demo
```

> 📌 如果 `github.com` 连不上（定向拦截），按你的全局纪律用 SSH 地址：
> `git clone git@github.com:heweidong-ecco/fastapi-rag-agent.git rag-demo`

### 第 2 步｜写一个 `docker-compose.override.yml`

Docker Compose **会自动合并**同目录下的 `docker-compose.override.yml`。
把下面这份放进去 —— 它把**容器名、端口、卷名**全部改成一套新的：

```yaml
# docker-compose.override.yml  —— 让这套实例与你已有的容器完全隔离
services:
  api:
    container_name: rag-demo-api
    ports: ["18000:8000"]
  postgres:
    container_name: rag-demo-postgres
    ports: ["15432:5432"]
  redis:
    container_name: rag-demo-redis
    ports: ["16379:6379"]
  prometheus:
    container_name: rag-demo-prometheus
    ports: ["19090:9090"]
  grafana:
    container_name: rag-demo-grafana
    ports: ["13000:3000"]

volumes:
  postgres_data:  { name: rag-demo_postgres_data }
  redis_data:     { name: rag-demo_redis_data }
  prometheus_data:{ name: rag-demo_prometheus_data }
  grafana_data:   { name: rag-demo_grafana_data }
```

**为什么卷名也要改**：不改的话，新实例会挂到旧数据卷上 ——
轻则两套实例**共用同一个库**（互相污染），重则你以为在跑新库、其实在读写旧库。

### 第 3 步｜准备 `.env`（**这几个是必填，缺了起不来**）

```bash
cp .env.example .env
```

照 `.env.example` 填这 4 个（我从文件里核过，**必填**）：

| 键 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | **阿里百炼**的 key。**embedding 固定走这里**，不可替换 |
| `JWT_SECRET_KEY` | 随便一串强随机 |
| **`LOGIN_PASSWORD`** | ⚠️ **缺失则应用拒绝启动**（`config.validate_config`）。生成：`python3 -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `POSTGRES_PASSWORD` | 本地随便设 |

可选：要切 DeepSeek 当对话模型，把 `.env.example` 里**注释掉的四个键**打开（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_FAST` / `LLM_MODEL_CHAT`）。
> ⚠️ 这两个模型键**只管生成/对话**，embedding 仍走 DashScope，不受影响。

### 第 4 步｜起服务（**注意 `-p rag-demo`**）

```bash
docker compose -p rag-demo up -d
```

`-p rag-demo` 把**项目名**也换掉 ⇒ 网络名变成 `rag-demo_app-net`，不碰旧的 `my-fixed-name_app-net`。

### 第 5 步｜验证

```bash
docker compose -p rag-demo ps                    # 5 个容器应该是 Up / healthy
curl -s http://127.0.0.1:18000/health            # 应返回健康
```

然后在浏览器打开 **http://127.0.0.1:18000** → 用 `.env` 里的 `LOGIN_USER_NAME` / `LOGIN_PASSWORD` 登录。

---

## 3. ⚠️ 第一次跑起来，知识库是**空的**

这一点必须知道，否则你会以为"检索坏了"：

> **独立 clone + 新卷名 ⇒ 一个全新的空库。** 检索任何东西都只会返回"没找到"。
> **这跟代码无关，是数据没进去。**

⇒ 跑通之后，**先灌一份文档进知识库**，再去问它问题。
（`agent-eval-gate` 那边把这个叫 **seed 知识库**，并且把它列为**契约里的必做步骤** ——
契约 `评测-sut-adapter.md:42`：知识库不在 git，首跑必须自带文档集 + seed 步骤，否则检索不可复现。）

---

## 4. 备选路径（供你按本机情况选）

| 路径 | 什么时候用 | 代价 |
|---|---|---|
| **A（上面这条，推荐）** | 任何时候 —— **新旧完全隔离** | 多写一个 override 文件 |
| **B：用原目录直接跑** | 你本机**确认没有任何** rag 相关容器时 | 有旧容器就撞 |
| **C：先停旧的再起新的** | 你不需要旧实例了 | ⚠️ **会打断 `agent-eval-gate` 的评测**（compose 文件自己警告过） |

> **本机现状我不知道** —— 你跑一下 `docker ps -a` 就知道该走哪条。
> 但只要走 **A**，就不用管本机有没有旧容器。**所以建议直接走 A。**

---

## 5. 出问题时先查这 3 个

（编号沿用 `fastapi-rag-agent` 仓里已记录的坑，都是他们真实踩过的）

| 现象 | 根因 | 处置 |
|---|---|---|
| 起不来、报端口被占 | 旧容器占着 8000/5432/6379 | 走 §2 的 override，换到 18000 等 |
| 连不上后端起服务 | `localhost` 解析到 **IPv6**（`::1`），被别的进程占着 | 用 **`127.0.0.1`** 而不是 `localhost` |
| judge/外部调用报 `CERTIFICATE_VERIFY_FAILED` | 本机有 TLS 拦截，其 CA 只在系统信任库 | 设 `SSL_CERT_FILE=/etc/ssl/cert.pem` |

> 完整清单见 `fastapi-rag-agent` 的 `deploy.md` 与 `agent-eval-gate/docs/部署.md` §6。

---

## 6. 做完这一步，你得到什么

- ✅ 一个**能跑起来、你能打开看**的系统（`127.0.0.1:18000`）
- ✅ 一次性验证了"这套 compose 在我机器上没问题" —— **上云时的风险就只剩"机器够不够大"和"地址通不通"**
- ❌ **还不能给其他人** —— 那是第 ④⑤ 步（云主机 + 发链接）

> 对应缺口 2 文档里的 **L0 之前**：这一步是"自己先看见"，不是"别人能看见"。

---

## 7. 本机现状（待填）

| 项 | 值 |
|---|---|
| 本机有没有在跑的 rag 容器 | ⬜ 待你 `docker ps -a` |
| 本机 docker CPU / 内存 | ⬜ 待你 `docker info` |
| 本机是否已有该仓 | ⬜ 待确认（`~/agent-projects` **已确认不存在**） |
| 走的路径（A / B / C） | ⬜ |
| 跑通时间 | ⬜ |
| 访问地址 | ⬜ `127.0.0.1:18000` |
| 知识库是否已 seed | ⬜ **必做，见 §3** |

---

## 来源

- [云开发机 DevBox — 阿里云帮助文档](https://help.aliyun.com/zh/oos/getting-started/devbox-overview)
- 项目自述与坑位：`fastapi-rag-agent` 的 `README.md` / `deploy.md` / `docker-compose.yml`；`agent-eval-gate` 的 `docs/部署.md`
