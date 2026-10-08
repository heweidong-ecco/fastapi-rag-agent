# DEC-111 · MCP 会话从「每次自开自关」改成**长驻**（actor 模式）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施（2026-10-08）** —— 批④-**B**，4 个 Task 全部落地 |
| **触发** | ① `DEC-104` §2.1 路线（业务方 2026-10-08 选「**批④：B**」）② 本轮**调研**（业务方裁「**先调研**」）③ 业务方 2026-10-08 裁「**两个一起做**」（= 本文 + 那条 stdout bug） |
| **类型** | 性能（单次调用 **~2s → ~5ms**）· 会话模型 · 顺带修两个真 bug |
| **落点** | `api/agent_graph_advanced.py`（actor）· `api/main.py`（生命周期）· `api/mcp_server.py`（stdout）· `api/test_agent_repairs.py`（守卫自称订正）· 🆕 `api/test_mcp_long_session.py` · 🆕 `api/test_mcp_stdout_is_clean.py` |
| **施工单** | `fastapi-rag-agent-TODO待办/施工单-20261008-mcp长驻会话.md` |
| **调研** | `docs/说明/mcp长驻会话-调研-20261008.md`（**实测数据全在那里**） |
| **判据** | 见 §七 |

---

## 一 · 要裁的是什么

「**每次工具调用起一次 MCP 子进程**（实测 **2.42 / 2.09 / 1.93 秒**）」要不要改成**复用**。
成本几乎全在**起子进程 + 重新 import langchain**，⛔ 不在那次工具计算上。

🔴 **但这条路本仓栽过**：2026-09-20 试过**会话池**，结果 `stdio_client` 基于 anyio，
其 cancel scope 要求「**进入与退出在同一个 task**」，而池化横跨 3 个 task
⇒ `RuntimeError: Attempted to exit cancel scope in a different task…`
⇒ **应用启动直接失败**（`Application startup failed. Exiting.`）。
⚠️ 那比原来的缺陷更糟：原来是"应用能跑、只是 MCP 健康检查挂"。

---

## 二 · 决策：**actor 模式**

> **一个 holder task 独占整个 `async with`；调用方只往队列投请求、等一个 future。**

🔵 **实测（连跑三轮）**：首次 ~0.022–0.025 s（含握手），之后稳定 **4–7 ms**；
并发 5 个 ~0.021–0.027 s；**退出干净，anyio cancel-scope 报错 0 次**。

🔴 **与 24 天前那次的真正区别，⛔ 不在"池化 vs 不池化"**：

| | 2026-09-20（❌ 炸） | 本次（✅ 通） |
|---|---|---|
| 那个 `async with` **横跨几个 task** | **3 个**（启动建 · 请求用 · 归还关） | **1 个**（holder task 独占） |
| 调用方怎么拿到结果 | 直接拿 pool 里的 session 用 | **投队列、等 future**（⛔ 不碰 session） |

📌 **可复用的判据**：**anyio 只管「进入与退出在不在同一个 task」，⛔ 不管中间被谁 await 过。**
⇒ 「长驻会话」的难点**不是"跨 task 共享对象"**，是**"别让别人碰那个 context manager"**。

### 2.1 三个设计点

| # | 点 | 怎么定的 |
|---|---|---|
| 1 | **会话归谁** | 模块级 actor；`main.py` 用 `_get_actor()` 起、`aclose_mcp_session()` 关 |
| 2 | **测试用的 `asyncio.run` 每次新 loop** | actor **按 loop 认领**（loop 变了就重建）—— 队列/Future 绑在创建它的 loop 上 |
| 3 | **子进程崩了** | holder task 结束即标记失效，下次调用**自动重建**；⚠️ **限流 5 次**，⛔ 不无限重启 |

⚠️ **还有一条不写在施工单里、但很重要的**：**一个请求失败⛔ 不该弄死整个会话**。
长驻之后，一次工具异常会波及**之后所有**调用 —— 那是"每次自开自关"都**没有**的脆弱性，必须显式挡掉。

---

## 三 · 顺带照出的**两个真 bug**（都与长驻会话**独立**，现状就在发生）

### 3.1 🔴 服务端 `print` 写到 **stdout**（= MCP 的传输通道）

```
ValidationError: Invalid JSON … input_value='MCP Server 启动中... 已注册 7 个工具'
```
🔴 **每次工具调用稳定 1 条**（实测 3/3）。其中 `list_tools` 那处更危险 ——
它跑在 `tools/list` **请求当中**，正是客户端在等响应的时候。
✅ **已修**（两处 → `sys.stderr`）+ 🆕 守卫 `api/test_mcp_stdout_is_clean.py`（3 条，
含 **AST 扫**（⛔ 不用 grep —— 注释里也写着 `print(`）与**真起子进程断言 stdout 为空**）。
📄 现场 ⇒ `docs/说明/mcp长驻会话-调研-20261008.md` §五

### 3.2 🔴 `agent_graph_advanced.py` 里 **`asyncio` 根本没被 import**

而 2026-09-20 那句**去重注释**还写着「本文件 `:8` 已经有 `asyncio`」——
去重时把**唯一**那一处也删了，当时**没有任何代码用它**，所以一直没暴露。
✅ **本轮 actor 一用 `asyncio.*` 当场 `NameError`** ⇒ 已补在文件顶部 + 订正那句注释。
📌 **教训：注释说「别处有」⛔ 不等于「别处真有」—— 去重时得核，不能只信注释。**

---

## 四 · 🔴 一条**我自己的流程错**（记下来防复发）

做 stdout 修复的**反证**时，我用 `git checkout -- api/mcp_server.py`「还原」——
⚠️ **但那时修复还没提交** ⇒ 那条命令把文件还原到 **HEAD（= 没修的样子）**，
**把要提交的修复一起抹掉了**。我把「`git diff` 为 0」误读成「还原干净」。
⇒ 那一版提交里**只有守卫、没有修复**。

🔴 **是【守卫本身】把这件事抓出来的**（下次全量跑，它红）。
✅ 已 `--amend` + `--force-with-lease` 修正（该分支当时**未开 PR**，无人依赖旧 sha）。

📌 **可复用的判据**：**要做反证时，先 `git stash` 或先提交** ——
`git checkout -- <file>` 的语义是「**回到 HEAD**」，⛔ 不是「回到我动手之前」。
**"diff 为空"只说明"和 HEAD 一样"，⛔ 不说明"我的改动还在"。**

---

## 五 · 备选与反悔成本

| 决策点 | 没选的备选 | 为什么 | 反悔成本 |
|---|---|---|---|
| 形状 | **会话池**（2026-09-20 那条） | 横跨 3 个 task ⇒ anyio 炸 | — （已证明不可行） |
| 形状 | **常驻 HTTP/SSE 服务** | 2.x 里形态齐备（服务端 `streamable_http_app`；客户端 `streamable_http`/`sse`）⇒ **可行**，但要多一个进程 + 一个本机端口，而 actor 已经**决定性胜出**（4–7ms） | 中（换传输层） |
| 生命周期 | **会话挂在每次请求上** | 省得少（每请求仍付一次 ~2s），但零跨请求风险 | 低 |
| `main.py` 那两处 | **不接生命周期**（靠懒起 + loop 关闭时自动收） | 实测**不漏子进程**（§七 ②）⇒ 不接也安全；接上只是让释放时机**可预期** | 低 |

🔴 **反悔路径**：`call_mcp_tool` 改回 `async with mcp_session() as session: …` 即可（**一个函数**）。
⚠️ 但那样会**同时**退掉性能与"一次失败不弄死会话"那条保护。

---

## 六 · ⚠️ 仍未验证的（⛔ 别把本文读成"这套已经稳了"）

| 没测的 | 为什么重要 |
|---|---|
| **子进程【崩了】的真实恢复** | 代码里有重建 + 限流，但**只在假对象上测过**（`test_a_failing_call_does_not_kill_the_session`），⛔ **没真杀过子进程试** |
| **高并发 / 压力** | 只测到 **5 并发**。MCP 单会话是**请求-响应串行**的 ⇒ **并发上限未探** |
| **创空间那台机器** | 所有数都是**本机**量的。创空间是 **2 vCPU / 8 GiB / Swap=0** ⇒ **未在那上面量过** |
| **长跑的内存漂移** | 84 MB 是**刚起来**量的（`docs/说明/mcp长驻会话-调研-20261008.md` §3.3），**没有跑几小时看它涨不涨** |

---

## 七 · 判据（逐条可打印）

```bash
# ① 会话真的只开一次（本批的全部收益）
venv/bin/python -m pytest api/test_mcp_long_session.py -q          # ⇒ 5 passed

# ② 真起子进程 + 真协议，且 **stdout 干净**
venv/bin/python -m pytest api/test_mcp_protocol_e2e.py api/test_mcp_stdout_is_clean.py -q  # ⇒ 5 passed

# ③ 全量（CI 的等价物）
bash scripts/ci-local.sh
# ⇒ 858 passed, 2 skipped, 40 deselected（exit 0）
#    ⚠️ 【改前】= 850（`16acb9c`）⇒ +8 = 5(长驻) + 3(stdout 守卫)

# ④ 🔴 **不漏子进程**（本批最担心的一件事）—— ⚠️ 别只查一次
bash scripts/ci-local.sh > /dev/null 2>&1
for i in 1 2 3 4 5 6; do sleep 3; ps -eo command= | grep -c "[m]cp_server.py"; done
# ⇒ 0 0 0 0 0 0
#    ⚠️ **只查一次（尤其 `sleep 2`）会看到"正在退出中"的进程而误报残留** —— 实测踩过

# ⑤ 性能（端到端，非 mock）
cd api && ../venv/bin/python -c "
import asyncio, sys, time; sys.path.insert(0,'.')
from agent_graph_advanced import call_mcp_tool
for i in range(3):
    t=time.time(); call_mcp_tool('calculator', {'expression': f'{i}+1'})
    print(f'{time.time()-t:.4f}s')" 2>/dev/null
```

🔴 **反证**：把 `_McpSessionActor` 换回「每次调用自开自关」⇒ ① 里 `initialize` 会变成 3 次 ⇒ **红**。

⚠️ **两条既有守卫的【自称】本轮被证伪并订正**（`api/test_agent_repairs.py`）：
它们自称钉「`call_mcp_tool` **返回时**已关闭 / 不许改回池化」，
🔵 **实测只检查 `asyncio.run` 结束之后的序列** ⇒ 本批把会话改成长驻（**正是它声称要拦的事**），
**它照样绿**。⇒ 判据已重述（现钉「三层嵌套顺序 + 跑完确实关了」），
而「进入与退出在同一个 task」那条不变量的守卫**搬到了 `test_mcp_long_session.py`**。

---

## 关联

- 📄 **路线裁定（A/B 的母体）** ⇒ `DEC-104`（§2.1 长驻会话 · §2.2 两层拆分）
- 📄 **实测数据（三轮计数 · 84 MB · stdout 现场）** ⇒ `docs/说明/mcp长驻会话-调研-20261008.md`
- 📄 **SDK 2.x 迁移（本批的前提）** ⇒ `DEC-110`
- 📄 **那次栽跟头的两处记录** ⇒ `api/agent_graph_advanced.py` 的 `mcp_session()` docstring
  · `api/test_agent_repairs.py` 的 `test_call_mcp_tool_keeps_session_lifecycle_inside_one_task`
- ⛔ **本批【不含】**「执行统一」（`DEC-104` §2.2 ②）—— 把另外四条链也改走 MCP 会把它们
  从 **~0ms** 变成 **~2s/次**。⚠️ 本批**先把成本降下来**，才有资格谈统一
