"""代码执行器服务 —— 跑在**独立执行器容器**里的极小 HTTP 服务（批② · Task 2）。

## 它为什么存在

业务方 2026-10-07 原话：

> 「`execute_python` 这个代码执行器要在 **docker 容器中执行**，使用 docker 容器**热启动**的方式，
> **预先加载**，`execute_python` 直接进容器中执行，**不要暴露在系统中执行，是安全事故**」

⇒ 现状（**宿主同权限的子进程 + 白名单**）不够；要一层**容器**。
⇒ 但**应用不能自己 `docker run`** —— 那需要挂 `/var/run/docker.sock`，
   而 **`docker.sock` = 宿主 root 等价**。**本应用自己就在容器里** ⇒
   把 sock 挂给它 = 把宿主 root 交给它 ⇒ **把"代码执行逃逸"的洞换成更大的"容器逃逸"洞**。

⇒ 所以：**另起一个容器跑本服务**，应用**只发 HTTP**，⛔ 永远不认识 Docker。
   本容器由 `docker-compose.yml` 的 `executor` 服务定义（硬化配置见那里）。

## 本文件的两条不变量

1. 🔴 **执行逻辑⛔ 一行都不在这里** —— 全部复用 `code_executor_impl.run_in_sandbox_subprocess`。
   ⛔ **不许在这里抄第二份白名单 / 超时文案**（批① 刚把"同一个东西抄 5 份"收口掉 · `DEC-107`）。
2. 🔴 **每次请求起一个【新】子进程** —— 那是 `run_in_sandbox_subprocess` 的性质。
   ⛔ **不许改成常驻解释器**（`exec` 的 `globals` 会跨请求活着 ⇒ 访客互相污染）。
   守卫：`api/test_executor_server.py::test_execute_does_not_leak_state_between_requests`。

## 边界（⚠️ 知道再改）

- ⛔ **不做鉴权** —— 它**只在 compose 的内部网络里**被 `api` 调，⛔ **不映射端口到宿主**。
  改这个前提（比如给它开 `ports:`）⇒ **先加鉴权**。
- ⛔ **不暴露 `/docs`**（下面 `docs_url=None` 等）—— 内部机制，⛔ 不需要给人看的接口文档，
  少一个面就少一个面。
- 🔴 **真正的隔离在容器那一层**（只读根 · 无网 · `cap_drop` · 非 root · mem/pids 限制），
  **不是在本文件里** —— 本文件只是那个容器的入口。
"""

from fastapi import FastAPI
from pydantic import BaseModel

from code_executor_impl import run_in_sandbox_subprocess

app = FastAPI(
    title="code executor",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ExecuteRequest(BaseModel):
    """请求体。⚠️ `code` **必填** —— 缺了由 FASTAPI 给 4xx，⛔ 不静默当空串去执行。"""

    code: str


@app.post("/execute")
def execute(req: ExecuteRequest) -> dict:
    """在**一个新子进程**里跑 `req.code`，把结果原样报回。

    返回 `{"ok": bool, "out": str}` —— ⚠️ **形状与 `_SANDBOX_CHILD` 的 payload 同形**，
    这样应用侧（`code_executor_impl` 的远端路径）能**复用同一套解析**。

    ⚠️ **被执行的代码抛异常 ⇒ `ok=False`，但 HTTP 仍是 200** ——
       那个异常是**业务结果**（"你给的代码错了"），⛔ 不是"服务坏了"。
       服务坏了（比如子进程起不来）也走 `ok=False`，因为对调用方而言**处置一样**。
    """
    ok, out = run_in_sandbox_subprocess(req.code)
    return {"ok": ok, "out": out}


@app.get("/health")
def health() -> dict:
    """容器 healthcheck 用。⚠️ **不返回任何环境变量 / 凭据**（本仓红线）。"""
    return {"status": "ok"}
