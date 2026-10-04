"""探针 · **真流式**在「子图」与「节点返回值」两个维度上的实测行为（2026-10-04）。

    ./venv/bin/python "fastapi-rag-agent-TODO待办/探针-真流式与子图.py"

⛔ 不联网、不花钱（假模型）。⛔ 不 import 本仓任何模块（只为隔离 langgraph 自身行为）。
📌 **它存在的理由**：`DEC-050` 的探针**没测过子图**，而 `advanced_chat` 整条链
   **是 5 个部门子图拼的**（`agent_graph_advanced_learning.py:352-356`）。
   不测这一步，就会照着 `DEC-050` 的 diff 去改，**改完接口一切正常、而一个字都不流**。

---

## 实测结果（2026-10-04 · 本机）

| # | 节点返回值 | 在子图里？ | `subgraphs` | **块数** | 节点名 |
|---|---|---|---|---|---|
| ① | 返回 `messages` | 否 | False | **3** ✅ | `chat` |
| ② | 返回 `messages` | **是** | False | **1** ⚠️ | **外层名** `dept` |
| ③ | 返回 `messages` | **是** | **True** | **3** ✅ | **内层名** `dept` |
| ④ | **只写 `final_output`** | 否 | False | **3** ✅ | `chat` |
| ⑤ | **只写 `final_output`** | **是** | False | **0** ❌ | — |
| ⑥ | **只写 `final_output`** | **是** | **True** | **3** ✅ | 内层名 `dept` |

### 三条结论

1. 🔴 **子图必须开 `subgraphs=True`** —— 否则：
   * 节点返回 `messages` 时，只收到**子图节点的返回值**（**1 块整段**，node 名是**外层**名）；
   * 节点**不**返回 `messages`（= `chat_node` / `translate_execute` / `calc_execute` /
     `search_summarize` 的现状）时，**一块都没有**。
2. ✅ **节点返回什么【不影响】流式**（① vs ④、③ vs ⑥）——
   token 来自 `on_llm_new_token`，与节点往 state 里写了什么无关。
   ⇒ **不必为了流式去改 `advanced_chat` 各节点的返回值**（那会是行为变更）。
3. ⚠️ **`subgraphs=True` 会换掉产出的形状**：由 `(chunk, meta)` 变成 `(namespace, (chunk, meta))`
   —— 共享层要认这个形状，而**只有 `advanced_chat` 这一条链需要**。

### 一条必须记住的副作用

`subgraphs=True` 之后，**子图内每一个调 LLM 的节点**都会出块 ——
包括 `supervisor`（输出**路由词** `SEARCH`/`CALCULATOR`/…）和
`calc_execute`（只**提取表达式**，如 `6*7`）。
⇒ **节点名白名单不是可选项**（见 `api/agent_graph_advanced_learning.py` 的 `STREAMABLE_NODES`）。

---

## ⚠️ 本探针**没有**证明的（别拿它当结论）

* 真服务的行为（本探针是进程内的假模型）。**取消/断连那一侧仍要真服务验**（`DEC-054` 的教训）。
* `usage_metadata` 在流式聚合后还在不在 —— **没测**，那是 `plan_execute` 的记账问题。
* 本仓三张真图的**节点名清单** —— 由 `grep add_node` 独立核过，⛔ 不是本探针给的。
"""
import asyncio
from typing import Annotated, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.graph import END, StateGraph

try:
    from langgraph.graph.message import add_messages
except ImportError:  # 老版路径
    from langgraph.graph import add_messages


# ==================== 假模型（⛔ 不联网） ====================

class Fake(BaseChatModel):
    reply: str = "你好呀"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _stream(self, messages, stop=None, run_manager=None, **kw):
        for ch in self.reply:
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])


M = Fake()


class S(TypedDict):
    messages: Annotated[list, add_messages]
    final_output: str


def _consume_and_aggregate(state, config):
    """`DEC-050` 采纳的写法：`.stream(..., config=config)` + **`+` 聚合**。"""
    resp = None
    for c in M.stream(state["messages"], config=config):
        resp = c if resp is None else resp + c
    return resp


def make_node(returns_message: bool):
    """`returns_message=False` 复刻 `chat_node` 的现状：**只写 `final_output`**。"""
    def node(state: S, config):
        resp = _consume_and_aggregate(state, config)
        text = getattr(resp, "content", "") or ""
        if returns_message:
            return {"messages": [resp], "final_output": text}
        return {"final_output": text}
    return node


# ==================== 六个剧本 ====================

async def run(label, returns_message, in_subgraph, **kw):
    inner = make_node(returns_message)
    if in_subgraph:
        sub = StateGraph(S)
        sub.add_node("dept", inner)
        sub.set_entry_point("dept")
        sub.add_edge("dept", END)

        parent = StateGraph(S)
        parent.add_node("dept", sub.compile())   # ← 子图挂成一个节点
        parent.set_entry_point("dept")
        parent.add_edge("dept", END)
        g = parent.compile()
    else:
        g = StateGraph(S)
        g.add_node("chat", inner)
        g.set_entry_point("chat")
        g.add_edge("chat", END)
        g = g.compile()

    rows = []
    async for item in g.astream(
        {"messages": [HumanMessage(content="hi")]},
        config={"configurable": {"thread_id": label}},
        stream_mode="messages",
        **kw,
    ):
        # subgraphs=True ⇒ (namespace, (chunk, meta))；否则 (chunk, meta)
        ns, (chunk, meta) = item if isinstance(item[0], tuple) else (None, item)
        rows.append((meta.get("langgraph_node"), repr(chunk.content)))

    print(f"\n{label}")
    for node, content in rows:
        print(f"    node={node!r} content={content}")
    print(f"  ⇒ 块数 {len(rows)}   （3 = token 级真流式 · 1 = 整段 · 0 = 什么都流不出来）")


async def main():
    await run("① 返回 messages · 非子图 · subgraphs=False", True, False)
    await run("② 返回 messages · 子图   · subgraphs=False", True, True)
    await run("③ 返回 messages · 子图   · subgraphs=True ", True, True, subgraphs=True)
    await run("④ 只写 final_output · 非子图 · subgraphs=False", False, False)
    await run("⑤ 只写 final_output · 子图   · subgraphs=False", False, True)
    await run("⑥ 只写 final_output · 子图   · subgraphs=True ", False, True, subgraphs=True)


if __name__ == "__main__":
    asyncio.run(main())
