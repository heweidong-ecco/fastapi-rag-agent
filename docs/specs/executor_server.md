# `api/executor_server.py`

| 项 | 内容 |
|---|---|
| **状态** | 🔵 **新建（2026-10-08 · 批② Task 2）** —— ⚠️ **服务本体在，但【应用侧还没接线】**（那是 Task 4） |
| **对外提供** | `POST /execute` —— 入 `{"code": str}`，出 `{"ok": bool, "out": str}`<br>`GET /health` —— 容器的 `healthcheck` 用<br>⚠️ **⛔ 不提供 `/docs`**（`docs_url=None`）：内部机制，少一个面就少一个面 |
| **谁在用** | ⚠️ **暂时没有人** —— `docker-compose.yml` 的 `executor` 服务会起它（Task 3），<br>应用侧（`code_executor_impl` 的**远端路径**）到 **Task 4** 才接 |
| **测试** | `api/test_executor_server.py`（**6**）· ⚠️ 数字会变，判据：`cd api && ../venv/bin/python -m pytest test_executor_server.py --collect-only -q \| tail -1` |

## ✅ 做了什么

- 一个**极小**的 HTTP 服务：**热启动常驻**，收 `code`、在**新子进程**里跑、把结果报回
- 🔴 **执行逻辑一行都不在本文件** —— 全部调 `code_executor_impl.run_in_sandbox_subprocess`
  （白名单 / 超时 / 报错文案**只有那一份**）
- 🔴 **每次请求起一个【新】子进程** ⇒ `exec` 的 `globals` **不跨请求**
- 镜像 `api/executor.Dockerfile` —— ⚠️ **只装 `fastapi` + `uvicorn`**，⛔ 不 `-r requirements.txt`

## 🟡 做到哪 / 缺什么

- ⬜ **应用侧还没接线**（Task 4）· **compose 还没加这个服务**（Task 3）
- ⬜ **没有鉴权**（⚠️ 前提是"只在内部网络里" —— 见下）
- ⬜ **没有并发信号量**（Task 5）
- ⬜ **容器硬化配置还没落地**（Task 3：只读根 / 无网 / `cap_drop` / 非 root / mem·pids 限制）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「它就是个转发壳，没什么好看的」 | 🔴 **它是安全边界那一层的【入口】** —— 这个容器里跑的是**任意代码**，所以**镜像刻意做小**（⛔ 没有应用那一堆依赖、⛔ 没有凭据、⛔ 不挂任何卷）：「这个容器里有什么」= 「逃出去的人能拿到什么」 |
| 「**应用自己 `docker run`** 不是更直接」 | ⛔ **那要挂 `/var/run/docker.sock`**，而 **sock = 宿主 root 等价**，且**本应用自己就在容器里** ⇒ **把"代码执行逃逸"的洞换成更大的"容器逃逸"洞**。⇒ 应用**只发 HTTP**，⛔ 永远不认识 Docker |
| 「直接调 `execute_python_impl` 就少一层」 | ⛔ **那会把「意图检测」也搬进执行器** —— 那是**产品策略**（"这个工具只执行代码、不生成代码"），⛔ **不是执行机制**。策略留在应用侧（`execute_python_impl` 里、**在决定走本地还是远端之前**） |
| 「超时那条用例要等 5 秒，太慢，把 `MAX_EXEC_TIME` 调小就行」 | ⛔ **调小再测，测的就不是真实配置下的行为**。那 5 秒是**有意付的** |
| 「它没有鉴权 ⇒ 是个洞」 | ⚠️ **前提是"只在 compose 的内部网络里"**：⛔ 不映射端口到宿主。**改这个前提（给它开 `ports:`）⇒ 先加鉴权** |
| 「`/execute` 抛异常会 500 吧」 | ⛔ **不会** —— 被执行的代码抛异常是**业务结果**（"你给的代码错了"），走 `ok=False` + **HTTP 200**。**服务真的坏了**（子进程起不来）也走 `ok=False`，因为对调用方**处置一样** |
| 「用 `globals()` 就能测出有没有串状态」 | ⚠️ **沙箱白名单里没有 `globals`**（实测 `NameError`）。能用的是 **`dir`** —— `exec(code, g)` 里 `dir()` 列的就是 `g` 的键 |

## 关联

- **决策 / 计划** ⇒ 批② 施工单（在 `fastapi-rag-agent-TODO待办/` 下、名为「施工单-20261008-代码执行器进容器」；
  ⚠️ 它落在分支 `docs/ledger-reconcile` 上（PR `#114`），**主干上暂时还没有**
  ⇒ 这里**⛔ 不写 `.md` 全路径**，否则断链门判红）· `DEC-104` §三
- **复用的唯一实现** ⇒ `docs/specs/` 里 `code_executor` 那份（⚠️ **那份目前还没有** —— 归批② Task 7）
- **守卫** ⇒ `api/test_executor_server.py`（6 条：响应形状 ×3 · **不串状态** · **超时硬杀且服务存活** · 健康检查）
- ⚠️ **不要**在这里 import `tool_cache` / `langchain` / 任何数据库驱动 —— 见上表第一条
