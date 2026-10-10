# `app/demo_main.py`

## ✅ 做了什么

**demo 的入口** —— `uvicorn demo_main:app` 用它。它做的事只有两件：
`from main import app`（复用本仓那一套，⛔ **不改它**），
再把 `app/demo/claim.py` 的 router `include_router` 挂上去。

| 跑哪条线 | 命令 | demo 的东西在不在 |
|---|---|---|
| **本仓（完整版）** | `uvicorn main:app` | 🔴 **不在** —— `main.py` ⛔ 不 import 它，也不 import `demo/` 包 |
| **demo** | `uvicorn demo_main:app` | ✅ 在 |

## 🟡 做到哪 / 缺什么

- ✅ 两条线都起真服务验过（2026-10-10）：本仓那条路上 `/api/v1/demo/claim` ⇒ **404**；demo 那条 ⇒ 200。
- 🔴 **本文件只有 36 行，而它是整个「甲」的关键一环** —— 守卫 ⇒
  `app/tests/test_demo_claim.py` 的「`demo_main` 真的把那条 router 挂上去了」（AST 判据）。

## ⚠️ 看代码会误判的地方 ⭐

1. 🔴🔴 **删掉那两行，本仓所有守卫照样全绿，而 demo 那条路上访客再也领不到凭据。**
   —— 这是**接线**坏掉、**行为**判据一条都够不到的那一类。
   📄 本仓为此专门记过一份复盘：`docs/复盘/2026-10-09-测试全绿而活路径坏了两次.md`。
   ⇒ 所以这里单有一条 **AST** 判据（⛔ 不是子串匹配 —— 那会数到注释）。
2. 🔴 **⚠️ import 本模块 = 【就地改掉 `main.app`】**（`include_router` 改的是那个对象本身）。
   ⇒ ⛔ **别在 pytest 里 import 它** —— 从那以后**同一个会话里后面所有**看路由表的用例
   都会看到一条多出来的路由，而**同进程里改不回来**（路由是 import 时注册的）。
   ⇒ 而且**没法用子进程绕**（`main` 一 import 就撞 Mem0 单实例锁，见
   `app/demo/specs/claim.md` 第 ⑧ 条）。
3. ⚠️ **「默认 = 完整版」靠【结构】，⛔ 不靠开关。**
   `DEC-142` 要的是「不设环境变量时行为与今天逐字一致」；
   ⚠️ 开关写法（判一个环境变量）**要靠人记得把默认值写对**，
   而这里靠的是「**本仓那条路上压根没有这个模块**」。
   ⇒ ⛔ **别把它改成开关**：那正是 2026-10-10 被业务方要求回滚的第二种写法
   （"包一层开关门控"看着像默认不变，实际仍是 demo 长进了本仓）。
4. ⚠️ **平台约束**（demo 要部署到创空间）：端口必须是 `0.0.0.0:7860`（⛔ 不是 8000），
   且 ⛔ **不得读 `Authorization` 头**（平台往每个请求注入 449 字符）。
   📄 `docs/说明/魔搭创空间-部署与平台约束.md`

## 关联

- `app/demo/CLAUDE.md` · `app/demo/specs/claim.md` —— demo 那一侧的模块与规矩
- `app/specs/main.md` —— 本仓的入口（⛔ 本模块**不动它**）
- `app/tests/test_demo_claim.py` —— 守卫
- `docs/decisions/DEC-142-demo代码通道的默认值.md` · `DEC-143-demo访客凭据的发放方式.md`
