
import os
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：本行 `SqliteSaver` 从未被使用 ——
#    真正用的是下面函数内那处（同名再导入一次）。
# 新增,RedisSaver 版本不兼容问题还没解决，现在暂时不用
# from langgraph.checkpoint.redis import RedisSaver  
from llm_factory import make_llm   # ①b Task 5：model / api_key / base_url / max_tokens 的唯一落点
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig   # B1：节点要靠它把回调接进模型调用
from datetime import datetime
from safe_math import calculate  # DEC-049：`calculator` 的求值实现 —— ⛔ 别改回 `eval`
from search_tools import web_search  # DEC-051：换掉本机不可达的 DuckDuckGo（见 `agent_graph.py` 同名处）

# 🔴 2026-10-03（`DEC-056` 丙段）：本图**接上审批门**，语义**从 `agent_graph` 引入**。
#    ⛔ **不在这里抄一份** —— 抄一份正是 `DEC-051` 记的病根（同一个判断两处实现，
#       一边改了另一边不知道，而**不一致时不报错** ⇒ 审批静默地永不触发 / 对错的工具触发）。
#    ⚠️ `agent_graph.py` 末行在 **import 期**就跑 `validate_approval_config()` ⇒
#       白名单为空 / 名字不存在，会在这里**一并响亮地报**（不用再调一次）。
from agent_graph import SENSITIVE_TOOLS, should_continue, human_approval

# ==================== 初始化模型 ====================
# ⚠️ 角色 = 「模型轴 fast」+「长度轴 agent(1024)」—— 见 `api/llm_factory.py` 的模块 docstring。
llm = make_llm("fast", "agent")

# ==================== 定义工具 ====================
@tool
def calculator(expression: str) -> str:
    """计算数学表达式，例如 3*4-5/6。"""
    # 🔴 DEC-049：⛔ 不许改回 `eval` —— 理由与实测见 `api/agent_graph.py` 同名处 / `api/safe_math.py`。
    return calculate(expression)

@tool
def date_today(query: str = "") -> str:
    """查询今天的日期、星期几。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekdays[now.weekday()]}"

tools = [web_search, calculator, date_today]
# 🔴 DEC-051：工具名的**唯一来源** —— 分派查这张表，⛔ 别在 `tool_execute` 里再抄一遍名字。
#    ⚠️ 本文件是那次「按 `"search"` 分派、而真名是 `duckduckgo_search`」bug 的**第二处**现场
#       （活路径 = `POST /agent/memory_chat`）。守卫 ⇒ `api/test_tool_dispatch.py`
TOOLS_BY_NAME = {t.name: t for t in tools}

llm_with_tools = llm.bind_tools(tools)

# ==================== 定义 State ====================
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]

# ==================== 定义节点 ====================
from token_tracker import record_usage #Token统计模块
def agent_decide(state: AgentState, config: RunnableConfig):
    """决策节点（`B1` · 2026-10-04 改真流式）。

    🔴 **真流式的唯一条件 = 声明 `config` 并把它转发给模型的 `.stream()`**（`DEC-050`）。
       ⛔ 别改成 `async def` —— 同步的 `graph.invoke()` 会当场抛
       `TypeError: No synchronous function provided to "agent"`，而 `/agent/memory_chat` 在用它。
       （同型实现见 `api/agent_graph.py::agent_decide`，那份是 `DEC-050` 的样板。）
    """
    response = None
    for chunk in llm_with_tools.stream(state["messages"], config=config):
        # ⚠️ 用 `AIMessageChunk.__add__`（`+`）合并，⛔ **不是** `response.content += chunk.content`：
        #    后者会丢掉**碎片化**到达的 `tool_calls`（name 一块、args 几块）
        #    ⇒ `should_continue` 判不出 `"approval"` / `"tools"` ⇒ **审批门静默失效**。
        # 🔴 并且**必须遍历【所有】块**，⛔ 不许跳过 `content` 为空的块 ——
        #    provider 把 `usage_metadata` 挂在**最后一块**（`content=''`）上（实测，
        #    `fastapi-rag-agent-TODO待办/探针-流式与记账.py`）⇒ 跳过它，下面那段记账就没了，
        #    而接口一切正常。
        response = chunk if response is None else response + chunk
    # 统计 Token
    # 🔴 **下面这个判据恒为 False**（既有 bug，⛔ 本轮不修）—— 真 `AIMessage` / `AIMessageChunk`
    #    都**没有** `.usage` 属性（只有 `usage_metadata`）⇒ **本端点的记账从来没执行过**。
    #    ⚠️ 本轮**原样保留**这里的每一个字节：修它会让 `/agent/memory_chat` **开始拦人**
    #       （配额从"形同虚设"变成"真的生效"）—— 那是**行为变更**，要单独裁。
    #    📄 发现经过 ⇒ `fastapi-rag-agent-TODO待办/硬门A-Agent端流式勘察-20261003.md` §8.5
    if hasattr(response, "usage"):
        record_usage(
            # ⚠️ 2026-10-01 修（🅗 S4）：原写死 `"qwen-turbo"`，而本文件的 `llm` 用的是
            #    `LLM_MODEL_FAST`（= DeepSeek）⇒ 金额按**错的单价**记。
            #    改从对象取（照抄 `plan_execute.py:154`）。
            model=getattr(llm, "model_name", None) or getattr(llm, "model", "unknown"),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            purpose="query_rewrite",
        )
    return {"messages": [response]}

def tool_execute(state: AgentState):
    """执行节点。🔴 **DEC-051：按 `TOOLS_BY_NAME` 查表分派** —— 理由与实测见 `agent_graph.py` 同名处。

    ✅ **2026-10-03 更正（`DEC-056` 丙段已修）**：本文件原先**没有审批门**
       （`DEC-051` §遗留·2：「同一个仓里，一条路停下等人批，另一条直接执行」）。
       现在 `build_checkpointer_agent()` 带 `interrupt_before=["approval"]`，
       路由/白名单**从 `agent_graph` 引入**（⛔ 不是抄一份）。
       ⇒ **能走到本节点的 `tool_calls` 都是非敏感的**（敏感的会先停在 `approval`）。
    """
    last_message = state["messages"][-1]
    tool_messages = []
    for tc in last_message.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]
        tool = TOOLS_BY_NAME.get(tool_name)
        result = tool.invoke(tool_args) if tool else f"未找到工具: {tool_name}"
        tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tool_name)
        tool_messages.append(tool_msg)

    return {"messages": tool_messages}

# 🔴 2026-10-03（`DEC-056` 丙段）：本文件原先在这里**自己写了一份** `should_continue`
#    （只有两条路：`tool_calls` ⇒ "tools" / 否则 END）。已删除 —— 改用 `agent_graph` 那一份
#    （三条路，含 `"approval"`）。理由：审批的判据只能有**一处**，见文件顶部 import 处的注释。

# ==================== 流式白名单（B1 · 2026-10-04）====================
# 🔴 **`B1`：可流节点名单放在【图模块里】，⛔ 端点不许自己抄一份字面量**（理由见
#    `api/agent_graph.py` 同名常量处 —— 一个名字两个来源必然漂移，而漂移是**静默**的）。
# ⚠️ 必须放在**模块级**（⛔ 不能放进 `build_checkpointer_agent()`）：端点是按
#    `agent_checkpointer.STREAMABLE_NODES` 取的，函数体里的是局部名，外面拿不到。
# ⛔ `tools` / `approval` **不在**里面：它们不调 LLM（无字可流），
#    而 `tools` 返回的 `ToolMessage` 会被当成"新消息"发出来 ⇒ 混进正文（实测）。
STREAMABLE_NODES = frozenset({"agent"})


# ==================== 构建图（支持选择 Checkpointer 后端） ====================
# ======= 支持 MemorySaver SqliteSaver RedisSaver 自主选择架构后端 =======
def build_checkpointer_agent(backend: str = "memory"): # 默认memory即MemorySaver
    workflow = StateGraph(AgentState)
    # 添加节点和边（与基础 Agent 一致：决策 → 工具 → 决策循环）
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    # 🔴 2026-10-03（`DEC-056` 丙段）：审批节点 —— 与 `agent_graph` 同形（三条路由 + `interrupt_before`）。
    workflow.add_node("approval", human_approval)
    workflow.set_entry_point("agent")
    # ⚠️ 映射必须**写全三条**：`should_continue` 现在会返回 `"approval"`，
    #    少了它 langgraph 会以 "unknown branch" 抛错（不是静默走默认）。
    workflow.add_conditional_edges(
        "agent", should_continue,
        {"approval": "approval", "tools": "tools", END: END},
    )
    # 审批通过后，从 "approval" 去 "tools" 执行（与 `agent_graph` 同）
    workflow.add_edge("approval", "tools")
    workflow.add_edge("tools", "agent")

    # 根据后端选择 Checkpointer
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = os.path.join(os.path.dirname(__file__), "agent_history.db")
        checkpointer = SqliteSaver.from_conn_string(db_path)
    elif backend == "redis":
        # ⚠️ 2026-09-20 删（D1/pyflakes：局部变量赋值后从未使用）：此处原有
        #       redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        #    它**只被下面那行注释掉的代码用过** ⇒ 是死变量。
        # 新增,RedisSaver 版本不兼容问题还没解决，现在暂时不用
        # checkpointer = RedisSaver.from_conn_string(redis_url)
        checkpointer = MemorySaver()  # 暂以内存兜底，避免编译空图
    else:  # 默认 memory
        checkpointer = MemorySaver()

    # 🔴 `interrupt_before=["approval"]` —— 进入审批节点**之前**暂停（与 `agent_graph` 同）。
    #    ⚠️ 少了这个参数，`approval` 节点会被**直接走进去**（它什么也不做）⇒ 门形同虚设。
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["approval"])

# 全局实例（可通过环境变量 AGENT_CHECKPOINT_BACKEND 切换）
backend = os.getenv("AGENT_CHECKPOINT_BACKEND", "memory")
checkpointer_agent = build_checkpointer_agent(backend=backend)