# 决策记录：DEC-066 · **第 6 份 `calculator` 还留着 `eval`** —— 守卫的**形状盲区**，且**匿名 WS 可达**

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施**（2026-10-04） |
| **触发** | 业务方追问「`get_weather` / `calculator` 怎么没有消费者」⇒ 顺着核账时挖出来 |
| **类型** | 🔴 **安全收口**（`DEC-049` 同一根因的**第 6 处**）+ **守卫判据修正** |
| **落点** | `api/api_v1_rag.py` · `api/test_safe_math_wiring.py` · `docs/specs/safe_math.md` |

---

## 一 · 它是什么

`api/api_v1_rag.py` 的 `get_agent_executor()` 里，**本地又定义了一套 tools**（第 6 份拷贝），其中：

```python
@tool
async def calculator(expression: str) -> str:
    """计算一个数学表达式。例如3*4-5/6。输入的必须是纯数学表达式"""
    result = await asyncio.to_thread(eval, expression)   # 🔴 这一行
    return str(result)
```

**三条，都可打印地核过**：

### 1. 它是 `DEC-049` 修过的那同一个洞

`DEC-049` 把 `eval(expression)` 换成 `safe_math.calculate`（AST 白名单求值），理由是
**`expression` 是 LLM 生成的，而 LLM 的输入含用户提问 / RAG 文档 / 搜索结果** ——
`eval` 等于**把任意代码执行开在服务进程里**。本处**一个字没改**。

### 2. 它**真的会执行** —— 实测，不是推断

我按**完全相同的调用形状**跑了一次：

```bash
$ ../venv/bin/python -c "
  import asyncio
  async def m():
      return await asyncio.to_thread(eval, \"__import__('os').system('touch /tmp/probe_eval_bypass_marker')\")
  print(asyncio.run(m()))"
0                                  # ← system() 的返回值被 str() 成 "0"
$ ls /tmp/probe_eval_bypass_marker
/tmp/probe_eval_bypass_marker      # ← 命令真的跑了
```

⚠️ **这个签名与 `DEC-049` 记下的一模一样**（原话：「返回的是 `'0'` ⇒ 命令执行成功，
而**模型收到的是一条正常的"答案是 0"**」）—— **没有任何异常信号**。

### 3. 它是**匿名可达**的

```
匿名连 ws://<host>/api/v1/ws/agent
  → api_v1_rag.py:884  get_agent_executor()
  → AgentExecutor(tools=[calculator, date_today, search])
  → LLM 被诱导调用 calculator(恶意表达式)
  → :801 eval 在服务进程里执行
```

- 🔴 **该 WS 整条没有鉴权** —— 代码自己的注释写着（`api_v1_rag.py:836-840`），
  `DEC-041 §遗留·1` 也记着，**至今挂着**。
- 🔴 **`scripts/check_route_auth.py` 结构上就看不见它** —— 它的扫描只认 `APIRoute`（`:70`），
  **WebSocket 不在范围内** ⇒ 那份「无鉴权路由」审计**从来覆盖不到 WS**。
- ⚠️ **⛔ 不是"要用户自己输 payload"**：`expression` 是 **LLM 生成**的，
  而 `search` 工具会把**外部网页内容**拉进 LLM 的上下文 ⇒ 这是**间接提示注入**面。

> 📌 **引入时间**：`git log -S 'asyncio.to_thread(eval' -- api/api_v1_rag.py` ⇒ **`2c1a922`（2026-07-17）**。

---

## 二 · 🔴 最值钱的一条：**守卫为什么看不见它**

`DEC-049` 配了两道闸（`api/test_safe_math_wiring.py`），其中一道的**自述**是：

> 「防止"第 6 份拷贝"：**全仓扫一遍**，谁再写裸 `eval` 就当违规。」

**它扫了，它返回空。** 因为判据是**形状**写死的：

```python
isinstance(node, ast.Call)
and isinstance(node.func, ast.Name)
and node.func.id == "eval"
```

—— 这认的是 **`eval(x)`**（被调用的目标就是裸名 `eval`）。
而本处写的是 **`asyncio.to_thread(eval, expression)`**：**`eval` 是实参**，
`ast.Call` 的 `func` 是 `asyncio.to_thread`。⇒ **两道闸都返回空。**

实测（把两种形状并排扫一遍）：

```
守卫(ast.Call + Name==eval) 能抓到的： 【空】
eval 作为【参数】传出去的： ['api_v1_rag.py:801  asyncio.to_thread(eval, expression)']
```

### ⚠️ 这条比"修一个洞"值钱

它推翻了**守卫自己的那句自述**（`test_no_other_module_defines_an_eval_based_calculator` 的 docstring 写着「全仓扫一遍」，
而 `docs/specs/safe_math.md` 与 `docs/说明/测试.md` 都据此写过「**整个 `api/` 里没有 `eval` 调用**」）——
**那句话是假的，而闸是绿的。**

🔴 **同族**（本仓今天已经栽过一次同型）：
- `DEC-061` · **「幽灵锚点」** —— 一句「判据」指向**根本不存在**的用例；
- `DEC-065` · **空清单 = 静默假通过** —— 守卫的 `for` 体从不执行，永远是绿的。

⇒ **共同的形状**：**「门上看得出挂着锁」≠「锁真的在那个位置」。**
⚠️ 而本条的**判据错在「形状」，不在「名单」** —— 所以本文**不是**再加一条规矩，
是**把判据换成一个抓不到边界的形状**（见 §三）。

---

## 三 · 裁决与做法

### 3.1 TDD：**RED ⇒ GREEN**

**RED（先改判据，先看它红）** —— 把检测抽成**唯一一个函数** `eval_name_offenders()`，
两条闸都调它（⛔ 不许各写一份，那正是漂移的来源）。新判据：

```python
isinstance(node, ast.Name) and node.id == "eval"
```

—— **只要这个名字被读出来就报**，与它的**调用形状无关**：
`eval(x)` ✅ · `to_thread(eval, x)` ✅ · `f = eval` ✅。
⚠️ **⛔ 不会误伤 `redis_client.eval(...)`**（`api/rate_limiter.py` 真家伙）——
它的 `eval` 是 `ast.Attribute.attr`，**不是** `ast.Name`。

跑一次，**红在它该红的地方**：

```
E  AssertionError: 🔴 全仓还有裸名 `eval` —— 每多一处，就是一个未收口的任意代码执行面：['api_v1_rag.py:801']
```

**GREEN（再收口那一处）** —— 两行：

| 行 | 改前 | 改后 | 依据 |
|---|---|---|---|
| `:801` | `await asyncio.to_thread(eval, expression)` | `await asyncio.to_thread(calculate, expression)` | `DEC-049` |
| `:793` | `DuckDuckGoSearchRun()` | `search_tools.web_search.invoke` | `DEC-051` |

⚠️ **第二行不是"顺手"**：`api/search_tools.py:47` 记着 2026-09-21 的实测 ——
`duckduckgo.com` **本机完全不通**（`cn.bing.com` 是当时唯一可达的）
⇒ 旧写法在**本机部署下必定失败**，`/ws/agent` 的搜索**每次都返回失败**。
**两条改动同一个主题**：*这条遗留链的本地工具集，是第 6 份手抄的拷贝，已经和别处漂开了。*

### 3.2 判据（可打印）

```bash
# ① 守卫：改前红（列出 api_v1_rag.py:801）⇒ 改后绿
venv/bin/python -m pytest api/test_safe_math_wiring.py -q            # ⇒ 1 failed ⇒ 23 passed
# ② 替换形状真的可用（两条都实测过）
venv/bin/python -c "…asyncio.to_thread(calculate, 恶意表达式)…"       # ⇒ '计算错误: …' · 标记文件【没】被创建
venv/bin/python -c "…asyncio.to_thread(calculate, '6*7')…"           # ⇒ '42'（功能没被一起收掉）
venv/bin/python -c "…web_search.invoke('test')…"                     # ⇒ '搜索「test」的结果（共 8 条）…'
# ③ 全量
venv/bin/python -m pytest api/ -q -m "not integration and not needs_db"   # ⇒ 518 passed, 3 skipped, 31 deselected
```

---

## 四 · 改了哪几处

| # | 位置 | 改了什么 |
|---|---|---|
| ① | `api/api_v1_rag.py` `:793` | `DuckDuckGoSearchRun` → `search_tools.web_search` |
| ② | `api/api_v1_rag.py` `:801` | `eval` → `safe_math.calculate`（**本份的主改动**） |
| ③ | `api/api_v1_rag.py` 函数内 import | 去 `langchain_community.tools`，加 `safe_math` / `search_tools` |
| ④ | `api/test_safe_math_wiring.py` | 抽出 `eval_name_offenders()`，**两条闸共用**；判据由「调用的形状」换成「**名字本身**」 |
| ⑤ | `docs/specs/safe_math.md` | 「谁在用」**5 处 → 6 处**；⚠️ 表里补一行「**形状盲区**」 |
| ⑥ | `docs/说明/测试.md` | ⚠️ 两处「全仓没有 `eval`」的话**改成实测口径**（那是**假判据**，见 §二） |
| ⑦ | `CHANGELOG.md` | `[Unreleased] → ### Fixed` |

⚠️ **⛔ 没有动 `/ws/agent` 的鉴权** —— 见 §五。

---

## 五 · ⚠️ 本份【没有】解决什么（**别读成"这条链干净了"**）

1. 🔴 **`/api/v1/ws/agent` 整条仍然没有鉴权** —— `DEC-041 §遗留·1`，本份**没碰**。
   本份只保证：**就算匿名连上，`calculator` 那条路不再是 RCE**。
   ⚠️ **「堵了 RCE」≠「这条链安全了」** —— 匿名仍然可以**无限烧 token**（B8 上限**按连接**算，
   换连接 = 换桶，因为**没有身份就谈不上按人计**）。
2. ⚠️ **本处的 `calculator` 没有被行为测试覆盖，且做不到** —— 它是 `get_agent_executor()`
   的**嵌套函数**，**import 不到**。⇒ 它只有**静态那道闸**。
   📌 与 `tools_with_cache.calculator` 同型（那份是**够不着 Redis**），但**成因不同**：
   那份是"调一次要连 Redis"，这份是"**在函数体里，取不到**"。
   ⇒ **如实写在这里，⛔ 不假装它也验了行为。**
3. ⚠️ **端到端（真 LLM + 真 WS 走通一次）我没跑** —— 我验的是**调用形状等价性** +
   `calculate` 的替换形状可用。真链路要真模型、**花钱**。
4. ⚠️ **`/ws/agent` 那条链还有别的遗留**（`date_today` 也是第 N 份手抄副本；
   `search` 的**召回源**与别处不同）—— 本份**只收口了安全那一条**，⛔ 不顺手整理。

---

## 六 · 反悔成本（**低**）

| 想反悔什么 | 代价 |
|---|---|
| 把 `eval` 改回来 | 🟡 **技术上一行**，但**判据会立刻拦**（新守卫抓 `ast.Name`）⇒ 要先删判据 = **动作显式、不可静默** |
| 把守卫判据改回"只看 `eval(...)`" | 🔴 **不建议**：那正是本份的成因。改回去 = 把 `to_thread(eval, …)` 这一类**重新变成盲区** |
| 把 `search` 改回 DuckDuckGo | 🟡 一行；⚠️ 但 `duckduckgo.com` 在本机**仍然不通**（`DEC-051`），改回去就是**恢复一个必定失败的搜索** |

---

## 七 · 关联

| 文档 | 说明 |
|---|---|
| 🔵 **`docs/decisions/DEC-049-calculator的eval换成AST白名单求值.md`** | ⭐ **同一根因的先例** —— 本份是它的**第 6 处遗漏**；§遗留 2（`tools_with_cache` 只有静态闸）与本份 §五·2 同型 |
| 🔵 **`docs/decisions/DEC-051-…`** | `search_tools.web_search` 换掉 DuckDuckGo 的那次（本份第二处改动照它） |
| 🔵 **`docs/decisions/DEC-061-判据必须钉在真实存在的用例上.md`** | ⭐ **同族** —— 「以为门上挂着锁」（幽灵锚点） |
| 🔵 **`docs/decisions/DEC-065-…`** | ⭐ **同族** —— 「空清单 = 静默假通过」 |
| `docs/decisions/DEC-041-…` §遗留·1 | 🔴 **`/ws/agent` 无鉴权** —— 本份**没解决**，仍开着 |
| `docs/specs/safe_math.md` | 收口清单（**5 → 6 处**）+ 新增「形状盲区」行 |
| `docs/说明/测试.md` | ⚠️ 两处「全仓没有 `eval`」的**假判据**（本份更正） |
| `api/test_safe_math_wiring.py` | 两道闸 + **共用的检测函数** `eval_name_offenders()` |

## 变更记录

- 2026-10-04 建立（实施同日）。触发：业务方追问「`get_weather` / `calculator` 怎么没有消费者」——
  核账时发现**真问题不是"没有消费者"，是"有一份还在 `eval`"**。
  ⚠️ 同批另裁：**`/ws/agent` 的鉴权【分开做】**（先堵 RCE），本份按此执行。
