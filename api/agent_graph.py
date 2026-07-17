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
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from datetime import datetime

# ==================== 初始化模型 ====================
llm = ChatOpenAI(
    model="qwen-turbo",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0
)

# ==================== 定义工具 ====================
@tool
def calculator(expression: str) -> str:
    """计算数学表达式，例如 3*4-5/6。"""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算错误: {e}"

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

# ==================== 定义 Agent 的状态 ====================
class AgentState(TypedDict):
    # 对话历史消息列表。operator.add 表示新消息会被追加到末尾，而不是覆盖。
    messages: Annotated[List, operator.add]

# ==================== 定义节点函数 ====================
def agent_decide(state: AgentState):
    """
    决策节点：调用模型，让它决定是回复文本还是调用工具。
    """
    response = llm_with_tools.invoke(state["messages"])
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

def should_continue(state: AgentState):
    """
    路由函数：检查最后一条消息是否包含tool_calls。
    如果包含，说明模型想调用工具，路由到"tools"节点。
    如果不包含，说明模型给出了最终答案，路由到END结束。
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

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
    # 关键修改：从 "agent" 节点出发，不再直接去 "tools"
    # 而是先去 "approval" 审批节点
    # 添加条件边：从"agent"节点出发，根据should_continue函数决定下一步
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "approval",  # 改动如果需要调用工具，去"tools"节点,改为去审批节点
            END: END              # 如果结束，直接终止
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

# 创建全局 graph 实例
agent_graph = build_agent_graph()