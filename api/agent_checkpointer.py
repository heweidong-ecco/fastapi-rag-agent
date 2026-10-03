
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
from datetime import datetime
from safe_math import calculate  # DEC-049：`calculator` 的求值实现 —— ⛔ 别改回 `eval`
from search_tools import web_search  # DEC-051：换掉本机不可达的 DuckDuckGo（见 `agent_graph.py` 同名处）

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
def agent_decide(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    # 统计 Token
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

    ⚠️ 本文件**没有审批节点**（无 `interrupt_before` / 无 `SENSITIVE_TOOLS`）⇒
       这里**不做** `validate_approval_config()` 那种启动自检。
       📌 「`/agent/memory_chat` 这条路径完全没有审批门」是**已知遗留**，见 `DEC-051` 遗留·2。
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

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# ==================== 构建图（支持选择 Checkpointer 后端） ====================
# ======= 支持 MemorySaver SqliteSaver RedisSaver 自主选择架构后端 =======
def build_checkpointer_agent(backend: str = "memory"): # 默认memory即MemorySaver
    workflow = StateGraph(AgentState)
    # 添加节点和边（与基础 Agent 一致：决策 → 工具 → 决策循环）
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
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

    return workflow.compile(checkpointer=checkpointer)

# 全局实例（可通过环境变量 AGENT_CHECKPOINT_BACKEND 切换）
backend = os.getenv("AGENT_CHECKPOINT_BACKEND", "memory")
checkpointer_agent = build_checkpointer_agent(backend=backend)