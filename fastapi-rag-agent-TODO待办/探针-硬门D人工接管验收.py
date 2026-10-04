#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探针 · **硬门 D 端到端验收** —— 人工接管三条出口 + 「接管后上下文连续」（2026-10-04）

    # ⚠️ 先起服务（`docker compose up -d api`），再跑：
    ./venv/bin/python "fastapi-rag-agent-TODO待办/探针-硬门D人工接管验收.py"

🔴 **本探针【真打 API】**（每轮约 10–20 次真实 LLM 调用 · 联网花钱）——
   ⛔ **别塞进 `pytest`**（会变成 CI 里花钱 + 要 key 的用例）。
   ⛔ **也别拿假模型替它** —— 它要验的恰恰是**假模型验不了**的那一格（见下）。

📌 **它存在的理由**：`api/test_approval_resume.py` 的 `B6` 那 6 条用的是**假图** ——
   **不校验消息结构**、假 `invoke` **不会有"下一轮"**。而硬门 D 的
   **证真②（接管后会话上下文连续）只有真模型跑得出来**：真网关会校验
   「带 `tool_calls` 的 assistant 消息后面必须跟配对的 tool 消息」，
   假图那条路**永远不会**报 400。**实测就是这样**：单测 21 条全绿，真服务三条出口全坏（`DEC-062`）。

判据来源 ⇒ `fastapi-rag-agent-TODO待办/通用/四硬门-定义与验收标准.md` §硬门 D
  **证真①**：接管事件有记录（**谁 / 何时 / 为什么**）
  **证真②**：接管后会话**上下文连续**

覆盖：**三条出口**（改写放行 / 原样放行 / 拒绝）各起一条独立会话，**每条之后在同一 `thread_id` 上再问一句**；
      并覆盖「**批了但它又停在审批点**」⇒ 必须**重新入队**（2026-10-04 之前的孤儿会话来源）。

---

## 实测结果

### 2026-10-04 · 修复【前】（`main@51376d0` · 真 DeepSeek · 真 `MemorySaver`）

**证真① 过 · 证真② 不过** —— 三条出口**每一条都会把会话弄坏**：

| 出口 | 实测 | 后果 |
|---|---|---|
| 改写后放行 | `approve` **0.017s** 返回 200、`answer` **= 输入原文** | 图**当场 END**（`tools`/`agent` 一个都没跑） |
| 原样放行（放行后模型**又**要敏感工具） | `answer=""`、图**仍停在审批点**，而队列**已被清空** | 🔴 **孤儿会话**（查不到、批不了） |
| 拒绝 | `answer` = **内部指令原文照抄吐给用户** | 界面上弹出一句写给模型看的话 |

**三条共通的硬症状**：同 `thread_id` 再问一句 ⇒ **HTTP 500**
（`OpenAI 400: An assistant message with 'tool_calls' must be followed by tool messages`）。
⚠️ **而单测全程 21 条绿。**

### 2026-10-04 · 修复【后】（`DEC-062`：A+B+C）

**22/22 通过**（本文件原样跑出来的）：
- 证真① 谁=admin · 何时 · **为什么** = `['date_today', 'web_search']` ✅
- 证真② **三条出口之后，同一 thread 都还能复述第一问** ✅
- 🔴 场景 2 里模型**连续 3 次**放行后又要求审批 ⇒ **每次都重新入队**（改前这正是最常踩的孤儿路径）✅

⚠️ **分母不是固定值** —— 复跑第二次是 **19/19 · 0 失败**。原因：有几条断言写在
「`while j['status'] == 'pending_approval'`」那个循环里，而**模型这次要不要"再要一次审批"不确定**
⇒ 分母随运行变化。**判据看的是"有没有 🔴"**，⛔ 别拿分母当固定分数比。

📄 全文（根因 · 否掉的 4 个备选 · 边界 4 条）⇒ `docs/decisions/DEC-062-人工接管三条出口都破坏会话.md`
"""
import json
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
# ⚠️ `.env` 按**本文件位置**推（⛔ 不写死绝对路径 —— 换机器/换检出目录就跑不了）。
ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
RESULT = []


def env(key):
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    raise KeyError(key)


def jprint(tag, r, dt):
    try:
        j = r.json()
    except Exception:
        j = {"_raw": r.text[:200]}
    print(f"  [{tag}] HTTP {r.status_code} · {dt:.1f}s")
    print("   " + json.dumps(j, ensure_ascii=False)[:400])
    return r.status_code, (j if isinstance(j, dict) else {})


def note(ok, label, detail=""):
    RESULT.append((ok, label, detail))
    print(f"  {'✅' if ok else '🔴'} {label}" + (f" —— {detail}" if detail else ""))


def main():
    c = httpx.Client(timeout=180.0)
    r = c.post(f"{BASE}/auth/login", json={
        "user_name": env("LOGIN_USER_NAME"), "password": env("LOGIN_PASSWORD")})
    assert r.status_code == 200, f"登录失败 {r.status_code} {r.text[:200]}"
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    print(f"✅ 登录成功（user={env('LOGIN_USER_NAME')}）")

    def pending_of(tid):
        j = c.get(f"{BASE}/agent/pending", headers=H).json()
        return j.get("count"), [x for x in j.get("items", []) if x.get("raw_thread_id") == tid]

    def ask(tid, q):
        t0 = time.time()
        return jprint("chat", c.post(f"{BASE}/agent/langgraph_chat",
                                     params={"question": q, "thread_id": tid}, headers=H),
                      time.time() - t0)

    def approve(tid, **kw):
        p = {"thread_id": tid, "approved": "true"}
        p.update(kw)
        t0 = time.time()
        return jprint("approve", c.post(f"{BASE}/agent/approve", params=p, headers=H),
                      time.time() - t0)

    RUN = str(int(time.time()))          # ⚠️ 独占：MemorySaver 持久，复用 thread_id 会读上一轮的状态
    Q1 = "请用搜索工具帮我查一下「2026年诺贝尔文学奖得主」，把搜索到的结果告诉我。"
    Q2 = "请原样复述我在这段会话里问你的【第一个问题】的原文，不要添加任何解释。"

    # ════════════════════════════════════════════════════════════════
    # 场景 1 · 改写后放行
    # ════════════════════════════════════════════════════════════════
    print("\n" + "═" * 74 + "\n场景 1 · 改写后放行\n" + "═" * 74)
    T1 = f"acc-v2-edit-{RUN}"
    st, j = ask(T1, Q1)
    note(j.get("status") == "pending_approval", "Q1 触发审批", f"status={j.get('status')}")

    # 证真①
    cnt, mine = pending_of(T1)
    if mine:
        row = mine[0]
        note(bool(row.get("user_name")) and bool(row.get("since")) and bool(row.get("tool_calls")),
             "证真① 接管事件有记录（谁/何时/为什么）",
             f"谁={row.get('user_name')} 何时={time.strftime('%H:%M:%S', time.localtime(row['since']))} "
             f"为什么={[t['name'] for t in row['tool_calls']]}")
    else:
        note(False, "证真① 队列里找不到这条", f"count={cnt}")

    EDITED = "（人工代答）2026年诺贝尔文学奖得主是「林昭华」。"
    st, j = approve(T1, edited_answer=EDITED)
    note(st == 200 and j.get("status") in ("approved", "pending_approval"),
         "approve 没报错", f"status={j.get('status')}")
    # ⚠️ 改写生效要判**最终那条终答**，⛔ 不是第一次 approve 的返回 ——
    #    第一次很可能又停下（`answer=""`），人写的内容要等模型真答完才看得到。
    answers = [j.get("answer") or ""]
    # 若又停下 ⇒ 必须已重新入队（这就是改前的孤儿会话）
    while j.get("status") == "pending_approval":
        cnt, mine = pending_of(T1)
        note(bool(mine), "🔴 又停在审批点 ⇒ **已重新入队**（改前=孤儿会话）", f"count={cnt}")
        st, j = approve(T1)                     # 原样放行，直到走完
        answers.append(j.get("answer") or "")
    last = answers[-1]
    note("林昭华" in last, "🔴 人写的结论真的传到了模型（终答里带出来了）", repr(last)[:200])
    cnt, mine = pending_of(T1)
    note(not mine, "走完后队列里已清掉", f"count={cnt}")

    st, j = ask(T1, Q2)
    note(st == 200, "🔴 证真② 接管后同一 thread 仍可用（改前必 500）", f"HTTP {st}")
    note("诺贝尔文学奖" in (j.get("answer") or ""),
         "🔴 证真② 上下文连续 —— 追问能复述第一问", repr(j.get("answer", ""))[:200])

    # ════════════════════════════════════════════════════════════════
    # 场景 2 · 原样放行（模型很可能又一次要求敏感工具）
    # ════════════════════════════════════════════════════════════════
    print("\n" + "═" * 74 + "\n场景 2 · 原样放行\n" + "═" * 74)
    T2 = f"acc-v2-pass-{RUN}"
    st, j = ask(T2, Q1)
    note(j.get("status") == "pending_approval", "Q1 触发审批", f"status={j.get('status')}")
    rounds = 0
    st, j = approve(T2)
    while j.get("status") == "pending_approval" and rounds < 4:
        rounds += 1
        cnt, mine = pending_of(T2)
        note(bool(mine), f"第 {rounds} 次「又停下」⇒ 已重新入队", f"count={cnt}")
        st, j = approve(T2)
    note(j.get("status") == "approved", "最终走完", f"status={j.get('status')} 轮数={rounds}")
    print(f"  ℹ️ 观察：模型放行后又要求过审批 {rounds} 次"
          + ("（本次覆盖到了改前最常见的孤儿路径）" if rounds else
             "（本次没复现；场景 1 的第一轮已覆盖过一次）"))
    st, j = ask(T2, Q2)
    note(st == 200 and "诺贝尔文学奖" in (j.get("answer") or ""),
         "🔴 证真② 原样放行后 thread 连续", f"HTTP {st} {repr(j.get('answer',''))[:150]}")

    # ════════════════════════════════════════════════════════════════
    # 场景 3 · 拒绝
    # ════════════════════════════════════════════════════════════════
    print("\n" + "═" * 74 + "\n场景 3 · 拒绝\n" + "═" * 74)
    T3 = f"acc-v2-reject-{RUN}"
    st, j = ask(T3, Q1)
    note(j.get("status") == "pending_approval", "Q1 触发审批", f"status={j.get('status')}")
    t0 = time.time()
    st, j = jprint("reject", c.post(f"{BASE}/agent/approve",
                                    params={"thread_id": T3, "approved": "false"}, headers=H),
                   time.time() - t0)
    ans = j.get("answer") or ""
    note(st == 200 and j.get("status") in ("rejected", "pending_approval"),
         "拒绝返回得体的 status", f"status={j.get('status')}")
    note("请不要再调用它" not in ans, "🔴 拒绝终答里没有那条内部指令原文", repr(ans)[:200])
    note("拒绝" in ans, "拒绝语义传达到了", repr(ans)[:200])
    st, j = ask(T3, Q2)
    note(st == 200, "🔴 证真② 拒绝后 thread 仍可用", f"HTTP {st}")
    note("诺贝尔文学奖" in (j.get("answer") or ""),
         "🔴 证真② 拒绝后上下文连续", repr(j.get("answer", ""))[:200])

    # ════════════════════════════════════════════════════════════════
    bad = [x for x in RESULT if not x[0]]
    print("\n" + "═" * 74)
    print(f"小结：{len(RESULT) - len(bad)}/{len(RESULT)} 通过")
    for _, label, detail in bad:
        print(f"  🔴 {label} —— {detail}")
    print("═" * 74)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
