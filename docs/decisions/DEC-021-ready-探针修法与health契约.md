# 决策记录：DEC-021 · `/ready` 探针的修法，与 `/health` 的行为契约

- 日期：2026-09-20
- 状态：**已采纳并执行**
- 关联：`docs/待办登记-2026-09-20-全仓审计与方向更正.md` §一·**A**（🔴A）

## 决策事项

🔴A 怎么修？

**🔴A 是什么**：`health_check()` 有**两种返回类型** ——
健康时 `return dict`，不健康时 `return JSONResponse(503, ...)`。
而 `/ready`（`main.py:440`）拿到它后**无条件**调 `.get("status")`
⇒ `JSONResponse` 没有 `.get` ⇒ `AttributeError` ⇒ 全局处理器兜住 ⇒ **`/ready` 返回 500 而不是 503**。
实测原文：`AttributeError: 'JSONResponse' object has no attribute 'get'`（`main.py:441`）。

## 背景与约束

- `health_check` 是**双重身份**：它既是 `@app.get("/health")` 的**路由本体**，又被 `/ready` 当**helper** 调。
  （实测：全仓**只有 `/ready` 一处**调它，见 `scripts/impact.sh health_check`。）
- ⚠️ **对 K8s / 负载均衡，503 与 500 是不同语义**：
  503 = "暂时别把流量给我"；500 = "我坏了"。
  **把"依赖挂了"报成"我坏了"，正是就绪探针最不该犯的错。**
- **约束**：`/health` 的对外行为（**200 + dict** / **503 + 错误体**）**必须逐字不变** —— 它是对外接口。

## 备选方案

| 方案 | 一句话 |
|---|---|
| **甲 · 拆「算」与「渲染」**（采纳） | 抽出 `_compute_health() -> dict`（**永远返回 dict**）；`/health` 负责把它渲染成 200/503；`/ready` 调 `_compute_health()` |
| 乙 · 在 `/ready` 里做类型判断 | `status = 503 if isinstance(health, JSONResponse) else health.get("status")` |
| 丙 · 让 `health_check` 永远返回 dict | 删掉那段 `JSONResponse`，靠 FastAPI 自动渲染 |

## 评估标准

1. **`/health` 的对外行为是否逐字不变**（硬约束）
2. **根因是否消除**（"一个函数两种返回类型"还会不会再坑到下一个调用方）
3. **改动面**
4. **可测性**

## 方案对比

| 标准 | 甲 · 拆 | 乙 · 类型判断 | 丙 · 永远 dict |
|---|---|---|---|
| **1 `/health` 不变** | ✅ 显式渲染，逐字保留 | ✅ 不动 `/health` | 🔴 **会变！** `health_check` 不再返回 `JSONResponse` ⇒ FastAPI 把 dict 当 200 ⇒ **`/health` 从不健康时的 503 变成 200** |
| **2 根因消除** | ✅ **消除了** —— 不再有"两种返回类型"这回事 | ❌ **保留根因**：下一个调 `health_check` 的人**照样会被坑** | ✅ 消除 |
| **3 改动面** | ⚠️ 中（拆函数 + 两处调用） | ✅ 最小（1 行） | ✅ 最小（删 8 行） |
| **4 可测性** | ✅ 两条用例分别守 `/health` 与 `/ready` | ✅ 同 | ✅ 同 |

## 最终决策 + 理由

**采纳「甲 · 拆「算」与「渲染」」。**

1. **丙 被标准 1 直接淘汰** —— 它看着最小，却会**静默把 `/health` 的 503 变成 200**。
   ⚠️ **这正是本仓反复防的那类改动**：改动面小、看着无害、**却改了一个对外接口的语义**，
   而且**只靠 diff 看不出来**（diff 里只是"删了一段 return"）。
2. **乙 只治症状** —— 它让 `/ready` 好了，但 `health_check` **仍然是"一个函数两种返回类型"**。
   下一个调用方（或下一个 `_compute_health` 式的复用）会再踩一次。**根因不该留着。**
3. **甲 同时满足 1 与 2**：拆完之后，"算健康"这件事**只有一个返回类型**，
   而 `/health` 的渲染是**显式写出来的**（谁想改它的语义，必须改那三行，藏不住）。

## 影响与后续行动

| 项 | 状态 |
|---|---|
| `api/main.py`：抽出 `_compute_health()`；`/health` 显式渲染；`/ready` 改调 `_compute_health()` | ✅ 完成 |
| 新增用例 `test_ready_returns_503_not_500_when_unhealthy` | ✅ 完成（**红→绿已验证**：红时报的真实状态码是 **500**） |
| `/health` 行为对照 | ✅ **改前 = 改后**（实测 `GET /health -> 200 {"status":"healthy",...}` 两边一致） |
| 全套离线层 | ✅ **71 passed / 1 skipped / 11 deselected**（68 基线 + 3 新增，**零回归**） |
| `import main`：`ROUTES=13` / `OPENAPI_PATHS=59` | ✅ 与改动前一致 |

**📌 用例上的一个刻意的写法**：测试用了 `TestClient(M.app, raise_server_exceptions=False)`。
默认的 `True` 会把 `AttributeError` **直接抛到测试里** ⇒ 测出来的是"抛了异常"，
**而不是"生产上到底返回 500 还是 503"**（生产环境有全局处理器兜住）。
⇒ **要断言对外契约，就得让测试看到真实的 HTTP 响应。**

## 反悔成本

**低。** 三种改法都是同一个文件里的局部改动；`git revert` 即可回到 `health_check` 的双返回型。
⚠️ **但回到"乙"要留意**：那是把根因留着，**下一个人还会踩**。
