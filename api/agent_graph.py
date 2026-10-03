"""
LangGraph Agent 示例：基于图结构的智能助理
"""
import os
import json
import asyncio
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from llm_factory import make_llm   # ①b Task 5：model / api_key / base_url / max_tokens 的唯一落点
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig   # B1：节点要靠它把回调接进模型调用
from datetime import datetime
from safe_math import calculate  # DEC-049：`calculator` 的求值实现 —— ⛔ 别改回 `eval`

# ==================== 初始化模型 ====================
# ⚠️ 角色 = 「模型轴 fast」+「长度轴 agent(1024)」—— 见 `api/llm_factory.py` 的模块 docstring。
llm = make_llm("fast", "agent")

# ==================== 定义工具 ====================
@tool
def calculator(expression: str) -> str:
    """计算数学表达式，例如 3*4-5/6。"""
    # 🔴 DEC-049：**不许改回 `eval(expression)`**。
    #    `expression` 是 LLM 生成的，而 LLM 的输入包含用户提问 / RAG 文档 / 搜索结果
    #    ⇒ `eval` 等于把任意代码执行开在服务进程里。实测（改前）：喂
    #    `__import__('os').system('touch /tmp/x')` **命令真的跑了**，返回 `'0'`
    #    —— 模型收到的是一条正常的"答案是 0"，没有任何异常信号。
    #    ⇒ 实现与三道闸见 `api/safe_math.py`；接线由 `api/test_safe_math_wiring.py` 守。
    return calculate(expression)

@tool
def date_today(query: str = "") -> str:
    """查询今天的日期、星期几。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekdays[now.weekday()]}"

search_tool = DuckDuckGoSearchRun()
tools = [search_tool, calculator, date_today]

# 将工具绑定到模型，这样模型就知道可以调用哪些工具
llm_with_tools = llm.bind_tools(tools)

# ==================== 审批白名单（B4）====================
# 🔴 改前：**只要产生任意 tool_calls 就进审批** ⇒ 问一句"今天几号"也会停下来等人批。
#    硬门 D 要的是「**该被接管时被接管**」，⛔ 不是「全都接管」。
# ⚠️ 它是**白名单**：没登记的工具**默认不敏感** ⇒ **新加的工具默认不过审批**。
#    要它过，就把名字加进 `.env` 的 `SENSITIVE_TOOLS`（逗号分隔）。
# 📄 裁定 ⇒ `fastapi-rag-agent-TODO待办/后端补齐清单-待裁-20260929.md` B4 · 📌 判据 ⇒ `api/test_approval_trigger.py`
SENSITIVE_TOOLS: frozenset[str] = frozenset(
    n.strip() for n in os.getenv("SENSITIVE_TOOLS", "search_tool").split(",") if n.strip()
)


def validate_approval_config() -> None:
    """启动自检：白名单**不许为空**。

    🔴 空 ⇒ 审批**永不触发** ⇒ 硬门 D 名存实亡 —— 而且**不会有任何报错**，
       要等人验收时才发现「接管从来没发生过」。⇒ 让它在**启动时就报**。
    """
    if not SENSITIVE_TOOLS:
        raise EnvironmentError(
            "SENSITIVE_TOOLS 为空 —— 人工审批将永不触发（硬门 D 名存实亡）。"
            " 请在 .env 里写明需要审批的工具名（逗号分隔），例如 SENSITIVE_TOOLS=search_tool"
        )

# ==================== 定义 Agent 的状态 ====================
class AgentState(TypedDict):
    # 对话历史消息列表。operator.add 表示新消息会被追加到末尾，而不是覆盖。
    messages: Annotated[List, operator.add]

# ==================== 定义节点函数 ====================
def agent_decide(state: AgentState, config: RunnableConfig):
    """
    决策节点：调用模型，让它决定是回复文本还是调用工具。

    🔴 **B1（2026-10-03）：本节点必须"声明 `config` + 转发给模型的流式调用"** ——
       这是 `astream(..., stream_mode="messages")` 出不出 token 的**唯一条件**。
       实测（假模型探针，见 `api/test_agent_sse.py` 文件头）：

       | 写法 | `astream(stream_mode="messages")` |
       |---|---|
       | 不接 `config` + `invoke()` | **1 块**（整段，`on_llm_end` 吐的）＝**假流式** |
       | 接 `config` + `.stream(config)` | **N 块**、时间戳递增 ＝真流式 |

    ⚠️ **别只看"接口返回了 `text/event-stream` 就以为成了"** ——
       上面那两种写法**接口长得一模一样**，只有数块数才分得出来。

    ⛔ **别把本节点改成 `async def`** —— 实测会让**同步的** `graph.invoke()` 直接抛
       `TypeError: No synchronous function provided to "agent"`，而非流式路径
       （`/agent/langgraph_chat` · `api_v1.py` · `api_v1_rag.py`）**都在用它**。
       同步节点 + 同步 `.stream()` 就能真流式，⛔ 不需要 async。

    ⚠️ **聚合用 `AIMessageChunk.__add__`（LangChain 自带），⛔ 别手拼 content** ——
       `tool_calls` 是**碎片化**到达的（name 一块、args 几块）。
       只拼 `content` 会把 `tool_calls` 丢掉 ⇒ `should_continue` 判不出 `"approval"`
       ⇒ **B4 人工审批静默失效**，而接口返回 `{"status": "answered"}` 一切正常。
       守卫 ⇒ `api/test_agent_sse.py::test_agent_decide_preserves_tool_calls`
    """
    response = None
    for chunk in llm_with_tools.stream(state["messages"], config=config):
        # ⚠️ 用 `+` 合并，⛔ 不是 `response.content += chunk.content`：
        #    后者会丢掉 `tool_call_chunks`（见上面 ⚠️）。
        response = chunk if response is None else response + chunk
    # ⛔ **别在这里加 `if response is None: response = AIMessage(content="")` 兜底** ——
    #    那是**不可达代码**：模型吐零块时，langchain 的 `BaseChatModel.stream()` **自己会**
    #    `raise ValueError("No generation chunks were returned")`
    #    （`langchain_core/language_models/chat_models.py:551`，2026-10-03 实测），
    #    **永远不会返回一个空迭代器** ⇒ `response` 循环后必非 None。
    #    守卫 ⇒ `api/test_agent_sse.py::test_empty_stream_neither_writes_none_nor_returns_an_empty_answer`
    # 返回一个AIMessage，LangGraph会自动将它追加到messages中
    return {"messages": [response]}

def tool_execute(state: AgentState):
    """
    执行节点：解析模型的工具调用请求，执行工具，并返回ToolMessage。
    """
    last_message = state["messages"][-1]
    tool_messages = []

    for tc in last_message.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        # 找到对应的工具并执行
        if tool_name == "search":
            result = search_tool.invoke(tool_args["query"])
        elif tool_name == "calculator":
            result = calculator.invoke(tool_args)
        elif tool_name == "date_today":
            result = date_today.invoke(tool_args)
        else:
            result = f"未找到工具: {tool_name}"

        # 生成ToolMessage
        tool_msg = ToolMessage(
            content=str(result),
            tool_call_id=tc["id"],
            name=tool_name
        )
        tool_messages.append(tool_msg)

    return {"messages": tool_messages}

def needs_approval(tool_calls: list) -> bool:
    """这轮 tool_calls 里**有没有**需要人工审批的（B4）。

    ⚠️ 判据是「**有任何一个**」⇒ 混合调用（本地工具 + search_tool）**整体**审批，
       ⛔ 不能"挑着执行"—— 那等于给敏感调用开了个绕过口子。
    """
    names = {tc.get("name") for tc in tool_calls or []}
    return bool(names & SENSITIVE_TOOLS)


def should_continue(state: AgentState):
    """
    路由函数（B4 起是**三条**路，⛔ 不再是两条）：
      * 没有 tool_calls         ⇒ END（模型给出了最终答案）
      * 有 tool_calls **且含敏感** ⇒ "approval"（停下来等人批）
      * 只有**非敏感** tool_calls ⇒ "tools"（直接执行，⛔ 不再无谓地等人）
    """
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls:
        return END
    if needs_approval(tool_calls):
        return "approval"
    return "tools"

#  新增部分 人工审批节点
def human_approval(state: AgentState):
    """
    人工审批节点：什么也不做，只是一个用于暂停的中断点。
    """
    # 这里可以打印或记录日志，方便调试
    print("流程已暂停，等待人工审批...")
    return {}

# ==================== 构建图 ====================
def build_agent_graph():
    """构建并编译 LangGraph Agent 图（带人工审批）"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    # 新增审批节点
    workflow.add_node("approval", human_approval)

    # 设置图的入口点
    workflow.set_entry_point("agent")
    # 条件边：从 "agent" 出发，由 should_continue 决定去哪（B4 起是三条路）
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "approval": "approval",  # 含**敏感**工具 ⇒ 进审批节点（interrupt_before 在此暂停）
            "tools": "tools",        # 只有**本地**工具 ⇒ 直接执行，无人值守也能跑完
            END: END                 # 模型给了最终答案 ⇒ 结束
        }
    )

    # 审批通过后，从 "approval" 节点去 "tools" 节点执行工具
    workflow.add_edge("approval", "tools")
    # 工具执行完后，回到 "agent" 继续思考
    # 添加普通边：工具执行完后，总是回到"agent"节点继续思考
    workflow.add_edge("tools", "agent")

    # 编译图
    memory = MemorySaver()  # 用于持久化状态
    # 关键：interrupt_before=["approval"] 告诉 LangGraph 在进入审批节点前暂停
    return workflow.compile(checkpointer=memory, interrupt_before=["approval"])

# 启动自检：白名单为空 ⇒ 直接起不来（⛔ 别让它"静默地永不触发"，那是验收时才发现的失败）
validate_approval_config()

# 创建全局 graph 实例
agent_graph = build_agent_graph()